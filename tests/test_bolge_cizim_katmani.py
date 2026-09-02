"""Bölge çizimi TEK katman: bölgeyi ya sunucu ya tuval çizer, ikisi birden asla.

Neden bu testler var:

Bölge, bir zamanlar İKİ kez çiziliyordu — biri önizleme JPEG'inin içine
(sunucu, mor), diğeri o JPEG'in üstündeki tuvale (tarayıcı, turuncu). Ekranda
tek bölgenin iki ayrı çizgisi görünüyordu; tuval ile görüntü ölçüsü birebir
oturmadığında çizgiler birbirinden kayıyor ve kullanıcı "sistem bölgeyi yanlış
görüyor" sanıyordu. Oysa sistem doğru görüyordu, ekran yanlış gösteriyordu.

Kural şu: bölge çizim/düzenleme sayfasında bölgeleri YALNIZCA tuval çizer
(görüntü sunucudan bölgesiz istenir), izleme ekranlarında ise YALNIZCA sunucu
çizer. Renk her iki yolda da aynıdır, yoksa aynı bölge sayfadan sayfaya renk
değiştirmiş gibi görünür.

İkinci konu tuvalin ölçüsü: tuvalin çizim tamponu görüntünün ekrandaki
kutusuyla birebir aynı olmalıdır. Sabit bir bekleme süresine güvenilemez —
önizleme her saniye yeni bir kare yükler ve görüntü gelene kadar kutunun
yüksekliği yanlıştır. Ölçü GÖRÜNTÜNÜN yüklenmesine ve kutunun ölçü
değişimine bağlanır.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.analiz.boru_hatti import _BOLGE_RENGI, _RENKLER, KameraHatti
from app.rules.tipler import Bolge, Tespit

_JS = Path("backend/app/web/static/kamera_detay.js")
_ONIZLEME_JS = Path("backend/app/web/static/onizleme.js")


def _hex_kod(bgr) -> str:  # BGR -> #RRGGBB
    return f"#{bgr[2]:02X}{bgr[1]:02X}{bgr[0]:02X}"


def _renk_piksel_sayisi(jpeg: bytes, bgr) -> int:
    """JPEG içinde verilen renge YAKIN piksel sayısı (sıkıştırma payı bırakılır)."""
    dizi = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert dizi is not None, "JPEG çözülemedi"
    fark = np.abs(dizi.astype(np.int16) - np.array(bgr, dtype=np.int16)).sum(axis=2)
    return int((fark < 90).sum())


def _hat_kur() -> KameraHatti:
    hat = KameraHatti(kamera_id=1, fps=6)
    bolge = Bolge(
        id=1,
        tip="restricted",
        poligon=[(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)],
    )
    hat.yapilandir([bolge], [], None)
    return hat


def _kare_isle(hat: KameraHatti) -> None:
    kare = np.full((480, 640, 3), 128, dtype=np.uint8)  # düz gri zemin
    kisi = Tespit(sinif="person", kutu=(40.0, 40.0, 100.0, 200.0), takip_id=7)
    hat._overlay_guncelle(kare, [kisi], [])


# ---- sunucu tarafı: bölgeli ve bölgesiz sürüm ----


def test_bolgesiz_surumde_bolge_cizgisi_yok():
    """Çizim sayfasına giden karede bölge ÇİZİLİ OLMAMALI — o sayfada bölgeyi
    tuval çiziyor; sunucu da çizerse aynı bölge ekranda iki kez görünür."""
    hat = _hat_kur()
    _kare_isle(hat)

    bolgeli = hat.son_islenmis_jpeg()
    bolgesiz = hat.son_islenmis_jpeg(bolgeler_dahil=False)
    assert bolgeli is not None and bolgesiz is not None

    assert _renk_piksel_sayisi(bolgeli, _BOLGE_RENGI) > 100, "izleme karesinde bölge çizilmemiş"
    assert _renk_piksel_sayisi(bolgesiz, _BOLGE_RENGI) == 0, (
        "çizim sayfasına giden karede bölge çizgisi var — bölge iki kez görünür"
    )


def test_bolgesiz_surum_tespit_kutularini_korur():
    """Bölgesiz sürüm HAM kare değildir: tespit kutuları orada da durmalı,
    yoksa çizim sayfasında sistemin ne gördüğü görünmez olur."""
    hat = _hat_kur()
    _kare_isle(hat)

    bolgesiz = hat.son_islenmis_jpeg(bolgeler_dahil=False)
    assert bolgesiz is not None
    assert _renk_piksel_sayisi(bolgesiz, _RENKLER["person"]) > 50


def test_bolge_yokken_iki_surum_ayni():
    """Bölge yoksa ikinci bir JPEG kodlamaya gerek yok — aynı kare döner."""
    hat = KameraHatti(kamera_id=1, fps=6)
    hat.yapilandir([], [], None)
    _kare_isle(hat)

    assert hat.son_islenmis_jpeg() == hat.son_islenmis_jpeg(bolgeler_dahil=False)


# ---- hangi sayfa hangi sürümü istiyor ----


def test_cizim_sayfasi_bolgesiz_kare_ister(istemci, test_ayarlari):
    """Kamera detay (çizim) sayfası bölgesiz kare ister; kamera LİSTESİ ise
    istemez — orada tuval yok, bölgeyi sunucu çizmeli."""
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "K1", "source_type": "file", "source_url": str(video), "sample_fps": "6"},
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])

    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert 'data-bolgesiz="1"' in detay

    liste = istemci.get("/kameralar").text
    assert "data-bolgesiz" not in liste


def test_onizleme_rotasi_bolgesiz_parametresini_iletir(istemci, test_ayarlari):
    """?bolgesiz=1 sorusu süpervizöre 'bölgeleri çizme' olarak gitmeli."""
    istekler: list[bool] = []

    class SahteSupervizor:
        def onizleme_jpeg(self, kamera_id: int, bolgeler_dahil: bool = True):
            istekler.append(bolgeler_dahil)
            return None

    istemci.app.state.supervizor = SahteSupervizor()
    try:
        istemci.get("/kameralar/1/onizleme.jpg")
        istemci.get("/kameralar/1/onizleme.jpg?bolgesiz=1")
    finally:
        istemci.app.state.supervizor = None

    assert istekler == [True, False]


def test_onizleme_js_bolgesiz_adresi_kurar():
    """Tarayıcı tarafı: data-bolgesiz taşıyan görüntü bölgesiz kare istemeli."""
    kaynak = _ONIZLEME_JS.read_text(encoding="utf-8")
    assert "bolgesiz" in kaynak
    assert "?bolgesiz=1" in kaynak


# ---- tuval: renk ve ölçü ----


def test_tuvalin_bolge_rengi_sunucuyla_ayni():
    """Aynı bölge, sayfadan sayfaya renk değiştirmemeli: tuvalin çizdiği renk
    sunucunun çizdiği renkle (ve renk anahtarıyla) birebir aynı olmalı."""
    kaynak = _JS.read_text(encoding="utf-8")
    hex_kod = _hex_kod(_BOLGE_RENGI)
    assert hex_kod in kaynak, f"tuval bölgeyi {hex_kod} ile çizmeli"

    anahtar = Path("backend/app/web/templates/renk_anahtari.html").read_text(encoding="utf-8")
    assert hex_kod in anahtar


def test_tuval_olcusu_goruntuye_bagli():
    """Ölçü, görüntünün YÜKLENMESİNE ve kutunun ölçü değişimine bağlı olmalı.
    Sabit bekleme süresi (setTimeout) yeterli değildir: önizleme her saniye yeni
    kare yükler, kare 150 ms'de gelmemiş olabilir ve tuval yanlış ölçüde kalır —
    o zaman tıkladığınız yer ile çizilen nokta kayar."""
    kaynak = _JS.read_text(encoding="utf-8")
    assert 'resim.addEventListener("load"' in kaynak
    assert "ResizeObserver" in kaynak
    assert "setTimeout(boyutla" not in kaynak, "ölçü hâlâ sabit bekleme süresine bağlı"


def test_tiklamadan_once_olcu_esitleniyor():
    """Tıklama anında tampon ile ekran ölçüsü eşit değilse nokta kayar."""
    kaynak = _JS.read_text(encoding="utf-8")
    tiklama = kaynak.split('tuval.addEventListener("click"', 1)[1]
    assert "boyutuEsitle()" in tiklama.split("});", 1)[0]

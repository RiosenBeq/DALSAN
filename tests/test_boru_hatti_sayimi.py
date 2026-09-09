"""Sayımın GERÇEK boru hattında çalıştığının kanıtı (analiz/boru_hatti.py).

Kural motoru testleri saf veriyle çalışır; bu test bir adım ötesini sınar:
sahte bir tespitçiyle beslenen hat, bölge sayımını üretiyor mu ve sayı
görüntünün üstüne yazılıyor mu? Kullanıcının "videoda kolayca sayması"
beklentisi bu iki şeye bağlıdır.

Model GEREKMEZ: tespitçi yerine sabit kutu döndüren bir taklit kullanılır.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.analiz.boru_hatti import KameraHatti
from app.analiz.kkd_siniflandirici import KkdSiniflandirici
from app.rules.tipler import Bolge

GENISLIK, YUKSEKLIK = 640, 480

# Karenin ortasında bir bölge (normalize)
ORTA_BOLGE = Bolge(
    id=1,
    tip="loading_area",
    poligon=[(0.25, 0.25), (0.75, 0.25), (0.75, 0.85), (0.25, 0.85)],
)


class SahteTespitci:
    """Her karede aynı kutuları döndürür — takip kimliği kararlı kalsın."""

    def __init__(self, kutular, siniflar):
        self._kutular = np.array(kutular, dtype=float)
        self._siniflar = np.array(siniflar)

    def tespit_et(self, kare):
        guvenler = np.full(len(self._kutular), 0.9)
        return self._kutular, guvenler, self._siniflar


@pytest.fixture
def kare():
    return np.full((YUKSEKLIK, GENISLIK, 3), 90, np.uint8)


def _hat():
    hat = KameraHatti(kamera_id=1, fps=6)
    hat.yapilandir([ORTA_BOLGE], [], None)
    return hat


def _besle(hat, kare, tespitci, kere=6):
    """Aynı kareyi birkaç kez işler: takip ve sayım kararlılık istiyor."""
    kkd = KkdSiniflandirici(None)
    for i in range(kere):
        hat.isle(kare, float(i), tespitci, kkd)


def test_bolgedeki_kisi_sayilir(kare):
    """Bölgenin ortasında duran kişi hem 'içeride' hem 'giren' sayılmalı."""
    hat = _hat()
    # Ayak noktası (alt-orta) bölgenin içinde: x=320, y=300
    _besle(hat, kare, SahteTespitci([[290, 150, 350, 300]], ["person"]))
    sayimlar = hat.sayimlar()
    assert len(sayimlar) == 1
    assert sayimlar[0]["bolge_id"] == 1
    assert sayimlar[0]["anlik"] == {"person": 1}
    assert sayimlar[0]["giren"] == {"person": 1}


def test_bolge_disindaki_kisi_sayilmaz(kare):
    hat = _hat()
    # Ayak noktası y=460 → normalize 0,958: bölgenin (0,85) altında
    _besle(hat, kare, SahteTespitci([[300, 380, 340, 460]], ["person"]))
    assert hat.sayimlar()[0]["anlik"] == {}


def test_kare_sayimi_bolgeden_bagimsiz(kare):
    """Bölge dışındaki nesne de karede görünüyor: kullanıcı 'sistem bir şey
    görüyor mu' sorusunun cevabını almalı."""
    hat = _hat()
    _besle(hat, kare, SahteTespitci([[300, 380, 340, 460]], ["person"]))
    assert hat.kare_sayimi() == {"person": 1}


def test_ayni_kisi_uzun_sure_kalinca_bir_kez_sayilir(kare):
    """Kare bazlı sayım olsaydı 60 karede 60 'kişi' üretilirdi."""
    hat = _hat()
    _besle(hat, kare, SahteTespitci([[290, 150, 350, 300]], ["person"]), kere=60)
    assert hat.sayimlar()[0]["giren"] == {"person": 1}


def test_sayac_sifirlama_gireni_siler(kare):
    hat = _hat()
    tespitci = SahteTespitci([[290, 150, 350, 300]], ["person"])
    _besle(hat, kare, tespitci)
    assert hat.sayimlar()[0]["giren"] == {"person": 1}
    hat.sayaci_sifirla()
    # Sıfırlamadan sonraki ilk karede aynı kişi YENİDEN sayılır (yeni vardiya)
    _besle(hat, kare, tespitci, kere=1)
    assert hat.sayimlar()[0]["giren"] == {"person": 1}


def test_sayim_rozeti_goruntuye_cizilir(kare):
    """Sayı videonun ÜSTÜNDE görünmeli: kullanıcı sayıyı saydığı yerde arar."""
    bos_hat = _hat()
    kkd = KkdSiniflandirici(None)
    bos_hat.isle(kare, 0.0, SahteTespitci(np.empty((0, 4)), np.array([])), kkd)
    bossuz = bos_hat.son_islenmis_jpeg()

    dolu_hat = _hat()
    _besle(dolu_hat, kare, SahteTespitci([[290, 150, 350, 300]], ["person"]))
    dolu = dolu_hat.son_islenmis_jpeg()

    assert bossuz and dolu
    # Rozet + kutu çizildiği için görüntü belirgin biçimde farklı olmalı
    a = cv2.imdecode(np.frombuffer(bossuz, np.uint8), cv2.IMREAD_COLOR)
    b = cv2.imdecode(np.frombuffer(dolu, np.uint8), cv2.IMREAD_COLOR)
    assert float(np.abs(a.astype(int) - b.astype(int)).mean()) > 0.5


def test_bos_bolgeye_rozet_cizilmez(kare):
    """Altı bölgeli bir kamerada altı tane '0' yalnızca gürültüdür."""
    hat = _hat()
    kkd = KkdSiniflandirici(None)
    hat.isle(kare, 0.0, SahteTespitci(np.empty((0, 4)), np.array([])), kkd)
    assert hat.sayimlar()[0]["anlik"] == {}


def test_pasif_bolge_sayilmaz(kare):
    hat = KameraHatti(kamera_id=1, fps=6)
    pasif = Bolge(id=1, tip="loading_area", poligon=ORTA_BOLGE.poligon, aktif=False)
    hat.yapilandir([pasif], [], None)
    _besle(hat, kare, SahteTespitci([[290, 150, 350, 300]], ["person"]))
    assert hat.sayimlar() == []


def test_tanimayan_sinif_kamerayi_korletmez(kare):
    """Modele yeni bir sınıf eklenirse takip katmanı ÇÖKMEMELİ; o kamera
    her karede hata verip kalıcı olarak körleşirdi."""
    hat = _hat()
    tespitci = SahteTespitci([[290, 150, 350, 300], [100, 100, 160, 200]], ["person", "vinc"])
    _besle(hat, kare, tespitci)
    # Bilinmeyen sınıf atlandı, insan yine sayıldı
    assert hat.sayimlar()[0]["anlik"] == {"person": 1}


# --------------------------------------------------------------- tarama


def test_bolge_ici_tarali_cizilir(kare):
    """Kullanıcı "alanın içi neresi" sorusunu VİDEOYA bakarak cevaplamalı.

    Yalnız çerçeve çizmek yetmiyordu: yan yana iki bölgede hangi çizginin
    hangisine ait olduğu anlaşılmıyordu.
    """
    hat = _hat()
    kkd = KkdSiniflandirici(None)
    bos = SahteTespitci(np.empty((0, 4)), np.array([]))
    hat.isle(kare, 0.0, bos, kkd)
    gorsel = cv2.imdecode(np.frombuffer(hat.son_islenmis_jpeg(), np.uint8), cv2.IMREAD_COLOR)

    # Bölgenin İÇİ (0,25-0,75 x, 0,25-0,85 y) taralı → renk değişkenliği var.
    ic = gorsel[
        int(0.35 * YUKSEKLIK) : int(0.7 * YUKSEKLIK), int(0.35 * GENISLIK) : int(0.65 * GENISLIK)
    ]
    dis = gorsel[0 : int(0.15 * YUKSEKLIK), 0 : int(0.9 * GENISLIK)]
    assert ic.std() > 5.0, "bölge içi taranmamış"
    assert dis.std() < 3.0, "bölge dışına taşmış"


def test_tarama_alttaki_goruntuyu_ortmez(kare):
    """Tarama bir VURGU, örtü değil: alandaki insan görünmeye devam etmeli."""
    hat = _hat()
    _besle(hat, kare, SahteTespitci([[290, 150, 350, 300]], ["person"]))
    gorsel = cv2.imdecode(np.frombuffer(hat.son_islenmis_jpeg(), np.uint8), cv2.IMREAD_COLOR)
    # Kişi kutusunun YEŞİL kenarı hâlâ bulunabilmeli (G kanalı baskın piksel)
    dilim = gorsel[150:300, 285:355].astype(int)
    yesil_baskin = (
        (dilim[:, :, 1] > dilim[:, :, 0] + 25) & (dilim[:, :, 1] > dilim[:, :, 2] + 25)
    ).sum()
    assert yesil_baskin > 50, "tespit kutusu taramanın altında kaybolmuş"


def test_tarama_maskesi_onbelleklenir(kare):
    """Her karede yeniden üretmek 7x24 çalışmada boşa harcanan işlemcidir."""
    hat = _hat()
    kkd = KkdSiniflandirici(None)
    bos = SahteTespitci(np.empty((0, 4)), np.array([]))
    hat.isle(kare, 0.0, bos, kkd)
    ilk = hat._tarama_maskesi
    hat.isle(kare, 1.0, bos, kkd)
    assert hat._tarama_maskesi is ilk, "maske yeniden üretilmiş"


def test_bolge_degisince_tarama_yenilenir(kare):
    """Bölge yeniden çizilince tarama eski çizime takılı kalmamalı."""
    hat = _hat()
    kkd = KkdSiniflandirici(None)
    bos = SahteTespitci(np.empty((0, 4)), np.array([]))
    hat.isle(kare, 0.0, bos, kkd)
    ilk = hat._tarama_maskesi
    hat.yapilandir(
        [Bolge(id=1, tip="loading_area", poligon=[(0.1, 0.1), (0.4, 0.1), (0.4, 0.4), (0.1, 0.4)])],
        [],
        None,
    )
    hat.isle(kare, 1.0, bos, kkd)
    assert hat._tarama_maskesi is not ilk


def test_kare_disina_dusen_bolge_cokmez(kare):
    """Poligon tümüyle kare dışındaysa tarama sessizce atlanmalı."""
    hat = KameraHatti(kamera_id=1, fps=6)
    hat.yapilandir(
        [Bolge(id=1, tip="restricted", poligon=[(0.0, 0.0), (0.0, 0.0), (0.0, 0.0)])], [], None
    )
    hat.isle(kare, 0.0, SahteTespitci(np.empty((0, 4)), np.array([])), KkdSiniflandirici(None))
    assert hat.son_islenmis_jpeg() is not None

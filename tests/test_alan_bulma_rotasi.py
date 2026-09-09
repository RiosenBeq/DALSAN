"""\"Alanları Otomatik Bul\" rotası (app/web/alan_rotalari.py).

Sınanan sözler:
  · Ekran görüntüsü yüklenince alan önerisi döner (kamera bağlı olmasa bile).
  · Yüklenen görüntü DİSKE YAZILMAZ (KVKK — alan_rotalari.py başlığı).
  · Bulunamadığında hata değil, ne yapılacağını söyleyen Türkçe cümle döner.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from tests.test_alan_bulucu import yaya_yolu_zemini, zemin


@pytest.fixture
def kamera_id(istemci):
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Sevkiyat kapısı",
            "area": "Sevkiyat",
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.5/akis",
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return 1


def _jpeg(kare: np.ndarray) -> bytes:
    tamam, veri = cv2.imencode(".jpg", kare)
    assert tamam
    return veri.tobytes()


def test_yuklenen_ekran_goruntusunden_alan_bulunur(istemci, kamera_id):
    yanit = istemci.post(
        f"/kameralar/{kamera_id}/alan-bul",
        files={"gorsel": ("ekran.jpg", _jpeg(yaya_yolu_zemini()), "image/jpeg")},
    )
    assert yanit.status_code == 200
    veri = yanit.json()
    assert veri["tamam"] is True
    assert veri["oneriler"], veri["mesaj"]
    ilk = veri["oneriler"][0]
    assert ilk["tip"] == "pedestrian_path"
    assert ilk["tip_adi"] == "Yaya yolu"
    assert len(ilk["poligon"]) >= 3
    assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in ilk["poligon"])
    assert 0 <= ilk["guven_yuzde"] <= 100


def test_yuklenen_goruntu_tuvale_arka_plan_olarak_doner(istemci, kamera_id):
    """Kamera bağlı değilken çizim yapılabilmesi buna bağlı."""
    yanit = istemci.post(
        f"/kameralar/{kamera_id}/alan-bul",
        files={"gorsel": ("ekran.jpg", _jpeg(yaya_yolu_zemini()), "image/jpeg")},
    )
    assert yanit.json()["gorsel"].startswith("data:image/jpeg;base64,")


def test_yuklenen_goruntu_diske_yazilmaz(istemci, kamera_id, test_ayarlari):
    """KVKK: fabrika karesinde çalışanlar var; saklamadığımız görüntü
    saklama süresi ve silme sorusu doğurmaz."""
    once = {p for p in test_ayarlari.veri_dizini.rglob("*") if p.is_file()}
    istemci.post(
        f"/kameralar/{kamera_id}/alan-bul",
        files={"gorsel": ("ekran.jpg", _jpeg(yaya_yolu_zemini()), "image/jpeg")},
    )
    sonra = {p for p in test_ayarlari.veri_dizini.rglob("*") if p.is_file()}
    yeni = {p.name for p in sonra - once if p.suffix.lower() in (".jpg", ".jpeg", ".png")}
    assert not yeni, f"Yüklenen görüntü diske yazılmış: {yeni}"


def test_boyasiz_zeminde_yol_gosteren_mesaj_doner(istemci, kamera_id):
    yanit = istemci.post(
        f"/kameralar/{kamera_id}/alan-bul",
        files={"gorsel": ("ekran.jpg", _jpeg(zemin()), "image/jpeg")},
    )
    assert yanit.status_code == 200  # hata DEĞİL: bulunamamak olağandır
    veri = yanit.json()
    assert veri["tamam"] is False
    assert veri["oneriler"] == []
    assert "elle çizin" in veri["mesaj"]


def test_bulunamayinca_teshis_goruntusu_doner(istemci, kamera_id):
    """ "Neden bulamadı" sorusunun cevabı ekranda görünmeli: sistemin boya
    saydığı yerler işaretli bir görsel döner."""
    veri = istemci.post(
        f"/kameralar/{kamera_id}/alan-bul",
        files={"gorsel": ("ekran.jpg", _jpeg(zemin()), "image/jpeg")},
    ).json()
    assert veri["teshis"].startswith("data:image/jpeg;base64,")


def test_bulununca_teshis_uretilmez(istemci, kamera_id):
    """Bulunduğunda kimse sormaz; her istekte ikinci JPEG kodlamak boşa işlemci."""
    veri = istemci.post(
        f"/kameralar/{kamera_id}/alan-bul",
        files={"gorsel": ("ekran.jpg", _jpeg(yaya_yolu_zemini()), "image/jpeg")},
    ).json()
    assert veri["tamam"] is True
    assert veri["teshis"] is None


def test_bozuk_dosya_anlasilir_cumleyle_reddedilir(istemci, kamera_id):
    yanit = istemci.post(
        f"/kameralar/{kamera_id}/alan-bul",
        files={"gorsel": ("belge.jpg", b"bu bir goruntu degil", "image/jpeg")},
    )
    veri = yanit.json()
    assert veri["tamam"] is False
    assert "görüntü olarak açılamadı" in veri["mesaj"]


def test_dosyasiz_istek_kamera_baglantisiz_iken_yol_gosterir(istemci, kamera_id):
    """Analiz kapalı (test) → canlı kare yok. Kullanıcı çıkmaza girmemeli."""
    yanit = istemci.post(f"/kameralar/{kamera_id}/alan-bul")
    veri = yanit.json()
    assert veri["tamam"] is False
    assert "ekran görüntüsü" in veri["mesaj"]


def test_olmayan_kamera(istemci):
    veri = istemci.post("/kameralar/999/alan-bul").json()
    assert veri["tamam"] is False
    assert "Kamera bulunamadı" in veri["mesaj"]


def test_onerilen_poligon_bolge_olarak_kaydedilebilir(istemci, kamera_id):
    """Önerinin gerçek değeri, kaydedilebilmesidir: aynı doğrulamadan geçmeli."""
    oneri = istemci.post(
        f"/kameralar/{kamera_id}/alan-bul",
        files={"gorsel": ("ekran.jpg", _jpeg(yaya_yolu_zemini()), "image/jpeg")},
    ).json()["oneriler"][0]

    import json

    kayit = istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": "Ana yaya yolu",
            "zone_type": oneri["tip"],
            "polygon": json.dumps(oneri["poligon"]),
        },
        follow_redirects=False,
    )
    assert kayit.status_code == 303
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert "Ana yaya yolu" in sayfa

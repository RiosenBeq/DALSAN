"""Kamera yönetimi testleri: CRUD, maskeleme, bölge ve kalibrasyon uçları."""

from __future__ import annotations


def _kamera_ekle(istemci, ad="Test Kamera", url="rtsp://admin:gizli123@10.0.0.5:554/ana"):
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": ad,
            "area": "Sevkiyat",
            "source_type": "rtsp",
            "source_url": url,
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return int(yanit.headers["location"].rsplit("/", 1)[1])


def test_kamera_ekleme_ve_listeleme(istemci):
    kamera_id = _kamera_ekle(istemci)
    liste = istemci.get("/kameralar").text
    assert "Test Kamera" in liste
    assert "Sevkiyat" in liste
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "Test Kamera" in detay


def test_rtsp_sifresi_listede_maskelenir(istemci):
    _kamera_ekle(istemci, url="rtsp://admin:cokgizli@10.0.0.5:554/kanal1")
    liste = istemci.get("/kameralar").text
    assert "cokgizli" not in liste  # şifre asla listede görünmez
    assert "••••@10.0.0.5" in liste


def test_gecersiz_kamera_reddedilir(istemci):
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "X",
            "source_type": "rtsp",
            "source_url": "http://yanlis-protokol",
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    assert "rtsp://" in yanit.json()["hata"]


def test_kamera_silinince_bolgeleri_de_silinir(istemci):
    kamera_id = _kamera_ekle(istemci)
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": "Rampa",
            "zone_type": "ppe_required",
            "polygon": "[[0.1,0.1],[0.9,0.1],[0.9,0.9]]",
        },
        follow_redirects=False,
    )
    assert "Rampa" in istemci.get(f"/kameralar/{kamera_id}").text
    istemci.post(f"/kameralar/{kamera_id}/sil", follow_redirects=False)
    assert "Test Kamera" not in istemci.get("/kameralar").text


def test_bolge_en_az_uc_nokta(istemci):
    kamera_id = _kamera_ekle(istemci)
    yanit = istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={"name": "Eksik", "zone_type": "restricted", "polygon": "[[0.1,0.1],[0.9,0.1]]"},
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    assert "3 nokta" in yanit.json()["hata"]


def test_bolge_adi_xss_kacirilir(istemci):
    """Depolanan XSS engeli: bölge adı script bloğuna ham basılmamalı."""
    kamera_id = _kamera_ekle(istemci)
    zararli = "</script><img src=x onerror=alert(1)>"
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": zararli,
            "zone_type": "restricted",
            "polygon": "[[0.1,0.1],[0.9,0.1],[0.9,0.9]]",
        },
        follow_redirects=False,
    )
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "</script><img" not in detay  # ham payload asla sayfada olmamalı
    assert "\\u003c/script\\u003e" in detay  # kaçırılmış hali script verisinde
    # Kural formundaki bölge listesi de aynı veriyi basar
    form = istemci.get(f"/kurallar/yeni?kamera={kamera_id}").text
    assert "</script><img" not in form


def test_kalibrasyon_kaydi_ve_silme(istemci):
    kamera_id = _kamera_ekle(istemci)
    yanit = istemci.post(
        f"/kameralar/{kamera_id}/kalibrasyon",
        data={
            "image_points": "[[0,0],[1,0],[1,1],[0,1]]",
            "world_points": "[[0,0],[10,0],[10,10],[0,10]]",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert "kalibre —" in istemci.get(f"/kameralar/{kamera_id}").text
    istemci.post(f"/kameralar/{kamera_id}/kalibrasyon/sil", follow_redirects=False)
    assert "kalibre değil" in istemci.get(f"/kameralar/{kamera_id}").text


def test_dogru_uzerindeki_kalibrasyon_noktalari_reddedilir(istemci):
    kamera_id = _kamera_ekle(istemci)
    yanit = istemci.post(
        f"/kameralar/{kamera_id}/kalibrasyon",
        data={
            "image_points": "[[0.1,0.1],[0.2,0.2],[0.3,0.3],[0.4,0.4]]",
            "world_points": "[[0,0],[1,1],[2,2],[3,3]]",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 400

"""Ek hazır kurallar ve kalibrasyon bekleyen kritik kural (docs/17 §6.4, §8.2; Faz 2c-4).

- Yaya yolunda araç ve araç yolunda yaya: birincil hazır kuralın YANINA
  kurulur, gölge modda doğar (olay yazılır, hoparlör susar) ve şema 007'nin
  mesajına bağlanır.
- Etkin güvenli mesafe / hız kuralı kalibrasyonsuz kamerada çalışmaz: kurulum
  listesi bunu kırmızı madde olarak söyler, /saglik `kritik_kural_pasif` verir.
"""

from __future__ import annotations

import json

from app import veritabani, zaman
from app.web.ortak import EK_HAZIR_KURALLAR, HAZIR_KURALLAR


def _kamera_ve_bolge(istemci, test_ayarlari, tip: str, ad: str = "Alan") -> tuple[int, int]:
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "Rampa", "source_type": "file", "source_url": str(video), "sample_fps": "6"},
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": ad,
            "zone_type": tip,
            "polygon": "[[0.25,0.25],[0.75,0.25],[0.75,0.75],[0.25,0.75]]",
        },
        follow_redirects=False,
    )
    return kamera_id, _satirlar(test_ayarlari, "SELECT MAX(id) AS m FROM zones")[0]["m"]


def _satirlar(test_ayarlari, sorgu: str, parametreler: tuple = ()) -> list[dict]:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return [dict(s) for s in baglanti.execute(sorgu, parametreler)]
    finally:
        baglanti.close()


def _mesaj_id(test_ayarlari, anahtar: str) -> int:
    return _satirlar(
        test_ayarlari, "SELECT id FROM announcement_messages WHERE key = ?", (anahtar,)
    )[0]["id"]


def test_ek_kurallar_golgede_dogar_ve_yeni_mesaja_baglanir(istemci, test_ayarlari):
    for tip, (ek,) in EK_HAZIR_KURALLAR.items():
        kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, tip, f"Alan {tip}")
        yanit = istemci.post(
            "/kurallar/hazir",
            data={"zone_id": str(bolge_id), "ek": ek.anahtar},
            follow_redirects=False,
        )
        assert yanit.status_code == 303, yanit.text
        (kural,) = _satirlar(test_ayarlari, "SELECT * FROM rules WHERE zone_id = ?", (bolge_id,))
        assert kural["shadow_mode"] == 1, "ek kural gölge modda doğmalı"
        assert kural["enabled"] == 1
        assert kural["announcement_id"] == _mesaj_id(test_ayarlari, ek.anons_anahtari)
        assert sorted(json.loads(kural["target_classes"])) == sorted(ek.hedef_siniflar)
        params = json.loads(kural["params"])
        assert params["mode"] == "inside" and params["gecit_haric"] is True


def test_birincil_ve_ek_kural_ayni_bolgede_yan_yana(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, "pedestrian_path", "Koridor")
    ek = EK_HAZIR_KURALLAR["pedestrian_path"][0]
    birincil = HAZIR_KURALLAR["pedestrian_path"]

    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert f'"Koridor" için {birincil.kisa_ad} ekle' in sayfa
    assert f'"Koridor" için {ek.kisa_ad} ekle (gölge modda)' in sayfa

    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert f"{birincil.kisa_ad} ekle" not in sayfa, "kurulan kuralın düğmesi kalkar"
    assert f"{ek.kisa_ad} ekle" in sayfa, "ek kural hâlâ kurulabilir"

    istemci.post(
        "/kurallar/hazir", data={"zone_id": str(bolge_id), "ek": ek.anahtar}, follow_redirects=False
    )
    yanit = istemci.post(
        "/kurallar/hazir", data={"zone_id": str(bolge_id), "ek": ek.anahtar}, follow_redirects=False
    )
    assert yanit.status_code == 400 and "zaten bir kural var" in yanit.json()["hata"]
    kurallar = _satirlar(test_ayarlari, "SELECT shadow_mode FROM rules ORDER BY id")
    assert [k["shadow_mode"] for k in kurallar] == [0, 1]
    assert "Hazır kurallar" not in istemci.get(f"/kameralar/{kamera_id}").text


def test_bilinmeyen_ek_kural_reddedilir(istemci, test_ayarlari):
    _, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, "restricted")
    yanit = istemci.post(
        "/kurallar/hazir",
        data={"zone_id": str(bolge_id), "ek": "yok_boyle"},
        follow_redirects=False,
    )
    assert yanit.status_code == 400


# ------------------------------------------------------------------ kalibrasyon bekleyen


def test_kalibrasyonsuz_mesafe_kurali_kurulum_listesinde_ve_saglikta(istemci, test_ayarlari):
    assert istemci.get("/saglik").json()["sorunlar"] == []

    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, "vehicle_area", "Saha")
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)

    assert istemci.get("/saglik").json()["sorunlar"] == ["kritik_kural_pasif"]
    komuta = istemci.get("/komuta").text
    assert "Mesafe ve hız kuralları çalışıyor mu?" in komuta
    assert "Kalibrasyon bekleniyor: Rampa kamerasındaki güvenli mesafe kuralı" in komuta

    # Kalibrasyon yapılınca madde kalkar
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        baglanti.execute(
            "INSERT INTO camera_calibrations (camera_id, image_points, world_points, homography, "
            "calibrated_at) VALUES (?, '[]', '[]', '[[1,0,0],[0,1,0],[0,0,1]]', ?)",
            (kamera_id, zaman.simdi_utc()),
        )
        baglanti.commit()
    finally:
        baglanti.close()
    assert istemci.get("/saglik").json()["sorunlar"] == []
    assert "Mesafe ve hız kuralları çalışıyor mu?" not in istemci.get("/komuta").text


def test_kalibrasyon_maddesi_cogulu_dogru_yazar():
    """Tek kamera/kural: "kamerasındaki … kuralı"; birden çoğu: "kameralarındaki … kuralları"."""
    from app.web.kilavuz import _kalibrasyon_adimi, _ve_ile

    assert [_ve_ile(x) for x in (["A"], ["A", "B"], ["A", "B", "C"])] == [
        "A",
        "A ve B",
        "A, B ve C",
    ]
    tek = _kalibrasyon_adimi(
        [{"kamera_adi": "Rampa", "kamera_id": 1, "rule_type": "safe_distance"}]
    )
    assert "Rampa kamerasındaki güvenli mesafe kuralı, kamera kalibre" in tek["aciklama"]
    cok = _kalibrasyon_adimi(
        [
            {"kamera_adi": "Saha", "kamera_id": 2, "rule_type": "safe_distance"},
            {"kamera_adi": "Rampa", "kamera_id": 1, "rule_type": "vehicle_speed"},
        ]
    )
    assert (
        "Rampa ve Saha kameralarındaki güvenli mesafe ve hız kuralları, kameralar kalibre"
        in cok["aciklama"]
    )
    assert cok["bag"] == "/kameralar/2"  # listenin ilk kuralının kamerası

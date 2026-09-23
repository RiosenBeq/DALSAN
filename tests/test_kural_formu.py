"""Kural formu: önem seçimi, yeni alanlar, şemadan varsayılanlar (docs/17 §6.2, R25; Faz 2c-4c).

- Önem "Varsayılan" (olay kodunun önemi) ya da açık bir düzeydir; varsayılanın
  ALTINA inmek onay ister ve bu, tarayıcıya güvenilmeden sunucuda denetlenir.
- `bitis_s`, `gecit_haric`, `histerezis_m` formda; kaydetmek formda olmayan bir
  parametreyi sessizce varsayılana döndürmez.
- Formun gösterdiği varsayılanlar şemadan gelir (rules/parametreler.py).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app import veritabani
from app.rules.parametreler import PARAM_SEMALARI, varsayilan_params
from app.web import kurallar as kurallar_web

SABLON = Path(kurallar_web.__file__).parent / "templates" / "kural_form.html"


def _satirlar(test_ayarlari, sorgu: str, parametreler: tuple = ()) -> list[dict]:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return [dict(s) for s in baglanti.execute(sorgu, parametreler)]
    finally:
        baglanti.close()


def _kamera_ve_bolge(istemci, test_ayarlari, tip: str = "restricted") -> tuple[int, int]:
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "Saha", "source_type": "file", "source_url": str(video), "sample_fps": "6"},
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": "Alan",
            "zone_type": tip,
            "polygon": "[[0.25,0.25],[0.75,0.25],[0.75,0.75],[0.25,0.75]]",
        },
        follow_redirects=False,
    )
    return kamera_id, _satirlar(test_ayarlari, "SELECT MAX(id) AS m FROM zones")[0]["m"]


def _bolge_kurali(kamera_id: int, bolge_id: int, **ek) -> dict:
    return {
        "camera_id": str(kamera_id),
        "rule_type": "zone_intrusion",
        "zone_id": str(bolge_id),
        "target_classes": ["person"],
        "mode": "inside",
        "min_dwell_s": "2",
        "cooldown_s": "120",
        "enabled": "1",
        **ek,
    }


def _kaydet(istemci, veri: dict):
    return istemci.post("/kurallar/kaydet", data=veri, follow_redirects=False)


def _kural(test_ayarlari) -> dict:
    satir = _satirlar(test_ayarlari, "SELECT * FROM rules ORDER BY id DESC LIMIT 1")[0]
    satir["params"] = json.loads(satir["params"])
    return satir


# ------------------------------------------------------------------ önem


def test_varsayilan_onem_warning_olarak_saklanir(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    assert _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id)).status_code == 303
    assert _kural(test_ayarlari)["severity"] == "warning"


def test_onemi_yukseltmek_onay_istemez(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    yanit = _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id, severity="critical"))
    assert yanit.status_code == 303
    assert _kural(test_ayarlari)["severity"] == "critical"


def test_varsayilanin_altina_inmek_onaysiz_reddedilir(istemci, test_ayarlari):
    """Yasak alana giriş Yüksek'tir; Orta yazmak onay ister ve kural yazılmaz."""
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    yanit = _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id, severity="medium"))
    assert yanit.status_code == 400
    assert "varsayılanından (Yüksek) düşük" in yanit.json()["hata"]
    assert _satirlar(test_ayarlari, "SELECT id FROM rules") == []

    yanit = _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id, severity="medium", onem_onay="1"))
    assert yanit.status_code == 303
    assert _kural(test_ayarlari)["severity"] == "medium"


def test_arac_yolundaki_yayayi_ortaya_indirmek_yukseltmeyi_kapatir_onay_ister(
    istemci, test_ayarlari
):
    """Varsayılanı Orta ama araç varken Yüksek: Orta seçmek yükseltmeyi kapatır."""
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, "vehicle_area")
    yanit = _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id, severity="medium"))
    assert yanit.status_code == 400


def test_gecersiz_onem_reddedilir(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    yanit = _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id, severity="info"))
    assert yanit.status_code == 400


def test_onem_ucu_varsayilani_ve_kaynagini_soyler(istemci, test_ayarlari):
    _, yasak = _kamera_ve_bolge(istemci, test_ayarlari)
    bilgi = istemci.get(
        "/kurallar/onem",
        params={"rule_type": "zone_intrusion", "zone_id": yasak, "hedef": "person"},
    ).json()
    assert bilgi == {
        "varsayilan": "high",
        "varsayilan_adi": "Yüksek",
        "aciklama": "Yasak alana giriş: Yüksek",
    }

    _, arac_yolu = _kamera_ve_bolge(istemci, test_ayarlari, "vehicle_area")
    bilgi = istemci.get(
        "/kurallar/onem",
        params={"rule_type": "zone_intrusion", "zone_id": arac_yolu, "hedef": ["person"]},
    ).json()
    assert bilgi["aciklama"] == "Araç yolunda yaya: Orta, aynı bölgede araç varken Yüksek"

    bilgi = istemci.get(
        "/kurallar/onem", params={"rule_type": "ppe_violation", "kkd": ["vest"]}
    ).json()
    assert (bilgi["varsayilan"], bilgi["aciklama"]) == ("medium", "Yelek yok: Orta")
    assert istemci.get("/kurallar/onem", params={"rule_type": "yok"}).status_code == 400


def test_liste_ve_duzenleme_formu_onemi_gosterir(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id))
    hap = '<span class="onem-hapi onem-high">Yüksek</span> <span class="not">varsayılan</span>'
    assert hap in istemci.get("/kurallar").text
    kural_id = _kural(test_ayarlari)["id"]
    form = istemci.get(f"/kurallar/{kural_id}/duzenle").text
    assert "Varsayılan (Yüksek)</option>" in form
    assert "Bu kuralın olayları: Yasak alana giriş: Yüksek." in form


# ------------------------------------------------------------------ yeni alanlar, korunan değerler


def test_yeni_alanlar_kaydedilir(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    # gecit_haric kutusu işaretsiz gönderildi → False
    _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id, bitis_s="7.5"))
    params = _kural(test_ayarlari)["params"]
    assert (params["bitis_s"], params["gecit_haric"]) == (7.5, False)

    yanit = _kaydet(
        istemci,
        {
            "camera_id": str(kamera_id),
            "rule_type": "safe_distance",
            "object_classes": ["forklift"],
            "distance_m": "3",
            "histerezis_m": "1.2",
            "require_moving_vehicle": "1",
            "enabled": "1",
        },
    )
    assert yanit.status_code == 303
    params = _kural(test_ayarlari)["params"]
    assert (params["histerezis_m"], params["bitis_s"]) == (1.2, 3.0)  # boş → şema varsayılanı


def test_formda_olmayan_parametre_kaydederken_korunur(istemci, test_ayarlari):
    """Eskiden form yalnız gösterdiğini yazıyordu: histerezis 1,2 m olan kural,
    alanı bilmeyen bir formla kaydedilince 0,5'e dönerdi."""
    kamera_id, _ = _kamera_ve_bolge(istemci, test_ayarlari)
    veri = {
        "camera_id": str(kamera_id),
        "rule_type": "safe_distance",
        "object_classes": ["forklift", "truck"],
        "histerezis_m": "1.2",
        "bitis_s": "9",
        "enabled": "1",
    }
    _kaydet(istemci, veri)
    kural_id = _kural(test_ayarlari)["id"]
    del veri["histerezis_m"], veri["bitis_s"]
    assert (
        _kaydet(istemci, {**veri, "kural_id": str(kural_id), "distance_m": "4"}).status_code == 303
    )
    params = _kural(test_ayarlari)["params"]
    assert (params["distance_m"], params["histerezis_m"], params["bitis_s"]) == (4.0, 1.2, 9.0)


def test_tip_degisince_eski_tipin_degeri_tasinmaz(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, "ppe_required")
    _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id, min_dwell_s="9"))
    kural_id = _kural(test_ayarlari)["id"]
    yanit = _kaydet(
        istemci,
        {
            "kural_id": str(kural_id),
            "camera_id": str(kamera_id),
            "rule_type": "ppe_violation",
            "zone_id": str(bolge_id),
            "required_ppe": ["helmet"],
            "enabled": "1",
        },
    )
    assert yanit.status_code == 303
    assert (
        _kural(test_ayarlari)["params"]["min_dwell_s"]
        == varsayilan_params("ppe_violation")["min_dwell_s"]
    )


def test_olmayan_kurali_duzenlemek_sessizce_gecmez(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    yanit = _kaydet(istemci, _bolge_kurali(kamera_id, bolge_id, kural_id="999"))
    assert yanit.status_code == 400
    assert "Kural bulunamadı" in yanit.json()["hata"]


@pytest.mark.parametrize("kural_tipi", sorted(PARAM_SEMALARI))
def test_semanin_her_alani_formda(kural_tipi):
    """Formda karşılığı olmayan bir şema alanı, kaydetmede hep önceki/varsayılan
    değerde kalırdı: operatör onu hiç değiştiremezdi."""
    liste_alanlari = {"mode", "object_classes", "subject_classes", "required_ppe"}
    formdakiler = (
        set(kurallar_web._SAYI_ALANLARI[kural_tipi])
        | set(kurallar_web._KUTU_ALANLARI[kural_tipi])
        | liste_alanlari
    )
    assert set(PARAM_SEMALARI[kural_tipi].model_fields) <= formdakiler

    sablon = SABLON.read_text(encoding="utf-8")
    for alan in (
        *kurallar_web._SAYI_ALANLARI[kural_tipi],
        *kurallar_web._KUTU_ALANLARI[kural_tipi],
    ):
        assert f'name="{alan}"' in sablon, alan


def test_yeni_kural_formu_varsayilanlari_semadan(istemci, test_ayarlari):
    _kamera_ve_bolge(istemci, test_ayarlari)
    form = istemci.get("/kurallar/yeni").text

    def deger(ad: str) -> str:
        eslesme = re.search(rf'name="{ad}"[^>]*?value="([^"]*)"', form, re.S)
        assert eslesme, ad
        return eslesme.group(1)

    mesafe = varsayilan_params("safe_distance")
    assert float(deger("distance_m")) == mesafe["distance_m"]
    assert float(deger("histerezis_m")) == mesafe["histerezis_m"]
    assert float(deger("bitis_s")) == varsayilan_params("zone_intrusion")["bitis_s"]
    assert float(deger("speed_limit_mps")) == varsayilan_params("vehicle_speed")["speed_limit_mps"]
    # Cooldown yeni kuralda tipin varsayılanı (docs/03), her tipte 120 değil
    assert deger("cooldown_s") == "120"  # ilk tip: bölge ihlali
    assert '"safe_distance": 90' in form and '"ppe_violation": 180' in form
    assert re.search(r'name="gecit_haric" value="1"\s+checked', form)  # geçit istisnası açık doğar

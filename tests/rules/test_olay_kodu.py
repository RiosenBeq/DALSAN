"""Olay kodları ve önem (docs/17 §6.1–6.3): sözlüğün tamamı ve motorun ataması.

Kod değerlendiricide değil motorda atanır; bu yüzden kural testlerinin geri
kalanı kod yüzünden değişmez. Burada sınanan: her ihlal tek ve doğru bir kod
alır, önem kural satırındaki seçime ve bağlama göre verilir.
"""

from __future__ import annotations

import pytest
from yardimci import KARE, bolge, kural, tespit

from app.rules.motor import DEGERLENDIRICILER, KuralMotoru
from app.rules.olay_kodu import (
    KAPANIS_SEBEPLERI,
    OLAY_KODLARI,
    ONEM_ADLARI,
    ONEMLER,
    SUREN_SISTEM_KODLARI,
    ihlal_kodu,
    olay_onemi,
)

# docs/17 §6.1 tablosu, önemleriyle. Tablo değişirse bu liste bilerek güncellenir.
TASARIMDAKI_KODLAR = {
    "PPE_NO_HELMET": "high",
    "PPE_NO_VEST": "medium",
    "PERSON_IN_VEHICLE_LANE": "medium",
    "VEHICLE_ON_WALKWAY": "high",
    "VEHICLE_PERSON_PROXIMITY": "critical",
    "RESTRICTED_ENTRY": "high",
    "PERSON_OFF_WALKWAY": "medium",
    "PERSON_IN_LOADING_AREA": "medium",
    "VEHICLE_OUT_OF_POSITION": "low",
    "VEHICLE_OVERSPEED": "high",
    "ZONE_INTRUSION": "medium",
    "CAMERA_DOWN": "system",
    "CAMERA_UP": "system",
    "VIDEO_FINISHED": "system",
    "DISK_LOW": "system",
    "MODEL_LOAD_FAILED": "system",
    "INFERENCE_DEVICE_FALLBACK": "system",
    "ANALYSIS_STALLED": "system",
    "ANALYSIS_DEGRADED": "system",
    "SYSTEM_STARTED": "system",
    "SYSTEM_STOPPED": "system",
    "PPE_COLLECTION_CHANGED": "system",
    "PPE_MODEL_CHANGED": "system",
    "AUDIO_CHANNEL_DOWN": "system",
    "AUDIO_CHANNEL_UP": "system",
    "ALERT_UNDELIVERED": "system",
}


# ------------------------------------------------------------------ sözlük


def test_sozluk_tasarimdaki_kodlarin_tamami():
    assert {k: v.onem for k, v in OLAY_KODLARI.items()} == TASARIMDAKI_KODLAR


def test_her_kodun_turkce_adi_var_ve_adlar_karismaz():
    adlar = [tanim.ad for tanim in OLAY_KODLARI.values()]
    assert all(ad.strip() for ad in adlar)
    # İki kod aynı adla görünseydi ekrandaki olay hangisi bilinmezdi
    assert len(set(adlar)) == len(adlar)
    assert set(ONEM_ADLARI) == set(ONEMLER)


def test_suren_sistem_olaylari_eslidir():
    """Açık doğan olayın kapatanı sözlükte vardır; kapatan da bir sistem olayıdır."""
    assert SUREN_SISTEM_KODLARI == {"CAMERA_DOWN", "AUDIO_CHANNEL_DOWN"}
    for tanim in OLAY_KODLARI.values():
        if tanim.kapattigi:
            assert tanim.sistem_mi
            assert OLAY_KODLARI[tanim.kapattigi].sistem_mi


def test_kapanis_sebepleri_tasarimdakileri_icerir():
    tasarim = {"kosul_bitti", "belirsiz", "iz_kayboldu", "kural_degisti", "kapanis"}
    assert tasarim | {"yeniden_baslama"} <= set(KAPANIS_SEBEPLERI)


# ------------------------------------------------------------------ ihlal kodu


@pytest.mark.parametrize(
    ("mod", "sinif", "bolge_tipi", "beklenen"),
    [
        ("inside", "person", "vehicle_area", "PERSON_IN_VEHICLE_LANE"),
        ("inside", "forklift", "pedestrian_path", "VEHICLE_ON_WALKWAY"),
        ("inside", "truck", "pedestrian_path", "VEHICLE_ON_WALKWAY"),
        ("inside", "person", "restricted", "RESTRICTED_ENTRY"),
        ("outside", "person", "pedestrian_path", "PERSON_OFF_WALKWAY"),
        ("inside", "person", "loading_area", "PERSON_IN_LOADING_AREA"),
        ("outside", "truck", "truck_parking", "VEHICLE_OUT_OF_POSITION"),
        # Tabloya uymayan birleşimler yedek koda düşer, kod uydurulmaz
        ("outside", "forklift", "truck_parking", "ZONE_INTRUSION"),
        ("inside", "forklift", "restricted", "ZONE_INTRUSION"),
        ("inside", "person", "pedestrian_path", "ZONE_INTRUSION"),
        ("outside", "person", "restricted", "ZONE_INTRUSION"),
        ("inside", "person", None, "ZONE_INTRUSION"),
    ],
)
def test_bolge_ihlali_kodu(mod, sinif, bolge_tipi, beklenen):
    assert ihlal_kodu("zone_intrusion", {"mode": mod, "sinif": sinif}, bolge_tipi) == beklenen


@pytest.mark.parametrize(
    ("eksik", "beklenen"),
    [
        (["helmet"], "PPE_NO_HELMET"),
        (["vest"], "PPE_NO_VEST"),
        # İki kalem birden: ağır olanın kodu (kalem başına olay Faz 3d)
        (["helmet", "vest"], "PPE_NO_HELMET"),
        (["vest", "helmet"], "PPE_NO_HELMET"),
    ],
)
def test_kkd_kodu_eksik_kaleme_gore(eksik, beklenen):
    assert ihlal_kodu("ppe_violation", {"eksik_kkd": eksik}, "ppe_required") == beklenen


def test_mesafe_ve_hiz_kodu():
    assert ihlal_kodu("safe_distance", {}, None) == "VEHICLE_PERSON_PROXIMITY"
    assert ihlal_kodu("vehicle_speed", {}, None) == "VEHICLE_OVERSPEED"


def test_her_kural_tipinin_kodu_var():
    """Yeni kural tipi eklenip kodu unutulursa bu test düşer (docs/03 §6)."""
    for tip in DEGERLENDIRICILER:
        assert ihlal_kodu(tip, {}, None) in OLAY_KODLARI
    with pytest.raises(ValueError):
        ihlal_kodu("bilinmeyen_kural", {}, None)


# ------------------------------------------------------------------ önem


def test_varsayilan_onem_kodun_onemidir():
    assert olay_onemi("RESTRICTED_ENTRY", "warning") == "high"
    assert olay_onemi("VEHICLE_PERSON_PROXIMITY", None) == "critical"


def test_kural_satirindaki_acik_onem_gecerlidir():
    assert olay_onemi("RESTRICTED_ENTRY", "critical") == "critical"
    assert olay_onemi("PERSON_OFF_WALKWAY", "low") == "low"


def test_taninmayan_onem_varsayilana_duser():
    """Elle yazılmış 'info' sessizce 'düşük' sayılmaz."""
    assert olay_onemi("RESTRICTED_ENTRY", "info") == "high"


def test_sistem_olayinin_onemi_hep_sistem():
    assert olay_onemi("CAMERA_DOWN", "critical") == "system"


def test_arac_yolundaki_yaya_arac_varken_yukselir():
    assert olay_onemi("PERSON_IN_VEHICLE_LANE", "warning", arac_ayni_bolgede=True) == "high"
    assert olay_onemi("PERSON_IN_VEHICLE_LANE", "warning") == "medium"
    # Yalnız bu kod yükselir; operatörün açık seçimi bağlamdan önce gelir
    assert olay_onemi("PERSON_OFF_WALKWAY", "warning", arac_ayni_bolgede=True) == "medium"
    assert olay_onemi("PERSON_IN_VEHICLE_LANE", "low", arac_ayni_bolgede=True) == "low"


def test_bilinmeyen_kodun_onemi_uydurulmaz():
    with pytest.raises(ValueError):
        olay_onemi("YOK_BOYLE_KOD")


# ------------------------------------------------------------------ motor ataması


def _bolge_ihlali(bolge_tipi, tespitler, *, mod="inside", hedefler=None):
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [
            kural(
                "zone_intrusion",
                hedefler=hedefler or ["person"],
                params={"mode": mod, "min_dwell_s": 1.0},
            )
        ]
    )
    bolgeler = [bolge(tip=bolge_tipi)]
    motor.degerlendir(0.0, KARE, tespitler, bolgeler, None)
    return motor.degerlendir(1.5, KARE, tespitler, bolgeler, None)


def test_motor_ihlale_kod_ve_onem_yazar():
    (ihlal,) = _bolge_ihlali("restricted", [tespit(ayak=(0.5, 0.5))])
    assert (ihlal.kod, ihlal.onem) == ("RESTRICTED_ENTRY", "high")


def test_yedek_kodda_bolge_tipi_ayrintiya_yazilir():
    (ihlal,) = _bolge_ihlali("ppe_required", [tespit(ayak=(0.5, 0.5))])
    assert ihlal.kod == "ZONE_INTRUSION"
    assert ihlal.detaylar["bolge_tipi"] == "ppe_required"


def test_arac_yolunda_arac_varken_yaya_ihlali_yuksek():
    kisi = tespit(ayak=(0.5, 0.5), takip_id=1)
    forklift_icerde = tespit(sinif="forklift", ayak=(0.6, 0.6), takip_id=2)
    (ihlal,) = _bolge_ihlali("vehicle_area", [kisi, forklift_icerde])
    assert (ihlal.kod, ihlal.onem) == ("PERSON_IN_VEHICLE_LANE", "high")
    assert ihlal.detaylar["arac_ayni_bolgede"] is True


def test_arac_bolge_disindayken_yaya_ihlali_orta():
    kisi = tespit(ayak=(0.5, 0.5), takip_id=1)
    forklift_disarida = tespit(sinif="forklift", ayak=(0.9, 0.9), takip_id=2)
    (ihlal,) = _bolge_ihlali("vehicle_area", [kisi, forklift_disarida])
    assert (ihlal.kod, ihlal.onem) == ("PERSON_IN_VEHICLE_LANE", "medium")
    assert "arac_ayni_bolgede" not in ihlal.detaylar


def test_yaya_yolundaki_arac_kodunu_tetikleyen_sinif_verir():
    """Hedefinde hem kişi hem araç olan kural: kodu kuralın listesi değil,
    ihlali o an tetikleyen nesne belirler."""
    (ihlal,) = _bolge_ihlali(
        "pedestrian_path", [tespit(sinif="truck", ayak=(0.5, 0.5))], hedefler=["truck", "person"]
    )
    assert (ihlal.kod, ihlal.onem) == ("VEHICLE_ON_WALKWAY", "high")

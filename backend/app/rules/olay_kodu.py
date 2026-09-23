"""Olay kodları ve önem (docs/17 §6.1–6.2) — saf, tek kaynak.

Her olay satırı (`events.event_code`, şema 007) bu sözlükteki bir kodu taşır.
Kodu İHLALDE kural motoru atar (rules/motor.py: kural tipi + bölge tipi +
tetikleyen sınıf), SİSTEM OLAYINDA yazan yer açıkça verir
(olaylar/yazici.py `sistem_olayi_yaz(kod=...)`). Ekrandaki Türkçe ad ve
varsayılan önem de buradan gelir; bir kodun adı iki ayrı yerde yazılmaz.

Önem kuralı (docs/17 §6.2): kural satırındaki `severity` 'warning' ise
(bugünkü bütün satırlar; şema varsayılanı) kodun varsayılanı geçerlidir;
`critical` / `high` / `medium` / `low` ise o geçerlidir. Başka bir değer
(elle yazılmış 'info' gibi) tanınmaz ve kodun varsayılanına düşer: önemi
bilinmeyen bir olay sessizce "düşük" sayılmamalı.

Sözlükte bu turda HENÜZ ÜRETİLMEYEN kodlar da vardır (KKD modeli F3, ses
kanalları F4, bekçi 2d). Tablo tasarımın tamamıdır; üreticisi geldiğinde
yalnız çağrı eklenir, ad ve önem tartışması yeniden açılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rules.tipler import SINIF_FORKLIFT, SINIF_INSAN, SINIF_TIR

# Önem düzeyleri (events.severity). Sıra anlamlıdır: en ciddiden en hafife.
ONEM_KRITIK = "critical"
ONEM_YUKSEK = "high"
ONEM_ORTA = "medium"
ONEM_DUSUK = "low"
ONEM_SISTEM = "system"
IHLAL_ONEMLERI: tuple[str, ...] = (ONEM_KRITIK, ONEM_YUKSEK, ONEM_ORTA, ONEM_DUSUK)
ONEMLER: tuple[str, ...] = (*IHLAL_ONEMLERI, ONEM_SISTEM)

ONEM_ADLARI = {
    ONEM_KRITIK: "Kritik",
    ONEM_YUKSEK: "Yüksek",
    ONEM_ORTA: "Orta",
    ONEM_DUSUK: "Düşük",
    ONEM_SISTEM: "Sistem",
}

# Kural satırında "önemi kodun varsayılanından al" demek olan değer
# (rules.severity DEFAULT 'warning', şema 001).
KURAL_VARSAYILAN_ONEMI = "warning"

ARAC_SINIFLARI = frozenset({SINIF_FORKLIFT, SINIF_TIR})


@dataclass(frozen=True)
class OlayKodu:
    kod: str
    onem: str  # varsayılan önem (ONEMLER'den)
    ad: str  # ekranda görünen Türkçe ad
    # Yalnız sistem olaylarında: bu olay hangi AÇIK olayı kapatır. Kapatılan
    # kod "süren" bir olaydır (resolved_at boş doğar); eşi gelince kapanır.
    kapattigi: str | None = None

    @property
    def sistem_mi(self) -> bool:
        return self.onem == ONEM_SISTEM


def _tablo(*kodlar: OlayKodu) -> dict[str, OlayKodu]:
    return {k.kod: k for k in kodlar}


OLAY_KODLARI: dict[str, OlayKodu] = _tablo(
    # ---- ihlaller
    OlayKodu("PPE_NO_HELMET", ONEM_YUKSEK, "Baret yok"),
    OlayKodu("PPE_NO_VEST", ONEM_ORTA, "Yelek yok"),
    # Aynı bölgede bir aracın ayak noktası da varsa önem yükselir (olay_onemi).
    OlayKodu("PERSON_IN_VEHICLE_LANE", ONEM_ORTA, "Araç yolunda yaya"),
    OlayKodu("VEHICLE_ON_WALKWAY", ONEM_YUKSEK, "Yaya yolunda araç"),
    OlayKodu("VEHICLE_PERSON_PROXIMITY", ONEM_KRITIK, "Araç–yaya yakınlığı"),
    OlayKodu("RESTRICTED_ENTRY", ONEM_YUKSEK, "Yasak alana giriş"),
    OlayKodu("PERSON_OFF_WALKWAY", ONEM_ORTA, "Yaya yolu dışında"),
    OlayKodu("PERSON_IN_LOADING_AREA", ONEM_ORTA, "Yükleme alanında yaya"),
    OlayKodu("VEHICLE_OUT_OF_POSITION", ONEM_DUSUK, "Tır park yeri dışında"),
    OlayKodu("VEHICLE_OVERSPEED", ONEM_YUKSEK, "Hız aşımı"),
    # Sözlüğe uymayan bölge ihlali birleşimi (ör. yükleme alanının DIŞINDAKİ
    # forklift). Bölge tipi olayın ayrıntısına yazılır.
    OlayKodu("ZONE_INTRUSION", ONEM_ORTA, "Bölge ihlali"),
    # ---- sistem
    OlayKodu("CAMERA_DOWN", ONEM_SISTEM, "Kamera çevrimdışı"),
    OlayKodu("CAMERA_UP", ONEM_SISTEM, "Kamera tekrar çevrimiçi", kapattigi="CAMERA_DOWN"),
    OlayKodu("VIDEO_FINISHED", ONEM_SISTEM, "Video analizi tamamlandı"),
    OlayKodu("DISK_LOW", ONEM_SISTEM, "Disk azalıyor"),
    OlayKodu("MODEL_LOAD_FAILED", ONEM_SISTEM, "Tespit modeli yüklenemedi"),
    OlayKodu("INFERENCE_DEVICE_FALLBACK", ONEM_SISTEM, "GPU istendi, CPU kullanılıyor"),
    OlayKodu("ANALYSIS_STALLED", ONEM_SISTEM, "Analiz takıldı"),  # 2d (bekçi)
    OlayKodu("ANALYSIS_DEGRADED", ONEM_SISTEM, "Analiz yavaşladı"),  # 2d
    OlayKodu("SYSTEM_STARTED", ONEM_SISTEM, "Sistem başladı"),
    OlayKodu("SYSTEM_STOPPED", ONEM_SISTEM, "Sistem durdu"),
    OlayKodu("PPE_COLLECTION_CHANGED", ONEM_SISTEM, "KKD veri toplama değişti"),  # 2e
    OlayKodu("PPE_MODEL_CHANGED", ONEM_SISTEM, "KKD modeli değişti"),  # F3
    OlayKodu("AUDIO_CHANNEL_DOWN", ONEM_SISTEM, "Ses kanalı koptu"),  # F4
    OlayKodu(
        "AUDIO_CHANNEL_UP",
        ONEM_SISTEM,
        "Ses kanalı tekrar bağlandı",
        kapattigi="AUDIO_CHANNEL_DOWN",
    ),  # F4
    OlayKodu("ALERT_UNDELIVERED", ONEM_SISTEM, "Uyarı hiçbir sesli kanala ulaşamadı"),  # F4
)

# Açık doğan (resolved_at boş) sistem olayları: kapatanı olanlar.
SUREN_SISTEM_KODLARI: frozenset[str] = frozenset(
    k.kapattigi for k in OLAY_KODLARI.values() if k.kapattigi
)

# Bir olayın neden bittiği (details.kapanis_sebebi). Kod İngilizce değil:
# bunlar veritabanı kodu değil, ayrıntı JSON'undaki açıklama anahtarlarıdır
# ve docs/17 §6.3'te bu adlarla geçer.
KAPANIS_SEBEPLERI = {
    "kosul_bitti": "Durum sona erdi",
    "belirsiz": "Karar belirsize döndü",
    "iz_kayboldu": "Görüş alanından çıktı",
    "kural_degisti": "Kural değiştirildi ya da kapatıldı",
    "kamera_degisti": "Kamera ayarı değişti ya da kamera kapatıldı",
    "kamera_koptu": "Kamera görüntüsü kesildi; durum izlenemedi",
    "hat_yenilendi": "Kamera işleme hattı hatalar yüzünden yeniden kuruldu",
    "kapanis": "Sistem durduruldu",
    "yeniden_baslama": "Sistem yeniden başladı; olay açık kalmıştı",
}

# Bölge ihlalinin kodu: (yön, bölge tipi) → (tetikleyebilecek sınıflar, kod).
# Tabloya uymayan birleşim ZONE_INTRUSION olur (docs/17 §6.1).
_BOLGE_KODLARI: dict[tuple[str, str], tuple[frozenset[str], str]] = {
    ("inside", "vehicle_area"): (frozenset({SINIF_INSAN}), "PERSON_IN_VEHICLE_LANE"),
    ("inside", "pedestrian_path"): (ARAC_SINIFLARI, "VEHICLE_ON_WALKWAY"),
    ("inside", "restricted"): (frozenset({SINIF_INSAN}), "RESTRICTED_ENTRY"),
    ("outside", "pedestrian_path"): (frozenset({SINIF_INSAN}), "PERSON_OFF_WALKWAY"),
    ("inside", "loading_area"): (frozenset({SINIF_INSAN}), "PERSON_IN_LOADING_AREA"),
    # Yalnız tır: forklift sahanın her yerinde çalışır, park yeri onun yeri değil.
    ("outside", "truck_parking"): (frozenset({SINIF_TIR}), "VEHICLE_OUT_OF_POSITION"),
}


def ihlal_kodu(kural_tipi: str, detaylar: dict, bolge_tipi: str | None) -> str:
    """İhlalin olay kodu.

    `detaylar` değerlendiricinin yazdığı ayrıntıdır: bölge ihlalinde
    tetikleyen sınıf (`sinif`) ve yön (`mode`), KKD'de eksik kalemler
    (`eksik_kkd`). Kural tipi tanınmıyorsa ValueError: kod uydurulmaz.
    """
    if kural_tipi == "safe_distance":
        return "VEHICLE_PERSON_PROXIMITY"
    if kural_tipi == "vehicle_speed":
        return "VEHICLE_OVERSPEED"
    if kural_tipi == "ppe_violation":
        # Tek olay iki eksik kalem taşıyabilir (kalem başına ayrı olay Faz 3d);
        # o zaman daha ağır olanın kodu verilir, iki kalem de ayrıntıda durur.
        eksik = detaylar.get("eksik_kkd") or []
        return "PPE_NO_VEST" if eksik and "helmet" not in eksik else "PPE_NO_HELMET"
    if kural_tipi == "zone_intrusion":
        anahtar = (str(detaylar.get("mode", "inside")), str(bolge_tipi or ""))
        eslesme = _BOLGE_KODLARI.get(anahtar)
        if eslesme is not None and detaylar.get("sinif") in eslesme[0]:
            return eslesme[1]
        return "ZONE_INTRUSION"
    raise ValueError(f"Olay kodu verilemeyen kural tipi: {kural_tipi!r}")


def olay_onemi(
    kod: str, kural_siddet: str | None = None, *, arac_ayni_bolgede: bool = False
) -> str:
    """Olayın önemi (docs/17 §6.2–6.3).

    Sistem olayı her zaman 'system'dır. İhlalde kural satırında açık bir önem
    yazılıysa o geçerlidir (operatörün seçimi bağlamdan önce gelir); yoksa
    kodun varsayılanı. Araç yolundaki yaya, aynı bölgede bir araç varken
    'high' olur: boş yolda duran kişiyle forkliftin önündeki kişi aynı değil.
    """
    tanim = OLAY_KODLARI.get(kod)
    if tanim is None:
        raise ValueError(f"Bilinmeyen olay kodu: {kod!r}")
    if tanim.sistem_mi:
        return ONEM_SISTEM
    if kural_siddet in IHLAL_ONEMLERI:
        return kural_siddet
    if arac_ayni_bolgede and kod == "PERSON_IN_VEHICLE_LANE":
        return ONEM_YUKSEK
    return tanim.onem


def _en_agir_onemi(kod: str) -> str:
    """Kodun bağlamsal yükseltme dahil ulaşabileceği en ağır varsayılan önem."""
    return olay_onemi(kod, arac_ayni_bolgede=True)


def kural_olay_kodlari(
    kural_tipi: str, bolge_tipi: str | None, params: dict, hedef_siniflar
) -> list[str]:
    """Kuralın üretebileceği ihlal kodları, en ağır önemden hafife (kural formu).

    Bölge ihlalinde her hedef sınıf ayrı kod verebilir (araç sahasında insan
    PERSON_IN_VEHICLE_LANE, forklift ZONE_INTRUSION); KKD'de her zorunlu
    kalem kendi kodunu verir. Kod yine `ihlal_kodu`'ndan gelir: eşleme iki
    yerde yazılmaz.
    """
    if kural_tipi == "zone_intrusion":
        yon = params.get("mode", "inside")
        detaylar = [{"mode": yon, "sinif": s} for s in hedef_siniflar] or [{"mode": yon}]
    elif kural_tipi == "ppe_violation":
        detaylar = [{"eksik_kkd": [k]} for k in params.get("required_ppe") or ("helmet", "vest")]
    else:
        detaylar = [{}]
    kodlar = {ihlal_kodu(kural_tipi, d, bolge_tipi) for d in detaylar}
    return sorted(kodlar, key=lambda k: (IHLAL_ONEMLERI.index(_en_agir_onemi(k)), k))


def kural_varsayilan_onemi(
    kural_tipi: str, bolge_tipi: str | None, params: dict, hedef_siniflar
) -> str:
    """Kural satırında açık önem yokken kuralın EN AĞIR olayının önemi.

    Bağlamsal yükseltme dahildir: araç yolundaki yaya Orta doğar ama aynı
    bölgede araç varken Yüksek olur. Kural formunda "Orta" seçmek bu
    yükseltmeyi kapatır (açık önem bağlamdan önce gelir), yani varsayılanın
    altına inmektir ve onay ister.
    """
    kodlar = kural_olay_kodlari(kural_tipi, bolge_tipi, params, hedef_siniflar)
    return _en_agir_onemi(kodlar[0])


def onem_daha_hafif(onem: str, karsi: str) -> bool:
    """`onem`, `karsi`dan daha mı hafif? İkisi de IHLAL_ONEMLERI'nden."""
    return IHLAL_ONEMLERI.index(onem) > IHLAL_ONEMLERI.index(karsi)

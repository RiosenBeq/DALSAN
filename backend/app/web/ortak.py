"""Web katmanının ortak yardımcıları: istek başına veritabanı bağlantısı,
RTSP maskeleme, Türkçe etiket tabloları ve bölge tiplerinin hazır kuralları."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Request

from app import veritabani
from app.rules.parametreler import params_dogrula

# Kullanıcıya görünen Türkçe adlar (kod içi değerler İngilizce kalır)
BOLGE_TIPLERI = {
    "pedestrian_path": "Yaya yolu",
    "loading_area": "Yükleme alanı",
    "truck_parking": "Tır park alanı",
    "vehicle_area": "Araç sahası",
    "ppe_required": "KKD zorunlu alan",
    "restricted": "Yasak bölge",
}

KURAL_TIPLERI = {
    "zone_intrusion": "Bölge ihlali",
    "safe_distance": "Güvenli mesafe",
    "ppe_violation": "KKD (baret/yelek)",
}

OLAY_DURUMLARI = {"new": "Yeni", "reviewed": "İncelendi", "false_alarm": "Yanlış alarm"}

SINIFLAR = {"person": "İnsan", "forklift": "Forklift", "truck": "Tır/Araç"}


def baglanti_al(istek: Request) -> Iterator:
    """İstek başına SQLite bağlantısı (FastAPI dependency)."""
    baglanti = veritabani.baglanti_ac(istek.app.state.ayarlar.veritabani_yolu)
    try:
        yield baglanti
    finally:
        baglanti.close()


def rtsp_maskele(url: str) -> str:
    """rtsp://kullanici:sifre@ip/... → rtsp://••••@ip/...  (docs/01 §3.6)."""
    return re.sub(r"//[^/@]+@", "//••••@", url)


def guvenli_json(veri) -> str:
    """<script> bloğuna gömülecek JSON — HTML'e özel karakterler kaçırılır.

    json.dumps `<`, `>`, `&` karakterlerini kaçırmaz; kullanıcı verisi (örn.
    bölge adı) `</script><img onerror=...>` içerirse depolanan XSS olurdu.
    Unicode kaçışları JSON içinde birebir aynı metni temsil eder.
    """
    metin = json.dumps(veri, ensure_ascii=False)
    return metin.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# ---------------------------------------------------------------- hazır kurallar
#
# Kullanıcı bir bölge çizdiğinde "çizdim ama hiçbir şey olmuyor" durumuna
# düşmemeli: her bölge tipinin, tek tıkla kurulabilen bir karşılığı vardır.
# Eşleme ve varsayılanlar docs/03-KURAL-MOTORU.md'den alınmıştır.


@dataclass(frozen=True)
class HazirKural:
    """Bir bölge tipinin tek tıkla kurulan kural karşılığı (docs/03).

    `params` YALNIZCA şema varsayılanından FARKLI olan alanları taşır; kalan
    eşikler app/rules/parametreler.py'deki (yine docs/03 tablolarından alınmış)
    varsayılanlardan gelir. Böylece hiçbir eşik iki ayrı yerde yazılmaz.
    """

    kural_tipi: str
    hedef_siniflar: tuple[str, ...]
    params: dict
    anons_anahtari: str | None  # announcement_messages.key — yoksa yalnız ekran uyarısı
    cooldown_s: int | None  # None → VARSAYILAN_COOLDOWN_SN[kural_tipi]
    kisa_ad: str  # düğme metni: '"Ad" için {kisa_ad} ekle'
    aciklama: str  # {param} yer tutucuları çözülmüş params ile doldurulur


# docs/03: kural tipine göre varsayılan cooldown (saniye)
VARSAYILAN_COOLDOWN_SN = {"zone_intrusion": 120, "safe_distance": 90, "ppe_violation": 180}

HAZIR_KURALLAR: dict[str, HazirKural] = {
    # docs/03 Ek — yolu KULLANMAYAN kişi ihlaldir (mode=outside)
    "pedestrian_path": HazirKural(
        kural_tipi="zone_intrusion",
        hedef_siniflar=("person",),
        params={"mode": "outside", "min_dwell_s": 5.0},
        anons_anahtari="pedestrian_path",
        cooldown_s=180,
        kisa_ad="yaya yolu kuralı",
        aciklama=(
            "Yaya yolunun DIŞINDA {min_dwell_s:g} saniyeden uzun kalan kişi uyarı üretir; "
            "yolun kenarına bir adım atan kişi uyarı üretmez. Hoparlörden "
            "«Lütfen yaya yolunu kullanınız.» anonsu geçilir."
        ),
    ),
    # docs/03 §1 — yasak bölgede olmak ihlaldir (mode=inside, varsayılan)
    "restricted": HazirKural(
        kural_tipi="zone_intrusion",
        hedef_siniflar=("person",),
        params={"mode": "inside"},
        anons_anahtari=None,
        cooldown_s=None,
        kisa_ad="yasak bölge kuralı",
        aciklama=(
            "Yasak bölgeye girip {min_dwell_s:g} saniyeden uzun kalan kişi uyarı üretir. "
            "Bu kurala hazır bir anons bağlanmaz; uyarı ekranda ve olay listesinde görünür."
        ),
    ),
    # docs/03 §1 tablosu — "Yükleme alanında yaya": inside / person
    "loading_area": HazirKural(
        kural_tipi="zone_intrusion",
        hedef_siniflar=("person",),
        params={"mode": "inside"},
        anons_anahtari=None,
        cooldown_s=None,
        kisa_ad="yükleme alanı kuralı",
        aciklama=(
            "Yükleme alanının İÇİNDE {min_dwell_s:g} saniyeden uzun kalan kişi uyarı üretir "
            "— forklift ve tırın çalıştığı alanda yaya durmamalıdır."
        ),
    ),
    # docs/03 §1 tablosu — "Tır yanlış konumda": outside / truck
    "truck_parking": HazirKural(
        kural_tipi="zone_intrusion",
        hedef_siniflar=("truck",),
        params={"mode": "outside"},
        anons_anahtari="vehicle_position",
        cooldown_s=None,
        kisa_ad="tır konumlanma kuralı",
        aciklama=(
            "Tır park alanının DIŞINDA {min_dwell_s:g} saniyeden uzun duran tır uyarı üretir. "
            "Hoparlörden «Lütfen aracınızı belirlenen alana konumlandırınız.» anonsu geçilir."
        ),
    ),
    # docs/03 §2 — güvenli mesafe; bölge verilince yalnız o alandaki kişiler korunur
    "vehicle_area": HazirKural(
        kural_tipi="safe_distance",
        hedef_siniflar=("person", "forklift", "truck"),
        params={},
        anons_anahtari="safe_distance",
        cooldown_s=None,
        kisa_ad="güvenli mesafe kuralı",
        aciklama=(
            "Bu alandaki bir kişi ile HAREKET HALİNDEKİ forklift/tır arasındaki mesafe "
            "{distance_m:g} metrenin altına düşerse uyarı üretir. Hoparlörden "
            "«Lütfen iş makinelerinden güvenli mesafede durunuz.» anonsu geçilir."
        ),
    ),
    # docs/03 §3 — KKD kuralı yalnızca bu tipte bölgede çalışır
    "ppe_required": HazirKural(
        kural_tipi="ppe_violation",
        hedef_siniflar=("person",),
        params={},
        anons_anahtari=None,  # baret ve yelek mesajı ayrıdır; kullanıcı seçer
        cooldown_s=None,
        kisa_ad="KKD (baret/yelek) kuralı",
        aciklama=(
            "Bu bölgede baret veya yelek takmayan kişi uyarı üretir. Karar tek kareye değil "
            "{window_size} gözlemlik pencereye bakılarak verilir; emin olunamayan durum ihlal "
            "sayılmaz. Baret/yelek anonsunu Kurallar sayfasından seçebilirsiniz."
        ),
    ),
}


def hazir_kural_params(hazir: HazirKural) -> dict:
    """Hazır kuralın TAM parametre sözlüğü: farklar + şema varsayılanları."""
    return params_dogrula(hazir.kural_tipi, dict(hazir.params))


def hazir_kural_aciklamasi(hazir: HazirKural) -> str:
    """Kullanıcıya gösterilen cümle; içindeki sayılar kaydedilecek değerlerdir."""
    return hazir.aciklama.format(**hazir_kural_params(hazir))


def hazir_kural_cooldown(hazir: HazirKural) -> int:
    return hazir.cooldown_s or VARSAYILAN_COOLDOWN_SN[hazir.kural_tipi]

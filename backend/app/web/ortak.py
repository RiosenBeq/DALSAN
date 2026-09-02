"""Web katmanının ortak yardımcıları: istek başına veritabanı bağlantısı,
RTSP maskeleme, Türkçe etiket tabloları ve bölge tiplerinin hazır kuralları."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Request

from app import veritabani, zaman
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

# Cümle içinde küçük harfle geçen durum adı ("… · incelendi").
# Jinja'nın |lower süzgeci BURADA KULLANILAMAZ: Python "İncelendi".lower()
# çağrısında "i̇ncelendi" üretir (i + ayrı nokta), çünkü Türkçe büyük İ'nin
# küçüğü noktasız bir i değildir. Ekranda gözle görülür bir bozukluk olur.
OLAY_DURUMLARI_KUCUK = {"new": "yeni", "reviewed": "incelendi", "false_alarm": "yanlış alarm"}

SINIFLAR = {"person": "İnsan", "forklift": "Forklift", "truck": "Tır/Araç"}

# KKD parçalarının Türkçe adları. Olay özetinde ve inceleme ekranında AYNI
# kelime görünsün diye tek yerde durur.
KKD_ADLARI = {"helmet": "baret", "vest": "yelek"}

# .env'deki ANONS ayarının başlıkta gösterilen KISA adı. Uzun açıklamalar
# web/anons_web.py ANONS_ACIKLAMALARI'nda; burada yalnızca tek kelimelik ad.
ANONS_KISA_ADLARI = {"null": "kapalı", "ses_karti": "ses kartı", "http": "IP hoparlör"}


# ---------------------------------------------------------------- olay özeti
#
# Olay listesi, CSV, canlı akış (SSE) ve komuta ekranı AYNI cümleyi göstermeli.
# Özet metni iki ayrı yerde üretilirse er ya da geç birbirinden ayrılır ve
# kullanıcı aynı olayı iki farklı isimle görür; bu yüzden tek yerde durur.

OLAY_SORGUSU = (
    "SELECT e.*, c.name AS kamera_adi, c.area AS kamera_alani "
    "FROM events e LEFT JOIN cameras c ON c.id = e.camera_id"
)


def sayi_metni(deger, birim: str = "", basamak: int = 1) -> str:
    """Ölçülen değeri Türkçe yazımıyla gösterir: 1.85 → '1,85 m'.

    Türkçede ondalık ayırıcı virgüldür; aynı sayı ekranın bir yerinde nokta,
    başka yerinde virgülle görünürse kullanıcı iki farklı ölçüm sanır.
    Değer yoksa BOŞ metin döner — çağıran taraf o kutuyu hiç çizmez; boş
    kutuya "—" yazmak "ölçüldü ama sonuç çıkmadı" izlenimi verirdi.
    """
    if deger is None:
        return ""
    try:
        metin = f"{float(deger):.{basamak}f}"
    except (TypeError, ValueError):
        return ""
    if "." in metin:
        metin = metin.rstrip("0").rstrip(".")
    return f"{metin.replace('.', ',')} {birim}".strip()


def olay_hazirla(satir) -> dict:
    """Veritabanı satırını ekrana hazır olay sözlüğüne çevirir."""
    olay = dict(satir)
    olay["yerel_zaman"] = zaman.ekranda_goster(olay["occurred_at"])
    olay["durum_adi"] = OLAY_DURUMLARI.get(olay["status"], olay["status"])
    olay["durum_kucuk"] = OLAY_DURUMLARI_KUCUK.get(olay["status"], olay["status"])
    try:
        olay["detaylar"] = json.loads(olay["details"]) if olay["details"] else {}
    except json.JSONDecodeError:
        olay["detaylar"] = {"ham": olay["details"]}
    try:
        kural = json.loads(olay["rule_snapshot"]) if olay["rule_snapshot"] else {}
    except json.JSONDecodeError:
        kural = {}
    # Kural anlık görüntüsü (olay anındaki eşikler) inceleme ekranında
    # "ölçülen değer" ile "kural eşiği" yan yana gösterilirken kullanılır.
    olay["kural_kaydi"] = kural
    olay["kural_tipi_adi"] = KURAL_TIPLERI.get(kural.get("rule_type", ""), "")
    # GÖLGE MOD (şema 002): kural çalışıp olay yazmış ama hoparlör susmuş ve
    # ekranda uyarı bandı çıkmamıştır. Kuralın BUGÜNKÜ halinden değil olay
    # anındaki anlık görüntüsünden okunur: kural sonradan canlıya alındıysa
    # geçmiş olay "anons çaldı" diye görünmemeli.
    olay["golge_mod"] = bool(kural.get("shadow_mode"))
    if olay["event_type"] == "system":
        olay["ozet"] = olay["detaylar"].get("mesaj", "Sistem olayı")
    else:
        olay["ozet"] = olay["kural_tipi_adi"] or "İhlal"
        if olay["detaylar"].get("eksik_kkd"):
            olay["ozet"] += (
                " — "
                + ", ".join(KKD_ADLARI.get(k, k) for k in olay["detaylar"]["eksik_kkd"])
                + " yok"
            )
        elif olay["detaylar"].get("mesafe_m") is not None:
            olay["ozet"] += f" — {sayi_metni(olay['detaylar']['mesafe_m'], 'm', 2)}"
    return olay


def baglanti_al(istek: Request) -> Iterator:
    """İstek başına SQLite bağlantısı (FastAPI dependency)."""
    baglanti = veritabani.baglanti_ac(istek.app.state.ayarlar.veritabani_yolu)
    try:
        yield baglanti
    finally:
        baglanti.close()


def rtsp_maskele(url: str) -> str:
    """rtsp://kullanici:sifre@ip/... → rtsp://••••@ip/...  (docs/01 §3.6).

    Kamera adresleri için yazıldı, ama şema/protokole bakmaz: hoparlör
    bölgelerinin http adresleri de aynı desenle maskelenir. Adresin kendisi
    (ip, port, yol) görünür kalır — kullanıcı hangi cihazı yazdığını görmeli;
    gizlenen yalnızca kullanıcı adı ve şifredir.
    """
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

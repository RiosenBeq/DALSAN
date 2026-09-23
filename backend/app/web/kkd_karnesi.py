"""KKD gölge karnesi ve anons kapısı (docs/17 §5.7, K16; S33).

KKD kuralı gölge modda doğar: olay yazılır, hoparlör susar. Anonsu açmaya
kural motoru değil İSG'nin incelemesi karar verir. Gölgede üretilen olaylar
"İncelendi" ya da "Yanlış alarm" diye işaretlenir; kapı, KALEM (baret, yelek)
ve MODEL SÜRÜMÜ başına dört şartın dördü de sağlanınca açılır:

1. precision = incelendi / (incelendi + yanlış alarm) ≥ KKD_KAPI_PRECISION;
2. o kalem ve sürümün ilk olayından bu yana en az KKD_KAPI_GUN gün geçmiş
   (docs/04 §8.2: sistem en az üç gün gölgede çalışır);
3. en az KKD_KAPI_EN_AZ_OLAY incelenmiş olay. Tek doğru olayla precision %100
   çıkar. Hiç yanlış alarm yokken bile n olayla %95 güvenle söylenebilecek en
   iyi şey "hata oranı ≤ 3/n"dir ("üçler kuralı"); n = 30 bunu %10'a, yani
   0,90 eşiğine indirir (S33);
4. incelenmemiş olay kalmamış: yalnız seçilerek incelenen olaylardan
   hesaplanan oran şişebilir (docs/04 §8.2 "üretilen tüm KKD olayları
   incelenir").

Sayaçlar kameralar arasında toplanır, kural başına değil: precision modelin
ve kalemin özelliğidir. Yeni model sürümü sayaçları kendiliğinden sıfırlar,
çünkü yalnız `details.ppe.model_version`'ı yüklü sürüme eşit olaylar sayılır.

Kapı geçilmeden anons yalnız açık bir onayla ("ölçülmeden açıyorum") açılır;
onay PPE_GATE_OVERRIDDEN sistem olayı olarak yazılır (web/komuta.py).
Ölçülmeyen sayı yazılmaz, yerinde "ölçülecek" yazar (docs/17 §5.9).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from app import zaman
from app.web.ortak import KKD_ADLARI

# Olay kodu → kalem. Faz 3d'den beri her KKD olayı tek kalem taşır; daha eski
# iki kalemli bir olay, kodu gereği (ağır olan) barete sayılır.
KOD_KALEMLERI = {"PPE_NO_HELMET": "helmet", "PPE_NO_VEST": "vest"}
KALEMLER = tuple(KOD_KALEMLERI.values())
_GUN_SN = 86400

MODEL_YOK = "KKD modeli yüklü değil, ölçülecek olay yok"
HENUZ_OLAY_YOK = "bu model sürümüyle henüz olay yok"


@dataclass(frozen=True)
class KapiEsikleri:
    precision: float
    gun: int
    en_az_olay: int

    @classmethod
    def ayarlardan(cls, ayarlar) -> KapiEsikleri:
        return cls(ayarlar.kkd_kapi_precision, ayarlar.kkd_kapi_gun, ayarlar.kkd_kapi_en_az_olay)


@dataclass(frozen=True)
class KalemSayaci:
    """Bir kalemin yüklü model sürümüyle ürettiği olayların inceleme durumu."""

    olay: int = 0
    dogru: int = 0  # "İncelendi": gerçek ihlal (status = 'reviewed')
    yanlis: int = 0  # "Yanlış alarm" (status = 'false_alarm')
    ilk_olay_utc: str | None = None

    @property
    def incelenen(self) -> int:
        return self.dogru + self.yanlis

    @property
    def bekleyen(self) -> int:
        return self.olay - self.incelenen


@dataclass(frozen=True)
class Sart:
    ad: str  # "Precision en az 0,90"
    durum: str  # ölçülen: "0,93", "ölçülecek", "4 gün 2 sa"
    tamam: bool
    eksik: str  # tamam değilse "Anonsu aç"ın yanında yazan kısa cümle


def yuklu_surum(istek) -> str:
    """Analizin şu an kullandığı KKD model sürümü; model yoksa boş metin."""
    supervizor = getattr(istek.app.state, "supervizor", None)
    kkd = getattr(supervizor, "kkd", None)
    return kkd.model_surumu if kkd is not None and kkd.model_var else ""


def kural_kalemleri(params: dict) -> list[str]:
    """Kuralın istediği kalemler (params.required_ppe); boşsa ikisi de
    (KkdParams varsayılanı)."""
    kalemler = [k for k in params.get("required_ppe") or () if k in KALEMLER]
    return kalemler or list(KALEMLER)


def sayaclar(baglanti, model_surumu: str) -> tuple[dict[str, KalemSayaci], int]:
    """Yüklü sürümün kalem başına sayaçları ve BAŞKA sürümlerin olay sayısı.

    Sürüm, olayın `details` JSON'undadır (rules/kkd.py) ve Python'da okunur:
    SQLite'ın JSON işlevlerine dayanılmaz.
    """
    ham = {kalem: [0, 0, 0, None] for kalem in KALEMLER}  # olay, doğru, yanlış, ilk
    baska = 0
    for satir in baglanti.execute(
        "SELECT event_code, status, occurred_at, details FROM events "
        "WHERE event_type = 'violation' AND event_code IN ('PPE_NO_HELMET', 'PPE_NO_VEST') "
        "ORDER BY occurred_at, id"
    ):
        try:
            detay = json.loads(satir["details"] or "{}")
        except (TypeError, json.JSONDecodeError):
            detay = {}
        ppe = detay.get("ppe") if isinstance(detay, dict) else None
        surum = ppe.get("model_version") if isinstance(ppe, dict) else None
        if not model_surumu or surum != model_surumu:
            baska += 1
            continue
        sayac = ham[KOD_KALEMLERI[satir["event_code"]]]
        sayac[0] += 1
        if satir["status"] == "reviewed":
            sayac[1] += 1
        elif satir["status"] == "false_alarm":
            sayac[2] += 1
        sayac[3] = sayac[3] or satir["occurred_at"]
    return {kalem: KalemSayaci(*degerler) for kalem, degerler in ham.items()}, baska


def oran_metni(deger: float) -> str:
    """0.9 → '0,90'; 0.925 → '0,925'. En az iki basamak: eşik '0,9' yazmaz."""
    metin = f"{deger:.3f}".rstrip("0")
    if len(metin.partition(".")[2]) < 2:
        metin = f"{deger:.2f}"
    return metin.replace(".", ",")


def precision_metni(sayac: KalemSayaci) -> str:
    """AŞAĞI yuvarlanır: 0,899 "0,90" görünüp kapalı kapıyı açık sandırmasın."""
    if not sayac.incelenen:
        return "ölçülecek"
    yuzde = sayac.dogru * 100 // sayac.incelenen
    return f"{yuzde // 100},{yuzde % 100:02d}"


def kapsama_metni(sayac: KalemSayaci) -> str:
    """İncelenen / üretilen, AŞAĞI yuvarlanır: %99,6 "%100" görünmesin."""
    if not sayac.olay:
        return "—"
    return f"%{sayac.incelenen * 100 // sayac.olay}"


def sartlar(sayac: KalemSayaci, esik: KapiEsikleri, simdi_utc: str) -> list[Sart]:
    """Kapının dört şartı, ekrandaki sırayla.

    Precision kesirle karşılaştırılır: 27/30 kayan noktada 0,9'un altında
    kalıp kapıyı yanlışlıkla kapalı tutmasın.
    """
    esik_metni = oran_metni(esik.precision)
    p_metni = precision_metni(sayac)
    p_tamam = bool(sayac.incelenen) and (
        Fraction(sayac.dogru, sayac.incelenen) >= Fraction(str(esik.precision))
    )
    gecen = zaman.sure_saniye(sayac.ilk_olay_utc, simdi_utc) if sayac.ilk_olay_utc else 0.0
    gecen_metni = zaman.sure_metni(gecen) if sayac.ilk_olay_utc else "henüz olay yok"
    return [
        Sart(
            f"Precision en az {esik_metni}",
            p_metni,
            p_tamam,
            f"precision {p_metni} (en az {esik_metni})"
            if sayac.incelenen
            else "precision ölçülemedi, incelenmiş olay yok",
        ),
        Sart(
            f"İlk olaydan bu yana en az {esik.gun} gün",
            gecen_metni,
            bool(sayac.ilk_olay_utc) and gecen >= esik.gun * _GUN_SN,
            f"ilk olaydan bu yana {gecen_metni} (en az {esik.gun} gün)",
        ),
        Sart(
            f"En az {esik.en_az_olay} incelenmiş olay",
            str(sayac.incelenen),
            sayac.incelenen >= esik.en_az_olay,
            f"{sayac.incelenen} incelenmiş olay (en az {esik.en_az_olay})",
        ),
        Sart(
            "İncelenmemiş olay kalmamış",
            f"{sayac.bekleyen} olay bekliyor" if sayac.bekleyen else "bekleyen olay yok",
            sayac.bekleyen == 0,
            f"{sayac.bekleyen} olay incelenmedi",
        ),
    ]


def kalem_karnesi(
    kalem: str, sayac: KalemSayaci, esik: KapiEsikleri, simdi_utc: str, model_surumu: str
) -> dict:
    """Bir kalemin karnesi. Ekrandaki özet satırı ("Precision: 0,93 (30
    incelenmiş olay, kapsama %100, model kkd-…)") bilesen.html'deki
    `karne_ozeti` makrosunda kurulur; burada yalnız parçaları üretilir."""
    sart_listesi = sartlar(sayac, esik, simdi_utc)
    if sayac.olay:
        eksikler = [s.eksik for s in sart_listesi if not s.tamam]
        aciklama = f"{sayac.incelenen} incelenmiş olay, kapsama {kapsama_metni(sayac)}"
    else:
        # Olay yokken dört eksik yazmak aynı şeyi dört kez söylerdi
        eksikler = [HENUZ_OLAY_YOK]
        aciklama = HENUZ_OLAY_YOK
    return {
        "kalem": kalem,
        "ad": KKD_ADLARI[kalem].capitalize(),
        "oge": KKD_ADLARI[kalem],  # web/ortak.OGELER anahtarı: rozet ve renk
        "precision": precision_metni(sayac),
        "aciklama": aciklama,
        "model": model_surumu,
        "sartlar": sart_listesi,
        "eksikler": eksikler,
        "acik": not eksikler,
        "sayac": sayac,
    }


def karne_hesapla(baglanti, ayarlar, model_surumu: str, simdi_utc: str | None = None) -> dict:
    """KKD sayfası ve Uyarı zinciri için kalem başına karne.

    Model yüklü değilse karne boştur: ölçülecek bir sürüm yoktur.
    """
    esik = KapiEsikleri.ayarlardan(ayarlar)
    if not model_surumu:
        return {"model": "", "kalemler": {}, "baska_surum_olay": 0, "esik": esik}
    simdi = simdi_utc or zaman.simdi_utc()
    sayac_haritasi, baska = sayaclar(baglanti, model_surumu)
    return {
        "model": model_surumu,
        "kalemler": {
            kalem: kalem_karnesi(kalem, sayac_haritasi[kalem], esik, simdi, model_surumu)
            for kalem in KALEMLER
        },
        "baska_surum_olay": baska,
        "esik": esik,
    }


def kapi_eksikleri(karne: dict, kalemler: Iterable[str]) -> list[str]:
    """Kuralın istediği kalemlerin eksik şartları, kalem adıyla ("Baret: …").
    Boş liste kapının açık olduğunu söyler."""
    if not karne["model"]:
        return [MODEL_YOK]
    eksikler = []
    for kalem in dict.fromkeys(kalemler):
        kalem_karne = karne["kalemler"].get(kalem)
        if kalem_karne is not None:
            eksikler += [f"{kalem_karne['ad']}: {e}" for e in kalem_karne["eksikler"]]
    return eksikler


def kapi_ozeti(karne: dict, kalemler: Iterable[str]) -> str:
    """Eksik şartların ekrandaki tek cümlesi, kalem başına toplu:
    "Yelek: precision 0,80 (en az 0,90) · 4 olay incelenmedi". Ayırıcı virgül
    değil: ondalık virgülüyle karışırdı."""
    if not karne["model"]:
        return MODEL_YOK
    parcalar = []
    for kalem in dict.fromkeys(kalemler):
        kalem_karne = karne["kalemler"].get(kalem)
        if kalem_karne is not None and kalem_karne["eksikler"]:
            parcalar.append(f"{kalem_karne['ad']}: {' · '.join(kalem_karne['eksikler'])}")
    return "; ".join(parcalar)

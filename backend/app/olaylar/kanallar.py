"""Uyarı kanalları: hoparlör satırları (speaker_zones) ve .env'den tek seferlik aktarım.

Kanal yapılandırmasının TEK yeri `speaker_zones`'dur (docs/17 K22, şema 009):
her satır bir kanal. `kind` = `ses_karti` (bu bilgisayarın ses çıkışı; kablolu
amfi ya da Bluetooth hoparlör, `device` = çıkışın adı) ya da `http` (IP hoparlör,
`address`). `area` boş satır "Tüm fabrika"dır: bölümünde kanal olmayan olay
oraya düşer (docs/17 §7.3-1).

Eskiden kanalı .env'deki ANONS / ANONS_SES_CIHAZI / ANONS_HTTP_ADRESI da
tanımlıyordu. Bunlar 009'dan sonraki ilk açılışta BİR KEZ satıra aktarılır
(`env_anonsunu_aktar`); aktarımın yapıldığı `sema_surumu`'na bir adım adı
olarak yazılır. Böylece aktarım yarıda kalırsa bir sonraki açılışta yeniden
denenir, yapıldıysa operatörün sonradan sildiği satır geri gelmez.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app import zaman
from app.ayarlar import env_degerlerini_oku
from app.loglama import adres_maskele
from app.olaylar import ses_cihazlari

KANAL_TURLERI = {
    "ses_karti": "Ses çıkışı (kablolu ya da Bluetooth)",
    "http": "IP hoparlör",
}
# Satır içindeki kısa ad ("IP hoparlör · Sevkiyat rampaları")
KANAL_KISA_ADLARI = {"ses_karti": "ses çıkışı", "http": "IP hoparlör"}
TUM_FABRIKA = "Tüm fabrika"  # area = '' satırının ekrandaki adı

# sema_surumu'na yazılan adım adı. Betik değildir (.sql değil); semayi_uygula
# yalnız .sql dosyalarını uyguladığı için karışmaz. MAX(surum) "009_…sql"de kalır.
AKTARIM_ADIMI = "009_uyari_kanallari.env_aktarimi"


def kanal_ozeti(acik_kanal: int) -> str:
    """Kısa durum metni ("3 sesli kanal" / "sesli kanal yok"). Ana sayfa, komuta
    alt başlığı ve anons yöneticisi aynı cümleyi kullanır."""
    return f"{acik_kanal} sesli kanal" if acik_kanal else "sesli kanal yok"


def acik_kanal_sayisi(baglanti: sqlite3.Connection) -> int:
    return baglanti.execute("SELECT COUNT(*) FROM speaker_zones WHERE enabled = 1").fetchone()[0]


def bluetooth_kanali_mi(satir) -> bool:
    """Ses çıkışı kanalı bir Bluetooth hoparlör mü (çıkışın adından)."""
    return satir["kind"] == "ses_karti" and ses_cihazlari.bluetooth_mu(satir["device"] or "")


def kanal_sagligi_ozeti(baglanti: sqlite3.Connection, canli: bool) -> dict:
    """/saglik, sistem şeridi, Kontrol Paneli ve kurulum listesi için kanal özeti
    (docs/17 §7.3-1, §7.4, §9.1). Açık kanallara bakar; ekran kanalı sayılmaz.

    `canli`: sağlık izlemesi çalışıyor mu (analiz açık). Kapalıyken `health`
    sütunu önceki çalışmadan kalmadır: garanti doğrulanamaz (None) ve Bluetooth
    denetimi yalnız yapılandırmaya bakar ("Bluetooth dışında kanal var mı").

    Döner:
      uyari_garantisi  True: en az bir kanal bağlı · False: kanal yok ya da hepsi
                       koptu · None: doğrulanamıyor (bilinmiyor, henüz yoklanmadı,
                       analiz kapalı)
      sorunlar         sesli_kanal_yok · yedek_ses_kanali_yok · tek_kanal_bluetooth
      kanallar         [{"ad", "tur", "saglik"}] (oturumlu ayrıntı)
      bluetooth_disi   Bluetooth olmayan açık kanal sayısı (kurulum listesinin cümlesi)
    """
    satirlar = baglanti.execute(
        "SELECT name, area, kind, device, health FROM speaker_zones WHERE enabled = 1 "
        "ORDER BY (area = ''), area, name"
    ).fetchall()
    kanallar = [
        {"ad": s["name"], "tur": s["kind"], "saglik": s["health"] if canli else None}
        for s in satirlar
    ]
    if not satirlar:
        return {
            "uyari_garantisi": False,
            "sorunlar": ["sesli_kanal_yok"],
            "kanallar": [],
            "bluetooth_disi": 0,
        }
    sagliklar = [k["saglik"] for k in kanallar]
    if not canli:
        garanti = None
    elif "ok" in sagliklar:
        garanti = True
    elif any(d in (None, "unknown") for d in sagliklar):
        garanti = None
    else:
        garanti = False  # hepsi koptu
    sorunlar = []
    # Bölümlü kanal var ama geri düşülecek "Tüm fabrika" satırı yok: kanalı
    # olmayan ya da kanalları kopan bölümün uyarısı hiçbir yerden duyulmaz
    bolumlu = any((s["area"] or "").strip() for s in satirlar)
    if bolumlu and not any(not (s["area"] or "").strip() for s in satirlar):
        sorunlar.append("yedek_ses_kanali_yok")
    # GÖREV §7: Bluetooth tek uyarı kanalı olamaz (Ç38, S32). Canlıyken Bluetooth
    # dışındaki kanalların şu an bağlı olması gerekir, kapalıyken var olması.
    bluetooth = [bluetooth_kanali_mi(s) for s in satirlar]
    disi = [k for k, bt in zip(kanallar, bluetooth, strict=True) if not bt]
    if any(bluetooth):
        yedek = any(k["saglik"] == "ok" for k in disi) if canli else bool(disi)
        if not yedek:
            sorunlar.append("tek_kanal_bluetooth")
    return {
        "uyari_garantisi": garanti,
        "sorunlar": sorunlar,
        "kanallar": kanallar,
        "bluetooth_disi": len(disi),
    }


def _aktarim_gerekli_mi(baglanti: sqlite3.Connection) -> bool:
    uygulananlar = {s[0] for s in baglanti.execute("SELECT surum FROM sema_surumu")}
    return "009_uyari_kanallari.sql" in uygulananlar and AKTARIM_ADIMI not in uygulananlar


def env_anonsunu_aktar(baglanti: sqlite3.Connection, env_yolu: Path) -> list[str]:
    """.env'deki anons kanalını "Tüm fabrika" satırına BİR KEZ aktarır (K22).

    Bugünkü DUYULUR davranış aynen sürmeli (docs/17 §7.3-1):

    - ANONS=http: bugün anons önce bölümün, sonra "Tüm fabrika" hoparlörüne,
      ikisi de yoksa .env'deki adrese gidiyordu. "Tüm fabrika" satırı yoksa
      .env adresi o satır olur; varsa .env adresi zaten hiç kullanılmıyordu.
    - ANONS=ses_karti: bugün ses her ihlalde bu bilgisayarın seçili çıkışından
      çıkıyor, hoparlör bölgeleri KULLANILMIYORDU. Seçili çıkış "Tüm fabrika"
      satırı olur; eski satırlar kapalı aktarılır, yoksa aktarımdan sonra
      kendi bölümlerinde çalmaya başlarlardı.
    - ANONS=null: hiçbir yerden ses çıkmıyordu; eski satırlar kapalı aktarılır.

    Günlüğe yazılacak Türkçe cümleleri döndürür (boş = yapılacak bir şey yoktu).
    """
    if not _aktarim_gerekli_mi(baglanti):
        return []
    degerler = env_degerlerini_oku(env_yolu) if env_yolu.is_file() else {}
    anons = (degerler.get("ANONS") or "null").strip()
    cihaz = (degerler.get("ANONS_SES_CIHAZI") or "").strip()
    adres = (degerler.get("ANONS_HTTP_ADRESI") or "").strip()
    simdi = zaman.simdi_utc()
    mesajlar: list[str] = []
    with baglanti:
        if anons in ("null", "ses_karti"):
            kapatilan = baglanti.execute(
                "UPDATE speaker_zones SET enabled = 0, updated_at = ? WHERE enabled = 1",
                (simdi,),
            ).rowcount
            if kapatilan:
                mesajlar.append(
                    f"{kapatilan} hoparlör bölgesi kapalı aktarıldı: .env ANONS={anons} iken "
                    "kullanılmıyorlardı ve duyulan davranış değişmesin. Kullanmak için Anons "
                    "sayfasından açın."
                )
        if anons == "ses_karti":
            _tum_fabrika_ekle(baglanti, "ses_karti", "", cihaz, simdi)
            mesajlar.append(
                "Anons kanalı .env'den aktarıldı: “Tüm fabrika” = bu bilgisayarın ses çıkışı"
                + (f" ({cihaz})." if cihaz else " (işletim sisteminin varsayılanı).")
            )
        elif anons == "http" and adres:
            tum_fabrika = baglanti.execute(
                "SELECT 1 FROM speaker_zones WHERE area = '' AND enabled = 1"
            ).fetchone()
            if tum_fabrika is None:
                _tum_fabrika_ekle(baglanti, "http", adres, "", simdi)
                mesajlar.append(
                    "Anons kanalı .env'den aktarıldı: “Tüm fabrika” = IP hoparlör "
                    f"({adres_maskele(adres)})."
                )
        baglanti.execute(
            "INSERT INTO sema_surumu (surum, uygulanma_zamani) VALUES (?, ?)",
            (AKTARIM_ADIMI, simdi),
        )
    return mesajlar


def _tum_fabrika_ekle(
    baglanti: sqlite3.Connection, tur: str, adres: str, cihaz: str, simdi: str
) -> None:
    baglanti.execute(
        "INSERT INTO speaker_zones (name, area, address, description, enabled, kind, device, "
        "created_at, updated_at) VALUES (?, '', ?, ?, 1, ?, ?, ?, ?)",
        (
            TUM_FABRIKA,
            adres,
            ".env'deki anons ayarından aktarıldı (docs/17 K22).",
            tur,
            cihaz,
            simdi,
            simdi,
        ),
    )

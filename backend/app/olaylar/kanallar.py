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

KANAL_TURLERI = {
    "ses_karti": "Ses çıkışı (kablolu ya da Bluetooth)",
    "http": "IP hoparlör",
}
TUM_FABRIKA = "Tüm fabrika"  # area = '' satırının ekrandaki adı

# sema_surumu'na yazılan adım adı. Betik değildir (.sql değil); semayi_uygula
# yalnız .sql dosyalarını uyguladığı için karışmaz. MAX(surum) "009_…sql"de kalır.
AKTARIM_ADIMI = "009_uyari_kanallari.env_aktarimi"


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

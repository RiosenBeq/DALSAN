"""Zaman yönetiminin TEK yeri.

Kural: veritabanına yazılan her zaman `simdi_utc()` ile üretilmiş
ISO-8601 UTC metnidir; ekranda gösterilen her zaman `ekranda_goster()`
ile Türkiye saatine (Europe/Istanbul) çevrilir.

Kodun BAŞKA HİÇBİR YERİNDE datetime.now() kullanılmaz — iki ayrı saat
kaynağı olursa olay zamanları tutarsızlaşır (bkz. docs/08 R7).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    _ISTANBUL = ZoneInfo("Europe/Istanbul")
except ZoneInfoNotFoundError:
    # Windows'ta IANA saat dilimi veritabanı bulunmayabilir. Türkiye 2016'dan
    # beri yaz saati uygulamadan sabit UTC+3 kullanır; bu yedek o durumda
    # birebir aynı sonucu verir.
    _ISTANBUL = timezone(timedelta(hours=3), "Europe/Istanbul")


def simdi_utc() -> str:
    """Şu an, ISO-8601 UTC metni. Örnek: '2026-08-26T13:05:41+00:00'.

    Sabit uzunlukta olduğu için metin olarak sıralanabilir — SQLite'ta
    ORDER BY ve indeksler doğru çalışır.
    """
    return datetime.now(UTC).isoformat(timespec="seconds")


def gun_once_utc(gun: int) -> str:
    """Bugünden `gun` gün öncesi, ISO-8601 UTC metni (saklama süresi sınırı)."""
    return (datetime.now(UTC) - timedelta(days=gun)).isoformat(timespec="seconds")


def yerel_gun_baslangici_utc(tarih: str) -> str:
    """'2026-09-02' (Türkiye tarihi) → o günün 00:00'ının UTC karşılığı.

    Olay filtresi ekranda Türkiye saati gösterirken sınırları UTC sanırsa,
    gece 00:00-03:00 arası olaylar yanlış güne düşer (ya da hiç görünmez).
    """
    return _yerel_an_utc(tarih, 0)


def yerel_gun_sonu_utc(tarih: str) -> str:
    """'2026-09-02' → ERTESİ günün 00:00'ının UTC karşılığı (üst sınır, hariç).

    Gün sonunu 23:59:59 yerine ertesi günün başlangıcı olarak vermek, saniyenin
    altındaki damgaların da kapsanmasını garanti eder.
    """
    return _yerel_an_utc(tarih, 1)


def _yerel_an_utc(tarih: str, gun_ekle: int) -> str:
    try:
        gun = datetime.strptime(tarih, "%Y-%m-%d")
    except ValueError as hata:
        raise ValueError(f"Geçersiz tarih: {tarih!r} (beklenen biçim: YYYY-AA-GG)") from hata
    yerel = (gun + timedelta(days=gun_ekle)).replace(tzinfo=_ISTANBUL)
    return yerel.astimezone(UTC).isoformat(timespec="seconds")


def ekranda_goster(utc_metni: str) -> str:
    """UTC metnini Türkiye saatine çevirip 'GG.AA.YYYY SS:DD:SS' döndürür."""
    try:
        an = datetime.fromisoformat(utc_metni)
    except ValueError as hata:
        raise ValueError(f"Geçersiz zaman metni: {utc_metni!r}") from hata
    if an.tzinfo is None:
        # Saat dilimi belirtilmemiş metin UTC kabul edilir — veritabanındaki
        # her değer zaten UTC yazılır.
        an = an.replace(tzinfo=UTC)
    return an.astimezone(_ISTANBUL).strftime("%d.%m.%Y %H:%M:%S")

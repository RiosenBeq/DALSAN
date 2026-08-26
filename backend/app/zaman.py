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

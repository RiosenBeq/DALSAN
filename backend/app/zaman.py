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


def gun_basi_utc(gun_once: int = 0) -> str:
    """Türkiye saatine göre `gun_once` gün önceki günün 00:00'ı, UTC metni.

    `gun_once=0` bugünün başlangıcıdır. Komuta ekranındaki "bugün" ve
    "son 7 gün" pencereleri buradan gelir. Sınır UTC'ye göre kurulursa
    gece 00:00-03:00 arasındaki olaylar bir önceki güne düşer ve kullanıcı
    "bugünkü ihlal sayısı yanlış" der (docs/08 R7).
    """
    yerel = datetime.now(UTC).astimezone(_ISTANBUL) - timedelta(days=gun_once)
    gun_basi = yerel.replace(hour=0, minute=0, second=0, microsecond=0)
    return gun_basi.astimezone(UTC).isoformat(timespec="seconds")


def ekranda_goster(utc_metni: str) -> str:
    """UTC metnini Türkiye saatine çevirip 'GG.AA.YYYY SS:DD:SS' döndürür."""
    return _yerel(utc_metni).strftime("%d.%m.%Y %H:%M:%S")


def ekranda_goster_kisa(utc_metni: str) -> str:
    """Saniyesiz gösterim: 'GG.AA.YYYY SS:DD'.

    Komuta başlığındaki saat gibi, saniyenin bilgi taşımadığı yerler içindir.
    Biçim burada durur: ekran metnini kesip biçen ikinci bir yer olmasın.
    """
    return _yerel(utc_metni).strftime("%d.%m.%Y %H:%M")


def ekranda_tarih(utc_metni: str) -> str:
    """Yalnız tarih: 'GG.AA.YYYY'."""
    return _yerel(utc_metni).strftime("%d.%m.%Y")


def ekranda_saat(utc_metni: str) -> str:
    """Yalnız saat: 'SS:DD' — canlı akış satırlarındaki gibi, günü belli olan
    listelerde tarihi tekrar yazmamak için."""
    return _yerel(utc_metni).strftime("%H:%M")


def ne_kadar_once(utc_metni: str) -> str:
    """Geçen süreyi insan diliyle söyler: '1 sn önce', '48 sn önce', '3 dk önce'.

    Kamera sağlığı ekranında "son kare ne zaman geldi" sorusunun cevabıdır.
    Tam saat yazmak burada işe yaramaz: kullanıcı "14:37" ile "şimdi" arasını
    kafasında çıkarmak zorunda kalır. Biçim ve hesap tek yerde durur ki
    ekranın başka köşesinde farklı bir "önce" yazımı doğmasın.
    """
    saniye = (datetime.now(UTC) - _yerel(utc_metni)).total_seconds()
    if saniye < 0:
        # İleri tarihli damga: sunucu saati geri alınmış olabilir. Negatif
        # süre ("−3 sn önce") yazmak yerine nötr bir ifade kullanılır.
        return "az önce"
    if saniye < 60:
        return f"{max(int(saniye), 1)} sn önce"
    if saniye < 3600:
        return f"{int(saniye // 60)} dk önce"
    if saniye < 86400:
        return f"{int(saniye // 3600)} saat önce"
    return f"{int(saniye // 86400)} gün önce"


def yerel_saat(utc_metni: str) -> int:
    """Olayın Türkiye saatindeki saat dilimi (0-23) — saatlik histogram için."""
    return _yerel(utc_metni).hour


def _yerel(utc_metni: str) -> datetime:
    try:
        an = datetime.fromisoformat(utc_metni)
    except ValueError as hata:
        raise ValueError(f"Geçersiz zaman metni: {utc_metni!r}") from hata
    if an.tzinfo is None:
        # Saat dilimi belirtilmemiş metin UTC kabul edilir — veritabanındaki
        # her değer zaten UTC yazılır.
        an = an.replace(tzinfo=UTC)
    return an.astimezone(_ISTANBUL)

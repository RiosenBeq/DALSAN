"""SQLite bağlantısı ve sürümlü şema uygulaması.

Veritabanı tek dosyadır: veri/dalsan.db (docs/09 karar #2).
Şema, backend/sema/ altındaki sıralı .sql betikleriyle kurulur; uygulanan
betikler `sema_surumu` tablosunda tutulur ve iki kez uygulanmaz.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app import zaman
from app.hatalar import VeritabaniHatasi

# Şema betikleri: backend/sema/001_ilk.sql, 002_... (isim sırasına göre uygulanır)
SEMA_DIZINI = Path(__file__).resolve().parents[1] / "sema"


def baglanti_ac(veritabani_yolu: Path | str) -> sqlite3.Connection:
    """Doğru PRAGMA'larla yeni bir SQLite bağlantısı açar.

    PRAGMA'lar bağlantı bazlıdır; her bağlantıda yeniden verilmeleri gerekir.
    Bu yüzden sqlite3.connect() hiçbir yerde doğrudan çağrılmaz, hep bu
    fonksiyon kullanılır.
    """
    # PRAGMA'lar da try içinde: SQLite dosyayı tembel açar, bozuk bir dosyanın
    # hatası connect()'te değil ilk sorguda (ilk PRAGMA'da) çıkar. Kullanıcıya
    # ham İngilizce traceback yerine Türkçe mesaj gitmeli.
    try:
        baglanti = sqlite3.connect(str(veritabani_yolu))
        baglanti.row_factory = sqlite3.Row

        # foreign_keys = ON: SQLite yabancı anahtarları VARSAYILAN OLARAK ZORLAMAZ.
        # Bunu açmazsak silinen bir kameraya bağlı bölge/kural kayıtları sessizce
        # sahipsiz kalır ve veri bütünlüğü fark edilmeden bozulur.
        baglanti.execute("PRAGMA foreign_keys = ON")

        # journal_mode = WAL: analiz iş parçacığı olay YAZARKEN web sayfası aynı
        # anda OKUYABİLSİN. Varsayılan modda yazma, okuyanları bloklar.
        # (Bu ayar veritabanı dosyasında kalıcıdır; her bağlantıda vermek zararsızdır.)
        baglanti.execute("PRAGMA journal_mode = WAL")

        # busy_timeout: iki bağlantı aynı anda yazmaya çalışırsa hemen
        # "database is locked" hatası verme, 5 saniyeye kadar sıranı bekle.
        baglanti.execute("PRAGMA busy_timeout = 5000")
    except sqlite3.Error as hata:
        raise VeritabaniHatasi(
            f"Veritabanı açılamadı: {veritabani_yolu} — {hata}. "
            "Dosya bozuk olabilir; veri/yedekler/ içindeki son yedeği geri yükleyin "
            "veya dosyayı taşıyıp sistemi yeniden başlatın (boş veritabanı kurulur)."
        ) from hata

    return baglanti


def semayi_uygula(baglanti: sqlite3.Connection, sema_dizini: Path = SEMA_DIZINI) -> None:
    """sema/ altındaki .sql betiklerini isim sırasıyla, birer kez uygular.

    Uygulanan her betiğin adı sema_surumu tablosuna yazılır; kayıtlı betik
    atlanır. Böylece açılışta her seferinde çağrılabilir — idempotenttir.
    """
    baglanti.execute(
        "CREATE TABLE IF NOT EXISTS sema_surumu ("
        "  surum TEXT PRIMARY KEY,"
        "  uygulanma_zamani TEXT NOT NULL"
        ")"
    )
    baglanti.commit()

    uygulananlar = {satir["surum"] for satir in baglanti.execute("SELECT surum FROM sema_surumu")}

    betikler = sorted(sema_dizini.glob("*.sql"))
    if not betikler:
        raise VeritabaniHatasi(f"Şema betiği bulunamadı: {sema_dizini} klasörü boş.")

    for betik in betikler:
        if betik.name in uygulananlar:
            continue
        if "'" in betik.name:
            raise VeritabaniHatasi(f"Şema betiği adında tek tırnak olamaz: {betik.name}")
        sql = betik.read_text(encoding="utf-8")
        # Betik ile sürüm kaydı TEK transaction'da uygulanır: elektrik kesintisinde
        # ya ikisi de yazılır ya hiçbiri. Aksi halde "tablolar var ama sürüm kaydı yok"
        # durumunda sistem bir daha açılamazdı. Bu yüzden betikler BEGIN/COMMIT
        # İÇERMEZ; sarmalamayı burası yapar. (Değerler bizim ürettiğimiz dosya adı
        # ve zaman damgasıdır — kullanıcı girdisi değildir.)
        tam_sql = (
            "BEGIN;\n"
            f"{sql}\n"
            "INSERT INTO sema_surumu (surum, uygulanma_zamani) "
            f"VALUES ('{betik.name}', '{zaman.simdi_utc()}');\n"
            "COMMIT;\n"
        )
        try:
            baglanti.executescript(tam_sql)
        except sqlite3.Error as hata:
            baglanti.rollback()
            raise VeritabaniHatasi(f"Şema betiği uygulanamadı: {betik.name} — {hata}") from hata


def mevcut_surum(baglanti: sqlite3.Connection) -> str | None:
    """En son uygulanan şema betiğinin adı (ör. '001_ilk.sql')."""
    satir = baglanti.execute("SELECT MAX(surum) AS surum FROM sema_surumu").fetchone()
    return satir["surum"] if satir else None


def tablo_adlari(baglanti: sqlite3.Connection) -> list[str]:
    """Veritabanındaki tablo adları (SQLite'ın iç tabloları hariç)."""
    satirlar = baglanti.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [satir["name"] for satir in satirlar]

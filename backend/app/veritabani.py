"""SQLite bağlantısı ve sürümlü şema uygulaması.

Veritabanı tek dosyadır: veri/dalsan.db (docs/09 karar #2).
Şema, backend/sema/ altındaki sıralı .sql betikleriyle kurulur; uygulanan
betikler `sema_surumu` tablosunda tutulur ve iki kez uygulanmaz.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app import kaynaklar, zaman
from app.hatalar import VeritabaniHatasi

# Şema betikleri: backend/sema/001_ilk.sql, 002_... (isim sırasına göre uygulanır).
# Yol app/kaynaklar.py'den çözülür: paketlenmiş programda bu dosyalar depoda
# değil, paketin açıldığı geçici klasörde durur.
SEMA_DIZINI = kaynaklar.kaynak_yolu("backend", "sema")

# Bir şema betiği bu satırı içeriyorsa, betik çalışırken yabancı anahtar
# zorlaması KAPATILIR ve sonrasında geri açılır.
#
# NEDEN GEREKLİ: SQLite'ta bir CHECK kısıtını değiştirmenin tek yolu tabloyu
# yeniden kurmaktır (yeni tablo + kopyala + eskiyi bırak). `rules` tablosunu
# böyle taşırken `DROP TABLE rules`, yabancı anahtar zorlaması AÇIKKEN
# `events.rule_id ... ON DELETE SET NULL` eylemini tetikler ve TÜM OLAY
# GEÇMİŞİNİN kural bağlantısı sessizce silinir. Bu ölçülerek doğrulandı.
#
# NEDEN BETİĞİN İÇİNE PRAGMA YAZILAMAZ: bu PRAGMA bir işlemin İÇİNDE
# etkisizdir; betikler ise tek transaction içinde çalıştırılır. Bu yüzden
# anahtarı betik değil, uygulayıcı çevirir.
#
# Atomiklik BOZULMAZ: betik + sürüm kaydı yine tek transaction'dadır.
YABANCI_ANAHTAR_KAPALI = "-- DALSAN-SEMA: YABANCI-ANAHTAR-KAPALI"


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
        # check_same_thread=False: FastAPI, istek bağımlılığını threadpool'da,
        # async gövdeyi event loop'ta çalıştırabilir — bağlantı istek boyunca
        # SIRALI kullanılır, eşzamanlı kullanılmaz; CPython sqlite3 zaten
        # 'serialized' derlenir. Bu bayrak olmadan async uçlar ProgrammingError verir.
        baglanti = sqlite3.connect(str(veritabani_yolu), check_same_thread=False)
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
            # "Yedeği geri yükleyin" tek başına bir talimat değil: kullanıcı
            # yazılımcı değil, HANGİ dosyayı NEREYE koyacağını bilmiyor.
            "Kayıt dosyası açılamadı; bozulmuş olabilir. Kontrol Paneli'nde Durdur'a "
            "basın. Program klasöründeki veri/yedekler/ klasöründe duran en yeni "
            "dalsan-... dosyasını veri klasörüne kopyalayıp adını dalsan.db yapın, "
            "sonra Sistemi Başlat'a basın. Yedek yoksa bozuk dalsan.db dosyasının "
            "adını dalsan-bozuk.db yapın — sistem boş bir kayıt dosyasıyla açılır, "
            "eski olay kayıtları geri gelmez.",
            f"Veritabanı açılamadı: {veritabani_yolu} — {hata!r}",
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
        raise VeritabaniHatasi(
            "Sistem dosyaları eksik görünüyor: veritabanı kurulum dosyaları bulunamadı. "
            "Program klasörünü eksiksiz kopyalayıp yeniden deneyin; sorun sürerse "
            "program klasöründeki veri/loglar/sistem.log dosyasını destek ekibine iletin.",
            f"Şema betiği bulunamadı: {sema_dizini} klasörü boş.",
        )

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
        # Yabancı anahtar yalnızca betik açıkça istediyse kapatılır (bkz.
        # YABANCI_ANAHTAR_KAPALI). Kapatma transaction DIŞINDA yapılmalıdır.
        fk_kapatilacak = YABANCI_ANAHTAR_KAPALI in sql
        if fk_kapatilacak:
            baglanti.execute("PRAGMA foreign_keys = OFF")
        try:
            baglanti.executescript(tam_sql)
            if fk_kapatilacak:
                # Yeniden kurulan tablo, kendisine bakan kayıtları sahipsiz
                # bırakmış olabilir. Bu sessizce bozulmuş bir veritabanıdır;
                # açılış DURMALI ki kullanıcı yedeğe dönebilsin.
                bozuklar = baglanti.execute("PRAGMA foreign_key_check").fetchall()
                if bozuklar:
                    raise VeritabaniHatasi(
                        "Veritabanı güncellemesi yarım kaldı; kayıtlar arasındaki "
                        "bağlantılar bozulmuş görünüyor. Kontrol Paneli'nde Durdur'a "
                        "basıp 'Yedekten Geri Yükle' ile son yedeğe dönün.",
                        f"{betik.name} sonrası foreign_key_check {len(bozuklar)} "
                        f"bozuk satır buldu: {bozuklar[:5]}",
                    )
        except sqlite3.Error as hata:
            baglanti.rollback()
            raise VeritabaniHatasi(
                "Veritabanı güncellemesi tamamlanamadı; hiçbir değişiklik yazılmadı. "
                "Kontrol Paneli'nde Durdur'a, sonra Sistemi Başlat'a basın. Sorun sürerse "
                "program klasöründeki veri/loglar/sistem.log dosyasını destek ekibine iletin.",
                f"Şema betiği uygulanamadı: {betik.name} — {hata!r}",
            ) from hata
        finally:
            # Anahtar HER DURUMDA geri açılır: hata yüzünden kapalı kalırsa
            # bağlantının geri kalanı yabancı anahtar korumasız çalışırdı ve
            # bu, bozulmayı fark edilmeden büyütürdü.
            if fk_kapatilacak:
                baglanti.execute("PRAGMA foreign_keys = ON")


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

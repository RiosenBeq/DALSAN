"""Dosya yollarının TEK çözüm yeri.

İki ayrı soru vardır ve bu modül ikisini birbirinden ayırır:

1. **Kaynak dosyalar nerede?** — şablonlar, stil dosyaları, şema betikleri,
   `.env.example`. Bunlar programla birlikte gelir, program bunları YAZMAZ.
   Cevap: `kaynak_yolu(...)`.
2. **Yazılabilir veri nerede?** — `veri/` (veritabanı, kanıt fotoğrafları,
   günlük, yedekler), `models/` (indirilen model) ve `.env`. Bunlar
   kullanıcıya aittir, program bunlara YAZAR.
   Cevap: `veri_konumu()`.

NEDEN AYRILDI — paketleme (tek dosyalık uygulama) sırasında bu iki soru aynı
cevabı vermez:

* Kaynak dosyalar, program açılırken geçici bir klasöre açılır. `__file__`
  o klasörü göstermez; PyInstaller yerini `sys._MEIPASS` içinde bildirir.
* Uygulama paketinin kendisi SALT OKUNURDUR (macOS'ta imzalı `.app`,
  Windows'ta Program Files). Veritabanı, günlük ve indirilen model oraya
  yazılamaz; kullanıcı profilindeki klasöre yazılır.

Paketlenmemiş (geliştirme) çalışmada davranış BUGÜNKÜ HALİYLE aynıdır:
her iki soru da depo kökünü gösterir. Ayrım tek yerde, burada yapılır;
başka hiçbir dosya `sys._MEIPASS` ya da `__file__` ile yol çözmez.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Kullanıcı profilindeki klasörün adı. Ürün adıyla aynıdır: kullanıcı
# yedek alırken klasörü adından tanısın (masaüstü uygulaması: NextGen Detector).
UYGULAMA_ADI = "NextGen Detector"

# Yazılabilir kökün altındaki sabit yerleşim. Kayıtların "kurulu" sayılması
# için bakılan dosya budur.
_VERITABANI_IZI = ("veri", "dalsan.db")


def paketlenmis_mi() -> bool:
    """Program tek dosyalık paket olarak mı çalışıyor?

    PyInstaller, açtığı geçici kaynak klasörünü `sys._MEIPASS` içine yazar;
    normal Python çalıştırmasında bu değişken YOKTUR. Karar tam olarak bu
    değişkene bağlanır, çünkü kaynak dosyaların yerini belirleyen de odur.
    """
    return bool(getattr(sys, "_MEIPASS", ""))


def kaynak_yolu(*parcalar: str) -> Path:
    """Programla gelen (salt okunur) bir dosyanın tam yolu.

    Parçalar DEPO KÖKÜNE GÖRE verilir; paketleme yapılırken dosyalar pakete
    aynı klasör düzeniyle konur, böylece tek bir çağrı iki modda da çalışır:

        kaynak_yolu("backend", "sema")               → şema betikleri
        kaynak_yolu("backend", "app", "web", "templates")
        kaynak_yolu(".env.example")
    """
    return _kaynak_koku().joinpath(*parcalar)


def _kaynak_koku() -> Path:
    gecici_klasor = getattr(sys, "_MEIPASS", "")
    if gecici_klasor:
        return Path(gecici_klasor).resolve()
    # backend/app/kaynaklar.py → iki üst klasör depo köküdür.
    # __file__ YALNIZCA burada kullanılır (bkz. tests/test_paketlemeye_hazirlik.py).
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class VeriKonumu:
    """Yazılabilir kök + (varsa) kullanıcıya/günlüğe anlatılacak durum."""

    kok: Path
    # Ekrana ve Kontrol Paneli günlüğüne çıkan sade cümle. Olağan durumda boş.
    gunluk_notu: str = ""
    # Yalnızca veri/loglar/sistem.log'a yazılan tam yollar (loglama.py `ayrinti`).
    gunluk_ayrintisi: str = ""


def veri_konumu(
    program_dizini_: Path | None = None, kullanici_dizini: Path | None = None
) -> VeriKonumu:
    """`veri/`, `models/` ve `.env`'in duracağı klasörü seçer.

    Kurallar:

    * Paketlenmemiş çalışmada depo kökü kullanılır — BUGÜNKÜ davranış aynen
      korunur, geliştirme kurulumunun veri yolu değişmez.
    * Paketlenmiş çalışmada kullanıcı profilindeki klasör kullanılır.
    * ANCAK programın yanında (eski düzendeki gibi) zaten bir kayıt dosyası
      varsa ve yeni yerde yoksa, ESKİ YER kullanılmaya devam eder.

    Son kural bilerek böyledir: veriyi kullanıcıya sormadan taşımak, yapılacak
    en tehlikeli iştir. Kopyalama yarıda kalırsa ya da kullanıcı yedeğini eski
    klasörde ararsa, kayıtlarını bulamaz. Bunun yerine hiçbir şey taşınmaz,
    eski yer kullanılmaya devam edilir ve durum günlüğe yazılır.
    """
    if not paketlenmis_mi():
        return VeriKonumu(_kaynak_koku())

    program = (program_dizini_ or program_dizini()).resolve()
    yeni = (kullanici_dizini or kullanici_veri_koku()).resolve()
    if _kayit_dosyasi_var(program) and not _kayit_dosyasi_var(yeni):
        return VeriKonumu(
            program,
            gunluk_notu=(
                "Kayıtlar programın yanındaki klasörde bulundu; sistem oradan "
                "çalışmaya devam ediyor. Hiçbir dosya taşınmadı."
            ),
            gunluk_ayrintisi=f"kullanılan veri kökü: {program} (yeni konum boştu: {yeni})",
        )
    return VeriKonumu(yeni)


def _kayit_dosyasi_var(kok: Path) -> bool:
    """Bu klasörde daha önce çalışmış bir kurulum var mı?

    Ölçüt veritabanı dosyasıdır: geri getirilemeyecek tek şey odur. `.env`
    kaybolursa varsayılanlarla yeniden kurulur, olay kayıtları kurulamaz.
    """
    return kok.joinpath(*_VERITABANI_IZI).is_file()


def program_dizini() -> Path:
    """Paketlenmiş programın DURDUĞU klasör (yanındaki dosyaların yeri).

    macOS'ta çalışan dosya `Ad.app/Contents/MacOS/Ad` içindedir; kullanıcının
    gördüğü klasör `.app`'in bulunduğu klasördür.
    """
    calisan = Path(sys.executable).resolve()
    for ust in calisan.parents:
        if ust.suffix == ".app":
            return ust.parent
    return calisan.parent


def kullanici_veri_koku() -> Path:
    """İşletim sisteminin, uygulama verisi için ayırdığı yazılabilir klasör.

    macOS  : ~/Library/Application Support/NextGen Detector
    Windows: %LOCALAPPDATA%\\NextGen Detector
    Diğer  : ~/.local/share/NextGen Detector  (XDG_DATA_HOME varsa orası)
    """
    if sys.platform.startswith("win"):
        temel = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        temel = str(Path.home() / "Library" / "Application Support")
    else:
        temel = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(temel).expanduser() / UYGULAMA_ADI

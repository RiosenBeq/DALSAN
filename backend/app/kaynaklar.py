"""Dosya yollarının TEK çözüm yeri.

İki ayrı soru vardır ve bu modül ikisini birbirinden ayırır:

1. **Kaynak dosyalar nerede?** - şablonlar, stil dosyaları, şema betikleri,
   `.env.example`. Bunlar programla birlikte gelir, program bunları YAZMAZ.
   Cevap: `kaynak_yolu(...)`.
2. **Yazılabilir veri nerede?** - `veri/` (veritabanı, kanıt fotoğrafları,
   günlük, yedekler), `models/` (indirilen model) ve `.env`. Bunlar
   kullanıcıya aittir, program bunlara YAZAR.
   Cevap: `veri_konumu()`.

NEDEN AYRILDI - paketlenmiş uygulamada (PyInstaller klasör paketi, tek dosya
değil) bu iki soru aynı cevabı vermez:

* Kaynak dosyalar paketin içindeki bir klasördedir (Windows'ta `_internal`,
  macOS'ta `.app` içinde). PyInstaller yerini `sys._MEIPASS` içinde bildirir.
* O klasör SALT OKUNUR OLABİLİR (macOS'ta imzalı `.app`, Windows'ta Program
  Files) ve güncellemede üstüne yenisi kopyalanır. Veritabanı, günlük ve
  indirilen model bu yüzden oraya yazılmaz; kullanıcı profilindeki klasöre
  yazılır.

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
    """Program PyInstaller paketi olarak mı çalışıyor?

    PyInstaller, paketin kaynak klasörünü `sys._MEIPASS` içine yazar;
    normal Python çalıştırmasında bu değişken YOKTUR. Karar tam olarak bu
    değişkene bağlanır, çünkü kaynak dosyaların yerini belirleyen de odur.
    """
    return bool(getattr(sys, "_MEIPASS", ""))


def kapsayicida_mi() -> bool:
    """Program Docker kapsayıcısında mı çalışıyor?

    Sezgiye (/.dockerenv, cgroup) değil, Dockerfile'ın koyduğu AÇIK işarete
    bakılır: sezgiler geliştirici makinesinde yanlış "evet" diyebilir ve
    şifresiz kurulumu durdururdu. Karar iki yerde kullanılır: kapsayıcıda
    şifresiz açılış reddedilir (ayarlar.py, R13) ve eksik ayar dosyası için
    Docker'a özgü tarif verilir.
    """
    return os.environ.get("DALSAN_KAPSAYICI") == "1"


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

    * Paketlenmemiş çalışmada depo kökü kullanılır - BUGÜNKÜ davranış aynen
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


# ------------------------------------------------ ekranda gösterilecek yerler
#
# Hata mesajları, giriş sayfası ve kılavuz kullanıcıya bir dosyanın yerini
# söyler (günlük, ayar dosyası, anons sesleri). "Program klasörü" yalnız veri
# programın yanındaysa doğrudur: paketlenmiş programda veri kullanıcı
# profilindedir (veri_konumu) ve programın klasöründe aranan dosya bulunamaz.
# Yer bu yüzden tek yerde, burada söylenir.


def kurulum_turu() -> str:
    """Sistemin nasıl kurulduğu: "paket" (Windows ve Mac uygulaması, docs/13),
    "docker", "hizmet" (systemd birimi, docs/06 §1.2.1) ya da "kaynak" (Başlat
    betikleri). Docker gibi systemd de sezgiyle değil, birimin koyduğu açık
    işaretle (DALSAN_HIZMET=1) tanınır."""
    if paketlenmis_mi():
        return "paket"
    if kapsayicida_mi():
        return "docker"
    if os.environ.get("DALSAN_HIZMET") == "1":
        return "hizmet"
    return "kaynak"


def sunucu_kurulumu_mu() -> bool:
    """Docker ya da systemd: Kontrol Paneli yoktur, sistem sunucuda hizmet olarak
    çalışır ve onu sistem yöneticisi başlatıp durdurur (docs/06)."""
    return kurulum_turu() in ("docker", "hizmet")


# Sunucuyu kendi alt süreci olarak çalıştıran ve kapanınca yeniden açan
# masaüstü gözetmeni bu değişkeni "1" yapar: Başlat betiğinin Kontrol Paneli
# (masaustu/dalsan_launcher.py). Testler adın orada da aynı olduğunu denetler.
GOZETMEN_DEGISKENI = "DALSAN_GOZETMEN"


def yeniden_acan_var_mi() -> bool:
    """Program kapanırsa onu yeniden açan biri var mı?

    Docker (`restart:`) ve systemd (`Restart=`) açar; masaüstünde bu işi
    Kontrol Paneli ya da paketlenmiş uygulamanın gözetmeni yapar ve bunu
    GOZETMEN_DEGISKENI ile bildirir. Elle çalıştırılan sunucuyu (geliştirme,
    testler) kimse açmaz: bekçi orada süreçten çıkmaz, yalnız uyarır.
    """
    return sunucu_kurulumu_mu() or os.environ.get(GOZETMEN_DEGISKENI) == "1"


def baslatma_tarifi(*, yeniden: bool = True, cumle_basi: bool = True) -> str:
    """Sistemi (yeniden) başlatmanın bu kurulumdaki yolu: noktasız emir cümlesi.

    Masaüstünde (Başlat betikleri, Windows ve Mac uygulaması) Kontrol
    Paneli'nin düğmeleri; sunucu kurulumunda (Docker, systemd) Kontrol Paneli
    yoktur ve hata mesajı "Durdur'a basın" derse kullanıcı düğmeyi arar.
    """
    if sunucu_kurulumu_mu():
        metin = "sistemi sunucuda yeniden başlatın" if yeniden else "sistemi sunucuda başlatın"
        return metin[0].upper() + metin[1:] if cumle_basi else metin
    if yeniden:
        return "Kontrol Paneli'nde Durdur'a, sonra Sistemi Başlat'a basın"
    return "Kontrol Paneli'nde Sistemi Başlat'a basın"


def veri_klasoru_metni() -> str | None:
    """Paketlenmiş programın kullanıcı klasörü, ekranda gösterilecek biçimde.

    Dosya Gezgini'nin adres çubuğuna ya da Finder'ın "Klasöre Git" kutusuna
    olduğu gibi yapıştırılabilir ve kullanıcı adını içermez: mutlak yol
    ekranda gösterilmez (tests/test_ayarlar_sayfasi.py). Veri programın
    yanındaysa (geliştirme, Docker ya da eski düzende kalmış paket) None:
    o zaman doğru ad "program klasörü"dür.
    """
    if not paketlenmis_mi():
        return None
    try:
        # Hata mesajı yazılırken çağrılır (ör. kamera iş parçacığının son
        # çaresi, 500 sayfası): disk okunamıyorsa burası da patlamamalı.
        profilde = veri_konumu().kok == kullanici_veri_koku().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not profilde:
        return None
    if sys.platform.startswith("win"):
        return "%LOCALAPPDATA%\\" + UYGULAMA_ADI
    if sys.platform == "darwin":
        return "~/Library/Application Support/" + UYGULAMA_ADI
    temel = "$XDG_DATA_HOME" if os.environ.get("XDG_DATA_HOME") else "~/.local/share"
    return f"{temel}/{UYGULAMA_ADI}"


def kok_klasoru_adi() -> str:
    """Yazılabilir kökün adı, "klasörü" sözüyle çekimlenmek üzere:
    f"{kok_klasoru_adi()} klasörünün içinde" → "program klasörünün içinde"."""
    return veri_klasoru_metni() or "program"


@dataclass(frozen=True)
class EkranYolu:
    """Yazılabilir kökteki bir dosyanın ekrandaki yeri.

    `onek` kullanıcının bildiği klasörü anlatan sözdür ("program
    klasöründeki "), `yol` açılıp kopyalanacak kısımdır. Ayrı durur, çünkü
    şablonlar yalnız yolu kalın yazar. Metin olarak ikisi birleşir.
    """

    onek: str
    yol: str

    def __str__(self) -> str:
        return self.onek + self.yol


def ekran_yolu(*parcalar: str) -> EkranYolu:
    """`veri/loglar/sistem.log` gibi köke göre bir yolun ekrandaki yeri."""
    klasor = veri_klasoru_metni()
    if klasor is None:
        return EkranYolu("program klasöründeki ", "/".join(parcalar))
    ayrac = "\\" if sys.platform.startswith("win") else "/"
    return EkranYolu("", ayrac.join((klasor, *parcalar)))


def gunluk_dosyasi() -> EkranYolu:
    """Destek ekibine iletilecek günlük dosyasının yeri (loglama.py)."""
    return ekran_yolu("veri", "loglar", "sistem.log")


def ayar_dosyasi() -> EkranYolu:
    """Ayar dosyasının (.env) yeri.

    Docker'da ayarlar sunucudaki ayar/.env dosyasındadır (docker-compose.yml);
    kapsayıcının içindeki .env ona bağlanan bir yoldur.
    """
    if kapsayicida_mi():
        return EkranYolu("program klasöründeki ", "ayar/.env")
    return ekran_yolu(".env")

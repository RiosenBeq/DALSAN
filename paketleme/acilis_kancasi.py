"""Paketlenmiş uygulamada açılış hatalarını GÖRÜNÜR kılar (Windows + macOS).

Bu dosya PyInstaller'ın "runtime hook"udur: paketlenmiş programda, asıl
program başlamadan ÖNCE çalışır.

NEDEN GEREKLİ
-------------
İki platformda da uygulama pencereli üretilir (`console=False`): kullanıcı
çift tıklayınca arkasında siyah bir komut penceresi açılmaz. macOS'ta bir
`.app` Finder'dan açıldığında da durum aynıdır. Bedeli şudur:

1. `sys.stdout` ve `sys.stderr` YOKTUR (ikisi de None). Programın ekrana
   yazdığı her satır — hata mesajları dahil — hiçbir yere gitmez.
2. Program açılırken çökerse kullanıcı HİÇBİR ŞEY görmez: simgeye çift
   tıklar, bir saniye bekler, hiçbir şey olmaz. Ne söyleyeceğini bilemez,
   biz de sebebi öğrenemeyiz. (Bu gerçekten yaşandı: tkinter'ı olmayan bir
   Python'la üretilen .app Finder'da sessizce hiç açılmıyordu.)

Bu kanca üç işi yapar:

* Kayıp çıkış akışlarını bir dosyaya bağlar (boyutu sınırlıdır, aşağıya bak).
* Yakalanmamış her hatayı ayrıntısıyla dosyaya yazar.
* Kullanıcıya TÜRKÇE bir uyarı penceresi gösterir ve dosyanın yerini söyler.

Böylece "konsol gizli olsun" ile "hata görünsün" aynı anda sağlanır.

Kanca, paket dışında (normal `python` çalıştırmasında) HİÇBİR ŞEY yapmaz:
kurulum, dosyanın en altında `sys.frozen` kontrolüne bağlıdır. Testler bu
sayede modülü yan etkisiz okuyup parçalarını tek tek deneyebiliyor.
"""

import os
import sys
import traceback
from pathlib import Path

# Uygulamanın kendi modülleri (app.kaynaklar) okunamazsa kullanılacak son
# çare. Bilerek burada tekrarlanıyor: bu kancanın görevi, tam da uygulamanın
# kendi kodu yüklenemediğinde bile kullanıcıya bir şey söyleyebilmektir.
UYGULAMA_ADI = "NextGen Detector"

HATA_DOSYASI_ADI = "acilis-hatasi.log"
EKRAN_DOSYASI_ADI = "son-calistirma.log"

# Ekran akışı dosyasının üst sınırı. Sunucunun günlük satırları da buraya
# akar; 7/24 çalışan bir sistemde sınırsız bir dosya diski doldururdu. Açılış
# sorunları ilk saniyelerde görünür, 1 MB fazlasıyla yeter. Kalıcı kayıt
# zaten veri/loglar/sistem.log dosyasındadır ve o kendi kendine döner.
EKRAN_DOSYASI_SINIRI = 1024 * 1024


def gunluk_klasoru(kok: Path | None = None) -> Path:
    """Kayıtların yazılacağı klasör; yoksa oluşturur.

    Yer, uygulamanın geri kalanıyla AYNI kuraldan gelir (app/kaynaklar.py) —
    kullanıcı günlüğü, veritabanının ve kanıt fotoğraflarının yanında bulsun.
    """
    if kok is None:
        try:
            from app import kaynaklar

            kok = kaynaklar.veri_konumu().kok
        except (ImportError, OSError, ValueError):
            # Uygulamanın kendi modülü okunamıyor: hata muhtemelen bu yüzden.
            temel = os.environ.get("LOCALAPPDATA") or str(Path.home())
            kok = Path(temel) / UYGULAMA_ADI
    klasor = kok / "veri" / "loglar"
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


class SinirliDosya:
    """Dosyaya yazan, ama sınırı geçince susan çıkış akışı.

    `write` dışındaki her şey (flush, encoding, fileno, reconfigure…) gerçek
    dosyaya devredilir: kendisini bir dosya sanan kütüphaneler bozulmasın.
    """

    def __init__(self, dosya, sinir: int = EKRAN_DOSYASI_SINIRI) -> None:
        self._dosya = dosya
        self._kalan = sinir

    def write(self, metin: str) -> int:
        uzunluk = len(metin)
        if self._kalan <= 0:
            return uzunluk
        self._kalan -= uzunluk
        if self._kalan <= 0:
            metin += "\n[... dosya sınırına ulaşıldı, bundan sonrası yazılmadı ...]\n"
        self._dosya.write(metin)
        return uzunluk

    def __getattr__(self, ad: str):
        return getattr(self._dosya, ad)


def ciktilari_dosyaya_yonlendir(kok: Path | None = None) -> Path | None:
    """Kayıp `sys.stdout` / `sys.stderr` yerine bir dosya koyar.

    Dosya her açılışta SIFIRLANIR: içi, son çalıştırmanın ekran çıktısıdır.
    Akışlar zaten yerindeyse hiçbir şey yapılmaz (geliştirme kurulumu).
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None
    try:
        yol = gunluk_klasoru(kok) / EKRAN_DOSYASI_ADI
        dosya = open(yol, "w", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        # Klasör yazılamıyor (salt okunur disk, izin). Program yine de
        # açılmalı; hata penceresi bu durumda dosya adı vermeyecek.
        return None
    akis = SinirliDosya(dosya)
    if sys.stdout is None:
        sys.stdout = akis
    if sys.stderr is None:
        sys.stderr = akis
    return yol


def hatayi_yaz(metin: str, kok: Path | None = None) -> Path | None:
    """Hata ayrıntısını dosyaya ekler; dosyanın yolunu döndürür."""
    try:
        yol = gunluk_klasoru(kok) / HATA_DOSYASI_ADI
        with open(yol, "a", encoding="utf-8", errors="replace") as dosya:
            dosya.write(metin.rstrip() + "\n" + "-" * 70 + "\n")
        return yol
    except OSError:
        return None


def _mac_penceresi(mesaj: str) -> bool:
    """macOS'un kendi uyarı penceresi (osascript). Gösterildiyse True.

    Mesaj ARGÜMAN olarak geçirilir, betiğin içine gömülmez: tırnak, ters
    bölü ve satır sonu içeren bir metni AppleScript kaynağına yapıştırmak
    betiği bozar ve pencere hiç açılmaz — yani tam da işe yaraması gereken
    anda susardı.
    """
    if sys.platform != "darwin":
        return False
    if not getattr(sys, "frozen", False):
        # Paketlenmemiş çalışmada (geliştirme, test) stderr GÖRÜNÜR durumdadır;
        # pencereye gerek yoktur. Dahası: modal bir pencere test çalıştırmasını
        # kilitler ve ekranın ortasında beklemeye başlar — bu gerçekten oldu.
        return False
    betik = (
        "on run argv\n"
        f'  display dialog (item 1 of argv) with title "{UYGULAMA_ADI} — hata" '
        'buttons {"Tamam"} default button 1 with icon stop\n'
        "end run"
    )
    try:
        import subprocess

        subprocess.run(
            ["osascript", "-e", betik, mesaj],
            capture_output=True,
            timeout=120,
            check=False,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def pencerede_goster(dosya_yolu: Path | None) -> None:
    """Kullanıcıya Türkçe bir uyarı penceresi gösterir.

    İşletim sisteminin KENDİ ileti penceresi kullanılır (Windows'ta ctypes,
    macOS'ta osascript). tkinter BİLEREK kullanılmaz: çökme sebebimiz tam da
    tkinter'ın açılamaması olabilir — nitekim bir kez öyle oldu.
    """
    if dosya_yolu is None:
        mesaj = (
            "Program açılırken beklenmeyen bir hata oluştu ve durdu.\n\n"
            "Ayrıntılar kaydedilemedi (kayıt klasörüne yazılamıyor).\n\n"
            "Bilgisayarı yeniden başlatıp bir daha deneyin."
        )
    else:
        mesaj = (
            "Program açılırken beklenmeyen bir hata oluştu ve durdu.\n\n"
            "Ne olduğu şu dosyaya yazıldı:\n"
            f"{dosya_yolu}\n\n"
            "Bu dosyayı destek için gönderebilirsiniz."
        )
    if _mac_penceresi(mesaj):
        return
    try:
        import ctypes

        # MB_ICONERROR (0x10) + MB_SETFOREGROUND (0x10000): pencere öne gelsin.
        ctypes.windll.user32.MessageBoxW(None, mesaj, f"{UYGULAMA_ADI} — hata", 0x10 | 0x10000)
    except (AttributeError, OSError, ImportError):
        # Windows dışında ya da ileti penceresi açılamıyorsa: hiç değilse yaz.
        print(mesaj, file=sys.stderr)


def hata_yakalayici(tur, deger, iz) -> None:
    """Yakalanmamış hatalarda çağrılır (`sys.excepthook`)."""
    yol = hatayi_yaz("".join(traceback.format_exception(tur, deger, iz)))
    pencerede_goster(yol)


def kur() -> None:
    """Kancayı yerine takar."""
    _coklu_surec_tuzagini_kapat()
    ciktilari_dosyaya_yonlendir()
    sys.excepthook = hata_yakalayici


def _coklu_surec_tuzagini_kapat() -> None:
    """TUZAK: paketlenmiş programda `sys.executable` artık python değil,
    UYGULAMANIN KENDİSİDİR. Bir kütüphane arka planda ikinci bir işlem
    başlatmaya kalkarsa Windows uygulamayı baştan açar — ekranda ikinci bir
    Kontrol Paneli belirir, o da bir üçüncüsünü açar. `freeze_support`, böyle
    bir başlatmayı tanıyıp asıl programı çalıştırmadan bitirir.
    """
    import multiprocessing

    multiprocessing.freeze_support()


if getattr(sys, "frozen", False):
    try:
        kur()
    except (OSError, ValueError, ImportError) as hata:
        # Kanca kurulamazsa program YİNE DE açılmalı: kanca bir kolaylıktır,
        # ön koşul değil.
        print(f"[paketleme] acilis kancasi kurulamadi: {hata}", file=sys.stderr)

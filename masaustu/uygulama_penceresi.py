"""İzleme ekranını TARAYICI SEKMESİ yerine kendi penceresinde açar.

SORUN — Kontrol Paneli "İzleme Ekranını Aç" dediğinde `webbrowser.open()`
çağırıyordu. Sonuç, kullanıcının gördüğü haliyle şuydu: adres çubuğu, sekmeler,
yer imleri, arama kutusu, eklenti simgeleri. Yani bir UYGULAMA değil, bir web
sayfası. Görev çubuğunda/Dock'ta da programın değil TARAYICININ simgesi
görünüyordu; kullanıcı iki pencere arasında hangisinin "sistem" olduğunu
ayırt edemiyordu.

ÇÖZÜM — Chromium tabanlı tarayıcıların "uygulama kipi" (`--app=ADRES`).
Açılan pencerede adres çubuğu, sekme şeridi ve yer imleri YOKTUR; görev
çubuğunda AYRI bir giriş olarak, kendi başlığıyla durur. Kullanıcı açısından
bu bir uygulama penceresidir.

NEDEN pywebview / Qt / Electron DEĞİL (CLAUDE.md §3 — en az parça):

  * Windows'ta Microsoft Edge her kurulumda VARDIR ve kaldırılamaz. Yani
    ek bir şey indirmeden, kurmadan, paketlemeden uygulama penceresi elde
    edilir.
  * pywebview Windows'ta pythonnet + WebView2 çalışma zamanı ister; ikisi de
    paketin boyutunu ve "çalışmama" ihtimalini büyütür.
  * Qt/Electron zaten açıkça yasaklı (CLAUDE.md §4 — Node.js YOK).

DÜRÜST GERİ ÇEKİLME — uygun bir tarayıcı bulunamazsa (çıplak bir Mac'te
yalnız Safari varsa) sistem SESSİZCE olağan tarayıcıyı açar ve Kontrol Paneli
günlüğüne tek satır not düşer. "Uygulama gibi açılamadı" diye işi durdurmak,
çalışan bir ekranı hiç açmamaktan iyi değildir.

Bu modül tek başına çalışır: yalnızca standart kütüphaneyi kullanır ve
uygulamanın hiçbir parçasını import etmez, böylece testler onu doğrudan
okuyabilir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

# Uygulama kipinde açılan pencerenin ilk boyutu. Komuta ekranı bu genişlikte
# tek sütuna düşmeden sığar.
PENCERE_GENISLIGI = 1440
PENCERE_YUKSEKLIGI = 900

# Aday tarayıcılar, TERCİH SIRASINA göre. Sıra rastgele değil:
#   Windows'ta Edge her kurulumda vardır — ilk sırada olması, hiçbir şey
#   kurmamış bir kullanıcıda da uygulama penceresinin açılması demektir.
#   macOS'ta Edge genelde yoktur; Chrome ve Brave yaygındır.
# Safari ve Firefox BİLEREK YOK: ikisinin de uygulama kipi (çerçevesiz,
# sekmesiz pencere) yoktur. Listeye konsaydı sıradan bir tarayıcı sekmesi
# açılır, üstelik "uygulama gibi açıldı" sanılırdı.
# Yollar TERS BÖLÜLÜ METİN DEĞİL, parça listesi olarak yazılır: `Path` onları
# çalışılan işletim sisteminin ayracıyla birleştirir. Metin olsalardı bu
# arama yalnız Windows'ta anlamlı olur, dolayısıyla yalnız Windows'ta
# sınanabilirdi — yani hiç sınanmazdı (geliştirme Mac'te yapılıyor).
_WINDOWS_ADAYLARI = (
    ("Microsoft", "Edge", "Application", "msedge.exe"),
    ("Google", "Chrome", "Application", "chrome.exe"),
    ("BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ("Chromium", "Application", "chrome.exe"),
)

_MAC_ADAYLARI = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)

# Linux (geliştirme kurulumu). PATH'te aranır.
_LINUX_ADAYLARI = (
    "google-chrome",
    "google-chrome-stable",
    "microsoft-edge",
    "chromium",
    "chromium-browser",
    "brave-browser",
)


def tarayici_bul() -> str | None:
    """Uygulama kipini destekleyen bir tarayıcının tam yolu; yoksa None."""
    if sys.platform.startswith("win"):
        return _windows_tarayicisi()
    if sys.platform == "darwin":
        return next((aday for aday in _MAC_ADAYLARI if Path(aday).is_file()), None)
    return next((yol for aday in _LINUX_ADAYLARI if (yol := shutil.which(aday))), None)


def _windows_tarayicisi() -> str | None:
    """Edge/Chrome'un Windows'taki üç olağan kurulum kökünde aranması.

    Kayıt defteri (registry) BİLEREK okunmuyor: `winreg` yalnız Windows'ta
    vardır, bu modülün geri kalanı her yerde okunabilmeli ve üç klasör zaten
    kurulumların tamamına yakınını karşılıyor. 64-bit program klasörü ve
    kullanıcıya özel kurulum (LOCALAPPDATA) ayrı ayrı bakılıyor: Chrome
    yönetici hakkı olmayan bilgisayarlarda kullanıcı klasörüne kurulur ve
    yalnız "Program Files"a bakan bir arama onu HİÇ bulamaz.
    """
    kokler = [
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("PROGRAMFILES"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for aday in _WINDOWS_ADAYLARI:
        for kok in kokler:
            if not kok:
                continue
            yol = Path(kok).joinpath(*aday)
            if yol.is_file():
                return str(yol)
    return None


def komut(tarayici: str, adres: str, profil_klasoru: Path | None = None) -> list[str]:
    """Uygulama kipinde açan komut satırı.

    `--user-data-dir` ŞART, süs değil: bu bayrak olmadan pencere kullanıcının
    AÇIK tarayıcı oturumunun içinde açılır. Üç sonucu vardır ve üçü de kötüdür:
    kullanıcı tarayıcısını kapatınca sistem ekranı da kapanır; görev çubuğunda
    tarayıcıyla aynı simgenin altında gruplanır; eklentiler (reklam engelleyici,
    kurumsal ilkeler) sistemin sayfasına da karışır. Ayrı profil, pencereyi
    gerçekten ayrı bir uygulama yapar.
    """
    argumanlar = [
        tarayici,
        f"--app={adres}",
        f"--window-size={PENCERE_GENISLIGI},{PENCERE_YUKSEKLIGI}",
        # Bu pencere yalnızca 127.0.0.1'deki kendi sunucumuzu gösterir;
        # ilk açılış sihirbazı, oturum açma daveti ve varsayılan tarayıcı
        # sorusu burada yalnızca yolu tıkar.
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if profil_klasoru is not None:
        argumanlar.insert(1, f"--user-data-dir={profil_klasoru}")
    return argumanlar


def ac(adres: str, profil_klasoru: Path | None = None, log=None) -> bool:
    """İzleme ekranını açar. Uygulama penceresi açıldıysa True.

    False dönmesi BAŞARISIZLIK DEĞİLDİR: ekran yine açılmıştır, yalnızca
    olağan tarayıcıda. Dönüş değeri çağıranın günlüğe doğru cümleyi
    yazabilmesi içindir.
    """

    def yaz(satir: str) -> None:
        if log is not None:
            log(satir)

    tarayici = tarayici_bul()
    if tarayici is not None:
        if profil_klasoru is not None:
            try:
                profil_klasoru.mkdir(parents=True, exist_ok=True)
            except OSError:
                # Profil klasörü açılamıyorsa bayrağı hiç verme: bozuk bir yol
                # veren tarayıcı hiç açılmaz. Profilsiz pencere yine iş görür.
                profil_klasoru = None
        try:
            subprocess.Popen(  # noqa: S603 — yol bizim listemizden, kullanıcı girdisi değil
                komut(tarayici, adres, profil_klasoru),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError as hata:
            # Tarayıcı dosyası duruyor ama çalıştırılamıyor (izin, bozuk
            # kurulum, virüs korumasının kilidi). Sebep günlüğe yazılır ve
            # olağan tarayıcıya düşülür — kullanıcı ekransız kalmaz.
            yaz(f"[!] Uygulama penceresi açılamadı ({hata}); tarayıcıda açılıyor.")
    else:
        yaz(
            "[i] Uygulama penceresi için Chrome, Edge veya Brave gerekiyor; "
            "ekran olağan tarayıcıda açılıyor."
        )
    webbrowser.open(adres)
    return False

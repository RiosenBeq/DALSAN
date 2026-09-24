"""İzleme ekranını TARAYICI AÇMADAN, programın kendi penceresinde gösterir.

Operatör isteği (23.09.2026): *"zaten exe olarak olması lazım tarayıcı da
açılmaması lazım ve bunu en iyi uygulama şeklinde yap fabrikada olacağı
için"*. Sıra şudur:

1. KENDİ PENCERESİ (asıl yol). Ekranı işletim sisteminin yerleşik web
   görünümü çizer: Windows'ta WebView2 (Windows 10/11 ile gelir), macOS'ta
   WKWebView (işletim sisteminin parçası). Aracı `pywebview`'dir ve
   paketlenmiş uygulamanın içinde gelir. Adres çubuğu, sekme ve yer imi
   YOKTUR; pencere görev çubuğunda / Dock'ta programın simgesiyle durur.

   Pencere programın AYRI bir kopyasında açılır (`--izleme-penceresi`):
   macOS'ta hem Kontrol Paneli (Tk) hem web görünümü ana iş parçacığını ister,
   ikisi aynı süreçte yaşayamaz. İki süreç arasındaki dil birkaç satırdır:
   pencere sayfayı yükleyince `HAZIR` yazar, panel `GOSTER` yazınca pencere
   öne gelir. Panel kapanınca (ya da çökünce) kanal kapanır ve pencere de
   kendini kapatır: sunucusu durmuş boş bir ekran ortada kalmaz.

2. TARAYICISIZ YEDEK. Web görünümü kurulamazsa (Windows'ta WebView2 çalışma
   zamanı silinmiş ya da bozuk) Chromium tabanlı bir tarayıcının "uygulama
   kipi" (`--app=ADRES`) kullanılır: adres çubuğu ve sekme şeridi olmayan
   ayrı bir pencere. Windows'ta Edge her kurulumda vardır.

3. OLAĞAN TARAYICI SEKMESİ HİÇ AÇILMAZ. İkisi de olmazsa Kontrol Paneli
   günlüğüne neyin eksik olduğu ve ne yapılacağı yazılır. Fabrikada
   "tarayıcı açıldı" durumu bir daha yaşanmasın diye bu yol bilerek kapalı.

Kontrol Paneli tarafı yalnızca standart kütüphaneyi kullanır ve uygulamanın
hiçbir parçasını import etmez; testler modülü doğrudan okuyabilir.
`pywebview` yalnız pencere sürecinde, fonksiyonun içinde yüklenir.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

# Pencerenin ilk boyutu. Komuta ekranı bu genişlikte tek sütuna düşmeden sığar.
PENCERE_GENISLIGI = 1440
PENCERE_YUKSEKLIGI = 900
# Bundan dar bir pencerede komuta ekranı okunmaz hale gelir.
EN_KUCUK_PENCERE = (1024, 640)
PENCERE_BASLIGI = "NextGen Detector - İzleme Ekranı"
# Sayfa yüklenene kadar görünen zemin: arayüzün kendi zemin rengi (stil.css
# --zemin). Beyaz olsaydı her açılışta ekran bir an parlardı.
PENCERE_ZEMINI = "#EEF1F6"

# pywebview'ün kendi metinleri: Mac'in uygulama menüsü, sayfadaki onay
# kutusunun düğmeleri (onay.js window.confirm), indirmedeki kaydetme
# penceresi, Windows'un dosya süzgeci. Verilmezse İngilizce çıkarlar
# ("OK/Cancel", "Quit"); arayüz Türkçedir. Anahtarlar pywebview 6.2.1'in
# webview/localization.py dosyasındakilerdir. Mac menüsünde uygulamanın adı
# metnin SONUNA eklenir ("Hakkında: NextGen Detector").
PYWEBVIEW_METINLERI = {
    "global.quitConfirmation": "Çıkmak istediğinize emin misiniz?",
    "global.ok": "Tamam",
    "global.quit": "Çık",
    "global.cancel": "Vazgeç",
    "global.saveFile": "Dosyayı kaydet",
    "cocoa.menu.about": "Hakkında:",
    "cocoa.menu.services": "Servisler",
    "cocoa.menu.view": "Görüntü",
    "cocoa.menu.edit": "Düzen",
    "cocoa.menu.hide": "Gizle:",
    "cocoa.menu.hideOthers": "Diğerlerini Gizle",
    "cocoa.menu.showAll": "Tümünü Göster",
    "cocoa.menu.quit": "Çık:",
    "cocoa.menu.fullscreen": "Tam Ekrana Geç",
    "cocoa.menu.cut": "Kes",
    "cocoa.menu.copy": "Kopyala",
    "cocoa.menu.paste": "Yapıştır",
    "cocoa.menu.selectAll": "Tümünü Seç",
    "windows.fileFilter.allFiles": "Tüm dosyalar",
    "windows.fileFilter.otherFiles": "Diğer dosya türleri",
    "linux.openFile": "Dosya aç",
    "linux.openFiles": "Dosyaları aç",
    "linux.openFolder": "Klasör aç",
}

# Program bu bağımsız değişkenle açılınca Kontrol Paneli yerine yalnız izleme
# penceresi açılır (dalsan_launcher.py buna Tk kurulmadan önce bakar).
YEREL_PENCERE_ARGUMANI = "--izleme-penceresi"
# Paketin kendi kendini sınaması: pencere bileşeni pakete girmiş ve bu
# bilgisayarda yükleniyor mu? Pencere AÇMAZ (docs/13 §7).
PENCERE_DENETIM_ARGUMANI = "--pencere-denetimi"

# Pencere süreci ile Kontrol Paneli arasındaki satırlar.
HAZIR_SINYALI = "HAZIR"  # pencere -> panel: sayfa yüklendi, pencere açık
HATA_ONEKI = "HATA "  # pencere -> panel: sebep; panel günlüğüne yazılır
ONE_GETIR = "GOSTER"  # panel -> pencere: öne gel

# Web görünümü kurulduğu halde sayfa bu sürede HİÇ yüklenmezse (WebView2
# bozuk) pencere kendini kapatır ve panel yedek pencereye geçer. Sunucu
# kapalıyken bile sayfa hemen yüklenir: web görünümü bir hata sayfası çizer.
YUKLEME_BEKLEMESI_SN = 20.0
# Panel, HAZIR satırını ya da sürecin kapanmasını en çok bu kadar bekler.
# Yukarıdakinden UZUN olmalı: kısa olsaydı yüklenemeyen pencere, panel
# beklemeyi bıraktıktan sonra kapanır ve yedek pencere hiç açılmazdı.
# Arka planda beklenir; panel bu sırada donmaz.
YEREL_ACILIS_BEKLEMESI_SN = 45.0
# Panel kapanırken pencerenin kendini kapatması için tanınan süre.
KAPANIS_BEKLEMESI_SN = 2.0

KOD_KULLANIM = 2
KOD_PYWEBVIEW_YOK = 3
KOD_WEB_GORUNUMU_KURULAMADI = 4
_SEBEPLER = {
    KOD_KULLANIM: "pencere süreci eksik bilgiyle başlatıldı",
    KOD_PYWEBVIEW_YOK: "pencere bileşeni (pywebview) bu kurulumda yok",
    KOD_WEB_GORUNUMU_KURULAMADI: "işletim sisteminin web görünümü açılamadı",
}

# Açık izleme penceresinin süreci. Kilit, iki hızlı tıklamanın iki pencere
# açmasını önler.
_kilit = threading.Lock()
_yerel_surec: subprocess.Popen | None = None

# YEDEK yolun aday tarayıcıları, TERCİH SIRASINA göre. Sıra rastgele değil:
#   Windows'ta Edge her kurulumda vardır - ilk sırada olması, hiçbir şey
#   kurmamış bir kullanıcıda da uygulama penceresinin açılması demektir.
#   macOS'ta Edge genelde yoktur; Chrome ve Brave yaygındır.
# Safari ve Firefox BİLEREK YOK: ikisinin de uygulama kipi (çerçevesiz,
# sekmesiz pencere) yoktur. Listeye konsaydı sıradan bir tarayıcı sekmesi
# açılır, üstelik "uygulama gibi açıldı" sanılırdı.
# Yollar TERS BÖLÜLÜ METİN DEĞİL, parça listesi olarak yazılır: `Path` onları
# çalışılan işletim sisteminin ayracıyla birleştirir. Metin olsalardı bu
# arama yalnız Windows'ta anlamlı olur, dolayısıyla yalnız Windows'ta
# sınanabilirdi - yani hiç sınanmazdı (geliştirme Mac'te yapılıyor).
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


# ============================================================ Kontrol Paneli


def ac(adres: str, profil_klasoru: Path | None = None, log=None) -> bool:
    """İzleme ekranını açar; açıldıysa True. TARAYICI SEKMESİ AÇMAZ.

    Önce programın kendi penceresi, olmazsa tarayıcının uygulama kipi.
    Pencere sürecinin açıldığı anlaşılana kadar saniyeler sürebilir: Kontrol
    Paneli bunu arka planda çağırır. Pencere zaten açıksa öne getirilir.
    """

    def yaz(satir: str) -> None:
        if log is not None:
            log(satir)

    # Web görünümünün verisi (giriş çerezi, ekranın ses tercihi) yedek
    # pencerenin profilinden ayrı bir alt klasörde durur.
    pencere_profili = profil_klasoru / "pencere" if profil_klasoru is not None else None
    if _yerel_pencere_dene(adres, pencere_profili, yaz):
        return True
    if _uygulama_kipinde_ac(adres, profil_klasoru, yaz):
        yaz("[i] İzleme ekranı yedek pencerede açıldı (tarayıcının uygulama kipi).")
        return True
    yaz(
        "[!] İzleme ekranı açılamadı: bu bilgisayarda gereken web görünümü yok. "
        "Windows'ta Microsoft Edge WebView2 çalışma zamanını kurun (Microsoft'un "
        "sitesinden, ücretsiz), sonra 'İzleme Ekranını Aç' düğmesine basın. "
        "Sistem ve uyarı kanalları çalışmaya devam ediyor. "
        f"Ekran adresi: {adres}"
    )
    return False


def pencereyi_kapat() -> None:
    """Kontrol Paneli kapanırken açık izleme penceresini de kapatır.

    Önce kanal kapatılır, pencere kendini kapatır; süre içinde kapanmazsa
    süreç sonlandırılır. Kilit ALINMAZ: panelin ana iş parçacığından çağrılır
    ve açılmakta olan bir pencereyi beklerken paneli dondurmamalı (o pencere
    de panel kapanınca kanalı kapanmış bulur ve kendini kapatır).
    """
    global _yerel_surec
    surec, _yerel_surec = _yerel_surec, None
    if surec is None or surec.poll() is not None:
        return
    try:
        surec.stdin.close()
    except OSError:
        # Kanal zaten kopmuş: aşağıdaki bekleme süreci yine sonlandırır.
        pass
    try:
        surec.wait(timeout=KAPANIS_BEKLEMESI_SN)
    except subprocess.TimeoutExpired:
        surec.terminate()


def yerel_pencere_komutu(adres: str, profil_klasoru: Path | None = None) -> list[str]:
    """Pencere sürecini başlatan komut: programın KENDİSİ + bağımsız değişkenler.

    Paketlenmiş uygulamada `sys.executable` uygulamanın kendisidir (NextGen
    Detector.exe ya da .app'in içindeki program); geliştirmede Python'dur ve
    bu dosya betik olarak çalışır.
    """
    if getattr(sys, "frozen", False):
        satir = [sys.executable, YEREL_PENCERE_ARGUMANI, adres]
    else:
        satir = [sys.executable, str(Path(__file__).resolve()), YEREL_PENCERE_ARGUMANI, adres]
    if profil_klasoru is not None:
        satir.append(str(profil_klasoru))
    return satir


def _yerel_pencere_dene(adres: str, profil_klasoru: Path | None, yaz) -> bool:
    """Ekranı programın kendi penceresinde açar; açılamadıysa False."""
    global _yerel_surec
    with _kilit:
        acik = _yerel_surec
        if acik is not None and acik.poll() is None:
            _one_gelmesine_izin_ver(acik)
            if _satir_gonder(acik, ONE_GETIR):
                return True
        _yerel_surec = None
        try:
            surec = subprocess.Popen(  # noqa: S603 - komut programın kendisi
                yerel_pencere_komutu(adres, profil_klasoru),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                # Geliştirmede python.exe bir konsol programıdır; bu bayrak
                # olmasa pencerenin arkasında siyah bir komut penceresi açılırdı.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as hata:
            yaz(f"[!] Uygulama penceresi başlatılamadı ({hata}).")
            return False
        hazir = threading.Event()
        durum = {"bekleniyor": True, "sebepler": []}
        threading.Thread(
            target=_ciktiyi_izle,
            args=(surec, hazir, durum, yaz),
            daemon=True,
            name="izleme-penceresi-kanali",
        ).start()
        hazir.wait(YEREL_ACILIS_BEKLEMESI_SN)
        durum["bekleniyor"] = False
        kod = surec.poll()
        if kod is None:
            # HAZIR geldi ya da pencere hâlâ açılıyor (çok yavaş bir
            # bilgisayar). İkisinde de pencere yolda: yedek açılsaydı iki
            # pencere olurdu.
            _yerel_surec = surec
            return True
        if kod == 0:
            # Pencere açıldı ve kullanıcı (belki daha yüklenirken) kapattı: hata değil.
            return True
        sebep = _SEBEPLER.get(kod, f"pencere süreci {kod} koduyla kapandı")
        if durum["sebepler"]:
            sebep = f"{sebep}: {durum['sebepler'][-1]}"
        yaz(f"[i] Uygulama penceresi açılamadı ({sebep}).")
        return False


def _ciktiyi_izle(surec: subprocess.Popen, hazir: threading.Event, durum: dict, yaz) -> None:
    """Pencere sürecinin çıktısını SONUNA kadar okur (arka plan iş parçacığı).

    HAZIR gelince bekleyeni uyandırır; süreç kapanınca da (çıkış kodu okunmuş
    olarak). Okumayı pencere açıldıktan sonra da sürdürür: okunmayan bir boru
    dolar ve pencere süreci yazmaya çalışırken donar.
    """
    try:
        for ham in surec.stdout:
            satir = ham.strip()
            if satir == HAZIR_SINYALI:
                hazir.set()
            elif satir.startswith(HATA_ONEKI):
                sebep = satir[len(HATA_ONEKI) :]
                durum["sebepler"].append(sebep)
                if not durum["bekleniyor"]:
                    yaz(f"[i] İzleme penceresi: {sebep}")
    except (OSError, ValueError):
        # Kanal koptu: süreç kapanıyor; çıkış kodu aşağıda okunur.
        pass
    kod = surec.wait()
    if not durum["bekleniyor"] and kod != 0:
        sebep = _SEBEPLER.get(kod, f"{kod} koduyla kapandı")
        yaz(f"[!] İzleme penceresi kapandı ({sebep}). 'İzleme Ekranını Aç' ile yeniden açın.")
    hazir.set()


def _satir_gonder(surec: subprocess.Popen, satir: str) -> bool:
    try:
        surec.stdin.write(satir + "\n")
        surec.stdin.flush()
    except (OSError, ValueError):
        # Kanal kopmuş: pencere süreci kapanıyor. Çağıran yenisini açar.
        return False
    return True


def _one_gelmesine_izin_ver(surec: subprocess.Popen) -> None:
    """Windows, arkadaki bir programın kendini öne almasını engeller.

    Düğmeye basılan panel o an öndedir; izni pencere sürecine devreder.
    Verilemezse pencere yine öne gelmeye çalışır, en kötü görev çubuğunda
    yanıp söner. Başka işletim sistemlerinde gerekmez.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.user32.AllowSetForegroundWindow(surec.pid)
    except (AttributeError, OSError):
        pass


# ============================================================ tarayıcısız yedek


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


def _uygulama_kipinde_ac(adres: str, profil_klasoru: Path | None, yaz) -> bool:
    """Tarayıcının adres çubuksuz, sekmesiz uygulama penceresi; yoksa False."""
    tarayici = tarayici_bul()
    if tarayici is None:
        return False
    if profil_klasoru is not None:
        try:
            profil_klasoru.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Profil klasörü açılamıyorsa bayrağı hiç verme: bozuk bir yol
            # veren tarayıcı hiç açılmaz. Profilsiz pencere yine iş görür.
            profil_klasoru = None
    try:
        subprocess.Popen(  # noqa: S603 - yol bizim listemizden, kullanıcı girdisi değil
            komut(tarayici, adres, profil_klasoru),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as hata:
        yaz(f"[!] Yedek pencere açılamadı ({hata}).")
        return False
    return True


# ============================================================ pencere süreci


def pencere_sureci_mi(argumanlar: list[str]) -> bool:
    """Program izleme penceresi (ya da paket sınaması) olarak mı açıldı?"""
    return YEREL_PENCERE_ARGUMANI in argumanlar or PENCERE_DENETIM_ARGUMANI in argumanlar


def pencere_sureci_ana(argumanlar: list[str]) -> int:
    """`--izleme-penceresi ADRES [PROFİL]` ya da `--pencere-denetimi` ile açılan kopya."""
    for akis in (sys.stdin, sys.stdout):
        # Panel satırları UTF-8 okuyup yazar; Windows'un yerel kod sayfası
        # (cp1254) Türkçe sebep metinlerini bozardı.
        if akis is not None and hasattr(akis, "reconfigure"):
            try:
                akis.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    if PENCERE_DENETIM_ARGUMANI in argumanlar:
        return pencere_denetimi()
    try:
        sira = argumanlar.index(YEREL_PENCERE_ARGUMANI)
        adres = argumanlar[sira + 1]
    except (ValueError, IndexError):
        _cikti(f"{HATA_ONEKI}kullanım: {YEREL_PENCERE_ARGUMANI} ADRES [PROFİL]")
        return KOD_KULLANIM
    profil = Path(argumanlar[sira + 2]) if len(argumanlar) > sira + 2 else None
    return yerel_pencereyi_calistir(adres, profil)


def yerel_pencereyi_calistir(adres: str, profil_klasoru: Path | None = None) -> int:
    """Web görünümünü açar ve pencere kapanana kadar döner; çıkış kodu (KOD_*).

    Oturum çerezi (giriş şifresi varsa) ve ekranın ses tercihi
    `profil_klasoru`nda saklanır: her açılışta yeniden sorulmaz.
    """
    try:
        import webview
    except ImportError as hata:
        _cikti(f"{HATA_ONEKI}{hata}")
        return KOD_PYWEBVIEW_YOK

    hal = {"motor": None, "yuklenemedi": False, "kucuk": False, "buyuk": False}

    def motoru_denetle(renderer: str) -> bool:
        hal["motor"] = renderer
        # WebView2 yoksa pywebview Windows'ta Internet Explorer motoruna
        # düşer. İzleme ekranı orada çalışmaz (canlı akış ve güncel
        # JavaScript yok): False dönünce pencere hiç açılmaz, panel yedek
        # pencereye geçer.
        return renderer != "mshtml"

    try:
        # İndirmeler (CSV, veri seti) pencerede de çalışsın: kaydetme
        # penceresi açılır. Yeni pencere isteyen bir bağlantı da TARAYICIYI
        # açmasın, aynı pencerede açılsın (arayüzde böyle bağlantı yok;
        # tests/test_uygulama_penceresi.py korur).
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
        pencere = webview.create_window(
            PENCERE_BASLIGI,
            adres,
            width=PENCERE_GENISLIGI,
            height=PENCERE_YUKSEKLIGI,
            min_size=EN_KUCUK_PENCERE,
            background_color=PENCERE_ZEMINI,
            # Olağan bir sayfa gibi: yazı seçilip kopyalanabilir, büyük
            # ekranda yakınlaştırılabilir (pywebview ikisini de kapalı başlatır).
            text_select=True,
            zoomable=True,
        )
        pencere.events.initialized += motoru_denetle
        pencere.events.minimized += lambda: hal.update(kucuk=True)
        pencere.events.maximized += lambda: hal.update(kucuk=False, buyuk=True)
        pencere.events.restored += lambda: hal.update(kucuk=False, buyuk=False)
        depo = None
        if profil_klasoru is not None:
            profil_klasoru.mkdir(parents=True, exist_ok=True)
            depo = str(profil_klasoru)
        # Arka plan işi SÜREÇ KAPANIŞINI BEKLETMEZ (daemon): kullanıcı pencereyi
        # kapatınca süreç hemen biter. Bitmeseydi panel onu açık sanar,
        # düğmeye basılınca penceresi olmayan bir sürece "öne gel" derdi.
        threading.Thread(
            target=_pencere_gorevi, args=(pencere, hal), daemon=True, name="panel-kanali"
        ).start()
        # private_mode=False: giriş çerezi ve ses tercihi kalıcı olsun.
        webview.start(private_mode=False, storage_path=depo, localization=dict(PYWEBVIEW_METINLERI))
    except Exception as hata:  # noqa: BLE001 - sebep panele yazılır, yedek pencereye geçilir
        _cikti(f"{HATA_ONEKI}{hata!r}")
        return KOD_WEB_GORUNUMU_KURULAMADI
    if hal["motor"] == "mshtml":
        _cikti(f"{HATA_ONEKI}WebView2 çalışma zamanı bulunamadı")
        return KOD_WEB_GORUNUMU_KURULAMADI
    if hal["yuklenemedi"]:
        return KOD_WEB_GORUNUMU_KURULAMADI
    return 0


def _pencere_gorevi(pencere, hal: dict) -> None:
    """Pencere sürecinin arka plan işi: sayfa yüklenince haber ver, paneli dinle."""
    if not pencere.events.loaded.wait(YUKLEME_BEKLEMESI_SN):
        # Web görünümü kuruldu ama sayfa hiç yüklenmedi: WebView2 bozuk.
        hal["yuklenemedi"] = True
        _cikti(f"{HATA_ONEKI}sayfa {int(YUKLEME_BEKLEMESI_SN)} saniyede yüklenmedi")
        try:
            pencere.destroy()
        except Exception:  # noqa: BLE001 - pencere hiç oluşmadı: süreç yine de bitmeli
            os._exit(KOD_WEB_GORUNUMU_KURULAMADI)
        return
    _cikti(HAZIR_SINYALI)
    giris = sys.stdin
    if giris is None:
        return  # panel olmadan (elle) açılmış pencere: dinlenecek kanal yok
    try:
        for satir in giris:
            if satir.strip() == ONE_GETIR:
                _one_getir(pencere, hal)
    except (OSError, ValueError):
        # Kanal okunamıyor: pencere açık kalır; panel kapanırken süreci sonlandırır.
        return
    # Kanal kapandı: Kontrol Paneli kapandı ya da çöktü. Sunucu da durduğu için
    # ekran boş kalırdı; pencere de kapanır.
    try:
        pencere.destroy()
    except Exception as hata:  # noqa: BLE001 - kullanıcı pencereyi tam bu anda kapatmış olabilir
        _cikti(f"{HATA_ONEKI}pencere kapatılamadı ({hata!r})")


def _one_getir(pencere, hal: dict) -> None:
    """Paneldeki düğmeye basılınca açık pencereyi öne getirir."""
    try:
        if hal["kucuk"]:
            # Küçültülmeden önce ekranı kaplıyorsa yine ekranı kaplasın.
            if hal["buyuk"]:
                pencere.maximize()
            else:
                pencere.restore()
        pencere.show()
    except Exception as hata:  # noqa: BLE001 - kapanmakta olan pencere; sebep panele yazılır
        _cikti(f"{HATA_ONEKI}pencere öne getirilemedi ({hata!r})")


def _cikti(satir: str) -> None:
    """Pencere sürecinden Kontrol Paneli'ne bir satır."""
    akis = sys.stdout
    if akis is None:
        return  # panel olmadan (elle) açılmış pencere: okuyan yok
    try:
        akis.write(satir + "\n")
        akis.flush()
    except (OSError, ValueError):
        # Panel kapanmış: okuyan yok, pencere işine devam eder.
        pass


def pencere_denetimi() -> int:
    """Paket sınaması: pencere bileşeni pakette mi, bu bilgisayarda yükleniyor mu?

    Pencere AÇMAZ. Uygulamayı üreten iş (GitHub Actions) ve destek kullanır:
    `NextGen Detector.exe --pencere-denetimi` 0 ile bitmeli (docs/13 §7).
    """
    try:
        import webview  # noqa: F401 - yüklenebiliyor mu, sınanan bu
    except ImportError as hata:
        _cikti(f"{HATA_ONEKI}pywebview yok ({hata})")
        return KOD_PYWEBVIEW_YOK
    arka_uc = {"win32": "winforms", "darwin": "cocoa"}.get(sys.platform)
    if arka_uc is None:
        _cikti("pywebview yüklü; bu işletim sisteminde yerel pencere denetlenmiyor")
        return 0
    try:
        modul = importlib.import_module(f"webview.platforms.{arka_uc}")
    except Exception as hata:  # noqa: BLE001 - denetimin işi sebebi yazmak
        _cikti(f"{HATA_ONEKI}web görünümü yüklenemedi ({hata!r})")
        return KOD_WEB_GORUNUMU_KURULAMADI
    # Windows'ta "mshtml" WebView2'nin bu bilgisayarda olmadığı demektir:
    # paket sağlam, uygulama yedek pencereyle açılır.
    _cikti(f"pencere bileşeni tamam: {arka_uc}, motor {getattr(modul, 'renderer', '?')}")
    return 0


if __name__ == "__main__":  # geliştirme: Kontrol Paneli bu dosyayı betik olarak açar
    raise SystemExit(pencere_sureci_ana(sys.argv[1:]))

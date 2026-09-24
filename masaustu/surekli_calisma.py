"""Program, kullanıcı kapatana kadar açık kalır (Windows uygulaması).

Operatör, 24.09.2026: "uygulamayı bir kere açınca ben kapatana kadar otomatik
açılmayı ve bu tarz senaryoları düşünüp buna göre kodla". İlk aşamada sistem
fabrikanın Windows bilgisayarında, sunucusuz çalışır (docs/17 §16, S1):
Docker'ın ya da systemd'nin yaptığı "kapanırsa yeniden aç" işini burada
programın kendisi yapar. Dört parça:

* **Gözetmen.** Çift tıklanan (ya da Windows açılışında başlayan) süreç
  Kontrol Paneli'ni kendi alt süreci olarak açar ve bekler. Panel çökerse ya
  da bekçi takılan analizi 70 koduyla kapatırsa paneli yeniden açar; bir
  saatte en çok 3 kez. Sınır dolarsa paneli son bir kez, bu sefer bekçi
  yalnız uyaracak şekilde açar: pencere ortada kalır ve sorunu gösterir.
* **Windows açılışı.** Gözetmen başlarken programı kullanıcının "oturum
  açılınca başlat" listesine (HKCU\\...\\Run) yazar; kullanıcı paneli kapatınca
  panel onu siler. Elektrik kesilip bilgisayar yeniden açılınca ya da Windows
  güncellemeden sonra yeniden başlayınca program, oturum açılınca kendiliğinden
  başlar. Görev Yöneticisi'nin Başlangıç sekmesinde kapatılmışsa dokunulmaz,
  panel bunu söyler.
* **Uyku engeli.** Sistem çalışırken Windows uykuya geçmez (ekran kapanabilir).
* **Tek kopya.** Program zaten açıkken yeniden açılırsa ikinci kopya açılmaz;
  açık olan Kontrol Paneli öne gelir.

Kapatma ile çökme çıkış koduyla ayrılır: 0 = kullanıcı kapattı (onay
sorusundan sonra), 70 = bekçi yeniden başlatma istedi, 71 = sunucu beklenmedik
şekilde durdu, başka her kod = çökme. Windows kapanırken ya da oturum
kapanırken gözetmen paneli yeniden açmaz.

Yalnız Windows'ta çalışır: Mac uygulaması geliştirme ve deneme içindir, orada
bu modül hiçbir şey yapmaz. Windows çağrıları küçük sarmalayıcılardan geçer;
testler aynı adlı sahte nesneler verir.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")

# Programın paneli açan kopyası bu argümanla başlar; argümansız açılış gözetmendir.
PANEL_ARGUMANI = "--panel"
# Windows açılışındaki kayıt bu argümanı ekler: panel günlüğe "kendiliğinden
# başladı" yazar.
KENDILIGINDEN_ARGUMANI = "--kendiliginden"

# Panelin (ve içindeki sunucunun) ortamına yazılır: bekçi ancak süreci yeniden
# açan biri varken çıkar. Ad backend/app/kaynaklar.py GOZETMEN_DEGISKENI ile
# aynıdır (test denetler).
GOZETMEN_DEGISKENI = "DALSAN_GOZETMEN"
# Panelin bir önceki kapanışın sebebini günlüğe yazabilmesi için.
ONCEKI_KAPANIS_DEGISKENI = "DALSAN_ONCEKI_KAPANIS"
PYINSTALLER_SIFIRLA = "PYINSTALLER_RESET_ENVIRONMENT"

# Çıkış kodları. BEKCI_KODU backend/app/analiz/bekci.py YENIDEN_BASLATMA_KODU
# ile aynıdır (test denetler).
BEKCI_KODU = 70
SUNUCU_DURDU_KODU = 71

# Analiz her açılışta yine takılıyorsa gözetmen döngüye girmez.
YENIDEN_ACMA_SINIRI = 3
YENIDEN_ACMA_PENCERESI_SN = 3600
# Kapanan sürecin portu ve dosyaları bırakması için kısa bekleme.
YENIDEN_ACMA_BEKLEMESI_SN = 3.0

# Paneli yeniden açma sebepleri (ONCEKI_KAPANIS_DEGISKENI'nin değerleri).
KENDILIGINDEN = "kendiliginden"
BEKCI = "bekci"
SUNUCU_DURDU = "sunucu"
SINIR = "sinir"
COKME_ONEKI = "cokme:"

RUN_ANAHTARI = r"Software\Microsoft\Windows\CurrentVersion\Run"
# Görev Yöneticisi > Başlangıç sekmesinin açık/kapalı kaydı.
BASLANGIC_ONAYI_ANAHTARI = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
# Kayıt defterindeki adı, kullanıcının Başlangıç listesinde gördüğü addır.
# backend/app/kaynaklar.py UYGULAMA_ADI ile aynıdır (test denetler).
RUN_DEGERI = "NextGen Detector"
# Açık paneli öne getirmek için aranan pencere başlığı
# (masaustu/dalsan_launcher.py APP_TITLE, paketlenmiş programda).
PANEL_BASLIGI = "NextGen Detector - Kontrol Paneli"
# Oturum başına tek kopya ("Local\" = bu kullanıcı oturumu).
TEK_KOPYA_ADI = "Local\\NextGenDetector.Gozetmen"
ERROR_ALREADY_EXISTS = 183

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

GUNLUK_ADI = "gozetmen.log"
GUNLUK_SINIRI = 256 * 1024


# --------------------------------------------------------------- Windows


class _WindowsApi:
    """Gözetmenin kullandığı birkaç Windows çağrısı (ctypes)."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        k32.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
        k32.SetThreadExecutionState.restype = ctypes.c_uint32
        u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        u32.FindWindowW.restype = wintypes.HWND
        u32.IsIconic.argtypes = [wintypes.HWND]
        u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.SetForegroundWindow.argtypes = [wintypes.HWND]
        u32.GetSystemMetrics.argtypes = [ctypes.c_int]
        u32.MessageBoxW.argtypes = [
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            ctypes.c_uint,
        ]
        self._k32 = k32
        self._u32 = u32

    def muteks_olustur(self, ad: str) -> tuple[int | None, int]:
        tutamac = self._k32.CreateMutexW(None, False, ad)
        return tutamac, self._ctypes.get_last_error()

    def tutamac_kapat(self, tutamac: int) -> None:
        self._k32.CloseHandle(tutamac)

    def pencere_bul(self, baslik: str) -> int | None:
        return self._u32.FindWindowW(None, baslik)

    def one_getir(self, pencere: int) -> bool:
        # Simge durumundaysa eski boyutuna döner; büyütülmüşse öyle kalır.
        self._u32.ShowWindow(pencere, 9 if self._u32.IsIconic(pencere) else 5)
        return bool(self._u32.SetForegroundWindow(pencere))

    def calisma_durumu(self, bayrak: int) -> int:
        return self._k32.SetThreadExecutionState(bayrak)

    def oturum_kapaniyor(self) -> bool:
        return bool(self._u32.GetSystemMetrics(0x2000))  # SM_SHUTTINGDOWN

    def bilgi_kutusu(self, metin: str, baslik: str) -> None:
        # MB_ICONINFORMATION + MB_SETFOREGROUND
        self._u32.MessageBoxW(None, metin, baslik, 0x40 | 0x10000)


def _windows_api() -> _WindowsApi | None:
    if not IS_WINDOWS:
        return None
    try:
        return _WindowsApi()
    except (AttributeError, OSError):
        return None


def _winreg():
    if not IS_WINDOWS:
        return None
    import winreg

    return winreg


# --------------------------------------------------------------- tek kopya

# Muteksin tutamacı süreç boyunca açık kalmalı: kapanırsa ikinci kopya açılabilir.
_tek_kopya_tutamaci: int | None = None


def tek_kopya_mi(api=None) -> bool:
    """Bu, programın bu oturumdaki tek kopyası mı?

    Muteks kurulamazsa açılış engellenmez: ikinci bir panel, hiç açılmayan
    bir programdan iyidir.
    """
    global _tek_kopya_tutamaci
    if api is None:
        api = _windows_api()
        if api is None:
            return True
    tutamac, son_hata = api.muteks_olustur(TEK_KOPYA_ADI)
    if not tutamac:
        return True
    if son_hata == ERROR_ALREADY_EXISTS:
        api.tutamac_kapat(tutamac)
        return False
    _tek_kopya_tutamaci = tutamac
    return True


def acik_paneli_one_getir(api=None) -> bool:
    """Açık Kontrol Paneli'ni öne getirir; bulunamazsa kullanıcıya söyler."""
    if api is None:
        api = _windows_api()
        if api is None:
            return False
    pencere = api.pencere_bul(PANEL_BASLIGI)
    if pencere and api.one_getir(pencere):
        return True
    api.bilgi_kutusu(
        "NextGen Detector zaten çalışıyor.\n\n"
        "Kontrol Paneli görev çubuğunda açık; ikinci bir kopya açılmadı.",
        RUN_DEGERI,
    )
    return False


# --------------------------------------------------------------- uyku


def uyku_engeli(acik: bool, api=None) -> bool:
    """Sistem çalışırken Windows'un uykuya geçmesini engeller ya da bırakır.

    Engel, çağıran iş parçacığına bağlıdır ve o iş parçacığı bitince kalkar:
    Kontrol Paneli bunu pencerenin ana iş parçacığından çağırır. Ekranın
    kapanması engellenmez; uyarı sesi yine çalar. Kullanıcı bilgisayarı
    kendisi uyutursa (menüden, kapak) engel yoktur.
    """
    if api is None:
        api = _windows_api()
        if api is None:
            return False
    bayrak = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if acik else 0)
    return api.calisma_durumu(bayrak) != 0


# --------------------------------------------------------------- Windows açılışı


def acilis_komutu(program: str) -> str:
    return f'"{program}" {KENDILIGINDEN_ARGUMANI}'


def acilisa_ekle(program: str, kayit=None) -> str | None:
    """Programı oturum açılınca başlayacaklar listesine yazar.

    Her açılışta yeniden yazılır: program klasörü taşındıysa kayıt yeni yeri
    gösterir. Döner: hata metni ya da None.
    """
    if kayit is None:
        kayit = _winreg()
        if kayit is None:
            return None
    try:
        with kayit.CreateKeyEx(
            kayit.HKEY_CURRENT_USER, RUN_ANAHTARI, 0, kayit.KEY_SET_VALUE
        ) as anahtar:
            kayit.SetValueEx(anahtar, RUN_DEGERI, 0, kayit.REG_SZ, acilis_komutu(program))
    except OSError as hata:
        return str(hata)
    return None


def acilistan_cikar(kayit=None) -> str | None:
    """Kullanıcı programı kapatınca: oturum açılınca artık başlamaz."""
    if kayit is None:
        kayit = _winreg()
        if kayit is None:
            return None
    try:
        with kayit.OpenKey(
            kayit.HKEY_CURRENT_USER, RUN_ANAHTARI, 0, kayit.KEY_SET_VALUE
        ) as anahtar:
            kayit.DeleteValue(anahtar, RUN_DEGERI)
    except FileNotFoundError:
        return None  # zaten yok
    except OSError as hata:
        return str(hata)
    return None


def acilis_durumu(program: str, kayit=None) -> str:
    """Windows açılışında başlama durumu.

    "kayitli" (bu programı başlatır), "yok", "baska" (kayıt başka bir yerdeki
    programı gösteriyor), "kapatilmis" (Görev Yöneticisi > Başlangıç'ta
    kapatılmış) ya da "desteklenmiyor" (Windows değil).
    """
    if kayit is None:
        kayit = _winreg()
        if kayit is None:
            return "desteklenmiyor"
    try:
        with kayit.OpenKey(kayit.HKEY_CURRENT_USER, RUN_ANAHTARI) as anahtar:
            deger, _ = kayit.QueryValueEx(anahtar, RUN_DEGERI)
    except OSError:
        return "yok"
    if str(deger).casefold() != acilis_komutu(program).casefold():
        return "baska"
    try:
        with kayit.OpenKey(kayit.HKEY_CURRENT_USER, BASLANGIC_ONAYI_ANAHTARI) as anahtar:
            onay, _ = kayit.QueryValueEx(anahtar, RUN_DEGERI)
    except OSError:
        return "kayitli"  # onay kaydı yoksa Windows açık sayar
    # İlk baytın tek olması "kapalı" demektir (02 açık, 03 kapalı).
    if isinstance(onay, (bytes, bytearray)) and onay and onay[0] & 1:
        return "kapatilmis"
    return "kayitli"


# --------------------------------------------------------------- gözetmen


def gozetmen_gerekli_mi(argumanlar: list[str], paketlenmis: bool) -> bool:
    """Bu süreç gözetmen mi olmalı? Yalnız paketlenmiş Windows programında ve
    panel argümanı olmadan (kullanıcının açtığı kopya)."""
    return paketlenmis and IS_WINDOWS and PANEL_ARGUMANI not in argumanlar


def yeniden_acma_karari(kod: int, gecmis: list[float], simdi: float) -> str:
    """Panel kapanınca ne yapılır: "bitir", "ac" ya da "sinir".

    `gecmis` son yeniden açmaların monotonic zamanlarıdır, yerinde güncellenir.
    """
    if kod == 0:
        return "bitir"
    gecmis[:] = [t for t in gecmis if simdi - t < YENIDEN_ACMA_PENCERESI_SN]
    if len(gecmis) >= YENIDEN_ACMA_SINIRI:
        return "sinir"
    gecmis.append(simdi)
    return "ac"


def kapanis_sebebi(kod: int) -> str:
    if kod == BEKCI_KODU:
        return BEKCI
    if kod == SUNUCU_DURDU_KODU:
        return SUNUCU_DURDU
    return f"{COKME_ONEKI}{kod}"


def acilis_notu(onceki: str) -> list[str]:
    """Panelin açılışta günlüğe yazacağı satırlar (önceki kapanışın sebebi)."""
    if onceki == KENDILIGINDEN:
        return ["Program Windows açılışında kendiliğinden başladı."]
    if onceki == BEKCI:
        return [
            "[!] Analiz takıldığı için program kendini kapatıp yeniden açtı (bekçi).",
            '    Olaylar sayfasında "Analiz takıldı" kaydı var.',
        ]
    if onceki == SUNUCU_DURDU:
        return ["[!] Sistem beklenmedik şekilde durmuştu; program kendiliğinden yeniden açıldı."]
    if onceki == SINIR:
        return [
            f"[HATA] Program son bir saatte {YENIDEN_ACMA_SINIRI} kez yeniden açılmak zorunda "
            "kaldı. Bu kez takılırsa",
            "    kendini kapatmayacak, yalnız uyaracak. Günlükteki hata satırlarını destek",
            "    ekibine iletin; bilgisayarı yeniden başlatmak sayacı sıfırlar.",
        ]
    if onceki.startswith(COKME_ONEKI):
        kod = onceki[len(COKME_ONEKI) :]
        return [
            f"[!] Program beklenmedik şekilde kapandı (çıkış kodu {kod}) ve kendiliğinden "
            "yeniden açıldı."
        ]
    return []


def windows_oturumu_kapaniyor(api=None) -> bool:
    if api is None:
        api = _windows_api()
        if api is None:
            return False
    return api.oturum_kapaniyor()


def _gunluk_klasoru() -> Path:
    try:
        from app import kaynaklar

        return kaynaklar.veri_konumu().kok / "veri" / "loglar"
    except (ImportError, OSError, RuntimeError, ValueError):
        temel = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(temel) / RUN_DEGERI / "veri" / "loglar"


def gunluk_yazici(klasor: Path | None = None) -> Callable[[str], None]:
    """Gözetmenin kendi günlüğü (veri/loglar/gozetmen.log).

    Gözetmen ekrana hiç yazmaz: paketlenmiş programda ekran akışı
    son-calistirma.log'dur ve onu panel her açılışta baştan yazar.
    """

    def yaz(mesaj: str) -> None:
        try:
            hedef = klasor if klasor is not None else _gunluk_klasoru()
            hedef.mkdir(parents=True, exist_ok=True)
            dosya = hedef / GUNLUK_ADI
            if dosya.exists() and dosya.stat().st_size > GUNLUK_SINIRI:
                dosya.replace(hedef / (GUNLUK_ADI + ".1"))
            with open(dosya, "a", encoding="utf-8") as akis:
                akis.write(f"{datetime.now().isoformat(timespec='seconds')} {mesaj}\n")
        except OSError:
            # Günlük yazılamıyor diye gözetmen durmamalı; iş paneli açık tutmak.
            return

    return yaz


def gozetmeni_calistir(
    program: str,
    argumanlar: list[str],
    *,
    baslat: Callable[..., subprocess.Popen] = subprocess.Popen,
    saat: Callable[[], float] = time.monotonic,
    uyu: Callable[[float], None] = time.sleep,
    oturum_kapaniyor: Callable[[], bool] | None = None,
    yaz: Callable[[str], None] | None = None,
    kayit=None,
) -> int:
    """Kontrol Paneli'ni açar, kapanırsa sebebine göre yeniden açar."""
    if oturum_kapaniyor is None:
        oturum_kapaniyor = windows_oturumu_kapaniyor
    if yaz is None:
        yaz = gunluk_yazici()
    hata = acilisa_ekle(program, kayit)
    if hata:
        yaz(f"Windows açılışına eklenemedi: {hata}")
    gecmis: list[float] = []
    onceki = KENDILIGINDEN if KENDILIGINDEN_ARGUMANI in argumanlar else ""
    gozetimli = True
    yaz(f"Gözetmen başladı ({onceki or 'kullanıcı açtı'}).")
    while True:
        ortam = dict(os.environ)
        ortam[GOZETMEN_DEGISKENI] = "1" if gozetimli else "0"
        ortam[ONCEKI_KAPANIS_DEGISKENI] = onceki
        # PyInstaller 6.9'dan beri programın kendi kopyasını açması "aynı
        # uygulamanın yardımcı alt süreci" sayılır; panel, kullanıcının açtığı
        # bağımsız bir program olarak kalkmalı (PyInstaller belgesi, "Common
        # Issues and Pitfalls": uygulamayı sys.executable ile yeniden açmak).
        ortam[PYINSTALLER_SIFIRLA] = "1"
        try:
            surec = baslat([program, PANEL_ARGUMANI], env=ortam)
        except OSError as hata:
            yaz(f"Kontrol Paneli açılamadı: {hata}")
            return 1
        kod = surec.wait()
        if kod == 0:
            yaz("Kontrol Paneli kapatıldı; gözetmen de kapanıyor.")
            return 0
        if not gozetimli:
            yaz(f"Kontrol Paneli {kod} koduyla kapandı; sınır dolduğu için yeniden açılmadı.")
            return kod
        if oturum_kapaniyor():
            yaz(f"Kontrol Paneli {kod} koduyla kapandı; Windows kapanıyor, yeniden açılmadı.")
            return 0
        if yeniden_acma_karari(kod, gecmis, saat()) == "sinir":
            gozetimli = False
            onceki = SINIR
            yaz(
                f"Kontrol Paneli {kod} koduyla kapandı; son bir saatte {YENIDEN_ACMA_SINIRI} kez "
                "yeniden açıldı. Son kez açılıyor; bekçi bu kez yalnız uyaracak."
            )
        else:
            onceki = kapanis_sebebi(kod)
            yaz(f"Kontrol Paneli {kod} koduyla kapandı ({onceki}); yeniden açılıyor.")
        uyu(YENIDEN_ACMA_BEKLEMESI_SN)
        if oturum_kapaniyor():
            yaz("Windows kapanıyor; panel yeniden açılmadı.")
            return 0

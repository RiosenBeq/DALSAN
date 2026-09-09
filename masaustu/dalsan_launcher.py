#!/usr/bin/env python3
"""
DALSAN ISG - Masaustu Kontrol Paneli
=====================================
Bu program, sistemi baslatip durdurmak icin kullanilir.
Terminal / komut satiri bilmeye gerek yoktur.

Mac'te   : Baslat-Mac.command  dosyasina cift tikla
Windows'ta: Baslat-Windows.bat dosyasina cift tikla
"""

import json
import logging
import os
import queue
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# ----------------------------------------------------------------------------
# Ayarlar
# ----------------------------------------------------------------------------
PORT = 8080
URL = f"http://127.0.0.1:{PORT}"

# Sunucunun DINLEYECEGI adres. .env'deki SUNUCU_ADRESI belirler:
#   127.0.0.1 (varsayilan) = yalniz bu bilgisayar
#   0.0.0.0                = agdaki diger cihazlar da erisebilir
# Backend, sifresiz bir sistemin aga acilmasini ACILISTA reddeder
# (app/ayarlar.py); panel o hatayi gunluge olduğu gibi yazar.
DINLEME_ADRESI_VARSAYILAN = "127.0.0.1"

IS_WINDOWS = os.name == "nt"

# Program, cift tiklanan bir uygulama (.app / .exe) olarak mi calisiyor?
# PyInstaller paketlenmis programda sys.frozen'i kurar; normal Python
# calistirmasinda bu ozellik YOKTUR.
#
# Paketlenmis programda IKI sey degisir:
#   1. Kurulum adimi YOKTUR — Python ortami ve paketler uygulamanin icinde
#      gelir; "Ilk Kurulumu Yap" dugmesi gosterilmez.
#   2. Sunucu ALT SUREC OLARAK BASLATILAMAZ. Paketlenmis programda
#      sys.executable artik python degil, UYGULAMANIN KENDISIDIR; onu
#      yeniden calistirmak ikinci bir Kontrol Paneli acar ve sonsuz dongu
#      olusur. Bu yuzden sunucu ayni surec icinde, bir is parcaciginda
#      calistirilir (bkz. _ic_surecte_baslat).
PAKETLENMIS = bool(getattr(sys, "frozen", False))

APP_TITLE = (
    "NextGen Detector — Kontrol Paneli" if PAKETLENMIS else "DALSAN İSG — Kontrol Paneli"
)


def _yazilabilir_kok() -> Path:
    """Veritabani, gunluk ve ayar dosyasinin duracagi klasor.

    Gelistirme kurulumunda depo kokudur (bugunku davranis). Paketlenmis
    programda uygulama paketinin ICI SALT OKUNURDUR; yazilabilir klasoru
    backend'le AYNI kural belirlemeli, yoksa panel ile sunucu iki ayri
    klasore bakar. Bu yuzden karar tek yerden, app/kaynaklar.py'den alinir.
    """
    if PAKETLENMIS:
        from app import kaynaklar

        return kaynaklar.veri_konumu().kok
    return Path(__file__).resolve().parent.parent


ROOT = _yazilabilir_kok()       # gelistirmede depo koku, pakette veri koku
BACKEND = ROOT / "backend"
VENV = ROOT / ".venv"
REQUIREMENTS = BACKEND / "requirements.txt"
MAIN_MODULE = BACKEND / "app" / "main.py"
ENV_FILE = ROOT / ".env"
# Paketlenmis programda ornek ayar dosyasi paketin icindedir ve .env'i
# app/ayarlar.py bir kez oradan uretir; buradaki kopyalama o modda calismaz.
ENV_EXAMPLE = ROOT / ".env.example"
DATA_DIR = ROOT / "veri"
LOG_FILE = DATA_DIR / "loglar" / "sistem.log"
VERITABANI = DATA_DIR / "dalsan.db"
YEDEK_DIZINI = DATA_DIR / "yedekler"

# Renkler (sade, goz yormayan)
BG = "#f5f5f4"
FG = "#1c1917"
MUTED = "#78716c"
OK = "#15803d"
WARN = "#b45309"
ERR = "#b91c1c"
ACCENT = "#1d4ed8"


# ----------------------------------------------------------------------------
# Yardimci fonksiyonlar (arayuzden bagimsiz)
# ----------------------------------------------------------------------------
def dinleme_adresi() -> str:
    """.env dosyasindaki SUNUCU_ADRESI (yoksa 127.0.0.1).

    .env'i tam ayrıştırmaya gerek yok: tek satir aranir. Boylece panel,
    backend'in ayar yukleyicisini import etmek zorunda kalmaz (paketlenmemis
    kurulumda venv henuz hazir olmayabilir).
    """
    try:
        for satir in ENV_FILE.read_text(encoding="utf-8").splitlines():
            temiz = satir.strip()
            if temiz.startswith("SUNUCU_ADRESI") and "=" in temiz:
                deger = temiz.split("=", 1)[1].split("#")[0].strip()
                if deger:
                    return deger
    except (OSError, UnicodeDecodeError):
        pass
    return DINLEME_ADRESI_VARSAYILAN


def venv_python() -> Path:
    """Sanal ortamdaki Python'un yolu."""
    return VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def python_ok() -> bool:
    # onnxruntime 3.11+ ister; 3.10'a izin vermek pip'i cok eski bir surume
    # dusuruyor ve tespit sessizce bozuluyordu.
    return sys.version_info >= (3, 11)


def venv_hazir() -> bool:
    """Ortam gercekten CALISIYOR mu? Yalnizca dosya varligina bakmak yetmez:
    Python surumu kaldirilinca .venv icindeki python calismaz hale gelir ama
    dosya durur; panel o zaman kurulumu atlayip cokmeye devam ederdi."""
    yol = venv_python()
    if not yol.exists():
        return False
    try:
        return subprocess.run(
            [str(yol), "-c", "pass"], capture_output=True, timeout=30
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def paketler_hazir() -> bool:
    """FastAPI kurulu mu diye bakar — kurulumun bittiginin isareti."""
    if PAKETLENMIS:
        # Paketler uygulamanin icinde gelir; kurulacak bir sey yoktur.
        return True
    if not venv_hazir():
        return False
    try:
        r = subprocess.run(
            [str(venv_python()), "-c", "import fastapi"],
            capture_output=True, timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


def kod_hazir() -> bool:
    """Sistemin kodu yazilmis mi? (Claude Code ile uretilecek)"""
    if PAKETLENMIS:
        # Kod uygulamanin icindedir; diskte aranacak bir dosya yoktur.
        return True
    return MAIN_MODULE.exists()


# Sunucunun uc hali. "Port dolu" ile "bizim sunucumuz calisiyor" AYNI SEY
# DEGILDIR; ayrimi yapmayan panel kullaniciyi kilitliyordu (bkz. asagisi).
DURDU = "durdu"
CALISIYOR = "calisiyor"
BASKASINDA = "baskasinda"


def sunucu_ayakta() -> bool:
    """Port dinleniyor mu? (ucuz kontrol — kim dinliyor, onu SOYLEMEZ)"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def bizim_sunucumuz_mu() -> bool:
    """Portu dinleyen program BIZIM sunucumuz mu?

    /saglik ucu yalnizca bu sistemde vardir ve {"durum": "calisiyor"} doner.
    """
    try:
        with urllib.request.urlopen(f"{URL}/saglik", timeout=2) as yanit:
            return json.loads(yanit.read(4096)).get("durum") == "calisiyor"
    except (urllib.error.URLError, OSError, ValueError):
        # Baglanti yok, HTTP hatasi, JSON degil, beklenen alan yok — hicbiri
        # bizim sunucumuz demek degildir.
        return False


def sunucu_durumu() -> str:
    """durdu | calisiyor | baskasinda

    NEDEN GEREKLI — 8080 cok yaygin bir porttur (XAMPP/MAMP, Tomcat, Jenkins,
    baska bir gelistirme sunucusu). Yalnizca "port dolu mu" diye bakan panel,
    baskasinin sunucusunu BIZIM sunucumuz sanir ve kullanici su kilide girer:
    durum satiri "CALISIYOR" der, "Sistemi Baslat" dugmesi kapali kalir,
    "Durdur" ise "calisan sistem bulunamadi" der. Sebep hicbir yerde yazmaz.
    """
    if not sunucu_ayakta():
        return DURDU
    return CALISIYOR if bizim_sunucumuz_mu() else BASKASINDA


def port_dolu_mesaji() -> list[str]:
    """Portu baskasi tutuyorken gunluge dusen aciklama (tek metin kaynagi)."""
    return [
        f"[HATA] {PORT} portunu bu bilgisayarda BAŞKA bir program kullanıyor;",
        "       sistem bu yüzden açılamıyor.",
        "       Bu portu genelde şu programlar tutar: XAMPP / MAMP, Tomcat,",
        "       Jenkins, ya da açık kalmış başka bir geliştirme sunucusu.",
        "       Çözüm: o programı kapatın ve 'Sistemi Başlat'a yeniden basın.",
    ]


PID_DOSYASI = DATA_DIR / "sunucu.pid"


def _pid_yaz(pid: int) -> None:
    """Calisan sunucunun numarasini yaz: panel cokerse sahiplenebilelim."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PID_DOSYASI.write_text(str(pid), encoding="utf-8")
    except OSError:
        pass


def _pid_sil() -> None:
    try:
        PID_DOSYASI.unlink(missing_ok=True)
    except OSError:
        pass


def _sahipsiz_sureci_durdur(log) -> bool:
    """Onceki panelden kalan sunucuyu durdurur. Durdurulduysa True."""
    try:
        pid = int(PID_DOSYASI.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    log(f"\nOnceki calistirmadan kalan sunucu bulundu (numara {pid}), durduruluyor…")
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(16):
                time.sleep(0.5)
                if not sunucu_ayakta():
                    break
            else:
                os.kill(pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError) as hata:
        log(f"[!] Durdurulamadi: {hata}")
        return False
    _pid_sil()
    log("✓ Durduruldu")
    return True


# ----------------------------------------------------------------------------
# Yedekten geri yukleme
#
# NEDEN WEB ARAYUZUNDE DEGIL, BURADA: sistem calisirken veritabani dosyasi
# ACIKTIR (analiz is parcacigi ona baglidir). Acik bir SQLite dosyasinin
# altindan dosyayi degistirmek veri kaybi demektir. Geri yukleme, ancak sistem
# DURDURULMUSKEN yapilabilir; onu da yalnizca Kontrol Paneli bilir.
#
# K7 (docs/01): "Yedek alma ve geri yukleme dokumante edilmis ve EN AZ BIR KEZ
# PROVA EDILMIS." Prova edilmemis bir yedek, yedek degildir.
# ----------------------------------------------------------------------------

# SQLite WAL kipinde iki yan dosya tutar. Ana dosya degisip bunlar KALIRSA
# SQLite eski WAL'i yeni veritabaninin ustune uygular ve dosya bozulur.
# Geri yuklemede ikisi de silinmelidir.
_WAL_UZANTILARI = ("-wal", "-shm")


def yedekleri_listele(yedek_dizini=None):
    """Yedek dosyalarini YENIDEN ESKIYE dogru sirali dondurur."""
    dizin = Path(yedek_dizini) if yedek_dizini else YEDEK_DIZINI
    if not dizin.is_dir():
        return []
    return sorted(dizin.glob("*.db"), key=lambda y: y.stat().st_mtime, reverse=True)


def yedekten_geri_yukle(yedek, veritabani=None):
    """Yedegi veritabaninin uzerine yazar. Doner: guvenlik kopyasinin yolu.

    Once mevcut veritabaninin GUVENLIK KOPYASI alinir: geri yukleme yanlis
    dosyayla yapilirsa kullanicinin donecek bir yeri olmalidir. Bu kopya
    olmadan "geri yukle" tek yonlu ve geri alinamaz bir dugme olurdu.
    """
    yedek = Path(yedek)
    hedef = Path(veritabani) if veritabani else VERITABANI
    if not yedek.is_file():
        raise FileNotFoundError(f"Yedek dosyasi bulunamadi: {yedek}")
    if yedek.resolve() == hedef.resolve():
        raise ValueError("Yedek dosyasi veritabaninin kendisi; geri yukleme yapilmadi.")

    hedef.parent.mkdir(parents=True, exist_ok=True)
    guvenlik = None
    if hedef.is_file():
        damga = time.strftime("%Y-%m-%d_%H-%M-%S")
        guvenlik = hedef.parent / "yedekler" / f"geri-yukleme-oncesi-{damga}.db"
        guvenlik.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(hedef, guvenlik)

    shutil.copy2(yedek, hedef)
    # Bayat WAL/SHM dosyalari yeni veritabanini bozar (bkz. _WAL_UZANTILARI).
    for uzanti in _WAL_UZANTILARI:
        yan = hedef.with_name(hedef.name + uzanti)
        if yan.exists():
            yan.unlink()
    return guvenlik


def klasorleri_hazirla() -> None:
    for p in [DATA_DIR, DATA_DIR / "loglar", DATA_DIR / "goruntuler", DATA_DIR / "yedekler"]:
        p.mkdir(parents=True, exist_ok=True)
    if ENV_EXAMPLE.exists() and not ENV_FILE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_FILE)


# ----------------------------------------------------------------------------
# Paketlenmis programda sunucu: AYNI SUREC, ayri is parcacigi
# ----------------------------------------------------------------------------
class _PanelGunlukAkisi(logging.Handler):
    """Sunucunun gunluk satirlarini Kontrol Paneli penceresine akitir.

    Gelistirme kurulumunda bu is alt surecin stdout'u okunarak yapilir.
    Paketlenmis programda stdout DIYE BIR SEY YOKTUR (.app Finder'dan acilir,
    ciktisi hicbir yere gitmez); satirlar bu yuzden dogrudan log sisteminden
    alinir.
    """

    def __init__(self, yaz) -> None:
        super().__init__()
        self._yaz = yaz
        self.panel_akisi = True

    def emit(self, kayit: logging.LogRecord) -> None:
        try:
            self._yaz(self.format(kayit))
        except (TypeError, ValueError, OSError):
            self.handleError(kayit)


def _gunlugu_panele_bagla(log) -> None:
    """Log sistemine panel akisini ekler (bir kez).

    Bicimlendirici, sunucunun EKRAN akisindan aynen odunc alinir: teknik
    ayrinti (dosya yollari, yigin izi) yine yalnizca gunluk DOSYASINA yazilir,
    panele degil (bkz. backend/app/loglama.py).
    """
    kok = logging.getLogger("dalsan")
    if any(getattr(h, "panel_akisi", False) for h in kok.handlers):
        return
    ekran_bicimi = next(
        (
            h.formatter
            for h in kok.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ),
        None,
    )
    akis = _PanelGunlukAkisi(log)
    if ekran_bicimi is not None:
        akis.setFormatter(ekran_bicimi)
    kok.addHandler(akis)


def _ic_surecte_baslat(log, gunluk_yaz=None):
    """Sunucuyu ayni surec icinde baslatir; uvicorn.Server nesnesini dondurur.

    Hata durumunda None doner ve sebebi Turkce olarak gunluge yazar.

    `gunluk_yaz`: sunucunun kendi gunluk satirlarinin gidecegi yer. Panelin
    `log`'undan AYRIDIR, cunku o satirlar zaten kendi akislarina yaziliyor;
    ikinci kez terminale basilmalari cikti ikilerdi.
    """
    import uvicorn

    from app.ayarlar import ayarlari_yukle
    from app.hatalar import AyarHatasi

    # On kontrol: app.main ayni dogrulamayi yapar ama hatasini stderr'e
    # yazar — .app olarak acildiginda stderr hicbir yere gitmez ve kullanici
    # sebebi HIC goremezdi.
    try:
        ayarlari_yukle()
    except AyarHatasi as hata:
        log(f"[AYAR HATASI] {hata.kullanici_mesaji}")
        return None

    # Uygulama HER baslatista yeniden kurulur (modul duzeyindeki hazir nesne
    # kullanilmaz): boylece Durdur → Sistemi Baslat turunda ayar dosyasi
    # yeniden okunur ve Ayarlar sayfasindaki degisiklik gercekten gecerli olur.
    from app.main import uygulamayi_kur

    fastapi_uygulamasi = uygulamayi_kur()

    # Log sistemi yukaridaki cagrida yeniden kuruldu; panel akisi ondan SONRA
    # baglanmali, yoksa akis temizlenir ve pencereye tek satir dusmez.
    _gunlugu_panele_bagla(gunluk_yaz if gunluk_yaz is not None else log)

    # log_config=None: uvicorn kendi log yapilandirmasini kurmasin, sistemin
    # kendi bicimi (JSON satirlari) bozulmasin.
    sunucu = uvicorn.Server(
        uvicorn.Config(
            fastapi_uygulamasi, host=dinleme_adresi(), port=PORT, log_config=None
        )
    )

    def calistir():
        try:
            sunucu.run()
        except SystemExit:
            # uvicorn adrese baglanamayinca sys.exit(1) cagirir; is
            # parcaciginda bu SESSIZCE biter ve kullanici sebebini goremez.
            log("[HATA] Sistem başlatılamadı: 8080 numaralı bağlantı noktası dolu olabilir.")
        except OSError as hata:
            log(f"[HATA] Sistem başlatılamadı: {hata}")

    threading.Thread(target=calistir, daemon=True, name="sunucu").start()
    return sunucu


# ----------------------------------------------------------------------------
# Arayuz
# ----------------------------------------------------------------------------
def arayuzu_baslat():
    import tkinter as tk
    from tkinter import filedialog, font as tkfont, messagebox, scrolledtext

    kok = tk.Tk()
    kok.title(APP_TITLE)
    kok.configure(bg=BG)
    kok.geometry("760x580")
    kok.minsize(680, 520)

    baslik_font = tkfont.Font(family="Helvetica", size=17, weight="bold")
    normal_font = tkfont.Font(family="Helvetica", size=12)
    kucuk_font = tkfont.Font(family="Helvetica", size=11)
    log_font = tkfont.Font(family="Menlo" if not IS_WINDOWS else "Consolas", size=10)

    durum = {"surec": None, "sunucu": None, "calisiyor": False, "mesgul": False}
    log_kuyrugu: "queue.Queue[str]" = queue.Queue()

    # paketler_hazir() bir alt surec calistirir (yavas). Ana pencere donmasin
    # diye kontrol ARKA PLANDA yapilir, sonucu burada saklanir.
    paket_durumu = {"hazir": None}  # None = henuz kontrol edilmedi

    def paketleri_arkada_kontrol_et():
        def kontrol():
            paket_durumu["hazir"] = paketler_hazir()
        threading.Thread(target=kontrol, daemon=True).start()

    paketleri_arkada_kontrol_et()

    # sunucu_durumu() /saglik ucuna HTTP istegi atar; portu tutan program
    # yanit vermiyorsa bu iki saniye surebilir. Ana pencere donmasin diye
    # kontrol ARKA PLANDA yapilir ve sonucu burada saklanir.
    sunucu_bilgisi = {"durum": DURDU, "kontrol_ediliyor": False}

    def sunucuyu_arkada_kontrol_et():
        if sunucu_bilgisi["kontrol_ediliyor"]:
            return                      # onceki kontrol daha bitmedi
        sunucu_bilgisi["kontrol_ediliyor"] = True

        def kontrol():
            try:
                sunucu_bilgisi["durum"] = sunucu_durumu()
            finally:
                sunucu_bilgisi["kontrol_ediliyor"] = False

        threading.Thread(target=kontrol, daemon=True).start()

    sunucuyu_arkada_kontrol_et()

    # ---- ust baslik ----
    ust = tk.Frame(kok, bg=BG)
    ust.pack(fill="x", padx=24, pady=(20, 8))
    tk.Label(ust, text="DALSAN İSG Görüntü Analiz Sistemi",
             font=baslik_font, bg=BG, fg=FG).pack(anchor="w")
    tk.Label(ust, text="Bu pencereyi kapatırsanız sistem durur.",
             font=kucuk_font, bg=BG, fg=MUTED).pack(anchor="w", pady=(2, 0))

    # ---- durum satirlari ----
    durum_cerceve = tk.Frame(kok, bg="white", relief="flat", bd=0,
                             highlightbackground="#e7e5e4", highlightthickness=1)
    durum_cerceve.pack(fill="x", padx=24, pady=10)

    # Paketlenmis programda kurulum satirlari GOSTERILMEZ: Python, paketler ve
    # kod uygulamanin icinde gelir — kullanicinin bakacagi tek satir sistemin
    # calisip calismadigidir.
    satirlar = (
        [("sunucu", "Sistem durumu")]
        if PAKETLENMIS
        else [
            ("python", "Python"),
            ("paket", "Gerekli paketler"),
            ("kod", "Sistem kodu"),
            ("sunucu", "Sistem durumu"),
        ]
    )
    durum_etiketleri = {}
    for anahtar, metin in satirlar:
        satir = tk.Frame(durum_cerceve, bg="white")
        satir.pack(fill="x", padx=16, pady=6)
        tk.Label(satir, text=metin, font=normal_font, bg="white", fg=MUTED,
                 width=18, anchor="w").pack(side="left")
        deger = tk.Label(satir, text="kontrol ediliyor…", font=normal_font,
                         bg="white", fg=MUTED, anchor="w")
        deger.pack(side="left", fill="x", expand=True)
        durum_etiketleri[anahtar] = deger

    # ---- butonlar ----
    btn_cerceve = tk.Frame(kok, bg=BG)
    btn_cerceve.pack(fill="x", padx=24, pady=(4, 10))

    def buton(metin, komut, ana=False):
        b = tk.Button(btn_cerceve, text=metin, command=komut, font=normal_font,
                      relief="flat", bd=0, padx=18, pady=9, cursor="hand2",
                      bg=ACCENT if ana else "white",
                      fg="white" if ana else FG,
                      activebackground="#1e40af" if ana else "#f5f5f4",
                      activeforeground="white" if ana else FG,
                      highlightbackground="#e7e5e4", highlightthickness=0 if ana else 1)
        b.pack(side="left", padx=(0, 10))
        return b

    # Paketlenmis programda kurulacak bir sey yoktur: dugme hic konmaz.
    kurulum_btn = None
    if not PAKETLENMIS:
        kurulum_btn = buton("İlk Kurulumu Yap", lambda: is_baslat(kurulumu_yap))
    baslat_btn = buton("Sistemi Başlat", lambda: is_baslat(sistemi_baslat), ana=True)
    durdur_btn = buton("Durdur", lambda: sistemi_durdur())
    ekran_btn = buton("İzleme Ekranını Aç", lambda: webbrowser.open(URL))
    geri_yukle_btn = buton("Yedekten Geri Yükle", lambda: yedekten_don())
    kilitlenecek = [b for b in (kurulum_btn, baslat_btn, durdur_btn, geri_yukle_btn)
                    if b is not None]

    # ---- log alani ----
    tk.Label(kok, text="Sistem günlüğü", font=kucuk_font, bg=BG, fg=MUTED)\
        .pack(anchor="w", padx=24, pady=(6, 2))
    log_kutusu = scrolledtext.ScrolledText(
        kok, height=14, font=log_font, bg="#1c1917", fg="#d6d3d1",
        insertbackground="#d6d3d1", relief="flat", bd=0, wrap="word")
    log_kutusu.pack(fill="both", expand=True, padx=24, pady=(0, 20))
    log_kutusu.configure(state="disabled")

    # ---- log yazma ----
    def log(mesaj: str):
        log_kuyrugu.put(mesaj)
        # Ayni satir terminale de dusurulur. Uygulama hic acilmiyorsa
        # (pencere gorunmuyorsa) tek teshis yolu budur: kullanici .app'i
        # Terminal'den calistirip sebebi okuyabilir. Finder'dan acildiginda
        # bu cikti hicbir yere gitmez, zarari yoktur.
        try:
            print(mesaj, file=sys.stderr, flush=True)
        except (OSError, ValueError, UnicodeEncodeError):
            # Cikti akisi kapali/yonlendirilmis olabilir. Yapilacak bir sey
            # yok: satir zaten pencerede duruyor, gunluk sistemi kendi
            # dosyasina yaziyor.
            pass

    def kuyrugu_bosalt():
        yazildi = False
        while True:
            try:
                satir = log_kuyrugu.get_nowait()
            except queue.Empty:
                break
            log_kutusu.configure(state="normal")
            log_kutusu.insert("end", satir.rstrip() + "\n")
            log_kutusu.configure(state="disabled")
            yazildi = True
        if yazildi:
            log_kutusu.see("end")
        kok.after(200, kuyrugu_bosalt)

    # ---- durum yenileme ----
    def durumu_yenile():
        if durum["mesgul"]:
            kok.after(1500, durumu_yenile)
            return

        def ayarla(anahtar, metin, renk):
            etiket = durum_etiketleri.get(anahtar)   # pakette kurulum satirlari yok
            if etiket is not None:
                etiket.configure(text=metin, fg=renk)

        if python_ok():
            ayarla("python", f"Hazır (sürüm {sys.version_info.major}.{sys.version_info.minor})", OK)
        else:
            ayarla("python", "Python 3.11 veya üstü gerekiyor", ERR)

        paket_hazir = paket_durumu["hazir"]
        if paket_hazir is None:
            ayarla("paket", "kontrol ediliyor…", MUTED)
        elif paket_hazir:
            ayarla("paket", "Kurulu", OK)
        elif venv_hazir():
            ayarla("paket", "Eksik — 'İlk Kurulumu Yap'a basın", WARN)
        else:
            ayarla("paket", "Kurulmamış — 'İlk Kurulumu Yap'a basın", WARN)

        if kod_hazir():
            ayarla("kod", "Hazır", OK)
        else:
            ayarla("kod", "Henüz yazılmadı (Claude Code ile üretilecek)", WARN)

        sunucuyu_arkada_kontrol_et()
        sunucu_hali = sunucu_bilgisi["durum"]
        ayakta = sunucu_hali == CALISIYOR
        durum["calisiyor"] = ayakta
        if ayakta:
            ayarla("sunucu", f"ÇALIŞIYOR — {URL}", OK)
        elif sunucu_hali == BASKASINDA:
            # "Durdu" demek yanlis olurdu: kullanici Baslat'a basacak ve
            # sebebini anlamadan basarisiz olacakti. Sebep burada yazar.
            ayarla("sunucu", f"{PORT} portunu başka bir program tutuyor", ERR)
        else:
            ayarla("sunucu", "Durdu", MUTED)

        baslat_btn.configure(state="normal" if (paket_hazir and kod_hazir() and not ayakta) else "disabled")
        durdur_btn.configure(state="normal" if ayakta else "disabled")
        ekran_btn.configure(state="normal" if ayakta else "disabled")
        if kurulum_btn is not None:
            kurulum_btn.configure(state="disabled" if durum["mesgul"] else "normal")

        kok.after(1500, durumu_yenile)

    # ---- uzun islemleri ayri is parcaciginda calistir ----
    def is_baslat(fonksiyon):
        if durum["mesgul"]:
            return
        durum["mesgul"] = True
        for b in kilitlenecek:
            b.configure(state="disabled")

        def sar():
            try:
                fonksiyon()
            except Exception as hata:
                log(f"[HATA] {hata}")
            finally:
                durum["mesgul"] = False

        threading.Thread(target=sar, daemon=True).start()

    # ---- komut calistirip ciktisini loga akitan yardimci ----
    def komut_calistir(komut, aciklama):
        log(f"\n▶ {aciklama}")
        # encoding ZORUNLU: alt surec UTF-8 yazar, Windows'ta varsayilan cozucu
        # cp1254'tur. Buyuk S ve G harfleri (U+015E / U+011E) cp1254'te tanimsiz
        # 0x9E baytina denk gelir; "SISTEM BASLATILIYOR" gibi bir satir
        # UnicodeDecodeError verip gunluk penceresini SESSIZCE dondururdu.
        surec = subprocess.Popen(
            komut, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )

        # Uzun indirmelerde ekran sessiz kalmasin: 20 sn'de bir yasam isareti.
        bitti = threading.Event()

        def yasam_isareti():
            gecen = 0
            while not bitti.wait(20):
                gecen += 20
                log(f"   … sürüyor ({gecen} sn geçti) — indirme devam ediyor, pencereyi kapatmayın.")

        threading.Thread(target=yasam_isareti, daemon=True).start()
        try:
            for satir in surec.stdout:
                log("   " + satir.rstrip())
            surec.wait()
        finally:
            bitti.set()
        if surec.returncode != 0:
            raise RuntimeError(f"{aciklama} başarısız oldu (kod {surec.returncode})")
        log(f"✓ {aciklama} tamam")

    # ---- ilk kurulum ----
    def kurulumu_yap():
        if not python_ok():
            log("[HATA] Bu bilgisayardaki Python sürümü çok eski (3.11 veya üstü gerekiyor).")
            log("       https://www.python.org/downloads/ adresinden Python 3.12 kurun,")
            log("       sonra bu paneli kapatıp yeniden açın.")
            return
        log("=" * 60)
        log("İLK KURULUM BAŞLIYOR — internet hızına göre 2-10 dakika sürer.")
        log("Aşağıya indirme satırları düşecek; ekran arada sessiz kalsa da")
        log("kurulum sürüyor demektir. PENCEREYİ KAPATMAYIN.")
        klasorleri_hazirla()
        log("✓ Klasörler hazırlandı")

        if not venv_hazir():
            komut_calistir([sys.executable, "-m", "venv", str(VENV)],
                           "Yalıtılmış Python ortamı oluşturuluyor")
        else:
            log("✓ Python ortamı zaten var")

        komut_calistir([str(venv_python()), "-m", "pip", "install", "--upgrade", "pip",
                        "--progress-bar", "off"],
                       "pip güncelleniyor")

        if REQUIREMENTS.exists():
            komut_calistir([str(venv_python()), "-m", "pip", "install", "-r", str(REQUIREMENTS),
                            "--progress-bar", "off"],
                           "Gerekli paketler kuruluyor (en uzun adım bu)")
        else:
            log("[!] backend/requirements.txt bulunamadı — bu dosya Claude Code ile üretilecek.")

        paketleri_arkada_kontrol_et()
        log("\n✓ KURULUM TAMAMLANDI")
        log("Şimdi 'Sistemi Başlat' düğmesine basabilirsiniz.")
        log("=" * 60)

    # ---- sistemi baslat ----
    def ciktiyi_oku():
        try:
            for satir in durum["surec"].stdout:
                log(satir.rstrip())
        except Exception as hata:
            # Sessizce yutulursa gunluk penceresi donar ve kimse sebebini
            # bilmez; en azindan satiri ekrana dusur.
            log(f"[HATA] Gunluk okunamadi: {hata}")

    def alt_surecte_baslat():
        """Gelistirme kurulumu: sunucu, .venv'deki python ile ayri surecte."""
        komut = [str(venv_python()), "-m", "uvicorn", "app.main:app",
                 "--host", dinleme_adresi(), "--port", str(PORT)]

        durum["surec"] = subprocess.Popen(
            komut, cwd=str(BACKEND),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0,
            start_new_session=not IS_WINDOWS,
        )
        _pid_yaz(durum["surec"].pid)
        threading.Thread(target=ciktiyi_oku, daemon=True).start()
        return True

    def sistemi_baslat():
        hal = sunucu_durumu()
        if hal == CALISIYOR:
            log("[!] Sistem zaten çalışıyor.")
            return
        if hal == BASKASINDA:
            for satir in port_dolu_mesaji():
                log(satir)
            return
        klasorleri_hazirla()
        log("=" * 60)
        log("SİSTEM BAŞLATILIYOR…")

        if PAKETLENMIS:
            durum["sunucu"] = _ic_surecte_baslat(log, log_kuyrugu.put)
            if durum["sunucu"] is None:
                return
        else:
            alt_surecte_baslat()

        # ILK acilis uzun surer: tanima modeli bir kez indirilir (~20-35 MB) ve
        # gecici onbellekler kurulur. 20 saniye yetmiyordu — sistem aslinda
        # sorunsuz acilirken ekranda "acilmadi" yaziyor, kullanici korkuyordu.
        for adim in range(360):      # en fazla 3 dakika
            if sunucu_ayakta():
                log(f"\n✓ SİSTEM ÇALIŞIYOR → {URL}")
                log("=" * 60)
                kok.after(400, lambda: webbrowser.open(URL))
                return
            if adim and adim % 30 == 0:
                log(f"   … hazırlanıyor ({adim // 2} sn geçti) — pencereyi kapatmayın.")
            time.sleep(0.5)
        log("[!] Sistem 3 dakikada açılmadı. Yukarıdaki hata satırlarına bakın.")

    # ---- sistemi durdur ----
    def ic_sureci_durdur() -> bool:
        """Ayni surecte calisan sunucuyu nazikce kapatir (kameralar dahil)."""
        sunucu = durum.get("sunucu")
        if sunucu is None:
            return False
        log("\nSistem durduruluyor…")
        sunucu.should_exit = True
        for _ in range(60):          # en fazla 15 saniye bekle
            if not sunucu_ayakta():
                break
            time.sleep(0.25)
        durum["sunucu"] = None
        log("✓ Durduruldu")
        return True

    def yedekten_don():
        """Yedekten geri yukleme — SISTEM DURMUSKEN.

        Uc kapi vardir ve ucu de bilerek konmustur:
          1. Sistem calisiyorsa reddedilir (acik veritabani dosyasinin altindan
             dosya degistirmek veri kaybidir),
          2. Kullanici dosyayi kendisi secer (yanlis yedegi geri yuklemek,
             hicbir sey yapmamaktan kotudur),
          3. Onay penceresinde ne olacagi acikca yazar ve mevcut verinin
             guvenlik kopyasinin alinacagi soylenir.
        """
        if sunucu_ayakta():
            messagebox.showwarning(
                "Sistem çalışıyor",
                "Geri yükleme yapabilmek için sistemin durmuş olması gerekir.\n\n"
                "Önce \"Durdur\" düğmesine basın, sonra yeniden deneyin.",
            )
            return

        yedekler = yedekleri_listele()
        if not yedekler:
            messagebox.showinfo(
                "Yedek yok",
                "Henüz hiç yedek alınmamış.\n\n"
                "Yedek almak için sistemi başlatıp izleme ekranındaki\n"
                "\"Yedek Al\" düğmesini kullanın.",
            )
            return

        secilen = filedialog.askopenfilename(
            title="Geri yüklenecek yedeği seçin",
            initialdir=str(YEDEK_DIZINI),
            filetypes=[("Veritabanı yedeği", "*.db")],
        )
        if not secilen:
            return

        ad = Path(secilen).name
        if not messagebox.askyesno(
            "Geri yükleme onayı",
            f"Şu yedek geri yüklenecek:\n\n{ad}\n\n"
            "BUGÜNKÜ kameralar, bölgeler, kurallar ve olay geçmişi bu yedektekilerle "
            "DEĞİŞTİRİLECEK.\n\n"
            "Mevcut verinin bir güvenlik kopyası yedekler klasörüne alınacak, "
            "böylece isterseniz geri dönebilirsiniz.\n\nDevam edilsin mi?",
            icon="warning",
        ):
            return

        try:
            guvenlik = yedekten_geri_yukle(secilen)
        except (OSError, ValueError) as hata:
            log(f"[!] Geri yükleme başarısız: {hata}")
            messagebox.showerror("Geri yükleme başarısız", str(hata))
            return

        log(f"\nYedek geri yüklendi: {ad}")
        if guvenlik:
            log(f"Önceki veriler şuraya kopyalandı: {guvenlik.name}")
        messagebox.showinfo(
            "Geri yükleme tamam",
            f"'{ad}' geri yüklendi.\n\n"
            + (f"Önceki verileriniz '{guvenlik.name}' adıyla saklandı.\n\n" if guvenlik else "")
            + "Şimdi \"Sistemi Başlat\" düğmesine basabilirsiniz.",
        )
        durumu_yenile()

    def sistemi_durdur():
        if PAKETLENMIS:
            if not ic_sureci_durdur():
                log("[!] Çalışan sistem bulunamadı.")
            return
        surec = durum.get("surec")
        if not surec or surec.poll() is not None:
            # Panel cokup yeniden acildiysa sunucu SAHIPSIZ calisiyor olabilir:
            # port dolu gorunur, "Durdur" ise "bulunamadi" der ve kullanici
            # panelden cikamayacagi bir duruma sikisirdi. PID dosyasi bu
            # durumdaki sureci sahiplenmeyi saglar.
            if _sahipsiz_sureci_durdur(log):
                durum["surec"] = None
                return
            log("[!] Çalışan sistem bulunamadı.")
            return
        log("\nSistem durduruluyor…")
        try:
            if IS_WINDOWS:
                # terminate() Windows'ta TerminateProcess'tir: kapanis kodu
                # (kamera is parcaciklari, baglantilar) hic calismaz. Once
                # nazik yolu dene.
                try:
                    surec.send_signal(signal.CTRL_BREAK_EVENT)
                    surec.wait(timeout=8)
                except Exception:
                    surec.terminate()
                    surec.wait(timeout=8)
            else:
                surec.terminate()
                surec.wait(timeout=8)
        except Exception:
            surec.kill()
        _pid_sil()
        durum["surec"] = None
        log("✓ Durduruldu")

    # ---- pencere kapatilirken ----
    def kapanirken():
        try:
            sistemi_durdur()
        except Exception:
            pass
        kok.destroy()

    kok.protocol("WM_DELETE_WINDOW", kapanirken)

    if PAKETLENMIS:
        # Kullaniciya mutlak dosya yolu gosterilmez (CLAUDE.md §8): paketlenmis
        # programda "proje klasoru" diye bir kavram da yoktur.
        log("NextGen Detector Kontrol Paneli hazır.")
        log("\nSistem kendiliğinden başlatılıyor; ilk açılış birkaç saniye sürer.")
        log("Bu pencereyi kapatırsanız sistem durur.\n")
    else:
        log("DALSAN İSG Kontrol Paneli hazır.")
        log(f"Proje klasörü: {ROOT}")
        log("\nİlk kez kullanıyorsanız: 'İlk Kurulumu Yap' düğmesine basın.\n")

    kuyrugu_bosalt()
    durumu_yenile()

    if PAKETLENMIS:
        # Cift tiklanan bir uygulamada ikinci bir "baslat" tiklamasi
        # gereksizdir: pencerenin kendisi zaten "kapatirsaniz sistem durur"
        # diyor — yani pencere acikken sistem calisiyor demektir. Kurulum
        # adimi da olmadigi icin kullanicinin yapabilecegi baska bir sey yok.
        # Baslatma basarisiz olursa "Sistemi Baslat" dugmesi yerinde durur;
        # kullanici sebebini gunlukte gorup tekrar deneyebilir.
        kok.after(600, lambda: is_baslat(sistemi_baslat))

    kok.mainloop()


# ----------------------------------------------------------------------------
# Arayuz acilamazsa metin modu
# ----------------------------------------------------------------------------
def metin_modu(hata):
    print("=" * 64)
    print(f"  {APP_TITLE}")
    print("=" * 64)
    print(f"\n  Pencere açılamadı: {hata}\n")
    if not PAKETLENMIS:
        print("  Mac'te Homebrew Python kullanıyorsanız şunu çalıştırın:")
        print("      brew install python-tk")
        print("\n  Ya da python.org üzerinden Python 3.12 kurun (tkinter dahildir).\n")
        print(f"  Proje klasörü : {ROOT}")
        print(f"  Python         : {'tamam' if python_ok() else 'SÜRÜM ESKİ'}")
        print(f"  Paketler       : {'kurulu' if paketler_hazir() else 'eksik'}")
        print(f"  Sistem kodu    : {'hazır' if kod_hazir() else 'henüz yok'}")
    hal = sunucu_durumu()
    print("  Sistem         : " + {
        CALISIYOR: "çalışıyor",
        BASKASINDA: f"{PORT} portunu BAŞKA bir program tutuyor",
        DURDU: "durdu",
    }[hal])
    print()
    input("  Kapatmak için Enter'a basın…")


if __name__ == "__main__":
    try:
        import tkinter  # noqa: F401
        arayuzu_baslat()
    except Exception as e:
        metin_modu(e)

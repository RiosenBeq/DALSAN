#!/usr/bin/env python3
"""
DALSAN ISG - Masaustu Kontrol Paneli
=====================================
Bu program, sistemi baslatip durdurmak icin kullanilir.
Terminal / komut satiri bilmeye gerek yoktur.

Mac'te   : Baslat-Mac.command  dosyasina cift tikla
Windows'ta: Baslat-Windows.bat dosyasina cift tikla
"""

import os
import queue
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# ----------------------------------------------------------------------------
# Ayarlar
# ----------------------------------------------------------------------------
APP_TITLE = "DALSAN İSG — Kontrol Paneli"
PORT = 8080
URL = f"http://127.0.0.1:{PORT}"

ROOT = Path(__file__).resolve().parent.parent   # depo kok dizini
BACKEND = ROOT / "backend"
VENV = ROOT / ".venv"
REQUIREMENTS = BACKEND / "requirements.txt"
MAIN_MODULE = BACKEND / "app" / "main.py"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
DATA_DIR = ROOT / "veri"
LOG_FILE = DATA_DIR / "loglar" / "sistem.log"

IS_WINDOWS = os.name == "nt"

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
    return MAIN_MODULE.exists()


def sunucu_ayakta() -> bool:
    """Port dinleniyor mu?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


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


def klasorleri_hazirla() -> None:
    for p in [DATA_DIR, DATA_DIR / "loglar", DATA_DIR / "goruntuler", DATA_DIR / "yedekler"]:
        p.mkdir(parents=True, exist_ok=True)
    if ENV_EXAMPLE.exists() and not ENV_FILE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_FILE)


# ----------------------------------------------------------------------------
# Arayuz
# ----------------------------------------------------------------------------
def arayuzu_baslat():
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import scrolledtext

    kok = tk.Tk()
    kok.title(APP_TITLE)
    kok.configure(bg=BG)
    kok.geometry("760x580")
    kok.minsize(680, 520)

    baslik_font = tkfont.Font(family="Helvetica", size=17, weight="bold")
    normal_font = tkfont.Font(family="Helvetica", size=12)
    kucuk_font = tkfont.Font(family="Helvetica", size=11)
    log_font = tkfont.Font(family="Menlo" if not IS_WINDOWS else "Consolas", size=10)

    durum = {"surec": None, "calisiyor": False, "mesgul": False}
    log_kuyrugu: "queue.Queue[str]" = queue.Queue()

    # paketler_hazir() bir alt surec calistirir (yavas). Ana pencere donmasin
    # diye kontrol ARKA PLANDA yapilir, sonucu burada saklanir.
    paket_durumu = {"hazir": None}  # None = henuz kontrol edilmedi

    def paketleri_arkada_kontrol_et():
        def kontrol():
            paket_durumu["hazir"] = paketler_hazir()
        threading.Thread(target=kontrol, daemon=True).start()

    paketleri_arkada_kontrol_et()

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

    durum_etiketleri = {}
    for anahtar, metin in [
        ("python", "Python"),
        ("paket", "Gerekli paketler"),
        ("kod", "Sistem kodu"),
        ("sunucu", "Sistem durumu"),
    ]:
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

    kurulum_btn = buton("İlk Kurulumu Yap", lambda: is_baslat(kurulumu_yap))
    baslat_btn = buton("Sistemi Başlat", lambda: is_baslat(sistemi_baslat), ana=True)
    durdur_btn = buton("Durdur", lambda: sistemi_durdur())
    ekran_btn = buton("İzleme Ekranını Aç", lambda: webbrowser.open(URL))

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
            durum_etiketleri[anahtar].configure(text=metin, fg=renk)

        if python_ok():
            ayarla("python", f"Hazır (sürüm {sys.version_info.major}.{sys.version_info.minor})", OK)
        else:
            ayarla("python", "Python 3.10 veya üstü gerekiyor", ERR)

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

        ayakta = sunucu_ayakta()
        durum["calisiyor"] = ayakta
        if ayakta:
            ayarla("sunucu", f"ÇALIŞIYOR — {URL}", OK)
        else:
            ayarla("sunucu", "Durdu", MUTED)

        baslat_btn.configure(state="normal" if (paket_hazir and kod_hazir() and not ayakta) else "disabled")
        durdur_btn.configure(state="normal" if ayakta else "disabled")
        ekran_btn.configure(state="normal" if ayakta else "disabled")
        kurulum_btn.configure(state="disabled" if durum["mesgul"] else "normal")

        kok.after(1500, durumu_yenile)

    # ---- uzun islemleri ayri is parcaciginda calistir ----
    def is_baslat(fonksiyon):
        if durum["mesgul"]:
            return
        durum["mesgul"] = True
        for b in (kurulum_btn, baslat_btn, durdur_btn):
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
            log("[HATA] Bu bilgisayardaki Python sürümü çok eski (3.10+ gerekiyor).")
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
    def sistemi_baslat():
        if sunucu_ayakta():
            log("[!] Sistem zaten çalışıyor.")
            return
        klasorleri_hazirla()
        log("=" * 60)
        log("SİSTEM BAŞLATILIYOR…")

        komut = [str(venv_python()), "-m", "uvicorn", "app.main:app",
                 "--host", "127.0.0.1", "--port", str(PORT)]

        durum["surec"] = subprocess.Popen(
            komut, cwd=str(BACKEND),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0,
            start_new_session=not IS_WINDOWS,
        )
        _pid_yaz(durum["surec"].pid)

        def ciktiyi_oku():
            try:
                for satir in durum["surec"].stdout:
                    log(satir.rstrip())
            except Exception as hata:
                # Sessizce yutulursa gunluk penceresi donar ve kimse sebebini
                # bilmez; en azindan satiri ekrana dusur.
                log(f"[HATA] Gunluk okunamadi: {hata}")

        threading.Thread(target=ciktiyi_oku, daemon=True).start()

        for _ in range(40):          # en fazla 20 saniye bekle
            if sunucu_ayakta():
                log(f"\n✓ SİSTEM ÇALIŞIYOR → {URL}")
                log("=" * 60)
                kok.after(400, lambda: webbrowser.open(URL))
                return
            time.sleep(0.5)
        log("[!] Sistem 20 saniyede açılmadı. Yukarıdaki hata satırlarına bakın.")

    # ---- sistemi durdur ----
    def sistemi_durdur():
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

    log("DALSAN İSG Kontrol Paneli hazır.")
    log(f"Proje klasörü: {ROOT}")
    log("\nİlk kez kullanıyorsanız: 'İlk Kurulumu Yap' düğmesine basın.\n")

    kuyrugu_bosalt()
    durumu_yenile()
    kok.mainloop()


# ----------------------------------------------------------------------------
# Arayuz acilamazsa metin modu
# ----------------------------------------------------------------------------
def metin_modu(hata):
    print("=" * 64)
    print("  DALSAN İSG — Kontrol Paneli")
    print("=" * 64)
    print(f"\n  Pencere açılamadı: {hata}\n")
    print("  Mac'te Homebrew Python kullanıyorsanız şunu çalıştırın:")
    print("      brew install python-tk")
    print("\n  Ya da python.org üzerinden Python 3.12 kurun (tkinter dahildir).\n")
    print(f"  Proje klasörü : {ROOT}")
    print(f"  Python         : {'tamam' if python_ok() else 'SÜRÜM ESKİ'}")
    print(f"  Paketler       : {'kurulu' if paketler_hazir() else 'eksik'}")
    print(f"  Sistem kodu    : {'hazır' if kod_hazir() else 'henüz yok'}")
    print(f"  Sistem         : {'çalışıyor' if sunucu_ayakta() else 'durdu'}")
    print()
    input("  Kapatmak için Enter'a basın…")


if __name__ == "__main__":
    try:
        import tkinter  # noqa: F401
        arayuzu_baslat()
    except Exception as e:
        metin_modu(e)

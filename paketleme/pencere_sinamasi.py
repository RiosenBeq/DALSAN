"""Üretilen uygulamanın izleme penceresini GERÇEKTEN açıp kapatır.

GitHub Actions üretim işi (.github/workflows/uygulama-uret.yml) her paketi
teslim etmeden önce bunu çalıştırır; elle de çalıştırılabilir:

    python paketleme/pencere_sinamasi.py pencere "<program>" [ekran.png]
    python paketleme/pencere_sinamasi.py tam "<program>" [ekran.png]

`<program>` Windows'ta `dist/NextGen Detector/NextGen Detector.exe`, Mac'te
`dist/NextGen Detector.app/Contents/MacOS/NextGen Detector`.

`pencere` - yalnız izleme penceresi, sunucusuz, birkaç saniye:
  1. `--pencere-denetimi` 0 ile bitmeli: pencere bileşeni pakette.
  2. `--izleme-penceresi ADRES`: işletim sisteminin web görünümü, geçici bir
     yerel sunucudaki sınama sayfasını gerçekten yükleyip HAZIR yazmalı.
     Sayfanın betiği motoru sunucuya bildirir; canlı akışı (EventSource)
     olmayan bir motor sınamayı geçemez.
  3. GOSTER: pencere öne gelirken süreç ayakta kalmalı ve HATA satırı
     yazmamalı (istenirse ekranın görüntüsü bu anda alınır).
  4. Kanal kapanınca pencere kendini kapatıp 0 ile bitmeli: Kontrol Paneli
     kapanınca olan budur.

`tam` - uygulamanın tamamı, kullanıcının çift tıklamasıyla aynı: Kontrol
  Paneli açılır, sistemi kendisi başlatır (ilk açılışta modeli indirir) ve
  izleme penceresini açar. /saglik yanıt verene, tespit modeli inip
  yüklenene ("model": "hazir"), pencere süreci görünene ve izleme ekranı
  canlı akışa bağlanana (/saglik?ayrinti=1 "ekran_istemci") kadar
  beklenir; pencere hâlâ açıksa ekranın görüntüsü alınır, uygulama kapatılır. Model inmez ya da
  yüklenemezse (yayın dosyası yok, özeti tutmuyor, biçimi uymuyor) paket
  tespitsiz çalışırdı: sınama bunu yakalar.

Bir adım tutmazsa sebebini yazar ve 1 ile biter. Yalnız standart kütüphane:
bunu uygulamanın içindeki değil, üretim işinin kendi Python'u çalıştırır.
"""

from __future__ import annotations

import http.server
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# İlk WebView2 açılışı (kullanıcı klasörü kurulur) üretim makinesinde yavaş olabilir.
HAZIR_BEKLEMESI_SN = 120
MOTOR_BEKLEMESI_SN = 20
KAPANIS_BEKLEMESI_SN = 30
# İlk açılışta tanıma modeli (~20-35 MB) indirilir; Kontrol Paneli 3 dakika bekler.
SISTEM_BEKLEMESI_SN = 300
PENCERE_BEKLEMESI_SN = 90
# Pencere açıldıktan sonra izleme ekranının sayfası yüklenip canlı akışa bağlanmalı
EKRAN_BEKLEMESI_SN = 90
# Pencere sürecinin panele yazdığı hata satırı öneki
# (masaustu/uygulama_penceresi.py HATA_ONEKI; testler ikisinin aynı olduğunu denetler)
HATA_ONEKI = "HATA "
# Sayfa motorunu bildirmezse canlı akış doğrulanamaz: sınama geçmez. Yalnız
# sayfa çizmeyen sahte kütüphaneyle koşan yerel test kapatır.
MOTOR_RAPORU_ZORUNLU = True
SAGLIK_ADRESI = "http://127.0.0.1:8080/saglik"

SAYFA = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>NextGen Detector - pencere sınaması</title>
<style>body{font:26px system-ui,sans-serif;background:#eef1f6;color:#1c1917;margin:48px}</style>
</head><body>
<h1>İzleme penceresi sınaması</h1>
<p>Bu sayfayı işletim sisteminin kendi web görünümü çiziyor; tarayıcı açılmadı.</p>
<p id="motor">motor okunuyor...</p>
<script>
  var bilgi = {canli_akis: typeof EventSource, istek: typeof fetch, ua: navigator.userAgent};
  document.getElementById("motor").textContent = JSON.stringify(bilgi);
  fetch("/motor?" + new URLSearchParams(bilgi));
</script>
</body></html>
"""


class SinamaHatasi(Exception):
    """Bir adım tutmadı; ileti kullanıcıya olduğu gibi yazılır."""


class _SinamaSunucusu(http.server.BaseHTTPRequestHandler):
    motorlar: queue.Queue = queue.Queue()

    def do_GET(self) -> None:  # noqa: N802 - http.server'ın adı
        yol = urllib.parse.urlsplit(self.path)
        if yol.path == "/motor":
            self.motorlar.put(dict(urllib.parse.parse_qsl(yol.query)))
            govde, tur = b"tamam", "text/plain"
        else:
            govde, tur = SAYFA.encode("utf-8"), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def log_message(self, *_bilgi) -> None:
        """Her isteği ekrana dökme."""


def _calistir(komut: list[str], **secenek) -> subprocess.CompletedProcess:
    return subprocess.run(
        komut, capture_output=True, text=True, encoding="utf-8", errors="replace", **secenek
    )


def pencere_sina(program: str, ekran: str | None) -> None:
    denetim = _calistir([program, "--pencere-denetimi"], timeout=180)
    print(f"denetim: {(denetim.stdout + denetim.stderr).strip()}")
    if denetim.returncode != 0:
        raise SinamaHatasi(f"--pencere-denetimi {denetim.returncode} koduyla bitti")

    sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SinamaSunucusu)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    adres = f"http://127.0.0.1:{sunucu.server_address[1]}/"
    profil = tempfile.mkdtemp(prefix="pencere-sinamasi-")
    surec = subprocess.Popen(  # noqa: S603 - sınanan program
        [program, "--izleme-penceresi", adres, profil],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    satirlar: queue.Queue = queue.Queue()

    def oku() -> None:
        for satir in surec.stdout:
            satirlar.put(satir.rstrip())
        satirlar.put(None)

    okuyucu = threading.Thread(target=oku, daemon=True)
    okuyucu.start()
    try:
        _hazir_bekle(surec, satirlar)
        try:
            motor = _SinamaSunucusu.motorlar.get(timeout=MOTOR_BEKLEMESI_SN)
        except queue.Empty:
            if MOTOR_RAPORU_ZORUNLU:
                raise SinamaHatasi(
                    f"sayfa motorunu {MOTOR_BEKLEMESI_SN} sn içinde bildirmedi: sayfanın "
                    "betiği çalışmıyor, canlı akış doğrulanamadı"
                ) from None
            print(f"UYARI: sayfa motorunu {MOTOR_BEKLEMESI_SN} sn içinde bildirmedi")
        else:
            print(f"motor: {json.dumps(motor, ensure_ascii=False)}")
            if motor.get("canli_akis") != "function":
                raise SinamaHatasi("web görünümünde canlı akış (EventSource) yok")

        surec.stdin.write("GOSTER\n")
        surec.stdin.flush()
        time.sleep(3)
        if surec.poll() is not None:
            raise SinamaHatasi(f"pencere öne getirilirken kapandı (kod {surec.returncode})")
        _hata_satirlarini_denetle(satirlar)
        if ekran:
            ekran_goruntusu(ekran)

        surec.stdin.close()
        try:
            kod = surec.wait(timeout=KAPANIS_BEKLEMESI_SN)
        except subprocess.TimeoutExpired as hata:
            raise SinamaHatasi("kanal kapandığı halde pencere kapanmadı") from hata
        if kod != 0:
            raise SinamaHatasi(f"pencere {kod} koduyla kapandı")
        okuyucu.join(timeout=10)
        _hata_satirlarini_denetle(satirlar)
        print("pencere: açıldı, öne geldi, kanal kapanınca kendini kapattı")
    finally:
        if surec.poll() is None:
            surec.kill()
        sunucu.shutdown()


def _hata_satirlarini_denetle(satirlar: queue.Queue) -> None:
    """HAZIR'dan sonra gelen satırlar: HATA satırı sınamayı düşürür.

    Süreç ayakta kalıp "HATA pencere öne getirilemedi" yazabilir; yalnız
    sürecin yaşadığına bakmak bunu geçirirdi.
    """
    while True:
        try:
            satir = satirlar.get_nowait()
        except queue.Empty:
            return
        if satir is None:
            continue  # çıktı kapandı; kalan satırlara bakılmaya devam
        print(f"pencere süreci: {satir}")
        if satir.startswith(HATA_ONEKI):
            raise SinamaHatasi(f"pencere süreci hata bildirdi: {satir[len(HATA_ONEKI) :]}")


def _hazir_bekle(surec: subprocess.Popen, satirlar: queue.Queue) -> None:
    son = time.monotonic() + HAZIR_BEKLEMESI_SN
    while (kalan := son - time.monotonic()) > 0:
        try:
            satir = satirlar.get(timeout=kalan)
        except queue.Empty:
            break
        if satir is None:
            surec.wait(timeout=10)
            hata = surec.stderr.read().strip()
            raise SinamaHatasi(
                f"pencere süreci HAZIR demeden {surec.returncode} koduyla kapandı"
                + (f": {hata[-2000:]}" if hata else "")
            )
        print(f"pencere süreci: {satir}")
        if satir == "HAZIR":
            return
    raise SinamaHatasi(f"pencere {HAZIR_BEKLEMESI_SN} sn içinde HAZIR demedi")


def tam_sina(program: str, ekran: str | None) -> None:
    grup = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if sys.platform.startswith("win")
        else {"start_new_session": True}
    )
    surec = subprocess.Popen(  # noqa: S603 - sınanan program
        [program],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **grup,
    )
    try:
        saglik = _saglik_bekle(surec)
        print(f"sistem: /saglik yanıt verdi ({', '.join(sorted(saglik))[:300]})")
        saglik = _model_bekle(surec)
        print(f"model: {saglik.get('model')} (sorunlar: {', '.join(saglik.get('sorunlar', []))})")
        _pencere_bekle(surec)
        print("pencere: Kontrol Paneli izleme penceresini kendiliğinden açtı")
        _ekran_bekle(surec)
        print("ekran: izleme ekranı yüklendi, canlı akışa bağlandı")
        time.sleep(10)  # sayfa otursun
        if not pencere_sureci_var():
            # Pencere yüklenemeyince kendini kapatır ve panel yedek pencereye geçer:
            # ekran yine bağlanır ama uygulamanın kendi penceresi yoktur.
            raise SinamaHatasi("izleme penceresi açıldıktan sonra kapandı")
        if ekran:
            ekran_goruntusu(ekran)
    finally:
        _agaci_kapat(surec)


def _ekran_bekle(surec: subprocess.Popen) -> None:
    """İzleme ekranının sayfası pencerede yüklenip canlı akışa bağlandı mı?

    /saglik?ayrinti=1'deki "ekran_istemci" (şifresiz ilk kurulumda oturum
    gerekmez). Yalnız pencere sürecine bakmak boş kalan bir pencereyi de
    geçirirdi.
    """
    son = time.monotonic() + EKRAN_BEKLEMESI_SN
    while time.monotonic() < son:
        if surec.poll() is not None:
            raise SinamaHatasi(f"uygulama {surec.returncode} koduyla kapandı")
        try:
            with urllib.request.urlopen(SAGLIK_ADRESI + "?ayrinti=1", timeout=3) as yanit:
                if (json.loads(yanit.read(65536)).get("ekran_istemci") or 0) >= 1:
                    return
        except (urllib.error.URLError, OSError, ValueError) as hata:
            print(f"ekran bekleniyor: {hata}")
        time.sleep(2)
    raise SinamaHatasi(
        f"izleme ekranı {EKRAN_BEKLEMESI_SN} sn içinde canlı akışa bağlanmadı "
        "(pencere açık ama sayfa yüklenmedi)"
    )


def _saglik_bekle(surec: subprocess.Popen) -> dict:
    son = time.monotonic() + SISTEM_BEKLEMESI_SN
    while time.monotonic() < son:
        if surec.poll() is not None:
            raise SinamaHatasi(f"uygulama {surec.returncode} koduyla kapandı")
        try:
            with urllib.request.urlopen(SAGLIK_ADRESI, timeout=3) as yanit:
                return json.loads(yanit.read(65536))
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(2)
    raise SinamaHatasi(f"sistem {SISTEM_BEKLEMESI_SN} sn içinde açılmadı (/saglik yanıtsız)")


def _model_bekle(surec: subprocess.Popen) -> dict:
    """Tespit modeli inip yüklenene kadar bekler; yüklenemezse sebebiyle düşer.

    /saglik'taki "model": indiriliyor / yukleniyor / hazir / hata / kapali.
    """
    son = time.monotonic() + SISTEM_BEKLEMESI_SN
    saglik: dict = {}
    while time.monotonic() < son:
        if surec.poll() is not None:
            raise SinamaHatasi(f"uygulama {surec.returncode} koduyla kapandı")
        try:
            with urllib.request.urlopen(SAGLIK_ADRESI, timeout=3) as yanit:
                saglik = json.loads(yanit.read(65536))
        except (urllib.error.URLError, OSError, ValueError):
            saglik = {}
        if saglik.get("model") == "hazir":
            return saglik
        if saglik.get("model") == "hata":
            raise SinamaHatasi(
                "tespit modeli yüklenemedi (sorunlar: "
                f"{', '.join(saglik.get('sorunlar', [])) or '-'})"
            )
        time.sleep(2)
    raise SinamaHatasi(
        f"tespit modeli {SISTEM_BEKLEMESI_SN} sn içinde hazır olmadı "
        f"(son durum: {saglik.get('model', 'yanıt yok')})"
    )


def _pencere_bekle(surec: subprocess.Popen) -> None:
    son = time.monotonic() + PENCERE_BEKLEMESI_SN
    while time.monotonic() < son:
        if surec.poll() is not None:
            raise SinamaHatasi(f"uygulama {surec.returncode} koduyla kapandı")
        if pencere_sureci_var():
            return
        time.sleep(2)
    raise SinamaHatasi(f"izleme penceresi {PENCERE_BEKLEMESI_SN} sn içinde açılmadı")


def pencere_sureci_var() -> bool:
    """`--izleme-penceresi` ile açılmış bir süreç çalışıyor mu?

    Windows'ta aramayı yapan PowerShell'in kendi komut satırı da aranan metni
    içerir: kendisi ($PID) dışarıda bırakılmazsa pencere hiç açılmasa da
    her zaman "var" derdi.
    """
    if sys.platform.startswith("win"):
        sonuc = _calistir(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID "
                "-and $_.CommandLine -like '*--izleme-penceresi*' } | "
                "ForEach-Object { $_.CommandLine }",
            ],
            timeout=60,
        )
    else:
        sonuc = _calistir(["ps", "-eo", "args"], timeout=30)
    return "--izleme-penceresi" in sonuc.stdout


def _agaci_kapat(surec: subprocess.Popen) -> None:
    """Uygulamayı çocuklarıyla (pencere süreci, web görünümü) birlikte kapatır."""
    if sys.platform.startswith("win"):
        _calistir(["taskkill", "/F", "/T", "/PID", str(surec.pid)], timeout=60)
    else:
        try:
            os.killpg(surec.pid, signal.SIGTERM)
            surec.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(surec.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # zaten kapanmış
    try:
        surec.wait(timeout=30)
    except subprocess.TimeoutExpired:
        print("UYARI: uygulama kapatılamadı")


def ekran_goruntusu(hedef: str) -> None:
    """Bütün ekranın görüntüsü; alınamazsa uyarır, sınamayı düşürmez."""
    hedef = os.path.abspath(hedef)
    if sys.platform.startswith("win"):
        betik = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
            "$r=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
            "$g=[System.Drawing.Graphics]::FromImage($r);"
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
            f"$r.Save('{hedef}',[System.Drawing.Imaging.ImageFormat]::Png)"
        )
        komut = ["powershell", "-NoProfile", "-Command", betik]
    elif sys.platform == "darwin":
        komut = ["screencapture", "-x", hedef]
    else:
        print("ekran görüntüsü: bu sistemde alınmıyor")
        return
    try:
        sonuc = _calistir(komut, timeout=60)
    except (OSError, subprocess.SubprocessError) as hata:
        print(f"UYARI: ekran görüntüsü alınamadı ({hata})")
        return
    if sonuc.returncode == 0 and os.path.isfile(hedef):
        print(f"ekran görüntüsü: {hedef}")
    else:
        print(f"UYARI: ekran görüntüsü alınamadı ({(sonuc.stdout + sonuc.stderr).strip()})")


def main(argumanlar: list[str]) -> int:
    if len(argumanlar) < 2 or argumanlar[0] not in ("pencere", "tam"):
        print(__doc__)
        return 2
    kip, program = argumanlar[0], argumanlar[1]
    ekran = argumanlar[2] if len(argumanlar) > 2 else None
    try:
        (pencere_sina if kip == "pencere" else tam_sina)(program, ekran)
    except SinamaHatasi as hata:
        print(f"HATA: {hata}")
        return 1
    print("SINAMA GEÇTİ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

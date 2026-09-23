"""Anons kanalları (docs/02 §7, docs/17 §7): ses çıkışı ve IP hoparlör.

KANALLAR speaker_zones satırlarıdır (şema 009, K22): `kind` = `ses_karti`
(bu bilgisayarın ses çıkışı; `device` = çıkışın adı) ya da `http` (IP hoparlör,
`address`). Olay, kameranın BÖLÜMÜNDEKİ bütün açık kanallara gider; bölümde
kanal yoksa "Tüm fabrika" (area boş) kanallarına. Hiç kanal yoksa ses çalmaz ve
bunu söyler; sistem anonstan bağımsız çalışır (K6). Eskiden kanalı .env'deki
ANONS ayarı seçiyordu; o ayar ilk açılışta bir kez satıra aktarılır
(olaylar/kanallar.py).

Anons cooldown'u ekran uyarısından BAĞIMSIZ ve daha uzundur - ekranda 3 olay
görünmesi sorun değil; hoparlörün 3 kez bağırması sorundur (docs/03 §5).

HTTP BİÇİMİ (.env → ANONS_HTTP_BICIMI): sahadaki IP hoparlörlerin HTTP
arayüzü tek tip değildir. Üç biçim desteklenir - `json` (gövdede JSON,
varsayılan), `form` (gövdede form alanı), `get` (adres çağrılır, mesaj adresteki
{anahtar}/{metin} yer tutucularına yazılır). Hangi cihaz için hangisinin
seçileceği docs/14-ANONS-SISTEMI-BAGLAMA.md'de tarif edilir.
"""

from __future__ import annotations

import ipaddress
import json
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app import veritabani, zaman
from app.ayarlar import Ayarlar
from app.loglama import adres_maskele, log_al
from app.olaylar import ekran, ses_cihazlari
from app.olaylar.dagitici import (
    ASAMA_ACILDI,
    ASAMA_TEST,
    SONUC_BASARISIZ,
    SONUC_BASTIRILDI,
    SONUC_DINLEYEN_YOK,
    SONUC_GERI_DUSUS,
    SONUC_GOLGE,
    SONUC_KESILDI,
    SONUC_TAMAM,
    CikisIscisi,
    UyariOgesi,
)
from app.olaylar.kanal_sagligi import (
    HAL_KOPTU,
    KOD_KOPTU,
    KanalHali,
    ilerle,
    kanal_imzasi,
    kanal_yokla,
)
from app.olaylar.kanallar import kanal_ozeti
from app.olaylar.teslim import TeslimKaydedici, teslim_satiri
from app.olaylar.yazici import olay_kapat, sistem_olayi_yaz
from app.rules.cooldown import Cooldown
from app.rules.olay_kodu import OLAY_KODLARI

_log = log_al("anons")

# Ses çalıcısı bu sürede bitmezse sonlandırılır; kesme bu aralıkla yoklanır
_CALMA_ZAMAN_ASIMI_SN = 20
_KESME_YOKLAMA_SN = 0.1


class AnonsHatasi(Exception):
    """Ses çalınamadı - sebebi Anons sayfasında gösterilir."""


class AnonsKesildi(AnonsHatasi):
    """Çalan ses, kritik bir uyarıya yer açmak için kesildi (docs/17 §7.3-3)."""


def _ses_komutu(ses_dosyasi: str, cihaz: str = "") -> list[str] | None:
    """İşletim sistemine göre WAV çalma komutu.

    Fabrika sunucusu Linux'tur (aplay/paplay); geliştirme Mac (afplay) olabilir.
    İkisinde de EK KURULUM GEREKTİRMEYEN, sistemde hazır gelen araçlar seçildi.
    Windows'ta KOMUT YOKTUR: ses Python'un kendi `winsound` modülüyle, süreç
    açmadan çalınır (`_windows_cal`); bu işlev orada None döner.

    `cihaz` (kanal satırının `device`'ı) hangi ses ÇIKIŞINA çalınacağıdır ve
    yalnızca Linux'ta işe yarar: paplay/aplay çıkışı adıyla alır, afplay ve
    winsound almaz. Mac/Windows'ta çıkış, işletim sisteminin ses
    ayarlarından seçilir - ayrıntı: olaylar/ses_cihazlari.py.
    """
    if sys.platform == "win32":
        return None
    # SIRA ÖNEMLİ - paplay, aplay'den ÖNCE denenir. aplay ham ALSA'dır ve
    # Bluetooth hoparlörü HİÇ GÖRMEZ; Bluetooth çıkışı PulseAudio/PipeWire
    # tarafındadır ve ona ancak paplay çalar. İkisi de kuruluyken aplay
    # seçilseydi, kullanıcı listeden Bluetooth hoparlörünü seçer ve ses
    # sessizce hiçbir yere gitmezdi.
    calici = shutil.which("afplay") or shutil.which("paplay") or shutil.which("aplay")
    if calici is None:
        return None
    if cihaz:
        # Cihaz bayrağı çalıcıya göre değişir. Bilinmeyen bir çalıcıya
        # tanımadığı bir bayrak vermek sesi HİÇ çaldırmazdı; o yüzden yalnızca
        # bayrağını bildiğimiz ikisinde eklenir, gerisinde sessizce atlanır.
        if calici.endswith("paplay"):
            return [calici, f"--device={cihaz}", ses_dosyasi]
        if calici.endswith("aplay"):
            return [calici, "-D", cihaz, ses_dosyasi]
    return [calici, ses_dosyasi]


def _windows_durdur() -> None:
    """Windows'ta çalan sesi keser (PlaySound süreç başına tek sestir)."""
    import winsound  # yalnız Windows'ta vardır

    winsound.PlaySound(None, 0)


def _sonlandir(surec: subprocess.Popen) -> None:
    surec.terminate()
    try:
        surec.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        surec.kill()
        surec.communicate()


def _sureci_calistir(komut: list[str], ses_dosyasi: str, kes: threading.Event | None) -> None:
    """Çalıcıyı başlatır ve biter, kesilir ya da zaman aşar diye 100 ms'de bir yoklar.

    `subprocess.run` yerine `Popen`: kritik bir uyarı gelince çalan düşük
    öncelikli ses sonlandırılabilsin (docs/17 §7.3-3). Sonuç yine BEKLENİR:
    beklenmezse komut hemen başarısız olsa bile "çalındı" yazardı.
    """
    try:
        surec = subprocess.Popen(komut, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except (OSError, subprocess.SubprocessError) as hata:
        raise AnonsHatasi(f"Ses çalınamadı ({ses_dosyasi}): {hata}") from hata
    son = time.monotonic() + _CALMA_ZAMAN_ASIMI_SN
    while True:
        try:
            _, hata_metni = surec.communicate(timeout=_KESME_YOKLAMA_SN)
            break
        except subprocess.TimeoutExpired:
            if kes is not None and kes.is_set():
                _sonlandir(surec)
                raise AnonsKesildi("Kritik bir uyarıya yer açmak için kesildi.") from None
            if time.monotonic() > son:
                _sonlandir(surec)
                raise AnonsHatasi(
                    f"Ses çalınamadı ({ses_dosyasi}): {_CALMA_ZAMAN_ASIMI_SN} sn içinde bitmedi."
                ) from None
    if surec.returncode != 0:
        ayrinti = (hata_metni or b"").decode("utf-8", "replace").strip()[:200]
        raise AnonsHatasi(
            f"Ses çalınamadı ({ses_dosyasi}). "
            + (f"Sebep: {ayrinti}" if ayrinti else "Dosya biçimi desteklenmiyor olabilir.")
        )


def _windows_cal(ses_dosyasi: str) -> None:
    """Windows: WAV'ı stdlib `winsound` ile çalar - süreç açılmaz, komut kurulmaz.

    Eskiden PowerShell'e `(New-Object Media.SoundPlayer '<yol>').PlaySync()`
    METNİ veriliyordu. Yol arayüzden girildiği için güvenlik tek tırnak
    kaçışına bağlıydı (docs/17 §10.5). winsound yolu komut değil VERİ olarak
    alır; kaçılacak bir şey yoktur.

    SND_NODEFAULT şarttır: onsuz, dosya bulunamadığında ya da WAV değilse
    Windows varsayılan "bip" sesini çalar ve çağrı BAŞARILI döner - "Anonsu
    Dene" düğmesi "çalındı" derdi. Çağrı ses bitene kadar bekler (anons zaten
    kendi iş parçacığındadır). İkinci bir anons ilki çalarken gelirse Windows
    ilkini keser: PlaySound süreç başına tek sestir. Üst üste binen iki
    anonstan anlaşılır olanı budur.
    """
    import winsound  # yalnız Windows'ta vardır

    try:
        winsound.PlaySound(ses_dosyasi, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
    except RuntimeError as hata:
        raise AnonsHatasi(
            f"Ses çalınamadı ({ses_dosyasi}). Dosya bulunamadı ya da WAV biçiminde değil."
        ) from hata


class SesKartiAnonscu:
    """Kayıtlı WAV dosyasını yerel ses kartından çalar → mevcut amplifikatör.

    macOS: afplay · Linux: aplay/paplay · Windows: winsound (Python ile gelir).
    Ses dosyası tanımlı değilse yalnız log düşer (sistem yine çalışır).
    """

    ad = "ses kartı"

    def __init__(self, cihaz: str = "") -> None:
        # Hangi ses çıkışına çalınacağı (kanal satırının `device`'ı). Boşsa
        # işletim sisteminin varsayılan çıkışı kullanılır.
        self.cihaz = cihaz
        # Windows'ta komut her zaman vardır; diğerlerinde varlığı sınanır
        self._kullanilabilir = sys.platform == "win32" or _ses_komutu("deneme") is not None
        if not self._kullanilabilir:
            _log.error(
                "Ses çalma komutu bulunamadı (afplay/aplay/paplay). "
                "Linux'ta 'sudo apt install pulseaudio-utils' kurun ya da bu kanalı "
                "Anons sayfasından kapatın."
            )

    def cal(
        self,
        anahtar: str,
        metin: str,
        ses_dosyasi: str | None,
        kes: threading.Event | None = None,
    ) -> None:
        """Sesi çalar; `kes` kurulursa (kritik uyarı geldi) çalmayı keser."""
        if not self._kullanilabilir:
            raise AnonsHatasi("Bu bilgisayarda ses çalma komutu bulunamadı (afplay/aplay/paplay).")
        if not ses_dosyasi:
            raise AnonsHatasi(
                f"'{anahtar}' mesajına ses dosyası bağlanmamış. Anons sayfasında "
                "bir .wav dosyasının yolunu yazın; yoksa yalnızca ekran uyarısı verilir."
            )
        if sys.platform == "win32":
            _windows_cal(ses_dosyasi)
            # Kesme Windows'ta PlaySound(None) ile yapılır; çağrı normal döner
            if kes is not None and kes.is_set():
                raise AnonsKesildi("Kritik bir uyarıya yer açmak için kesildi.")
            _log.info(f"Anons çalındı: {metin}")
            return
        komut = _ses_komutu(ses_dosyasi, self.cihaz)
        if komut is None:
            raise AnonsHatasi(f"Ses çalma komutu bulunamadı: {ses_dosyasi}")
        # Bu çağrı zaten ayrı bir iş parçacığındadır (çıkış işçisi, olaylar/
        # dagitici.py), bu yüzden sonucu BEKLEYEBİLİRİZ.
        _sureci_calistir(komut, ses_dosyasi, kes)
        _log.info(f"Anons çalındı: {metin}")


def adresi_doldur(adres: str, anahtar: str, metin: str) -> str:
    """Adresteki {anahtar} / {metin} yer tutucularını doldurur (URL kaçışlı).

    `str.format` KULLANILMAZ: adres kullanıcıdan gelir ve içinde anons
    sisteminin kendi süslü parantezleri olabilir ("...?q={id}"); format
    bunlarda KeyError fırlatıp anonsu tamamen susturur. Düz metin değişimi
    yalnızca bildiğimiz iki yer tutucuya dokunur, gerisini olduğu gibi bırakır.
    """
    return adres.replace("{anahtar}", urllib.parse.quote(anahtar, safe="")).replace(
        "{metin}", urllib.parse.quote(metin, safe="")
    )


def _yasak_mi(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Bu bilgisayar (loopback, 0.0.0.0) ya da bağlantı-yerel ağ (169.254/16,
    fe80::/10; bulut üst veri servisi 169.254.169.254 dahil)."""
    eslenik = getattr(ip, "ipv4_mapped", None)  # ::ffff:127.0.0.1 gibi
    return any(
        adres.is_loopback or adres.is_link_local or adres.is_unspecified
        for adres in (ip, eslenik)
        if adres is not None
    )


def hoparlor_adresini_dogrula(adres: str) -> None:
    """R30 (SSRF): IP hoparlör adresi bu bilgisayarı ya da bağlantı-yerel ağı
    gösteremez; gösteriyorsa AnonsHatasi.

    Hoparlör fabrika ağındadır. Formdan girilen bir adres sunucunun kendi
    servislerine (127.0.0.1) ya da bulut üst veri servisine (169.254.169.254)
    işaret ederse "Bu hoparlörü dene" ve kanal sağlık yoklaması bir iç ağ
    tarayıcısına dönüşürdü. Özel ağ adresleri (10/8, 192.168/16…) serbesttir:
    hoparlörler oradadır.

    Ad yazılmışsa ÇÖZÜLÜR ve her sonuç denetlenir: '2130706433' ya da
    '0177.0.0.1' gibi yazımlar da 127.0.0.1'e çıkar. Çözülemeyen ad burada
    reddedilmez; gönderimde urllib "ulaşılamadı" der. Gönderim bu işlevi her
    seferinde yeniden çağırır (kayıttan sonra değişen DNS için). Denetim ile
    bağlantı arasında DNS'in değişmesi (rebinding) bu düzeyde kapatılmaz.
    """
    maskeli = adres_maskele(adres)
    try:
        parca = urllib.parse.urlsplit(adres)
        sunucu = parca.hostname or ""
        port = parca.port or (443 if parca.scheme == "https" else 80)
    except ValueError:
        raise AnonsHatasi(f"Hoparlör adresi okunamadı ({maskeli}).") from None
    if not sunucu:
        raise AnonsHatasi(f"Hoparlör adresinde sunucu adı yok ({maskeli}).")
    if sunucu == "localhost" or sunucu.endswith(".localhost"):
        adresler = [ipaddress.ip_address("127.0.0.1")]
    else:
        try:
            adresler = [ipaddress.ip_address(sunucu)]
        except ValueError:
            try:
                bilgiler = socket.getaddrinfo(sunucu, port, proto=socket.IPPROTO_TCP)
            except (socket.gaierror, UnicodeError):
                return
            adresler = [ipaddress.ip_address(b[4][0].split("%", 1)[0]) for b in bilgiler]
    if any(_yasak_mi(ip) for ip in adresler):
        _log.error(f"Hoparlör adresi reddedildi, bu bilgisayarı gösteriyor: {maskeli}")
        raise AnonsHatasi(
            f"Hoparlör adresi ({maskeli}) bu bilgisayarı ya da bağlantı-yerel bir adresi "
            "gösteriyor; güvenlik nedeniyle kabul edilmez. IP hoparlörün fabrika ağındaki "
            "adresini yazın (örnek: http://10.0.0.9:8080/anons)."
        )


def _istek_hazirla(adres: str, anahtar: str, metin: str, bicim: str):
    """Biçime göre urllib isteği kurar (json | form | get).

    Üç biçim, sahadaki üç yaygın cihaz ailesine karşılık gelir:
      json - anons sunucuları / yazılım geçitleri (varsayılan, eski davranış)
      form - gömülü web arayüzlü amfi ve röle kartları
      get  - "adresi çağır, sesi çal" diyen IP hoparlörler
    """
    dolu_adres = adresi_doldur(adres, anahtar, metin)
    if bicim == "get":
        # Gövde YOK: urllib, data verilmezse GET kullanır.
        return urllib.request.Request(dolu_adres)
    if bicim == "form":
        veri = urllib.parse.urlencode({"key": anahtar, "text": metin}).encode("utf-8")
        return urllib.request.Request(
            dolu_adres,
            data=veri,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    veri = json.dumps({"key": anahtar, "text": metin}).encode("utf-8")
    return urllib.request.Request(
        dolu_adres, data=veri, headers={"Content-Type": "application/json"}
    )


def http_gonder(adres: str, anahtar: str, metin: str, bicim: str = "json") -> None:
    """Tek bir anons adresine HTTP isteği atar; başarısızlıkta AnonsHatasi.

    `bicim` .env'deki ANONS_HTTP_BICIMI'dir: json (gövdede JSON, varsayılan),
    form (gövdede form alanı) ya da get (adres çağrılır). Hangi cihaz için
    hangisi seçilir: docs/14-ANONS-SISTEMI-BAGLAMA.md.

    Ayrı bir fonksiyon: hem ihlal anındaki otomatik anons hem de arayüzdeki
    "Bu hoparlörü dene" düğmesi AYNI yoldan gider. İkisi ayrı kod olsaydı
    deneme başarılı olup gerçek anons sessizce başarısız olabilirdi.
    """
    # R30: her gönderimde (adres kayıttan sonra başka yeri gösterir olabilir)
    hoparlor_adresini_dogrula(adres)
    try:
        # İstek kurulumu da içeride: bozuk adresin ValueError'ı burada doğar
        istek = _istek_hazirla(adres, anahtar, metin, bicim)
        with urllib.request.urlopen(istek, timeout=5) as yanit:
            _log.info(f"Anons HTTP gönderildi ({yanit.status}): {metin}")
    except (urllib.error.URLError, TimeoutError, ValueError) as hata:
        # ValueError: adres biçimi bozuksa urllib bunu fırlatır - ve metnine
        # adresi OLDUĞU GİBİ koyar ("unknown url type: 'htp://kul:sifre@…'").
        # Adresteki kullanıcı adı/şifre ne günlüğe ne ekrana gider (R18): adres
        # de sebep de maskelenir; çağıran taraf hangi hoparlör olduğunu maskeli
        # adresle ekler. Zincir (`from`) kesilir: yığın izi günlüğe düşerse
        # ham metin oradan sızardı.
        sebep = adres_maskele(str(hata))
        _log.error(f"Anons HTTP gönderilemedi ({adres_maskele(adres)}): {sebep}")
        raise AnonsHatasi(
            f"Anons adresine ulaşılamadı. Sebep: {sebep}. "
            "Hoparlörün açık ve aynı ağda olduğunu doğrulayın."
        ) from None


class HttpAnonscu:
    """IP hoparlör / anons sunucusuna HTTP isteği atar (biçim .env'den)."""

    ad = "http"

    def __init__(self, adres: str, bicim: str = "json") -> None:
        self._adres = adres
        self._bicim = bicim

    @property
    def adres(self) -> str:
        return self._adres

    @property
    def bicim(self) -> str:
        return self._bicim

    def cal(
        self,
        anahtar: str,
        metin: str,
        ses_dosyasi: str | None,
        kes: threading.Event | None = None,
    ) -> None:
        # HTTP isteği kesilemez; kritik uyarı yalnız sırada öne geçer (§7.3-3)
        http_gonder(self._adres, anahtar, metin, self._bicim)


def bolgeleri_sec(bolgeler: list[dict], kamera_alani: str | None) -> list[dict]:
    """Olayın duyurulacağı kanallar - seçim kuralının TEK yeri (docs/17 §7.3-1).

    Kameranın bölümündeki BÜTÜN açık kanallar (bir bölümde ses çıkışı ve IP
    hoparlör birlikte olabilir); bölümde kanal yoksa "Tüm fabrika" (area boş)
    açık kanalları. İkisi de yoksa boş liste: ses çalmaz.

    Modül düzeyinde ve saf: Anons ekranı "bu kamera hangi hoparlöre bağlı"
    yazarken de bunu çağırır. İki ayrı seçim kodu olsaydı ekran bir hoparlörü
    gösterip anons başka hoparlörden çalabilirdi.
    """
    alan = (kamera_alani or "").strip()
    acik = [b for b in bolgeler if b.get("enabled")]
    if alan:
        bolumdekiler = [b for b in acik if (b.get("area") or "").strip() == alan]
        if bolumdekiler:
            return bolumdekiler
    return [b for b in acik if not (b.get("area") or "").strip()]


def bolge_sec(bolgeler: list[dict], kamera_alani: str | None) -> dict | None:
    """Seçilen kanallardan ilki (tek hoparlör adı yazan eski ekranlar için)."""
    secilenler = bolgeleri_sec(bolgeler, kamera_alani)
    return secilenler[0] if secilenler else None


def kanal_anonscu(kanal: dict, http_bicimi: str = "json"):
    """Kanal satırından adaptör: ses çıkışı ya da IP hoparlör.

    HTTP biçimi .env'de tek yerde durur (ANONS_HTTP_BICIMI): fabrikadaki
    hoparlörler aynı marka olur; kanal başına biçim, öğrenilecek ikinci bir
    kavram olurdu.
    """
    if kanal.get("kind") == "ses_karti":
        return SesKartiAnonscu(kanal.get("device") or "")
    return HttpAnonscu(kanal.get("address") or "", http_bicimi)


def cikis_anahtari(kanal: dict) -> tuple:
    """Kanalın ÇIKIŞI: aynı çıkışı gösteren iki satır tek işçiyi paylaşır ki
    aynı hoparlörde iki ses üst üste binmesin (docs/17 §7.3-2)."""
    if kanal.get("kind") == "ses_karti":
        return ("ses_karti", (kanal.get("device") or "").strip())
    return ("http", (kanal.get("address") or "").strip())


def _cikislara_gore_tekille(kanallar: list[dict]) -> list[dict]:
    """Aynı çıkışa giden ikinci satır aynı sesi ikinci kez çaldırmasın."""
    gorulen: set[tuple] = set()
    tekil = []
    for kanal in kanallar:
        anahtar = cikis_anahtari(kanal)
        if anahtar not in gorulen:
            gorulen.add(anahtar)
            tekil.append(kanal)
    return tekil


@dataclass(frozen=True)
class OlayBilgisi:
    """Uyarının ait olduğu olay: öncelik, bastırma ve teslim kaydı için."""

    olay_id: int | None = None  # None: olay satırı YAZILAMADI (fail-safe) ya da yok
    kod: str | None = None
    onem: str = "medium"
    asama: str = ASAMA_ACILDI
    kare_zamani: float | None = None  # kare yakalama anı (time.monotonic)


class _Dagitim:
    """Bir olayın bütün sesli/uzak kanal denemelerini toplar (garanti, §7.4-a).

    Denemelerin hepsi bitince olay "ulaştı" (en az biri çaldı ya da az önce
    zaten duyurulduğu için bastırıldı) ya da "ulaşmadı" sayılır. Bayat, kesilen
    ve başarısız deneme ulaşmış sayılmaz; ekran bu garantiye hiç girmez.
    """

    def __init__(self, yonetici: AnonsYoneticisi, olay: OlayBilgisi, kamera_id, beklenen: int):
        self._yonetici = yonetici
        self.olay = olay
        self.kamera_id = kamera_id
        self._kalan = beklenen
        self._ulasti = False
        self._kilit = threading.Lock()

    def sonuc(self, sonuc: str) -> None:
        with self._kilit:
            if sonuc in (SONUC_TAMAM, SONUC_BASTIRILDI):
                self._ulasti = True
            self._kalan -= 1
            if self._kalan != 0:
                return
            ulasti = self._ulasti
        self._yonetici._dagitim_bitti(self, ulasti)


class AnonsYoneticisi:
    """Uyarıyı kanallara dağıtır (docs/17 §7.3).

    Olay, kameranın bölümündeki bütün açık kanallara (yoksa "Tüm fabrika"
    kanallarına) gider. Her ÇIKIŞIN tek işçisi ve öncelikli kuyruğu vardır
    (olaylar/dagitici.py): analiz iş parçacığı hiçbir sesi ya da HTTP isteğini
    BEKLEMEZ; bir hoparlörün 5 saniyelik zaman aşımı fabrikanın izlenmemesine
    yol açmaz.

    Tekrar bastırması (kamera, mesaj, kanal) başınadır ve YALNIZ başarılı
    çalmada tüketilir (R20): çalamayan bir hoparlör, bir sonraki ihlalde yeniden
    denenir. Kritik bir olayın AÇILIŞI bastırılmaz: aynı kamerada ikinci, ayrı
    bir araç-yaya yakınlığı sesli duyurulmadan kalmamalı. Bastırılan deneme
    `suppressed_cooldown` diye iz bırakır. Her deneme `alert_deliveries`'e
    yazılır (olaylar/teslim.py).
    """

    def __init__(self, ayarlar: Ayarlar) -> None:
        self._http_bicimi = ayarlar.anons_http_bicimi
        self._bekleme_sn = ayarlar.anons_bekleme_sn
        self._goruntu_koku = ayarlar.kok_dizin
        self._veritabani_yolu = ayarlar.veritabani_yolu
        self._cooldown = Cooldown()
        self._bastirma_kilidi = threading.Lock()
        # Kuyrukta ya da çalmakta olan bastırma anahtarları: aynı uyarı
        # sonucu belli olmadan ikinci kez sıraya girmesin
        self._yoldakiler: set[tuple] = set()
        # Kanal satırları (speaker_zones, dict). Süpervizör yapılandırma her
        # değiştiğinde yeniler; yeniden başlatma gerekmez.
        self._bolgeler: list[dict] = []
        self._iscilar: dict[tuple, CikisIscisi] = {}
        self._iscilar_kilidi = threading.Lock()
        self._kayit = TeslimKaydedici(ayarlar.veritabani_yolu)
        self._kapandi = False
        self.son_sonuc: str = "Henüz anons denenmedi."
        # Kanal sağlığı (docs/17 §7.4): "anons-saglik" iş parçacığı doldurur
        self._saglik_araligi = float(ayarlar.anons_saglik_araligi_sn)
        self._kopuk_esigi = float(ayarlar.anons_kopuk_esigi_sn)
        self._haller: dict[int, KanalHali] = {}
        self._haller_kilidi = threading.Lock()
        self._saglik_is: threading.Thread | None = None
        self._saglik_dur = threading.Event()
        # Kanal listesi değişince beklemeden yoklansın (yeni kanal "denetleniyor"da kalmasın)
        self._saglik_uyandir = threading.Event()
        # Son yoklamanın çıkış listesi: Bluetooth hoparlör yeniden bağlanınca
        # adı (profil soneki) değişirse çalma bugünkü ada yapılır (§7.5-2)
        self._son_cihazlar: list[ses_cihazlari.SesCihazi] = []
        # Garanti (§7.4-a): son uyarı hiçbir sesli kanala ulaşmadıysa True;
        # /saglik "uyari_ulasmiyor". Sonraki ulaşan uyarı ya da başarılı bir
        # kanal denemesi siler.
        self.ulasmiyor = False
        self._ulasmayan_araligi = float(ayarlar.ulasmayan_uyari_araligi_sn)
        self._ulasmayan_son: dict = {}
        self._ulasmayan_birikim: dict = {}
        self._ulasmayan_kilidi = threading.Lock()

    @property
    def ad(self) -> str:
        """Ana sayfadaki kısa durum: kaç açık sesli kanal var."""
        return kanal_ozeti(sum(1 for b in self._bolgeler if b.get("enabled")))

    def bolgeleri_yukle(self, satirlar) -> None:
        """Kanal satırlarını tazeler (speaker_zones) ve sağlık yoklamasını uyandırır:
        eklenen ya da değişen kanal 10 sn "denetleniyor"da beklemesin."""
        self._bolgeler = [dict(satir) for satir in satirlar]
        self._saglik_uyandir.set()

    def bolge_sec(self, kamera_alani: str | None) -> dict | None:
        """İhlalin olduğu bölümün ilk kanalı (bkz. modül düzeyindeki bolge_sec)."""
        return bolge_sec(self._bolgeler, kamera_alani)

    # ------------------------------------------------------------ duyurma

    def duyur(
        self,
        kamera_id: int,
        kamera_alani: str | None,
        zaman_s: float,
        mesaj: dict | None,
        *,
        olay: OlayBilgisi | None = None,
    ) -> None:
        """Olayı kanallara sıraya koyar ve HEMEN döner.

        mesaj: announcement_messages satırı (dict) veya None. zaman_s: bastırma
        saati (çağıranın saati; süpervizörde time.monotonic).
        """
        if mesaj is None or not mesaj.get("enabled", 1):
            return
        olay = olay or OlayBilgisi()
        anahtar, metin = mesaj.get("key", ""), mesaj.get("text", "")
        hedefler, atlananlar = self._hedefleri_sec(kamera_alani)
        kanallar = _cikislara_gore_tekille(hedefler)
        # Garanti yalnız olayın AÇILIŞINDA aranır; hatırlatma aynı olaydır
        garanti = olay.asama == ASAMA_ACILDI
        if not kanallar:
            # Kanal yoksa ses çalmaz; bu bir hata değil, kurulum eksiğidir
            self._cal_ve_kaydet(anahtar, metin, None)
            if garanti:
                self._ulasmadi(olay, kamera_id, "sesli kanal tanımlı değil")
            return
        for kanal in atlananlar:
            self._teslimi_kaydet(
                UyariOgesi(
                    kanal=dict(kanal),
                    anahtar=anahtar,
                    metin=metin,
                    onem=olay.onem,
                    asama=olay.asama,
                    olay_id=olay.olay_id,
                    olay_kodu=olay.kod,
                    sonuc=SONUC_GERI_DUSUS,
                    ayrinti="bölüm kanalı koptu; uyarı “Tüm fabrika” kanalından duyuruldu",
                )
            )
        grup = _Dagitim(self, olay, kamera_id, len(kanallar)) if garanti else None
        ses_yolu, ses_hatasi = self._ses_yolu(mesaj)
        # Kritik olayın açılışı bastırmadan muaftır (docs/17 §7.3-7a)
        muaf = olay.onem == "critical" and olay.asama == ASAMA_ACILDI
        for kanal in kanallar:
            oge = UyariOgesi(
                kanal=dict(kanal),
                anahtar=anahtar,
                metin=metin,
                ses_yolu=ses_yolu,
                ses_hatasi=ses_hatasi,
                onem=olay.onem,
                asama=olay.asama,
                olay_id=olay.olay_id,
                olay_kodu=olay.kod,
                kamera_id=kamera_id,
                kare_zamani=olay.kare_zamani,
                grup=grup,
            )
            bastirma = ("anons", kamera_id, mesaj.get("id"), kanal.get("id"))
            with self._bastirma_kilidi:
                # Muaf olan (kritik açılış) denetlenmez ama başarılı çalınca
                # bastırmayı yine başlatır: arkasından gelen aynı uyarı susar.
                bastirildi = not muaf and (
                    bastirma in self._yoldakiler
                    or self._cooldown.bekliyor_mu(bastirma, zaman_s, float(self._bekleme_sn))
                )
                if not bastirildi:
                    self._yoldakiler.add(bastirma)
            if bastirildi:
                oge.sonuc = SONUC_BASTIRILDI
                oge.ayrinti = (
                    f"aynı kamera ve mesaj bu kanaldan son {self._bekleme_sn} sn "
                    "içinde duyuruldu ya da sırada"
                )
                self._teslimi_kaydet(oge)
                if grup is not None:
                    grup.sonuc(SONUC_BASTIRILDI)
                continue
            oge.bastirma, oge.bastirma_zamani = bastirma, zaman_s
            self._siraya_koy(oge)

    def golge_kaydet(
        self,
        kamera_id: int,
        kamera_alani: str | None,
        mesaj: dict | None,
        *,
        olay: OlayBilgisi | None = None,
    ) -> None:
        """Gölge moddaki kural: ses ÇALMAZ; "çalsaydı" hangi kanallardan
        çalacağı `shadow` diye yazılır (docs/17 §7.3-9)."""
        if mesaj is None or not mesaj.get("enabled", 1):
            return
        olay = olay or OlayBilgisi()
        for kanal in _cikislara_gore_tekille(bolgeleri_sec(self._bolgeler, kamera_alani)):
            oge = UyariOgesi(
                kanal=dict(kanal),
                anahtar=mesaj.get("key", ""),
                metin=mesaj.get("text", ""),
                onem=olay.onem,
                asama=olay.asama,
                olay_id=olay.olay_id,
                olay_kodu=olay.kod,
                kamera_id=kamera_id,
                sonuc=SONUC_GOLGE,
                ayrinti="kural gölge modda: anons çalınmadı",
            )
            self._teslimi_kaydet(oge)

    def ekran_kaydet(self, olay: OlayBilgisi) -> None:
        """Ekran kanalı: açık izleme ekranı var mıydı (bilgi; garantiye sayılmaz)."""
        sayi = ekran.istemci_sayisi()
        self._kayit.teslim(
            teslim_satiri(
                kanal="ekran",
                asama=olay.asama,
                sonuc=SONUC_TAMAM if sayi else SONUC_DINLEYEN_YOK,
                kuyruga_giris_utc=zaman.simdi_utc(),
                olay_id=olay.olay_id,
                olay_kodu=olay.kod,
                ayrinti=f"{sayi} izleme ekranı açık",
            )
        )

    def hemen_cal(self, mesaj: dict, bolge: dict | None = None) -> None:
        """Bastırmasız çalar. Kanal verilmezse "Tüm fabrika" kanallarından
        (arayüzdeki 'Anonsu Dene' düğmesi). Deneme gerçek uyarının önüne geçmez."""
        kanallar = [bolge] if bolge is not None else bolgeleri_sec(self._bolgeler, "")
        if not kanallar and any(k.get("enabled") for k in self._bolgeler):
            # Kanal VAR ama hepsi bir bölüme bağlı: "sesli kanal yok" demek yanlış olurdu
            self.son_sonuc = (
                "Mesaj denenemedi: deneme “Tüm fabrika” kanallarından çalar ve açık bir "
                "“Tüm fabrika” kanalı yok. Bölüm kanallarını kanal listesindeki Dene "
                "düğmesiyle sınayın."
            )
            return
        if not kanallar:
            self._cal_ve_kaydet(mesaj.get("key", ""), mesaj.get("text", ""), None)
            return
        ses_yolu, ses_hatasi = self._ses_yolu(mesaj)
        for kanal in _cikislara_gore_tekille(kanallar):
            self._siraya_koy(
                UyariOgesi(
                    kanal=dict(kanal),
                    anahtar=mesaj.get("key", ""),
                    metin=mesaj.get("text", ""),
                    ses_yolu=ses_yolu,
                    ses_hatasi=ses_hatasi,
                    onem="low",
                    asama=ASAMA_TEST,
                )
            )

    def kanali_dene(
        self,
        kanal: dict,
        anahtar: str,
        metin: str,
        ses_yolu: str | None,
        zaman_asimi: float = 25.0,
    ) -> tuple[str, str, int | None]:
        """Kanal satırının "Dene"si, çıkışın kuyruğundan geçerek (analiz açıkken
        gerçek uyarıyla üst üste binmesin). Sonucu bekler: (sonuç, ayrıntı,
        kuyruktan başlamaya ms)."""
        oge = UyariOgesi(
            kanal=dict(kanal),
            anahtar=anahtar,
            metin=metin,
            ses_yolu=ses_yolu,
            onem="low",
            asama=ASAMA_TEST,
            bitti=threading.Event(),
        )
        self._siraya_koy(oge)
        if not oge.bitti.wait(zaman_asimi):
            mesgul = "Deneme sırası gelmedi: çıkış meşgul, biraz sonra yineleyin."
            return SONUC_BASARISIZ, mesgul, None
        return oge.sonuc, oge.ayrinti, oge.kuyruktan_baslamaya_ms

    # ------------------------------------------------------------ yaşam döngüsü

    def bosalt(self, zaman_asimi: float = 5.0) -> bool:
        """Bütün kuyruklar ve kayıt boşalana kadar bekler (testler, kapanış)."""
        son = time.monotonic() + zaman_asimi
        with self._iscilar_kilidi:
            iscilar = list(self._iscilar.values())
        bos = all(isci.bosalt(max(0.0, son - time.monotonic())) for isci in iscilar)
        return self._kayit.bosalt(max(0.0, son - time.monotonic())) and bos

    def kapat(self, zaman_asimi: float = 3.0) -> None:
        """Süreç kapanırken kuyrukları en çok `zaman_asimi` sn boşaltır (kritik
        önce; sıra zaten öncelikli), sonra işçileri durdurur (docs/17 §7.3-11)."""
        self._kapandi = True
        self.saglik_durdur(1.0)
        son = time.monotonic() + zaman_asimi
        with self._iscilar_kilidi:
            iscilar = list(self._iscilar.values())
        for isci in iscilar:
            isci.durdur(max(0.0, son - time.monotonic()))
        self._kayit.durdur(max(0.5, son - time.monotonic()))

    # ------------------------------------------------------------ kanal sağlığı

    def saglik_baslat(self) -> None:
        """Kanal sağlığı iş parçacığını ("anons-saglik") başlatır (süpervizör açılırken)."""
        if self._saglik_is is not None:
            return
        self._saglik_dur.clear()
        self._saglik_is = threading.Thread(
            target=self._saglik_dongusu, name="anons-saglik", daemon=True
        )
        self._saglik_is.start()

    def saglik_durdur(self, zaman_asimi: float = 2.0) -> None:
        """Sağlık iş parçacığını durdurur. Süpervizör açık olayları kapatmadan
        ÖNCE çağırır: kapanış kaydından sonra yeni bir "koptu" yazılmasın."""
        self._saglik_dur.set()
        self._saglik_uyandir.set()
        if self._saglik_is is not None:
            self._saglik_is.join(timeout=zaman_asimi)
            self._saglik_is = None

    def kanal_halleri(self) -> dict[int, tuple[str | None, str]]:
        """Kanal id → (kararlaşmış sağlık ok|down|unknown|None, son yoklamanın açıklaması)."""
        with self._haller_kilidi:
            return {kid: (h.saglik, h.aciklama) for kid, h in self._haller.items()}

    def _saglik_dongusu(self) -> None:
        baglanti: sqlite3.Connection | None = None
        try:
            while not self._saglik_dur.is_set():
                try:
                    if baglanti is None:
                        baglanti = veritabani.baglanti_ac(self._veritabani_yolu)
                    self.saglik_turu(baglanti)
                except (sqlite3.Error, OSError) as hata:
                    _log.warning(f"Kanal sağlığı yazılamadı: {hata}")
                    if baglanti is not None:
                        baglanti.close()
                    baglanti = None
                except Exception as hata:  # noqa: BLE001 - yoklama durursa kopma görünmez
                    _log.error(f"Kanal sağlığı yoklanamadı: {hata}", exc_info=hata)
                self._saglik_uyandir.wait(self._saglik_araligi)
                self._saglik_uyandir.clear()
        finally:
            if baglanti is not None:
                baglanti.close()

    def saglik_turu(self, baglanti: sqlite3.Connection, simdi: float | None = None) -> None:
        """Açık kanalları bir kez yoklar, durumları ilerletir, değişeni yazar.

        Kanallar her turda veritabanından okunur: sağlık, analizin yapılandırma
        yüklemesini beklemez ve karşılaştırma sütunun GERÇEK değeriyle yapılır.
        Testler sahte saatle doğrudan çağırır (`simdi`).
        """
        simdi = time.monotonic() if simdi is None else simdi
        kanallar = [
            dict(k)
            for k in baglanti.execute("SELECT * FROM speaker_zones WHERE enabled = 1 ORDER BY id")
        ]
        ses_var = any(k.get("kind") == "ses_karti" for k in kanallar)
        cihazlar = ses_cihazlari.cihazlari_listele() if ses_var and sys.platform != "win32" else []
        self._son_cihazlar = cihazlar
        secim = ses_cihazlari.secim_destekleniyor_mu()
        calici_var = sys.platform == "win32" or _ses_komutu("deneme") is not None
        sunucu = ses_cihazlari.ses_sunucusu_durumu() if ses_var else None
        for kanal in kanallar:
            if self._saglik_dur.is_set():
                return  # kapanış: süpervizörün kapanış kayıtlarından sonra olay yazılmasın
            self._kanali_yokla(baglanti, kanal, cihazlar, secim, calici_var, sunucu, simdi)
        # Silinen ya da kapatılan kanalın açık "koptu" olayı asılı kalmasın
        acik_idler = {int(k["id"]) for k in kanallar}
        with self._haller_kilidi:
            gidenler = [(kid, h) for kid, h in self._haller.items() if kid not in acik_idler]
            for kid, _ in gidenler:
                del self._haller[kid]
        for kid, hali in gidenler:
            if hali.acik_olay is not None:
                olay_kapat(baglanti, hali.acik_olay, "kanal_degisti")
            # Kapatılan kanalın eski kararı, yeniden açılınca bayat görünmesin
            baglanti.execute(
                "UPDATE speaker_zones SET health = NULL, health_changed_at = ? WHERE id = ?",
                (zaman.simdi_utc(), kid),
            )
            baglanti.commit()

    def _kanali_yokla(
        self,
        baglanti: sqlite3.Connection,
        kanal: dict,
        cihazlar: list[ses_cihazlari.SesCihazi],
        secim: bool,
        calici_var: bool,
        sunucu: bool | None,
        simdi: float,
    ) -> None:
        kid = int(kanal["id"])
        imza = kanal_imzasi(kanal)
        with self._haller_kilidi:
            hali = self._haller.get(kid)
            eski = hali if hali is not None and hali.imza != imza else None
            if hali is None or eski is not None:
                # İlk yoklama sütundaki son karardan başlar (açılışta ekran ve
                # /saglik boşa düşmesin); çıkışı ya da adresi değişen kanalın
                # eski kararı ise geçersizdir
                hali = KanalHali(imza=imza, saglik=None if eski else kanal.get("health"))
                self._haller[kid] = hali
        if eski is not None and eski.acik_olay is not None:
            olay_kapat(baglanti, eski.acik_olay, "kanal_degisti")
        sonuc, aciklama = kanal_yokla(
            kanal,
            cihazlar,
            secim=secim,
            calici_var=calici_var,
            adres_dogrula=hoparlor_adresini_dogrula,
            ses_sunucusu=sunucu,
        )
        with self._haller_kilidi:
            kod = ilerle(hali, sonuc, simdi, self._kopuk_esigi)
            hali.aciklama = aciklama
            yeni = hali.saglik
        if yeni != kanal.get("health"):
            # updated_at'e DOKUNULMAZ: yapılandırma damgası her yoklamada
            # değişip süpervizör kanalları boş yere yeniden yüklemesin
            baglanti.execute(
                "UPDATE speaker_zones SET health = ?, health_changed_at = ? WHERE id = ?",
                (yeni, zaman.simdi_utc(), kid),
            )
            baglanti.commit()
        if kod is not None:
            self._saglik_olayi(baglanti, kanal, hali, kod, aciklama)

    def _saglik_olayi(
        self, baglanti: sqlite3.Connection, kanal: dict, hali: KanalHali, kod: str, aciklama: str
    ) -> None:
        ad = kanal.get("name", "")
        detay = {"kanal_id": kanal["id"], "kanal": ad, "tur": kanal.get("kind"), "sebep": aciklama}
        if kod == KOD_KOPTU:
            _log.error(f"Ses kanalı koptu: {ad} ({aciklama})")
            hali.acik_olay = sistem_olayi_yaz(
                baglanti,
                f"Ses kanalı koptu: {ad}. {aciklama}. Bu kanaldan anons duyulmaz; "
                "bölümün başka kanalı ya da “Tüm fabrika” kanalı kullanılır.",
                None,
                detay,
                kod="AUDIO_CHANNEL_DOWN",
            )
            return
        _log.info(f"Ses kanalı tekrar bağlandı: {ad}")
        if hali.acik_olay is not None:
            olay_kapat(baglanti, hali.acik_olay, "kosul_bitti")
            hali.acik_olay = None
        sistem_olayi_yaz(
            baglanti, f"Ses kanalı tekrar bağlandı: {ad}.", None, detay, kod="AUDIO_CHANNEL_UP"
        )

    def _koptu_mu(self, kanal: dict) -> bool:
        hali = self._haller.get(kanal.get("id"))
        return hali is not None and hali.hal == HAL_KOPTU

    def _hedefleri_sec(self, kamera_alani: str | None) -> tuple[list[dict], list[dict]]:
        """(çalınacak kanallar, geri düşüldüğü için atlanan bölüm kanalları).

        Seçim `bolgeleri_sec` ile aynıdır, yalnız KOPTU kanalı atlar: bölümde
        sağlıklı kanal kalmadıysa geri düşüş "Tüm fabrika"dır (docs/17 §7.3-1).
        Her şey kopuksa yine denenir: belki şimdi bağlanmıştır; sonuç kayda düşer.
        """
        alan = (kamera_alani or "").strip()
        acik = [b for b in self._bolgeler if b.get("enabled")]
        bolum = [b for b in acik if alan and (b.get("area") or "").strip() == alan]
        genel = [b for b in acik if not (b.get("area") or "").strip()]
        genel_saglikli = [b for b in genel if not self._koptu_mu(b)]
        if bolum:
            saglikli = [b for b in bolum if not self._koptu_mu(b)]
            if saglikli:
                return saglikli, []
            if genel_saglikli:
                return genel_saglikli, bolum
            return bolum, []
        return (genel_saglikli or genel), []

    # ------------------------------------------------------------ garanti

    def _dagitim_bitti(self, grup: _Dagitim, ulasti: bool) -> None:
        if ulasti:
            self.ulasmiyor = False
            return
        self._ulasmadi(grup.olay, grup.kamera_id, "hiçbir sesli kanal çalamadı")

    def _ulasmadi(self, olay: OlayBilgisi, kamera_id, sebep: str) -> None:
        """Gölgede olmayan olay hiçbir sesli/uzak kanala ulaşmadı (§7.4-a):
        CRITICAL günlük, /saglik "uyari_ulasmiyor" ve aynı kamera için en çok
        ULASMAYAN_UYARI_ARALIGI_SN'de bir ALERT_UNDELIVERED; aradakiler sayılır."""
        self.ulasmiyor = True
        tanim = OLAY_KODLARI.get(olay.kod or "")
        ad = tanim.ad if tanim else "İhlal"
        _log.critical(
            f"Uyarı hiçbir sesli kanala ulaşamadı: {ad} (kamera {kamera_id}, olay "
            f"{olay.olay_id}) - {sebep}"
        )
        simdi = time.monotonic()
        with self._ulasmayan_kilidi:
            son = self._ulasmayan_son.get(kamera_id)
            if son is not None and simdi - son < self._ulasmayan_araligi:
                self._ulasmayan_birikim[kamera_id] = self._ulasmayan_birikim.get(kamera_id, 0) + 1
                return
            arada = self._ulasmayan_birikim.pop(kamera_id, 0)
            self._ulasmayan_son[kamera_id] = simdi
        mesaj = f"Uyarı hiçbir sesli kanala ulaşamadı: {ad} - {sebep}."
        if arada:
            mesaj += f" Önceki kayıttan bu yana {arada} uyarı daha ulaşamadı."
        self._kayit.ulasmayan_uyari(
            mesaj,
            kamera_id,
            {
                "olay_id": olay.olay_id,
                "olay_kodu": olay.kod,
                "arada_ulasmayan": arada,
                "sebep": sebep,
            },
        )

    def kuyruk_durumu(self) -> dict[str, int]:
        """Çıkış başına bekleyen öğe sayısı (sağlık ayrıntısı için)."""
        with self._iscilar_kilidi:
            return {isci.ad: isci.bekleyen for isci in self._iscilar.values()}

    # ------------------------------------------------------------ iç işler

    def _ses_yolu(self, mesaj: dict) -> tuple[str | None, str]:
        """Mesajın WAV yolu (proje köküne göre) ve kullanılamıyorsa sebebi.

        Yol her çalışta yeniden doğrulanır: veritabanı başka bir yoldan
        düzenlenmiş ya da sürücü harfli mutlak bir değer girmiş olabilir.
        Sebep yalnız ses çıkışı kanalını durdurur; IP hoparlöre metin gider.
        """
        ses = mesaj.get("audio_file")
        if not ses:
            return None, ""
        kok = self._goruntu_koku.resolve()
        tam = (kok / ses).resolve()
        if not tam.is_relative_to(kok):
            _log.error(f"Anons ses dosyası proje klasörünün dışında, çalınmadı: {ses}")
            return None, f"Ses dosyası proje klasörünün dışında: {ses}"
        return str(tam), ""

    def _siraya_koy(self, oge: UyariOgesi) -> None:
        if self._kapandi:
            oge.sonuc, oge.ayrinti = SONUC_BASARISIZ, "sistem kapanıyordu"
            self._bitince(oge)
            if oge.bitti is not None:
                oge.bitti.set()
            return
        self._isci(oge.kanal).ekle(oge)

    def _isci(self, kanal: dict) -> CikisIscisi:
        anahtar = cikis_anahtari(kanal)
        with self._iscilar_kilidi:
            isci = self._iscilar.get(anahtar)
            if isci is None:
                durdurucu = (
                    _windows_durdur
                    if sys.platform == "win32" and anahtar[0] == "ses_karti"
                    else None
                )
                isci = CikisIscisi(
                    ad=f"{anahtar[0]}-{len(self._iscilar) + 1}",
                    isle=self._isle,
                    bitince=self._bitince,
                    bekleme_sn=float(self._bekleme_sn),
                    durdurucu=durdurucu,
                )
                self._iscilar[anahtar] = isci
        return isci

    def _isle(self, oge: UyariOgesi, kes: threading.Event) -> None:
        """Çıkış işçisinin çağırdığı: çal ve sonucu öğeye yaz."""
        oge.baslama = time.monotonic()
        oge.baslama_utc = zaman.simdi_utc()
        if oge.ses_hatasi and oge.kanal.get("kind") == "ses_karti":
            oge.sonuc, oge.ayrinti = SONUC_BASARISIZ, oge.ses_hatasi
            nereye = oge.kanal.get("name", "")
            self.son_sonuc = f"Son anons ÇALINAMADI ({nereye}) - {oge.ses_hatasi}"
        else:
            kanal = oge.kanal
            if kanal.get("kind") == "ses_karti" and kanal.get("device") and self._son_cihazlar:
                # Bluetooth hoparlör yeniden bağlanınca sink adının profil soneki
                # değişebilir; aynı adresli sink'in bugünkü adına çalınır (§7.5-2)
                kanal = {
                    **kanal,
                    "device": ses_cihazlari.guncel_cikis(kanal["device"], self._son_cihazlar),
                }
            oge.sonuc, oge.ayrinti = self._cal_ve_kaydet(
                oge.anahtar, oge.metin, oge.ses_yolu, kanal, kes=kes
            )
        oge.bitis_utc = zaman.simdi_utc()

    def _bitince(self, oge: UyariOgesi) -> None:
        """Öğe bitti (çaldı, çalamadı, kesildi ya da bayat): bastırma, kayıt."""
        if oge.bastirma is not None:
            with self._bastirma_kilidi:
                self._yoldakiler.discard(oge.bastirma)
                # Bastırma YALNIZ başarıda tüketilir (R20)
                if oge.sonuc == SONUC_TAMAM:
                    self._cooldown.kaydet(oge.bastirma, oge.bastirma_zamani)
        if oge.sonuc == SONUC_TAMAM and oge.kanal.get("id") is not None:
            self._son_anonsu_yaz(int(oge.kanal["id"]))
            if oge.asama == ASAMA_TEST:
                self.ulasmiyor = False  # kanal sınandı ve çaldı
        self._teslimi_kaydet(oge)
        if oge.grup is not None:
            oge.grup.sonuc(oge.sonuc)

    def _teslimi_kaydet(self, oge: UyariOgesi) -> None:
        self._kayit.teslim(
            teslim_satiri(
                kanal=oge.kanal.get("kind") or "http",
                asama=oge.asama,
                sonuc=oge.sonuc,
                kuyruga_giris_utc=oge.kuyruga_giris_utc,
                olay_id=oge.olay_id,
                olay_kodu=oge.olay_kodu,
                kanal_id=oge.kanal.get("id"),
                ayrinti=oge.ayrinti,
                baslama_utc=oge.baslama_utc,
                bitis_utc=oge.bitis_utc,
                kareden_baslamaya_ms=oge.kareden_baslamaya_ms,
            )
        )

    def _hedef_anonscu(self, bolge: dict):
        """Kanal satırının adaptörü (HTTP biçimi .env'den, tek yerde)."""
        return kanal_anonscu(bolge, self._http_bicimi)

    def _cal_ve_kaydet(
        self,
        anahtar: str,
        metin: str,
        ses_yolu: str | None,
        bolge: dict | None = None,
        *,
        kes: threading.Event | None = None,
    ) -> tuple[str, str]:
        """Tek kanalda eşzamanlı çalar, `son_sonuc`u yazar; (sonuç, ayrıntı) döner."""
        if bolge is None:
            # Kanal yoksa ses çalmaz; bu bir hata değil, kurulum eksiğidir
            self.son_sonuc = (
                "Son anons ÇALINAMADI - sesli kanal tanımlı değil. Anons sayfasından bir "
                "ses çıkışı ya da IP hoparlör ekleyin; o zamana kadar yalnızca ekran uyarısı "
                "verilir."
            )
            _log.info(f"Anons çalınmadı (sesli kanal yok): {metin}")
            return SONUC_BASARISIZ, "sesli kanal tanımlı değil"
        nereye = f" ({bolge.get('name', '')})"
        try:
            self._hedef_anonscu(bolge).cal(anahtar, metin, ses_yolu, kes=kes)
        except AnonsKesildi as hata:
            self.son_sonuc = f"Son anons KESİLDİ{nereye}: {hata}"
            _log.info(f"Anons kesildi{nereye}: {metin}")
            return SONUC_KESILDI, str(hata)
        except AnonsHatasi as hata:
            # Bilinen sebep: kullanıcıya olduğu gibi göster
            self.son_sonuc = f"Son anons ÇALINAMADI{nereye} - {hata}"
            _log.error(f"Anons çalınamadı: {hata}")
            return SONUC_BASARISIZ, str(hata)
        except Exception as hata:  # noqa: BLE001 - anons hatası sistemi durdurmaz
            self.son_sonuc = f"Son anons ÇALINAMADI{nereye} - beklenmeyen hata: {hata}"
            _log.error(f"Anons çalınamadı: {hata}", exc_info=hata)
            return SONUC_BASARISIZ, f"beklenmeyen hata: {hata}"
        self.son_sonuc = f"Son anons ÇALINDI{nereye}: {metin}"
        return SONUC_TAMAM, ""

    def _son_anonsu_yaz(self, bolge_id: int) -> None:
        """Kanalın 'son anons' damgası; kayıt iş parçacığı yazar. Yazılamazsa
        anons yine çalmıştır: ekrandaki bilgi eksik kalır, sistem durmaz."""
        self._kayit.son_anons(bolge_id, zaman.simdi_utc())

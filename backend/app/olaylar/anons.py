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
import urllib.error
import urllib.parse
import urllib.request

from app import veritabani, zaman
from app.ayarlar import Ayarlar
from app.loglama import adres_maskele, log_al
from app.olaylar.kanallar import kanal_ozeti
from app.rules.cooldown import Cooldown

_log = log_al("anons")


class AnonsHatasi(Exception):
    """Ses çalınamadı - sebebi Anons sayfasında gösterilir."""


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

    def cal(self, anahtar: str, metin: str, ses_dosyasi: str | None) -> None:
        if not self._kullanilabilir:
            raise AnonsHatasi("Bu bilgisayarda ses çalma komutu bulunamadı (afplay/aplay/paplay).")
        if not ses_dosyasi:
            raise AnonsHatasi(
                f"'{anahtar}' mesajına ses dosyası bağlanmamış. Anons sayfasında "
                "bir .wav dosyasının yolunu yazın; yoksa yalnızca ekran uyarısı verilir."
            )
        if sys.platform == "win32":
            _windows_cal(ses_dosyasi)
            _log.info(f"Anons çalındı: {metin}")
            return
        komut = _ses_komutu(ses_dosyasi, self.cihaz)
        if komut is None:
            raise AnonsHatasi(f"Ses çalma komutu bulunamadı: {ses_dosyasi}")
        # Bu çağrı zaten ayrı bir iş parçacığındadır (AnonsYoneticisi), bu
        # yüzden sonucu BEKLEYEBİLİRİZ. Beklemezsek komut hemen başarısız olsa
        # bile "gönderildi" yazardı ve 'Anonsu Dene' düğmesi yalan söylerdi.
        try:
            sonuc = subprocess.run(komut, capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as hata:
            raise AnonsHatasi(f"Ses çalınamadı ({ses_dosyasi}): {hata}") from hata
        if sonuc.returncode != 0:
            ayrinti = (sonuc.stderr or b"").decode("utf-8", "replace").strip()[:200]
            raise AnonsHatasi(
                f"Ses çalınamadı ({ses_dosyasi}). "
                + (f"Sebep: {ayrinti}" if ayrinti else "Dosya biçimi desteklenmiyor olabilir.")
            )
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

    def cal(self, anahtar: str, metin: str, ses_dosyasi: str | None) -> None:
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


class AnonsYoneticisi:
    """Anons cooldown'unu uygular ve mesajı kanallara iletir.

    Anons çağrısı HER ZAMAN ayrı bir iş parçacığında yapılır: HTTP anons
    sunucusu kapalıysa urlopen 5 saniye bekler ve o süre boyunca TEK analiz
    iş parçacığı durduğu için TÜM kameralar kör kalırdı. Bir hoparlörün
    gecikmesi, fabrikanın izlenmemesine yol açmamalı.
    """

    def __init__(self, ayarlar: Ayarlar) -> None:
        self._http_bicimi = ayarlar.anons_http_bicimi
        self._bekleme_sn = ayarlar.anons_bekleme_sn
        self._goruntu_koku = ayarlar.kok_dizin
        self._veritabani_yolu = ayarlar.veritabani_yolu
        self._cooldown = Cooldown()
        # Kanal satırları (speaker_zones, dict). Süpervizör yapılandırma her
        # değiştiğinde yeniler; yeniden başlatma gerekmez.
        self._bolgeler: list[dict] = []
        self.son_sonuc: str = "Henüz anons denenmedi."

    @property
    def ad(self) -> str:
        """Ana sayfadaki kısa durum: kaç açık sesli kanal var."""
        return kanal_ozeti(sum(1 for b in self._bolgeler if b.get("enabled")))

    def bolgeleri_yukle(self, satirlar) -> None:
        """Kanal satırlarını tazeler (speaker_zones)."""
        self._bolgeler = [dict(satir) for satir in satirlar]

    def bolge_sec(self, kamera_alani: str | None) -> dict | None:
        """İhlalin olduğu bölümün ilk kanalı (bkz. modül düzeyindeki bolge_sec)."""
        return bolge_sec(self._bolgeler, kamera_alani)

    def duyur(
        self, kamera_id: int, kamera_alani: str | None, zaman_s: float, mesaj: dict | None
    ) -> None:
        """mesaj: announcement_messages satırı (dict) veya None."""
        if mesaj is None or not mesaj.get("enabled", 1):
            return
        anahtar = ("anons", kamera_id, mesaj["id"])
        if not self._cooldown.izinli_mi(anahtar, zaman_s, float(self._bekleme_sn)):
            return
        kanallar = bolgeleri_sec(self._bolgeler, kamera_alani)
        for kanal in kanallar or [None]:
            self.hemen_cal(mesaj, kanal)

    def hemen_cal(self, mesaj: dict, bolge: dict | None = None) -> None:
        """Cooldown'suz çalar. Kanal verilmezse "Tüm fabrika" kanallarından
        (arayüzdeki 'Anonsu Dene' düğmesi bunu kullanır)."""
        ses = mesaj.get("audio_file")
        ses_yolu = None
        if ses:
            # Yol her çalışta yeniden doğrulanır: veritabanı başka bir yoldan
            # düzenlenmiş ya da sürücü harfli mutlak bir değer girmiş olabilir.
            kok = self._goruntu_koku.resolve()
            tam = (kok / ses).resolve()
            if not tam.is_relative_to(kok):
                _log.error(f"Anons ses dosyası proje klasörünün dışında, çalınmadı: {ses}")
                return
            ses_yolu = str(tam)
        kanallar = [bolge] if bolge is not None else bolgeleri_sec(self._bolgeler, "")
        if not kanallar and any(k.get("enabled") for k in self._bolgeler):
            # Kanal VAR ama hepsi bir bölüme bağlı: "sesli kanal yok" demek yanlış olurdu
            self.son_sonuc = (
                "Mesaj denenemedi: deneme “Tüm fabrika” kanallarından çalar ve açık bir "
                "“Tüm fabrika” kanalı yok. Bölüm kanallarını kanal listesindeki Dene "
                "düğmesiyle sınayın."
            )
            return
        for kanal in kanallar or [None]:
            threading.Thread(
                target=self._cal_ve_kaydet,
                args=(mesaj.get("key", ""), mesaj.get("text", ""), ses_yolu, kanal),
                name="anons",
                daemon=True,
            ).start()

    def _hedef_anonscu(self, bolge: dict):
        """Kanal satırının adaptörü (HTTP biçimi .env'den, tek yerde)."""
        return kanal_anonscu(bolge, self._http_bicimi)

    def _cal_ve_kaydet(
        self, anahtar: str, metin: str, ses_yolu: str | None, bolge: dict | None = None
    ) -> None:
        if bolge is None:
            # Kanal yoksa ses çalmaz; bu bir hata değil, kurulum eksiğidir
            self.son_sonuc = (
                "Son anons ÇALINAMADI - sesli kanal tanımlı değil. Anons sayfasından bir "
                "ses çıkışı ya da IP hoparlör ekleyin; o zamana kadar yalnızca ekran uyarısı "
                "verilir."
            )
            _log.info(f"Anons çalınmadı (sesli kanal yok): {metin}")
            return
        nereye = f" ({bolge.get('name', '')})"
        try:
            self._hedef_anonscu(bolge).cal(anahtar, metin, ses_yolu)
            self.son_sonuc = f"Son anons ÇALINDI{nereye}: {metin}"
            if bolge.get("id") is not None:
                self._son_anonsu_yaz(int(bolge["id"]))
        except AnonsHatasi as hata:
            # Bilinen sebep: kullanıcıya olduğu gibi göster
            self.son_sonuc = f"Son anons ÇALINAMADI{nereye} - {hata}"
            _log.error(f"Anons çalınamadı: {hata}")
        except Exception as hata:  # noqa: BLE001 - anons hatası sistemi durdurmaz
            self.son_sonuc = f"Son anons ÇALINAMADI{nereye} - beklenmeyen hata: {hata}"
            _log.error(f"Anons çalınamadı: {hata}", exc_info=hata)

    def _son_anonsu_yaz(self, bolge_id: int) -> None:
        """Bölgenin 'son anons' damgasını günceller.

        Anons ayrı bir iş parçacığında çalıştığı için burada KENDİ kısa ömürlü
        bağlantısı açılır; süpervizörün bağlantısı başka bir iş parçacığına
        aittir ve paylaşılamaz. Yazma başarısız olursa anons yine çalmıştır:
        ekrandaki "son anons" bilgisi eksik kalır, sistem durmaz.
        """
        try:
            baglanti = veritabani.baglanti_ac(self._veritabani_yolu)
            try:
                baglanti.execute(
                    "UPDATE speaker_zones SET last_announced_at = ? WHERE id = ?",
                    (zaman.simdi_utc(), bolge_id),
                )
                baglanti.commit()
            finally:
                baglanti.close()
        except (sqlite3.Error, OSError) as hata:
            _log.error(f"Hoparlör bölgesinin son anons zamanı yazılamadı ({bolge_id}): {hata}")

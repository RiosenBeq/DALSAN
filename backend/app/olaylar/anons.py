"""Anons adaptörü (docs/02 §7): Null / Ses kartı / HTTP.

Seçim .env'deki ANONS ayarıyla yapılır: null | ses_karti | http.
Anons cooldown'u ekran uyarısından BAĞIMSIZ ve daha uzundur — ekranda 3 olay
görünmesi sorun değil; hoparlörün 3 kez bağırması sorundur (docs/03 §4).

Anons altyapısı yoksa (ANONS=null) sistem bundan tamamen bağımsız çalışır (K6).

HOPARLÖR BÖLGELERİ (şema 002): ANONS=http iken anons, ihlalin olduğu BÖLÜMÜN
hoparlörüne gönderilir (speaker_zones tablosu, `area` alanı cameras.area ile
eşleşir). Bölüme ait bölge yoksa "tüm fabrika" bölgesi, o da yoksa .env'deki
tek adres kullanılır — yani bölge tanımlanmamış bir kurulumda davranış
eskisiyle birebir aynıdır.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import threading
import urllib.error
import urllib.request

from app import veritabani, zaman
from app.ayarlar import Ayarlar
from app.loglama import log_al
from app.rules.cooldown import Cooldown

_log = log_al("anons")


class AnonsHatasi(Exception):
    """Ses çalınamadı — sebebi Anons sayfasında gösterilir."""


class NullAnonscu:
    """Varsayılan: hiçbir şey çalmaz. Geliştirme + anons altyapısız fabrika."""

    ad = "kapalı"

    def cal(self, anahtar: str, metin: str, ses_dosyasi: str | None) -> None:
        _log.info(f"Anons (kapalı, çalınmadı): {metin}")
        raise AnonsHatasi(
            "Anons KAPALI (.env dosyasında ANONS=null). Hoparlörden ses çıkmaz; "
            "yalnızca ekran uyarısı verilir. Ses kartına bağlamak için ANONS=ses_karti, "
            "IP hoparlör için ANONS=http yapıp sistemi yeniden başlatın."
        )


def _ses_komutu(ses_dosyasi: str) -> list[str] | None:
    """İşletim sistemine göre WAV çalma komutu.

    Fabrika sunucusu Linux'tur (aplay); geliştirme Mac (afplay) veya
    Windows (PowerShell SoundPlayer) olabilir. Üçünde de EK KURULUM
    GEREKTİRMEYEN, sistemde hazır gelen araçlar seçildi.
    """
    if sys.platform == "win32":
        # Windows'ta afplay/aplay yoktur; SoundPlayer her Windows'ta hazırdır.
        # Tek tırnak İKİLENİR: yolda kesme işareti varsa ("Ali'nin Sesleri")
        # PowerShell metni erken kapanır — hem bozulur hem komut enjeksiyonu
        # yüzeyi olur (yol arayüzden girilir).
        guvenli = ses_dosyasi.replace("'", "''")
        return [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(New-Object Media.SoundPlayer '{guvenli}').PlaySync()",
        ]
    calici = shutil.which("afplay") or shutil.which("aplay") or shutil.which("paplay")
    return [calici, ses_dosyasi] if calici else None


class SesKartiAnonscu:
    """Kayıtlı WAV dosyasını yerel ses kartından çalar → mevcut amplifikatör.

    macOS: afplay · Linux: aplay/paplay · Windows: PowerShell SoundPlayer.
    Ses dosyası tanımlı değilse yalnız log düşer (sistem yine çalışır).
    """

    ad = "ses kartı"

    def __init__(self) -> None:
        # Windows'ta komut her zaman vardır; diğerlerinde varlığı sınanır
        self._kullanilabilir = sys.platform == "win32" or _ses_komutu("deneme") is not None
        if not self._kullanilabilir:
            _log.error(
                "Ses çalma komutu bulunamadı (afplay/aplay/paplay). "
                "Linux'ta 'sudo apt install alsa-utils' kurun ya da "
                ".env dosyasında ANONS=null yapın."
            )

    def cal(self, anahtar: str, metin: str, ses_dosyasi: str | None) -> None:
        if not self._kullanilabilir:
            raise AnonsHatasi("Bu bilgisayarda ses çalma komutu bulunamadı (afplay/aplay/paplay).")
        if not ses_dosyasi:
            raise AnonsHatasi(
                f"'{anahtar}' mesajına ses dosyası bağlanmamış. Anons sayfasında "
                "bir .wav dosyasının yolunu yazın; yoksa yalnızca ekran uyarısı verilir."
            )
        komut = _ses_komutu(ses_dosyasi)
        if komut is None:
            raise AnonsHatasi(f"Ses çalma komutu bulunamadı: {ses_dosyasi}")
        # Bu çağrı zaten ayrı bir iş parçacığındadır (AnonsYoneticisi), bu
        # yüzden sonucu BEKLEYEBİLİRİZ. Beklemezsek komut hemen başarısız olsa
        # bile "gönderildi" yazardı ve 'Anonsu Dene' düğmesi yalan söylerdi.
        try:
            sonuc = subprocess.run(
                komut,
                capture_output=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if sys.platform == "win32"
                else 0,
            )
        except (OSError, subprocess.SubprocessError) as hata:
            raise AnonsHatasi(f"Ses çalınamadı ({ses_dosyasi}): {hata}") from hata
        if sonuc.returncode != 0:
            ayrinti = (sonuc.stderr or b"").decode("utf-8", "replace").strip()[:200]
            raise AnonsHatasi(
                f"Ses çalınamadı ({ses_dosyasi}). "
                + (f"Sebep: {ayrinti}" if ayrinti else "Dosya biçimi desteklenmiyor olabilir.")
            )
        _log.info(f"Anons çalındı: {metin}")


def http_gonder(adres: str, anahtar: str, metin: str) -> None:
    """Tek bir anons adresine HTTP POST atar; başarısızlıkta AnonsHatasi.

    Gövde: {"key": ..., "text": ...} JSON. Somut uç nokta biçimi, sahadaki
    anons sistemi öğrenilince gerekirse uyarlanır (docs/08 R3).

    Ayrı bir fonksiyon: hem ihlal anındaki otomatik anons hem de arayüzdeki
    "Bu hoparlörü dene" düğmesi AYNI yoldan gider. İkisi ayrı kod olsaydı
    deneme başarılı olup gerçek anons sessizce başarısız olabilirdi.
    """
    veri = json.dumps({"key": anahtar, "text": metin}).encode("utf-8")
    istek = urllib.request.Request(adres, data=veri, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(istek, timeout=5) as yanit:
            _log.info(f"Anons HTTP gönderildi ({yanit.status}): {metin}")
    except (urllib.error.URLError, TimeoutError, ValueError) as hata:
        # ValueError: adres biçimi bozuksa urllib bunu fırlatır.
        # Adres MESAJA KONMAZ: içinde kullanıcı adı/şifre olabilir ve hata
        # ekranı onu ham gösterirdi. Tam adres yalnızca günlüğe yazılır;
        # çağıran taraf hangi hoparlör olduğunu maskeli adresle ekler.
        _log.error(f"Anons HTTP gönderilemedi ({adres}): {hata}")
        raise AnonsHatasi(
            f"Anons adresine ulaşılamadı. Sebep: {hata}. "
            "Hoparlörün açık ve aynı ağda olduğunu doğrulayın."
        ) from hata


class HttpAnonscu:
    """IP hoparlör / anons sunucusuna HTTP POST atar."""

    ad = "http"

    def __init__(self, adres: str) -> None:
        self._adres = adres

    @property
    def adres(self) -> str:
        return self._adres

    def cal(self, anahtar: str, metin: str, ses_dosyasi: str | None) -> None:
        http_gonder(self._adres, anahtar, metin)


def bolge_sec(bolgeler: list[dict], kamera_alani: str | None) -> dict | None:
    """İhlalin olduğu bölümün hoparlörü — seçim kuralının TEK yeri.

    Önce bölümü BİREBİR eşleşen açık bölge, sonra "tüm fabrika" (area boş)
    bölgesi. Hiçbiri yoksa None döner ve .env'deki tek adres kullanılır; yani
    hiç bölge tanımlanmamış bir kurulumda davranış eskisiyle aynıdır.

    Modül düzeyinde ve saf: Anons ekranı "bu kamera hangi hoparlöre bağlı"
    yazarken de bunu çağırır. İki ayrı seçim kodu olsaydı ekran bir hoparlörü
    gösterip anons başka hoparlörden çalabilirdi.
    """
    alan = (kamera_alani or "").strip()
    if alan:
        for bolge in bolgeler:
            if bolge.get("enabled") and (bolge.get("area") or "").strip() == alan:
                return bolge
    for bolge in bolgeler:
        if bolge.get("enabled") and not (bolge.get("area") or "").strip():
            return bolge
    return None


def anonscu_kur(ayarlar: Ayarlar):
    if ayarlar.anons == "ses_karti":
        return SesKartiAnonscu()
    if ayarlar.anons == "http":
        return HttpAnonscu(ayarlar.anons_http_adresi)
    return NullAnonscu()


class AnonsYoneticisi:
    """Anons cooldown'unu uygular ve mesajı adaptöre iletir.

    Anons çağrısı HER ZAMAN ayrı bir iş parçacığında yapılır: HTTP anons
    sunucusu kapalıysa urlopen 5 saniye bekler ve o süre boyunca TEK analiz
    iş parçacığı durduğu için TÜM kameralar kör kalırdı. Bir hoparlörün
    gecikmesi, fabrikanın izlenmemesine yol açmamalı.
    """

    def __init__(self, ayarlar: Ayarlar) -> None:
        self._anonscu = anonscu_kur(ayarlar)
        self._bekleme_sn = ayarlar.anons_bekleme_sn
        self._goruntu_koku = ayarlar.kok_dizin
        self._veritabani_yolu = ayarlar.veritabani_yolu
        self._cooldown = Cooldown()
        # speaker_zones satırları (dict). Süpervizör, konfigürasyon her
        # değiştiğinde yeniler; boş liste = eski davranış (.env'deki tek adres).
        self._bolgeler: list[dict] = []
        self.son_sonuc: str = "Henüz anons denenmedi."

    @property
    def ad(self) -> str:
        return self._anonscu.ad

    def bolgeleri_yukle(self, satirlar) -> None:
        """Hoparlör bölgelerini tazeler (speaker_zones satırları)."""
        self._bolgeler = [dict(satir) for satir in satirlar]

    def bolge_sec(self, kamera_alani: str | None) -> dict | None:
        """İhlalin olduğu bölümün hoparlörü (bkz. modül düzeyindeki bolge_sec)."""
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
        self.hemen_cal(mesaj, self.bolge_sec(kamera_alani))

    def hemen_cal(self, mesaj: dict, bolge: dict | None = None) -> None:
        """Cooldown'suz çalar (arayüzdeki 'Anonsu Dene' düğmesi bunu kullanır)."""
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
        threading.Thread(
            target=self._cal_ve_kaydet,
            args=(mesaj.get("key", ""), mesaj.get("text", ""), ses_yolu, bolge),
            name="anons",
            daemon=True,
        ).start()

    def _hedef_anonscu(self, bolge: dict | None):
        """Bölge seçildiyse AYNI adaptör, o bölgenin adresiyle.

        Hoparlör bölgesi yalnızca IP hoparlörde (ANONS=http) anlamlıdır: ses
        kartına bağlı tek amfide "hangi bölüme çalsın" diye bir seçim yoktur.
        """
        if bolge is None or not isinstance(self._anonscu, HttpAnonscu):
            return self._anonscu
        return HttpAnonscu(bolge["address"])

    def _cal_ve_kaydet(
        self, anahtar: str, metin: str, ses_yolu: str | None, bolge: dict | None = None
    ) -> None:
        nereye = f" ({bolge['name']})" if bolge else ""
        try:
            self._hedef_anonscu(bolge).cal(anahtar, metin, ses_yolu)
            self.son_sonuc = f"Son anons ÇALINDI{nereye}: {metin}"
            if bolge is not None:
                self._son_anonsu_yaz(int(bolge["id"]))
        except AnonsHatasi as hata:
            # Bilinen sebep: kullanıcıya olduğu gibi göster
            self.son_sonuc = f"Son anons ÇALINAMADI{nereye} — {hata}"
            _log.error(f"Anons çalınamadı: {hata}")
        except Exception as hata:  # noqa: BLE001 — anons hatası sistemi durdurmaz
            self.son_sonuc = f"Son anons ÇALINAMADI{nereye} — beklenmeyen hata: {hata}"
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

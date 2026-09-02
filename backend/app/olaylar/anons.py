"""Anons adaptörü (docs/02 §7): Null / Ses kartı / HTTP.

Seçim .env'deki ANONS ayarıyla yapılır: null | ses_karti | http.
Anons cooldown'u ekran uyarısından BAĞIMSIZ ve daha uzundur — ekranda 3 olay
görünmesi sorun değil; hoparlörün 3 kez bağırması sorundur (docs/03 §4).

Anons altyapısı yoksa (ANONS=null) sistem bundan tamamen bağımsız çalışır (K6).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request

from app.ayarlar import Ayarlar
from app.loglama import log_al
from app.rules.cooldown import Cooldown

_log = log_al("anons")


class NullAnonscu:
    """Varsayılan: hiçbir şey çalmaz. Geliştirme + anons altyapısız fabrika."""

    ad = "kapalı"

    def cal(self, anahtar: str, metin: str, ses_dosyasi: str | None) -> None:
        _log.info(f"Anons (kapalı, çalınmadı): {metin}")


def _ses_komutu(ses_dosyasi: str) -> list[str] | None:
    """İşletim sistemine göre WAV çalma komutu.

    Fabrika sunucusu Linux'tur (aplay); geliştirme Mac (afplay) veya
    Windows (PowerShell SoundPlayer) olabilir. Üçünde de EK KURULUM
    GEREKTİRMEYEN, sistemde hazır gelen araçlar seçildi.
    """
    if sys.platform == "win32":
        # Windows'ta afplay/aplay yoktur; SoundPlayer her Windows'ta hazırdır
        return [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(New-Object Media.SoundPlayer '{ses_dosyasi}').PlaySync()",
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
        if not self._kullanilabilir or not ses_dosyasi:
            _log.warning(f"Anons ses dosyası yok, çalınamadı: {anahtar} — {metin}")
            return
        komut = _ses_komutu(ses_dosyasi)
        if komut is None:
            _log.error(f"Anons çalınamadı, ses komutu yok: {ses_dosyasi}")
            return
        try:
            # Bloklamasın: hoparlör çalarken analiz beklememeli
            subprocess.Popen(komut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _log.info(f"Anons çalınıyor: {metin}")
        except OSError as hata:
            _log.error(f"Anons çalınamadı ({ses_dosyasi}): {hata}")


class HttpAnonscu:
    """IP hoparlör / anons sunucusuna HTTP POST atar.

    Gövde: {"key": ..., "text": ...} JSON. Somut uç nokta biçimi, sahadaki
    anons sistemi öğrenilince gerekirse uyarlanır (docs/08 R3).
    """

    ad = "http"

    def __init__(self, adres: str) -> None:
        self._adres = adres

    def cal(self, anahtar: str, metin: str, ses_dosyasi: str | None) -> None:
        veri = json.dumps({"key": anahtar, "text": metin}).encode("utf-8")
        istek = urllib.request.Request(
            self._adres, data=veri, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(istek, timeout=5) as yanit:
                _log.info(f"Anons HTTP gönderildi ({yanit.status}): {metin}")
        except (urllib.error.URLError, TimeoutError, ValueError) as hata:
            # ValueError: adres biçimi bozuksa urllib bunu fırlatır; ayarlar.py
            # açılışta engelliyor ama burada da yutulmalı — anons hatası
            # yüzünden analiz durmaz.
            _log.error(f"Anons HTTP gönderilemedi ({self._adres}): {hata}")


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
        self._cooldown = Cooldown()
        self.son_sonuc: str = "Henüz anons denenmedi."

    @property
    def ad(self) -> str:
        return self._anonscu.ad

    def duyur(self, kamera_id: int, zaman_s: float, mesaj: dict | None) -> None:
        """mesaj: announcement_messages satırı (dict) veya None."""
        if mesaj is None or not mesaj.get("enabled", 1):
            return
        anahtar = ("anons", kamera_id, mesaj["id"])
        if not self._cooldown.izinli_mi(anahtar, zaman_s, float(self._bekleme_sn)):
            return
        self.hemen_cal(mesaj)

    def hemen_cal(self, mesaj: dict) -> None:
        """Cooldown'suz çalar (arayüzdeki 'Anonsu Dene' düğmesi bunu kullanır)."""
        ses = mesaj.get("audio_file")
        ses_yolu = str(self._goruntu_koku / ses) if ses else None
        threading.Thread(
            target=self._cal_ve_kaydet,
            args=(mesaj.get("key", ""), mesaj.get("text", ""), ses_yolu),
            name="anons",
            daemon=True,
        ).start()

    def _cal_ve_kaydet(self, anahtar: str, metin: str, ses_yolu: str | None) -> None:
        try:
            self._anonscu.cal(anahtar, metin, ses_yolu)
            self.son_sonuc = f"Son anons gönderildi: {metin}"
        except Exception as hata:  # noqa: BLE001 — anons hatası sistemi durdurmaz
            self.son_sonuc = f"Son anons başarısız: {hata}"
            _log.error(f"Anons çalınamadı: {hata}", exc_info=hata)

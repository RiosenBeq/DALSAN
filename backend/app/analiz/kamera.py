"""Kamera kaynağı: 'son kare' deseni + otomatik yeniden bağlanma.

RTSP akışı kendi iş parçacığında SÜREKLİ okunur; işlenmeyen kareler atılır.
Aksi halde tampon dolar ve gecikme dakikalara çıkar (docs/02 §6). Analiz
tarafı her zaman en güncel kareyi alır.

Bir kameranın hatası yalnızca kendi iş parçacığını etkiler; üstel bekleme
(1 → 30 sn) ile yeniden bağlanılır. 60 sn kare gelmezse kamera 'offline'
sayılır ve süpervizör sistem olayı üretir.

Üç durum (docs/02 §6 + kullanıcıya dürüst geri bildirim):
  connecting  henüz hiç kare gelmedi, ilk bağlantı süresi (60 sn) dolmadı
  online      son 60 sn içinde kare geldi
  offline     bağlantı yok (hiç kurulamadı ya da koptu)
Bağlantı kurulamayınca SEBEP `son_hata` alanında tutulur ve kamera sayfasında
gösterilir — kullanıcı günlüğü karıştırmak zorunda kalmaz.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

# RTSP'yi TCP üzerinden aç (CLAUDE.md §4): UDP fabrika ağında paket kaybıyla
# bozuk kare üretir. Bu ortam değişkeni OpenCV'nin FFmpeg arkucunu ayarlar ve
# ilk VideoCapture'dan ÖNCE verilmelidir.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402  (yukarıdaki ortam değişkeni importtan önce gerekli)
import numpy as np  # noqa: E402

from app import zaman
from app.loglama import log_al

# Bağlantı denemeleri arasındaki üstel bekleme sınırları (sn)
_BEKLEME_ILK = 1.0
_BEKLEME_EN_COK = 30.0
# Bu süre kare gelmezse kamera offline kabul edilir (docs/02 §6)
OFFLINE_ESIGI_SN = 60.0
# RTSP ön kontrolü: kameranın portuna TCP ile ulaşma süresi
_AG_KONTROL_SN = 3.0
_RTSP_VARSAYILAN_PORT = 554

DURUM_ONLINE = "online"
DURUM_OFFLINE = "offline"
DURUM_BAGLANIYOR = "connecting"


class KameraKaynagi:
    """Tek kameranın okuma iş parçacığı. Yalnızca kare okur; VERİTABANINA
    DOKUNMAZ — durum bilgisini süpervizör okuyup DB'ye yazar."""

    def __init__(self, kamera_id: int, ad: str, kaynak_tipi: str, kaynak_url: str) -> None:
        self.kamera_id = kamera_id
        self.ad = ad
        self.kaynak_tipi = kaynak_tipi  # "rtsp" | "file"
        self.kaynak_url = kaynak_url
        self._log = log_al("kamera")
        self._kilit = threading.Lock()
        self._son_kare: np.ndarray | None = None
        self._son_kare_zamani: float = 0.0  # time.monotonic
        self._baslangic: float = 0.0  # time.monotonic; baslat() ile dolar
        self._kare_sayaci = 0
        self._sayac_baslangici = time.monotonic()
        self.olculen_fps: float = 0.0
        # Son başarısız bağlantı denemesinin Türkçe sebebi ve zamanı (UTC metni)
        self.son_hata: str = ""
        self.son_deneme_utc: str = ""
        self._dur = threading.Event()
        self._is_parcacigi = threading.Thread(
            target=self._dongu, name=f"kamera-{kamera_id}", daemon=True
        )

    # ---- dış API (süpervizör ve web kullanır) ----

    def baslat(self) -> None:
        self._baslangic = time.monotonic()
        self._is_parcacigi.start()

    def durdur(self) -> None:
        self._dur.set()
        self._is_parcacigi.join(timeout=5)

    def son_kare(self) -> tuple[np.ndarray | None, float]:
        """En güncel kare (BGR) ve monotonic zamanı. Kare yoksa (None, 0)."""
        with self._kilit:
            if self._son_kare is None:
                return None, 0.0
            return self._son_kare, self._son_kare_zamani

    def cevrimici_mi(self) -> bool:
        return self.durum() == DURUM_ONLINE

    def durum(self, simdi: float | None = None) -> str:
        """online / connecting / offline — tek karar noktası.

        Yeni eklenen kameraya daha ilk kare gelmeden 'çevrimdışı' olayı düşmesin
        diye ilk 60 sn 'connecting' sayılır; süre dolar da kare gelmezse offline.
        """
        an = time.monotonic() if simdi is None else simdi
        with self._kilit:
            kare_zamani = self._son_kare_zamani
        if kare_zamani > 0 and (an - kare_zamani) < OFFLINE_ESIGI_SN:
            return DURUM_ONLINE
        if kare_zamani == 0 and self._baslangic > 0 and (an - self._baslangic) < OFFLINE_ESIGI_SN:
            return DURUM_BAGLANIYOR
        return DURUM_OFFLINE

    # ---- iç döngü ----

    def _dongu(self) -> None:
        bekleme = _BEKLEME_ILK
        while not self._dur.is_set():
            yakalayici = self._ac()
            if yakalayici is None:
                self._log.warning(
                    f"Kamera bağlantısı kurulamadı: {self.ad} — {self.son_hata} "
                    f"({bekleme:.0f} sn sonra yeniden denenecek)"
                )
                if self._dur.wait(bekleme):
                    return
                bekleme = min(bekleme * 2, _BEKLEME_EN_COK)
                continue

            bekleme = _BEKLEME_ILK  # bağlantı kuruldu, sayaç sıfırlanır
            self.son_hata = ""
            self._log.info(f"Kamera bağlandı: {self.ad}")
            dosya_fps = yakalayici.get(cv2.CAP_PROP_FPS) or 0
            try:
                self._okuma_dongusu(yakalayici, dosya_fps)
            finally:
                yakalayici.release()
            if not self._dur.is_set():
                self.son_hata = "Görüntü akışı koptu; yeniden bağlanılıyor."
                self.son_deneme_utc = zaman.simdi_utc()
                self._log.warning(f"Kamera akışı koptu: {self.ad} — yeniden bağlanılıyor")

    def _ac(self) -> cv2.VideoCapture | None:
        """Kaynağı açar; açılamazsa `son_hata`ya Türkçe sebebi yazıp None döner.

        Ucuz ön kontroller (dosya var mı / kameranın portuna ulaşılıyor mu)
        OpenCV'den ÖNCE yapılır: hem sebep netleşir hem ulaşılamayan adreste
        FFmpeg'in uzun bekleme süresi harcanmaz.
        """
        self.son_deneme_utc = zaman.simdi_utc()
        on_kontrol = self._on_kontrol()
        if on_kontrol:
            self.son_hata = on_kontrol
            return None
        yakalayici = cv2.VideoCapture(self.kaynak_url, cv2.CAP_FFMPEG)
        if not yakalayici.isOpened():
            yakalayici.release()
            self.son_hata = self._acilamama_sebebi()
            return None
        return yakalayici

    def _on_kontrol(self) -> str:
        """Açmadan önce sebebi belli olan hatalar; sorun yoksa boş metin."""
        if self.kaynak_tipi == "file":
            if not Path(self.kaynak_url).is_file():
                return (
                    f"Video dosyası bulunamadı: {self.kaynak_url} — "
                    "Kamera ayarlarından dosyanın tam yolunu düzeltin."
                )
            return ""
        parca = urlsplit(self.kaynak_url)
        host, port = parca.hostname, parca.port or _RTSP_VARSAYILAN_PORT
        if not host:
            return "RTSP adresi çözümlenemedi. Biçim: rtsp://kullanici:sifre@IP:554/yol"
        try:
            with socket.create_connection((host, port), timeout=_AG_KONTROL_SN):
                return ""
        except socket.gaierror:
            return f"Kamera adresi çözümlenemedi: {host} — IP adresini kontrol edin."
        except (OSError, TimeoutError):
            return (
                f"Kameraya ağ üzerinden ulaşılamıyor ({host}:{port}). IP adresini, "
                "port numarasını ve kameranın/ağ kablosunun bağlı olduğunu kontrol edin."
            )

    def _acilamama_sebebi(self) -> str:
        if self.kaynak_tipi == "file":
            return (
                "Video dosyası açılamadı — dosya bozuk ya da biçimi desteklenmiyor "
                "olabilir (MP4/H.264 önerilir)."
            )
        return (
            "Kameraya ulaşıldı ama görüntü akışı açılamadı. Kullanıcı adı, şifre veya "
            "akış yolu yanlış olabilir. Şifrede @ : / # gibi karakter varsa "
            "%40 %3A %2F %23 biçiminde yazın."
        )

    def _okuma_dongusu(self, yakalayici: cv2.VideoCapture, dosya_fps: float) -> None:
        ardisik_basarisiz = 0
        while not self._dur.is_set():
            tamam, kare = yakalayici.read()
            if not tamam:
                if self.kaynak_tipi == "file":
                    # Video dosyası kamera taklidi yapar: bitince başa sar (dev/test).
                    # Art arda okunamıyorsa dosya bozuk demektir: işlemciyi %100
                    # döndürmek yerine çık, dış döngü yeniden açmayı dener.
                    ardisik_basarisiz += 1
                    if ardisik_basarisiz > 3:
                        return
                    yakalayici.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    if self._dur.wait(0.05):
                        return
                    continue
                return  # RTSP koptu → dış döngü yeniden bağlanır
            ardisik_basarisiz = 0

            simdi = time.monotonic()
            with self._kilit:
                self._son_kare = kare
                self._son_kare_zamani = simdi

            self._kare_sayaci += 1
            gecen = simdi - self._sayac_baslangici
            if gecen >= 10.0:
                self.olculen_fps = self._kare_sayaci / gecen
                self._kare_sayaci = 0
                self._sayac_baslangici = simdi

            if self.kaynak_tipi == "file" and dosya_fps > 0:
                # Dosyayı gerçek hızında oynat; yoksa saniyede yüzlerce kare döner
                if self._dur.wait(1.0 / dosya_fps):
                    return

"""Uyarı dağıtıcısının kuyruk ve işçi parçası (docs/17 §7.3-2, -3, -4, -11).

Her ÇIKIŞIN (bir ses çıkışı ya da bir IP hoparlör adresi) bir öncelikli kuyruğu
ve tek işçi iş parçacığı vardır: aynı çıkışta aynı anda tek ses çalar, farklı
çıkışlar birbirini beklemez. İşçi kanal SATIRINA değil çıkışa bağlıdır: iki
bölümün satırı aynı hoparlörü gösteriyorsa sesleri yine sıraya girer.

Sıra önce önem (kritik 0 … düşük 3; deneme en son), sonra kuyruğa giriş
sırasıdır. Kritik bir öğe gelince çalan kritik olmayan ses kesilir: işçinin
`kes` olayı kurulur, ses çalıcısı 100 ms'de bir yoklar ve süreci sonlandırır
(Windows'ta `durdurucu` çağrılır). HTTP isteği kesilemez; yalnız sırası öne
alınır. Kuyrukta bekleme süresini (ANONS_BEKLEME_SN) aşan kritik olmayan öğe
çalınmaz, "bayat" diye kaydedilir: geçmiş bir durumu anlatan anons da bir
yanlış alarm türüdür.

Çalma ve kayıt işini bu modül yapmaz; işçiye çağıranın `isle(oge, kes)` ve
`bitince(oge)` işlevleri verilir (olaylar/anons.py). Böylece kuyruk mekaniği
tek başına ve sahte çalıcıyla sınanır (tests/test_uyari_dagitici.py).
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app import zaman
from app.loglama import log_al

_log = log_al("anons")

# Önem → sıra (küçük önce). Bilinmeyen önem "orta" sayılır: önemi bilinmeyen
# bir uyarı sessizce en sona atılmamalı (rules/olay_kodu.py ile aynı ilke).
ONCELIKLER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
DENEME_ONCELIGI = 4  # deneme ve test sesi gerçek bir uyarının önüne geçmez
_DUR_ONCELIGI = 99  # işçiyi durduran işaret: kuyruktaki her şeyden sonra

# Aşamalar (alert_deliveries.stage)
ASAMA_ACILDI = "acildi"
ASAMA_HATIRLATMA = "hatirlatma"
ASAMA_TEST = "test"

# Sonuçlar (alert_deliveries.result, şema 009)
SONUC_TAMAM = "ok"
SONUC_BASARISIZ = "failed"
SONUC_GOLGE = "shadow"
SONUC_BAYAT = "stale"
SONUC_KESILDI = "preempted"
SONUC_DINLEYEN_YOK = "no_listener"
SONUC_BASTIRILDI = "suppressed_cooldown"
SONUC_GERI_DUSUS = "fallback"  # bölüm kanalı koptu, uyarı "Tüm fabrika"ya gitti


@dataclass
class UyariOgesi:
    """Bir kanala giden tek uyarı denemesi ve (işçi doldurunca) sonucu."""

    kanal: dict  # speaker_zones satırı (kuyruğa girdiği andaki hâli)
    anahtar: str  # mesaj anahtarı (helmet, safe_distance …)
    metin: str
    ses_yolu: str | None = None
    ses_hatasi: str = ""  # ses dosyası yolu kullanılamıyorsa sebebi
    onem: str = "medium"
    asama: str = ASAMA_ACILDI
    olay_id: int | None = None
    olay_kodu: str | None = None
    kamera_id: int | None = None
    kare_zamani: float | None = None  # kare yakalama anı (time.monotonic)
    bastirma: tuple | None = None  # başarılı çalınca tüketilecek bastırma anahtarı
    bastirma_zamani: float = 0.0
    grup: object | None = None  # olay düzeyindeki toplama (garanti, docs/17 §7.4)
    bitti: threading.Event | None = None  # eşzamanlı bekleyen (kanal denemesi) için
    kuyruga_giris: float = field(default_factory=time.monotonic)
    kuyruga_giris_utc: str = field(default_factory=zaman.simdi_utc)
    # İşçinin doldurdukları
    sonuc: str = ""
    ayrinti: str = ""
    baslama: float | None = None
    baslama_utc: str | None = None
    bitis_utc: str | None = None

    @property
    def oncelik(self) -> int:
        if self.asama == ASAMA_TEST:
            return DENEME_ONCELIGI
        return ONCELIKLER.get(self.onem, ONCELIKLER["medium"])

    @property
    def kritik(self) -> bool:
        return self.onem == "critical" and self.asama != ASAMA_TEST

    @property
    def kareden_baslamaya_ms(self) -> int | None:
        """Kare yakalama → çalıcının ya da isteğin başlaması (yalnız YAZILIM, §7.10)."""
        if self.kare_zamani is None or self.baslama is None:
            return None
        return max(0, round((self.baslama - self.kare_zamani) * 1000))

    @property
    def kuyruktan_baslamaya_ms(self) -> int | None:
        if self.baslama is None:
            return None
        return max(0, round((self.baslama - self.kuyruga_giris) * 1000))


class CikisIscisi:
    """Tek çıkışın öncelikli kuyruğu ve işçi iş parçacığı."""

    def __init__(
        self,
        ad: str,
        isle: Callable[[UyariOgesi, threading.Event], None],
        bitince: Callable[[UyariOgesi], None],
        bekleme_sn: float,
        durdurucu: Callable[[], None] | None = None,
    ) -> None:
        self.ad = ad
        self._isle = isle
        self._bitince = bitince
        self._bekleme_sn = bekleme_sn
        self._durdurucu = durdurucu
        self._kuyruk: queue.PriorityQueue = queue.PriorityQueue()
        self._sira = itertools.count()
        # Çıkış kilidi: işçi çalarken tutar. Kanal denemesi analiz kapalıyken
        # de aynı kilidi alır ki aynı hoparlörde iki ses üst üste binmesin.
        self.kilit = threading.Lock()
        self._durum_kilidi = threading.Lock()
        self._calan: UyariOgesi | None = None
        self._kes = threading.Event()
        self._bekleyen = 0
        self._bos = threading.Condition()
        self._is = threading.Thread(target=self._dongu, name=f"uyari-{ad}", daemon=True)
        self._is.start()

    # ------------------------------------------------------------ dışarıdan

    def ekle(self, oge: UyariOgesi) -> None:
        with self._bos:
            self._bekleyen += 1
        self._kuyruk.put((oge.oncelik, next(self._sira), oge))
        if oge.kritik:
            self._kesmeyi_dene()

    @property
    def bekleyen(self) -> int:
        """Kuyrukta bekleyen ve çalan öğe sayısı."""
        return self._bekleyen

    def bosalt(self, zaman_asimi: float) -> bool:
        """Kuyruk boşalana (çalan da bitene) kadar bekler; boşaldıysa True."""
        son = time.monotonic() + zaman_asimi
        with self._bos:
            while self._bekleyen:
                kalan = son - time.monotonic()
                if kalan <= 0:
                    return False
                self._bos.wait(kalan)
        return True

    def durdur(self, zaman_asimi: float) -> None:
        """Kuyruğu en çok `zaman_asimi` saniye boşaltır, sonra işçiyi durdurur."""
        self.bosalt(zaman_asimi)
        with self._bos:
            self._bekleyen += 1
        self._kuyruk.put((_DUR_ONCELIGI, next(self._sira), None))
        self._is.join(timeout=1.0)

    # ------------------------------------------------------------ işçi

    def _kesmeyi_dene(self) -> None:
        """Kritik öğe geldi: çalan kritik olmayan sesi kes (docs/17 §7.3-3)."""
        with self._durum_kilidi:
            calan = self._calan
            if calan is None or calan.kritik:
                return
            self._kes.set()
        if self._durdurucu is not None:
            try:
                self._durdurucu()
            except Exception as hata:  # noqa: BLE001 - kesme olmasa da kritik sırada öne geçti
                _log.warning(f"Çalan ses kesilemedi ({self.ad}): {hata}")

    def _siradaki_kritik_mi(self) -> bool:
        with self._kuyruk.mutex:
            bas = self._kuyruk.queue[0] if self._kuyruk.queue else None
        return bas is not None and bas[2] is not None and bas[2].kritik

    def _dongu(self) -> None:
        while True:
            _, _, oge = self._kuyruk.get()
            if oge is None:
                self._azalt()
                return
            try:
                self._tek_oge(oge)
            except Exception as hata:  # noqa: BLE001 - işçi ölürse o çıkış sonsuza dek susar
                _log.error(f"Uyarı işçisi hata verdi ({self.ad}): {hata}", exc_info=hata)
            finally:
                if oge.bitti is not None:
                    oge.bitti.set()
                self._azalt()

    def _tek_oge(self, oge: UyariOgesi) -> None:
        bekledi = time.monotonic() - oge.kuyruga_giris
        if not oge.kritik and bekledi > self._bekleme_sn:
            oge.sonuc = SONUC_BAYAT
            oge.ayrinti = (
                f"kuyrukta {bekledi:.0f} sn bekledi (sınır {self._bekleme_sn:g} sn); "
                "geçmiş bir durumu anlatacağı için çalınmadı"
            )
            oge.bitis_utc = zaman.simdi_utc()
        else:
            with self._durum_kilidi:
                self._calan = oge
                self._kes.clear()
            # Kritik öğe bu öğe kuyruktan alınırken geldiyse hemen kes
            if not oge.kritik and self._siradaki_kritik_mi():
                self._kes.set()
            try:
                with self.kilit:
                    self._isle(oge, self._kes)
            finally:
                with self._durum_kilidi:
                    self._calan = None
        self._bitince(oge)

    def _azalt(self) -> None:
        with self._bos:
            self._bekleyen -= 1
            if self._bekleyen <= 0:
                self._bekleyen = 0
                self._bos.notify_all()

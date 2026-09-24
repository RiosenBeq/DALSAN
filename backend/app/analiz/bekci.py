"""Bekçi (watchdog) - docs/17 §3.6.

Analiz iş parçacığı takılır ya da ölürse sistem görüntü almaya devam eder ama
HİÇBİR uyarı üretmez; ekran da "çalışıyor" gibi görünür. Bekçi bunu sessiz
bırakmaz: 10 sn'de bir analiz döngüsünün nabzına bakar.

- **Takıldı:** en az bir kamera görüntü verirken nabız `BEKCI_ESIGI_SN`'den
  eski. Görüntü yokken analizin beklemesi takılma değildir; model yüklenirken
  ya da indirilirken de sayılmaz.
- **Öldü:** analiz iş parçacığı çalışmıyor. Yeniden kurulmaz: aynı hatayla
  yine ölürdü.

Tepki: `ANALYSIS_STALLED` sistem olayı (bekçinin kendi kısa bağlantısıyla -
analizin bağlantısı kilitli olabilir), CRITICAL günlük ve /saglik'te
`analiz_takildi` / `analiz_olu` (hazır değil). `BEKCI_TEPKISI=yeniden_baslat`
(varsayılan) ise süreç `os._exit(70)` ile kapanır: takılan bir iş parçacığı
Python'da öldürülemez, tek çare süreci yeniden başlatmaktır. Bunu Docker
(`restart:`) ya da systemd (`Restart=`) yapar; masaüstünde Başlat betiğinin
Kontrol Paneli yapar (sunucu onun alt sürecidir; dalsan_launcher.py
`surec_kapaninca`). Süreci yeniden açan kimse yoksa (elle çalıştırılan
sunucu, testler, masaüstü paketi) çıkmak sistemi kalıcı olarak durdururdu:
orada yalnız uyarılır (kaynaklar.yeniden_acan_var_mi).

Aynı sorun bir kez bildirilir (olay seli yok); sorun geçince işaret kalkar.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable

from app import veritabani
from app.kaynaklar import yeniden_acan_var_mi
from app.loglama import log_al
from app.olaylar.yazici import sistem_olayi_yaz

# docs/17 §3.3: bekçi 10 sn'de bir bakar. Eşik (90 sn) bunun çok üstündedir.
BEKCI_ARALIGI_SN = 10.0
# Yeniden başlatma çıkış kodu (docs/17 §3.6; sysexits EX_SOFTWARE).
YENIDEN_BASLATMA_KODU = 70

ANALIZ_TAKILDI = "analiz_takildi"
ANALIZ_OLU = "analiz_olu"

# Model hazırlanırken analiz döngüsü henüz başlamamıştır: takılma sayılmaz.
_HAZIRLIK_EVRELERI = frozenset({"yukleniyor", "indiriliyor"})


class Bekci:
    """Analiz süpervizörünü izleyen iş parçacığı.

    `supervizor` şunları vermelidir: `analiz_canli_mi()`, `nabiz` (son turun
    monotonic zamanı, tur başlamadıysa None), `model_durumu`,
    `kare_ureten_kamera_var(simdi)`. Saat ve çıkış testte sahtesiyle verilir.
    """

    def __init__(
        self,
        supervizor,
        ayarlar,
        *,
        saat: Callable[[], float] = time.monotonic,
        cikis: Callable[[int], object] = os._exit,
        cikis_izinli: bool | None = None,
    ) -> None:
        self._supervizor = supervizor
        self._ayarlar = ayarlar
        self._saat = saat
        self._cikis = cikis
        if cikis_izinli is None:
            cikis_izinli = ayarlar.bekci_tepkisi == "yeniden_baslat" and yeniden_acan_var_mi()
        self._cikis_izinli = cikis_izinli
        self._log = log_al("bekci")
        self._dur = threading.Event()
        self._is_parcacigi = threading.Thread(target=self._dongu, name="bekci", daemon=True)
        # Şu an süren sorun (ANALIZ_TAKILDI / ANALIZ_OLU) ya da None; /saglik okur.
        self.sorun: str | None = None

    def baslat(self) -> None:
        self._is_parcacigi.start()

    def durdur(self) -> None:
        """Kapanışta analizden ÖNCE durdurulur: duran analiz "öldü" sanılmasın."""
        self._dur.set()
        if self._is_parcacigi.is_alive():
            self._is_parcacigi.join(timeout=BEKCI_ARALIGI_SN)

    def _dongu(self) -> None:
        while not self._dur.wait(BEKCI_ARALIGI_SN):
            try:
                self.tur()
            except Exception as hata:  # noqa: BLE001 - bekçinin kendisi ölmemeli
                self._log.error(f"Bekçi denetimi yapılamadı: {hata}", exc_info=hata)

    def denetle(self) -> tuple[str, str] | None:
        """Tek denetim: (sorun kodu, Türkçe açıklama) ya da None."""
        supervizor = self._supervizor
        if not supervizor.analiz_canli_mi():
            return ANALIZ_OLU, "analiz iş parçacığı çalışmıyor; hiçbir uyarı üretilmiyor."
        if supervizor.model_durumu in _HAZIRLIK_EVRELERI or supervizor.nabiz is None:
            return None
        simdi = self._saat()
        if not supervizor.kare_ureten_kamera_var(simdi):
            return None
        yas = simdi - supervizor.nabiz
        if yas < self._ayarlar.bekci_esigi_sn:
            return None
        return (
            ANALIZ_TAKILDI,
            f"görüntü geliyor ama analiz {yas:.0f} sn'dir ilerlemiyor; hiçbir uyarı üretilmiyor.",
        )

    def tur(self) -> None:
        bulgu = self.denetle()
        if bulgu is None:
            if self.sorun is not None:
                self._log.warning("Bekçi: analiz yeniden ilerliyor; uyarı kalktı.")
                self.sorun = None
            return
        kod, aciklama = bulgu
        if kod == self.sorun:
            return  # zaten bildirildi
        self.sorun = kod
        baslik = "Analiz durdu" if kod == ANALIZ_OLU else "Analiz takıldı"
        mesaj = f"{baslik}: {aciklama}"
        if self._cikis_izinli:
            mesaj += " Program yeniden başlatılıyor."
        self._log.critical(f"Bekçi - {mesaj}")
        self._olay_yaz(mesaj, kod)
        if self._cikis_izinli:
            self._cikis(YENIDEN_BASLATMA_KODU)

    def _olay_yaz(self, mesaj: str, kod: str) -> None:
        """Kendi kısa bağlantısıyla: analizin bağlantısı kilitli kalmış olabilir."""
        try:
            baglanti = veritabani.baglanti_ac(self._ayarlar.veritabani_yolu)
            try:
                sistem_olayi_yaz(baglanti, mesaj, detaylar={"sebep": kod}, kod="ANALYSIS_STALLED")
            finally:
                baglanti.close()
        except Exception as hata:  # noqa: BLE001 - günlük satırı zaten yazıldı
            self._log.error(f"Bekçi olayı veritabanına yazılamadı: {hata}")

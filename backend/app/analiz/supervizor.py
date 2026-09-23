"""Analiz süpervizörü - FastAPI içinde çalışan TEK arka plan iş parçacığı.

Görevleri:
- Aktif kameraların okuma iş parçacıklarını başlatır/durdurur
- 5 sn'de bir konfigürasyon değişikliğine bakar (MAX(updated_at)) ve
  RESTART'SIZ uygular (docs/02 §5)
- Her kamerayı kendi örnekleme hızında işler (tespit → takip → kural → olay)
- Kamera çevrimiçi/çevrimdışı geçişlerini DB'ye ve olay listesine yazar
- İhlalde anonsu tetikler, KKD bölgelerinden veri örnekler
- Günde bir kez saklama süresi (retention) temizliği ve disk kontrolü yapar

Bir kameranın hatası yalnızca o kamerayı atlatır; döngü asla ölmez -
7x24 çalışmanın gereği. Hatalar loglanır, sessizce yutulmaz.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path

from app import veritabani, zaman
from app.analiz import ortam
from app.analiz.bekci import Bekci
from app.analiz.boru_hatti import KameraHatti
from app.analiz.kamera import (
    DURUM_BAGLANIYOR,
    DURUM_BITTI,
    DURUM_OFFLINE,
    DURUM_ONLINE,
    KameraKaynagi,
)
from app.analiz.kkd_siniflandirici import KkdSiniflandirici, kisi_kirp, netlik_olc
from app.analiz.model_adi import gorunen_model_adi
from app.analiz.model_indir import (
    ModelIndirmeHatasi,
    indirilebilir_mi,
    modeli_indir,
    ozel_model_hatasi,
)
from app.analiz.tespit import ModelHatasi, Tespitci
from app.ayarlar import Ayarlar
from app.loglama import log_al
from app.olaylar.anons import AnonsYoneticisi, OlayBilgisi
from app.olaylar.yazici import acik_olaylari_kapat, ihlal_yaz, olay_kapat, sistem_olayi_yaz
from app.rules.olay_durumu import ACILDI, HATIRLATMA, KAPANDI, OlayGecisi
from app.rules.parametreler import KuralParametreHatasi, params_dogrula
from app.rules.tipler import BOLGE_TIPI_KODLARI, SINIF_INSAN, Bolge, Kalibrasyon, Kural


class _KameraOlcumu:
    """Bir kameranın işleme ölçümleri (docs/17 §13, 2b): kaç kare işlendi, işleme
    ve olay yazma ne kadar sürdü. /saglik?ayrinti=1 bunları gösterir (2d).

    Son N örnek tutulur: bellek 7x24 çalışmada sabit kalır. Ölçüm KARAR
    VERMEZ; yalnız "sistem yetişiyor mu" sorusunu sayıyla cevaplar.
    """

    def __init__(self) -> None:
        self.islenen: deque[float] = deque(maxlen=120)  # işlenen karelerin monotonic zamanı
        self.isle_ms: deque[float] = deque(maxlen=200)
        self.ihlal_yaz_ms: deque[float] = deque(maxlen=50)

    def islenen_fps(self, simdi: float, pencere_sn: float = 10.0) -> float:
        son = [t for t in self.islenen if simdi - t <= pencere_sn]
        if len(son) < 2 or son[-1] <= son[0]:
            return 0.0
        return (len(son) - 1) / (son[-1] - son[0])

    def ozet(self, simdi: float) -> dict:
        return {
            "islenen_fps": round(self.islenen_fps(simdi), 1),
            "isle_p90_ms": _yuzdelik(self.isle_ms, 90),
            "ihlal_yaz_p90_ms": _yuzdelik(self.ihlal_yaz_ms, 90),
        }


def _yuzdelik(degerler, yuzde: int) -> float | None:
    """En yakın sıra yöntemiyle yüzdelik; örnek yoksa None (ölçülmedi ≠ 0)."""
    sirali = sorted(degerler)
    if not sirali:
        return None
    return round(sirali[max(0, math.ceil(yuzde / 100 * len(sirali)) - 1)], 1)


def _islenen_hedefi(konfig: dict, kaynak) -> float:
    """İşlenen hızın hedefi: ayarlanan örnekleme hızı ile kameranın gerçekten
    verdiği hızın küçüğü - saniyede 3 kare veren kameradan 6 kare işlenemez."""
    ayarlanan = max(float(konfig["sample_fps"]), 0.1)
    return min(ayarlanan, kaynak.olculen_fps or ayarlanan)


def _geri_al(baglanti) -> None:
    """Yarım kalmış işlemi geri alır: sonraki yazmalar temiz bir işlemle başlasın."""
    try:
        baglanti.rollback()
    except sqlite3.Error:
        pass  # bağlantı zaten kullanılamaz durumda; asıl hata çoktan günlükte


_KONFIG_KONTROL_SN = 5.0
_DURUM_YAZMA_SN = 5.0
_BAKIM_ARALIGI_SN = 24 * 3600.0
# analysis_hours birikimi bu aralıkla yazılır (şema 007); çökmede en çok bu
# kadarlık ölçüm kaybolur.
_ANALIZ_SAATI_YAZMA_SN = 60.0
# Ardışık iki işlenmiş kare arasındaki boşluk bundan uzunsa "analiz edilen
# süre"ye eklenmez: kopukluk, takılma ya da uzun bekleme analiz değildir.
# Yavaşlamış analiz (saniyede 1 kare) yine sayılır.
_ANALIZ_BOSLUK_SN = 5.0
_ANALIZ_SAATI_UPSERT = (
    "INSERT INTO analysis_hours (camera_id, hour_utc, analyzed_s, frames_processed, "
    "frames_failed) VALUES (?, ?, ?, ?, ?) ON CONFLICT (camera_id, hour_utc) DO UPDATE SET "
    "analyzed_s = analyzed_s + excluded.analyzed_s, "
    "frames_processed = frames_processed + excluded.frames_processed, "
    "frames_failed = frames_failed + excluded.frames_failed"
)


class AnalizSupervizoru:
    def __init__(self, ayarlar: Ayarlar) -> None:
        self.ayarlar = ayarlar
        self._log = log_al("supervizor")
        self._dur = threading.Event()
        self._is_parcacigi = threading.Thread(target=self._dongu, name="analiz", daemon=True)

        self._kaynaklar: dict[int, KameraKaynagi] = {}
        # Kaynak kurulurken kameranın `updated_at` damgası. Biten bir videonun
        # yeniden çalıştırılıp çalıştırılmayacağına bakılan tek yer burasıdır.
        self._kaynak_damgalari: dict[int, str] = {}
        self._hatlar: dict[int, KameraHatti] = {}
        self._kamera_konfig: dict[int, dict] = {}
        self._anons_mesajlari: dict[int, dict] = {}
        self._son_durumlar: dict[int, str] = {}
        self._son_islenen_kare: dict[int, float] = {}
        self._siradaki_ornek: dict[int, float] = {}
        self._son_kkd_ornek: dict[int, float] = {}
        self._olcumler: dict[int, _KameraOlcumu] = {}
        # Kamera id → açık "Kamera çevrimdışı" olayının id'si. Kamera dönünce,
        # kapatılınca ya da silinince bu olay kapatılır (docs/17 §6.1). Id ile
        # tutulur: silinen kameranın olaylarında camera_id boşalır (FK SET NULL)
        # ve olay artık kameradan bulunamazdı.
        self._kopukluk_olaylari: dict[int, int] = {}
        # Olay anahtarı (kural, kamera, iz…) → açık ihlal olayının id'si
        # (rules/olay_durumu.py). Kapanış geçişi gelince bitiş bu satıra yazılır.
        self._acik_olaylar: dict[tuple, int] = {}
        # Kural id → gölge / anons / önem (docs/17 §3.5). Yapılandırma damgasıyla
        # tazelenir. Kural satırı okunamazsa (kilitli veritabanı) gölge ve anons
        # kararı buradan verilir: uyarı, kayıt yapılamasa da duyurulur. Motorun
        # kural imzasına GİRMEZ; gölge açılıp kapanınca pencereler sıfırlanmasın.
        self._kural_haritasi: dict[int, dict] = {}
        # Son ihlal kaydının hatası; /saglik "olay_yazilamadi" der. Bir sonraki
        # başarılı kayıt temizler.
        self.olay_yazma_hatasi: str | None = None
        # Analiz döngüsünün nabzı: her turun başında time.monotonic(). Bekçi
        # bununla takılmayı anlar; döngü hiç başlamadıysa None.
        self.nabiz: float | None = None
        # Kamera id → üst üste işlenemeyen kare sayısı (ANALIZ_HATA_ESIGI)
        self._ardisik_hata: dict[int, int] = {}
        # Kamera id → işlenen hızın hedefin altına ilk düştüğü an; bildirilenler
        self._yavas_baslangic: dict[int, float] = {}
        self._yavas_bildirildi: set[int] = set()
        # (kamera id, 'YYYY-MM-DDTHH') → [analiz edilen sn, işlenen, başarısız]
        self._analiz_saatleri: dict[tuple[int, str], list] = {}
        self._son_analiz_karesi: dict[int, float] = {}
        self._son_analiz_saati_yazma = 0.0

        self._son_konfig_kontrol = 0.0
        self._son_durum_yazma = 0.0
        # Bakım zamanlayıcısı _dongu() başında tohumlanır. 0.0 bırakılırsa koşul
        # `time.monotonic() >= 86400` olur; monotonic MAKİNENİN AÇIK KALMA
        # SÜRESİDİR, uygulamanınki değil. Her vardiya sonunda kapatılan bir
        # bilgisayarda 86400'e hiç ulaşılmaz → saklama süresi temizliği ve disk
        # uyarısı HİÇ çalışmaz, disk sessizce dolardı.
        self._son_bakim = 0.0
        self._konfig_damgasi: str = ""
        # Kamera başına canlı sayım: {kamera_id: {"person": 2, "truck": 1}}
        self._canli_sayim: dict[int, dict[str, int]] = {}

        self.tespitci: Tespitci | None = None
        self.tespit_hatasi: str | None = None
        # CIKARIM_CIHAZI=cuda istenip CPU'ya düşüldüyse Türkçe uyarı (ana sayfa)
        self.cihaz_uyarisi: str = ""
        # yukleniyor | indiriliyor | hazir | hata - ana sayfa bunu gösterir
        self.model_durumu: str = "yukleniyor"
        # KKD modeli analiz iş parçacığında yüklenir (_kkd_modelini_kur); o
        # zamana kadar ve dosya yoksa gözlem üretilmez
        self.kkd = KkdSiniflandirici(None)
        self.kkd_hatasi: str | None = None
        self._anons = AnonsYoneticisi(ayarlar)
        self.bekci = Bekci(self, ayarlar)

    # ---- yaşam döngüsü ----

    def baslat(self) -> None:
        self._is_parcacigi.start()
        self.bekci.baslat()

    def durdur(self) -> None:
        # Bekçi önce: duran analiz iş parçacığı "öldü" diye bildirilmesin
        self.bekci.durdur()
        self._dur.set()
        self._is_parcacigi.join(timeout=10)
        # Sırada bekleyen uyarılar en çok birkaç saniye içinde çalınır
        # (kritik önce, docs/17 §7.3-11); sonra çıkış işçileri durur
        self._anons.kapat(3.0)
        for kaynak in self._kaynaklar.values():
            kaynak.durdur()

    # ---- bekçinin sorduğu ----

    def analiz_canli_mi(self) -> bool:
        return self._is_parcacigi.is_alive()

    def kare_ureten_kamera_var(self, simdi: float) -> bool:
        """En az bir kamera şu an görüntü veriyor mu? (Görüntü yokken analizin
        beklemesi takılma değildir.)"""
        return any(k.durum(simdi) == DURUM_ONLINE for k in list(self._kaynaklar.values()))

    # ---- web'in kullandığı arayüz ----

    def canli_sayim(self, kamera_id: int) -> dict[str, int]:
        """Kameranın o anda gördüğü nesne sayıları (takip bazlı, kare değil)."""
        return dict(self._canli_sayim.get(kamera_id, {}))

    def toplam_canli_sayim(self) -> dict[str, int]:
        """Tüm kameraların toplamı - ana sayfadaki özet."""
        toplam: dict[str, int] = {}
        for sayim in self._canli_sayim.values():
            for sinif, adet in sayim.items():
                toplam[sinif] = toplam.get(sinif, 0) + adet
        return toplam

    def kamera_durumu(self, kamera_id: int) -> dict:
        """Kamera sayfasının 2 sn'de bir sorduğu canlı durum: online /
        connecting / offline + kullanıcının anlayacağı Türkçe açıklama."""
        kaynak = self._kaynaklar.get(kamera_id)
        if kaynak is None:
            return {
                "durum": DURUM_BAGLANIYOR,
                "mesaj": "Kamera birkaç saniye içinde başlatılacak…",
            }
        durum = kaynak.durum()
        son_hata = kaynak.son_hata
        if durum == DURUM_ONLINE:
            fps = round(kaynak.olculen_fps, 1)
            mesaj = "Görüntü akıyor" + (f" - ölçülen {fps:g} fps" if fps else "")
        elif durum == DURUM_BAGLANIYOR:
            mesaj = "Bağlanılıyor… (ilk bağlantı 30 sn sürebilir)"
            if son_hata:
                mesaj += f" Son deneme başarısız: {son_hata}"
        elif durum == DURUM_BITTI:
            # Bir hata DEĞİL: "bağlantı yok, yeniden deneniyor" cümlesi burada
            # kullanıcıyı boşuna beklemeye iterdi.
            mesaj = (
                "Video sonuna kadar izlendi - analiz tamamlandı. Bulunan ihlaller "
                "Olaylar sayfasında. Baştan çalıştırmak için Kameralar → Video Yükle "
                'sayfasındaki "Yeniden Çalıştır" düğmesini kullanın.'
            )
        else:
            mesaj = "Bağlantı yok."
            if son_hata:
                mesaj += f" {son_hata}"
            mesaj += " Sistem otomatik olarak yeniden denemeye devam ediyor."
        return {
            "durum": durum,
            "mesaj": mesaj,
            "son_deneme": zaman.ekranda_goster(kaynak.son_deneme_utc)
            if kaynak.son_deneme_utc
            else "",
            "sayim": self.canli_sayim(kamera_id),
            "bolge_sayimlari": self.bolge_sayimlari(kamera_id),
            "kalite": self._kalite(kamera_id),
            "olcum": self.islem_olcumu(kamera_id),
        }

    def islem_olcumu(self, kamera_id: int) -> dict:
        """İşlenen fps ve işleme/olay yazma süreleri (p90, ms). Ölçüm yoksa boş."""
        olcum = self._olcumler.get(kamera_id)
        return olcum.ozet(time.monotonic()) if olcum is not None else {}

    def bolge_sayimlari(self, kamera_id: int) -> list[dict]:
        """Kameranın bölge bölge sayım tablosu (rules/sayim.py).

        Kamera henüz başlamadıysa BOŞ liste döner; ekran bunu "sayım için
        analiz başlatılmalı" diye gösterir, sıfır yazıp yanıltmaz.
        """
        hat = self._hatlar.get(kamera_id)
        return hat.sayimlar() if hat is not None else []

    def sayaci_sifirla(self, kamera_id: int, bolge_id: int | None = None) -> bool:
        """Kümülatif 'giren' sayacını sıfırlar (vardiya başı düğmesi).

        Döner: sıfırlama gerçekten yapıldı mı. Kamera çalışmıyorsa False -
        ekran "sıfırlandı" yazıp hiçbir şey yapmamış olmamalı.
        """
        hat = self._hatlar.get(kamera_id)
        if hat is None:
            return False
        hat.sayaci_sifirla(bolge_id)
        return True

    def _kalite(self, kamera_id: int) -> dict:
        hat = self._hatlar.get(kamera_id)
        return hat.kalite() if hat is not None else {"sorun": "yok", "mesaj": ""}

    def onizleme_jpeg(self, kamera_id: int, bolgeler_dahil: bool = True) -> bytes | None:
        """İşlenmiş (kutulu) son kare; yoksa ham son kare.

        bolgeler_dahil=False → bölgeler görüntüye çizilmez. Bölge çizim sayfası
        bölgeleri kendi tuvaline çizdiği için oraya bu sürüm gider.
        """
        hat = self._hatlar.get(kamera_id)
        if hat is not None:
            jpeg = hat.son_islenmis_jpeg(bolgeler_dahil)
            if jpeg is not None:
                return jpeg
        kaynak = self._kaynaklar.get(kamera_id)
        if kaynak is None:
            return None
        kare, _ = kaynak.son_kare()
        if kare is None:
            return None
        import cv2

        tamam, jpeg = cv2.imencode(".jpg", kare, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return jpeg.tobytes() if tamam else None

    # ---- ana döngü ----

    def _dongu(self) -> None:
        try:
            baglanti = veritabani.baglanti_ac(self.ayarlar.veritabani_yolu)
        except Exception as hata:  # noqa: BLE001 - iş parçacığı SESSİZCE ölmesin
            self.model_durumu = "hata"
            # Ekranda sade Türkçe; özgün hata metni yalnızca günlüğe yazılır.
            self.tespit_hatasi = (
                "Analiz başlatılamadı. Kontrol Paneli'nde Durdur'a, sonra Sistemi Başlat'a "
                "basın. Sorun sürerse program klasöründeki veri/loglar/sistem.log dosyasını "
                "destek ekibine iletin."
            )
            self._log.error(f"Analiz başlatılamadı: {hata}", exc_info=hata)
            return
        try:
            self._acilis_olaylarini_yaz(baglanti)
        except Exception as hata:  # noqa: BLE001 - olay yazılamadı diye analiz başlamamazlık etmez
            self._log.error(f"Açılış olayları yazılamadı: {hata}", exc_info=hata)
        try:
            self._tespitciyi_kur(baglanti)
        except Exception as hata:  # noqa: BLE001 - model kurulamadı diye kameralar durmaz
            self.tespitci = None
            self.model_durumu = "hata"
            # Ekranda ürün adı + yapılabilir adım; ham hata metni günlüğe gider.
            self.tespit_hatasi = (
                f"{gorunen_model_adi(self.ayarlar.model_dosyasi.name)} başlatılamadı. "
                "Kontrol Paneli'nde Durdur'a, sonra Sistemi Başlat'a basın. Sorun sürerse "
                "program klasöründeki veri/loglar/sistem.log dosyasını destek ekibine iletin."
            )
            self._log.error(f"Tespit modeli kurulamadı: {hata}", exc_info=hata)
            # Beklenmeyen hata yolu da olay yazar (docs/17 §6.1): eskiden yalnız
            # tipli hata yolu yazıyordu ve bu durumda Olaylar'da iz kalmıyordu.
            self._sistem_olayi(
                baglanti,
                f"Tespit modeli yüklenemedi: {self.tespit_hatasi}",
                kod="MODEL_LOAD_FAILED",
            )
        self._kkd_modelini_kur(baglanti)
        # Bakım açılıştan hemen sonra bir kez, sonra her 24 saatlik UYGULAMA
        # çalışma süresinde bir çalışsın (makinenin uptime'ından bağımsız).
        self._son_bakim = time.monotonic() - _BAKIM_ARALIGI_SN
        # Yanlış OpenCV sürümü nesne tanımayı SESSİZCE bozar (analiz/ortam.py).
        # Günlüğe düşmesi şart: kullanıcı destek için günlüğü kopyalıyor.
        uyari = ortam.opencv_uyarisi()
        if uyari:
            self._log.warning(uyari, extra={"ayrinti": f"cv2 {ortam.opencv_surumu()}"})
        self._log.info("Analiz süpervizörü başladı.")
        try:
            while not self._dur.is_set():
                simdi = time.monotonic()
                self.nabiz = simdi
                try:
                    if simdi - self._son_konfig_kontrol >= _KONFIG_KONTROL_SN:
                        self._son_konfig_kontrol = simdi
                        self._konfigurasyonu_yenile(baglanti)
                    self._kameralari_isle(baglanti, simdi)
                    if simdi - self._son_durum_yazma >= _DURUM_YAZMA_SN:
                        self._son_durum_yazma = simdi
                        self._durumlari_yaz(baglanti)
                        self._analiz_hizini_denetle(baglanti, simdi)
                    if simdi - self._son_analiz_saati_yazma >= _ANALIZ_SAATI_YAZMA_SN:
                        self._son_analiz_saati_yazma = simdi
                        self._analiz_saatlerini_yaz(baglanti)
                    if simdi - self._son_bakim >= _BAKIM_ARALIGI_SN:
                        self._son_bakim = simdi
                        self._bakimi_baslat()
                except Exception as hata:  # noqa: BLE001 - 7x24 döngüsü ölmemeli;
                    # hata tam ayrıntıyla loglanır, bir sonraki turda devam edilir
                    self._log.error(f"Analiz döngüsünde hata: {hata}", exc_info=hata)
                self._dur.wait(0.05)
        finally:
            self._analiz_saatlerini_yaz(baglanti)
            try:
                self._kapanis_olaylarini_yaz(baglanti)
            except Exception as hata:  # noqa: BLE001 - bağlantı yine kapanmalı
                self._log.error(f"Kapanış olayları yazılamadı: {hata}", exc_info=hata)
            baglanti.close()
            self._log.info("Analiz süpervizörü durdu.")

    # ---- sistem olayları ----

    def _sistem_olayi(
        self,
        baglanti,
        mesaj: str,
        *,
        kod: str,
        kamera_id: int | None = None,
        detaylar: dict | None = None,
    ) -> int | None:
        """Sistem olayını yazar; yazılamazsa günlüğe düşer ve None döner.

        Olay kaydı başarısız diye analiz durmaz (docs/17 §3.5): kilitli ya da
        dolu bir veritabanı yüzünden model atılmamalı, kamera durumları
        yazılmaya devam etmeli.
        """
        try:
            return sistem_olayi_yaz(baglanti, mesaj, kamera_id, detaylar, kod=kod)
        except sqlite3.Error as hata:
            self._log.error(
                f"Sistem olayı veritabanına yazılamadı ({kod}): {hata}",
                extra={"ayrinti": mesaj},
                exc_info=hata,
            )
            return None

    def _acilis_olaylarini_yaz(self, baglanti) -> None:
        """Önceki çalışmadan açık kalan olayları kapatır, "Sistem başladı" yazar.

        Açık kalan olay (elektrik kesintisinde "Kamera çevrimdışı" gibi) ekranda
        sonsuza kadar "sürüyor" görünürdü. Son yaşam olayı "Sistem başladı"
        ise önceki çalışma "Sistem durdu" yazamadan bitmiştir; bu da çalışma
        süresi ölçümünün (docs/17 §14) kanıtıdır ve olayda söylenir.
        """
        try:
            son = baglanti.execute(
                "SELECT event_code FROM events "
                "WHERE event_code IN ('SYSTEM_STARTED', 'SYSTEM_STOPPED') "
                "ORDER BY occurred_at DESC, id DESC LIMIT 1"
            ).fetchone()
            kapatilan = acik_olaylari_kapat(baglanti, "yeniden_baslama")
        except sqlite3.Error as hata:
            self._log.error(f"Açık kalan olaylar kapatılamadı: {hata}", exc_info=hata)
            son, kapatilan = None, 0
        mesaj = "Sistem başladı"
        detaylar: dict = {}
        if son is not None and son["event_code"] == "SYSTEM_STARTED":
            mesaj += (
                " - önceki çalışma düzgün kapanmamıştı (elektrik kesintisi ya da "
                "program çökmesi olabilir)"
            )
            detaylar["onceki_calisma"] = "duzgun_kapanmadi"
        if kapatilan:
            detaylar["kapatilan_acik_olay"] = kapatilan
        self._sistem_olayi(baglanti, mesaj, kod="SYSTEM_STARTED", detaylar=detaylar)

    def _kapanis_olaylarini_yaz(self, baglanti) -> None:
        """Düzgün kapanışta açık olayları kapatır ve "Sistem durdu" yazar."""
        try:
            kapatilan = acik_olaylari_kapat(baglanti, "kapanis")
        except sqlite3.Error as hata:
            self._log.error(f"Açık olaylar kapanışta kapatılamadı: {hata}", exc_info=hata)
            kapatilan = 0
        self._kopukluk_olaylari.clear()
        self._acik_olaylar.clear()
        self._sistem_olayi(
            baglanti,
            "Sistem durdu",
            kod="SYSTEM_STOPPED",
            detaylar={"kapatilan_acik_olay": kapatilan} if kapatilan else None,
        )

    def _kopuklugu_kapat(
        self, baglanti, kamera_id: int, sebep: str, bitis_utc: str | None = None
    ) -> None:
        """Kameranın açık "çevrimdışı" olayını (varsa) kapatır."""
        olay_id = self._kopukluk_olaylari.pop(kamera_id, None)
        if olay_id is None:
            return
        try:
            olay_kapat(baglanti, olay_id, sebep, bitis_utc)
        except sqlite3.Error as hata:
            self._log.error(
                f"Kamera çevrimdışı olayı kapatılamadı (olay {olay_id}): {hata}", exc_info=hata
            )

    def _tespitciyi_kur(self, baglanti) -> None:
        try:
            self._modeli_hazirla()
            self.tespitci = Tespitci(
                self.ayarlar.model_dosyasi,
                self.ayarlar.cikarim_cihazi,
                guven_esigi=self.ayarlar.tespit_guven_esigi,
                insan_guven_esigi=self.ayarlar.tespit_insan_guven_esigi,
                nms_esigi=self.ayarlar.tespit_nms_esigi,
                en_kucuk_kenar_px=self.ayarlar.tespit_en_kucuk_kenar_px,
                is_parcacigi=self.ayarlar.cikarim_is_parcacigi,
            )
            self.tespit_hatasi = None
            self.model_durumu = "hazir"
            if self.tespitci.cihaz_uyarisi:
                # GPU istenip CPU'ya düşülmüşse kullanıcı bunu bilmeli
                self.cihaz_uyarisi = self.tespitci.cihaz_uyarisi
                self._sistem_olayi(
                    baglanti, self.tespitci.cihaz_uyarisi, kod="INFERENCE_DEVICE_FALLBACK"
                )
        except (ModelHatasi, ModelIndirmeHatasi) as hata:
            # Model yokken sistem ÇÖKMEZ: kameralar izlenir, tespit yapılmaz.
            # Durum ana sayfada ve olay listesinde görünür.
            self.tespitci = None
            self.tespit_hatasi = hata.kullanici_mesaji
            self.model_durumu = "hata"
            # Ekranda sade mesaj, günlük DOSYASINDA tam ayrıntı (indirme
            # adresi, dosya yolu, özgün hata). Teknik metin `mesaj` alanına
            # yazılırsa Kontrol Paneli penceresinde de görünürdü.
            self._log.error(
                hata.kullanici_mesaji,
                extra={"ayrinti": hata.teknik_ayrinti},
                exc_info=hata,
            )
            self._sistem_olayi(
                baglanti,
                f"Tespit modeli yüklenemedi: {hata.kullanici_mesaji}",
                kod="MODEL_LOAD_FAILED",
            )

    def _kkd_surumunu_denetle(self, baglanti) -> None:
        """Onaylanmamış KKD model sürümüyle anons çalmaz (docs/17 §5.7-4).

        Anonsu açık (gölgede olmayan) bir KKD kuralının onaylı sürümü yüklü
        modelden farklıysa ya da hiç onaylanmamışsa kural gölgeye alınır ve
        PPE_MODEL_CHANGED yazılır. Olay kaydı sürer, yalnız hoparlör susar;
        kapı yeni sürümle yeniden ölçülür. Gölge bilgisi kural imzasına girmez:
        pencereler ve bekleme süreleri sıfırlanmaz (rules/motor.py).
        """
        if not self.kkd.model_var:
            return  # model yoksa KKD olayı da yok; onay sorusu doğmaz
        surum = self.kkd.model_surumu
        satirlar = baglanti.execute(
            "SELECT id, camera_id, approved_model_version FROM rules "
            "WHERE rule_type = 'ppe_violation' AND shadow_mode = 0 "
            "AND (approved_model_version IS NULL OR approved_model_version != ?)",
            (surum,),
        ).fetchall()
        for satir in satirlar:
            onayli = satir["approved_model_version"]
            try:
                baglanti.execute(
                    "UPDATE rules SET shadow_mode = 1, updated_at = ? WHERE id = ?",
                    (zaman.simdi_utc(), satir["id"]),
                )
                baglanti.commit()
            except sqlite3.Error as hata:
                _geri_al(baglanti)
                self._log.error(f"KKD kuralı #{satir['id']} gölgeye alınamadı: {hata}")
                continue
            if satir["id"] in self._kural_haritasi:
                self._kural_haritasi[satir["id"]]["shadow_mode"] = 1  # beklemeden sussun
            onceki = f"onaylı sürüm {onayli}" if onayli else "hiçbir sürüm onaylanmamış"
            self._sistem_olayi(
                baglanti,
                f"KKD modeli değişti ({onceki}, yüklü {surum}): KKD kuralı #{satir['id']} "
                "gölge moda alındı. Olaylar kaydedilir, anons KKD kapısı yeni sürümle "
                "ölçülene kadar çalmaz.",
                kod="PPE_MODEL_CHANGED",
                kamera_id=satir["camera_id"],
                detaylar={"kural_id": satir["id"], "onayli_surum": onayli, "yuklu_surum": surum},
            )

    def _kkd_modelini_kur(self, baglanti) -> None:
        """KKD modeli (docs/17 §5.2, §12.5). Dosya yoksa sessiz: model henüz
        eğitilmedi, KKD kuralı olay üretmez ve KKD sayfası bunu söyler. Dosya
        VAR ama doğrulanamıyorsa (özet yok ya da tutmuyor, açılmıyor, sözleşmeye
        uymuyor) MODEL_LOAD_FAILED yazılır ve modelsiz devam edilir: bölge,
        yakınlık ve hız kuralları bundan etkilenmez."""
        try:
            self.kkd = KkdSiniflandirici(self.ayarlar.kkd_model_dosyasi)
        except ModelHatasi as hata:
            self.kkd = KkdSiniflandirici(None)
            self.kkd_hatasi = hata.kullanici_mesaji
            self._log.error(hata.kullanici_mesaji, extra={"ayrinti": hata.teknik_ayrinti})
            self._sistem_olayi(baglanti, hata.kullanici_mesaji, kod="MODEL_LOAD_FAILED")
            return
        except Exception as hata:  # noqa: BLE001 - KKD modeli analizi durdurmamalı
            self.kkd = KkdSiniflandirici(None)
            self.kkd_hatasi = "KKD modeli yüklenemedi; ayrıntı sistem günlüğünde."
            self._log.error(f"KKD modeli yüklenemedi: {hata}", exc_info=hata)
            self._sistem_olayi(baglanti, self.kkd_hatasi, kod="MODEL_LOAD_FAILED")
            return
        self.kkd_hatasi = None
        if self.kkd.model_var:
            self._log.info(f"KKD modeli yüklendi: {self.kkd.model_surumu}")

    def _modeli_hazirla(self) -> None:
        """Model dosyası yoksa ve bilinen bir YOLOX modeliyse bir kez indirir.
        Kullanıcı terminalde betik çalıştırmak zorunda kalmaz (CLAUDE.md §8)."""
        dosya = self.ayarlar.model_dosyasi
        if dosya.exists():
            return
        if not indirilebilir_mi(dosya):
            # Kendi modelini koyan kullanıcı "dosya bulunamadı" yerine NE YAPACAĞINI
            # söyleyen markalı açıklamayı görsün; metin tek yerde durur.
            raise ozel_model_hatasi(dosya)
        self.model_durumu = "indiriliyor"
        self._log.info(
            f"{gorunen_model_adi(dosya.name)} ilk kez indiriliyor (bir kez, ~20-35 MB) …",
            extra={"ayrinti": f"model dosyası: {dosya}"},
        )
        son_yuzde = -1

        def ilerleme(inen: int, toplam: int) -> None:
            nonlocal son_yuzde
            if toplam <= 0:
                return
            yuzde = inen * 100 // toplam
            if yuzde // 25 != son_yuzde // 25:  # her %25'te bir satır, günlük şişmesin
                son_yuzde = yuzde
                self._log.info(f"Model indiriliyor: %{yuzde}")

        modeli_indir(dosya, ilerleme)
        self._log.info(
            f"{gorunen_model_adi(dosya.name)} indirildi.",
            extra={"ayrinti": f"model dosyası: {dosya}"},
        )

    # ---- konfigürasyon ----

    def _konfigurasyonu_yenile(self, baglanti) -> None:
        damga_satiri = baglanti.execute(
            "SELECT (SELECT COALESCE(MAX(updated_at), '') FROM cameras) || '|' || "
            "(SELECT COALESCE(MAX(updated_at), '') FROM zones) || '|' || "
            "(SELECT COALESCE(MAX(updated_at), '') FROM rules) || '|' || "
            "(SELECT COALESCE(MAX(calibrated_at), '') FROM camera_calibrations) || '|' || "
            "(SELECT COALESCE(COUNT(*), 0) FROM cameras) || '|' || "
            "(SELECT COALESCE(COUNT(*), 0) FROM zones) || '|' || "
            "(SELECT COALESCE(COUNT(*), 0) FROM rules) || '|' || "
            # Hoparlör bölgesi eklenince/değişince anons hemen doğru adrese
            # gitsin; kullanıcıdan sistemi yeniden başlatması istenmesin.
            "(SELECT COALESCE(MAX(updated_at), '') FROM speaker_zones) || '|' || "
            "(SELECT COALESCE(COUNT(*), 0) FROM speaker_zones) || '|' || "
            # Anons mesajı metni ya da WAV'ı değişince (şema 007, AUDIT R19) yeni
            # metin yeniden başlatmadan çalınsın.
            "(SELECT COALESCE(MAX(updated_at), '') FROM announcement_messages) AS damga"
        ).fetchone()
        damga = damga_satiri["damga"]
        if damga == self._konfig_damgasi:
            return
        self._log.info("Konfigürasyon değişti - yeniden yükleniyor (restart yok).")

        kameralar = self._atanmis_kameralar(baglanti)
        self._anons_mesajlari = {
            satir["id"]: dict(satir)
            for satir in baglanti.execute("SELECT * FROM announcement_messages")
        }
        self._kural_haritasi = {
            satir["id"]: {
                "shadow_mode": satir["shadow_mode"],
                "announcement_id": satir["announcement_id"],
                "severity": satir["severity"],
            }
            for satir in baglanti.execute(
                "SELECT id, shadow_mode, announcement_id, severity FROM rules"
            )
        }
        self._kkd_surumunu_denetle(baglanti)
        # Anons, ihlalin olduğu BÖLÜMÜN hoparlörüne gider (şema 002).
        # Bölge tanımlanmamışsa liste boş kalır ve .env'deki tek adres kullanılır.
        self._anons.bolgeleri_yukle(baglanti.execute("SELECT * FROM speaker_zones ORDER BY id"))

        aktif_idler = set()
        for kamera in kameralar:
            kid = kamera["id"]
            aktif_idler.add(kid)
            self._kamera_konfig[kid] = kamera

            mevcut = self._kaynaklar.get(kid)
            # Şema 006: yüklenen videoda "bitince dur / başa sar" seçimi.
            # Sütun eski veritabanlarında bulunmayabilir diye .get ile okunur.
            dongu = bool(kamera.get("loop_video", 1))
            # Döngü seçimi okuma iş parçacığının İÇİNDE karar verir; sonradan
            # değiştirilemez, o yüzden değişince kaynak yeniden kurulur.
            #
            # BİTEN VİDEONUN YENİDEN ÇALIŞMASI da aynı kapıdan geçer: iş
            # parçacığı sonlandığı için kaynak yeniden kurulmadan video bir daha
            # oynamaz. Ölçüt kameranın `updated_at` DAMGASIDIR - yani kullanıcı
            # bu kamerayı gerçekten değiştirdi mi (Yeniden Çalıştır, ad/fps
            # düzenleme). Damga yerine `status` sütununa bakılsaydı istek
            # kaybolurdu: durum yazıcı (_durumlari_yaz) konfigürasyon
            # kontrolünden daha SIK çalışır ve 'finished'ı geri yazardı.
            yeni_damga = str(kamera["updated_at"])
            adres_degisti = mevcut is not None and (
                mevcut.kaynak_url != kamera["source_url"]
                or mevcut.dongu != (dongu or kamera["source_type"] != "file")
                or (mevcut.bitti and self._kaynak_damgalari.get(kid) != yeni_damga)
            )
            if adres_degisti:
                mevcut.durdur()
                mevcut = None
                del self._kaynaklar[kid]
                # Durum makinesi baştan başlar ("bağlanıyor"); eski kaynağın
                # "çevrimdışı" olayı bir "tekrar çevrimiçi" ile kapanamaz artık.
                self._kopuklugu_kapat(baglanti, kid, "kamera_degisti")
                # Adres değiştiyse ESKİ kameranın son karesi ve takip durumu
                # yeni kameraya ait değildir: hat da sıfırlanmalı, yoksa
                # önizlemede eski görüntü ve yanlış takip id'leri sürerdi.
                self._hatti_birak(baglanti, kid, "kamera_degisti")
                self._son_islenen_kare.pop(kid, None)
                self._canli_sayim.pop(kid, None)
            if mevcut is None:
                kaynak = KameraKaynagi(
                    kid,
                    kamera["name"],
                    kamera["source_type"],
                    kamera["source_url"],
                    dongu=dongu,
                    kopuk_esigi_sn=self.ayarlar.kamera_kopuk_esigi_sn,
                    acilis_zaman_asimi_ms=self.ayarlar.rtsp_acilis_zaman_asimi_ms,
                    okuma_zaman_asimi_ms=self.ayarlar.rtsp_okuma_zaman_asimi_ms,
                )
                kaynak.baslat()
                self._kaynaklar[kid] = kaynak
                self._kaynak_damgalari[kid] = yeni_damga
                self._siradaki_ornek[kid] = 0.0
                self._son_durumlar.pop(kid, None)

            hat = self._hatlar.get(kid)
            # Örnekleme hızı değiştiyse takipçinin kare hızı da değişmeli
            if hat is not None and hat.fps != int(kamera["sample_fps"]):
                hat = None
                self._hatti_birak(baglanti, kid, "kamera_degisti")
            if hat is None:
                hat = self._yeni_hat(kid, kamera)
                self._hatlar[kid] = hat
            hat.yapilandir(
                self._bolgeleri_yukle(baglanti, kid),
                self._kurallari_yukle(baglanti, kid),
                self._kalibrasyonu_yukle(baglanti, kid),
            )
            # Değişen ya da kaldırılan kuralın açık olayı hemen kapanır
            # (kural_degisti); kamera kare vermiyor olsa bile asılı kalmaz.
            self._gecisleri_isle(baglanti, hat, time.monotonic())

        # Silinen/pasifleşen kameraların iş parçacıkları durdurulur; pasif
        # kamera listede 'çevrimiçi' görünmeye devam etmesin diye durumu sıfırlanır
        for kid in list(self._kaynaklar):
            if kid not in aktif_idler:
                self._kaynaklar.pop(kid).durdur()
                self._kopuklugu_kapat(baglanti, kid, "kamera_degisti")
                self._kaynak_damgalari.pop(kid, None)
                self._hatti_birak(baglanti, kid, "kamera_degisti")
                self._kamera_konfig.pop(kid, None)
                self._son_durumlar.pop(kid, None)
                self._canli_sayim.pop(kid, None)
                self._olcumler.pop(kid, None)
                self._ardisik_hata.pop(kid, None)
                self._yavas_baslangic.pop(kid, None)
                self._yavas_bildirildi.discard(kid)
                self._son_analiz_karesi.pop(kid, None)
                baglanti.execute(
                    "UPDATE cameras SET status = ?, measured_fps = NULL WHERE id = ?",
                    (DURUM_OFFLINE, kid),
                )
        baglanti.commit()
        # Damga ancak yenileme BAŞARIYLA bittikten sonra yazılır: ortada bir
        # hata olursa bir sonraki turda aynı değişiklik tekrar denenir, sessizce
        # yutulmaz.
        self._konfig_damgasi = damga

    def _yeni_hat(self, kid: int, kamera: dict) -> KameraHatti:
        return KameraHatti(
            kid,
            int(kamera["sample_fps"]),
            iyilestir=self.ayarlar.goruntu_iyilestirme == "otomatik",
            takip_hafiza_sn=self.ayarlar.takip_hafiza_sn,
        )

    def _atanmis_kameralar(self, baglanti) -> list[dict]:
        """Bu analizörün ilgilendiği kameralar (ADR-008): bugün 'tüm aktifler'.

        Fabrika geneline çıkarken bölümlendirme YALNIZCA bu fonksiyonu değiştirir.
        """
        return [
            dict(satir) for satir in baglanti.execute("SELECT * FROM cameras WHERE enabled = 1")
        ]

    def _bolgeleri_yukle(self, baglanti, kamera_id: int) -> list[Bolge]:
        bolgeler = []
        for satir in baglanti.execute("SELECT * FROM zones WHERE camera_id = ?", (kamera_id,)):
            # Şema 007'den sonra veritabanında tip denetimi (CHECK) yoktur; elle
            # ya da eski bir sürümle yazılmış bilinmeyen tip burada ayıklanır.
            # Atlanır, kamera durmaz: bilinmeyen tip hiçbir kurala girmemeli.
            if satir["zone_type"] not in BOLGE_TIPI_KODLARI:
                self._log.warning(
                    f"Bilinmeyen bölge tipi atlandı (bölge {satir['id']}): {satir['zone_type']!r}"
                )
                continue
            try:
                poligon = [tuple(nokta) for nokta in json.loads(satir["polygon"])]
            except (json.JSONDecodeError, TypeError) as hata:
                self._log.error(f"Bölge poligonu bozuk (id {satir['id']}): {hata}")
                continue
            bolgeler.append(
                Bolge(
                    id=satir["id"],
                    tip=satir["zone_type"],
                    poligon=poligon,
                    aktif=bool(satir["enabled"]),
                )
            )
        return bolgeler

    def _kurallari_yukle(self, baglanti, kamera_id: int) -> list[Kural]:
        kurallar = []
        for satir in baglanti.execute(
            "SELECT * FROM rules WHERE camera_id = ? AND enabled = 1", (kamera_id,)
        ):
            try:
                params = params_dogrula(satir["rule_type"], json.loads(satir["params"]))
                hedefler = json.loads(satir["target_classes"])
            except (KuralParametreHatasi, json.JSONDecodeError) as hata:
                self._log.error(f"Kural {satir['id']} yüklenemedi, atlandı: {hata}")
                continue
            kurallar.append(
                Kural(
                    id=satir["id"],
                    kamera_id=kamera_id,
                    tip=satir["rule_type"],
                    bolge_id=satir["zone_id"],
                    hedef_siniflar=hedefler,
                    params=params,
                    cooldown_s=float(satir["cooldown_s"]),
                    anons_id=satir["announcement_id"],
                    siddet=satir["severity"],
                )
            )
        return kurallar

    def _kalibrasyonu_yukle(self, baglanti, kamera_id: int) -> Kalibrasyon | None:
        satir = baglanti.execute(
            "SELECT homography FROM camera_calibrations WHERE camera_id = ?", (kamera_id,)
        ).fetchone()
        if satir is None:
            return None
        try:
            return Kalibrasyon(homografi=json.loads(satir["homography"]))
        except (json.JSONDecodeError, TypeError) as hata:
            self._log.error(f"Kalibrasyon bozuk (kamera {kamera_id}): {hata}")
            return None

    # ---- kare işleme ----

    def _kameralari_isle(self, baglanti, simdi: float) -> None:
        for kid, kaynak in list(self._kaynaklar.items()):
            konfig = self._kamera_konfig.get(kid)
            if konfig is None:
                continue
            fps = max(float(konfig["sample_fps"]), 0.1)
            if simdi < self._siradaki_ornek.get(kid, 0.0):
                continue
            self._siradaki_ornek[kid] = simdi + 1.0 / fps

            kare, kare_zamani = kaynak.son_kare()
            if kare is None or kare_zamani <= self._son_islenen_kare.get(kid, 0.0):
                continue  # yeni kare yok - aynı kareyi iki kez işleme
            self._son_islenen_kare[kid] = kare_zamani

            hat = self._hatlar[kid]
            olcum = self._olcumler.setdefault(kid, _KameraOlcumu())
            baslangic = time.perf_counter()
            try:
                # Kurala KARENİN zamanı gider, işlendiği an değil (AUDIT R29):
                # kare kuyrukta beklediyse hız hesabındaki dt ve kalış süresi
                # kayardı. İkisi de aynı monotonic saattendir.
                tespitler, ihlaller = hat.isle(kare, kare_zamani, self.tespitci, self.kkd)
            except Exception as hata:  # noqa: BLE001 - kamera izolasyonu:
                # bir kameranın işleme hatası diğerlerini durdurmamalı
                self._log.error(f"Kare işlenemedi (kamera {kid}): {hata}", exc_info=hata)
                self._isleme_hatasi(baglanti, kid)
                continue
            self._ardisik_hata.pop(kid, None)
            olcum.isle_ms.append((time.perf_counter() - baslangic) * 1000)
            olcum.islenen.append(simdi)
            self._analiz_saati_ekle(kid, simdi)

            # Canlı sayım: takip edilen nesneler (kare başına ham tespit değil)
            sayim: dict[str, int] = {}
            for tespit in tespitler:
                sayim[tespit.sinif] = sayim.get(tespit.sinif, 0) + 1
            self._canli_sayim[kid] = sayim

            # İhlal listesi önizleme çizimi içindir; OLAYLAR geçişlerden doğar
            # (açıldı / hatırlatma / kapandı, rules/olay_durumu.py).
            del ihlaller
            self._gecisleri_isle(baglanti, hat, simdi, kare_zamani)
            self._kkd_ornekle(baglanti, kid, kare, tespitler, hat, simdi)

    # ---- analiz sağlığı (docs/17 §3.6) ----

    def _isleme_hatasi(self, baglanti, kid: int) -> None:
        """Üst üste ANALIZ_HATA_ESIGI kare işlenemezse kameranın hattı yeniden
        kurulur ve ANALYSIS_DEGRADED yazılır. Eskiden hata yalnız günlükte
        kalıyor, kamera sessizce analizsiz akıyordu."""
        self._analiz_saati_ekle(kid, None)
        sayi = self._ardisik_hata.get(kid, 0) + 1
        self._ardisik_hata[kid] = sayi
        if sayi < self.ayarlar.analiz_hata_esigi:
            return
        self._ardisik_hata[kid] = 0
        konfig = self._kamera_konfig.get(kid)
        if konfig is None:
            return
        self._log.critical(
            f"Kamera {kid}: {sayi} kare üst üste işlenemedi - işleme hattı yeniden kuruluyor."
        )
        # Yeni hat ÖNCE kurulur: yapılandırma başarısız olursa eski hat kalır
        yeni = self._yeni_hat(kid, konfig)
        yeni.yapilandir(
            self._bolgeleri_yukle(baglanti, kid),
            self._kurallari_yukle(baglanti, kid),
            self._kalibrasyonu_yukle(baglanti, kid),
        )
        self._hatti_birak(baglanti, kid, "hat_yenilendi")
        self._hatlar[kid] = yeni
        self._sistem_olayi(
            baglanti,
            f"Analiz yavaşladı: {konfig.get('name', kid)} kamerasında {sayi} görüntü üst "
            "üste işlenemedi; kameranın işleme hattı yeniden kuruldu.",
            kamera_id=kid,
            detaylar={"sebep": "isleme_hatasi", "ardisik_hata": sayi},
            kod="ANALYSIS_DEGRADED",
        )

    def _analiz_hizini_denetle(self, baglanti, simdi: float) -> None:
        """İşlenen hız hedefin FPS_UYARI_ORANI'nın altında ANALIZ_YAVAS_SURE_SN
        kalırsa ANALYSIS_DEGRADED (kamera başına bir kez; hız düzelince yeniden).

        Hedef, ayarlanan örnekleme hızı ile kameranın gerçekten verdiği hızın
        küçüğüdür: saniyede 3 kare veren kameradan 6 kare işlenemez, bu analiz
        yavaşlığı değildir. Model yokken hız ölçülmez.
        """
        if self.tespitci is None:
            return
        for kid, kaynak in list(self._kaynaklar.items()):
            konfig = self._kamera_konfig.get(kid)
            if konfig is None or kaynak.durum(simdi) != DURUM_ONLINE:
                self._yavas_baslangic.pop(kid, None)
                continue
            hedef = _islenen_hedefi(konfig, kaynak)
            olcum = self._olcumler.get(kid)
            islenen = olcum.islenen_fps(simdi) if olcum is not None else 0.0
            if islenen >= hedef * self.ayarlar.fps_uyari_orani:
                self._yavas_baslangic.pop(kid, None)
                self._yavas_bildirildi.discard(kid)
                continue
            baslangic = self._yavas_baslangic.setdefault(kid, simdi)
            if (
                kid in self._yavas_bildirildi
                or simdi - baslangic < self.ayarlar.analiz_yavas_sure_sn
            ):
                continue
            self._yavas_bildirildi.add(kid)
            islenen_metni = f"{islenen:.1f}".replace(".", ",")
            hedef_metni = f"{hedef:.1f}".replace(".", ",")
            self._sistem_olayi(
                baglanti,
                f"Analiz yavaşladı: {konfig.get('name', kid)} kamerasında saniyede "
                f"{islenen_metni} görüntü işleniyor, hedef {hedef_metni}. Uyarılar gecikebilir.",
                kamera_id=kid,
                detaylar={
                    "sebep": "yavas",
                    "islenen_fps": round(islenen, 1),
                    "hedef_fps": round(hedef, 1),
                },
                kod="ANALYSIS_DEGRADED",
            )

    def _analiz_saati_ekle(self, kid: int, simdi: float | None) -> None:
        """analysis_hours birikimi. `simdi` None ise kare işlenemedi demektir.

        Yalnız tespit modeli yüklüyken işlenen kare sayılır: model yokken
        görüntü akar ama analiz edilmez. Analiz edilen süre, ardışık iki
        işlenmiş kare arasındaki süredir; _ANALIZ_BOSLUK_SN'den uzun boşluk
        (kopukluk, takılma) sayılmaz.
        """
        kova = self._analiz_saatleri.setdefault((kid, zaman.simdi_utc()[:13]), [0.0, 0, 0])
        if simdi is None:
            kova[2] += 1
            return
        if self.tespitci is None:
            self._son_analiz_karesi.pop(kid, None)
            return
        kova[1] += 1
        onceki = self._son_analiz_karesi.get(kid)
        self._son_analiz_karesi[kid] = simdi
        if onceki is not None and 0 < simdi - onceki <= _ANALIZ_BOSLUK_SN:
            kova[0] += simdi - onceki

    def _analiz_saatlerini_yaz(self, baglanti) -> None:
        """Birikimi upsert eder; yazılamazsa kaybetmez, bir sonraki turda dener."""
        if not self._analiz_saatleri:
            return
        kovalar, self._analiz_saatleri = self._analiz_saatleri, {}
        try:
            baglanti.executemany(
                _ANALIZ_SAATI_UPSERT,
                [
                    (kid, saat, round(sure, 3), islenen, basarisiz)
                    for (kid, saat), (sure, islenen, basarisiz) in kovalar.items()
                ],
            )
            baglanti.commit()
        except sqlite3.Error as hata:
            _geri_al(baglanti)
            for anahtar, degerler in kovalar.items():
                kova = self._analiz_saatleri.setdefault(anahtar, [0.0, 0, 0])
                for i, deger in enumerate(degerler):
                    kova[i] += deger
            self._log.error(f"Analiz saatleri yazılamadı, sonra denenecek: {hata}")

    # ---- olay yaşam döngüsü ----

    def _gecisleri_isle(
        self, baglanti, hat: KameraHatti, simdi: float, kare_zamani: float | None = None
    ) -> None:
        """Hattın olay geçişlerini veritabanına ve anonsa taşır (docs/17 §6.3).

        açıldı → yeni olay satırı (bitişi boş) + anons; hatırlatma → yeni satır
        YOK, yalnız anons (S17); kapandı → satıra bitiş ve sebep. Bir geçişin
        veritabanı hatası diğerlerini düşürmez: her biri ayrı denenir.
        """
        for gecis in hat.gecisleri_al():
            try:
                self._gecisi_isle(baglanti, hat, gecis, simdi, kare_zamani)
            except sqlite3.Error as hata:
                self._log.error(
                    f"Olay geçişi veritabanına yazılamadı ({gecis.asama}, anahtar "
                    f"{gecis.anahtar}): {hata}",
                    exc_info=hata,
                )

    def _gecisi_isle(
        self,
        baglanti,
        hat: KameraHatti,
        gecis: OlayGecisi,
        simdi: float,
        kare_zamani: float | None = None,
    ) -> None:
        if gecis.asama == KAPANDI:
            self._olayi_kapat(baglanti, gecis)
        elif gecis.asama == HATIRLATMA and gecis.anahtar in self._acik_olaylar:
            olay_id = self._acik_olaylar[gecis.anahtar]
            self._log.info(f"İhlal sürüyor (olay {olay_id}) - anons tekrarlanıyor.")
            self._duyur(
                gecis.ihlal,
                self._kural_kaydini_al(baglanti, gecis.ihlal.kural_id),
                simdi,
                olay_id=olay_id,
                asama=HATIRLATMA,
                kare_zamani=kare_zamani,
            )
        elif gecis.asama in (ACILDI, HATIRLATMA):
            # Hatırlatma ama satır yok: açılış yazılamamıştı; olay şimdi yazılır
            olay_id = self._ihlali_kaydet(
                baglanti, hat, gecis.ihlal, simdi, suruyor=True, kare_zamani=kare_zamani
            )
            if olay_id is not None:
                self._acik_olaylar[gecis.anahtar] = olay_id

    def _olayi_kapat(self, baglanti, gecis: OlayGecisi) -> None:
        olay_id = self._acik_olaylar.pop(gecis.anahtar, None)
        if olay_id is None:
            return  # açılışı yazılamamış olay: kapatılacak satır yok
        # Bitiş, koşulun son görüldüğü an: kare zamanı monotonik saattedir.
        bitis = (
            zaman.saniye_once_utc(time.monotonic() - gecis.son_aktif_s)
            if gecis.son_aktif_s is not None
            else None
        )
        olay_kapat(baglanti, olay_id, gecis.sebep, bitis)
        self._log.info(f"Olay bitti (olay {olay_id}, sebep {gecis.sebep}).")

    def _hatti_birak(self, baglanti, kamera_id: int, sebep: str) -> None:
        """Kameranın hattını atar; açık ihlal olayları son görüldükleri anda biter."""
        hat = self._hatlar.pop(kamera_id, None)
        if hat is None:
            return
        for gecis in hat.olaylari_birak(sebep):
            try:
                self._olayi_kapat(baglanti, gecis)
            except sqlite3.Error as hata:
                self._log.error(f"Olay kapatılamadı (kamera {kamera_id}): {hata}", exc_info=hata)

    def _ihlali_kaydet(
        self,
        baglanti,
        hat: KameraHatti,
        ihlal,
        simdi: float,
        *,
        suruyor: bool = False,
        kare_zamani: float | None = None,
    ) -> int | None:
        """İhlali kaydeder ve duyurur; kayıt başarısız olsa da DUYURUR (docs/17 §3.5).

        Sıra güvenlik içindir. Eskiden kural satırı ya da olay satırı yazılamazsa
        (kilitli veritabanı, dolu disk) istisna anonsa hiç ulaşmadan döngüde
        yutuluyordu: ihlal ne kayda geçiyor ne duyuruluyordu. Şimdi kural satırı
        okunamazsa gölge/anons kararı bellekteki haritadan verilir; olay satırı
        yazılamazsa CRITICAL günlük ve /saglik "olay_yazilamadi" - ama anons yine
        çalar. Dönen değer olay id'si; yazılamadıysa None.
        """
        kural_kaydi = self._kural_kaydini_al(baglanti, ihlal.kural_id)
        olay_id = None
        baslangic = time.perf_counter()
        try:
            olay_id = ihlal_yaz(
                baglanti,
                self.ayarlar,
                ihlal,
                kural_kaydi,
                hat.son_islenmis_jpeg(),
                suruyor=suruyor,
            )
        except Exception as hata:  # noqa: BLE001 - kayıt hatası uyarıyı susturmamalı
            self.olay_yazma_hatasi = f"{type(hata).__name__}: {hata}"
            self._log.critical(
                f"İhlal olayı KAYDEDİLEMEDİ (kamera {ihlal.kamera_id}, kural "
                f"{ihlal.kural_id}); uyarı yine de duyuruluyor: {hata}",
                exc_info=hata,
            )
            _geri_al(baglanti)
        else:
            self.olay_yazma_hatasi = None
            self._olcumler.setdefault(ihlal.kamera_id, _KameraOlcumu()).ihlal_yaz_ms.append(
                (time.perf_counter() - baslangic) * 1000
            )
            self._log.info(
                f"İhlal kaydedildi (olay {olay_id}, kamera {ihlal.kamera_id}, "
                f"kural {ihlal.kural_id})"
            )
        # Olay satırı yazılamadıysa olay_id None: teslim kaydı yine yazılır
        # (event_id NULL, docs/17 §3.5 ve şema 009)
        self._duyur(ihlal, kural_kaydi, simdi, olay_id=olay_id, kare_zamani=kare_zamani)
        return olay_id

    def _kural_kaydini_al(self, baglanti, kural_id: int) -> dict:
        """Kural satırı; okunamazsa bellekteki harita (anlık görüntü eksik kalır).

        Okunabildiğinde satır tercih edilir: gölge modu açıp kapatmak bir
        sonraki ihlalde hemen etkili olsun.
        """
        try:
            return self._kural_kaydi(baglanti, kural_id)
        except Exception as hata:  # noqa: BLE001 - kural okunamadı diye uyarı susmamalı
            self._log.critical(
                f"Kural {kural_id} satırı okunamadı; gölge ve anons kararı bellekten "
                f"veriliyor: {hata}",
                exc_info=hata,
            )
            _geri_al(baglanti)
            return {"id": kural_id, **self._kural_haritasi.get(kural_id, {})}

    def sorunlar(self) -> list[str]:
        """/saglik "sorunlar" listesine süpervizörün kodları (docs/17 §9.1)."""
        sorunlar = [self.bekci.sorun] if self.bekci.sorun else []
        if self.model_durumu == "hata":
            sorunlar.append("model_yuklenemedi")
        if self.olay_yazma_hatasi:
            sorunlar.append("olay_yazilamadi")
        if getattr(self.tespitci, "ort_paket_cakismasi", False):
            sorunlar.append("ort_paket_cakismasi")
        return sorunlar

    def analiz_tur_yasi(self) -> float | None:
        """Analiz döngüsünün son turu kaç saniye önce başladı (tur yoksa None)."""
        nabiz = self.nabiz
        return None if nabiz is None else round(time.monotonic() - nabiz, 1)

    def kamera_saglik_ozeti(self) -> list[dict]:
        """/saglik?ayrinti=1 ve Komuta → Sağlık için kamera başına ölçüm.

        Okunan hız kameranın verdiği, işlenen hız analizin yetiştirdiğidir
        (R12: ikisi eskiden karışıyordu). Kamera adı YOK: yalnız id.
        """
        simdi = time.monotonic()
        ozet = []
        for kid, kaynak in sorted(list(self._kaynaklar.items())):
            _, kare_zamani = kaynak.son_kare()
            olcum = self._olcumler.get(kid)
            konfig = self._kamera_konfig.get(kid)
            islenen = olcum.islenen_fps(simdi) if olcum else 0.0
            hedef = _islenen_hedefi(konfig, kaynak) if konfig else None
            ozet.append(
                {
                    "id": kid,
                    "durum": kaynak.durum(simdi),
                    "okunan_fps": round(kaynak.olculen_fps, 1),
                    "islenen_fps": round(islenen, 1),
                    "hedef_fps": round(hedef, 1) if hedef else None,
                    # ANALYSIS_DEGRADED ile aynı ölçüt; yalnız görüntü akarken
                    "yavas": bool(
                        hedef
                        and kaynak.durum(simdi) == DURUM_ONLINE
                        and islenen < hedef * self.ayarlar.fps_uyari_orani
                    ),
                    "isle_p50_ms": _yuzdelik(olcum.isle_ms, 50) if olcum else None,
                    "isle_p90_ms": _yuzdelik(olcum.isle_ms, 90) if olcum else None,
                    "son_kare_yasi_sn": round(simdi - kare_zamani, 1) if kare_zamani > 0 else None,
                }
            )
        return ozet

    def _duyur(
        self,
        ihlal,
        kural_kaydi: dict,
        simdi: float,
        *,
        olay_id: int | None = None,
        asama: str = ACILDI,
        kare_zamani: float | None = None,
    ) -> None:
        # Kamera konfigürasyonu _atanmis_kameralar()'tan gelen dict'tir;
        # bölüm adı anonsun HANGİ kanallara gideceğini belirler.
        konfig = self._kamera_konfig.get(ihlal.kamera_id) or {}
        anons_id = kural_kaydi.get("announcement_id")
        olay = OlayBilgisi(
            olay_id=olay_id,
            kod=ihlal.kod or None,
            onem=ihlal.onem or "medium",
            asama=asama,
            kare_zamani=kare_zamani,
        )
        # GÖLGE MOD (şema 002): kural çalışır ve olay yazılır, ama hoparlör
        # susar. Yeni kurulan bir kuralın güvenli deneme yoludur (docs/04 §8.2:
        # KKD 3 gün "aktif ama anonssuz" çalışır, precision ölçülür, sonra anons
        # açılır). Kural motoruna DOKUNULMAZ: karar yine kural motorundan gelir,
        # burada yalnızca duyurma adımı atlanır. Hatırlatma da aynı kapıdan geçer.
        # "Çalsaydı" hangi kanallardan çalacağı teslim kaydına `shadow` diye düşer.
        if kural_kaydi.get("shadow_mode"):
            self._log.info(f"Kural {ihlal.kural_id} gölge modda - anons çalınmadı.")
            self._anons.golge_kaydet(
                ihlal.kamera_id,
                konfig.get("area", ""),
                self._anons_mesajlari.get(anons_id) if anons_id else None,
                olay=olay,
            )
            return
        if asama == ACILDI:
            self._anons.ekran_kaydet(olay)  # ekran kanalı: bilgi, garantiye sayılmaz
        if anons_id:
            self._anons.duyur(
                ihlal.kamera_id,
                konfig.get("area", ""),
                simdi,
                self._anons_mesajlari.get(anons_id),
                olay=olay,
            )

    def _kural_kaydi(self, baglanti, kural_id: int) -> dict:
        satir = baglanti.execute("SELECT * FROM rules WHERE id = ?", (kural_id,)).fetchone()
        if satir is None:
            return {"id": kural_id}
        kayit = dict(satir)
        for alan in ("params", "target_classes"):
            try:
                kayit[alan] = json.loads(kayit[alan])
            except (json.JSONDecodeError, TypeError):
                pass  # ham metin kalsın - olay kaydı yine de anlamlı
        return kayit

    def _kkd_ornekle(
        self, baglanti, kamera_id: int, kare, tespitler, hat: KameraHatti, simdi: float
    ) -> None:
        """KKD bölgesindeki kişilerden saatlik limitle veri örnekler (docs/04 §4.3).

        KVKK tabanı (docs/17 §5.8): örnek yalnız veri toplama kapısı AÇIKKEN
        alınır ve kapı örnek yazılmadan HEMEN önce okunur - kapatma gecikmesizdir,
        yeniden başlatma gerekmez. Muaf alandaki kişiden (kabin) ve KKD kuralının
        en küçük kişi boyundan kısa kişiden örnek alınmaz: küçük görüntü eğitimde
        işe yaramaz, yalnız kişisel veri biriktirirdi.
        """
        en_az_aralik = 3600.0 / self.ayarlar.kkd_ornek_saat_limit
        if simdi - self._son_kkd_ornek.get(kamera_id, 0.0) < en_az_aralik:
            return
        boyut = (float(kare.shape[1]), float(kare.shape[0]))
        for tespit in tespitler:
            if tespit.sinif != SINIF_INSAN or not hat.kkd_bolgesinde_mi(tespit, boyut):
                continue
            if tespit.kutu[3] - tespit.kutu[1] < hat.kkd_ornek_en_kucuk_boy():
                continue
            # Deneme sayılır: kapı kapalıyken de bir sonraki deneme saatlik
            # limitle gelir, satır her karede okunmaz.
            self._son_kkd_ornek[kamera_id] = simdi
            if not self._kkd_toplama_acik_mi(baglanti):
                return
            kirpik = kisi_kirp(kare, tespit.kutu)
            if kirpik is None:
                continue
            boy_px = round(tespit.kutu[3] - tespit.kutu[1])
            self._kkd_ornek_kaydet(baglanti, kamera_id, kirpik, boy_px, netlik_olc(kirpik))
            break  # bu turda tek örnek yeter

    def _kkd_toplama_acik_mi(self, baglanti) -> bool:
        """KKD veri toplama kapısı (ppe_collection_gate, şema 007). Okunamazsa
        KAPALI sayılır: şüphede kişisel veri toplanmaz."""
        try:
            satir = baglanti.execute(
                "SELECT enabled FROM ppe_collection_gate WHERE id = 1"
            ).fetchone()
        except sqlite3.Error as hata:
            self._log.error(f"KKD veri toplama kapısı okunamadı; toplanmıyor: {hata}")
            return False
        return bool(satir and satir["enabled"])

    def _kkd_ornek_kaydet(
        self, baglanti, kamera_id: int, kirpik, boy_px: int, netlik: float
    ) -> None:
        import cv2

        simdi_utc = zaman.simdi_utc()
        goreli = str(
            Path("kkd-ornekler")
            / simdi_utc[:7]
            / f"{simdi_utc.replace(':', '-').replace('+', 'Z')}-k{kamera_id}.jpg"
        )
        tam_yol = self.ayarlar.goruntu_klasoru / goreli
        try:
            tam_yol.parent.mkdir(parents=True, exist_ok=True)
            # cv2.imwrite YERİNE imencode + write_bytes: imwrite yolu işletim
            # sisteminin ANSI kod sayfasıyla kodlar ve Türkçe karakter içeren
            # bir yolda (C:\Users\Gökhan\...) hata FIRLATMADAN False döner.
            # Sonuç: veritabanında var görünen ama diskte olmayan örnekler.
            tamam, tampon = cv2.imencode(".jpg", kirpik)
            if not tamam:
                self._log.error(
                    "KKD örneği kaydedilemedi (görüntü kodlanamadı).",
                    extra={"ayrinti": f"dosya: {tam_yol}"},
                )
                return
            tam_yol.write_bytes(tampon.tobytes())
        except (OSError, cv2.error) as hata:
            self._log.error(
                f"KKD örneği diske yazılamadı: {hata}",
                extra={"ayrinti": f"dosya: {tam_yol}"},
            )
            return
        # Kamera bu arada silinmiş olabilir (konfig penceresi) - FK hatası yerine
        # örnek kamerasız kaydedilir; eğitim verisi yine de değerlidir.
        kamera_var = baglanti.execute("SELECT 1 FROM cameras WHERE id = ?", (kamera_id,)).fetchone()
        # Boy ve netlik veri setinde kırılım olur (şema 008): hangi boydaki
        # ve netlikteki kişide modelin yanıldığı ancak böyle görülür
        baglanti.execute(
            "INSERT INTO ppe_samples (camera_id, captured_at, crop_path, source, "
            "person_height_px, sharpness) VALUES (?, ?, ?, 'auto', ?, ?)",
            (kamera_id if kamera_var else None, simdi_utc, goreli, boy_px, round(netlik, 1)),
        )
        baglanti.commit()

    # ---- durum yazımı ----

    def _durumlari_yaz(self, baglanti) -> None:
        """Üç durum: connecting (ilk 60 sn, olay yok) / online / offline.

        Olay yalnızca GERÇEK geçişlerde üretilir: 'çevrimdışı' ilk bağlantı
        süresi dolunca ya da akan görüntü kesilince; 'tekrar çevrimiçi' yalnız
        çevrimdışından dönüşte. Yeni eklenen ya da yeniden başlatılan sistemde
        henüz bağlanmakta olan kamera olay üretmez.

        'Tekrar çevrimiçi' ancak görüntü KAMERA_UP_KARARLILIK_SN boyunca
        kesintisiz akınca yazılır (docs/17 K8). Gidip gelen bir bağlantı
        (her iki saniyede bir kopan kablo) aksi halde Olaylar'ı dakikada
        onlarca çevrimdışı/çevrimiçi satırıyla doldururdu. Karar burada verilir,
        kamera.durum()'da değil: ekrandaki durum anlıktır, olay kararlıdır.
        """
        for kid, kaynak in self._kaynaklar.items():
            durum = kaynak.durum()
            onceki = self._son_durumlar.get(kid)
            if (
                durum == DURUM_ONLINE
                and onceki == DURUM_OFFLINE
                and kaynak.kesintisiz_akis_sn() < self.ayarlar.kamera_up_kararlilik_sn
            ):
                # Geçiş henüz kesinleşmedi: olay yok, önceki durum korunur.
                # Akış bu arada yine koparsa hiç olay yazılmamış olur.
                durum_olayi = onceki
            else:
                durum_olayi = durum
            if durum_olayi != onceki:
                self._son_durumlar[kid] = durum_olayi
                ad = self._kamera_konfig.get(kid, {}).get("name", kid)
                if durum != DURUM_OFFLINE:
                    # "Kamera çevrimdışı" SÜREN bir olaydır (docs/17 §6.1): görüntü
                    # geri geldiği an biter - fark edildiği an değil, kararlılık
                    # süresi kadar önce. Video bittiyse de kopukluk sona ermiştir.
                    self._kopuklugu_kapat(
                        baglanti,
                        kid,
                        "kosul_bitti",
                        zaman.saniye_once_utc(kaynak.kesintisiz_akis_sn()),
                    )
                if durum == DURUM_BITTI:
                    # "Çevrimdışı" DEĞİL: video planlandığı gibi bitti. Aynı
                    # cümle kullanılsaydı kullanıcı bozulduğunu sanıp aramaya
                    # koyulurdu (docs/12 - dürüst geri bildirim).
                    self._log.info(f"Video analizi tamamlandı: {ad}")
                    self._sistem_olayi(
                        baglanti,
                        f"Video analizi tamamlandı: {ad}",
                        kod="VIDEO_FINISHED",
                        kamera_id=kid,
                    )
                elif durum == DURUM_OFFLINE:
                    sebep = f" - {kaynak.son_hata}" if kaynak.son_hata else ""
                    self._log.warning(f"Kamera çevrimdışı: {ad}{sebep}")
                    olay_id = self._sistem_olayi(
                        baglanti,
                        f"Kamera çevrimdışı: {ad}{sebep}",
                        kod="CAMERA_DOWN",
                        kamera_id=kid,
                    )
                    if olay_id is not None:
                        self._kopukluk_olaylari[kid] = olay_id
                    # Görüntü yokken ihlalin sürüp sürmediği bilinemez: açık
                    # ihlal olayları son görüldükleri anda biter. Kamera dönüp
                    # kişi hâlâ oradaysa kural yeniden ihlal üretir.
                    hat = self._hatlar.get(kid)
                    if hat is not None:
                        for gecis in hat.olaylari_birak("kamera_koptu"):
                            self._olayi_kapat(baglanti, gecis)
                elif durum == DURUM_ONLINE and onceki == DURUM_OFFLINE:
                    self._log.info(f"Kamera tekrar çevrimiçi: {ad}")
                    self._sistem_olayi(
                        baglanti,
                        f"Kamera tekrar çevrimiçi: {ad}",
                        kod="CAMERA_UP",
                        kamera_id=kid,
                    )
            if durum == DURUM_ONLINE:
                baglanti.execute(
                    "UPDATE cameras SET status = ?, last_frame_at = ?, measured_fps = ? "
                    "WHERE id = ?",
                    (durum, zaman.simdi_utc(), round(kaynak.olculen_fps, 1), kid),
                )
            else:
                # last_frame_at KORUNUR: "en son ne zaman görüntü geldi" bilgisi
                # kamera koptuğunda en çok ihtiyaç duyulan bilgidir; silinmez.
                baglanti.execute(
                    "UPDATE cameras SET status = ?, measured_fps = NULL WHERE id = ?",
                    (durum, kid),
                )
        baglanti.commit()

    # ---- bakım (retention + disk) ----

    def _bakimi_baslat(self) -> None:
        """Bakımı KENDİ iş parçacığında çalıştırır: binlerce dosya silmek
        dakikalar sürebilir; kare işleme bu sürede durmamalı."""
        if getattr(self, "_bakim_calisiyor", False):
            return
        self._bakim_calisiyor = True

        def _calistir() -> None:
            # Bağlantı açılışı da try İÇİNDE: açılış hatası (bozuk DB, izin)
            # yakalanmazsa bayrak True'da takılı kalır ve bakım restart'a
            # kadar sessizce devre dışı kalırdı.
            bakim_baglantisi = None
            try:
                bakim_baglantisi = veritabani.baglanti_ac(self.ayarlar.veritabani_yolu)
                self._bakim_yap(bakim_baglantisi)
            except Exception as hata:  # noqa: BLE001 - bakım hatası sistemi durdurmaz
                self._log.error(f"Bakım hatası: {hata}", exc_info=hata)
            finally:
                if bakim_baglantisi is not None:
                    bakim_baglantisi.close()
                self._bakim_calisiyor = False

        threading.Thread(target=_calistir, name="bakim", daemon=True).start()

    def _bakim_yap(self, baglanti) -> None:
        a = self.ayarlar
        sinir = zaman.gun_once_utc(a.olay_saklama_gun)
        silinen_olay = baglanti.execute(
            "DELETE FROM events WHERE event_type = 'violation' AND occurred_at < ?",
            (sinir,),
        ).rowcount
        silinen_sistem = baglanti.execute(
            "DELETE FROM events WHERE event_type = 'system' AND occurred_at < ?",
            (zaman.gun_once_utc(a.sistem_olay_saklama_gun),),
        ).rowcount
        # Teslim kaydı olayla birlikte gider (ON DELETE CASCADE); olay satırı
        # olmayanlar (fail-safe, test sesi) ihlal saklama süresiyle silinir.
        baglanti.execute("DELETE FROM alert_deliveries WHERE queued_at < ?", (sinir,))
        baglanti.commit()

        silinen_foto = self._eski_dosyalari_sil(
            a.goruntu_klasoru, a.goruntu_saklama_gun, a.nesne_klasoru
        )
        # Dosya silindiği halde events.snapshot_path dolu kalırsa olay ekranında
        # kırık resim görünür; kaydı da temizle (olayın kendisi korunur).
        baglanti.execute(
            "UPDATE events SET snapshot_path = NULL "
            "WHERE snapshot_path IS NOT NULL AND occurred_at < ?",
            (zaman.gun_once_utc(a.goruntu_saklama_gun),),
        )
        baglanti.commit()
        silinen_kkd = self._kkd_hamlarini_sil(baglanti)

        import shutil as _shutil

        bos_gb = _shutil.disk_usage(a.veri_dizini).free / (1024**3)
        self._log.info(
            f"Bakım: {silinen_olay} olay, {silinen_sistem} sistem olayı, "
            f"{silinen_foto} fotoğraf, {silinen_kkd} KKD örneği silindi; "
            f"boş disk {bos_gb:.1f} GB"
        )
        if bos_gb < a.disk_uyari_gb:
            self._sistem_olayi(
                baglanti,
                f"Disk azalıyor: {bos_gb:.1f} GB kaldı (uyarı eşiği {a.disk_uyari_gb} GB). "
                "Saklama sürelerini kısaltmayı veya disk açmayı değerlendirin.",
                kod="DISK_LOW",
            )

    def _eski_dosyalari_sil(self, klasor: Path, gun: int, nesne_klasoru: Path) -> int:
        """Eski OLAY fotoğraflarını siler.

        kkd-ornekler/ alt ağacına DOKUNMAZ: etiketli örnekler eğitim veri
        setidir ve asla silinmez; etiketsizlerin süresi _kkd_hamlarini_sil
        tarafından ayrı (daha kısa) politika ile yönetilir (docs/06 §5).

        `nesne_klasoru` ağacına da DOKUNMAZ (.env → NESNE_KLASORU): oradaki
        fotoğrafları kullanıcı kendi eliyle yükledi, onlar kanıt değil TANIM.
        Klasör varsayılan yerleşimde zaten görüntü klasörünün dışındadır; bu
        kontrol, iki klasörü iç içe ayarlayan bir kurulumda da korur. Korunan
        klasör parametre olarak GEÇİLİR (self.ayarlar'dan okunmaz): bakım
        mantığı, çağıranın hangi klasörü koruduğunu görünür kılsın.
        """
        sinir = time.time() - gun * 86400
        kkd_klasoru = klasor / "kkd-ornekler"
        nesne_kok = nesne_klasoru.resolve()
        sayi = 0
        for dosya in klasor.rglob("*.jpg"):
            if dosya.is_relative_to(kkd_klasoru) or dosya.resolve().is_relative_to(nesne_kok):
                continue
            try:
                if dosya.stat().st_mtime < sinir:
                    dosya.unlink()
                    sayi += 1
            except OSError:
                # Windows'ta başka bir işlemin (Defender, yedekleme, dizin
                # oluşturucu) açık tuttuğu dosya PermissionError verir.
                # Yalnızca FileNotFoundError yakalamak, TEK kilitli dosya
                # yüzünden o günkü bakımın tamamını iptal ediyordu.
                continue
        return sayi

    def _kkd_hamlarini_sil(self, baglanti) -> int:
        """Etiketlenmemiş KKD örnekleri süre dolunca dosyasıyla birlikte silinir.
        Etiketlenenler veri setidir; retention onlara dokunmaz (docs/06 §5)."""
        sinir = zaman.gun_once_utc(self.ayarlar.kkd_ham_veri_saklama_gun)
        satirlar = baglanti.execute(
            "SELECT id, crop_path FROM ppe_samples WHERE labeled_at IS NULL AND captured_at < ?",
            (sinir,),
        ).fetchall()
        for satir in satirlar:
            dosya = self.ayarlar.goruntu_klasoru / satir["crop_path"]
            try:
                dosya.unlink(missing_ok=True)
            except OSError as hata:
                self._log.error(
                    f"Eski KKD örneği silinemedi: {hata}",
                    extra={"ayrinti": f"dosya: {dosya}"},
                )
        baglanti.execute(
            "DELETE FROM ppe_samples WHERE labeled_at IS NULL AND captured_at < ?",
            (sinir,),
        )
        baglanti.commit()
        return len(satirlar)

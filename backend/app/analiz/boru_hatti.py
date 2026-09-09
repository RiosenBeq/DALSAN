"""Kamera başına işleme hattı: tespit → takip → (KKD) → kural motoru → overlay.

Veritabanına DOKUNMAZ; süpervizör konfigürasyonu verir, ihlalleri alıp yazar.
"""

from __future__ import annotations

import threading

import cv2
import numpy as np

from app.analiz import goruntu
from app.analiz.kkd_siniflandirici import KkdSiniflandirici, kisi_kirp
from app.analiz.takip import Takipci
from app.analiz.tespit import SINIF_OVERLAY, Tespitci
from app.rules.geometri import nokta_poligonda
from app.rules.motor import KuralMotoru
from app.rules.sayim import BolgeSayaci, BolgeSayimi
from app.rules.tipler import (
    SINIF_INSAN,
    VAR,
    YOK,
    Bolge,
    Ihlal,
    Kalibrasyon,
    Kural,
    Tespit,
)


def _yazi(gorsel, metin: str, konum: tuple[int, int], renk, kalinlik: int = 1) -> None:
    """Okunaklı etiket: koyu dış hat + renkli iç. Açık arka planda (beton, kar)
    ince renkli yazı kaybolur; fabrikada ekrana uzaktan bakılır."""
    cv2.putText(
        gorsel,
        metin,
        konum,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (20, 20, 20),
        kalinlik + 2,
        cv2.LINE_AA,
    )
    cv2.putText(gorsel, metin, konum, cv2.FONT_HERSHEY_SIMPLEX, 0.55, renk, kalinlik, cv2.LINE_AA)


# KKD çağrısı seyrek: kişi track'i başına her 5. işlenen karede bir (docs/02 §6)
_KKD_KARE_ARALIGI = 5

# Overlay renkleri (BGR). Ekrandaki renk anahtarı (kamera sayfası) bu tabloyla
# BİREBİR aynı olmalı — kullanıcı ekranda gördüğü rengi tanıyabilmeli.
_RENKLER = {
    "person": (80, 200, 80),  # yeşil  — insan
    "forklift": (0, 170, 255),  # turuncu — forklift
    "truck": (255, 140, 60),  # mavi   — tır/araç
}
_IHLAL_RENGI = (0, 0, 220)  # kırmızı — kural ihlali olan nesne
_BOLGE_RENGI = (200, 60, 160)  # mor — araç mavisiyle karışmasın
# KKD göstergeleri: baret beyaz-mavi, reflektörlü yelek SARI (sahadaki yeleğin
# rengiyle aynı olsun ki bakan kişi anında eşleştirsin)
_BARET_RENGI = (255, 200, 60)
_YELEK_RENGI = (0, 220, 245)
_KKD_YOK_RENGI = (0, 0, 220)
# Önizleme JPEG kalitesi: ağ trafiği ile okunabilirlik arasında denge
_JPEG_KALITE = [int(cv2.IMWRITE_JPEG_QUALITY), 80]

# SAYIM ROZETİ — bölgenin içine yazılan "3 insan · 1 tır" etiketi.
# Sayı, kuralın ürettiği uyarıdan BAĞIMSIZ bir bilgidir; bu yüzden ihlal
# kırmızısından da bölge morundan da farklı, nötr koyu bir zemine yazılır.
_SAYIM_ZEMINI = (45, 40, 38)
_SAYIM_YAZISI = (245, 245, 245)
_SAYIM_YUKSEKLIGI = 22

# BÖLGE TARAMASI — bölgenin içi çapraz çizgilerle taranır. Yalnızca çerçeve
# çizmek yetmiyordu: kullanıcı "alanın içi neresi" sorusunu görüntüye bakarak
# cevaplayamıyordu; iç içe ya da yan yana iki bölgede hangi çizginin hangisine
# ait olduğu da anlaşılmıyordu. Tarama, alanı bir bakışta okunur yapar.
#
# HIZ — ölçüldü (1080p, bölgenin sınır kutusu karenin ~%65'i):
#   tam kare boolean maskesi + numpy .......... 22,2 ms/kare
#   dağınık koordinatlarla fancy-index ......... 7,2 ms/kare
#   sınır kutusunda cv2.addWeighted + copyTo ... 1,1 ms/kare   ← seçilen
# Fark aritmetikte değil BELLEK ERİŞİMİNDE: 164 bin dağınık koordinata tek tek
# gitmek, bitişik bir bloğu baştan sona taramaktan pahalıdır. Maske, renk katı
# ve harman tamponu bölge çizimi değişmedikçe yeniden üretilmez.
# 7x24 çalışan, kamera başına saniyede 6 kare işleyen bir sistemde bu fark
# işlemcinin kendisidir.
# Aralık, karenin KISA KENARINA oranlıdır; sabit piksel değil. Sabit 14 px,
# 480p'de seyrek görünürken 1080p'de saç teli gibi sıklaşıyordu — hem çirkin
# hem gereksiz pahalıydı (taranan piksel sayısı çözünürlükle katlanıyordu).
_TARAMA_ARALIK_ORANI = 0.022
_TARAMA_EN_AZ_ARALIK_PX = 9
# Çizgi kalınlığı da aralığa oranlıdır: 1 px'lik tarama HD görüntüde,
# hele dokulu bir fabrika zemininde, gözle seçilemiyordu.
_TARAMA_KALINLIK_ORANI = 0.11

# Tarama çizgilerinin harmanı: bölge rengi %75, alttaki görüntü %25. Çizgiler
# alanın ancak %8'ini kapladığı için güçlü renk ALTTAKİ GÖRÜNTÜYÜ ÖRTMEZ;
# zayıf harman ise dokulu bir fabrika zemininde tamamen kayboluyordu.
_TARAMA_KARISIMI = 0.75

# Bölge sayacının "kararlı" saydığı ardışık kare sayısı. Kamera 6 kare/sn
# örneklerken yarım saniye eder: sınırda titreyen kutu sayıyı zıplatmaz,
# gerçekten giren kişi de yarım saniyede sayılır.
_SAYIM_MIN_KARE = 3


class KameraHatti:
    def __init__(self, kamera_id: int, fps: int, iyilestir: bool = False) -> None:
        self.kamera_id = kamera_id
        # Süpervizör, örnekleme hızı değişince hattı yeniden kurmak için okur:
        # ByteTrack'in kare hızı yanlış kalırsa takip hafızası saniye cinsinden
        # kayar ve aynı kişiye ikinci kez uyarı üretilir.
        self.fps = fps
        # Düşük kaliteli kamerada kontrast dengeleme (.env → GORUNTU_IYILESTIRME)
        self.iyilestir = iyilestir
        self._kalite: dict = {"sorun": "yok", "mesaj": ""}
        self._kalite_sayaci = 0
        self._takipci = Takipci(fps)
        self._motor = KuralMotoru(kamera_id)
        # Sayım kuraldan AYRIDIR: ihlal üretmez, yalnız "kaç var / kaç girdi"
        # sorusunu cevaplar (rules/sayim.py). Yanlış sayım kimseyi uyarmaz.
        self._sayac = BolgeSayaci(min_kare=_SAYIM_MIN_KARE)
        self._sayimlar: list[BolgeSayimi] = []
        self._kare_sayimi: dict[str, int] = {}
        self._bolgeler: list[Bolge] = []
        self._kalibrasyon: Kalibrasyon | None = None
        # Tarama önbelleği — bölge çizimi değişmedikçe yeniden üretilmez.
        self._tarama_imzasi: tuple | None = None
        self._tarama_kutu: tuple[int, int, int, int] | None = None
        self._tarama_maskesi: np.ndarray | None = None
        self._tarama_renk_kati: np.ndarray | None = None
        self._tarama_harman: np.ndarray | None = None
        self._kkd_sayac: dict[int, int] = {}  # takip_id -> işlenen kare sayısı
        self._kilit = threading.Lock()
        # ÖNİZLEME TEMBELDİR: kare saklanır, JPEG ancak İSTENDİĞİNDE üretilir.
        #
        # Ölçüldü: JPEG kodlaması kare işleme süresinin %62'si (1080p'de 8,95 ms
        # / 14,33 ms). Eskiden her karede yapılıyordu — tarayıcıda hiç sayfa
        # açık olmasa bile. 4 kamera x 6 kare/sn ile bu, bir çekirdeğin
        # %21'inin karşılığı olmayan bir işe gitmesi demekti.
        #
        # Önizleme sayfası saniyede bir soruyor, hat saniyede altı kare
        # işliyor: istendiğinde kodlama, açık sayfada bile 6 kat az iş demek.
        self._son_kare_bolgeli: np.ndarray | None = None
        # Bölgeleri ÇİZİLMEMİŞ son kare. Bölge çizim sayfası bölgeleri kendi
        # tuvaline çizer; oraya bölgesi çizili kare giderse aynı bölge ekranda
        # iki kez görünür. None = bölge yok, iki sürüm zaten aynı.
        self._son_kare_bolgesiz: np.ndarray | None = None
        # Kare sayacı, JPEG önbelleğinin hangi kareye ait olduğunu söyler.
        self._kare_sayaci = 0
        self._jpeg_onbellek: dict[bool, tuple[int, bytes]] = {}

    def yapilandir(
        self, bolgeler: list[Bolge], kurallar: list[Kural], kalibrasyon: Kalibrasyon | None
    ) -> None:
        self._bolgeler = bolgeler
        self._kalibrasyon = kalibrasyon
        self._motor.kurallari_yukle(kurallar)

    def isle(
        self,
        kare: np.ndarray,
        zaman_s: float,
        tespitci: Tespitci | None,
        kkd: KkdSiniflandirici,
    ) -> tuple[list[Tespit], list[Ihlal]]:
        # Kalite ölçümü seyrek: her 50 işlenen karede bir yeter, ölçüm bedava değil
        self._kalite_sayaci += 1
        if self._kalite_sayaci % 50 == 1:
            self._kalite = goruntu.kalite_olc(kare)

        if self.iyilestir:
            # Tespit ve önizleme AYNI kareyi kullanır: kullanıcı ekranda modelin
            # gördüğü görüntüyü görmeli (docs/09 — dürüstlük)
            kare = goruntu.iyilestir(kare)

        yukseklik, genislik = kare.shape[:2]

        if tespitci is None:
            tespitler: list[Tespit] = []  # model yok — kamera izlenir, tespit yapılmaz
        else:
            kutular, guvenler, siniflar = tespitci.tespit_et(kare)
            tespitler = self._takipci.guncelle(kutular, guvenler, siniflar)

        self._kkd_degerlendir(kare, tespitler, (genislik, yukseklik), kkd)

        ihlaller = self._motor.degerlendir(
            zaman_s,
            (float(genislik), float(yukseklik)),
            tespitler,
            self._bolgeler,
            self._kalibrasyon,
        )

        # Sayım kural motorundan SONRA ve ondan bağımsız çalışır: kural hiç
        # kurulmamış bir kamerada da bölgeler sayılır. Kullanıcı çoğu zaman
        # önce "kaç kişi geçiyor" sorusunun cevabını ister, uyarıyı sonra kurar.
        self._sayimlar = self._sayac.guncelle(
            (float(genislik), float(yukseklik)), tespitler, self._bolgeler
        )
        self._kare_sayimi = self._sayac.kare_sayimi(tespitler)

        self._overlay_guncelle(kare, tespitler, ihlaller)
        return tespitler, ihlaller

    def kalite(self) -> dict:
        """Son ölçülen görüntü kalitesi (kamera sayfasında gösterilir)."""
        return dict(self._kalite)

    def sayimlar(self) -> list[dict]:
        """Bölge bölge sayım tablosu (kamera sayfası ve Sayım ekranı okur).

        Dataclass yerine dict döner: web katmanı bunu doğrudan JSON'a çevirir
        ve arada bir dönüştürme adımı olmasın.
        """
        return [
            {
                "bolge_id": s.bolge_id,
                "anlik": dict(s.anlik),
                "giren": dict(s.giren),
                "zirve": dict(s.zirve),
                "anlik_toplam": s.anlik_toplam,
                "giren_toplam": s.giren_toplam,
            }
            for s in self._sayimlar
        ]

    def kare_sayimi(self) -> dict[str, int]:
        """Bölgeden bağımsız, karenin tamamındaki nesne sayısı."""
        return dict(self._kare_sayimi)

    def sayaci_sifirla(self, bolge_id: int | None = None) -> None:
        """Kümülatif ('giren') sayaçları sıfırlar — vardiya başı içindir."""
        self._sayac.sifirla(bolge_id)

    def son_islenmis_jpeg(self, bolgeler_dahil: bool = True) -> bytes | None:
        """Son işlenmiş kare (JPEG) — İSTENDİĞİNDE kodlanır.

        bolgeler_dahil=False → kayıtlı bölgelerin ÇİZİLMEDİĞİ sürüm. Bölge
        çizim sayfası bölgeleri kendi tuvaline çizdiği için oraya bu sürüm
        gider; aksi halde tek bölgenin iki ayrı çizgisi görünür.

        Aynı kare için ikinci istek önbellekten döner: canlı duvarda altı
        kamera aynı kareyi sorabilir, altı kez kodlamanın anlamı yok.
        """
        with self._kilit:
            sayac = self._kare_sayaci
            onbellek = self._jpeg_onbellek.get(bolgeler_dahil)
            if onbellek is not None and onbellek[0] == sayac:
                return onbellek[1]
            kare = self._son_kare_bolgeli if bolgeler_dahil else self._son_kare_bolgesiz
            if kare is None:
                # Bölgesiz sürüm istendi ama çizili bölge yok → iki sürüm aynı.
                kare = self._son_kare_bolgeli
            if kare is None:
                return None

        # Kodlama KİLİT DIŞINDA: 1080p'de ~9 ms sürer ve o süre boyunca analiz
        # iş parçacığının yeni kare yazmasını engellemenin anlamı yok. Kareler
        # yazıldıktan sonra bir daha DEĞİŞTİRİLMEZ (her kare yeni kopya açar),
        # bu yüzden kilitsiz okumak güvenlidir.
        tamam, jpeg = cv2.imencode(".jpg", kare, _JPEG_KALITE)
        if not tamam:
            return None
        veri = jpeg.tobytes()

        with self._kilit:
            # Bu arada yeni kare geldiyse önbelleğe KOYMA: eski kareyi yeni
            # karenin yerine servis etmek, ekranda donmuş görüntü demektir.
            if self._kare_sayaci == sayac:
                self._jpeg_onbellek[bolgeler_dahil] = (sayac, veri)
        return veri

    def kkd_bolgesinde_mi(self, tespit: Tespit, kare_boyutu: tuple[float, float]) -> bool:
        ayak = tespit.ayak_noktasi()
        ayak_norm = (ayak[0] / kare_boyutu[0], ayak[1] / kare_boyutu[1])
        return any(
            b.tip == "ppe_required" and b.aktif and nokta_poligonda(ayak_norm, b.poligon)
            for b in self._bolgeler
        )

    # ---- iç ----

    def _kkd_degerlendir(
        self,
        kare: np.ndarray,
        tespitler: list[Tespit],
        kare_boyutu: tuple[float, float],
        kkd: KkdSiniflandirici,
    ) -> None:
        if not kkd.model_var:
            return  # gözlem üretilmez; kural motoru belirsiz sayar
        # Kadans sayaçları yalnızca ekranda olan takipler için tutulur;
        # aksi halde sözlük 7x24 çalışmada sınırsız büyürdü.
        mevcutlar = {t.takip_id for t in tespitler}
        self._kkd_sayac = {t: s for t, s in self._kkd_sayac.items() if t in mevcutlar}
        for tespit in tespitler:
            if tespit.sinif != SINIF_INSAN:
                continue
            if not self.kkd_bolgesinde_mi(tespit, kare_boyutu):
                continue
            sayac = self._kkd_sayac.get(tespit.takip_id, 0) + 1
            self._kkd_sayac[tespit.takip_id] = sayac
            if sayac % _KKD_KARE_ARALIGI != 1:
                continue
            kirpik = kisi_kirp(kare, tespit.kutu)
            if kirpik is not None:
                tespit.kkd_gozlemi = kkd.degerlendir(kirpik)

    def _overlay_guncelle(
        self, kare: np.ndarray, tespitler: list[Tespit], ihlaller: list[Ihlal]
    ) -> None:
        gorsel = kare.copy()
        yukseklik, genislik = gorsel.shape[:2]

        ihlal_takipleri = {t for ihlal in ihlaller for t in ihlal.takip_idler}
        for tespit in tespitler:
            x1, y1, x2, y2 = (int(v) for v in tespit.kutu)
            ihlalli = tespit.takip_id in ihlal_takipleri
            renk = _IHLAL_RENGI if ihlalli else _RENKLER.get(tespit.sinif, (180, 180, 180))
            cv2.rectangle(gorsel, (x1, y1), (x2, y2), renk, 3 if ihlalli else 2)
            etiket = f"{SINIF_OVERLAY.get(tespit.sinif, tespit.sinif)} #{tespit.takip_id}"
            _yazi(gorsel, etiket, (x1, max(y1 - 6, 12)), renk)
            if tespit.sinif == SINIF_INSAN:
                self._kkd_isaretle(gorsel, tespit, (x1, y1, x2, y2))

        # Bölgeler EN SON ve AYRI bir kopyaya çizilir: böylece elimizde hem
        # bölgeli (izleme ekranları) hem bölgesiz (bölge çizim sayfası) kare olur.
        bolgeli = gorsel
        aktif_bolgeler = [b for b in self._bolgeler if b.aktif]
        if aktif_bolgeler:
            bolgeli = gorsel.copy()
            self._taramayi_uygula(bolgeli, aktif_bolgeler)
            sayim_tablosu = {s.bolge_id: s for s in self._sayimlar}
            for bolge in aktif_bolgeler:
                noktalar = np.array(
                    [(int(x * genislik), int(y * yukseklik)) for x, y in bolge.poligon]
                )
                cv2.polylines(bolgeli, [noktalar], True, _BOLGE_RENGI, 2)
                self._sayim_rozeti(bolgeli, noktalar, sayim_tablosu.get(bolge.id))

        # JPEG BURADA ÜRETİLMEZ (bkz. son_islenmis_jpeg): kareler saklanır,
        # kodlama isteyen olursa yapılır. Sayaç artınca önbellek kendiliğinden
        # geçersizleşir — ayrıca temizlemek gerekmez.
        with self._kilit:
            self._son_kare_bolgeli = bolgeli
            self._son_kare_bolgesiz = gorsel if aktif_bolgeler else None
            self._kare_sayaci += 1

    def _taramayi_uygula(self, gorsel: np.ndarray, bolgeler: list[Bolge]) -> None:
        """Bölgelerin içini çapraz taramayla doldurur (yerinde değiştirir).

        Yalnız tarama çizgileri renklenir; alanın altındaki görüntü (insan,
        forklift) okunur kalır — bu bir vurgu, örtü değil. Çalışma, bölgelerin
        sınır kutusuyla sınırlıdır ve tamamı OpenCV'nin bitişik bellek
        yollarından geçer (bkz. yukarıdaki HIZ ölçümü).
        """
        if not self._taramayi_hazirla(gorsel.shape[:2], bolgeler):
            return
        x0, y0, x1, y1 = self._tarama_kutu
        roi = gorsel[y0:y1, x0:x1]
        cv2.addWeighted(
            roi,
            1.0 - _TARAMA_KARISIMI,
            self._tarama_renk_kati,
            _TARAMA_KARISIMI,
            0,
            dst=self._tarama_harman,
        )
        cv2.copyTo(self._tarama_harman, self._tarama_maskesi, roi)

    def _taramayi_hazirla(self, bicim: tuple[int, int], bolgeler: list[Bolge]) -> bool:
        """Tarama maskesini/tamponlarını (gerekiyorsa) üretir. Döner: çizilecek var mı."""
        yukseklik, genislik = bicim
        imza = (
            genislik,
            yukseklik,
            tuple((b.id, tuple(map(tuple, b.poligon))) for b in bolgeler),
        )
        if imza == self._tarama_imzasi:
            return self._tarama_maskesi is not None

        self._tarama_imzasi = imza
        self._tarama_kutu = None
        self._tarama_maskesi = None

        alan = np.zeros((yukseklik, genislik), np.uint8)
        for bolge in bolgeler:
            noktalar = np.array(
                [(int(x * genislik), int(y * yukseklik)) for x, y in bolge.poligon],
                dtype=np.int32,
            )
            cv2.fillPoly(alan, [noktalar], 255)

        kutu = cv2.boundingRect(alan)
        if kutu[2] <= 0 or kutu[3] <= 0:
            return False  # çizilecek alan yok (poligonlar kare dışında kalmış)
        x0, y0, kutu_g, kutu_y = kutu
        alan_roi = alan[y0 : y0 + kutu_y, x0 : x0 + kutu_g]

        # 45 derecelik çapraz çizgiler. Yatay/dikey yerine çapraz seçildi:
        # fabrika görüntüsünde raf, direk ve zemin derzleri zaten yatay-dikey;
        # çapraz tarama onlarla karışmaz ve alan gözle ayırt edilir.
        aralik = max(int(min(genislik, yukseklik) * _TARAMA_ARALIK_ORANI), _TARAMA_EN_AZ_ARALIK_PX)
        kalinlik = max(int(aralik * _TARAMA_KALINLIK_ORANI), 1)
        cizgiler = np.zeros_like(alan_roi)
        for kayma in range(-kutu_y, kutu_g, aralik):
            cv2.line(cizgiler, (kayma, 0), (kayma + kutu_y, kutu_y), 255, kalinlik)

        self._tarama_kutu = (x0, y0, x0 + kutu_g, y0 + kutu_y)
        self._tarama_maskesi = cv2.bitwise_and(cizgiler, alan_roi)
        self._tarama_renk_kati = np.full((kutu_y, kutu_g, 3), _BOLGE_RENGI, np.uint8)
        self._tarama_harman = np.empty((kutu_y, kutu_g, 3), np.uint8)
        return True

    @staticmethod
    def _sayim_rozeti(gorsel: np.ndarray, noktalar: np.ndarray, sayim) -> None:
        """Bölgenin ÜST KENARINA "3 insan · 1 tir" rozeti çizer.

        Sayı, videonun üstünde görünmelidir: kullanıcı sayıyı ayrı bir tabloda
        değil, saydığı yerin üstünde görmek ister. Boş bölgeye rozet
        ÇİZİLMEZ — altı bölgeli bir kamerada altı tane "0" yalnızca gürültüdür.

        Yazı ASCII'dir (cv2.putText Türkçe harf çizemez, "tır" → "t?r"):
        SINIF_OVERLAY tablosu tespit kutularıyla aynı karşılıkları verir.
        """
        if sayim is None or not sayim.anlik:
            return
        metin = " · ".join(
            f"{adet} {SINIF_OVERLAY.get(sinif, sinif)}"
            for sinif, adet in sorted(sayim.anlik.items())
        )
        (yazi_g, yazi_y), _ = cv2.getTextSize(metin, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)

        # Rozetin çıpası bölgenin EN ÜST köşesidir; poligon nasıl çizilmiş
        # olursa olsun (saat yönü ya da tersi) rozet hep aynı yerde durur.
        ust = noktalar[noktalar[:, 1].argmin()]
        x = int(ust[0])
        y = int(ust[1]) - 6
        yukseklik, genislik = gorsel.shape[:2]
        # Kare dışına taşarsa içeri al: taşan rozet hiç çizilmez ve sayı kaybolur
        x = max(2, min(x, genislik - yazi_g - 12))
        y = max(_SAYIM_YUKSEKLIGI + 2, min(y, yukseklik - 4))

        cv2.rectangle(
            gorsel,
            (x, y - _SAYIM_YUKSEKLIGI),
            (x + yazi_g + 10, y),
            _SAYIM_ZEMINI,
            -1,
        )
        cv2.rectangle(
            gorsel,
            (x, y - _SAYIM_YUKSEKLIGI),
            (x + yazi_g + 10, y),
            _BOLGE_RENGI,
            1,
        )
        cv2.putText(
            gorsel,
            metin,
            (x + 5, y - (_SAYIM_YUKSEKLIGI - yazi_y) // 2 - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            _SAYIM_YAZISI,
            1,
            cv2.LINE_AA,
        )

    def _kkd_isaretle(
        self, gorsel: np.ndarray, tespit: Tespit, kutu: tuple[int, int, int, int]
    ) -> None:
        """Kişinin baret/yelek durumunu kutunun sağ üstüne küçük rozetlerle çizer.

        ÜÇ DURUM gösterilir: var (renkli dolu), yok (kırmızı çapraz), belirsiz
        (gri boş). "Belirsiz" ihlal DEĞİLDİR (docs/04 §1) ve öyle de görünmelidir;
        KKD modeli henüz eğitilmediği sürece tüm kişiler belirsizdir.
        """
        gozlem = tespit.kkd_gozlemi
        if gozlem is None:
            return
        x1, y1, x2, _ = kutu
        for sira, (durum, dolu_renk, harf) in enumerate(
            ((gozlem.baret, _BARET_RENGI, "B"), (gozlem.yelek, _YELEK_RENGI, "Y"))
        ):
            kx = min(x2 - 4, x1 + 4 + sira * 26)
            ky = max(y1 + 4, 4)
            if durum == VAR:
                cv2.rectangle(gorsel, (kx, ky), (kx + 22, ky + 20), dolu_renk, -1)
                _yazi(gorsel, harf, (kx + 6, ky + 15), (20, 20, 20), kalinlik=2)
            elif durum == YOK:
                cv2.rectangle(gorsel, (kx, ky), (kx + 22, ky + 20), _KKD_YOK_RENGI, -1)
                cv2.line(gorsel, (kx + 3, ky + 3), (kx + 19, ky + 17), (255, 255, 255), 2)
                cv2.line(gorsel, (kx + 19, ky + 3), (kx + 3, ky + 17), (255, 255, 255), 2)
            else:  # belirsiz — karar verilemedi, ihlal sayılmaz
                cv2.rectangle(gorsel, (kx, ky), (kx + 22, ky + 20), (150, 150, 150), 1)
                _yazi(gorsel, "?", (kx + 7, ky + 15), (150, 150, 150))

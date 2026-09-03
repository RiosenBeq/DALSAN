"""Kıyas takımı: kütüphaneye yüklenecek REFERANS fotoğraflar + SORGU sahneleri.

Kurgu, sahadaki kullanımın birebir karşılığıdır:
  1. Kullanıcı bir nesnenin 4 fotoğrafını yükler       → referanslar
  2. Sonra başka bir fotoğraf yükleyip "bunda var mı?"  → sorgular

Sorgular referanslardan BİLEREK farklıdır; gerçek hayatta ne değişiyorsa o
değişir: açı, ölçek, aydınlatma, bulanıklık, JPEG bozulması, kısmi örtülme ve
arka plan. Her bozulma iki şiddette sorulur (hafif / sert) — motorun nerede
dayandığı, nerede koptuğu böyle görünür.

Zeminler önemlidir: her nesnenin bir "evi" vardır (durduğu yerin zemini) ve
referansların dördü de orada çekilmiştir. Sorguların çoğu aynı zemin ailesinde
ama BAŞKA bir noktada geçer; iki sorgu ise nesneyi bilerek bambaşka bir zemine
taşır. Bu ayrım şunu ölçer: parmak izi nesneyi mi tanıyor, yoksa arkasındaki
zemini mi?

Ayrıca kütüphanede HİÇ OLMAYAN nesneler ve boş zeminler de sorulur; bunlara
isim yazılması kaçırmaktan çok daha ağır bir kusurdur.

SERTLEŞTİRME (bu takımın sonradan kapatılmış KÖR NOKTASI). İlk takım motorun
en zayıf dalını — kararı YALNIZ renge bırakan "iki taraf da desensiz" dalını —
hiç sınamıyordu. Üç eksik vardı ve üçü de kapatıldı:

  1. Yabancı nesnelerin hepsi kütüphanedekilerden BAŞKA renkteydi. Şimdi
     `DUZ_YABANCILAR` var: kütüphanedeki düz nesnelerle AYNI renkte ama başka
     biçimde 8 nesne (mavi kasa/palet/örtü/duvar, gri sac levha/beton blok,
     beyaz çuval/levha), 24 sorgu. Hepsi negatiftir.
  2. Boş zemin sorgularının hiçbiri gerçekten desensiz değildi (tam karede
     14-111 ORB noktası). Şimdi `cizim.DESENSIZ_ZEMIN_TURLERI` var: bulanık,
     karanlık ve tek renge boyanmış yüzeyler — ölçülen ORB nokta sayısı
     SIFIR, yani düz-düz dalına gerçekten giriyorlar.
  3. En sert bulanıklık k=9'du, yani kütüphanedeki bir nesnenin deseni hiç
     tamamen silinmiyordu. Şimdi k=13/15/17 kademeleri de var: deseni silinen
     bir nesnenin KARDEŞİNİN adını alması (kütüphane İÇİ yanlış isim) en
     tehlikeli hatadır ve ancak burada görünür.

Her görüntü tohumludur: aynı takım her makinede aynı çıkar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.nesneler.kutuphane import Nesne, Parmakizi, parmakizi_cikar

from . import cizim

# Sahne boyutu: telefonla çekilmiş bir fotoğrafın küçültülmüş hali (4:3).
SAHNE_GENIS, SAHNE_YUKSEK = 384, 288
# Referans fotoğrafın tuval boyu (kırpılmadan önce)
_REFERANS_TUVAL = 320
# Yüklenen fotoğraflar JPEG'dir; referanslar da diske JPEG yazılır (depo.py).
_REFERANS_JPEG_KALITESI = 90
_SORGU_JPEG_KALITESI = 88

ZORLUK_ADLARI = {
    "yuksek": "Yüksek desenli",
    "orta": "Orta desenli",
    "duz": "Düz renkli (desensiz)",
    "benzer-renk": "Tuzak: aynı renk, farklı desen",
    "benzer-desen": "Tuzak: farklı renk, aynı desen",
    "negatif": "Kütüphanede yok (negatif)",
    "duz-yabanci": "Tuzak: aynı renk, desensiz (neg.)",
    "desensiz-zemin": "Desensiz boş zemin (negatif)",
}

# Nesnelerin "ev" zeminleri sırayla bunlardan seçilir; "komşu" bir sonrakidir.
_EV_ZEMINLERI = ("beton", "izgara", "palet", "tugla")
# Nesnenin hiç görülmediği zeminler (arka plan değişimi sorgusu için)
_YABANCI_ZEMINLER = ("cim", "koyu")


@dataclass(frozen=True)
class NesneTanimi:
    """Takımdaki bir nesnenin adı, zorluk sınıfı, çizimi ve durduğu zemin."""

    ad: str
    zorluk: str
    cizici: cizim.Cizici
    ev_zemini: str = "beton"
    komsu_zemin: str = "izgara"
    yabanci_zemin: str = "cim"
    # Yalnız `DUZ_YABANCILAR` için: bu yabancı nesne kütüphanedeki HANGİ düz
    # nesneyle aynı renktedir? Rapor "hangi adın yazılması bekleniyordu"yu
    # yazabilsin ve kalite kapısı ikizin gerçekten kütüphanede olduğunu
    # doğrulayabilsin diye tutulur. Karara GİRMEZ.
    ikiz: str = ""


@dataclass(frozen=True)
class Bozulma:
    """Bir sorgu fotoğrafının nasıl bozulacağı.

    `zemin`: "ev" (nesnenin bulunduğu zemin, başka nokta), "komsu" (benzer ama
    başka bir zemin) ya da "yabanci" (bambaşka bir zemin).
    """

    ad: str
    derece: float  # döndürme
    egim: float  # perspektif
    kenar: int  # nesnenin sahnedeki kenarı (px)
    zemin: str = "ev"
    isik_carpan: float = 1.0
    isik_ekle: float = 0.0
    bulaniklik: int = 0  # Gauss çekirdeği (0 = yok)
    jpeg: int = _SORGU_JPEG_KALITESI
    ortme: float = 0.0  # nesnenin kapatılan oranı


@dataclass(frozen=True)
class Sorgu:
    """Kullanıcının 'bunda var mı?' diye yüklediği tek bir fotoğraf."""

    dogru_ad: str | None  # None → kütüphanede olmayan bir şey soruldu (negatif)
    zorluk: str
    bozulma: str
    gorsel: np.ndarray
    # Nesnenin sahnedeki GERÇEK yeri. Ölçüm bunu karar vermek için KULLANMAZ;
    # yalnız teşhis için: "pencere nesneyi tam çerçeveleseydi skor ne olurdu?"
    kutu: tuple[int, int, int, int] | None = None

    @property
    def etiket(self) -> str:
        return f"{self.dogru_ad or 'YOK'} / {self.bozulma}"


@dataclass(frozen=True)
class Takim:
    nesneler: list[Nesne]  # kütüphane (parmak izleriyle)
    sorgular: list[Sorgu]


def _zeminli(tanimlar: tuple[tuple[str, str, cizim.Cizici], ...]) -> tuple[NesneTanimi, ...]:
    """Her nesneye sırayla bir ev zemini, komşusu ve yabancı bir zemin verir."""
    hazir = []
    for sira, (ad, zorluk, cizici) in enumerate(tanimlar):
        ev = _EV_ZEMINLERI[sira % len(_EV_ZEMINLERI)]
        komsu = _EV_ZEMINLERI[(sira + 1) % len(_EV_ZEMINLERI)]
        yabanci = _YABANCI_ZEMINLER[sira % len(_YABANCI_ZEMINLER)]
        hazir.append(NesneTanimi(ad, zorluk, cizici, ev, komsu, yabanci))
    return tuple(hazir)


# Kütüphaneye tanıtılan nesneler. Sıra zorluk kademesine göredir.
KUTUPHANE: tuple[NesneTanimi, ...] = _zeminli(
    (
        ("Uyarı panosu (yazılı)", "yuksek", cizim.yazili_pano),
        ("Logolu malzeme kutusu", "yuksek", cizim.logolu_kutu),
        ("Barkod etiketi", "yuksek", cizim.barkod_etiketi),
        ("Halkalı gaz tüpü", "orta", cizim.halkali_tup),
        ("Çizgili baret", "orta", cizim.cizgili_baret),
        ("Düz mavi bidon", "duz", cizim.duz_bidon),
        ("Düz beyaz baret", "duz", cizim.duz_baret),
        ("Gri boru", "duz", cizim.gri_boru),
        ("Gri pano A (kareli)", "benzer-renk", cizim.gri_pano_kareli),
        ("Gri pano B (çapraz)", "benzer-renk", cizim.gri_pano_capraz),
        ("Sarı çizgili kasa", "benzer-desen", cizim.sari_cizgili_kasa),
        ("Yeşil çizgili kasa", "benzer-desen", cizim.yesil_cizgili_kasa),
    )
)

# Kütüphaneye GİRMEYEN nesneler: bunlara isim yazılırsa yanlış isimdir.
YABANCILAR: tuple[NesneTanimi, ...] = _zeminli(
    (
        ("Kırmızı yangın söndürücü", "negatif", cizim.yangin_sondurucu),
        ("Mor kablo makarası", "negatif", cizim.kablo_makarasi),
        ("Turuncu trafik konisi", "negatif", cizim.trafik_konisi),
        ("Siyah lastik yığını", "negatif", cizim.lastik_yigini),
    )
)

# SERTLEŞTİRME 1 — kütüphanedekiyle AYNI RENKTE, düz, YABANCI nesneler.
#
# Bunlar `YABANCILAR`dan ayrı durur çünkü ölçtükleri şey başkadır: oradakiler
# "başka renkte bir şeye isim yazılıyor mu" diye sorar (motorun kolay işi),
# buradakiler "renk aynıysa, desen yokken ne oluyor" diye sorar — motorun
# kararı YALNIZ renge bıraktığı dal. Doğru cevap hepsinde "eşleşme yok"tur.
#
# Her biri, ikizinin DURDUĞU zemine konur. Bu bilerek yapılmıştır: fabrikada
# yabancı nesne de aynı zeminin üstündedir, ve zemin farklı olsaydı sorgu
# kolaylaşır, delik görünmezdi. "arka plan (sert)" bozulması ise nesneyi
# bambaşka bir zemine taşır — böylece "adı nesne mi yazdırıyor, zemin mi"
# sorusu da ölçülmüş olur.
DUZ_YABANCILAR: tuple[NesneTanimi, ...] = (
    NesneTanimi(
        "Mavi kasa", "duz-yabanci", cizim.mavi_kasa, "izgara", "palet", "cim", ikiz="Düz mavi bidon"
    ),
    NesneTanimi(
        "Mavi palet",
        "duz-yabanci",
        cizim.mavi_palet,
        "izgara",
        "palet",
        "koyu",
        ikiz="Düz mavi bidon",
    ),
    NesneTanimi(
        "Mavi örtü", "duz-yabanci", cizim.mavi_ortu, "izgara", "palet", "cim", ikiz="Düz mavi bidon"
    ),
    NesneTanimi(
        "Mavi duvar parçası",
        "duz-yabanci",
        cizim.mavi_duvar_parcasi,
        "izgara",
        "palet",
        "koyu",
        ikiz="Düz mavi bidon",
    ),
    NesneTanimi(
        "Gri sac levha",
        "duz-yabanci",
        cizim.gri_sac_levha,
        "tugla",
        "beton",
        "koyu",
        ikiz="Gri boru",
    ),
    NesneTanimi(
        "Gri beton blok",
        "duz-yabanci",
        cizim.gri_beton_blok,
        "beton",
        "izgara",
        "cim",
        ikiz="Gri pano A (kareli)",
    ),
    NesneTanimi(
        "Beyaz çuval",
        "duz-yabanci",
        cizim.beyaz_cuval,
        "palet",
        "tugla",
        "cim",
        ikiz="Düz beyaz baret",
    ),
    NesneTanimi(
        "Beyaz levha",
        "duz-yabanci",
        cizim.beyaz_levha,
        "palet",
        "tugla",
        "koyu",
        ikiz="Düz beyaz baret",
    ),
)

# Referans fotoğraflar: kullanıcının aynı yerde, farklı açı/ışıkta çektiği 4 kare.
# (derece, perspektif eğimi, ışık çarpanı, ışık eklentisi, gürültü)
_REFERANS_VARYASYONLARI = (
    (0.0, 0.00, 1.00, 0.0, 1.5),
    (-7.0, 0.05, 1.12, 10.0, 2.5),
    (6.0, 0.02, 0.88, -12.0, 2.5),
    (2.0, 0.10, 1.04, 4.0, 3.5),
)

# Sorgu bozulmaları: yedi tür, her biri en az iki şiddette.
#
# SERTLEŞTİRME 3 — bulanıklık beş kademelidir. Parantezdeki sayı Gauss
# çekirdeğidir. k=5 ve k=9 nesneyi yalnız yumuşatır; k=13/15/17 ise deseni
# GERÇEKTEN siler ve nesneyi motorun gözünde desensiz bir renk yamasına
# çevirir. Kritik olan kademeler bunlardır: deseni silinen bir kütüphane
# nesnesi, kendi adını değil KARDEŞİNİN adını alabilir (kütüphane içi yanlış
# isim). Ölçüldü — bugün "Gri pano A" k=13/15/17'de her seferinde "Gri pano B"
# adayını en tepeye çıkarıyor, skor 0,20-0,24 ile çıtanın hemen altında
# duruyor. Bu üç kademe olmasaydı o rakam hiç görünmezdi.
_SORGU_TARIFLERI: tuple[Bozulma, ...] = (
    Bozulma("açı (hafif)", 10.0, 0.08, 124),
    Bozulma("açı (sert)", 22.0, 0.20, 124),
    Bozulma("ölçek (hafif)", -3.0, 0.03, 96),
    Bozulma("ölçek (sert)", -3.0, 0.03, 66),
    Bozulma("aydınlatma (hafif)", 4.0, 0.04, 126, isik_carpan=0.75, isik_ekle=-10),
    Bozulma("aydınlatma (sert)", 4.0, 0.04, 126, isik_carpan=0.50, isik_ekle=-28),
    Bozulma("bulanıklık (hafif)", -5.0, 0.04, 120, bulaniklik=5),
    Bozulma("bulanıklık (sert)", -5.0, 0.04, 120, bulaniklik=9),
    Bozulma("bulanıklık (13)", -5.0, 0.04, 120, bulaniklik=13),
    Bozulma("bulanıklık (15)", -5.0, 0.04, 120, bulaniklik=15),
    Bozulma("bulanıklık (17)", -5.0, 0.04, 120, bulaniklik=17),
    Bozulma("JPEG (hafif)", 6.0, 0.05, 118, jpeg=35),
    Bozulma("JPEG (sert)", 6.0, 0.05, 118, jpeg=18),
    Bozulma("örtülme (hafif)", -3.0, 0.06, 132, ortme=0.25),
    Bozulma("örtülme (sert)", -3.0, 0.06, 132, ortme=0.45),
    Bozulma("arka plan (hafif)", 3.0, 0.04, 124, zemin="komsu"),
    Bozulma("arka plan (sert)", 3.0, 0.04, 124, zemin="yabanci"),
)

# Küçük takım: pytest kapısı tam takımı çalıştıracak kadar hızlı değildir.
# Seçim rastgele değil — her zorluk kademesinden bir nesne ve YANLIŞ İSİM
# tuzağının iki yarısı da içeride kalır.
_KUCUK_ADLAR = (
    "Uyarı panosu (yazılı)",  # yüksek desenli
    "Halkalı gaz tüpü",  # orta desenli
    "Düz mavi bidon",  # düz renkli — mavi yabancıların ikizi
    "Düz beyaz baret",  # düz renkli — beyaz yabancıların ikizi
    "Gri boru",  # düz renkli — gri sac levhanın ikizi
    "Gri pano A (kareli)",  # tuzak 1'in iki yarısı
    "Gri pano B (çapraz)",
    "Sarı çizgili kasa",  # tuzak 2'nin iki yarısı
    "Yeşil çizgili kasa",
)
# Üç düz nesne küçük takıma SONRADAN eklendi: `DUZ_YABANCILAR` "kütüphanedeki
# düz nesneyle aynı renk" diye kuruludur, ikizi kütüphanede olmayan bir yabancı
# hiçbir şey ölçmez. Kapının üç rengi de (mavi/gri/beyaz) görmesi gerekir.
_KUCUK_BOZULMALAR = (
    "açı (hafif)",
    "bulanıklık (sert)",
    "bulanıklık (17)",  # deseni SİLİNEN kütüphane nesnesi — kardeş adı tuzağı
    "arka plan (sert)",
)


def takim_olustur(kucuk: bool = False) -> Takim:
    """Kütüphaneyi kurar ve bütün sorgu sahnelerini üretir."""
    tanimlar = _kutuphane_tanimlari(kucuk)
    nesneler = [
        Nesne(id=sira, ad=tanim.ad, parmakizleri=_parmakizleri(tanim))
        for sira, tanim in enumerate(tanimlar, start=1)
    ]
    sorgular = [sorgu for tanim in tanimlar for sorgu in _sorgular(tanim, kucuk)]
    sorgular += _negatif_sorgular(kucuk)
    return Takim(nesneler=nesneler, sorgular=sorgular)


def _kutuphane_tanimlari(kucuk: bool) -> tuple[NesneTanimi, ...]:
    if not kucuk:
        return KUTUPHANE
    return tuple(tanim for tanim in KUTUPHANE if tanim.ad in _KUCUK_ADLAR)


# ------------------------------------------------------------- referanslar


def referans_gorselleri(tanim: NesneTanimi) -> list[np.ndarray]:
    """Kütüphaneye yüklenecek 4 fotoğraf: nesne yakın plan, kendi zemininde.

    Çerçeve nesneye YAKIN tutulur (kenarda %15 pay) ve nesnenin kendi en boy
    oranını korur — insan da öyle fotoğraf çeker: yatık bir boruyu enine,
    dikey bir tüpü boyuna çerçeveler. Kareye tamamlamak, çerçevenin yarısını
    zemine ayırırdı; o zaman ölçtüğümüz şey nesne değil, altındaki zemin
    olurdu.
    """
    gorseller = []
    for sira, (derece, egim, carpan, ekle, gurultu) in enumerate(_REFERANS_VARYASYONLARI):
        gorsel, maske = tanim.cizici()
        gorsel, maske = cizim.donustur(gorsel, maske, derece, egim)
        tohum = _tohum(tanim.ad, 900 + sira)
        zemin = cizim.arka_plan(tanim.ev_zemini, _REFERANS_TUVAL, _REFERANS_TUVAL, tohum=tohum)
        yer = (_REFERANS_TUVAL - cizim.TUVAL) // 2
        cizim.yerlestir(zemin, gorsel, maske, yer, yer)
        tam_maske = np.zeros((_REFERANS_TUVAL, _REFERANS_TUVAL), dtype=np.uint8)
        tam_maske[yer : yer + cizim.TUVAL, yer : yer + cizim.TUVAL] = maske
        zemin = _nesneyi_cercevele(zemin, tam_maske)
        zemin = cizim.isik(zemin, carpan, ekle)
        zemin = cizim.gurultu_ekle(zemin, gurultu, tohum=tohum + 3)
        gorseller.append(cizim.jpeg_bozulmasi(zemin, _REFERANS_JPEG_KALITESI))
    return gorseller


def _nesneyi_cercevele(gorsel: np.ndarray, maske: np.ndarray) -> np.ndarray:
    """Nesnenin kutusunu %15 payla kırpar; en boy oranı korunur."""
    x, y, genis, yuksek = cv2.boundingRect(maske)
    pay_x, pay_y = int(genis * 0.15), int(yuksek * 0.15)
    sol = max(x - pay_x, 0)
    ust = max(y - pay_y, 0)
    sag = min(x + genis + pay_x, gorsel.shape[1])
    alt = min(y + yuksek + pay_y, gorsel.shape[0])
    return gorsel[ust:alt, sol:sag]


def _parmakizleri(tanim: NesneTanimi) -> list[Parmakizi]:
    izler = []
    for gorsel in referans_gorselleri(tanim):
        izi = parmakizi_cikar(gorsel)
        if izi is None:
            raise ValueError(f"'{tanim.ad}' referansından parmak izi çıkmadı — çizim bozuk.")
        izler.append(izi)
    return izler


# ----------------------------------------------------------------- sorgular


def _sorgular(tanim: NesneTanimi, kucuk: bool) -> list[Sorgu]:
    tarifler = _SORGU_TARIFLERI
    if kucuk:
        tarifler = tuple(tarif for tarif in tarifler if tarif.ad in _KUCUK_BOZULMALAR)
    return [
        Sorgu(dogru_ad=tanim.ad, zorluk=tanim.zorluk, bozulma=tarif.ad, **_sahne_uret(tanim, tarif))
        for tarif in tarifler
    ]


# Düz yabancıların bozulmaları. Üçü de bilerek seçilmiştir:
#   açı (hafif)       → nesne kendi zemininde, olağan hâli
#   bulanıklık (sert) → deseni büsbütün silinmiş hâli (en tehlikelisi)
#   arka plan (sert)  → nesne bambaşka bir zeminde; ad hâlâ yazılıyorsa
#                       yazdıran şey ZEMİN değil, NESNENİN KENDİSİDİR
_DUZ_YABANCI_BOZULMALAR = ("açı (hafif)", "bulanıklık (sert)", "arka plan (sert)")


def _negatif_sorgular(kucuk: bool) -> list[Sorgu]:
    """Kütüphanede olmayan nesneler + boş zeminler + desensiz zeminler.

    Hepsinin doğru cevabı aynıdır: "eşleşme yok".
    """
    # Küçük takımda da yabancı nesnelerin HEPSİ sorulur: kapının koruduğu asıl
    # şey "kütüphanede olmayana isim yazılmaması"dır, orada kısıntı olmaz.
    tarifler = _SORGU_TARIFLERI[:1] if kucuk else _SORGU_TARIFLERI[::3]
    sorgular = [
        Sorgu(
            dogru_ad=None,
            zorluk="negatif",
            bozulma=f"{tanim.ad} / {tarif.ad}",
            **_sahne_uret(tanim, tarif),
        )
        for tanim in YABANCILAR
        for tarif in tarifler
    ]
    sorgular += _duz_yabanci_sorgular(kucuk)
    zeminler = cizim.ARKA_PLAN_TURLERI[:2] if kucuk else cizim.ARKA_PLAN_TURLERI
    for sira, tur in enumerate(zeminler):
        zemin = cizim.arka_plan(tur, SAHNE_GENIS, SAHNE_YUKSEK, tohum=400 + sira)
        sorgular.append(
            Sorgu(
                dogru_ad=None,
                zorluk="negatif",
                bozulma=f"boş zemin ({tur})",
                gorsel=cizim.jpeg_bozulmasi(zemin, _SORGU_JPEG_KALITESI),
            )
        )
    sorgular += _desensiz_zemin_sorgulari()
    return sorgular


def _duz_yabanci_sorgular(kucuk: bool) -> list[Sorgu]:
    """SERTLEŞTİRME 1: kütüphanedekiyle aynı renkte, düz, yabancı nesneler.

    Küçük takımda da SEKİZİNİN HEPSİ sorulur (yalnız bozulma sayısı düşer):
    kalite kapısının asıl beklediği delik buradadır, orada kısıntı olmaz.
    """
    bozulmalar = _DUZ_YABANCI_BOZULMALAR[:1] if kucuk else _DUZ_YABANCI_BOZULMALAR
    tarifler = [tarif for tarif in _SORGU_TARIFLERI if tarif.ad in bozulmalar]
    return [
        Sorgu(
            dogru_ad=None,
            zorluk="duz-yabanci",
            bozulma=f"{tanim.ad} / {tarif.ad}",
            **_sahne_uret(tanim, tarif),
        )
        for tanim in DUZ_YABANCILAR
        for tarif in tarifler
    ]


def _desensiz_zemin_sorgulari() -> list[Sorgu]:
    """SERTLEŞTİRME 2: tutunacak deseni GERÇEKTEN olmayan zeminler.

    Küçük takımda da altısının hepsi kalır: her biri tek bir sahnedir (nesne
    yerleştirme yok), ucuzdur, ve motorun düz-düz dalına giren tek sorgu
    ailesidir.
    """
    sorgular = []
    for sira, tur in enumerate(cizim.DESENSIZ_ZEMIN_TURLERI):
        zemin = cizim.desensiz_zemin(tur, SAHNE_GENIS, SAHNE_YUKSEK, tohum=700 + sira)
        sorgular.append(
            Sorgu(
                dogru_ad=None,
                zorluk="desensiz-zemin",
                bozulma=f"desensiz zemin ({tur})",
                gorsel=cizim.jpeg_bozulmasi(zemin, _SORGU_JPEG_KALITESI),
            )
        )
    return sorgular


def _sahne_uret(tanim: NesneTanimi, tarif: Bozulma) -> dict:
    """Tek bir sorgu fotoğrafı + nesnenin sahnedeki kutusu (teşhis için)."""
    tohum = _tohum(tanim.ad, _tohum(tarif.ad, 3))

    gorsel, maske = tanim.cizici()
    gorsel, maske = cizim.donustur(gorsel, maske, tarif.derece, tarif.egim)
    gorsel, maske = cizim.olcekle(gorsel, maske, tarif.kenar)

    sahne = cizim.arka_plan(_zemin_sec(tanim, tarif), SAHNE_GENIS, SAHNE_YUKSEK, tohum=tohum)
    rastgele = np.random.default_rng(tohum)
    x = int(rastgele.integers(10, SAHNE_GENIS - tarif.kenar - 10))
    y = int(rastgele.integers(10, SAHNE_YUKSEK - tarif.kenar - 10))
    cizim.yerlestir(sahne, gorsel, maske, x, y)

    if tarif.ortme > 0:
        # Nesnenin alt bölümü kapanır: önüne bir şey konmuş / önünden geçiyor
        ust = y + int(tarif.kenar * (1 - tarif.ortme))
        cizim.ort(sahne, (x, ust, x + tarif.kenar, y + tarif.kenar), (58, 60, 64))
    if tarif.isik_carpan != 1.0 or tarif.isik_ekle != 0.0:
        sahne = cizim.isik(sahne, tarif.isik_carpan, tarif.isik_ekle)
    if tarif.bulaniklik:
        sahne = cizim.bulanik(sahne, tarif.bulaniklik)

    sahne = cizim.gurultu_ekle(sahne, 3.0, tohum=tohum + 7)
    return {
        "gorsel": cizim.jpeg_bozulmasi(sahne, tarif.jpeg),
        "kutu": (x, y, x + tarif.kenar, y + tarif.kenar),
    }


def _zemin_sec(tanim: NesneTanimi, tarif: Bozulma) -> str:
    if tarif.zemin == "ev":
        return tanim.ev_zemini
    if tarif.zemin == "komsu":
        return tanim.komsu_zemin
    return tanim.yabanci_zemin


def _tohum(ad: str, ek: int) -> int:
    """Ada bağlı ama makineye bağlı OLMAYAN tohum (PYTHONHASHSEED etkisiz)."""
    toplam = sum((sira + 1) * harf for sira, harf in enumerate(ad.encode("utf-8")))
    return (toplam * 31 + ek) % 100_000


# ------------------------------------------------------------------ dökme


def gorselleri_yaz(takim: Takim, klasor: Path) -> int:
    """Takımı diske döker — kullanıcı neyin ölçüldüğünü GÖZÜYLE görebilsin diye."""
    klasor.mkdir(parents=True, exist_ok=True)
    yazilan = 0
    for tanim in KUTUPHANE:  # DUZ_YABANCILAR'ın referansı YOKTUR (kütüphaneye girmez)
        for sira, gorsel in enumerate(referans_gorselleri(tanim), start=1):
            ad = f"referans-{_dosya_adi(tanim.ad)}-{sira}.jpg"
            yazilan += int(cv2.imwrite(str(klasor / ad), gorsel))
    for sira, sorgu in enumerate(takim.sorgular, start=1):
        etiket = _dosya_adi(sorgu.dogru_ad or "negatif")
        ad = f"sorgu-{sira:03d}-{etiket}-{_dosya_adi(sorgu.bozulma)}.jpg"
        yazilan += int(cv2.imwrite(str(klasor / ad), sorgu.gorsel))
    return yazilan


def _dosya_adi(metin: str) -> str:
    degistir = str.maketrans("çğıöşüÇĞİÖŞÜ ", "cgiosucgiosu-")
    sade = metin.translate(degistir).lower()
    return "".join(harf for harf in sade if harf.isalnum() or harf == "-")[:40]

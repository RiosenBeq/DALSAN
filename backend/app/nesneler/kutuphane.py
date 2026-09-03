"""Parmak izi çıkarma ve eşleştirme — MODEL EĞİTİMİ DEĞİLDİR.

Kullanıcı bir nesnenin birkaç fotoğrafını yükler (ölçülen yeterli sayı: 4 —
bkz. teshis.FOTOGRAF_EGRISI); her fotoğraftan iki parmak izi çıkarılır:

1. **Renk parmak izi** (HSV histogramı): nesnenin renk dağılımı. Aydınlatma
   değişse de kabaca korunur; ama aynı renkte başka nesneler karışabilir.
   Tek bir histogram değildir: bütün karenin yanında ORTASININ histogramı da
   çıkarılır (doğru adın sahnenin yanlış köşesine yazılmasını önler) ve
   referans, bir de "bir adım geriden" çerçevelenmiş hâliyle saklanır (kullanıcı
   yakın çekim yapar, tarama penceresi ise nesnenin yanına hep biraz zemin
   alır).
2. **Desen parmak izi** (ORB anahtar noktaları): yazı, logo, kenar deseni.
   Renk aynı olsa bile deseni farklı olan nesneleri ayırır. Kaç noktanın
   eşleştiği tek başına sayılmaz; eşleşmelerin TEK bir dönüşümle (döndürme +
   ölçek + kaydırma) açıklanabilenleri sayılır. Rastgele denk gelen noktalar
   görüntüye dağılır, gerçek eşleşme dağılmaz.

Karar ikisinin BİRLEŞİMİDİR ve iki kanıt birbirini doğrulamalıdır. Kanıtlardan
biri eksik ya da çelişkiliyse ceza DERECELİDİR: kanıt ne kadar yoksa skor o
kadar sertçe kırpılır. Elde YALNIZ renk kanıtı kaldığında ise kırpma değil,
KESİN bir tavan uygulanır: tek kanıtlı bir karşılaştırmanın alabileceği en
yüksek skor, kabul çıtasının bir oranıdır (TEK_KANIT_TAVAN_ORANI) ve çıta kaça
çekilirse çekilsin onun ALTINDA kalır. Yani düz gri desensiz nesnelerde sistem
"zayıf" değil, çekimserdir: isim yazmaz. Yöntem ayırt edici deseni olan
nesnelerde (yazılı pano, sarı tüp, markalı kutu) çalışır. Eşiğin altında kalan
en iyi skor bile kabul edilmez — sistem uydurma isim YAZMAZ, "eşleşme yok" der
(docs/12'deki üç durum ilkesiyle aynı çizgi).

Buradaki her sayı ELDE ÖLÇÜLMÜŞTÜR, tahmin değildir; ölçüm düzeneği
`tests/nesne_kiyas` altındadır ve `.venv/bin/python -m tests.nesne_kiyas` ile
çalışır. Bir sabiti değiştirmeden önce onu koşturun.

Bu dosya `rules/` altında DEĞİLDİR ve olamaz: cv2 kullanır (CLAUDE.md §6).
Kural motoru buradan hiçbir şey import etmez, buraya hiçbir şey yazmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# Karşılaştırmadan önce her görüntü bu boyuta getirilir (hız + tutarlılık)
_STANDART_BOYUT = (160, 160)
# HSV histogram gözleri: ton 24, doygunluk 8 (parlaklık bilerek düşük ağırlıklı —
# fabrika aydınlatması saatten saate değişir, ton değişmez)
_TON_GOZ, _DOYGUNLUK_GOZ = 24, 8
# Renk izinin İKİNCİ katmanı: karşılaştırma karesinin ortasındaki dairenin
# yarıçapı (kenarın bu oranı kadar). Neden gerekli: tek bir histogram bütün
# kareyi tek torbaya atar, "ortada nesne, kenarda zemin" bilgisi kaybolur.
# Ölçümde bunun bedeli görüldü — düz renkli nesnelerde isabetin %45'i doğruydu
# ama işaretin yalnız %4,8'i gerçekten nesnenin üstündeydi; sistem doğru adı
# sahnenin başka bir köşesindeki aynı renkli yamaya yazıyordu. Kullanıcı
# fotoğrafı nesne ortada olacak şekilde çeker; pencerenin ORTASI da uymuyorsa
# renk kanıtı sayılmaz. DAİRE seçildi (kare değil): döndürülmüş bir sorguda
# kare köşeleri farklı şeyleri kapsar, daire kapsamaz.
_MERKEZ_YARICAP_ORANI = 0.24
# Merkez kanıtına tanınan PAY: ortası, bütün karenin bu kadar altında kalabilir
# ve ceza yemez. Sıfır pay (sert veto) ölçüldü ve fazla sertti — pencere
# ızgarası nesneyi hiçbir zaman referanstaki kadar sıkı çerçevelemediği için
# doğru eşleşmeleri de kesiyordu.
_MERKEZ_PAYI = 0.25
# Renk izinin ÜÇÜNCÜ katmanı: aynı görüntünün bir adım GERİDEN çekilmiş hâli.
# Neden: kullanıcı nesnenin fotoğrafını yakından, çerçeveyi doldurarak çeker;
# tarama ise fotoğrafı sabit kare pencerelerle gezer ve o pencereye nesnenin
# yanı sıra hep biraz zemin girer. İki çerçeveleme birbirini tutmaz. Referansın
# kenarları bu oranda dışa doğru uzatılarak (kenar pikseli tekrarlanarak) ikinci
# bir renk izi çıkarılır; karşılaştırma iki çerçevelemenin İYİ olanını kullanır.
# Ölçüldü: aynı şeyi ikinci bir DESEN izi ekleyerek yapmak da işe yarıyordu ama
# tarama süresini üçe katlıyordu — kazancın tamamına yakını renkten geliyor.
_GENIS_CERCEVE = 1.60
# ORB anahtar nokta sayısı
_ORB_NOKTA = 300
# İki ORB tanımlayıcısı bu Hamming mesafesinin altındaysa "eşleşti" sayılır
_ORB_MESAFE = 55
# GEOMETRİ SINAMASI: eşleşen noktalar aynı katı dönüşümle (döndürme + ölçek +
# kaydırma) açıklanabiliyor mu? Rastgele desen eşleşmeleri görüntüye dağılır;
# gerçek eşleşmeler tek bir dönüşümde toplanır. 160x160'lık karşılaştırma
# çerçevesinde bu kadar piksellik sapma hoş görülür.
_GEOMETRI_SAPMA_PX = 12.0
# Geometri sınamasından geçmiş sayılmak için gereken en az uyan nokta. Dönüşümün
# kendisi İKİ noktayla kurulur; dört beş nokta rastlantıyla da hizalanabilir.
# Bunun altındaki desen kanıtı "az" değil, YOK sayılır (0) — çünkü az anahtar
# noktalı bir referansta (düz beyaz baret: ~20 nokta) beş rastgele eşleşme bile
# 0,25'lik bir desen skoru yapar ve yanlış isim yazdırır.
_GEOMETRI_EN_AZ_UYAN = 6
# Desen skorunun PAYDA TABANI. Skor "eşleşen nokta / iki taraftaki en az nokta"
# oranıdır; az anahtar noktalı bir referansta bu oran şişer (17 noktalı bir
# baretin 6 noktası rastlantıyla tutunca skor 0,35 çıkar ve barkoda "baret"
# adı yazılır). Payda bu sayının altına düşmez: az noktalı nesne yüksek desen
# skoru KAZANAMAZ, kararı rengine bırakır.
#
# AÇIK (alt çizgisiz) ad: `teshis.py` bunu okur. Kullanıcıya "bu nesne kolay mı
# tanınır" derken uydurma bir sınır değil, MOTORUN KENDİ dallanma noktası
# kullanılsın diye — motor değişirse teşhis de kendiliğinden onunla değişir.
DESEN_TABAN_NOKTA = 30
# Renk ve desen skorlarının karışım ağırlığı
_RENK_AGIRLIGI = 0.45
_DESEN_AGIRLIGI = 0.55
# İki kanıttan biri bu değerin altındaysa (biri uyuyor, öteki uymuyor) skor
# düşürülür — çelişkili kanıt "eşleşti" saydırmamalı. Ceza SABİT DEĞİLDİR:
# zayıf kanıt sıfıra yaklaştıkça sertleşir, sınıra yaklaştıkça yumuşar.
# Gerekçe ölçüldü: sabit çarpanla, rengi bambaşka ama deseni BİREBİR aynı iki
# nesne (aynı ürünün başka renklisi) 0,38 alıyordu — kanıtın biri hiç yokken
# bu kadar yüksek bir skor "eşleşti" saydırır. Dereceli cezayla aynı çift
# 0,06'ya iner; kanıtı yalnız ZAYIF olan gerçek eşleşmeler ise az kaybeder.
_UYUSMA_ALT_SINIRI = 0.30
_CELISKI_CEZASI = 0.65
# Desen kanıtı için gereken en az anahtar nokta (altındaysa "desensiz").
# Açık ad: `teshis.py` bunu okur — bkz. DESEN_TABAN_NOKTA'daki gerekçe.
EN_AZ_ANAHTAR_NOKTA = 8
# İki taraf da desensizse tutunacak tek iz renktir. Bu üç sayı artık bir
# SKOR değil, "yalnız renge bakarken ne kadar güvenebilirim" GÜVENİDİR (0-1):
# renk barı geçiyorsa güven yüksek, geçmiyorsa düşük tutulur. Güvenin skora
# çevrilmesi aşağıda, `kabul_skoru()` içinde ve ÇITAYA GÖRE yapılır.
_DUZ_RENK_BARI = 0.68
_DUZ_KABUL = 0.62
_DUZ_ZAYIF = 0.38
# Biri desenli öteki düz: kanıtlar uyuşmuyor. Ceza burada da DERECELİDİR —
# düz tarafta hiç anahtar nokta yoksa (bomboş bir duvar/zemin parçası) çelişki
# tamdır ve skor sıfırlanır; birkaç nokta varsa (bulanıklıktan deseni silinmiş
# bir pencere) çelişki kısmidir. Ölçüldü: sabit çarpanla, desenli bir nesneyle
# AYNI RENKTE düz bir yama o nesnenin adını alabiliyordu (0,30) — sistemin
# yazmaması gereken tam da bu isimdir.
# Bu da bir skor değil GÜVENDİR (bkz. _DUZ_KABUL); çıtaya çevrilmesi
# `kabul_skoru()` işidir.
_KANIT_UYUSMAZLIGI = 0.26

# ===========================================================================
# DEĞİŞMEZ KURAL: RENK YALNIZCA DOĞRULAR, TAŞIMAZ
# ===========================================================================
# Bir isim yazılabilmesi için DESEN kanıtının kendi payıyla çıtayı geçmesi
# gerekir. Renk, üstüne eklenip skoru yükseltebilir ama çıtayı geçiren şey
# ASLA renk olamaz. Tek cümlelik hâli: yalnız renge dayanan bir kanıt tek
# başına isim yazdıramaz. Sistem emin değilse "eşleşme yok" der (docs/00:
# kaçırmak sistemin bilinen sınırıdır, yanlış alarm ise güveni bitirir).
#
# Kural TEK ve HER DALA aynı biçimde uygulanır — `benzerlik_ayrintili()`
# skorun DESEN'den gelen payını (`Skor.desen_payi`) da döndürür:
#
#   iki taraf da desensiz    → desen payı 0  → taşımaz
#   biri desenli öteki düz   → desen payı 0  → taşımaz
#   ikisi de desenli         → desen payı = ağırlıklı desen skoru; çıtayı
#                              geçiyorsa skor olduğu gibi, geçmiyorsa aşağıdaki
#                              tavana sıkıştırılır
#
# GÜVENCE ORANSALDIR: taşımayan bir karşılaştırmanın alabileceği EN YÜKSEK
# skor, kabul çıtasının bu oranı kadardır. Oran 1'in ALTINDA olduğu sürece —
# çıta .env'den (NESNE_ESLESME_ESIGI) kaça çekilirse çekilsin — o skor çıtayı
# MATEMATİKSEL OLARAK aşamaz (ham skor tanım gereği 0-1 arasındadır):
#
#     tavan = TEK_KANIT_TAVAN_ORANI · çıta  <  çıta        (0 < oran < 1)
#
# NEDEN SABİT TAVAN OLMAZ — BU HATA BİR KEZ YAPILDI: eski güvence sabitti
# (düz-düz dalının tavanı 0,62, uyuşmazlık dalınınki 0,23) ve çıta 0,42'yken
# doğruydu. Çıta 0,24'e indirilince dal tavanları yerinde kaldı, güvence
# sessizce çöktü: kütüphanede OLMAYAN düz mavi bir kasa "Düz mavi bidon" adını
# almaya başladı (%43), düz gri bir sac levha "Gri boru" (%45). Çıtayı 0,42'ye
# geri çekmek de kapatmıyordu, çünkü delik çıtada değil dalın formülündeydi.
# Oransal tavanda böyle bir sessiz çöküş olamaz; üstelik
# tests/test_nesne_kutuphanesi.py bunu 0,05'ten 0,95'e her çıta için sınar.
#
# NEDEN "DESEN PAYI ÇITAYI GEÇSİN" — İKİNCİ DELİK: ilk düzeltmede yalnız
# desensiz iki dal kapatıldı ve ölçüm ikinci bir deliği gösterdi. Kütüphanedeki
# "Düz beyaz baret" referansının 23 anahtar noktası var (yani motor onu
# "desenli" sayıyor), ama bu noktalar desen değil GÖLGE gürültüsüdür. Beyaz bir
# çuvalın 9 noktası rastlantıyla hizalanınca desen skoru 0,30, renk 0,754 ve
# toplam 0,504 çıkıyordu — skorun 0,339'u (üçte ikisi) RENKTEN geliyordu.
# Desen payı ise yalnız 0,165'ti, yani çıtayı tek başına asla geçemezdi.
# Kural bu yüzden dala değil, PAYA bakar.
TEK_KANIT_TAVAN_ORANI = 0.90
# Bu skorun altındaki eşleşmeler kabul edilmez ("eşleşme yok").
# Sahada değiştirilebilir: .env → NESNE_ESLESME_ESIGI (ayarlar.py).
#
# NEDEN 0,24: kıyas ölçümü (tests/nesne_kiyas) 264 sorguda eşiği 0,10'dan
# 0,60'a tarar ve "yanlış isim sıfır kalırken en çok bulan" noktayı arar.
# 2026-09'da, "renk taşımaz" kuralıyla birlikte YENİDEN ölçüldü: o nokta yine
# 0,24'tür (8/204 isabet, 0 yanlış isim); ilk yanlış isim 0,22'de çıkar, yani
# bir adımlık pay vardır. Çıtanın üstündeki bütün kademelerde de yanlış isim
# sıfırdır ve isabet düşer — yükseltmenin kazancı yoktur.
#
# Bu sayı artık GÜVENLİKTEN sorumlu değildir, yalnız isabet/kaçırma dengesini
# ayarlar: yalnız renge dayanan bir kanıtın isim yazdıramaması çıtanın
# DEĞERİNE değil, çıtayla birlikte oynayan orana bağlıdır
# (TEK_KANIT_TAVAN_ORANI). Yani bu sayı .env'den serbestçe değiştirilebilir;
# değiştiren kişi isabeti oynatır, güvenceyi delemez.
VARSAYILAN_ESIK = 0.24


@dataclass(frozen=True)
class RenkIzi:
    """Renk parmak izi: TÜM karenin histogramı + ORTASININ histogramı."""

    tum: np.ndarray
    merkez: np.ndarray
    # Geniş çerçeve YALNIZ referanslarda doldurulur (aşağıdaki gerekçe):
    # taranan pencerelerde boşuna hesaplanmasın diye None kalır.
    genis_tum: np.ndarray | None = None
    genis_merkez: np.ndarray | None = None


@dataclass(frozen=True)
class Desen:
    """ORB anahtar noktaları: tanımlayıcılar + görüntüdeki YERLERİ.

    Yerler de saklanır, çünkü kaç noktanın eşleştiği tek başına yanıltıcıdır:
    barkodun 300 çubuğuyla düz bir baretin 15 gürültü noktası, hiç ilgisi
    olmadığı hâlde rastgele eşleşebilir. Noktalar elde olunca "bu eşleşmeler
    tek bir dönüşümle açıklanıyor mu" diye sorulabilir (`_desen_benzerligi`).
    """

    tanimlayicilar: np.ndarray
    noktalar: np.ndarray  # (N, 2) float32 — standart 160x160 çerçevesinde

    def __len__(self) -> int:
        return len(self.tanimlayicilar)


@dataclass(frozen=True)
class Skor:
    """Bir karşılaştırmanın HAM sonucu + o sonucun DESEN'den gelen payı.

    İkisi ayrı ayrı gerekir, çünkü kabul kararı ikisine birden bakar: skorun
    kendisi çıtayı geçse bile, çıtayı geçiren şey renkse isim yazılmaz
    (`kabul_skoru`). Ham değer yine de saklanır ki teşhis ve ölçüm "renk ne
    kadar tuttu" sorusunu sorabilsin.

    `ham` tanım gereği 0-1 arasındadır (ağırlıklar toplamı 1, cezalar yalnız
    küçültür); oransal tavanın güvencesi buna dayanır.
    `desen_payi`, `ham`ın içindedir: ham = renk payı + desen payı.
    """

    ham: float
    desen_payi: float


@dataclass
class Parmakizi:
    """Tek bir fotoğrafın renk + desen izi. `desen` None ise nesne desensizdir."""

    renk: RenkIzi
    desen: Desen | None


@dataclass
class Nesne:
    """Bir nesnenin adı ve referans fotoğraflarının parmak izleri."""

    id: int
    ad: str
    parmakizleri: list[Parmakizi] = field(default_factory=list)


def _orb():
    return cv2.ORB_create(nfeatures=_ORB_NOKTA)


def parmakizi_cikar(bgr: np.ndarray | None) -> Parmakizi | None:
    """Görüntüden renk + desen parmak izi. Görüntü yoksa ya da çok küçükse None."""
    if bgr is None or bgr.size == 0 or min(bgr.shape[:2]) < 16:
        return None
    kucuk = cv2.resize(bgr, _STANDART_BOYUT, interpolation=cv2.INTER_AREA)
    return Parmakizi(renk=renk_izi(kucuk, genis_de=True), desen=desen_izi(kucuk))


def _merkez_maskesi(oran: float) -> np.ndarray:
    """Karşılaştırma karesinin ortasındaki daire (255) — dışı 0."""
    maske = np.zeros((_STANDART_BOYUT[1], _STANDART_BOYUT[0]), dtype=np.uint8)
    merkez = (_STANDART_BOYUT[0] // 2, _STANDART_BOYUT[1] // 2)
    cv2.circle(maske, merkez, int(min(_STANDART_BOYUT) * oran), 255, -1)
    return maske


_MERKEZ_MASKESI = _merkez_maskesi(_MERKEZ_YARICAP_ORANI)


def _histogram(hsv: np.ndarray, maske: np.ndarray | None) -> np.ndarray:
    histogram = cv2.calcHist([hsv], [0, 1], maske, [_TON_GOZ, _DOYGUNLUK_GOZ], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram, 0, 1, cv2.NORM_MINMAX)
    return histogram.flatten()


def _geriden(bgr: np.ndarray) -> np.ndarray:
    """Görüntüyü bir adım geriden çekilmiş gibi gösterir (kenarı uzatarak)."""
    pay_y = int(bgr.shape[0] * (_GENIS_CERCEVE - 1) / 2)
    pay_x = int(bgr.shape[1] * (_GENIS_CERCEVE - 1) / 2)
    genis = cv2.copyMakeBorder(bgr, pay_y, pay_y, pay_x, pay_x, cv2.BORDER_REPLICATE)
    return standart_boy(genis)


def renk_izi(bgr: np.ndarray, genis_de: bool = False) -> RenkIzi:
    """Renk izi — taramanın UCUZ ön elemesi de bunu kullanır.

    `genis_de` yalnız REFERANS fotoğraflar için açılır. Geniş çerçeve
    karşılaştırmada hep referans tarafından okunur; taranan her pencere için de
    hesaplamak bir fotoğrafta on binlerce gereksiz iş demekti (ölçüldü: tarama
    süresi üçe katlanıyordu, sonuç ise değişmiyordu).

    Girdi `standart_boy()` çıktısı olmalıdır; merkez maskesi o boyuta göre
    hazırlanmıştır. Başka boyut gelirse sessizce yanlış ölçmek yerine küçültülür.
    """
    if bgr.shape[:2] != (_STANDART_BOYUT[1], _STANDART_BOYUT[0]):
        bgr = standart_boy(bgr)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    izi = RenkIzi(tum=_histogram(hsv, None), merkez=_histogram(hsv, _MERKEZ_MASKESI))
    if not genis_de:
        return izi
    genis_hsv = cv2.cvtColor(_geriden(bgr), cv2.COLOR_BGR2HSV)
    return RenkIzi(
        tum=izi.tum,
        merkez=izi.merkez,
        genis_tum=_histogram(genis_hsv, None),
        genis_merkez=_histogram(genis_hsv, _MERKEZ_MASKESI),
    )


def desen_izi(bgr: np.ndarray) -> Desen | None:
    """Yalnız desen (ORB) izi — taramanın PAHALI adımı budur."""
    gri = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # NOT: ORB öncesi kontrast açma (CLAHE) kardeş sistemde denendi ve GERİ
    # ALINDI — düz/mat yüzeylerde sensör gürültüsünden kararsız sahte desen
    # üretip düz nesnenin kendisiyle eşleşmesini bozuyordu.
    noktalar, tanimlayicilar = _orb().detectAndCompute(gri, None)
    if tanimlayicilar is None or not noktalar:
        return None
    yerler = np.array([nokta.pt for nokta in noktalar], dtype=np.float32)
    return Desen(tanimlayicilar=tanimlayicilar, noktalar=yerler)


def standart_boy(bgr: np.ndarray) -> np.ndarray:
    """Parmak izi çıkarılacak karşılaştırma boyutuna küçültür."""
    return cv2.resize(bgr, _STANDART_BOYUT, interpolation=cv2.INTER_AREA)


def _desensiz(izi: Parmakizi) -> bool:
    """Tutunacak desen kanıtı var mı? (küçük/bulanık/düz yüzeyli nesnelerde yok)"""
    return nokta_sayisi(izi) < EN_AZ_ANAHTAR_NOKTA


def nokta_sayisi(izi: Parmakizi) -> int:
    """Parmak izindeki desen (ORB) anahtar noktası sayısı.

    `teshis.py` de bunu okur: kullanıcıya "bu nesnenin tutunacak deseni var mı"
    derken motorun saydığı sayının aynısı sayılsın diye.
    """
    return 0 if izi.desen is None else len(izi.desen)


def renk_benzerligi(a: RenkIzi, b: RenkIzi) -> float:
    """İki renk izi arasında 0-1 benzerlik.

    İki soru sorulur ve İKİSİ BİRDEN tutmalıdır (küçüğü alınır, ortalaması
    değil): bütün karenin rengi uyuyor mu, ORTASININ rengi uyuyor mu? Bunlar
    birbirini tamamlayan değil, birbirini DOĞRULAYAN kanıtlardır. Bütün kare
    uyup ortası uymuyorsa doğru renk sahnenin yanlış yerindedir; ortası uyup
    bütünü uymuyorsa nesnenin yalnız bir parçası pencereye girmiştir. İkisinde
    de "buldum" demek işareti yanlış yere koydurur.

    Bu soru çifti referansın İKİ çerçevelemesi için ayrı ayrı sorulur (yakın
    çekim ve bir adım geriden — `_GENIS_CERCEVE`); iyi olan kazanır, çünkü
    pencerenin nesneyi hangi sıkılıkta çerçevelediğini önceden bilemeyiz.

    `arama.py`'deki ucuz ön eleme de tam bu fonksiyonu çağırır; dolayısıyla
    `renk_alt_siniri()` sınırı bu değerin ta kendisi üzerinde tanımlıdır.
    """
    dar = _cerceve_benzerligi(a, b.tum, b.merkez)
    if b.genis_tum is None or b.genis_merkez is None:
        return dar
    return max(dar, _cerceve_benzerligi(a, b.genis_tum, b.genis_merkez))


def _cerceve_benzerligi(aday: RenkIzi, tum: np.ndarray, merkez: np.ndarray) -> float:
    """Aday izin, referansın TEK bir çerçevelemesine benzerliği."""
    return min(_kesisim(aday.tum, tum), _kesisim(aday.merkez, merkez) + _MERKEZ_PAYI)


def _kesisim(a: np.ndarray, b: np.ndarray) -> float:
    """Histogram kesişimi: 0 (hiç benzemiyor) — 1 (aynı)."""
    toplam = float(np.sum(np.maximum(a, b)))
    if toplam <= 0:
        return 0.0
    return float(np.sum(np.minimum(a, b)) / toplam)


def _desen_benzerligi(a: Desen | None, b: Desen | None) -> float:
    """Eşleşen ORB anahtar noktalarının oranı — İKİ elemeden geçirilmiş.

    1. Oran testi (Lowe): bir noktanın EN yakın eşi, ikinci en yakınından
       belirgin iyi değilse eşleşme rastlantısaldır ve sayılmaz.
    2. GEOMETRİ sınaması: kalan eşleşmelerin, iki görüntü arasındaki TEK bir
       dönüşümle (döndürme + ölçek + kaydırma) açıklanabilenleri sayılır.
       Neden şart: oran testi tek tek noktalara bakar, bütüne bakmaz. Ölçümde
       "barkod" sorulunca "düz beyaz baret" adının 0,40 skorla yazıldığı
       görüldü — baretin az sayıdaki gürültü noktası barkodun çubuklarına
       dağınık biçimde denk gelmişti. Gerçek bir eşleşmede noktalar dağılmaz,
       hepsi aynı yer değiştirmeyi gösterir. Bu sınama o yanlış isimleri
       (ölçümde 5 taneydi, hepsi bu daldandı) sıfıra indirir.
    """
    if a is None or b is None or len(a) < 8 or len(b) < 8:
        return 0.0
    eslestirici = cv2.BFMatcher(cv2.NORM_HAMMING)
    aday_yerleri, referans_yerleri = [], []
    for komsu in eslestirici.knnMatch(a.tanimlayicilar, b.tanimlayicilar, k=2):
        if len(komsu) < 2:
            continue
        birinci, ikinci = komsu
        if birinci.distance <= _ORB_MESAFE and birinci.distance < 0.75 * ikinci.distance:
            aday_yerleri.append(a.noktalar[birinci.queryIdx])
            referans_yerleri.append(b.noktalar[birinci.trainIdx])

    iyi = _geometrik_uyanlar(aday_yerleri, referans_yerleri)
    payda = max(min(len(a), len(b)), DESEN_TABAN_NOKTA)
    # knnMatch bire-çok eşleşebildiği için oran 1'i aşabilir; skor 0-1 kalmalı
    return min(iyi / payda, 1.0)


def _geometrik_uyanlar(aday_yerleri: list, referans_yerleri: list) -> int:
    """Aynı dönüşümle açıklanabilen eşleşme sayısı; yetersizse 0.

    Eşik altındaki sayı "biraz benziyor" diye kısmen sayılmaz, hiç sayılmaz:
    ölçümde yanlış isimlerin tamamı böyle avuç içi kadar bir eşleşme
    yığınından çıkıyordu.
    """
    if len(aday_yerleri) < _GEOMETRI_EN_AZ_UYAN:
        return 0
    _, uyanlar = cv2.estimateAffinePartial2D(
        np.array(referans_yerleri, dtype=np.float32).reshape(-1, 1, 2),
        np.array(aday_yerleri, dtype=np.float32).reshape(-1, 1, 2),
        method=cv2.RANSAC,
        ransacReprojThreshold=_GEOMETRI_SAPMA_PX,
        maxIters=200,
        refineIters=0,
    )
    if uyanlar is None:
        return 0
    uyan = int(uyanlar.sum())
    return uyan if uyan >= _GEOMETRI_EN_AZ_UYAN else 0


def benzerlik_ayrintili(aday: Parmakizi, referans: Parmakizi) -> Skor:
    """İki parmak izinin HAM karşılaştırması — hangi daldan geçtiğiyle birlikte.

    İki kanıt (renk ve desen) birbirini DOĞRULAMALIDIR. Yalnız biri uyuyorsa
    skor düşürülür; çünkü:
    - aynı renk + farklı desen  → iki ayrı gri elektrik panosu
    - farklı renk + aynı desen  → aynı üreticinin başka renk ürünü
    Bunları "eşleşti" saymak, tarama raporunu güvenilmez yapar.

    Dönen `Skor`, ham değerin yanında DESEN'den gelen payı da taşır. Desen
    kanıtının hiç olmadığı ya da çelişik olduğu iki dalda bu pay SIFIRDIR;
    kararı çıtayla karşılaştıran `kabul_skoru()` böyle bir değeri çıtanın
    altına indirir (bkz. TEK_KANIT_TAVAN_ORANI). Burada çıta bilinmez ve
    bilinmemelidir: bu fonksiyon ölçer, karar vermez.
    """
    renk = renk_benzerligi(aday.renk, referans.renk)
    aday_desensiz = _desensiz(aday)
    referans_desensiz = _desensiz(referans)

    if aday_desensiz != referans_desensiz:
        # Biri desenli, öteki düz: kanıtlar UYUŞMUYOR (aynı nesne olsaydı
        # ikisinde de benzer desen çıkardı). Güven, düz tarafta ne kadar nokta
        # kaldığına göre derecelenir: hiç yoksa sıfırdır.
        duz_nokta = min(nokta_sayisi(aday), nokta_sayisi(referans))
        return Skor(renk * _KANIT_UYUSMAZLIGI * duz_nokta / EN_AZ_ANAHTAR_NOKTA, 0.0)

    if aday_desensiz and referans_desensiz:
        # İkisi de düz/desensiz: tutunacak tek iz renktir. Renk barı geçilmediyse
        # güven ayrıca düşürülür — orta karar bir renk benzerliği "aynı nesne"
        # saydırmaya hiç yaklaşmasın.
        return Skor(renk * (_DUZ_KABUL if renk >= _DUZ_RENK_BARI else _DUZ_ZAYIF), 0.0)

    desen = _desen_benzerligi(aday.desen, referans.desen)
    renk_payi = _RENK_AGIRLIGI * renk
    desen_payi = _DESEN_AGIRLIGI * desen
    ceza = 1.0
    zayif = min(renk, desen)
    if zayif < _UYUSMA_ALT_SINIRI:
        ceza = _CELISKI_CEZASI * (zayif / _UYUSMA_ALT_SINIRI)
    # Ceza iki paya da uygulanır ki `desen_payi` gerçekten "skorun desenden
    # gelen kısmı" olsun: ham = renk payı + desen payı, her zaman.
    return Skor((renk_payi + desen_payi) * ceza, desen_payi * ceza)


def tek_kanit_tavani(esik: float) -> float:
    """Kararı fiilen RENGE kalmış bir karşılaştırmanın alabileceği en yüksek skor.

    Kabul çıtasının `TEK_KANIT_TAVAN_ORANI` katıdır ve oran 1'in altında
    olduğu için sonuç HER ZAMAN çıtanın altındadır. Güvencenin tamamı bu tek
    satırdadır; `tests/test_nesne_kutuphanesi.py` bunu 0,05'ten 0,95'e kadar
    her çıta için sınar.
    """
    return esik * TEK_KANIT_TAVAN_ORANI


def desen_tasiyor(skor: Skor, esik: float) -> bool:
    """Skoru çıtanın üstüne taşıyan şey DESEN mi? (renkse isim yazılmaz)"""
    return skor.desen_payi >= esik


def kabul_skoru(skor: Skor, esik: float) -> float:
    """Ham karşılaştırmayı, çıtayla karşılaştırılabilir skora çevirir.

    Desen payı çıtayı tek başına geçiyorsa skor olduğu gibi geçer: renk orada
    yalnızca doğrulama görevindedir. Geçmiyorsa skor `[0, tavan]` aralığına
    ORANI KORUYARAK sıkıştırılır — sıralama bozulmaz (hangi karşılaştırma daha
    çok tuttuysa o hâlâ önde), ama çıta MATEMATİKSEL OLARAK aşılamaz.

    Sıkıştırma yerine düz bir `min()` KULLANILMADI, bilerek: `min` bütün zayıf
    adayları tavana yığar ve kullanıcıya "en yüksek benzerlik %22, çıta %24"
    dedirtir — teşhis buna bakıp "kıl payı kaldı, bu açıdan bir fotoğraf
    ekleyin" der (teshis._YAKIN_PAYI), oysa fotoğraf eklemek bu durumu
    düzeltmez. Oranı koruyan sıkıştırmada zayıf kanıt zayıf sayı olarak görünür.
    """
    if desen_tasiyor(skor, esik):
        return skor.ham
    return skor.ham * tek_kanit_tavani(esik)


def benzerlik(aday: Parmakizi, referans: Parmakizi, esik: float = VARSAYILAN_ESIK) -> float:
    """İki parmak izi arasında 0-1 arası, ÇITAYA GÖRE kabul edilebilir benzerlik.

    Çıta parametredir çünkü "renk taşımaz" güvencesi çıtaya ORANLIDIR: çıta
    .env'den kaça çekilirse çekilsin, desen payı çıtayı geçmeyen bir kanıt
    tek başına isim yazdıramaz. Çağıran, sahada kullanılan çıtayı geçirmelidir.
    """
    return kabul_skoru(benzerlik_ayrintili(aday, referans), esik)


def renk_alt_siniri(esik: float) -> float:
    """Renk benzerliği bunun ALTINDAYSA, desen ne kadar uysa da eşik aşılamaz.

    Neden var: tarama, yüklenen fotoğrafı yüzlerce pencereye bölüp her birini
    kütüphaneyle karşılaştırır. Pahalı olan adım desen (ORB) çıkarımıdır; renk
    histogramı ise ucuzdur. Bu fonksiyon, "bu pencere için desen hesaplamaya
    hiç değmez" diyebilmenin GÜVENLİ sınırını verir — hesap `benzerlik()`
    formülünün üst sınırından çıkarılmıştır, tahmin değildir. Desen en fazla 1
    olabileceğine göre, bir renk değeri `r` için alınabilecek en yüksek skor:

      r ≥ 0,30 →  0,45·r + 0,55                       (ceza yok)
      r < 0,30 → (0,45·r + 0,55) · 0,65 · r / 0,30     (ceza dereceli)

    Tek kanıtlı dallar (desensiz ve uyuşmazlık) bu hesaba HİÇ girmez: onların
    tavanı zaten çıtanın altındadır (`tek_kanit_tavani`), yani renk 1,0 bile
    olsa eşiği geçemezler. Eleme yalnızca hızlandırır; sonucu DEĞİŞTİRMEZ —
    tests/test_nesne_kutuphanesi.py bunu rastgele çiftlerle sınar.
    """
    sinirda = _RENK_AGIRLIGI * _UYUSMA_ALT_SINIRI + _DESEN_AGIRLIGI
    if esik > sinirda:  # ancak cezasız dalda ulaşılabilir
        return min((esik - _DESEN_AGIRLIGI) / _RENK_AGIRLIGI, 1.0)
    if esik > sinirda * _CELISKI_CEZASI:  # cezalı dalın tavanının üstünde
        return _UYUSMA_ALT_SINIRI
    # Cezalı dal: (a·r + b)·r = esik ikinci derece denklemi
    a = _RENK_AGIRLIGI * _CELISKI_CEZASI / _UYUSMA_ALT_SINIRI
    b = _DESEN_AGIRLIGI * _CELISKI_CEZASI / _UYUSMA_ALT_SINIRI
    return max(float((-b + np.sqrt(b * b + 4 * a * esik)) / (2 * a)), 0.0)


def en_iyi_eslesme(
    aday_bgr: np.ndarray, nesneler: list[Nesne], esik: float = VARSAYILAN_ESIK
) -> tuple[Nesne | None, float]:
    """Aday görüntüyü kütüphanedeki nesnelerle karşılaştırır.

    Nesnenin BİRDEN ÇOK açıdan fotoğrafı varsa en iyi eşleşen açı kullanılır —
    bu yüzden farklı açılardan fotoğraf yüklemek isabeti artırır.
    Eşiğin altındaki en iyi skor bile kabul EDİLMEZ: (None, skor) döner.
    """
    aday = parmakizi_cikar(aday_bgr)
    if aday is None or not nesneler:
        return None, 0.0
    return en_iyi_eslesme_izinden(aday, nesneler, esik)


def en_iyi_eslesme_izinden(
    aday: Parmakizi, nesneler: list[Nesne], esik: float = VARSAYILAN_ESIK
) -> tuple[Nesne | None, float]:
    """`en_iyi_eslesme` ile aynı karar; parmak izi hazırsa yeniden hesaplamaz.

    Çıta yalnız "kabul edildi mi" sorusunda değil, skorun KENDİSİNDE de
    kullanılır (`kabul_skoru`): tek kanıtlı bir aday çıtanın altında bir skor
    alır, dolayısıyla kabul edilebilir bir adayı asla geçemez — sıralamayı
    bozmadan elenir.
    """
    en_iyi_nesne, en_iyi_skor = None, 0.0
    for nesne in nesneler:
        for referans in nesne.parmakizleri:
            # En iyi eşleşen açı kazanır (top-2 harmanı kardeş sistemde denendi
            # ve GERİ ALINDI: yalnız bir açıdan benzeyen gerçek eşleşmeleri
            # eşiğin altına itiyor, "farklı açı eklemek isabeti artırır"
            # vaadini tersine çeviriyordu).
            skor = benzerlik(aday, referans, esik)
            if skor > en_iyi_skor:
                en_iyi_nesne, en_iyi_skor = nesne, skor
    if en_iyi_skor < esik:
        return None, en_iyi_skor
    return en_iyi_nesne, en_iyi_skor


# ============================================================================
# DENENDİ VE GERİ ALINDI — aynı yollara tekrar girilmesin diye yazılıyor.
# 1-5 arası `tests/nesne_kiyas` tam takımıyla (12 nesne, 194 sorgu) ölçüldü;
# 6 ve sonrası sertleştirilmiş takımla (264 sorgu).
# ============================================================================
#
# 1) NESNE BAŞINA ÇITA. Her nesnenin kendi fotoğraflarına benzerliği ile
#    kütüphanedeki başkalarına benzerliği ölçülüp (leave-one-out) çıtası bu
#    ikisinin arasına konuldu. Ölçüm bu iki dağılımın GERÇEKTEN ayrıştığını
#    gösterdi (logolu kutuda +0,52, birbirinin eşi iki gri panoda -0,06), ama
#    sonuç KÖTÜLEŞTİ: 81 isabet → 52. Sebebi şu: karışabilir nesnelerin çıtası
#    yükselince o nesneler artık HİÇ bulunamıyor, kazanılan yanlış-isim payı
#    ise kaybedilen isabeti karşılamıyor. Fikir mantıklı, sonucu değil.
#
# 2) REFERANSI YAKINLAŞTIRARAK ÇOK ÖLÇEKLİ PARMAK İZİ (referansın ortasını
#    kırpıp ayrıca izlemek). FELAKET: sıkı kırpılmış referans neredeyse tek
#    renkli bir yamaya dönüşüyor ve her şeye benziyor — her eşikte yüzlerce
#    yanlış isim. UZAKLAŞTIRMAK (kenarı uzatarak geniş çerçeve) ise işe
#    yaradı; bugün `_GENIS_CERCEVE` olarak duruyor.
#
# 3) GENİŞ ÇERÇEVE İÇİN AYRI BİR DESEN (ORB) İZİ. İşe yarıyordu ama tarama
#    süresini üçe katlıyordu. Ölçüldü: kazancın tamamına yakını RENK
#    katmanından geliyor, desen katmanı eklemek isabeti kıl payı oynatıyor.
#    Bu yüzden geniş çerçeve yalnız renk izinde tutuldu.
#
# 4) MERKEZ RENK KANITINI SERT VETO YAPMAK (`_MERKEZ_PAYI = 0`). İşareti
#    nesnenin üstüne getiriyordu ama isabeti düşürüyordu (52 → 43): pencere
#    ızgarası nesneyi hiçbir zaman referanstaki kadar sıkı çerçevelemiyor.
#    Paylı hâli (0,25) ikisini birden kazandırdı.
#
# 5) ÇELİŞKİ CEZASINI SABİT TUTUP ÇITAYI DÜŞÜRMEK. Kıyas takımında yanlış isim
#    çıkmıyordu ama `tests/test_nesne_kutuphanesi.py` içindeki saf tuzaklar
#    ötmüştü: rengi bambaşka ama deseni birebir aynı iki nesne 0,38, desenli
#    bir nesneyle aynı renkte DÜZ bir yama 0,30 alıyordu. Kıyas takımının
#    zeminleri nesnelerle aynı renkte olmadığı için bu delik orada görünmüyor.
#    Dereceli cezalar bu iki skoru 0,11 ve 0,00'a indirdi; bedeli isabette 87 →
#    53 oldu ve bilerek ödendi (docs/00: yanlış alarm güveni bitirir).
#
# 6) ÇITAYI YÜKSELTEREK "RENK TAŞIYOR" DELİĞİNİ KAPATMAK. Sertleştirilmiş takım
#    (264 sorgu) çıtayı 0,42'ye geri çekmenin yanlış ismi 76'dan 58'e indirip
#    BİTİRMEDİĞİNİ gösterdi. Sebebi basit: delik çıtada değil, dalın
#    formülündeydi — düz-düz dalının tavanı (0,62) çıtadan (0,24) yüksekti ve
#    çıtayla birlikte oynamıyordu. Bugünkü çözüm tavanı çıtaya BAĞLADI.
#
# 7) "RENK TAŞIMAZ" KURALINI GEVŞETMEK (desen payından çıtanın tamamı yerine
#    bir kesri istemek). Ölçüldü: istenen pay çıtanın 0,8'ine indirilince
#    isabet 8'den 21'e çıkıyor ama yanlış isim geri geliyor (1), 0,5'te isabet
#    30 / yanlış isim 3, 0'da isabet 33 / yanlış isim 4. Yanlış isimlerin
#    TAMAMI tek bir kütüphane nesnesinden ("Düz beyaz baret") geliyor: o nesne
#    aslında düz, ama gölgesinden 23-51 ORB noktası çıkardığı için motor onu
#    "desenli" sayıyor ve beyaz bir çuvalın 9 gürültü noktası hizalanabiliyor.
#    Doğru çözüm çıtayı ya da oranı oynatmak DEĞİL, referansın deseninin
#    AYIRT EDİCİ olup olmadığını ölçmektir (docs/07-YOL-HARITASI.md).
#
# 8) DÜZ NESNELERE "İKİNCİ KANIT" ARAMAK — RENKTEN BAĞIMSIZ BİR ÖLÇÜ.
#    Düz/desensiz nesnelerin isabeti bugün sıfırdır ve bunu kurtarmanın tek
#    meşru yolu, renge dayanmayan İKİNCİ bir kanıt bulmaktır (çünkü "renk
#    taşımaz" kuralı gevşetilemez). Üç aile ayrı ayrı ve birlikte ölçüldü;
#    ÜÇÜ DE REDDEDİLDİ. Ölçüm düzeneği: tam takım, düz nesnelerin sorguları
#    ile kütüphanedekiyle AYNI RENKTEKİ yabancı nesnelerin sorguları, her
#    ikisi de AYNI bozulmalarla ve IDEAL çerçeveyle (yani adaylara sahada
#    hiç olmayacak kadar iyi bir şans tanınarak).
#
#    Ölçülen sayı AYIRT GÜCÜ'dür (AUC): "düz nesnenin kendi sorgusu, aynı
#    renkteki yabancıdan daha yüksek skor alıyor mu?" 0,50 yazı-turadır.
#
#      aday kanıt                          adil AUC
#      A  uzamsal renk düzeni (2x2+merkez)   0,190
#      A' baskın renk bölgesinin halka profili + doluluğu   0,222
#      B  kenar/siluet haritası (8x8)        0,000
#      B' satır-sütun kenar profili          0,000
#      B''Hu momentleri (Otsu + en büyük kontur)  ölçülemedi (bkz. aşağıda)
#      C  kenar yönelim dağılımı 3x3x8 (HOG) 0,381
#      C' kenar yönelim dağılımı 2x2x8       0,508
#      P  parlaklık düzeni (8x8)             0,143
#      A+B+C birlikte                        0,016
#      hepsi birlikte                        0,000
#      ORACLE (her sorguda en iyi aday)      0,333
#
#    HEPSİ 0,50'NİN ALTINDA: bu kanıtlar zayıf değil, TERSİNE çalışıyor.
#    Sebebi ölçülünce anlaşıldı ve tasarımı bağlar: bir nesne ne kadar
#    desensizse, aynı renkteki BAŞKA bir desensiz nesnenin "temiz referans
#    fotoğrafı"na o kadar benzer. Yabancı düz nesneler (mavi kasa, mavi örtü,
#    gri sac levha) pürüzsüz oldukları için referansa, sahnede dönmüş /
#    bulanıklaşmış / yarısı örtülmüş GERÇEK nesneden DAHA ÇOK benziyor.
#    Bu yüzden aynı nesnenin dört referansı birbirini, ikizini tanıdığından
#    DAHA AZ tanıyor (ör. HOG: kendi 0,827 — ikizi 0,850). Sıralaması ters
#    olan bir kanıt hiçbir eşik, ağırlık ya da birleşimle düzelmez.
#
#    Hu momentleri ayrıca elendi: aynı nesnenin dört referansı arasındaki
#    tutarlılığı 0,110 çıktı (yani nesne kendini bile tanımıyor), çünkü Otsu
#    eşiklemesi tarama penceresinde nesneyi zeminden ayıramıyor.
#
#    SONUÇ: düz/desensiz nesneler bu yöntemle BULUNAMAZ ve bu, kapatılmamış
#    bir eksiktir. Gizlenmiyor: Nesneler sayfasında rozet "Düz renkli —
#    bulunamaz" der, kılavuzda ve "Bu yöntem ne yapar, ne yapmaz" bölümünde
#    de yazar. Sıradaki fikir (ölçülmedi): tarama penceresini nesnenin
#    silüetine OTURTMAK — bugün kare pencere ızgarası nesneyi hiçbir zaman
#    referanstaki gibi çerçevelemiyor, dolayısıyla biçim kanıtı daha
#    hesaplanırken bozuluyor (docs/07-YOL-HARITASI.md).

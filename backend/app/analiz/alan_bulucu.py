"""Fabrika alanını GÖRÜNTÜDEN tanıma: zemindeki boyalı çizgilerden bölge önerisi.

NE İŞE YARAR
Kullanıcı bölgeyi bugün köşe köşe tıklayarak çiziyor. Fabrika zemininde o alan
ZATEN BOYALI: yaya yolu sarı çizgilerle, yükleme alanı beyaz çerçeveyle,
yasak bölge sarı-siyah taramayla işaretlidir. Bu modül o boyayı bulur ve
kullanıcıya hazır bir poligon ÖNERİR. Kullanıcı tek düğmeyle kabul eder,
beğenmezse köşeleri sürükleyip düzeltir ya da tümüyle yok sayar.

ÖNERİ, KARAR DEĞİLDİR. Bu modül veritabanına hiçbir şey yazmaz ve hiçbir
kuralı etkilemez. Yanlış bir öneri, kullanıcının kabul etmediği bir çizimdir —
sistemin davranışı değişmez. Bu yüzden cömert davranır: şüpheli adayı da
gösterir, seçmeyi kullanıcıya bırakır.

NASIL ÇALIŞIR (üç adım, hepsi OpenCV — yeni kütüphane YOK)
1. Renk maskesi: HSV uzayında sarı ve beyaz boya ayrı ayrı maskelenir.
   HSV seçildi çünkü fabrika aydınlatması gün içinde değişir; parlaklıktan
   bağımsız olan TON (hue) kanalı sarıyı sabah da akşam da aynı bulur.
2. Boşlukları kapatma: yol çizgileri çoğu zaman KESİKLİDİR ve yaya yolu İKİ
   paralel çizgiyle işaretlidir. Maskeye morfolojik kapama uygulanarak hem
   kesikler birleştirilir hem iki paralel çizgi arasındaki şerit doldurulur —
   böylece "çizgi" değil "ALAN" bulunur; kullanıcının istediği de budur.
3. Poligonlaştırma: kontur bulunur, `approxPolyDP` ile köşe sayısı azaltılır
   (12 köşeli bir bölgeyi kullanıcı elle düzeltemez), normalize (0-1)
   koordinata çevrilir.

NEDEN `rules/` DEĞİL: OpenCV kullanır (CLAUDE.md §6). Kural mantığına da
girmez — çıktısı yalnızca arayüzde gösterilen bir öneridir.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Boya renkleri (HSV alt/üst sınır)
# ---------------------------------------------------------------------------
#
# OpenCV'de H kanalı 0-179'dur (0-359 DEĞİL). Sarı boya yaklaşık H=20-35'te
# durur; sınırlar sahada solmuş, tozlanmış boyayı da yakalayacak kadar geniş
# tutuldu. Doygunluk (S) alt sınırı önemlidir: onsuz gri beton da "sarı" çıkar.
_SARI_ALT = np.array([18, 70, 80], dtype=np.uint8)
_SARI_UST = np.array([38, 255, 255], dtype=np.uint8)

# Beyaz boya: TON yok (her ton olabilir), ayırt edici olan DÜŞÜK doygunluk +
# YÜKSEK parlaklıktır. Üst S sınırı düşük tutulmazsa açık gri zemin de girer.
_BEYAZ_ALT = np.array([0, 0, 185], dtype=np.uint8)
_BEYAZ_UST = np.array([179, 45, 255], dtype=np.uint8)

# Kapama çekirdeği, karenin kısa kenarının yüzdesi olarak. Sabit piksel
# kullanılamaz: aynı çekirdek 640px'lik bir akışta şeridi kapatırken
# 1920px'lik akışta kesikleri hiç birleştiremez.
_KAPAMA_ORANI = 0.035

# Aday alan, karenin bu kadarından küçükse gürültüdür (boya lekesi, yansıma);
# bu kadarından büyükse alan değil, kamera görüşünün tamamıdır.
_EN_KUCUK_ALAN_ORANI = 0.012
_EN_BUYUK_ALAN_ORANI = 0.82

# Poligon sadeleştirme: çevrenin bu oranı kadar sapmaya izin verilir. Büyük
# değer az köşe (kaba), küçük değer çok köşe (elle düzeltilemez) demektir.
_SADELESTIRME_ORANI = 0.018

# Kullanıcıya gösterilecek en çok köşe. Bunu aşan poligon, dışbükey zarfına
# indirgenir: 30 köşeli tırtıklı bir alan düzeltilemez.
_EN_COK_KOSE = 12

# YAYA YOLU ÖZEL DURUMU: yaya yolu tek bir çizgiyle değil, İKİ PARALEL
# çizgiyle işaretlenir ve aradaki boşluk (yolun kendisi) kapama çekirdeğinden
# kat kat geniştir. Birinci geçiş bu yüzden iki çizgiyi ayrı ayrı bulur ve
# ikisini de "çok ince" diye eler. İkinci geçiş, birbirine bu mesafeden yakın
# parça KÜMELERİNİ tek alan sayar ve kümenin dışbükey zarfını önerir —
# aradaki yol da alana dahil olur. Oran, karenin kısa kenarına göredir.
_GRUP_MESAFE_ORANI = 0.28

# Bir küme "alan" sayılmak için en az bu kadar ayrı parça içermeli. Tek parça
# zaten birinci geçişte değerlendirildi; onu ikinci kez önermek çift kayıt olur.
_EN_AZ_GRUP_PARCASI = 2

# Ölçüm hep bu genişlikte yapılır. 4K bir kare üzerinde morfoloji saniyeler
# sürerdi; alan tanıma ise kullanıcının düğmeye basıp beklediği bir iştir.
_ISLEME_GENISLIGI = 960


@dataclass
class AlanOnerisi:
    """Görüntüden bulunan tek bir bölge adayı.

    `poligon` normalize (0-1) koordinattır — kaydedilen bölgelerle aynı
    sözleşme (rules/tipler.py), böylece kullanıcı kabul edince dönüşüm gerekmez.
    """

    poligon: list[tuple[float, float]]
    tip: str  # önerilen zones.zone_type değeri
    tip_adi: str  # kullanıcıya görünen Türkçe ad
    guven: float  # 0-1: boyanın ne kadar belirgin olduğu
    aciklama: str  # "Zeminde sarı çizgiyle çevrili alan bulundu."

    @property
    def alan_yuzdesi(self) -> float:
        """Poligonun karenin yüzde kaçını kapladığı (ekranda gösterilir)."""
        return round(_poligon_alani(self.poligon) * 100, 1)


def alanlari_bul(kare: np.ndarray, en_cok: int = 4) -> list[AlanOnerisi]:
    """Karedeki boyalı alanları bulur, güvene göre sıralı öneri listesi döner.

    Hiçbir şey bulunamazsa BOŞ LİSTE döner — bu bir hata değildir: her fabrika
    zemininde boya yoktur. Çağıran taraf bunu kullanıcıya "bulunamadı, elle
    çizin" diye söyler.
    """
    if kare is None or kare.size == 0:
        return []

    kucuk, _ = _isleme_boyutuna_getir(kare)
    hsv = cv2.cvtColor(kucuk, cv2.COLOR_BGR2HSV)

    oneriler: list[AlanOnerisi] = []
    for maske_adi, alt, ust, tip, tip_adi in (
        ("sarı", _SARI_ALT, _SARI_UST, "pedestrian_path", "Yaya yolu"),
        ("beyaz", _BEYAZ_ALT, _BEYAZ_UST, "loading_area", "Yükleme alanı"),
    ):
        maske = cv2.inRange(hsv, alt, ust)
        oneriler.extend(_maskeden_oneriler(maske, kucuk.shape, maske_adi, tip, tip_adi))

    # Koordinatlar NORMALİZE üretildiği için küçültme ölçeğinin geri
    # çevrilmesi gerekmez: 0-1 aralığı her iki boyutta da aynıdır.
    oneriler.sort(key=lambda o: o.guven, reverse=True)
    return _cakisanlari_ele(oneriler)[:en_cok]


def maske_onizlemesi(kare: np.ndarray) -> np.ndarray | None:
    """Sistemin "boya" saydığı pikselleri işaretleyen görsel (teşhis içindir).

    Kullanıcı "neden bulamadı" diye sorduğunda cevabı ekranda görmelidir:
    boya soluksa maske boş çıkar ve bu, eşik oynamaktan daha açık bir yanıttır.
    """
    if kare is None or kare.size == 0:
        return None
    kucuk, _ = _isleme_boyutuna_getir(kare)
    hsv = cv2.cvtColor(kucuk, cv2.COLOR_BGR2HSV)
    sari = cv2.inRange(hsv, _SARI_ALT, _SARI_UST)
    beyaz = cv2.inRange(hsv, _BEYAZ_ALT, _BEYAZ_UST)

    gorsel = kucuk.copy()
    gorsel[sari > 0] = (0, 200, 255)  # sarı boya → turuncu işaret
    gorsel[beyaz > 0] = (255, 180, 80)  # beyaz boya → mavi işaret
    return cv2.addWeighted(kucuk, 0.45, gorsel, 0.55, 0)


# ---------------------------------------------------------------------------
# iç
# ---------------------------------------------------------------------------


def _isleme_boyutuna_getir(kare: np.ndarray) -> tuple[np.ndarray, float]:
    """Kareyi sabit genişliğe küçültür (büyükse). Döner: (kare, ölçek)."""
    yukseklik, genislik = kare.shape[:2]
    if genislik <= _ISLEME_GENISLIGI:
        return kare, 1.0
    olcek = _ISLEME_GENISLIGI / float(genislik)
    yeni = (int(genislik * olcek), max(int(yukseklik * olcek), 1))
    return cv2.resize(kare, yeni, interpolation=cv2.INTER_AREA), olcek


def _maskeden_oneriler(
    maske: np.ndarray, bicim: tuple, maske_adi: str, tip: str, tip_adi: str
) -> list[AlanOnerisi]:
    yukseklik, genislik = bicim[:2]
    kare_alani = float(genislik * yukseklik)
    if kare_alani <= 0:
        return []

    # Kesik çizgileri ve paralel şeritleri birleştir. ÖNCE kapama (boşluk
    # doldurur), SONRA açma (kalan tekil gürültü noktalarını siler).
    kenar = max(int(min(genislik, yukseklik) * _KAPAMA_ORANI) | 1, 3)
    cekirdek = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kenar, kenar))
    kapali = cv2.morphologyEx(maske, cv2.MORPH_CLOSE, cekirdek)
    kapali = cv2.morphologyEx(
        kapali, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )

    konturlar, _ = cv2.findContours(kapali, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    oneriler: list[AlanOnerisi] = []

    # İkinci geçiş: birbirine yakın parçaları tek alan say (paralel çizgilerle
    # işaretlenmiş yaya yolu). Birinci geçişin bulduklarıyla birlikte sıralanır.
    for zarf in _yakin_parca_zarflari(kapali, genislik, yukseklik):
        oneriler.extend(
            _konturdan_oneri(zarf, genislik, yukseklik, kare_alani, maske_adi, tip, tip_adi)
        )

    for kontur in konturlar:
        oneriler.extend(
            _konturdan_oneri(kontur, genislik, yukseklik, kare_alani, maske_adi, tip, tip_adi)
        )
    return oneriler


def _konturdan_oneri(
    kontur: np.ndarray,
    genislik: int,
    yukseklik: int,
    kare_alani: float,
    maske_adi: str,
    tip: str,
    tip_adi: str,
) -> list[AlanOnerisi]:
    """Tek konturu öneriye çevirir; elenirse boş liste (tek eleme yeri)."""
    alan = cv2.contourArea(kontur)
    oran = alan / kare_alani
    if oran < _EN_KUCUK_ALAN_ORANI or oran > _EN_BUYUK_ALAN_ORANI:
        return []

    poligon = _poligonlastir(kontur)
    if poligon is None:
        return []

    normalize = _sinirla([(float(x) / genislik, float(y) / yukseklik) for x, y in poligon])
    if len(normalize) < 3:
        return []

    return [
        AlanOnerisi(
            poligon=normalize,
            tip=tip,
            tip_adi=tip_adi,
            guven=_guven(alan, kontur, kare_alani),
            aciklama=(
                f"Zeminde {maske_adi} boyayla işaretli bir alan bulundu. "
                "Köşeleri sürükleyerek düzeltebilirsiniz."
            ),
        )
    ]


def _yakin_parca_zarflari(maske: np.ndarray, genislik: int, yukseklik: int) -> list[np.ndarray]:
    """Birbirine yakın boya parçalarını kümeleyip her kümenin dışbükey zarfını verir.

    Yaya yolunu bulmanın yolu budur: iki paralel çizgi ayrı ayrı "çok ince"
    olduğu için elenir, ama ikisinin ORTAK zarfı tam olarak yolun kendisidir.

    Kümeleme, kutu-kutu boşluk mesafesine göre tek bağlantılıdır (single
    linkage): A ile B yakınsa ve B ile C yakınsa üçü tek kümedir. Uzun bir yol
    boyunca dizilmiş kesik çizgiler böylece tek alanda toplanır.
    """
    sayi, etiketler, kutular, _ = cv2.connectedComponentsWithStats(maske, connectivity=8)
    if sayi <= 1:
        return []

    # 0 numaralı bileşen arka plandır. Çok küçük lekeler kümeye alınmaz:
    # tek bir yansıma pikseli iki ayrı alanı yanlışlıkla birleştirebilirdi.
    en_kucuk_parca = max(int(genislik * yukseklik * 0.0004), 12)
    parcalar = [i for i in range(1, sayi) if kutular[i, cv2.CC_STAT_AREA] >= en_kucuk_parca]
    if len(parcalar) < _EN_AZ_GRUP_PARCASI:
        return []

    esik = min(genislik, yukseklik) * _GRUP_MESAFE_ORANI
    kumeler = _tek_baglantili_kumele(parcalar, kutular, esik)

    zarflar: list[np.ndarray] = []
    for kume in kumeler:
        if len(kume) < _EN_AZ_GRUP_PARCASI:
            continue
        noktalar = np.column_stack(np.where(np.isin(etiketler, list(kume))))
        if noktalar.size == 0:
            continue
        # np.where satır/sütun verir; OpenCV x/y ister — eksenler çevrilir.
        xy = noktalar[:, ::-1].astype(np.int32).reshape(-1, 1, 2)
        zarflar.append(cv2.convexHull(xy))
    return zarflar


def _tek_baglantili_kumele(parcalar: list[int], kutular, esik: float) -> list[set[int]]:
    """Kutuları boşluk mesafesine göre kümeler (tek bağlantılı)."""
    kumeler: list[set[int]] = []
    for parca in parcalar:
        komsular = [k for k in kumeler if any(_kutu_bosluk(kutular, parca, d) <= esik for d in k)]
        if not komsular:
            kumeler.append({parca})
            continue
        # Bu parça birden çok kümeye değiyorsa hepsi TEK kümede birleşir.
        birlesik = {parca}
        for kume in komsular:
            birlesik |= kume
            kumeler.remove(kume)
        kumeler.append(birlesik)
    return kumeler


def _kutu_bosluk(kutular, a: int, b: int) -> float:
    """İki sınırlayıcı kutu arasındaki en kısa boşluk (kesişiyorlarsa 0)."""
    ax, ay = kutular[a, cv2.CC_STAT_LEFT], kutular[a, cv2.CC_STAT_TOP]
    aw, ah = kutular[a, cv2.CC_STAT_WIDTH], kutular[a, cv2.CC_STAT_HEIGHT]
    bx, by = kutular[b, cv2.CC_STAT_LEFT], kutular[b, cv2.CC_STAT_TOP]
    bw, bh = kutular[b, cv2.CC_STAT_WIDTH], kutular[b, cv2.CC_STAT_HEIGHT]
    yatay = max(0, max(ax - (bx + bw), bx - (ax + aw)))
    dikey = max(0, max(ay - (by + bh), by - (ay + ah)))
    return float((yatay**2 + dikey**2) ** 0.5)


def _poligonlastir(kontur: np.ndarray) -> list[tuple[int, int]] | None:
    """Konturu az köşeli, elle düzeltilebilir bir poligona indirger."""
    cevre = cv2.arcLength(kontur, True)
    if cevre <= 0:
        return None
    yaklasik = cv2.approxPolyDP(kontur, _SADELESTIRME_ORANI * cevre, True)
    noktalar = [(int(n[0][0]), int(n[0][1])) for n in yaklasik]
    if len(noktalar) > _EN_COK_KOSE:
        # Hâlâ çok köşeli: dışbükey zarf hem sadeleştirir hem içbükey
        # tırtıkları siler. Kullanıcı için "biraz geniş" bir alan,
        # "düzeltilemeyecek kadar tırtıklı" bir alandan iyidir.
        zarf = cv2.convexHull(kontur)
        cevre_zarf = cv2.arcLength(zarf, True)
        yaklasik = cv2.approxPolyDP(zarf, _SADELESTIRME_ORANI * cevre_zarf, True)
        noktalar = [(int(n[0][0]), int(n[0][1])) for n in yaklasik]
    return noktalar if len(noktalar) >= 3 else None


def _sinirla(poligon: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Noktaları 0-1 aralığına kırpar (kaydetme doğrulaması bunu şart koşar)."""
    return [(min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)) for x, y in poligon]


def _guven(alan: float, kontur: np.ndarray, kare_alani: float) -> float:
    """0-1 arası kabaca "bu ne kadar alan gibi duruyor" ölçüsü.

    İki şeyin çarpımı:
      · DOLULUK — kontur, kendi dışbükey zarfının ne kadarını dolduruyor.
        Boyalı bir alan dolgundur; rastgele bir yansıma tırtıklı ve seyrektir.
      · BÜYÜKLÜK — çok küçük alanlar daha az güvenilir.
    """
    zarf_alani = cv2.contourArea(cv2.convexHull(kontur))
    doluluk = (alan / zarf_alani) if zarf_alani > 0 else 0.0
    buyukluk = min((alan / kare_alani) / 0.25, 1.0)  # %25 ve üstü tam puan
    return round(min(max(doluluk * 0.7 + buyukluk * 0.3, 0.0), 1.0), 2)


def _poligon_alani(poligon: list[tuple[float, float]]) -> float:
    """Ayakkabı bağı (shoelace) formülü — normalize alan, 0-1."""
    if len(poligon) < 3:
        return 0.0
    toplam = 0.0
    for i in range(len(poligon)):
        x1, y1 = poligon[i]
        x2, y2 = poligon[(i + 1) % len(poligon)]
        toplam += x1 * y2 - x2 * y1
    return abs(toplam) / 2.0


def _cakisanlari_ele(oneriler: list[AlanOnerisi]) -> list[AlanOnerisi]:
    """Aynı alanı iki kez öneren adayları eler (sarı ve beyaz maske çakışabilir).

    Ölçü: merkezleri birbirine, alanların karekökünün yarısından yakınsa aynı
    alan sayılır. Güveni yüksek olan kalır (liste zaten sıralı gelir).
    """
    kalanlar: list[AlanOnerisi] = []
    for aday in oneriler:
        aday_merkez = _merkez(aday.poligon)
        aday_olcek = _poligon_alani(aday.poligon) ** 0.5
        cakisti = False
        for tutulan in kalanlar:
            merkez = _merkez(tutulan.poligon)
            uzaklik = ((aday_merkez[0] - merkez[0]) ** 2 + (aday_merkez[1] - merkez[1]) ** 2) ** 0.5
            if uzaklik < max(aday_olcek, _poligon_alani(tutulan.poligon) ** 0.5) * 0.5:
                cakisti = True
                break
        if not cakisti:
            kalanlar.append(aday)
    return kalanlar


def _merkez(poligon: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(x for x, _ in poligon) / len(poligon),
        sum(y for _, y in poligon) / len(poligon),
    )

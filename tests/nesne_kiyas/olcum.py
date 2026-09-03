"""Kıyas takımını motora sorar ve ÜÇ SAYIYI çıkarır.

  isabet        → doğru nesne, doğru adıyla bulundu mu? (yüzde)
  yanlış isim   → başka bir nesnenin adı yazıldı mı? (adet — SIFIR OLMALI)
  eşleşme yok   → sistem "bilmiyorum" dedi mi? (adet)

Yanlış isim İKİYE ayrılır, çünkü ikisi ayrı kusurdur ve ayrı ayrı sıfır olmak
zorundadır:

  KÜTÜPHANE DIŞI → kütüphanede hiç olmayan bir şeye (yabancı nesne, düz
                   yabancı, boş/desensiz zemin) isim yazıldı. Kullanıcı orada
                   olmayan bir şeyin raporlandığını görür.
  KÜTÜPHANE İÇİ  → kütüphanedeki A nesnesine, kütüphanedeki B nesnesinin adı
                   yazıldı. Daha sinsidir: rapor doğru görünür, yanlış nesneyi
                   gösterir. "Gri pano A" bulanıklaşınca kardeşi "Gri pano B"
                   olur — bu, sahada yanlış panonun önüne gitmek demektir.

Ayrıca her sorgu için taranan pencerelerin ORB anahtar nokta sayısı da
kaydedilir. Sebebi: motorun en zayıf dalı ("iki taraf da desensiz", karar
yalnız renge kalır) ancak nokta sayısı `EN_AZ_ANAHTAR_NOKTA`nın altındayken
çalışır. Bu sayı ölçülmezse takımın o dalı gerçekten sınayıp sınamadığı
bilinemez — ilk takımın kör noktası tam olarak buydu.

Kaçırmak kötüdür ama YANLIŞ İSİM YAZMAK felakettir: docs/00-PROJE-BAGLAMI.md
"Kaçırılan ihlal ... sistemin bilinen sınırıdır. Buna karşılık yanlış alarm
ciddi bir kusurdur — çünkü güveni ve dolayısıyla kullanımı bitirir."

Ölçüm, motorun KENDİ karar yolunu kullanır; benzerlik formülüne ya da eşik
mantığına burada dokunulmaz. Tek kısayol şu: her sorgu bir kez taranır ve her
pencerenin skoru saklanır; eşik taraması bu kayıtların üzerinden yürür.

Bu kısayolun EŞİKTEN BAĞIMSIZ olması ayrıca gerekçelidir. Motorda bir aday
ancak DESEN payı çıtayı geçtiğinde isim yazdırabilir (`kutuphane.Skor`); desen
payı çıtayı geçmeyen aday, eşiğe oranlı bir tavana sıkıştırıldığı için HER
eşikte eşiğin ALTINDA kalır — ne işaret yazdırabilir ne de yazdırabilecek bir
adayı geçebilir. Yani bir pencerenin kazananı, eşik verildiği anda iki
eşikten-bağımsız sayıdan (ham skor, desen payı) hesaplanabilir. Kayıt bu iki
sayıyı saklar; sonuç her eşikte baştan taramakla birebir aynıdır —
tests/test_nesne_kiyas_kapisi.py bunu gerçek `arama.tara()` çıktısıyla
karşılaştırarak sınar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from app.nesneler import arama

# `_olcekle` ve `_tekle` motorun iç adımlarıdır; ölçüm onları BİLEREK yeniden
# yazmaz — yeniden yazsaydık, motor değişince ölçüm sessizce başka bir şeyi
# ölçmeye başlardı.
from app.nesneler.arama import Bulgu, _olcekle, _tekle
from app.nesneler.kutuphane import (
    EN_AZ_ANAHTAR_NOKTA,
    VARSAYILAN_ESIK,
    Nesne,
    Parmakizi,
    benzerlik,
    benzerlik_ayrintili,
    desen_izi,
    kabul_skoru,
    nokta_sayisi,
    parmakizi_cikar,
    renk_benzerligi,
    renk_izi,
    standart_boy,
)

from .takim import ZORLUK_ADLARI, Sorgu, Takim

# Eşik eğrisi: 0,10'dan 0,60'a 0,02 adımlarla. Alt uç 2026-09'da 0,20'den
# 0,10'a indirildi: "renk taşımaz" kuralı çıtaya ORANLI olduğu için çıta
# düştükçe desenden istenen pay da düşer, yani güvenli bölge artık aşağıya
# doğru da uzayabilir. Eski aralık o bölgeyi hiç göremiyordu.
ESIK_ARALIGI: tuple[float, ...] = tuple(round(0.10 + 0.02 * adim, 2) for adim in range(26))


@dataclass(frozen=True)
class AdayKaydi:
    """Bir pencerede bir nesnenin ham sonucu (eşikten bağımsız iki sayı)."""

    ham: float
    desen_payi: float
    nesne_adi: str


@dataclass(frozen=True)
class PencereKaydi:
    """Tek pencerenin, HER eşikte kazananını verebilen kaydı.

    Bütün adaylar saklanmaz; MERDİVEN saklanır: adaylar desen payına göre
    azalan sıraya konur ve yalnız ham skoru bir öncekini AŞANLAR tutulur.
    Bir eşik verildiğinde, "desen payı ≥ eşik" koşulunu sağlayan adaylar bu
    sıranın bir ÖN EKİdir; o ön ekteki en yüksek ham skor da merdivenin o ön
    ekteki son basamağıdır. Yani merdiven, bütün adayları saklamakla aynı
    cevabı verir — genelde 1-3 basamak uzunluğunda.
    """

    kutu: tuple[int, int, int, int]
    merdiven: tuple[AdayKaydi, ...]

    def kazanan(self, esik: float) -> AdayKaydi | None:
        """Motorun bu eşikte bu pencere için yazacağı isim (yoksa None)."""
        en_iyi = None
        for aday in self.merdiven:
            if aday.desen_payi < esik:
                break
            en_iyi = aday
        if en_iyi is None or en_iyi.ham < esik:
            return None
        return en_iyi


def _merdiven(adaylar: list[AdayKaydi]) -> tuple[AdayKaydi, ...]:
    """Adayları `PencereKaydi.merdiven` biçimine indirger."""
    basamaklar: list[AdayKaydi] = []
    en_yuksek_ham = 0.0
    for aday in sorted(adaylar, key=lambda a: a.desen_payi, reverse=True):
        if aday.ham > en_yuksek_ham:
            basamaklar.append(aday)
            en_yuksek_ham = aday.ham
    return tuple(basamaklar)


@dataclass
class SorguKaydi:
    """Bir sorgu fotoğrafının taranmış hali + teşhis için skorlar."""

    sorgu: Sorgu
    pencereler: list[PencereKaydi] = field(default_factory=list)
    dogru_en_yuksek: float = 0.0  # doğru nesnenin gördüğü en iyi skor
    yabanci_en_yuksek: float = 0.0  # yanlış adayların gördüğü en iyi skor
    # TEŞHİS: pencere nesneyi tam çerçeveleseydi skor ne olurdu? İkisi
    # arasındaki fark, kaybın ne kadarının "pencere ızgarası nesneyi kötü
    # çerçeveledi"den, ne kadarının "nesne gerçekten farklı görünüyor"dan
    # geldiğini söyler. Karara GİRMEZ.
    ideal_skor: float = 0.0
    # DESEN KANITI: desen (ORB) hesabına giren her pencerenin anahtar nokta
    # sayısı. Motorun en zayıf dalı ancak bu sayı `EN_AZ_ANAHTAR_NOKTA`nın
    # altındayken çalıştığı için, takımın o dalı gerçekten sınayıp sınamadığı
    # yalnız buradan görülür. Karara GİRMEZ; rapor ve kalite kapısı okur.
    nokta_sayilari: list[int] = field(default_factory=list)
    # Bütün karenin (küçültülmüş sahnenin tamamının) anahtar nokta sayısı.
    # "Bu sorgu genel olarak desenli mi?" sorusunun tek sayılık cevabı.
    tam_kare_nokta: int = 0

    @property
    def desensiz_pencere(self) -> int:
        """Kaç pencere motorun 'desensiz' saydığı kadar noktasızdı?"""
        return sum(1 for nokta in self.nokta_sayilari if nokta < EN_AZ_ANAHTAR_NOKTA)

    @property
    def desensiz_oran(self) -> float:
        if not self.nokta_sayilari:
            return 0.0
        return self.desensiz_pencere / len(self.nokta_sayilari)

    @property
    def orta_nokta(self) -> float:
        """Pencerelerin ORTANCA anahtar nokta sayısı (uçlardan etkilenmez)."""
        return float(np.median(self.nokta_sayilari)) if self.nokta_sayilari else 0.0

    def isabet(self, esik: float) -> tuple[bool, bool]:
        """(doğru ad yazıldı mı, yazılan işaret nesnenin ÜSTÜNDE mi)

        İkinci soru şart: düz renkli bir nesnenin adı, sahnenin bambaşka bir
        köşesindeki benzer renkli bir yamaya da yazılabilir. Ad doğru ama
        işaret yanlış yerde ise kullanıcı fotoğrafa bakınca sistemin bilmeden
        tutturduğunu görür. İki sayıyı ayrı ayrı bilmek gerekir.
        """
        dogru = self.sorgu.dogru_ad
        if dogru is None:
            return False, False
        bulundu = yerinde = False
        for bulgu in self.bulgular(esik):
            if bulgu.nesne_adi != dogru:
                continue
            bulundu = True
            yerinde = yerinde or _kapsiyor(bulgu.kutu, self.sorgu.kutu)
        return bulundu, yerinde

    def bulgular(self, esik: float) -> list[Bulgu]:
        """Motorun bu eşikte ekrana yazacağı işaretler."""
        gecenler = []
        for pencere in self.pencereler:
            kazanan = pencere.kazanan(esik)
            if kazanan is not None:
                gecenler.append((kazanan.ham, pencere.kutu, kazanan.nesne_adi))
        return _tekle(gecenler)


def _kapsiyor(bulgu_kutusu, nesne_kutusu) -> bool:
    """İşaret, nesnenin en az yarısını içine alıyor mu?"""
    if nesne_kutusu is None:
        return False
    x1 = max(bulgu_kutusu[0], nesne_kutusu[0])
    y1 = max(bulgu_kutusu[1], nesne_kutusu[1])
    x2 = min(bulgu_kutusu[2], nesne_kutusu[2])
    y2 = min(bulgu_kutusu[3], nesne_kutusu[3])
    kesisim = max(x2 - x1, 0) * max(y2 - y1, 0)
    nesne_alani = (nesne_kutusu[2] - nesne_kutusu[0]) * (nesne_kutusu[3] - nesne_kutusu[1])
    return nesne_alani > 0 and kesisim / nesne_alani >= 0.5


# --------------------------------------------------------------- tarama


def olc(
    takim: Takim,
    ilerleme: Callable[[int, int, SorguKaydi], None] | None = None,
    esik: float = VARSAYILAN_ESIK,
) -> list[SorguKaydi]:
    """Takımdaki her sorguyu tarar. Pahalı adım budur; bir kez çalışır.

    `esik` KARARA girmez (karar eşik taramasında verilir); yalnız teşhis
    skorlarının hangi çıtaya göre okunacağını söyler. Tek kanıtlı adayların
    skoru çıtaya oranlı olduğu için, kullanıcıya görünen sayı ("en yüksek
    benzerlik %X") ancak bir çıta belirtilerek yazılabilir.
    """
    kayitlar = []
    for sira, sorgu in enumerate(takim.sorgular, start=1):
        kayit = _sorguyu_tara(sorgu, takim.nesneler, esik)
        kayitlar.append(kayit)
        if ilerleme is not None:
            ilerleme(sira, len(takim.sorgular), kayit)
    return kayitlar


def _sorguyu_tara(sorgu: Sorgu, nesneler: list[Nesne], esik: float) -> SorguKaydi:
    gorsel = _olcekle(sorgu.gorsel)
    yuksek, genis = gorsel.shape[:2]
    referans_renkleri = [izi.renk for nesne in nesneler for izi in nesne.parmakizleri]

    # 1) UCUZ geçiş — motordaki renk elemesi. Ölçümde eleme tabanı 0'dır:
    #    böylece kayıt, taranan HER eşik için yeterli olur (yüksek eşikte motor
    #    daha az pencereye bakar, o pencereler de zaten bu kümenin içindedir).
    adaylar = []
    for kutu in arama.pencereler(genis, yuksek):
        x1, y1, x2, y2 = kutu
        kirpik = standart_boy(gorsel[y1:y2, x1:x2])
        renk = renk_izi(kirpik)
        en_iyi_renk = max((renk_benzerligi(renk, r) for r in referans_renkleri), default=0.0)
        adaylar.append((en_iyi_renk, kutu, kirpik, renk))
    adaylar.sort(key=lambda aday: aday[0], reverse=True)

    # 2) PAHALI geçiş — desen (ORB) ve karar
    kayit = SorguKaydi(
        sorgu=sorgu,
        ideal_skor=_ideal_cerceve_skoru(sorgu, nesneler, esik),
        tam_kare_nokta=_tam_kare_nokta(gorsel),
    )
    for _, kutu, kirpik, renk in adaylar[: arama.EN_COK_DESEN]:
        izi = Parmakizi(renk=renk, desen=desen_izi(kirpik))
        kayit.nokta_sayilari.append(nokta_sayisi(izi))
        merdiven, nesne_basina = _pencere_karari(izi, nesneler, esik)
        if merdiven:
            kayit.pencereler.append(PencereKaydi(kutu=kutu, merdiven=merdiven))
        for ad, nesne_skoru in nesne_basina.items():
            if ad == sorgu.dogru_ad:
                kayit.dogru_en_yuksek = max(kayit.dogru_en_yuksek, nesne_skoru)
            else:
                kayit.yabanci_en_yuksek = max(kayit.yabanci_en_yuksek, nesne_skoru)
    return kayit


def _tam_kare_nokta(gorsel: np.ndarray) -> int:
    """Sahnenin TAMAMININ anahtar nokta sayısı — 'bu fotoğraf desenli mi?'"""
    kirpik = standart_boy(gorsel)
    return nokta_sayisi(Parmakizi(renk=renk_izi(kirpik), desen=desen_izi(kirpik)))


def _ideal_cerceve_skoru(sorgu: Sorgu, nesneler: list[Nesne], esik: float) -> float:
    """Nesnenin gerçek kutusu %12,5 payla çerçevelenseydi alınacak skor."""
    if sorgu.kutu is None or sorgu.dogru_ad is None:
        return 0.0
    dogru = next((nesne for nesne in nesneler if nesne.ad == sorgu.dogru_ad), None)
    if dogru is None:
        return 0.0
    yuksek, genis = sorgu.gorsel.shape[:2]
    x1, y1, x2, y2 = sorgu.kutu
    pay = int((x2 - x1) * 0.125)
    pay = min(pay, x1, y1, genis - x2, yuksek - y2)  # kare kalsın, taşmasın
    izi = parmakizi_cikar(sorgu.gorsel[y1 - pay : y2 + pay, x1 - pay : x2 + pay])
    if izi is None:
        return 0.0
    return max((benzerlik(izi, referans, esik) for referans in dogru.parmakizleri), default=0.0)


def _pencere_karari(
    izi: Parmakizi, nesneler: list[Nesne], esik: float
) -> tuple[tuple[AdayKaydi, ...], dict[str, float]]:
    """Pencerenin eşikten bağımsız MERDİVENİ + nesne başına en iyi skor.

    Motorun `en_iyi_eslesme_izinden` kararı merdivenden yeniden kurulur
    (`PencereKaydi.kazanan`); burada karar VERİLMEZ, kararın malzemesi
    toplanır. Nesne başına saklanan skorlar ise teşhis içindir ve `esik`e göre
    okunur — kullanıcıya görünen sayı odur (`kabul_skoru`).
    """
    adaylar: list[AdayKaydi] = []
    nesne_basina: dict[str, float] = {}
    for nesne in nesneler:
        nesne_en_iyi = 0.0
        for referans in nesne.parmakizleri:
            ham = benzerlik_ayrintili(izi, referans)
            nesne_en_iyi = max(nesne_en_iyi, kabul_skoru(ham, esik))
            adaylar.append(AdayKaydi(ham.ham, ham.desen_payi, nesne.ad))
        nesne_basina[nesne.ad] = nesne_en_iyi
    return _merdiven(adaylar), nesne_basina


# ---------------------------------------------------------------- sayılar


@dataclass(frozen=True)
class EsikOzeti:
    esik: float
    pozitif: int
    isabet: int
    yerinde: int
    yanlis_isimli_sorgu: int
    yanlis_isimli_bulgu: int
    eslesme_yok: int
    negatif: int
    # Kütüphanede OLMAYAN bir şeye yazılan isimler (yabancı nesne, düz yabancı,
    # boş/desensiz zemin). Eski adı `negatife_isim`di; iki türü ayırt etmek
    # gerekince açık adını aldı.
    kutuphane_disi_yanlis: int
    # Kütüphanedeki A nesnesine yazılan, kütüphanedeki B nesnesinin adı.
    kutuphane_ici_yanlis: int

    @property
    def isabet_yuzde(self) -> float:
        return 100.0 * self.isabet / self.pozitif if self.pozitif else 0.0

    @property
    def yerinde_yuzde(self) -> float:
        return 100.0 * self.yerinde / self.pozitif if self.pozitif else 0.0

    @property
    def guvenli(self) -> bool:
        """Hiç yanlış isim yazılmadı mı? Kırmızı çizgi budur.

        İki tür de sıfır olmalıdır; toplam sıfırsa ikisi de sıfırdır.
        """
        return self.yanlis_isimli_bulgu == 0


@dataclass(frozen=True)
class ZorlukOzeti:
    zorluk: str
    toplam: int
    isabet: int
    yerinde: int
    yanlis_isim: int
    eslesme_yok: int
    ortalama_dogru_skor: float
    en_dusuk_dogru_skor: float
    ortalama_ideal_skor: float
    # Bu grubun tamamı negatif mi (doğru cevabı "eşleşme yok" olan sorgular)?
    # Öyleyse isabet sütunu anlamsızdır ve tabloda "—" basılır. Eskiden
    # zorluk adı "negatif"e eşit mi diye bakılıyordu; sertleştirmeyle birlikte
    # negatif grup sayısı üçe çıkınca ada değil, verinin kendisine bakılıyor.
    negatif: bool

    @property
    def isabet_yuzde(self) -> float:
        return 100.0 * self.isabet / self.toplam if self.toplam else 0.0

    @property
    def yerinde_yuzde(self) -> float:
        return 100.0 * self.yerinde / self.toplam if self.toplam else 0.0


def esik_ozeti(kayitlar: list[SorguKaydi], esik: float) -> EsikOzeti:
    pozitif = isabet = yerinde = yanlis_sorgu = yanlis_bulgu = eslesme_yok = 0
    negatif = disi = ici = 0
    for kayit in kayitlar:
        adlar = [bulgu.nesne_adi for bulgu in kayit.bulgular(esik)]
        yanlislar = [ad for ad in adlar if ad != kayit.sorgu.dogru_ad]
        if not adlar:
            eslesme_yok += 1
        if yanlislar:
            yanlis_sorgu += 1
            yanlis_bulgu += len(yanlislar)
        if kayit.sorgu.dogru_ad is None:
            negatif += 1
            disi += len(adlar)  # kütüphanede olmayan bir şeye yazılan her isim
        else:
            pozitif += 1
            ici += len(yanlislar)  # A nesnesine yazılan B adı
            bulundu, hedefte = kayit.isabet(esik)
            isabet += int(bulundu)
            yerinde += int(hedefte)
    return EsikOzeti(
        esik=esik,
        pozitif=pozitif,
        isabet=isabet,
        yerinde=yerinde,
        yanlis_isimli_sorgu=yanlis_sorgu,
        yanlis_isimli_bulgu=yanlis_bulgu,
        eslesme_yok=eslesme_yok,
        negatif=negatif,
        kutuphane_disi_yanlis=disi,
        kutuphane_ici_yanlis=ici,
    )


def esik_taramasi(kayitlar: list[SorguKaydi], esikler=ESIK_ARALIGI) -> list[EsikOzeti]:
    return [esik_ozeti(kayitlar, esik) for esik in esikler]


def en_iyi_guvenli_esik(ozetler: list[EsikOzeti]) -> EsikOzeti | None:
    """Yanlış isim SIFIR kalırken en yüksek isabeti veren eşik.

    Eşitlik olursa daha YÜKSEK eşik seçilir: aynı isabeti veriyorsa temkinli
    olan tercih edilir.
    """
    guvenliler = [ozet for ozet in ozetler if ozet.guvenli]
    if not guvenliler:
        return None
    return max(guvenliler, key=lambda ozet: (ozet.isabet, ozet.esik))


def zorluk_kirilimi(kayitlar: list[SorguKaydi], esik: float) -> list[ZorlukOzeti]:
    """Sonucu nesne türüne göre böler: nerede kaybettiğimiz görünsün."""
    ozetler = []
    for zorluk in ZORLUK_ADLARI:
        grup = [kayit for kayit in kayitlar if kayit.sorgu.zorluk == zorluk]
        if not grup:
            continue
        isabet = yerinde = yanlis = eslesme_yok = 0
        dogru_skorlar, ideal_skorlar = [], []
        for kayit in grup:
            adlar = [bulgu.nesne_adi for bulgu in kayit.bulgular(esik)]
            if not adlar:
                eslesme_yok += 1
            if any(ad != kayit.sorgu.dogru_ad for ad in adlar):
                yanlis += 1
            ideal_skorlar.append(kayit.ideal_skor)
            if kayit.sorgu.dogru_ad is not None:
                bulundu, hedefte = kayit.isabet(esik)
                isabet += int(bulundu)
                yerinde += int(hedefte)
                dogru_skorlar.append(kayit.dogru_en_yuksek)
            else:
                dogru_skorlar.append(kayit.yabanci_en_yuksek)
        ozetler.append(
            ZorlukOzeti(
                negatif=all(kayit.sorgu.dogru_ad is None for kayit in grup),
                zorluk=zorluk,
                toplam=len(grup),
                isabet=isabet,
                yerinde=yerinde,
                yanlis_isim=yanlis,
                eslesme_yok=eslesme_yok,
                ortalama_dogru_skor=float(np.mean(dogru_skorlar)),
                en_dusuk_dogru_skor=float(np.min(dogru_skorlar)),
                ortalama_ideal_skor=float(np.mean(ideal_skorlar)),
            )
        )
    return ozetler


def kacirilanlar(kayitlar: list[SorguKaydi], esik: float) -> list[tuple[str, str, float]]:
    """Bulunamayan pozitif sorgular: (nesne, bozulma, doğru nesnenin en iyi skoru)."""
    kacan = []
    for kayit in kayitlar:
        if kayit.sorgu.dogru_ad is None:
            continue
        if not kayit.isabet(esik)[0]:
            kacan.append((kayit.sorgu.dogru_ad, kayit.sorgu.bozulma, kayit.dogru_en_yuksek))
    return sorted(kacan, key=lambda satir: satir[2], reverse=True)


@dataclass(frozen=True)
class YanlisIsim:
    """Yazılan tek bir yanlış isim — hangi türden olduğu belli."""

    sorulan: str | None  # None → kütüphanede olmayan bir şey soruldu
    yazilan: str
    zorluk: str
    bozulma: str
    skor: float
    isaret_nesnenin_ustunde: bool

    @property
    def kutuphane_ici(self) -> bool:
        """A nesnesine B'nin adı mı yazıldı? (kütüphane İÇİ yanlış isim)"""
        return self.sorulan is not None

    @property
    def sorulan_metni(self) -> str:
        return self.sorulan or "kütüphanede yok"


def yanlis_isimler(kayitlar: list[SorguKaydi], esik: float) -> list[YanlisIsim]:
    """Yazılan yanlış isimlerin tamamı, skoru yüksekten alçağa."""
    hatalar = []
    for kayit in kayitlar:
        for bulgu in kayit.bulgular(esik):
            if bulgu.nesne_adi == kayit.sorgu.dogru_ad:
                continue
            hatalar.append(
                YanlisIsim(
                    sorulan=kayit.sorgu.dogru_ad,
                    yazilan=bulgu.nesne_adi,
                    zorluk=kayit.sorgu.zorluk,
                    bozulma=kayit.sorgu.bozulma,
                    skor=bulgu.skor,
                    isaret_nesnenin_ustunde=_isaret_nesnede(bulgu.kutu, kayit.sorgu.kutu),
                )
            )
    return sorted(hatalar, key=lambda hata: hata.skor, reverse=True)


def _isaret_nesnede(bulgu_kutusu, nesne_kutusu) -> bool:
    """İşaretin ALTINDA nesnenin kendisi mi var, yoksa boş zemin mi?

    `_kapsiyor`dan farklı bir soru sorar ve bilerek başka bir orana bakar.
    `_kapsiyor` "işaret nesnenin yarısını içine alıyor mu" der; bu, doğru
    bulguları ölçmek için doğrudur ama küçük bir pencere bunu hiçbir zaman
    başaramaz. Yanlış bir isimde sorulacak soru tersidir: "bu KÜÇÜK kutunun
    içi nesne mi?" — yani kesişim, NESNENİN değil PENCERENİN alanına oranlanır.
    Yanlış ismin nesnenin üstüne mi yoksa zemine mi düştüğünü ancak böyle
    ayırt edebiliriz; ikisi ayrı kusurdur (biri "yabancı nesneyi tanıdı
    sandı", öteki "bomboş zemine ad yazdı").
    """
    if nesne_kutusu is None:
        return False
    x1 = max(bulgu_kutusu[0], nesne_kutusu[0])
    y1 = max(bulgu_kutusu[1], nesne_kutusu[1])
    x2 = min(bulgu_kutusu[2], nesne_kutusu[2])
    y2 = min(bulgu_kutusu[3], nesne_kutusu[3])
    kesisim = max(x2 - x1, 0) * max(y2 - y1, 0)
    pencere_alani = (bulgu_kutusu[2] - bulgu_kutusu[0]) * (bulgu_kutusu[3] - bulgu_kutusu[1])
    return pencere_alani > 0 and kesisim / pencere_alani >= 0.5


def zorluk_tavani(kayitlar: list[SorguKaydi], zorluk: str) -> float:
    """Bir zorluk grubunda YANLIŞ adayın çıkabildiği en yüksek skor.

    Eşikten bağımsızdır: yanlış isim henüz yazılmıyorken bile çıtaya ne kadar
    yaklaşıldığını söyler. Kalite kapısının erken uyarısı budur.
    """
    grup = [kayit for kayit in kayitlar if kayit.sorgu.zorluk == zorluk]
    return max((kayit.yabanci_en_yuksek for kayit in grup), default=0.0)


def desensiz_kaniti(
    kayitlar: list[SorguKaydi], zorluk: str
) -> list[tuple[str, int, int, int, float]]:
    """DESEN KANITI: (bozulma, tam kare ORB, desensiz pencere, pencere, ortanca).

    Bir sorgu ailesinin motorun düz-düz dalına GERÇEKTEN girip girmediğini
    gösterir. Girmiyorsa o aile hiçbir şey ölçmüyordur — takımın eski kör
    noktası buydu ve bir daha sessizce geri gelmesin diye ölçülüp basılır.
    """
    return [
        (
            kayit.sorgu.bozulma,
            kayit.tam_kare_nokta,
            kayit.desensiz_pencere,
            len(kayit.nokta_sayilari),
            kayit.orta_nokta,
        )
        for kayit in kayitlar
        if kayit.sorgu.zorluk == zorluk
    ]

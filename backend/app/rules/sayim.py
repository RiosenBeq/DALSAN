"""Bölge sayımı — kaç nesne var, kaç tanesi girdi (CLAUDE.md §6: SAF).

Bu modül kural DEĞİLDİR: ihlal üretmez, anons tetiklemez, olay yazmaz.
Yalnızca "şu anda bölgede kaç kişi var" ve "vardiya başından beri kaç kişi
girdi" sorularını cevaplar. Ayrı tutulmasının nedeni budur — sayım yanlışsa
kimse uyarı almaz, yalnızca bir sayı yanlış görünür.

ÜÇ SAYI ÜRETİLİR, ÜÇÜ DE FARKLI SORUYU CEVAPLAR:

  anlik  — şu anda bölgede olan nesne sayısı ("içeride 3 kişi var")
  giren  — sayaç sıfırlandığından beri bölgeye giren AYRI nesne sayısı
           ("bu vardiyada 47 kişi girdi")
  zirve  — anlık sayının gördüğü en yüksek değer ("aynı anda en çok 7 kişi")

`giren` TAKİP BAZLIDIR: aynı kişi bölgede on dakika dursa da bir kez sayılır.
Kare bazlı sayım (her karede içeridekileri toplamak) saniyede altı kare işleyen
bir sistemde on dakikada 3600 "kişi" üretirdi.

NEDEN GECİKMELİ SAYIM (`min_kare`): tespit kutusu bölge sınırında titrer.
Toleranssız sayaç, sınırda duran tek bir kişiyi girip çıkıyor sanıp onlarca
kez sayardı. Bir nesne, sayılmadan önce ART ARDA `min_kare` değerlendirmede
bölgede görülmelidir.

NEDEN KAYIP TOLERANSI (`_KAYIP_TOLERANSI`): tozlu fabrika sahnesinde tek
karelik tespit kaçağı olağandır. Kaçak anında "çıktı" sayılırsa aynı kişi
tekrar tekrar girmiş görünür — `bolge_ihlali.py` ile aynı gerekçe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.rules.geometri import nokta_poligonda
from app.rules.tipler import Bolge, Tespit

# Bir takip bu kadar ardışık değerlendirme boyunca görülmezse "bölgeden çıktı"
# sayılır. bolge_ihlali.py'deki toleransla aynı büyüklükte tutuldu: iki modül
# aynı sahneye bakıp farklı zamanlarda "çıktı" derse ekrandaki iki sayı
# birbirini tutmaz ve kullanıcı hangisine güveneceğini bilemez.
_KAYIP_TOLERANSI = 5

# Sayılmış takiplerin kimlikleri sonsuza kadar tutulamaz (7x24 çalışma).
# Bu sayıya ulaşılınca en eskiler atılır. 20.000 takip, altı kare/sn ile
# çalışan tek kamerada günlerce yetiyor; bellekte ~1 MB'ın altında kalır.
_EN_COK_SAYILAN_KIMLIK = 20_000


@dataclass
class BolgeSayimi:
    """Tek bir bölgenin o andaki sayım tablosu.

    Sözlükler sınıf adına göredir: {"person": 3, "truck": 1}. Sıfır olan
    sınıflar YAZILMAZ — ekranda "forklift: 0" satırı, o bölgede hiç forklift
    beklenmediği durumda yalnızca gürültüdür.
    """

    bolge_id: int
    anlik: dict[str, int] = field(default_factory=dict)
    giren: dict[str, int] = field(default_factory=dict)
    zirve: dict[str, int] = field(default_factory=dict)

    @property
    def anlik_toplam(self) -> int:
        return sum(self.anlik.values())

    @property
    def giren_toplam(self) -> int:
        return sum(self.giren.values())


class BolgeSayaci:
    """Bir kameranın bölge sayaçları. Kare kare beslenir, durum içeride tutulur.

    Zamanı çağıran verir (kural motorundaki gibi): testte zaman ileri sarılır,
    gerçek saat beklenmez.
    """

    def __init__(self, min_kare: int = 3) -> None:
        # Sayılmadan önce art arda kaç değerlendirmede bölgede görülmeli
        self._min_kare = max(1, int(min_kare))
        # bolge_id -> takip_id -> ardışık görülme sayısı
        self._icerideki: dict[int, dict[int, int]] = {}
        # bolge_id -> takip_id -> ardışık görülmeme sayısı
        self._kayip: dict[int, dict[int, int]] = {}
        # bolge_id -> daha önce sayılmış takip kimlikleri (ekleme sıralı)
        self._sayilanlar: dict[int, dict[int, None]] = {}
        # bolge_id -> sinif -> toplam giren
        self._giren: dict[int, dict[str, int]] = {}
        # bolge_id -> sinif -> görülen en yüksek anlık değer
        self._zirve: dict[int, dict[str, int]] = {}

    # ---- ana giriş ----

    def guncelle(
        self,
        kare_boyutu: tuple[float, float],
        tespitler: list[Tespit],
        bolgeler: list[Bolge],
    ) -> list[BolgeSayimi]:
        """Bir kareyi işler ve TÜM aktif bölgelerin sayım tablosunu döndürür.

        Pasif (aktif=False) bölge sayılmaz ve sonuçta görünmez: sistem onu
        değerlendirmiyorsa ekranda da sayısı durmamalıdır.
        """
        aktifler = [b for b in bolgeler if b.aktif]
        self._olmayan_bolgeleri_unut({b.id for b in aktifler})

        sonuc: list[BolgeSayimi] = []
        for bolge in aktifler:
            sonuc.append(self._bolgeyi_say(bolge, tespitler, kare_boyutu))
        return sonuc

    def kare_sayimi(self, tespitler: list[Tespit]) -> dict[str, int]:
        """Bölgeden bağımsız, TÜM karedeki nesne sayısı: {"person": 4}.

        Bölge çizilmemiş bir kamerada da bir şey göstermek gerekir; kullanıcı
        önce "sistem bir şey görüyor mu" sorusunun cevabını arar.
        """
        sayim: dict[str, int] = {}
        for tespit in tespitler:
            sayim[tespit.sinif] = sayim.get(tespit.sinif, 0) + 1
        return sayim

    def sifirla(self, bolge_id: int | None = None) -> None:
        """Kümülatif sayaçları sıfırlar (vardiya başı / "Sayacı sıfırla" düğmesi).

        ANLIK sayı sıfırlanmaz — o, o anda görülen gerçektir; sıfırlanacak olan
        "kaç tane girdi" geçmişidir. bolge_id verilmezse tüm bölgeler sıfırlanır.
        """
        if bolge_id is None:
            self._sayilanlar.clear()
            self._giren.clear()
            self._zirve.clear()
            return
        self._sayilanlar.pop(bolge_id, None)
        self._giren.pop(bolge_id, None)
        self._zirve.pop(bolge_id, None)

    # ---- iç ----

    def _bolgeyi_say(
        self, bolge: Bolge, tespitler: list[Tespit], kare_boyutu: tuple[float, float]
    ) -> BolgeSayimi:
        icerideki = self._icerideki.setdefault(bolge.id, {})
        kayip = self._kayip.setdefault(bolge.id, {})
        sayilanlar = self._sayilanlar.setdefault(bolge.id, {})
        giren = self._giren.setdefault(bolge.id, {})
        zirve = self._zirve.setdefault(bolge.id, {})

        anlik: dict[str, int] = {}
        bu_karede_gorulen: set[int] = set()

        for tespit in tespitler:
            ayak = tespit.ayak_noktasi()
            ayak_norm = (ayak[0] / kare_boyutu[0], ayak[1] / kare_boyutu[1])
            if not nokta_poligonda(ayak_norm, bolge.poligon):
                # Bölge DIŞINDA gerçekten görüldü → anında çıkmış say.
                # (Kayıp toleransı yalnızca HİÇ görülmeyen takipler içindir.)
                icerideki.pop(tespit.takip_id, None)
                kayip.pop(tespit.takip_id, None)
                continue

            bu_karede_gorulen.add(tespit.takip_id)
            kayip.pop(tespit.takip_id, None)
            ardisik = icerideki.get(tespit.takip_id, 0) + 1
            icerideki[tespit.takip_id] = ardisik

            if ardisik < self._min_kare:
                continue  # henüz kararlı değil: ne anlık sayılır ne giren

            anlik[tespit.sinif] = anlik.get(tespit.sinif, 0) + 1
            if tespit.takip_id not in sayilanlar:
                sayilanlar[tespit.takip_id] = None
                giren[tespit.sinif] = giren.get(tespit.sinif, 0) + 1

        self._kayiplari_isle(icerideki, kayip, bu_karede_gorulen)
        self._kimlikleri_kirp(sayilanlar)

        for sinif, adet in anlik.items():
            if adet > zirve.get(sinif, 0):
                zirve[sinif] = adet

        return BolgeSayimi(
            bolge_id=bolge.id,
            anlik=dict(anlik),
            giren=dict(giren),
            zirve=dict(zirve),
        )

    @staticmethod
    def _kayiplari_isle(
        icerideki: dict[int, int], kayip: dict[int, int], gorulen: set[int]
    ) -> None:
        """Bu karede hiç tespit edilemeyen takipler: kısa kaçak tolere edilir."""
        for takip_id in list(icerideki):
            if takip_id in gorulen:
                continue
            kayip[takip_id] = kayip.get(takip_id, 0) + 1
            if kayip[takip_id] > _KAYIP_TOLERANSI:
                del icerideki[takip_id]
                del kayip[takip_id]

    @staticmethod
    def _kimlikleri_kirp(sayilanlar: dict[int, None]) -> None:
        """Sayılmış kimlik listesi sınırsız büyümesin (7x24 çalışma).

        En eski kimlikler atılır. Bunun tek görünür sonucu şudur: günler önce
        sayılmış bir takip kimliği yeniden ortaya çıkarsa ikinci kez sayılır.
        ByteTrack kimlikleri artan verdiği için bu pratikte olmaz; olsa da
        bedeli, belleğin sınırsız büyümesinden küçüktür.
        """
        fazla = len(sayilanlar) - _EN_COK_SAYILAN_KIMLIK
        if fazla <= 0:
            return
        for takip_id in list(sayilanlar)[:fazla]:
            del sayilanlar[takip_id]

    def _olmayan_bolgeleri_unut(self, mevcut: set[int]) -> None:
        """Silinen/pasifleşen bölgenin durumu bellekte kalmasın."""
        for depo in (self._icerideki, self._kayip, self._sayilanlar, self._giren, self._zirve):
            for bolge_id in [b for b in depo if b not in mevcut]:
                del depo[bolge_id]

"""Olay yaşam döngüsü (docs/17 §6.3) - saf; zamanı çağıran verir.

Değerlendiriciler bugünkü gibi `list[Ihlal]` üretir ve tekrar bastırmayı
(cooldown) kendileri uygular; bu makine o ihlalleri OLAYA çevirir:

- **açıldı:** anahtarı açık olmayan bir ihlal → yeni olay satırı, anons.
- **hatırlatma:** anahtar açıkken yeniden gelen ihlal (kuralın bekleme süresi
  doldu) → yeni satır AÇILMAZ, yalnız anons tekrarlanır (docs/17 S17). Uzun
  süren bir ihlal olay listesini artık her `cooldown_s`'de bir satırla doldurmaz.
- **kapandı:** anahtar `bitis_s` boyunca değerlendiricinin AKTİF kümesinde
  görünmedi → olayın bitişi yazılır. Bitiş, koşulun SON GÖRÜLDÜĞÜ andır;
  kapandığının fark edildiği an değil - bekleme süresi olayın süresine eklenmez.

Aktif küme, değerlendiricinin ÇIKIŞ eşiğidir (girişten gevşek olabilir): bölge
ihlalinde kişi bölgede ya da iz kayıp toleransı içinde; mesafede çift yakın;
KKD'de oy "yok"; hızda ortanca sınırın üstünde. Bu yüzden sınırda gidip gelen
kişi ya da bir an görünmeyen iz, `bitis_s` kısa boşlukları kapattığı için TEK
olay kalır.

Kapandıktan sonra aynı anahtar ancak değerlendirici yeniden ihlal ürettiğinde
açılır; o da kuralın bekleme süresine tabidir (cooldown zaten orada).

Anahtar, cooldown anahtarıyla aynı biçimdedir: (kural, kamera, iz) ya da
mesafede (kural, kamera, küçük iz, büyük iz); KKD'de sona kalem eklenir
(kural, kamera, iz, "helmet") - baret ve yelek ayrı olaydır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.rules.tipler import Ihlal

ACILDI = "acildi"
HATIRLATMA = "hatirlatma"
KAPANDI = "kapandi"

# `bitis_s` bilinmeyen kural için (kural bu turda kaldırıldıysa): parametre
# şemasının varsayılanıyla aynıdır (rules/parametreler.py).
VARSAYILAN_BITIS_S = 3.0


@dataclass
class OlayGecisi:
    asama: str  # ACILDI | HATIRLATMA | KAPANDI
    anahtar: tuple
    ihlal: Ihlal | None  # açılış ve hatırlatmada ihlalin kendisi
    # Yalnız kapanışta: neden bitti (olay_kodu.KAPANIS_SEBEPLERI) ve koşulun
    # son görüldüğü an (değerlendirme saatiyle, saniye).
    sebep: str = ""
    son_aktif_s: float | None = None


def olay_anahtari(ihlal: Ihlal) -> tuple:
    """İhlalin anahtarı: cooldown anahtarıyla aynı biçim (iz sırası önemsiz)."""
    anahtar = (ihlal.kural_id, ihlal.kamera_id, *sorted(ihlal.takip_idler))
    return (*anahtar, ihlal.kalem) if ihlal.kalem else anahtar


@dataclass
class _AcikOlay:
    son_aktif_s: float
    # Aktiflikten düştüğü İLK karedeki sebep; yeniden aktif olunca silinir.
    pasif_sebep: str = ""


class OlayDurumMakinesi:
    """Bir kameranın açık olaylarını tutar."""

    def __init__(self) -> None:
        self._acik: dict[tuple, _AcikOlay] = {}

    def acik_anahtarlar(self) -> set[tuple]:
        return set(self._acik)

    def kurali_birak(self, kural_id: int) -> list[OlayGecisi]:
        """Kural değişti ya da kaldırıldı: açık olayları hemen kapanır.

        Değerlendirici yeniden kurulduğu için eski olayın koşulu artık
        izlenemez; olay koşulun son görüldüğü anda biter.
        """
        gecisler = []
        for anahtar in [a for a in self._acik if a[0] == kural_id]:
            olay = self._acik.pop(anahtar)
            gecisler.append(OlayGecisi(KAPANDI, anahtar, None, "kural_degisti", olay.son_aktif_s))
        return gecisler

    def hepsini_birak(self, sebep: str) -> list[OlayGecisi]:
        """Açık olayların hepsi kapanır (kamera koptu, hat yeniden kuruldu):
        koşul artık izlenemiyor; her olay son görüldüğü anda biter."""
        gecisler = [
            OlayGecisi(KAPANDI, anahtar, None, sebep, olay.son_aktif_s)
            for anahtar, olay in self._acik.items()
        ]
        self._acik.clear()
        return gecisler

    def guncelle(
        self,
        zaman_s: float,
        ihlaller: list[Ihlal],
        aktifler: set[tuple],
        bitis_sureleri: dict[int, float],
        belirsizler: set[tuple] | frozenset = frozenset(),
        gorulen_izler: Iterable[int] | None = None,
    ) -> list[OlayGecisi]:
        """Bir değerlendirmenin geçişleri.

        `bitis_sureleri`: kural id → `bitis_s`. `belirsizler`: kararı belirsize
        dönmüş anahtarlar (KKD; kapanış sebebi `belirsiz`). `gorulen_izler`:
        bu karede görülen takip id'leri; anahtarın izi aralarında yoksa sebep
        `iz_kayboldu` olur. Verilmezse iz kaybı ayırt edilmez.
        """
        gorulen = None if gorulen_izler is None else set(gorulen_izler)
        gecisler: list[OlayGecisi] = []
        for ihlal in ihlaller:
            anahtar = olay_anahtari(ihlal)
            olay = self._acik.get(anahtar)
            if olay is None:
                self._acik[anahtar] = _AcikOlay(son_aktif_s=zaman_s)
                gecisler.append(OlayGecisi(ACILDI, anahtar, ihlal))
            else:
                olay.son_aktif_s, olay.pasif_sebep = zaman_s, ""
                gecisler.append(OlayGecisi(HATIRLATMA, anahtar, ihlal))

        for anahtar, olay in list(self._acik.items()):
            if anahtar in aktifler:
                olay.son_aktif_s, olay.pasif_sebep = zaman_s, ""
                continue
            if olay.son_aktif_s == zaman_s:
                continue  # bu karede ihlal üretti: ihlal, aktifliğin kanıtıdır
            if not olay.pasif_sebep:
                olay.pasif_sebep = self._pasif_sebebi(anahtar, belirsizler, gorulen)
            bitis_s = bitis_sureleri.get(anahtar[0], VARSAYILAN_BITIS_S)
            if zaman_s - olay.son_aktif_s >= bitis_s:
                del self._acik[anahtar]
                gecisler.append(
                    OlayGecisi(KAPANDI, anahtar, None, olay.pasif_sebep, olay.son_aktif_s)
                )
        return gecisler

    @staticmethod
    def _pasif_sebebi(anahtar: tuple, belirsizler, gorulen: set[int] | None) -> str:
        if anahtar in belirsizler:
            return "belirsiz"
        # İzler anahtarın tam sayı kısmıdır; KKD kalemi ("helmet") iz değildir
        izler = {parca for parca in anahtar[2:] if isinstance(parca, int)}
        if gorulen is not None and not izler <= gorulen:
            return "iz_kayboldu"
        return "kosul_bitti"

"""Kural tipi 1 — zone_intrusion: Bölge ihlali (docs/03 §1).

Soru: Tanımlı sınıftan bir nesne, tanımlı bölgede (veya mode=outside ise
bölge DIŞINDA), tanımlı süreden uzun kaldı mı?

Karar noktası: kutunun alt-orta noktası (zemin teması).
"""

from __future__ import annotations

from app.rules.geometri import nokta_poligonda
from app.rules.parametreler import BolgeIhlaliParams
from app.rules.tipler import Ihlal, Kural

# Tespit edilemeyen (dedektörün o karede kaçırdığı) takip bu kadar ardışık
# değerlendirme boyunca tolere edilir: kalış süresi sayacı korunur. Tozlu
# fabrika sahnesinde tek karelik tespit kaçağı OLAĞANDIR; toleranssız sayaç
# her kaçakta sıfırlanır ve bölgede sürekli duran kişi hiç ihlal üretmezdi.
# Bölgeden ÇIKAN (tespit edilip dışarıda görülen) kişi yine anında sıfırlanır.
_KAYIP_TOLERANSI = 5


class BolgeIhlaliDegerlendirici:
    def __init__(self, kural: Kural) -> None:
        self.kural = kural
        self.params = BolgeIhlaliParams(**kural.params)
        self._giris_zamani: dict[int, float] = {}  # takip_id -> koşulun başladığı an
        self._kayip_sayaci: dict[int, int] = {}  # takip_id -> ardışık görülmeme

    def degerlendir(self, baglam) -> list[Ihlal]:
        bolge = baglam.bolgeler.get(self.kural.bolge_id)
        if bolge is None or not bolge.aktif:
            return []

        ihlaller: list[Ihlal] = []
        gorulenler: set[int] = set()

        for tespit in baglam.tespitler:
            if tespit.sinif not in self.kural.hedef_siniflar:
                continue
            gorulenler.add(tespit.takip_id)

            ayak = tespit.ayak_noktasi()
            ayak_norm = (ayak[0] / baglam.kare_boyutu[0], ayak[1] / baglam.kare_boyutu[1])
            icinde = nokta_poligonda(ayak_norm, bolge.poligon)
            kosul = icinde if self.params.mode == "inside" else not icinde

            if not kosul:
                # Koşulu bozan GERÇEK gözlem: kişi bölgeden çıktı → anında sıfırla
                self._giris_zamani.pop(tespit.takip_id, None)
                self._kayip_sayaci.pop(tespit.takip_id, None)
                continue

            baslangic = self._giris_zamani.setdefault(tespit.takip_id, baglam.zaman_s)
            kalis = baglam.zaman_s - baslangic
            if kalis < self.params.min_dwell_s:
                continue
            anahtar = (self.kural.id, self.kural.kamera_id, tespit.takip_id)
            if not baglam.cooldown.izinli_mi(anahtar, baglam.zaman_s, self.kural.cooldown_s):
                continue
            ihlaller.append(
                Ihlal(
                    kural_id=self.kural.id,
                    kamera_id=self.kural.kamera_id,
                    takip_idler=[tespit.takip_id],
                    bolge_id=bolge.id,
                    olculen=round(kalis, 1),
                    detaylar={
                        "sinif": tespit.sinif,
                        "kalis_s": round(kalis, 1),
                        "mode": self.params.mode,
                    },
                )
            )

        # Bu karede hiç tespit edilemeyen takipler: kısa kaçaklar tolere edilir,
        # uzun kayıpta süre sayacı düşer (kişi gitmiş demektir)
        for takip_id in list(self._giris_zamani):
            if takip_id in gorulenler:
                self._kayip_sayaci.pop(takip_id, None)
                continue
            self._kayip_sayaci[takip_id] = self._kayip_sayaci.get(takip_id, 0) + 1
            if self._kayip_sayaci[takip_id] > _KAYIP_TOLERANSI:
                del self._giris_zamani[takip_id]
                del self._kayip_sayaci[takip_id]
        return ihlaller

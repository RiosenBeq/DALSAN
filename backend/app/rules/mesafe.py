"""Kural tipi 2 — safe_distance: Güvenli mesafe (docs/03 §2).

Soru: İnsan ile forklift/tır arasındaki GERÇEK DÜNYA mesafesi eşiğin
altına düştü mü?

Kalibrasyon zorunluluğu: kamera kalibre edilmemişse bu kural ÇALIŞMAZ —
sessizce yaklaşık sonuç üretmez, açıkça pasif kalır. Kalibre edilmemiş
piksel mesafesi perspektifle kat kat değişir; üretilen sayı yanıltıcı olur.
"""

from __future__ import annotations

from app.rules.geometri import nokta_poligonda, oklid_mesafe
from app.rules.parametreler import MesafeParams
from app.rules.tipler import Ihlal, Kural, Tespit


class MesafeDegerlendirici:
    def __init__(self, kural: Kural) -> None:
        self.kural = kural
        self.params = MesafeParams(**kural.params)
        self._ardisik: dict[tuple[int, int], int] = {}  # (id_kucuk, id_buyuk) -> sayaç

    def degerlendir(self, baglam) -> list[Ihlal]:
        if baglam.kalibrasyon is None:
            return []  # kural pasif — arayüz 'kalibrasyon bekleniyor' gösterir

        ozneler = [t for t in baglam.tespitler if t.sinif in self.params.subject_classes]
        nesneler = [t for t in baglam.tespitler if t.sinif in self.params.object_classes]
        if not ozneler or not nesneler:
            self._ardisik.clear()
            return []

        bolge = baglam.bolgeler.get(self.kural.bolge_id) if self.kural.bolge_id else None

        ihlaller: list[Ihlal] = []
        aktif_ciftler: set[tuple[int, int]] = set()

        for ozne in ozneler:
            if bolge is not None and not self._bolgede(ozne, bolge, baglam):
                continue  # bölge verilmişse yalnızca bölgedeki insanlar korunur
            ozne_konum = baglam.dunya_konumlari.get(ozne.takip_id)
            if ozne_konum is None:
                continue
            for nesne in nesneler:
                nesne_konum = baglam.dunya_konumlari.get(nesne.takip_id)
                if nesne_konum is None:
                    continue
                mesafe_m = oklid_mesafe(ozne_konum, nesne_konum)
                cift = (
                    min(ozne.takip_id, nesne.takip_id),
                    max(ozne.takip_id, nesne.takip_id),
                )
                aktif_ciftler.add(cift)

                # Park halindeki aracın yanındaki şoför gerçek risk değildir —
                # yanlış alarmların büyük kısmını bu tek koşul keser (docs/03 §2)
                hareketli = (
                    not self.params.require_moving_vehicle
                    or (nesne.hiz_mps or 0.0) >= self.params.min_speed_mps
                )
                if mesafe_m < self.params.distance_m and hareketli:
                    self._ardisik[cift] = self._ardisik.get(cift, 0) + 1
                else:
                    self._ardisik.pop(cift, None)
                    continue

                if self._ardisik[cift] < self.params.min_frames:
                    continue
                anahtar = (self.kural.id, self.kural.kamera_id) + cift
                if not baglam.cooldown.izinli_mi(anahtar, baglam.zaman_s, self.kural.cooldown_s):
                    continue
                ihlaller.append(
                    Ihlal(
                        kural_id=self.kural.id,
                        kamera_id=self.kural.kamera_id,
                        takip_idler=[ozne.takip_id, nesne.takip_id],
                        bolge_id=self.kural.bolge_id,
                        olculen=round(mesafe_m, 2),
                        detaylar={
                            "mesafe_m": round(mesafe_m, 2),
                            "arac_sinifi": nesne.sinif,
                            "arac_hiz_mps": round(nesne.hiz_mps or 0.0, 2),
                        },
                    )
                )

        # Artık yan yana olmayan çiftlerin sayaçları sıfırlanır
        for cift in list(self._ardisik):
            if cift not in aktif_ciftler:
                del self._ardisik[cift]
        return ihlaller

    def _bolgede(self, tespit: Tespit, bolge, baglam) -> bool:
        ayak = tespit.ayak_noktasi()
        ayak_norm = (ayak[0] / baglam.kare_boyutu[0], ayak[1] / baglam.kare_boyutu[1])
        return nokta_poligonda(ayak_norm, bolge.poligon)

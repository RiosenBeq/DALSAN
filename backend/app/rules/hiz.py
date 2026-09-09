"""Kural tipi 4 — vehicle_speed: Araç hız sınırı (docs/03 §4).

Soru: Forklift (ya da tır) fabrika içindeki hız sınırını aştı mı?

NEDEN AYRI BİR KURAL: güvenli mesafe kuralı hızı yalnızca "araç hareket
halinde mi" sorusuna cevap vermek için kullanır. Yanında kimse olmadan hızlı
giden bir forklift, mesafe kuralına GÖRÜNMEZ; oysa fabrika içi kaza
istatistiklerinde hız tek başına bir risktir.

Kalibrasyon zorunluluğu: hız, ayak noktasının ZEMİNDEKİ yer değişiminden
hesaplanır (rules/motor.py). Kamera kalibre edilmemişse `Tespit.hiz_mps`
hiç üretilmez; kural sessizce yaklaşık sonuç uydurmaz, açıkça pasif kalır —
güvenli mesafe kuralıyla aynı davranış (docs/03 §2).

TEK KARE KARARI YOKTUR (CLAUDE.md §7). Kare başına hız ölçümü gürültülüdür:
tespit kutusunun bir karelik oynaması ayak noktasını santimetrelerce kaydırır
ve 0,2 saniyelik aralığa bölününce metre/saniyelik bir sıçrama gibi görünür.
Karar, aynı takibin son N ölçümünün ORTANCASINA bakılarak verilir. Ortanca
seçildi çünkü tek bir sıçrama ortalamayı yukarı çeker ama ortancayı
etkilemez — ve ekrana yazılan sayı da bu ortancadır, yani kullanıcı olay
kaydında sıçrama değeri değil aracın gerçek hızını görür.
"""

from __future__ import annotations

from statistics import median

from app.rules.geometri import nokta_poligonda
from app.rules.parametreler import HizParams
from app.rules.tipler import Ihlal, Kural, Tespit

# Saniyede metre → saatte kilometre. Ayarlar m/sn cinsindendir (Tespit.hiz_mps
# ile aynı birim), ama kullanıcı hız sınırını km/sa olarak düşünür; olay
# kaydına ikisi de yazılır.
MPS_KMH = 3.6

# Tespit edilemeyen (ya da bölgeden çıkan) takip bu kadar ardışık
# değerlendirme boyunca tolere edilir; sonra ölçüm penceresi atılır.
# Tozlu sahnede tek karelik tespit kaçağı olağandır ve pencereyi her
# kaçakta sıfırlamak, hiç ihlal üretmeyen bir kural demektir.
_KAYIP_TOLERANSI = 5


class HizDegerlendirici:
    def __init__(self, kural: Kural) -> None:
        self.kural = kural
        self.params = HizParams(**kural.params)
        self._olcumler: dict[int, list[float]] = {}  # takip_id -> son hız ölçümleri
        self._kayip_sayaci: dict[int, int] = {}

    def degerlendir(self, baglam) -> list[Ihlal]:
        if baglam.kalibrasyon is None:
            return []  # kural pasif — arayüz 'kalibrasyon bekleniyor' gösterir

        bolge = baglam.bolgeler.get(self.kural.bolge_id) if self.kural.bolge_id else None
        if self.kural.bolge_id is not None and (bolge is None or not bolge.aktif):
            return []  # bölgeye bağlı kural, bölge yoksa/kapalıysa çalışmaz

        ihlaller: list[Ihlal] = []
        gorulenler: set[int] = set()

        for tespit in baglam.tespitler:
            if tespit.sinif not in self.kural.hedef_siniflar:
                continue
            if bolge is not None and not self._bolgede(tespit, bolge, baglam):
                continue
            gorulenler.add(tespit.takip_id)

            if tespit.hiz_mps is None:
                # Araç görülüyor ama bu karede hız ÖLÇÜLEMEDİ (ilk kare, ya da
                # ayak noktası ufka düştü). Pencere korunur, ölçüm eklenmez.
                continue

            pencere = self._olcumler.setdefault(tespit.takip_id, [])
            pencere.append(tespit.hiz_mps)
            del pencere[: -self.params.window_size]
            if len(pencere) < self.params.window_size:
                continue  # pencere dolmadan karar verilmez

            hiz = median(pencere)
            if hiz < self.params.speed_limit_mps:
                continue
            anahtar = (self.kural.id, self.kural.kamera_id, tespit.takip_id)
            if not baglam.cooldown.izinli_mi(anahtar, baglam.zaman_s, self.kural.cooldown_s):
                continue
            ihlaller.append(
                Ihlal(
                    kural_id=self.kural.id,
                    kamera_id=self.kural.kamera_id,
                    takip_idler=[tespit.takip_id],
                    bolge_id=self.kural.bolge_id,
                    olculen=round(hiz, 2),
                    detaylar={
                        "hiz_mps": round(hiz, 2),
                        "hiz_kmh": round(hiz * MPS_KMH, 1),
                        "limit_mps": self.params.speed_limit_mps,
                        "limit_kmh": round(self.params.speed_limit_mps * MPS_KMH, 1),
                        "arac_sinifi": tespit.sinif,
                        "olcum_sayisi": len(pencere),
                    },
                )
            )

        for takip_id in list(self._olcumler):
            if takip_id in gorulenler:
                self._kayip_sayaci.pop(takip_id, None)
                continue
            self._kayip_sayaci[takip_id] = self._kayip_sayaci.get(takip_id, 0) + 1
            if self._kayip_sayaci[takip_id] > _KAYIP_TOLERANSI:
                del self._olcumler[takip_id]
                del self._kayip_sayaci[takip_id]
        return ihlaller

    def _bolgede(self, tespit: Tespit, bolge, baglam) -> bool:
        ayak = tespit.ayak_noktasi()
        ayak_norm = (ayak[0] / baglam.kare_boyutu[0], ayak[1] / baglam.kare_boyutu[1])
        return nokta_poligonda(ayak_norm, bolge.poligon)

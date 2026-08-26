"""Kural motoru — saf orkestrasyon (CLAUDE.md §6).

Girdi: tespitler + bölgeler + kalibrasyon + kurallar. Çıktı: list[Ihlal].
Zamanı çağıran verir (zaman_s, saniye cinsinden monoton sayaç) — testlerde
zaman ileri sarılabilir. Hız tahmini de burada yapılır: kalibrasyonlu
kamerada ayak noktasının zemindeki yer değişiminden (m/sn).

Yeni kural tipi ekleme prosedürü docs/03 §5'tedir: değerlendirici + şema +
buradaki kayıt (DEGERLENDIRICILER) + test. Başka dosyaya dokunulmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.rules.bolge_ihlali import BolgeIhlaliDegerlendirici
from app.rules.cooldown import Cooldown
from app.rules.geometri import oklid_mesafe
from app.rules.kalibrasyon import KalibrasyonHatasi, dunyaya_cevir
from app.rules.kkd import KkdDegerlendirici
from app.rules.mesafe import MesafeDegerlendirici
from app.rules.tipler import Bolge, Ihlal, Kalibrasyon, Kural, Tespit

DEGERLENDIRICILER = {
    "zone_intrusion": BolgeIhlaliDegerlendirici,
    "safe_distance": MesafeDegerlendirici,
    "ppe_violation": KkdDegerlendirici,
}

# Hız tahmini için iki ölçüm arasındaki geçerli süre aralığı (sn)
_HIZ_DT_EN_AZ = 0.05
_HIZ_DT_EN_COK = 5.0


@dataclass
class Baglam:
    """Değerlendiricilere geçen tek kare bağlamı."""

    zaman_s: float
    kare_boyutu: tuple[float, float]  # (genişlik, yükseklik) piksel
    tespitler: list[Tespit]
    bolgeler: dict[int, Bolge]
    kalibrasyon: Kalibrasyon | None
    cooldown: Cooldown
    dunya_konumlari: dict[int, tuple[float, float]] = field(default_factory=dict)


class KuralMotoru:
    """Bir kameranın kural durumunu tutar ve her karede değerlendirir."""

    def __init__(self, kamera_id: int) -> None:
        self.kamera_id = kamera_id
        self._cooldown = Cooldown()
        self._degerlendiriciler: list = []
        self._kural_imzasi: tuple = ()
        # takip_id -> (zaman_s, dünya_konumu) — hız tahmini için
        self._son_konumlar: dict[int, tuple[float, tuple[float, float]]] = {}

    def kurallari_yukle(self, kurallar: list[Kural]) -> None:
        """Kural listesi değiştiyse değerlendiricileri yeniden kurar.

        Değişiklik yoksa mevcut durum (kalış süreleri, KKD pencereleri)
        korunur — restart'sız config yayılımının gereği (docs/02 §5).
        """
        imza = tuple(
            (k.id, k.tip, k.bolge_id, tuple(sorted(k.params.items(), key=str)), k.cooldown_s)
            for k in sorted(kurallar, key=lambda k: k.id)
        )
        if imza == self._kural_imzasi:
            return
        self._kural_imzasi = imza
        self._degerlendiriciler = [
            DEGERLENDIRICILER[k.tip](k) for k in kurallar if k.tip in DEGERLENDIRICILER
        ]

    def degerlendir(
        self,
        zaman_s: float,
        kare_boyutu: tuple[float, float],
        tespitler: list[Tespit],
        bolgeler: list[Bolge],
        kalibrasyon: Kalibrasyon | None,
    ) -> list[Ihlal]:
        baglam = Baglam(
            zaman_s=zaman_s,
            kare_boyutu=kare_boyutu,
            tespitler=tespitler,
            bolgeler={b.id: b for b in bolgeler},
            kalibrasyon=kalibrasyon,
            cooldown=self._cooldown,
        )
        if kalibrasyon is not None:
            self._konum_ve_hiz_hesapla(baglam)

        ihlaller: list[Ihlal] = []
        for degerlendirici in self._degerlendiriciler:
            ihlaller.extend(degerlendirici.degerlendir(baglam))

        self._cooldown.temizle(zaman_s - 3600)
        return ihlaller

    def _konum_ve_hiz_hesapla(self, baglam: Baglam) -> None:
        for tespit in baglam.tespitler:
            ayak = tespit.ayak_noktasi()
            ayak_norm = (ayak[0] / baglam.kare_boyutu[0], ayak[1] / baglam.kare_boyutu[1])
            try:
                konum = dunyaya_cevir(baglam.kalibrasyon.homografi, ayak_norm)
            except KalibrasyonHatasi:
                continue  # ufuk çizgisine düşen nokta — bu tespit için konum yok
            baglam.dunya_konumlari[tespit.takip_id] = konum

            onceki = self._son_konumlar.get(tespit.takip_id)
            if onceki is not None:
                dt = baglam.zaman_s - onceki[0]
                if _HIZ_DT_EN_AZ <= dt <= _HIZ_DT_EN_COK:
                    tespit.hiz_mps = oklid_mesafe(konum, onceki[1]) / dt
            self._son_konumlar[tespit.takip_id] = (baglam.zaman_s, konum)

        # Eski konum kayıtlarını temizle
        esik = baglam.zaman_s - 60
        self._son_konumlar = {
            t: kayit for t, kayit in self._son_konumlar.items() if kayit[0] >= esik
        }

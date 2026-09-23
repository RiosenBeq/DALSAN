"""Kural motoru - saf orkestrasyon (CLAUDE.md §6).

Girdi: tespitler + bölgeler + kalibrasyon + kurallar. Çıktı: list[Ihlal].
Zamanı çağıran verir (zaman_s, saniye cinsinden monoton sayaç) - testlerde
zaman ileri sarılabilir. Hız tahmini de burada yapılır: kalibrasyonlu
kamerada ayak noktasının zemindeki yer değişiminden (m/sn).

Olay kodu ve önemi de burada, değerlendirmeden SONRA atanır (rules/olay_kodu.py):
değerlendiriciler kodu bilmez, kendi testleri kod yüzünden değişmez. Olay yaşam
döngüsü de öyle (rules/olay_durumu.py): `degerlendir()` bugünkü gibi ihlalleri
döndürür; açılış / hatırlatma / kapanış geçişleri `gecisleri_al()` ile alınır.

Yeni kural tipi ekleme prosedürü docs/03 §6'tedir: değerlendirici + şema +
buradaki kayıt (DEGERLENDIRICILER) + olay kodu (olay_kodu.ihlal_kodu) + test.
Başka dosyaya dokunulmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.rules.bolge_ihlali import BolgeIhlaliDegerlendirici
from app.rules.cooldown import Cooldown
from app.rules.geometri import nokta_poligonda, oklid_mesafe
from app.rules.hiz import HizDegerlendirici
from app.rules.kalibrasyon import KalibrasyonHatasi, dunyaya_cevir
from app.rules.kkd import KkdDegerlendirici
from app.rules.mesafe import MesafeDegerlendirici
from app.rules.olay_durumu import OlayDurumMakinesi, OlayGecisi
from app.rules.olay_kodu import ARAC_SINIFLARI, ihlal_kodu, olay_onemi
from app.rules.tipler import Bolge, Ihlal, Kalibrasyon, Kural, Tespit

DEGERLENDIRICILER = {
    "zone_intrusion": BolgeIhlaliDegerlendirici,
    "safe_distance": MesafeDegerlendirici,
    "ppe_violation": KkdDegerlendirici,
    "vehicle_speed": HizDegerlendirici,
}

# İzi kaybolan nesneyi bir süre bekleyen (kayıp toleransı olan) değerlendiriciler.
# Mesafe ve KKD değerlendiricileri her karede yeniden karar verir; beklemezler.
KAYIP_TOLERANSLI_TIPLER = frozenset({"zone_intrusion", "vehicle_speed"})

# Bu tiplerin değerlendiricisi, kalibrasyon yoksa BOŞ liste döndürür: ikisi de
# gerçek dünya (metre) ölçüsüne dayanır ve kalibrasyonsuz piksel ölçüsünden
# yaklaşık sonuç UYDURMAZ. Arayüz bunu "kalibrasyon bekleniyor" rozetiyle
# gösterir; liste burada durur ki ekranla motor birbirinden ayrı düşmesin.
KALIBRASYON_GEREKTIREN = frozenset({"safe_distance", "vehicle_speed"})

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

    def __init__(self, kamera_id: int, kayip_toleransi: int | None = None) -> None:
        self.kamera_id = kamera_id
        # Tespit edilemeyen izin kaç değerlendirme boyunca bekleneceği. Takip
        # hafızası uzarsa kural da izi o kadar beklemeli, yoksa kalış sayacı
        # yine sıfırlanır (docs/17 §6.3). rules/ .env OKUMAZ: değeri hat verir,
        # verilmezse değerlendiricilerin kendi varsayılanı (5) geçerlidir.
        self._kayip_toleransi = kayip_toleransi
        self._cooldown = Cooldown()
        self._durum = OlayDurumMakinesi()
        # Alınmamış geçişler: degerlendir() ve kurallari_yukle() ekler,
        # gecisleri_al() boşaltır.
        self._gecisler: list[OlayGecisi] = []
        self._degerlendiriciler: list = []
        self._kural_imzasi: tuple = ()
        self._en_uzun_cooldown: float = 0.0
        # takip_id -> (zaman_s, dünya_konumu) - hız tahmini için
        self._son_konumlar: dict[int, tuple[float, tuple[float, float]]] = {}

    def kurallari_yukle(self, kurallar: list[Kural]) -> None:
        """Kural listesi değiştiyse DEĞİŞEN kuralların değerlendiricilerini kurar.

        Değişmeyen kuralın durumu (kalış süreleri, KKD pencereleri, açık
        olayı) korunur - restart'sız config yayılımının gereği (docs/02 §5).
        Bir kuralı düzenlemek aynı kameradaki başka bir kuralın açık olayını
        bitirmemeli. İmza, davranışı etkileyen HER alanı içermelidir; eksik
        alan, değişikliğin restart'a kadar sessizce uygulanmaması demektir
        (önem olayın önemini belirler: rules/olay_kodu.olay_onemi).
        """
        imza = tuple(
            (
                k.id,
                k.tip,
                k.bolge_id,
                tuple(sorted(k.hedef_siniflar)),
                tuple(sorted(k.params.items(), key=str)),
                k.cooldown_s,
                k.siddet,
            )
            for k in sorted(kurallar, key=lambda k: k.id)
        )
        if imza == self._kural_imzasi:
            return
        # Tanımı değişen (veya id'si yeniden kullanılan) kuralların cooldown
        # geçmişi eskidir - yeni kural eskisinin bastırmasını miras almamalı.
        eski = dict(self._eski_imzalar(self._kural_imzasi))
        yeni = dict(self._eski_imzalar(imza))
        for kural_id, kural_imza in yeni.items():
            if eski.get(kural_id) != kural_imza:
                self._cooldown.kural_sifirla(kural_id)
        # Değişen ya da kaldırılan kuralın açık olayı biter: değerlendiricisi
        # yeniden kuruluyor, eski koşul artık izlenemez (sebep: kural_degisti).
        for kural_id, kural_imza in eski.items():
            if yeni.get(kural_id) != kural_imza:
                self._gecisler.extend(self._durum.kurali_birak(kural_id))
        self._kural_imzasi = imza
        onceki = {d.kural.id: d for d in self._degerlendiriciler}
        self._degerlendiriciler = [
            onceki[k.id] if eski.get(k.id) == yeni[k.id] and k.id in onceki else self._kur(k)
            for k in kurallar
            if k.tip in DEGERLENDIRICILER
        ]
        # Cooldown temizliği, en uzun kuralın cooldown'unu asla kırpmamalı
        self._en_uzun_cooldown = max([k.cooldown_s for k in kurallar], default=0.0)

    def kayip_toleransi_guncelle(self, kayip_toleransi: int | None) -> None:
        """Örnekleme hızı değişti (R34): kayıp toleransı yeni hızın karşılığına
        güncellenir; değerlendiricilerin durumu (kalış süreleri, açık olaylar,
        cooldown) korunur. None: değerlendiricilerin kendi varsayılanı kalır."""
        self._kayip_toleransi = kayip_toleransi
        if kayip_toleransi is None:
            return
        for degerlendirici in self._degerlendiriciler:
            if degerlendirici.kural.tip in KAYIP_TOLERANSLI_TIPLER:
                degerlendirici.kayip_toleransi_guncelle(kayip_toleransi)

    def _kur(self, kural: Kural):
        sinif = DEGERLENDIRICILER[kural.tip]
        if self._kayip_toleransi is not None and kural.tip in KAYIP_TOLERANSLI_TIPLER:
            return sinif(kural, kayip_toleransi=self._kayip_toleransi)
        return sinif(kural)

    @staticmethod
    def _eski_imzalar(imza: tuple):
        return [(satir[0], satir) for satir in imza]

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
        aktifler: set[tuple] = set()
        belirsizler: set[tuple] = set()
        for degerlendirici in self._degerlendiriciler:
            for ihlal in degerlendirici.degerlendir(baglam):
                self._kodla(ihlal, degerlendirici.kural, baglam)
                ihlaller.append(ihlal)
            aktifler |= degerlendirici.aktif_anahtarlar()
            if hasattr(degerlendirici, "belirsiz_anahtarlar"):
                belirsizler |= degerlendirici.belirsiz_anahtarlar()
        self._gecisler.extend(
            self._durum.guncelle(
                zaman_s,
                ihlaller,
                aktifler,
                {d.kural.id: d.params.bitis_s for d in self._degerlendiriciler},
                belirsizler,
                (t.takip_id for t in tespitler),
            )
        )

        # Temizlik eşiği en uzun kuralın cooldown'unun gerisinde kalmalı;
        # aksi halde 1 saatten uzun cooldown'lar fiilen kırpılırdı.
        self._cooldown.temizle(zaman_s - max(3600.0, self._en_uzun_cooldown * 2))
        return ihlaller

    def olaylari_birak(self, sebep: str) -> list[OlayGecisi]:
        """Açık olayların hepsini kapatır ve geçişlerini döndürür (bkz.
        OlayDurumMakinesi.hepsini_birak). Değerlendirici durumu korunur."""
        return self._durum.hepsini_birak(sebep)

    def gecisleri_al(self) -> list[OlayGecisi]:
        """Son alıştan bu yana üretilen olay geçişleri (açıldı / hatırlatma /
        kapandı); alınan geçiş bir daha verilmez."""
        gecisler, self._gecisler = self._gecisler, []
        return gecisler

    @staticmethod
    def _kodla(ihlal: Ihlal, kural: Kural, baglam: Baglam) -> None:
        """İhlale olay kodunu ve önemini yazar (docs/17 §6.1-6.3)."""
        bolge = baglam.bolgeler.get(ihlal.bolge_id) if ihlal.bolge_id is not None else None
        bolge_tipi = bolge.tip if bolge is not None else None
        ihlal.kod = ihlal_kodu(kural.tip, ihlal.detaylar, bolge_tipi)
        if ihlal.kod == "ZONE_INTRUSION" and bolge_tipi:
            # Yedek kodda olayın NE olduğunu bölge tipi söyler (ekran ve rapor)
            ihlal.detaylar["bolge_tipi"] = bolge_tipi
        # Bağlamsal önem: araç yolundaki yaya, yolda o anda bir araç da varsa
        # daha ciddidir. Karar, ihlalin olduğu KAREDEKİ ayak noktalarıyla verilir.
        arac_var = (
            ihlal.kod == "PERSON_IN_VEHICLE_LANE"
            and bolge is not None
            and any(
                t.sinif in ARAC_SINIFLARI
                and nokta_poligonda(_normalize(t.ayak_noktasi(), baglam.kare_boyutu), bolge.poligon)
                for t in baglam.tespitler
            )
        )
        if arac_var:
            ihlal.detaylar["arac_ayni_bolgede"] = True
        ihlal.onem = olay_onemi(ihlal.kod, kural.siddet, arac_ayni_bolgede=arac_var)

    def _konum_ve_hiz_hesapla(self, baglam: Baglam) -> None:
        for tespit in baglam.tespitler:
            ayak = tespit.ayak_noktasi()
            ayak_norm = (ayak[0] / baglam.kare_boyutu[0], ayak[1] / baglam.kare_boyutu[1])
            try:
                konum = dunyaya_cevir(baglam.kalibrasyon.homografi, ayak_norm)
            except KalibrasyonHatasi:
                continue  # ufuk çizgisine düşen nokta - bu tespit için konum yok
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


def _normalize(nokta: tuple[float, float], kare_boyutu: tuple[float, float]) -> tuple[float, float]:
    return (nokta[0] / kare_boyutu[0], nokta[1] / kare_boyutu[1])

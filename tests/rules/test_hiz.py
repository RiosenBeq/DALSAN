"""vehicle_speed — araç hız sınırı kuralı (docs/03 §4).

Kamera YOK, model YOK: hız değerleri elle verilir. Sınanan sözler:
  · Kalibrasyonsuz kamerada kural PASİFTİR (uydurma sayı üretmez).
  · Karar TEK KAREYE değil ölçüm penceresinin ORTANCASINA bakar —
    tek karelik sıçrama ihlal üretmez (CLAUDE.md §7).
  · Olay kaydına yazılan sayı sıçrama değil ortancadır.
  · Bölge verilirse yalnız o bölgedeki araç değerlendirilir.
  · Cooldown aynı aracı üst üste bağırtmaz.
"""

from __future__ import annotations

from app.rules.cooldown import Cooldown
from app.rules.hiz import HizDegerlendirici
from app.rules.motor import Baglam
from tests.rules.yardimci import KALIBRASYON_10M, KARE, bolge, kural, tespit


def _baglam(tespitler, zaman_s=0.0, kalibrasyon=KALIBRASYON_10M, bolgeler=None, cooldown=None):
    return Baglam(
        zaman_s=zaman_s,
        kare_boyutu=KARE,
        tespitler=tespitler,
        bolgeler={b.id: b for b in (bolgeler or [])},
        kalibrasyon=kalibrasyon,
        cooldown=cooldown or Cooldown(),
    )


def _forklift(hiz, takip_id=1, ayak=(0.5, 0.5), sinif="forklift"):
    t = tespit(sinif=sinif, ayak=ayak, takip_id=takip_id)
    t.hiz_mps = hiz
    return t


def _hiz_kurali(params=None, bolge_id=None, cooldown_s=60.0):
    return kural(
        "vehicle_speed",
        bolge_id=bolge_id,
        hedefler=["forklift", "truck"],
        params=params or {},
        cooldown_s=cooldown_s,
    )


def _kareler(degerlendirici, hizlar, cooldown=None, **kw):
    """Verilen hızları sırayla besler, üretilen tüm ihlalleri döndürür."""
    cooldown = cooldown or Cooldown()
    ihlaller = []
    for sira, hiz in enumerate(hizlar):
        baglam = _baglam([_forklift(hiz)], zaman_s=sira * 0.2, cooldown=cooldown, **kw)
        ihlaller.extend(degerlendirici.degerlendir(baglam))
    return ihlaller


# ------------------------------------------------------- kalibrasyon şartı


def test_kalibrasyonsuz_kamerada_kural_pasif():
    """Hız zeminden ölçülür; kalibrasyon yoksa yaklaşık sonuç UYDURULMAZ."""
    d = HizDegerlendirici(_hiz_kurali())
    ihlaller = _kareler(d, [9.0] * 10, kalibrasyon=None)
    assert ihlaller == []


# --------------------------------------------------------- ortanca kararı


def test_sinir_asilinca_ihlal_uretilir():
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    ihlaller = _kareler(d, [3.0] * 5)
    assert len(ihlaller) == 1
    assert ihlaller[0].olculen == 3.0
    assert ihlaller[0].detaylar["arac_sinifi"] == "forklift"


def test_sinir_altinda_ihlal_yok():
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    assert _kareler(d, [2.0] * 10) == []


def test_pencere_dolmadan_karar_verilmez():
    """4 ölçüm sınırın üstünde olsa bile 5'lik pencere dolmadan uyarı yok."""
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    assert _kareler(d, [9.0] * 4) == []


def test_tek_karelik_sicrama_ihlal_uretmez():
    """Tespit kutusunun bir karelik oynaması hız sıçraması gibi görünür.
    Ortanca bunu yutar; ortalama alsaydık (0.5*4 + 20)/5 = 4,4 m/sn çıkar ve
    duran forklift hız cezası yerdi."""
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    assert _kareler(d, [0.5, 0.5, 20.0, 0.5, 0.5]) == []


def test_olay_kaydina_sicrama_degil_ortanca_yazilir():
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    ihlaller = _kareler(d, [3.0, 3.2, 30.0, 3.1, 3.0])
    assert len(ihlaller) == 1
    assert ihlaller[0].detaylar["hiz_mps"] == 3.1  # 30,0 değil
    assert ihlaller[0].olculen == 3.1


def test_kmh_karsiligi_da_yazilir():
    """Kullanıcı hız sınırını km/sa olarak düşünür; olay kaydı ikisini de taşır."""
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    detay = _kareler(d, [5.0] * 5)[0].detaylar
    assert detay["hiz_kmh"] == 18.0
    assert detay["limit_mps"] == 2.5
    assert detay["limit_kmh"] == 9.0


def test_hiz_olculemeyen_kare_pencereyi_bozmaz():
    """İlk karede ya da ufka düşen ayak noktasında hız None gelir; bu kare
    ölçüm sayılmaz ama biriken pencere de atılmaz."""
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    ihlaller = _kareler(d, [3.0, 3.0, None, 3.0, 3.0, 3.0])
    assert len(ihlaller) == 1


def test_yavaslayan_arac_artik_ihlal_uretmez():
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    cooldown = Cooldown()
    ilk = _kareler(d, [4.0] * 5, cooldown=cooldown)
    assert len(ilk) == 1
    # Pencere yavaş ölçümlerle dolunca ortanca sınırın altına iner
    sonra = _kareler(d, [0.4] * 5, cooldown=cooldown)
    assert sonra == []


# ---------------------------------------------------------------- kapsam


def test_hedef_disi_sinif_degerlendirilmez():
    """İnsan hedef sınıflarda değilse hızlı koşan biri hız cezası almaz."""
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    cooldown = Cooldown()
    ihlaller = []
    for sira in range(6):
        insan = _forklift(9.0, sinif="person")
        ihlaller.extend(d.degerlendir(_baglam([insan], sira * 0.2, cooldown=cooldown)))
    assert ihlaller == []


def test_bolge_verilirse_yalniz_bolgedeki_arac_sayilir():
    b = bolge(bolge_id=7, tip="vehicle_area")
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}, bolge_id=7))
    cooldown = Cooldown()
    ihlaller = []
    for sira in range(6):
        # (0.05, 0.05) bölgenin (0.25-0.75) DIŞINDA
        disarida = _forklift(9.0, ayak=(0.05, 0.05))
        ihlaller.extend(
            d.degerlendir(_baglam([disarida], sira * 0.2, bolgeler=[b], cooldown=cooldown))
        )
    assert ihlaller == []

    ihlaller = []
    for sira in range(6):
        icerde = _forklift(9.0, ayak=(0.5, 0.5))
        ihlaller.extend(
            d.degerlendir(_baglam([icerde], sira * 0.2, bolgeler=[b], cooldown=cooldown))
        )
    assert len(ihlaller) == 1
    assert ihlaller[0].bolge_id == 7


def test_bolge_kapaliysa_kural_calismaz():
    b = bolge(bolge_id=7, tip="vehicle_area")
    b.aktif = False
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}, bolge_id=7))
    ihlaller = []
    for sira in range(6):
        ihlaller.extend(d.degerlendir(_baglam([_forklift(9.0)], sira * 0.2, bolgeler=[b])))
    assert ihlaller == []


def test_bolgesiz_kural_tum_kareyi_kapsar():
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    cooldown = Cooldown()
    ihlaller = []
    for sira in range(5):
        kosede = _forklift(9.0, ayak=(0.02, 0.98))
        ihlaller.extend(d.degerlendir(_baglam([kosede], sira * 0.2, cooldown=cooldown)))
    assert len(ihlaller) == 1


# -------------------------------------------------------------- cooldown


def test_cooldown_ayni_araci_ust_uste_bagirtmaz():
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}, cooldown_s=60))
    ihlaller = _kareler(d, [4.0] * 20)
    assert len(ihlaller) == 1


def test_cooldown_dolunca_yeniden_uyarir():
    cooldown = Cooldown()
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}, cooldown_s=10))
    ihlaller = []
    for sira in range(60):  # 0,2 sn aralıkla 12 saniye
        baglam = _baglam([_forklift(4.0)], zaman_s=sira * 0.2, cooldown=cooldown)
        ihlaller.extend(d.degerlendir(baglam))
    assert len(ihlaller) == 2


def test_iki_arac_ayri_degerlendirilir():
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    cooldown = Cooldown()
    ihlaller = []
    for sira in range(5):
        hizli = _forklift(6.0, takip_id=1)
        yavas = _forklift(0.5, takip_id=2, ayak=(0.6, 0.6))
        ihlaller.extend(d.degerlendir(_baglam([hizli, yavas], sira * 0.2, cooldown=cooldown)))
    assert len(ihlaller) == 1
    assert ihlaller[0].takip_idler == [1]


def test_uzun_kayiptan_sonra_pencere_bastan_dolar():
    """Araç kareden çıkıp dönerse eski ölçümlerle karar verilmez."""
    d = HizDegerlendirici(_hiz_kurali({"speed_limit_mps": 2.5, "window_size": 5}))
    cooldown = Cooldown()
    # 4 hızlı ölçüm — pencere dolmadı
    for sira in range(4):
        d.degerlendir(_baglam([_forklift(9.0)], sira * 0.2, cooldown=cooldown))
    # Araç 6 kare boyunca yok (tolerans 5)
    for sira in range(4, 10):
        d.degerlendir(_baglam([], sira * 0.2, cooldown=cooldown))
    # Döndüğünde tek ölçüm yeterli olmamalı
    ihlal = d.degerlendir(_baglam([_forklift(9.0)], 2.0, cooldown=cooldown))
    assert ihlal == []

"""zone_intrusion testleri: pozitif, negatif, sınır, cooldown (docs/03 §5)."""

from __future__ import annotations

from yardimci import KARE, bolge, kural, tespit

from app.rules.motor import KuralMotoru


def _motor(mode: str = "inside", min_dwell_s: float = 2.0, cooldown_s: float = 60.0):
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [
            kural(
                "zone_intrusion",
                params={"mode": mode, "min_dwell_s": min_dwell_s},
                cooldown_s=cooldown_s,
            )
        ]
    )
    return motor


def _calistir(motor, zaman_s, tespitler):
    return motor.degerlendir(zaman_s, KARE, tespitler, [bolge()], None)


def test_bolgede_yeterince_kalan_ihlal_uretir():
    motor = _motor()
    icerde = [tespit(ayak=(0.5, 0.5))]
    assert _calistir(motor, 0.0, icerde) == []  # henüz süre dolmadı
    assert _calistir(motor, 1.0, icerde) == []
    ihlaller = _calistir(motor, 2.5, icerde)
    assert len(ihlaller) == 1
    assert ihlaller[0].takip_idler == [1]
    assert ihlaller[0].detaylar["sinif"] == "person"


def test_kisa_gecis_ihlal_uretmez():
    motor = _motor(min_dwell_s=2.0)
    assert _calistir(motor, 0.0, [tespit(ayak=(0.5, 0.5))]) == []
    # kişi bölgeden çıktı, süre sıfırlanır
    assert _calistir(motor, 1.0, [tespit(ayak=(0.1, 0.1))]) == []
    # tekrar girdi — sayaç baştan başlamalı
    assert _calistir(motor, 1.5, [tespit(ayak=(0.5, 0.5))]) == []
    assert _calistir(motor, 3.0, [tespit(ayak=(0.5, 0.5))]) == []  # 1.5 sn oldu
    assert len(_calistir(motor, 3.6, [tespit(ayak=(0.5, 0.5))])) == 1


def test_bolge_disindaki_ihlal_uretmez():
    motor = _motor()
    for zaman in (0.0, 1.0, 2.0, 3.0, 4.0):
        assert _calistir(motor, zaman, [tespit(ayak=(0.05, 0.05))]) == []


def test_hedef_sinif_disindaki_ihlal_uretmez():
    motor = _motor()  # hedef: person
    for zaman in (0.0, 3.0, 6.0):
        assert _calistir(motor, zaman, [tespit(sinif="truck", ayak=(0.5, 0.5))]) == []


def test_outside_modu():
    # "Yaya yolunu kullan" = yolun DIŞINDA olmak ihlal (docs/03 §1)
    motor = _motor(mode="outside")
    disari = [tespit(ayak=(0.05, 0.05))]
    _calistir(motor, 0.0, disari)
    assert len(_calistir(motor, 2.5, disari)) == 1
    # bölge İÇİNDEKİ kişi outside modunda ihlal değildir
    motor2 = _motor(mode="outside")
    _calistir(motor2, 0.0, [tespit(ayak=(0.5, 0.5))])
    assert _calistir(motor2, 2.5, [tespit(ayak=(0.5, 0.5))]) == []


def test_cooldown_tekrar_uyariyi_bastirir():
    motor = _motor(cooldown_s=60.0)
    icerde = [tespit(ayak=(0.5, 0.5))]
    _calistir(motor, 0.0, icerde)
    assert len(_calistir(motor, 2.5, icerde)) == 1  # ilk olay 2.5 sn'de
    # kişi bölgede kalmaya devam ediyor — cooldown (60 sn) boyunca yeni olay YOK
    for zaman in (3.0, 10.0, 30.0, 61.0):
        assert _calistir(motor, zaman, icerde) == []
    # cooldown dolunca (2.5 + 60 = 62.5) tekrar uyarı üretilir
    assert len(_calistir(motor, 63.0, icerde)) == 1


def test_tek_karelik_tespit_kacagi_sureyi_sifirlamaz():
    """Tozlu sahnede dedektörün tek kare kaçırması olağandır; bölgede
    kesintisiz duran kişinin kalış süresi bundan sıfırlanmamalı."""
    motor = _motor(min_dwell_s=2.0)
    ihlaller = []
    for i in range(20):  # 0.5 sn aralık, her 4. karede tespit kaçağı
        tespitler = [] if i % 4 == 3 else [tespit(ayak=(0.5, 0.5))]
        ihlaller.extend(_calistir(motor, i * 0.5, tespitler))
    assert len(ihlaller) == 1


def test_uzun_kayipta_sure_sifirlanir():
    # Kişi gerçekten gittiyse (uzun süre tespit yok) süre birikmeye devam etmemeli
    motor = _motor(min_dwell_s=5.0)
    _calistir(motor, 0.0, [tespit(ayak=(0.5, 0.5))])
    for i in range(1, 10):  # 9 ardışık kayıp — tolerans (5) aşılır
        _calistir(motor, i * 0.5, [])
    # Kişi 'geri geldi': süre baştan başlamalı, hemen ihlal ÜRETMEMELİ
    assert _calistir(motor, 5.5, [tespit(ayak=(0.5, 0.5))]) == []
    assert _calistir(motor, 9.0, [tespit(ayak=(0.5, 0.5))]) == []


def test_bolge_silinmis_veya_pasifse_olay_yok():
    motor = _motor()
    icerde = [tespit(ayak=(0.5, 0.5))]
    # Kuralın işaret ettiği bölge listede yok (silinmiş)
    assert motor.degerlendir(10.0, KARE, icerde, [], None) == []
    # Bölge var ama pasif
    pasif = bolge()
    pasif.aktif = False
    for zaman in (0.0, 3.0, 6.0):
        assert motor.degerlendir(zaman, KARE, icerde, [pasif], None) == []


def test_farkli_takipler_ayri_degerlendirilir():
    motor = _motor()
    ikili = [tespit(ayak=(0.5, 0.5), takip_id=1), tespit(ayak=(0.6, 0.6), takip_id=2)]
    _calistir(motor, 0.0, ikili)
    ihlaller = _calistir(motor, 2.5, ikili)
    assert sorted(i.takip_idler[0] for i in ihlaller) == [1, 2]

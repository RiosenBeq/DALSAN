"""Olay yaşam döngüsü (docs/17 §6.3): açıldı → hatırlatma → kapandı.

Kamera yok, veritabanı yok: zaman elle ilerletilir. Sınanan, değerlendiricinin
ürettiği ihlallerin OLAYA nasıl çevrildiğidir. Değerlendiricilerin kendi
davranışı (ne zaman ihlal ürettikleri) diğer dosyalarda sınanır ve değişmedi.
"""

from __future__ import annotations

from yardimci import KALIBRASYON_10M, KARE, bolge, kural, tespit

from app.rules.motor import KuralMotoru
from app.rules.olay_durumu import (
    ACILDI,
    HATIRLATMA,
    KAPANDI,
    OlayDurumMakinesi,
    olay_anahtari,
)
from app.rules.tipler import BELIRSIZ, VAR, YOK, Ihlal, KkdGozlem

ICERDE = (0.5, 0.5)
DISARIDA = (0.05, 0.05)


def _bolge_motoru(cooldown_s=60.0, bitis_s=None, kayip_toleransi=None, min_dwell_s=1.0):
    params = {"mode": "inside", "min_dwell_s": min_dwell_s}
    if bitis_s is not None:
        params["bitis_s"] = bitis_s
    motor = KuralMotoru(kamera_id=1, kayip_toleransi=kayip_toleransi)
    motor.kurallari_yukle([kural("zone_intrusion", params=params, cooldown_s=cooldown_s)])
    return motor


def _kare(motor, zaman_s, *ayaklar, sinif="person"):
    tespitler = [tespit(sinif=sinif, ayak=a, takip_id=1) for a in ayaklar]
    motor.degerlendir(zaman_s, KARE, tespitler, [bolge()], None)
    return [(g.asama, g.sebep) for g in motor.gecisleri_al()]


def _oynat(motor, adimlar):
    """adimlar: [(zaman, ayak | None)] — None: kişi bu karede görünmedi."""
    gecisler = []
    for zaman_s, ayak in adimlar:
        for asama, sebep in _kare(motor, zaman_s, *([ayak] if ayak else [])):
            gecisler.append((zaman_s, asama, sebep))
    return gecisler


# ------------------------------------------------------------------ temel döngü


def test_ihlal_olay_acar_surerken_hatirlatir_cikinca_kapanir():
    motor = _bolge_motoru(cooldown_s=10.0)
    adimlar = [(t / 2, ICERDE) for t in range(0, 45)]  # 0–22 sn içeride
    adimlar += [(22.5 + t / 2, DISARIDA) for t in range(0, 12)]  # çıktı
    gecisler = _oynat(motor, adimlar)
    assert [(t, a) for t, a, _ in gecisler] == [
        (1.0, ACILDI),  # kalış 1 sn
        (11.0, HATIRLATMA),  # bekleme süresi (10 sn) doldu: yeni satır yok, anons
        (21.0, HATIRLATMA),
        (25.0, KAPANDI),  # son görüldüğü 22,0'dan 3 sn (bitis_s) sonra
    ]
    assert gecisler[-1][2] == "kosul_bitti"


def test_bitis_son_goruldugu_andir_fark_edildigi_an_degil():
    motor = _bolge_motoru()
    _oynat(motor, [(0.0, ICERDE), (1.0, ICERDE), (2.0, ICERDE)])
    motor.degerlendir(2.5, KARE, [tespit(ayak=DISARIDA)], [bolge()], None)
    motor.degerlendir(5.0, KARE, [tespit(ayak=DISARIDA)], [bolge()], None)
    (kapanis,) = [g for g in motor.gecisleri_al() if g.asama == KAPANDI]
    assert kapanis.son_aktif_s == 2.0  # 5,0 değil: bekleme süresi olaya eklenmez


def test_bitis_s_kural_parametresidir():
    motor = _bolge_motoru(bitis_s=10.0)
    gecisler = _oynat(
        motor, [(0.0, ICERDE), (1.0, ICERDE)] + [(1.0 + t, DISARIDA) for t in range(1, 12)]
    )
    assert [(t, a) for t, a, _ in gecisler] == [(1.0, ACILDI), (11.0, KAPANDI)]


def test_kapanistan_sonra_bekleme_suresi_dolmadan_yeni_olay_acilmaz():
    motor = _bolge_motoru(cooldown_s=30.0)
    adimlar = [(0.0, ICERDE), (1.0, ICERDE)]  # açıldı (1 sn)
    adimlar += [(2.0 + t, DISARIDA) for t in range(4)]  # son aktif 1,0 → 4,0'da kapandı
    adimlar += [(6.0 + t, ICERDE) for t in range(10)]  # hemen geri döndü: 6–15 sn
    adimlar += [(31.0, ICERDE), (32.0, ICERDE)]  # bekleme süresi 31 sn'de doldu
    gecisler = [(t, a) for t, a, _ in _oynat(motor, adimlar)]
    assert gecisler == [(1.0, ACILDI), (4.0, KAPANDI), (31.0, ACILDI)]


# ------------------------------------------------------------------ gürültüye dayanıklılık


def test_kayip_toleransi_icindeki_kisa_ortulmede_olay_bitmez():
    """Kişi bir süre görünmez (forklift önünden geçti): iz kayıp toleransı
    içinde olduğu sürece koşul sürüyor sayılır."""
    motor = _bolge_motoru(kayip_toleransi=12, bitis_s=1.0)
    adimlar = [(t / 6, ICERDE) for t in range(0, 12)]  # 0–1,83 sn içeride
    adimlar += [(2.0 + t / 6, None) for t in range(0, 10)]  # 10 karede görünmedi
    adimlar += [(3.8 + t / 6, ICERDE) for t in range(0, 6)]
    gecisler = _oynat(motor, adimlar)
    assert [a for _, a, _ in gecisler] == [ACILDI]


def test_toleransi_asan_iz_kaybi_iz_kayboldu_sebebiyle_kapanir():
    motor = _bolge_motoru(kayip_toleransi=3)
    adimlar = [(0.0, ICERDE), (1.0, ICERDE)] + [(1.0 + t, None) for t in range(1, 10)]
    gecisler = _oynat(motor, adimlar)
    assert [(a, s) for _, a, s in gecisler] == [(ACILDI, ""), (KAPANDI, "iz_kayboldu")]


def test_sinirda_titresen_kisi_tek_olay():
    """Ayak noktası sınırın iki yanına gidip gelir; boşluklar bitis_s'den kısa."""
    motor = _bolge_motoru()
    adimlar = [(0.0, ICERDE), (1.0, ICERDE)]
    for i in range(20):
        t = 1.0 + i
        adimlar += [(t + 0.3, DISARIDA), (t + 0.8, ICERDE)]
    gecisler = _oynat(motor, adimlar)
    assert [a for _, a, _ in gecisler if a != HATIRLATMA] == [ACILDI]


# ------------------------------------------------------------------ KKD


def _kkd_motoru():
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [
            kural(
                "ppe_violation",
                params={"required_ppe": ["helmet"], "min_dwell_s": 0.0},
                cooldown_s=5.0,
            )
        ]
    )
    return motor


def _kkd_kare(motor, zaman_s, baret):
    gozlem = KkdGozlem(baret=baret, yelek=VAR, baret_guven=0.95, yelek_guven=0.95)
    motor.degerlendir(
        zaman_s,
        KARE,
        [tespit(ayak=ICERDE, boy_px=300, kkd=gozlem)],
        [bolge(tip="ppe_required")],
        None,
    )
    return motor.gecisleri_al()


def test_kkd_olayi_belirsize_donunce_belirsiz_sebebiyle_kapanir_hatirlatmaz():
    """Pencere 15 gözlem, en az 8 geçerli gözlem (docs/04 §7): 15 "yok"tan sonra
    gözlemler belirsizleşir. 7 belirsizde oy hâlâ "yok"tur (14…8 geçerli); 8.
    belirsizde (t=22) geçerli gözlem 7'ye iner ve karar BELİRSİZ olur."""
    motor = _kkd_motoru()
    zamanli = []
    for i in range(15):  # 15 "yok" gözlemi: oy "yok" (8. gözlemde, t=7)
        zamanli += [(i * 1.0, g) for g in _kkd_kare(motor, i * 1.0, YOK)]
    for i in range(15, 40):  # kişi sırtını döndü: gözlemler belirsiz
        zamanli += [(i * 1.0, g) for g in _kkd_kare(motor, i * 1.0, BELIRSIZ)]

    assert [(t, g.asama) for t, g in zamanli if g.asama != HATIRLATMA] == [
        (7.0, ACILDI),
        (24.0, KAPANDI),  # son "yok" oyu t=21'de; bitis_s 3 sn
    ]
    kapanis = zamanli[-1][1]
    assert (kapanis.sebep, kapanis.son_aktif_s) == ("belirsiz", 21.0)
    assert zamanli[0][1].ihlal.kod == "PPE_NO_HELMET"
    # Hatırlatmalar yalnız oy "yok"ken (bekleme 5 sn): belirsiz dönemde YOK
    assert [t for t, g in zamanli if g.asama == HATIRLATMA] == [12.0, 17.0]


def test_kkd_oyu_vara_donunce_kosul_bitti():
    motor = _kkd_motoru()
    for i in range(15):
        _kkd_kare(motor, i * 1.0, YOK)
    sonraki = []
    for i in range(15, 40):
        sonraki += _kkd_kare(motor, i * 1.0, VAR)
    (kapanis,) = [g for g in sonraki if g.asama == KAPANDI]
    assert kapanis.sebep == "kosul_bitti"


# ------------------------------------------------------------------ mesafe ve hız


def _mesafe_karesi(motor, zaman_s, kisi, forklift):
    tespitler = [
        tespit(ayak=kisi, takip_id=1),
        tespit(sinif="forklift", ayak=forklift, takip_id=2),
    ]
    motor.degerlendir(zaman_s, KARE, tespitler, [], KALIBRASYON_10M)
    return motor.gecisleri_al()


def test_mesafe_olayi_arac_durunca_bitmez_ayrilinca_biter():
    """Hareket şartı yalnız açılışta aranır; açılmış olay, çift ayrılınca biter."""
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [kural("safe_distance", bolge_id=None, params={"min_frames": 2}, cooldown_s=60.0)]
    )
    gecisler = []
    for i in range(6):  # forklift kişiye doğru ilerliyor (0,1 m/0,2 sn = 0,5 m/sn)
        gecisler += _mesafe_karesi(motor, i * 0.2, (0.5, 0.5), (0.6 - i * 0.01, 0.5))
    assert [g.asama for g in gecisler] == [ACILDI]
    # Forklift durdu, kişi hâlâ yanında: olay sürer
    for i in range(6, 30):
        gecisler += _mesafe_karesi(motor, i * 0.2, (0.5, 0.5), (0.55, 0.5))
    assert [g.asama for g in gecisler] == [ACILDI]
    # Kişi uzaklaştı (5 m): 3 sn sonra biter
    for i in range(30, 50):
        gecisler += _mesafe_karesi(motor, i * 0.2, (0.05, 0.5), (0.55, 0.5))
    assert [g.asama for g in gecisler] == [ACILDI, KAPANDI]
    assert gecisler[-1].sebep == "kosul_bitti"


def test_hiz_olayi_ortanca_sinirin_altina_inince_biter():
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [
            kural(
                "vehicle_speed",
                bolge_id=None,
                hedefler=["forklift"],
                params={"speed_limit_mps": 2.0, "window_size": 3},
            )
        ]
    )
    gecisler = []
    x = 0.1
    for i in range(40):
        adim = 0.06 if i < 15 else 0.01  # 3 m/sn, sonra 0,5 m/sn (0,2 sn aralık)
        x += adim
        motor.degerlendir(
            i * 0.2,
            KARE,
            [tespit(sinif="forklift", ayak=(x, 0.5), takip_id=7)],
            [],
            KALIBRASYON_10M,
        )
        gecisler += motor.gecisleri_al()
    assert [g.asama for g in gecisler] == [ACILDI, KAPANDI]


# ------------------------------------------------------------------ kural değişikliği


def test_kural_degisince_acik_olay_kural_degisti_sebebiyle_biter():
    motor = _bolge_motoru()
    _oynat(motor, [(0.0, ICERDE), (1.0, ICERDE)])
    motor.kurallari_yukle([kural("zone_intrusion", params={"mode": "inside", "min_dwell_s": 5.0})])
    (kapanis,) = motor.gecisleri_al()
    assert (kapanis.asama, kapanis.sebep, kapanis.son_aktif_s) == (KAPANDI, "kural_degisti", 1.0)


def test_baska_kural_degisince_acik_olay_surer():
    motor = KuralMotoru(kamera_id=1)
    birinci = kural("zone_intrusion", kural_id=1, params={"min_dwell_s": 1.0})
    ikinci = kural("zone_intrusion", kural_id=2, hedefler=["forklift"])
    motor.kurallari_yukle([birinci, ikinci])
    _oynat(motor, [(0.0, ICERDE), (1.0, ICERDE)])
    # Yalnız ikinci kuralın parametresi değişti
    motor.kurallari_yukle([birinci, kural("zone_intrusion", kural_id=2, hedefler=["truck"])])
    assert motor.gecisleri_al() == []
    assert [a for _, a, _ in _oynat(motor, [(t, ICERDE) for t in (2.0, 3.0, 4.0)])] == []


# ------------------------------------------------------------------ makine (doğrudan)


def test_anahtar_iz_sirasindan_bagimsiz():
    ihlal = Ihlal(kural_id=4, kamera_id=2, takip_idler=[9, 3], bolge_id=None, olculen=1.0)
    assert olay_anahtari(ihlal) == (4, 2, 3, 9)


def test_verilmeyen_kuralin_bitisi_varsayilandir():
    makine = OlayDurumMakinesi()
    ihlal = Ihlal(kural_id=4, kamera_id=2, takip_idler=[3], bolge_id=None, olculen=1.0)
    assert [g.asama for g in makine.guncelle(0.0, [ihlal], set(), {})] == [ACILDI]
    assert makine.guncelle(2.9, [], set(), {}) == []
    assert [g.asama for g in makine.guncelle(3.0, [], set(), {})] == [KAPANDI]
    assert makine.acik_anahtarlar() == set()

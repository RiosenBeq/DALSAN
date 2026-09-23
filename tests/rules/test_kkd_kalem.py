"""KKD kararı, Faz 3d (docs/17 §5.3-5.6): kalem başına olay, sürücü muafiyeti,
kişi örtüşmesi ve netlik.

- Baret ve yelek AYRI olay ve AYRI beklemedir: yalnız yelek eksikse yalnız
  PPE_NO_VEST; ikisi eksikse iki olay.
- Şüpheli gözlem (kabindeki sürücü, üst üste iki kişi, bulanık kırpık) o karede
  iki kalem için de BELİRSİZDİR; belirsiz asla olay üretmez.
- Örtüşme ve netlik eşiklerinin varsayılanı None = kapalı: test_kkd.py değişmez.
"""

from __future__ import annotations

import pytest
from yardimci import KARE, bolge, kural, tespit

from app.rules.motor import KuralMotoru
from app.rules.olay_durumu import ACILDI, KAPANDI, OlayDurumMakinesi, olay_anahtari
from app.rules.olay_kodu import ihlal_kodu
from app.rules.tipler import BELIRSIZ, VAR, YOK, KkdGozlem, Tespit

IKISI = {
    "required_ppe": ["helmet", "vest"],
    "min_person_height_px": 120,
    "min_confidence": 0.7,
    "window_size": 15,
    "min_valid_observations": 8,
    "violation_ratio": 0.75,
    "min_dwell_s": 3.0,
}


def _motor(cooldown_s: float = 180.0, **params) -> KuralMotoru:
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [kural("ppe_violation", params={**IKISI, **params}, cooldown_s=cooldown_s)]
    )
    return motor


def _kisi(baret: str, yelek: str, takip_id: int = 1, ayak=(0.5, 0.5), netlik=None) -> Tespit:
    return tespit(
        ayak=ayak,
        takip_id=takip_id,
        boy_px=200,
        kkd=KkdGozlem(
            baret=baret,
            yelek=yelek,
            baret_guven=0.9,
            yelek_guven=0.9,
            model_surumu="kkd-test",
            netlik=netlik,
        ),
    )


def _arac(sinif: str, kutu) -> Tespit:
    return Tespit(sinif=sinif, kutu=kutu, takip_id=90, guven=0.9)


def _seri(motor, adet: int, uret, baslangic: float = 0.0):
    """adet kez 0,5 sn arayla; `uret()` o karenin tespit listesini verir."""
    ihlaller = []
    for i in range(adet):
        ihlaller.extend(
            motor.degerlendir(baslangic + i * 0.5, KARE, uret(), [bolge(tip="ppe_required")], None)
        )
    return ihlaller


# ------------------------------------------------------------------ kalem başına olay


def test_yalniz_yelek_eksikse_yalniz_yelek_olayi():
    ihlaller = _seri(_motor(), 12, lambda: [_kisi(VAR, YOK)])
    assert len(ihlaller) == 1
    ihlal = ihlaller[0]
    assert ihlal.detaylar["eksik_kkd"] == ["vest"] and ihlal.kalem == "vest"
    assert ihlal.kod == "PPE_NO_VEST"
    # Ayrıntı iki kalemin kararını da taşır
    assert ihlal.detaylar["ppe"]["helmet"]["decision"] == "yes"


def test_ikisi_eksikse_iki_olay_iki_bekleme():
    motor = _motor(cooldown_s=60.0)
    ihlaller = _seri(motor, 12, lambda: [_kisi(YOK, YOK)])
    assert sorted(i.detaylar["eksik_kkd"][0] for i in ihlaller) == ["helmet", "vest"]
    assert {i.kod for i in ihlaller} == {"PPE_NO_HELMET", "PPE_NO_VEST"}
    assert len({olay_anahtari(i) for i in ihlaller}) == 2
    # Bekleme içinde ikisi de susar; dolunca ikisi ayrı ayrı yeniden gelir
    assert _seri(motor, 20, lambda: [_kisi(YOK, YOK)], baslangic=6.0) == []
    tekrar = _seri(motor, 4, lambda: [_kisi(YOK, YOK)], baslangic=70.0)
    assert sorted(i.kalem for i in tekrar) == ["helmet", "vest"]


def test_bir_kalemin_beklemesi_otekini_bastirmaz():
    """Baret olayı beklemedeyken yelek yeni eksilirse yelek olayı açılır."""
    motor = _motor(cooldown_s=600.0)
    assert [i.kalem for i in _seri(motor, 12, lambda: [_kisi(YOK, VAR)])] == ["helmet"]
    yeni = _seri(motor, 16, lambda: [_kisi(YOK, YOK)], baslangic=6.0)
    assert [i.kalem for i in yeni] == ["vest"]


def test_eski_iki_kalemli_olayin_kodu_degismez():
    """Faz 3d öncesi tek olay iki kalem taşıyordu: kodu hâlâ ağır olanınki."""
    assert ihlal_kodu("ppe_violation", {"eksik_kkd": ["helmet", "vest"]}, None) == "PPE_NO_HELMET"


# ------------------------------------------------------------------ yaşam döngüsü


def _gecisler(motor, kare_uret, sure_s: float) -> list:
    """0,5 sn arayla değerlendirir; motorun ürettiği olay geçişlerini toplar."""
    gecisler = []
    for i in range(int(sure_s / 0.5)):
        an = i * 0.5
        motor.degerlendir(an, KARE, kare_uret(an), [bolge(tip="ppe_required")], None)
        gecisler += motor.gecisleri_al()
    return gecisler


def test_kalemler_ayri_acilir_ve_kapanir():
    """İlk 10 sn ikisi de yok; sonra baret takılıyor, yelek hâlâ yok."""
    gecisler = _gecisler(
        _motor(cooldown_s=600.0),
        lambda an: [_kisi(YOK, YOK) if an < 10 else _kisi(VAR, YOK)],
        20.0,
    )
    acilanlar = [g.anahtar[-1] for g in gecisler if g.asama == ACILDI]
    kapananlar = [g for g in gecisler if g.asama == KAPANDI]
    assert sorted(acilanlar) == ["helmet", "vest"]
    assert [g.anahtar[-1] for g in kapananlar] == ["helmet"]
    assert kapananlar[0].sebep == "kosul_bitti", "iz görülüyor: 'iz kayboldu' değil"


def test_kalem_belirsize_donunce_yalniz_o_olay_belirsiz_kapanir():
    """10. sn'den sonra baş görünmüyor (baret belirsiz), yelek hâlâ yok."""
    gecisler = _gecisler(
        _motor(cooldown_s=600.0),
        lambda an: [_kisi(YOK, YOK) if an < 10 else _kisi(BELIRSIZ, YOK)],
        30.0,
    )
    kapananlar = [(g.anahtar[-1], g.sebep) for g in gecisler if g.asama == KAPANDI]
    assert kapananlar == [("helmet", "belirsiz")]


def test_olay_anahtari_kalemi_tasir_iz_denetimi_bozulmaz():
    makine = OlayDurumMakinesi()
    anahtar = (1, 1, 7, "vest")
    ihlal = _seri(_motor(), 12, lambda: [_kisi(VAR, YOK, takip_id=7)])[0]
    assert olay_anahtari(ihlal) == anahtar
    makine.guncelle(0.0, [ihlal], {anahtar}, {1: 3.0}, frozenset(), [7])
    # İz görünmüyor ve koşul geçti → sebep "iz kayboldu"; iz görünüyorsa değil
    kapanis = makine.guncelle(5.0, [], set(), {1: 3.0}, frozenset(), [8])
    assert [g.sebep for g in kapanis] == ["iz_kayboldu"]


# ------------------------------------------------------------------ sürücü muafiyeti


def _suruculu_kare(ayak=(0.5, 0.5)):
    # Kişi kutusu (460,300)-(540,500); forklift kutusu ayak noktasını içine alıyor
    return [_kisi(YOK, YOK, ayak=ayak), _arac("forklift", (400.0, 350.0, 700.0, 600.0))]


def test_kabindeki_surucu_icin_olay_yok():
    assert _seri(_motor(), 30, _suruculu_kare) == []
    # Muafiyet kapatılırsa aynı sahne olay üretir
    assert len(_seri(_motor(surucu_muaf=False), 30, _suruculu_kare)) == 2


def test_tir_kutusuyla_buyuk_ortusme_de_surucu_sayilir():
    # Ayak noktası kutunun dışında ama kişi kutusunun %75'i tırla örtüşüyor
    def kare():
        return [_kisi(YOK, VAR), _arac("truck", (440.0, 250.0, 700.0, 450.0))]

    assert _seri(_motor(), 30, kare) == []
    assert len(_seri(_motor(surucu_ortusme_orani=0.9), 30, kare)) == 1


def test_aracin_yanindaki_yaya_muaf_degil():
    def kare():
        return [_kisi(YOK, VAR), _arac("forklift", (600.0, 350.0, 900.0, 600.0))]

    assert len(_seri(_motor(), 30, kare)) == 1


# ------------------------------------------------------------------ örtüşme ve netlik


def _ust_uste():
    return [_kisi(YOK, VAR, takip_id=1), _kisi(YOK, VAR, takip_id=2, ayak=(0.52, 0.5))]


def test_kisi_ortusmesi_varsayilan_kapali_esikle_belirsiz():
    assert len(_seri(_motor(), 30, _ust_uste)) == 2  # None: bugünkü davranış
    assert _seri(_motor(max_kisi_ortusmesi=0.5), 30, _ust_uste) == []


def test_netlik_varsayilan_kapali_esikle_belirsiz():
    def bulanik():
        return [_kisi(YOK, VAR, netlik=4.0)]

    assert len(_seri(_motor(), 30, bulanik)) == 1  # None: bugünkü davranış
    assert _seri(_motor(min_netlik=20.0), 30, bulanik) == []
    # Netliği ölçülmemiş gözlem (eski model yolu) eşik yüzünden atılmaz
    assert len(_seri(_motor(min_netlik=20.0), 30, lambda: [_kisi(YOK, VAR)])) == 1


@pytest.mark.parametrize("belirsiz_kaynak", ["surucu", "ortusme", "netlik"])
def test_suphe_kaynaklari_asla_olay_uretmez(belirsiz_kaynak):
    """Her yeni belirsiz kaynağı için ana kural: belirsiz asla olay değildir."""
    params, uret = {
        "surucu": ({}, _suruculu_kare),
        "ortusme": ({"max_kisi_ortusmesi": 0.1}, _ust_uste),
        "netlik": ({"min_netlik": 1000.0}, lambda: [_kisi(YOK, YOK, netlik=5.0)]),
    }[belirsiz_kaynak]
    assert _seri(_motor(**params), 60, uret) == []

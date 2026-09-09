"""Bölge sayacı — kamerasız, sahte veriyle (CLAUDE.md §6).

Sayımın kullanıcı için anlamı şudur: ekrandaki sayı, sahada olanı yansıtmalı.
Bu testler o sözü korur — özellikle "aynı kişi ikinci kez sayılmasın".
"""

from __future__ import annotations

from app.rules.sayim import BolgeSayaci
from tests.rules.yardimci import KARE, bolge, tespit

DISARI = (0.05, 0.05)  # ORTA_BOLGE'nin dışında kalan normalize ayak noktası
ICERI = (0.5, 0.5)


def _kararli(sayac: BolgeSayaci, tespitler, bolgeler, kere: int = 3):
    """min_kare eşiğini aşacak kadar aynı kareyi besler; son sonucu döndürür."""
    sonuc = []
    for _ in range(kere):
        sonuc = sayac.guncelle(KARE, tespitler, bolgeler)
    return sonuc


def test_bolgedeki_kisi_anlik_sayilir():
    sayac = BolgeSayaci(min_kare=3)
    b = [bolge()]
    sonuc = _kararli(sayac, [tespit(ayak=ICERI, takip_id=1)], b)
    assert sonuc[0].anlik == {"person": 1}
    assert sonuc[0].giren == {"person": 1}


def test_bolge_disindaki_kisi_sayilmaz():
    sayac = BolgeSayaci(min_kare=3)
    sonuc = _kararli(sayac, [tespit(ayak=DISARI, takip_id=1)], [bolge()])
    assert sonuc[0].anlik == {}
    assert sonuc[0].giren == {}


def test_titreyen_kutu_hemen_sayilmaz():
    """min_kare dolmadan ne anlık ne giren sayılır — sınırdaki titreme
    onlarca sahte 'giriş' üretmemeli."""
    sayac = BolgeSayaci(min_kare=3)
    b = [bolge()]
    ilk = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    assert ilk[0].anlik == {} and ilk[0].giren == {}
    ikinci = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    assert ikinci[0].giren == {}
    ucuncu = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    assert ucuncu[0].giren == {"person": 1}


def test_ayni_kisi_iki_kez_sayilmaz():
    """Bölgede duran kişi her karede yeniden 'girmiş' sayılırsa sayaç patlar."""
    sayac = BolgeSayaci(min_kare=1)
    b = [bolge()]
    for _ in range(50):
        sonuc = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=7)], b)
    assert sonuc[0].giren == {"person": 1}
    assert sonuc[0].anlik == {"person": 1}


def test_farkli_takipler_ayri_sayilir():
    sayac = BolgeSayaci(min_kare=1)
    b = [bolge()]
    sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    sonuc = sayac.guncelle(
        KARE,
        [tespit(ayak=ICERI, takip_id=1), tespit(ayak=(0.6, 0.6), takip_id=2)],
        b,
    )
    assert sonuc[0].anlik == {"person": 2}
    assert sonuc[0].giren == {"person": 2}


def test_siniflar_ayri_sayilir():
    sayac = BolgeSayaci(min_kare=1)
    sonuc = sayac.guncelle(
        KARE,
        [
            tespit(sinif="person", ayak=ICERI, takip_id=1),
            tespit(sinif="truck", ayak=(0.6, 0.6), takip_id=2),
        ],
        [bolge()],
    )
    assert sonuc[0].anlik == {"person": 1, "truck": 1}


def test_cikan_kisi_anlik_sayidan_dusulur():
    sayac = BolgeSayaci(min_kare=1)
    b = [bolge()]
    sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    sonuc = sayac.guncelle(KARE, [tespit(ayak=DISARI, takip_id=1)], b)
    assert sonuc[0].anlik == {}
    # Ama GİREN geçmişi silinmez: o kişi gerçekten girmişti
    assert sonuc[0].giren == {"person": 1}


def test_kisa_tespit_kacagi_anlik_sayiyi_dusurmez():
    """Tozlu sahnede tek karelik kaçak olağandır; kişi 'çıktı' sayılmamalı."""
    sayac = BolgeSayaci(min_kare=1)
    b = [bolge()]
    sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    sayac.guncelle(KARE, [], b)  # kaçak: hiç tespit yok
    sonuc = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    # Kaçak sonrası aynı kişi geri geldi — İKİNCİ KEZ SAYILMAMALI
    assert sonuc[0].giren == {"person": 1}


def test_uzun_kayip_sonrasi_ayni_takip_yine_sayilmaz():
    """Takip kimliği aynı kaldığı sürece ikinci giriş sayılmaz."""
    sayac = BolgeSayaci(min_kare=1)
    b = [bolge()]
    sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    for _ in range(20):  # kayıp toleransını fazlasıyla aşar
        sayac.guncelle(KARE, [], b)
    sonuc = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    assert sonuc[0].giren == {"person": 1}


def test_zirve_en_yuksek_anlik_degeri_tutar():
    sayac = BolgeSayaci(min_kare=1)
    b = [bolge()]
    sayac.guncelle(
        KARE,
        [tespit(ayak=ICERI, takip_id=i) for i in range(1, 4)],
        b,
    )
    sonuc = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    assert sonuc[0].anlik == {"person": 1}
    assert sonuc[0].zirve == {"person": 3}  # zirve düşmez


def test_pasif_bolge_sayilmaz():
    sayac = BolgeSayaci(min_kare=1)
    pasif = bolge()
    pasif.aktif = False
    sonuc = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], [pasif])
    assert sonuc == []


def test_sifirla_gireni_siler_anligi_korur():
    sayac = BolgeSayaci(min_kare=1)
    b = [bolge()]
    sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    sayac.sifirla()
    sonuc = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], b)
    assert sonuc[0].anlik == {"person": 1}  # hâlâ içeride
    assert sonuc[0].giren == {"person": 1}  # sıfırlandıktan sonra yeniden sayıldı


def test_kare_sayimi_bolgesiz_calisir():
    sayac = BolgeSayaci()
    sayim = sayac.kare_sayimi(
        [
            tespit(sinif="person", takip_id=1),
            tespit(sinif="person", takip_id=2),
            tespit(sinif="truck", takip_id=3),
        ]
    )
    assert sayim == {"person": 2, "truck": 1}


def test_silinen_bolgenin_durumu_bellekte_kalmaz():
    sayac = BolgeSayaci(min_kare=1)
    b1, b2 = bolge(bolge_id=1), bolge(bolge_id=2)
    sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], [b1, b2])
    sonuc = sayac.guncelle(KARE, [tespit(ayak=ICERI, takip_id=1)], [b1])
    assert [s.bolge_id for s in sonuc] == [1]
    assert 2 not in sayac._giren  # bölge silindi → durumu da gitti


def test_toplam_ozellikleri():
    sayac = BolgeSayaci(min_kare=1)
    sonuc = sayac.guncelle(
        KARE,
        [
            tespit(sinif="person", ayak=ICERI, takip_id=1),
            tespit(sinif="truck", ayak=(0.6, 0.6), takip_id=2),
        ],
        [bolge()],
    )
    assert sonuc[0].anlik_toplam == 2
    assert sonuc[0].giren_toplam == 2

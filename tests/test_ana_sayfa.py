"""Ana sayfa (teşhis ekranı) testleri."""

from tests.sema_bilgisi import SON_SEMA_SURUMU


def test_ana_sayfa_200_donuyor(istemci):
    yanit = istemci.get("/")
    assert yanit.status_code == 200
    assert "DALSAN İSG" in yanit.text


def test_ana_sayfa_beklenen_bilgileri_gosteriyor(istemci):
    metin = istemci.get("/").text
    assert "Henüz kamera eklenmedi" in metin
    # Şema sürümü EN SON uygulanan betiktir: yeni göç eklendikçe burası da
    # ilerler. Ana sayfada görünmesi, kullanıcının "hangi sürümdeyim" sorusuna
    # tek bakışta cevap vermesi içindir.
    assert SON_SEMA_SURUMU in metin
    assert "Aktif ayarlar" in metin
    assert "Disk" in metin


def test_sifresizken_her_sayfa_dogrudan_acilir(istemci):
    """YONETICI_SIFRESI boşken bugünkü yerel kullanım aynen sürer.

    Kullanıcı sistemi kendi bilgisayarında denerken her açılışta şifre
    yazmak zorunda kalmamalı (web/giris.py).
    """
    for yol in ("/", "/kameralar", "/kurallar", "/olaylar", "/kkd"):
        assert istemci.get(yol).status_code == 200, yol


def test_sifresizken_giris_sayfasi_ana_sayfaya_yollar(istemci):
    """Şifre yokken giriş kutusu göstermek, kullanıcıyı ne yazacağını
    aramaya iter — anlamsız bir duvar."""
    yanit = istemci.get("/giris", follow_redirects=False)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/"

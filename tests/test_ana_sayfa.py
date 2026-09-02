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


def test_giris_sayfasi_yok_dogrudan_acilir(istemci):
    # Giriş/şifre bilerek kaldırıldı (docs/07 #0): her sayfa doğrudan açılır
    for yol in ("/", "/kameralar", "/kurallar", "/olaylar", "/kkd"):
        assert istemci.get(yol).status_code == 200, yol
    assert istemci.get("/giris").status_code == 404

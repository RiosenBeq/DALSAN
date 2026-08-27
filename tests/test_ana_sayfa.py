"""Ana sayfa (teşhis ekranı) testleri."""


def test_ana_sayfa_200_donuyor(istemci):
    yanit = istemci.get("/")
    assert yanit.status_code == 200
    assert "DALSAN İSG" in yanit.text


def test_ana_sayfa_beklenen_bilgileri_gosteriyor(istemci):
    metin = istemci.get("/").text
    assert "Henüz kamera eklenmedi" in metin
    assert "002_forklift_ornekleri.sql" in metin  # en son şema sürümü
    assert "Aktif ayarlar" in metin
    assert "Disk" in metin


def test_sifre_sayfada_asla_gorunmuyor(istemci):
    # conftest'teki test şifresi sayfada geçmemeli — maskeleme kuralı (docs/01 §3.6)
    metin = istemci.get("/").text
    assert "cok-gizli-test-sifresi" not in metin
    assert "maskeli" in metin

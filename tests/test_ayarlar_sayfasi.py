"""Ayarlar sayfası: eşikleri ve anons adresini ekrandan değiştirme.

NEDEN GEREKLİ: paketlenmiş programda `.env` dosyası kullanıcı profilindeki,
gözle bulunamayan bir klasörde durur ve kullanıcı yazılım bilmiyor. Bu sayfa
olmadan sahada bir eşik değiştirmenin yolu kalmazdı.

Testlerin koruduğu iki söz:

1. **Geçersiz ayar dosyaya YAZILMAZ.** Aksi halde kaydedilen tek bir yanlış
   değer, sistemin bir daha hiç açılmamasına yol açardı — kullanıcı da onu
   geri almayı bilemezdi.
2. **Açıklama satırları korunur.** Dosyanın içindeki Türkçe açıklamalar,
   ayarın ne işe yaradığını anlatan tek kaynaktır.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.ayarlar import env_guncelle
from app.uygulama import uygulama_olustur

ORNEK_ENV = """\
# DALSAN İSG — Ayarlar

# --- Saklama süreleri (gün) ---
OLAY_SAKLAMA_GUN=180
GORUNTU_SAKLAMA_GUN=90

# --- Analiz ---
CIKARIM_CIHAZI=cpu          # cpu | cuda   (fabrikada: cuda)
TESPIT_GUVEN_ESIGI=0.35
TESPIT_INSAN_GUVEN_ESIGI=0.28

# --- Anons: null | ses_karti | http ---
ANONS=null
ANONS_HTTP_ADRESI=
"""

# Formun tamamı gönderilir (tarayıcı da böyle yapar); testler yalnızca
# ilgilendikleri alanı değiştirir.
TAM_FORM = {
    "ANONS": "null",
    "ANONS_HTTP_ADRESI": "",
    "ANONS_BEKLEME_SN": "30",
    "TESPIT_INSAN_GUVEN_ESIGI": "0.28",
    "TESPIT_GUVEN_ESIGI": "0.35",
    "TESPIT_NMS_ESIGI": "0.45",
    "TESPIT_EN_KUCUK_KENAR_PX": "12",
    "GORUNTU_IYILESTIRME": "kapali",
    "CIKARIM_CIHAZI": "cpu",
    "OLAY_SAKLAMA_GUN": "180",
    "GORUNTU_SAKLAMA_GUN": "90",
    "KKD_HAM_VERI_SAKLAMA_GUN": "30",
    "SISTEM_OLAY_SAKLAMA_GUN": "90",
    "DISK_UYARI_GB": "5",
    "NESNE_ESLESME_ESIGI": "0.24",
}


@pytest.fixture
def ayarli_istemci(test_ayarlari):
    """Gerçek bir .env dosyası olan istemci (sayfa dosyaya yazacak)."""
    test_ayarlari.env_yolu.write_text(ORNEK_ENV, encoding="utf-8")
    uygulama = uygulama_olustur(test_ayarlari, analiz=False)
    with TestClient(uygulama) as istemci:
        yield istemci, test_ayarlari


def _form(**degisiklikler) -> dict:
    return {**TAM_FORM, **degisiklikler}


# ------------------------------------------------------------------- sayfa


def test_sayfa_aciliyor_ve_mevcut_degerleri_gosteriyor(ayarli_istemci):
    istemci, _ = ayarli_istemci
    yanit = istemci.get("/ayarlar")
    assert yanit.status_code == 200
    govde = yanit.text
    assert "Sistem ayarları" in govde
    assert 'name="TESPIT_INSAN_GUVEN_ESIGI"' in govde
    assert 'value="0.28"' in govde


def test_sayfa_yeniden_baslatma_uyarisini_kapatilamaz_bicimde_gosteriyor(ayarli_istemci):
    """ "Kaydettim ama hiçbir şey değişmedi" bu ekranın tek büyük tuzağıdır.

    Uyarı, gizlenebilen kılavuz şeridinde DEĞİL, kapatılamayan kendi
    bandındadır (uyari-serit).
    """
    istemci, _ = ayarli_istemci
    govde = istemci.get("/ayarlar").text
    assert "uyari-serit" in govde
    assert "yeniden başlatılınca geçerli olur" in govde
    # Kapatma düğmesi yalnızca kılavuz şeridine aittir; uyarı bandına değil.
    band = govde.split('class="uyari-serit"')[1].split("</section>")[0]
    assert "serit-kapat" not in band


def test_ayarlar_rafta_var(ayarli_istemci):
    istemci, _ = ayarli_istemci
    assert 'href="/ayarlar"' in istemci.get("/komuta").text


def test_ekranda_dosya_adi_ya_da_mutlak_yol_gorunmuyor(ayarli_istemci):
    """Kullanıcı yazılım bilmiyor: '.env' ve mutlak yol ekranda işi yok."""
    istemci, ayarlar = ayarli_istemci
    govde = istemci.get("/ayarlar").text
    assert ".env" not in govde
    assert str(ayarlar.kok_dizin) not in govde


# ------------------------------------------------------------------ kaydetme


def test_gecerli_deger_kaydediliyor(ayarli_istemci):
    istemci, ayarlar = ayarli_istemci

    yanit = istemci.post(
        "/ayarlar/kaydet",
        data=_form(TESPIT_INSAN_GUVEN_ESIGI="0.22", OLAY_SAKLAMA_GUN="365"),
        follow_redirects=False,
    )
    assert yanit.status_code == 303

    metin = ayarlar.env_yolu.read_text(encoding="utf-8")
    assert "TESPIT_INSAN_GUVEN_ESIGI=0.22" in metin
    assert "OLAY_SAKLAMA_GUN=365" in metin


def test_nesne_arama_citasi_ekrandan_degistirilebiliyor(ayarli_istemci):
    """Nesneler sayfasındaki "Ayar notu" bu kutuyu tarif eder — kutu OLMALI.

    .env git'e girmediği için eski bir kurulum kendi çıtasıyla kalır. Not
    kullanıcıya "Ayarlar sayfasındaki Nesne arama titizliği kutusuna 0.24
    yazın" der; o kutu yoksa not, yapılamayacak bir şey söylemiş olur.
    """
    istemci, ayarlar = ayarli_istemci
    assert 'name="NESNE_ESLESME_ESIGI"' in istemci.get("/ayarlar").text

    yanit = istemci.post(
        "/ayarlar/kaydet", data=_form(NESNE_ESLESME_ESIGI="0.24"), follow_redirects=False
    )
    assert yanit.status_code == 303
    assert "NESNE_ESLESME_ESIGI=0.24" in ayarlar.env_yolu.read_text(encoding="utf-8")


def test_nesne_arama_citasi_sinir_disinda_kaydedilmez(ayarli_istemci):
    """Doğrulama açılıştakiyle aynı: kaydedilen bir değer sistemi bozamaz."""
    istemci, ayarlar = ayarli_istemci
    onceki = ayarlar.env_yolu.read_text(encoding="utf-8")

    yanit = istemci.post(
        "/ayarlar/kaydet",
        data=_form(NESNE_ESLESME_ESIGI="1.5"),
        headers={"accept": "text/html"},
    )

    assert yanit.status_code == 400
    assert ayarlar.env_yolu.read_text(encoding="utf-8") == onceki


def test_kaydettikten_sonra_yeniden_baslatma_hatirlatiliyor(ayarli_istemci):
    istemci, _ = ayarli_istemci
    yanit = istemci.post("/ayarlar/kaydet", data=_form(DISK_UYARI_GB="10"))
    assert yanit.status_code == 200
    assert "Sistemi Başlat" in yanit.text


def test_aciklama_satirlari_kayboluyor_MU_hayir(ayarli_istemci):
    """Dosya baştan yazılmaz: Türkçe açıklamalar ve satır içi notlar kalır."""
    istemci, ayarlar = ayarli_istemci

    istemci.post("/ayarlar/kaydet", data=_form(CIKARIM_CIHAZI="cuda"))

    metin = ayarlar.env_yolu.read_text(encoding="utf-8")
    assert "# DALSAN İSG — Ayarlar" in metin
    assert "# --- Saklama süreleri (gün) ---" in metin
    assert "CIKARIM_CIHAZI=cuda          # cpu | cuda   (fabrikada: cuda)" in metin


def test_gecersiz_deger_dosyaya_YAZILMAZ(ayarli_istemci):
    """Kaydedilen bir ayar, sistemin bir daha açılmamasına yol açamaz."""
    istemci, ayarlar = ayarli_istemci
    onceki = ayarlar.env_yolu.read_text(encoding="utf-8")

    yanit = istemci.post(
        "/ayarlar/kaydet",
        data=_form(TESPIT_GUVEN_ESIGI="9"),  # izinli aralık 0.05 – 0.95
        headers={"accept": "text/html"},
    )

    assert yanit.status_code == 400
    assert ayarlar.env_yolu.read_text(encoding="utf-8") == onceki


def test_gecersiz_deger_mesaji_anahtar_degil_ekran_adini_soyluyor(ayarli_istemci):
    """Kullanıcı bir dosya değil, bir form dolduruyor: mesaj o dilde olmalı."""
    istemci, _ = ayarli_istemci

    yanit = istemci.post(
        "/ayarlar/kaydet",
        data=_form(TESPIT_GUVEN_ESIGI="9"),
        headers={"accept": "text/html"},
    )

    govde = yanit.text
    assert "Forklift ve tır için güven eşiği" in govde
    assert "TESPIT_GUVEN_ESIGI" not in govde
    assert ".env" not in govde


def test_anons_http_secilip_adres_bos_birakilirsa_kaydedilmez(ayarli_istemci):
    """Açılışta durduran kural, kaydetme anında da geçerlidir."""
    istemci, ayarlar = ayarli_istemci
    onceki = ayarlar.env_yolu.read_text(encoding="utf-8")

    yanit = istemci.post(
        "/ayarlar/kaydet",
        data=_form(ANONS="http", ANONS_HTTP_ADRESI=""),
        headers={"accept": "text/html"},
    )

    assert yanit.status_code == 400
    assert ayarlar.env_yolu.read_text(encoding="utf-8") == onceki


def test_anons_adresi_semasiz_yazilirsa_kaydedilmez(ayarli_istemci):
    istemci, ayarlar = ayarli_istemci
    onceki = ayarlar.env_yolu.read_text(encoding="utf-8")

    yanit = istemci.post(
        "/ayarlar/kaydet",
        data=_form(ANONS="http", ANONS_HTTP_ADRESI="10.0.0.9/anons"),
        headers={"accept": "text/html"},
    )

    assert yanit.status_code == 400
    assert ayarlar.env_yolu.read_text(encoding="utf-8") == onceki


def test_kaydedilen_deger_sistemin_acilisinda_gecerli_oluyor(ayarli_istemci, tmp_path):
    """Kaydetmek yetmez: dosya, sistemin AÇILIŞTA okuduğu biçimde olmalı."""
    from app.ayarlar import ayarlari_yukle

    istemci, ayarlar = ayarli_istemci
    istemci.post(
        "/ayarlar/kaydet",
        data=_form(ANONS="http", ANONS_HTTP_ADRESI="http://10.0.0.9:8080/anons"),
    )

    yeniden = ayarlari_yukle(ayarlar.kok_dizin)
    assert yeniden.anons == "http"
    assert yeniden.anons_http_adresi == "http://10.0.0.9:8080/anons"


def test_env_dosyasi_yoksa_kayit_yine_de_calisir(test_ayarlari):
    """Ayar dosyası silinmiş olsa bile sayfa kilitlenmez, dosyayı yeniden kurar."""
    ayarlar = dataclasses.replace(test_ayarlari)
    assert not ayarlar.env_yolu.exists()

    uygulama = uygulama_olustur(ayarlar, analiz=False)
    with TestClient(uygulama) as istemci:
        istemci.post("/ayarlar/kaydet", data=_form(DISK_UYARI_GB="9"))

    assert "DISK_UYARI_GB=9" in ayarlar.env_yolu.read_text(encoding="utf-8")


# --------------------------------------------------- .env metin güncellemesi


def test_env_guncelle_yalnizca_ilgili_satirin_degerini_degistirir():
    metin = "# baslik\nA=1   # aciklama\nB=2\n\n# ara yorum\nC=3\n"
    yeni = env_guncelle(metin, {"B": "20"})
    assert yeni == "# baslik\nA=1   # aciklama\nB=20\n\n# ara yorum\nC=3\n"


def test_env_guncelle_satir_ici_aciklamayi_koruyor():
    yeni = env_guncelle("A=1   # neden 1 olduğu\n", {"A": "5"})
    assert yeni == "A=5   # neden 1 olduğu\n"


def test_env_guncelle_yorum_satirindaki_anahtari_canlandirmaz():
    """'# A=1' bir açıklamadır; ayar olarak diriltilmemeli."""
    yeni = env_guncelle("# A=1\n", {"A": "5"})
    assert "# A=1" in yeni
    assert yeni.strip().endswith("A=5")


def test_env_guncelle_olmayan_anahtari_sona_ekliyor():
    yeni = env_guncelle("A=1\n", {"B": "2"})
    assert "A=1" in yeni
    assert "B=2" in yeni


def test_anons_hata_mesajinda_iki_ayar_da_dogru_adiyla_geciyor(ayarli_istemci):
    """ "ANONS" kısa adı, "ANONS_HTTP_ADRESI"nin İÇİNDE de geçer.

    Kısa anahtar önce değiştirilirse uzun anahtar ortasından bölünür ve ekranda
    "“Anons yolu”_HTTP_ADRESI" gibi bozuk bir metin çıkar.
    """
    istemci, _ = ayarli_istemci

    govde = istemci.post(
        "/ayarlar/kaydet",
        data=_form(ANONS="http", ANONS_HTTP_ADRESI=""),
        headers={"accept": "text/html"},
    ).text

    assert "IP hoparlör adresi" in govde
    assert "_HTTP_ADRESI" not in govde
    assert "ANONS" not in govde


@pytest.mark.parametrize(
    "deger",
    ["http://10.0.0.9:8080/anons", "bir iki", "a#b", "adres # not", ""],
)
def test_yazilan_deger_aynen_geri_okunuyor(tmp_path, deger):
    """Boşluk ya da '#' içeren bir değer, yazılıp okununca DEĞİŞMEMELİ.

    Tırnaklanmayan bir '#', dosyayı okuyan tarafta açıklama başlangıcı sayılır
    ve adresin yarısı sessizce kaybolurdu.
    """
    from app.ayarlar import env_degerlerini_oku, env_dosyasina_yaz

    env_yolu = tmp_path / ".env"
    env_yolu.write_text("ANONS_HTTP_ADRESI=\n", encoding="utf-8")

    env_dosyasina_yaz(env_yolu, {"ANONS_HTTP_ADRESI": deger})

    assert env_degerlerini_oku(env_yolu)["ANONS_HTTP_ADRESI"] == deger


def test_tirnakli_degerin_ici_aciklama_sanilmiyor():
    """`A="adres # not"` satırında ' # not' değerin PARÇASIDIR.

    Açıklama sanılırsa bir sonraki kayıtta satırın sonuna yapıştırılır ve
    değer her kayıtta biraz daha bozulur.
    """
    from app.ayarlar import env_guncelle

    metin = env_guncelle("A=eski\n", {"A": "adres # not"})
    assert metin == 'A="adres # not"\n'

    # İkinci kayıt: tırnaklı değerin içindeki '#' satır sonuna taşınmamalı.
    assert env_guncelle(metin, {"A": "yeni"}) == "A=yeni\n"

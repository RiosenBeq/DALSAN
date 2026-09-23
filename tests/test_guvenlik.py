"""Faz 2a güvenlik tabanı (docs/17-V2-TASARIM.md §10.5).

Bu dosyadaki her test, Faz 0 denetiminde (docs/AUDIT.md) KODDAN doğrulanmış
bir açığın kapalı kaldığını korur. Test adı açığı, docstring saldırıyı anlatır.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.ayarlar import env_degerlerini_oku
from app.uygulama import uygulama_olustur
from app.web.giris import cerez_gecerli, cerez_uret, denemeleri_sifirla

SIFRE = "dalsan2026"
TURKCE_SIFRE = "şİğüçö2026"


@pytest.fixture(autouse=True)
def _kilitleri_temizle():
    denemeleri_sifirla()
    yield
    denemeleri_sifirla()


def _istemci(test_ayarlari, sifre: str, env: str | None = None) -> TestClient:
    ayarlar = dataclasses.replace(test_ayarlari, yonetici_sifresi=sifre)
    if env is not None:
        ayarlar.env_yolu.write_text(env, encoding="utf-8")
    return TestClient(uygulama_olustur(ayarlar, analiz=False))


# ------------------------------------------------ R7: kilit X-Forwarded-For ile atlanmaz


def test_sahte_x_forwarded_for_kilidi_atlatamaz(test_ayarlari):
    """Saldırgan her denemede başka bir X-Forwarded-For uydurur. Eski kod o
    başlığın İLK değerini adres sayıyordu: her deneme 'yeni bir adres' olur,
    kilit hiç tetiklenmez ve şifre sınırsız denenirdi."""
    with _istemci(test_ayarlari, SIFRE) as istemci:
        for i in range(5):
            istemci.post(
                "/giris",
                data={"sifre": "yanlis", "sonra": "/"},
                headers={"x-forwarded-for": f"10.9.8.{i}"},
            )
        yanit = istemci.post(
            "/giris",
            data={"sifre": "yanlis", "sonra": "/"},
            headers={"x-forwarded-for": "10.9.8.250"},
            follow_redirects=False,
        )
        assert "kilit=" in yanit.headers["location"]


def test_kilitliyken_sahte_basliklarla_dogru_sifre_de_gecmez(test_ayarlari):
    with _istemci(test_ayarlari, SIFRE) as istemci:
        for _ in range(5):
            istemci.post("/giris", data={"sifre": "yanlis", "sonra": "/"})
        yanit = istemci.post(
            "/giris",
            data={"sifre": SIFRE, "sonra": "/"},
            headers={"x-forwarded-for": "192.0.2.77"},
            follow_redirects=False,
        )
        assert "kilit=" in yanit.headers["location"]


# ------------------------------------------- R15: Türkçe karakterli şifre 500 vermez


def test_turkce_karakterli_sifreyle_giris_calisir(test_ayarlari):
    """hmac.compare_digest iki METNİ ASCII dışında karşılaştıramaz; 'ş' içeren
    şifre kurulduğunda doğru şifreyle giriş bile 500 veriyordu."""
    with _istemci(test_ayarlari, TURKCE_SIFRE) as istemci:
        yanit = istemci.post(
            "/giris", data={"sifre": TURKCE_SIFRE, "sonra": "/"}, follow_redirects=False
        )
        assert yanit.status_code == 303
        assert yanit.headers["location"] == "/"
        assert istemci.get("/kameralar", follow_redirects=False).status_code == 200


def test_giris_kutusuna_turkce_harf_yazmak_500_vermez(test_ayarlari):
    with _istemci(test_ayarlari, SIFRE) as istemci:
        yanit = istemci.post(
            "/giris", data={"sifre": "şifreğ", "sonra": "/"}, follow_redirects=False
        )
        assert yanit.status_code == 303
        assert "hata=1" in yanit.headers["location"]


def test_ascii_disi_cerez_imzasi_cokmez():
    assert cerez_gecerli("9999999999.şğ", SIFRE) is False
    assert cerez_gecerli(cerez_uret(TURKCE_SIFRE), TURKCE_SIFRE) is True


# ------------------------------------------------ R9: şifre sayfaya basılmaz


def _girisli(istemci: TestClient, sifre: str) -> None:
    istemci.post("/giris", data={"sifre": sifre, "sonra": "/"})


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


def _env(sifre: str) -> str:
    return f"# ayar\nYONETICI_SIFRESI={sifre}\nSUNUCU_ADRESI=127.0.0.1\n"


def test_ayarlar_sayfasi_sifreyi_gostermez(test_ayarlari):
    """Şifre `type=text` kutuda DEĞERİYLE basılıyordu: sayfa kaynağında,
    tarayıcı önbelleğinde ve ekran görüntüsünde okunabiliyordu."""
    with _istemci(test_ayarlari, SIFRE, _env(SIFRE)) as istemci:
        _girisli(istemci, SIFRE)
        sayfa = istemci.get("/ayarlar").text
        assert SIFRE not in sayfa
        assert 'type="password" name="YONETICI_SIFRESI" value=""' in sayfa
        assert "Şifre kurulu." in sayfa


def test_bos_sifre_kutusu_mevcut_sifreyi_korur(test_ayarlari):
    """Kutu artık boş gelir. Başka bir ayarı kaydeden kullanıcının şifresi
    sessizce silinmemeli."""
    with _istemci(test_ayarlari, SIFRE, _env(SIFRE)) as istemci:
        _girisli(istemci, SIFRE)
        yanit = istemci.post(
            "/ayarlar/kaydet",
            data={**TAM_FORM, "YONETICI_SIFRESI": "", "DISK_UYARI_GB": "7"},
            follow_redirects=False,
        )
        assert yanit.status_code == 303
        metin = test_ayarlari.env_yolu.read_text(encoding="utf-8")
        assert f"YONETICI_SIFRESI={SIFRE}" in metin
        assert "DISK_UYARI_GB=7" in metin


def test_yeni_sifre_yazilinca_degisir(test_ayarlari):
    with _istemci(test_ayarlari, SIFRE, _env(SIFRE)) as istemci:
        _girisli(istemci, SIFRE)
        istemci.post("/ayarlar/kaydet", data={**TAM_FORM, "YONETICI_SIFRESI": "yeni-sifre-9"})
        assert "YONETICI_SIFRESI=yeni-sifre-9" in test_ayarlari.env_yolu.read_text(encoding="utf-8")


def test_sifreyi_kaldir_kutusu_sifreyi_siler(test_ayarlari):
    with _istemci(test_ayarlari, SIFRE, _env(SIFRE)) as istemci:
        _girisli(istemci, SIFRE)
        istemci.post(
            "/ayarlar/kaydet",
            data={**TAM_FORM, "YONETICI_SIFRESI": "", "YONETICI_SIFRESI_KALDIR": "1"},
        )
        metin = test_ayarlari.env_yolu.read_text(encoding="utf-8")
        assert "YONETICI_SIFRESI=\n" in metin


def test_ag_acikken_sifre_kaldirilamaz(test_ayarlari):
    """Ağa açık + şifresiz kurulum oluşamaz (docs/15): kaldırma isteği de
    açılış doğrulayıcısından geçer, dosyaya hiçbir şey yazılmaz."""
    env = f"YONETICI_SIFRESI={SIFRE}\nSUNUCU_ADRESI=0.0.0.0\n"
    with _istemci(test_ayarlari, SIFRE, env) as istemci:
        _girisli(istemci, SIFRE)
        yanit = istemci.post(
            "/ayarlar/kaydet",
            data={**TAM_FORM, "YONETICI_SIFRESI_KALDIR": "1"},
            follow_redirects=False,
        )
        assert yanit.status_code != 303
        assert test_ayarlari.env_yolu.read_text(encoding="utf-8") == env


# ------------------------------- R8: Host izin listesi (DNS yeniden bağlama) + köken


def _kameralar(istemci: TestClient) -> str:
    return istemci.get("/kameralar").text


KAMERA_FORMU = {
    "name": "Sahte Kamera",
    "area": "",
    "source_type": "rtsp",
    "source_url": "rtsp://10.0.0.5:554/1",
    "sample_fps": "6",
}


def test_yabanci_sitenin_formu_reddedilir(test_ayarlari):
    """Başka bir sitenin sayfası, oturumu açık tarayıcı üzerinden form
    gönderir (CSRF). Tarayıcı Origin'e o sitenin adını yazar."""
    with _istemci(test_ayarlari, "") as istemci:
        yanit = istemci.post(
            "/kameralar/yeni",
            data=KAMERA_FORMU,
            headers={"origin": "http://evil.example"},
            follow_redirects=False,
        )
        assert yanit.status_code == 403
        assert "Sahte Kamera" not in _kameralar(istemci)


def test_ayni_kokenden_form_gecer(test_ayarlari):
    with _istemci(test_ayarlari, "") as istemci:
        yanit = istemci.post(
            "/kameralar/yeni",
            data=KAMERA_FORMU,
            headers={"origin": "http://testserver", "sec-fetch-site": "same-origin"},
            follow_redirects=False,
        )
        assert yanit.status_code == 303
        assert "Sahte Kamera" in _kameralar(istemci)


def test_dns_yeniden_baglama_host_ile_durur(test_ayarlari):
    """Saldırganın adı bu makineye çözüldüğünde tarayıcı için köken
    değişmemiştir: Origin ve Host AYNI sahte adı taşır, Sec-Fetch-Site
    'same-origin' der. Origin'i Host'la kıyaslamak hiçbir şeyi durdurmaz;
    durduran, Host'un izin listesinde olmamasıdır. GET de reddedilir —
    saldırının amacı yanıtı OKUMAKTIR."""
    with _istemci(test_ayarlari, "") as istemci:
        sahte = {
            "host": "evil.example:8080",
            "origin": "http://evil.example:8080",
            "sec-fetch-site": "same-origin",
        }
        assert istemci.get("/olaylar", headers=sahte).status_code == 421
        yanit = istemci.post(
            "/kameralar/yeni", data=KAMERA_FORMU, headers=sahte, follow_redirects=False
        )
        assert yanit.status_code == 421
        assert "Sahte Kamera" not in _kameralar(istemci)


def test_origin_null_reddedilir(test_ayarlari):
    """Sandbox'lı iframe ve file:// sayfası 'Origin: null' gönderir."""
    with _istemci(test_ayarlari, "") as istemci:
        yanit = istemci.post(
            "/kameralar/yeni",
            data=KAMERA_FORMU,
            headers={"origin": "null"},
            follow_redirects=False,
        )
        assert yanit.status_code == 403


def test_capraz_site_isareti_reddedilir(test_ayarlari):
    """Origin'i olmayan (eski) bir istekte bile tarayıcının Sec-Fetch-Site
    başlığını sayfa değiştiremez."""
    with _istemci(test_ayarlari, "") as istemci:
        yanit = istemci.post(
            "/kameralar/yeni",
            data=KAMERA_FORMU,
            headers={"sec-fetch-site": "cross-site"},
            follow_redirects=False,
        )
        assert yanit.status_code == 403


def test_ayni_makinenin_baska_portundaki_sayfa_reddedilir(test_ayarlari):
    """Port karşılaştırılmaz, yani 127.0.0.1:8100'deki bir sayfanın Origin'i
    izinli görünür. Tarayıcı o isteğe 'same-site' der; sistemin kendi sayfası
    her zaman 'same-origin' gönderir."""
    with _istemci(test_ayarlari, "") as istemci:
        yanit = istemci.post(
            "/kameralar/yeni",
            data=KAMERA_FORMU,
            headers={"origin": "http://127.0.0.1:8100", "sec-fetch-site": "same-site"},
            follow_redirects=False,
        )
        assert yanit.status_code == 403
        assert "Sahte Kamera" not in _kameralar(istemci)


@pytest.mark.parametrize(
    ("yonlendiren", "beklenen"),
    [("http://evil.example/sayfa", 403), ("http://testserver/kameralar", 303)],
)
def test_origin_yoksa_referer_bakilir(test_ayarlari, yonlendiren, beklenen):
    with _istemci(test_ayarlari, "") as istemci:
        yanit = istemci.post(
            "/kameralar/yeni",
            data=KAMERA_FORMU,
            headers={"referer": yonlendiren},
            follow_redirects=False,
        )
        assert yanit.status_code == beklenen


def test_basliksiz_istemci_gecer(test_ayarlari):
    """Origin, Referer ve Sec-Fetch-Site'ın üçü de yok: tarayıcı değil (curl,
    Kontrol Paneli). CSRF'in aracı her zaman bir tarayıcıdır."""
    with _istemci(test_ayarlari, "") as istemci:
        yanit = istemci.post("/kameralar/yeni", data=KAMERA_FORMU, follow_redirects=False)
        assert yanit.status_code == 303


def test_guvenli_yontemde_koken_sorulmaz(test_ayarlari):
    """Başka siteden gelen bağlantıyla sayfa AÇMAK serbesttir; yalnız durum
    değiştiren istek denetlenir."""
    with _istemci(test_ayarlari, "") as istemci:
        yanit = istemci.get(
            "/kameralar",
            headers={"referer": "http://evil.example/", "sec-fetch-site": "cross-site"},
        )
        assert yanit.status_code == 200


@pytest.mark.parametrize("host", ["127.0.0.1:8080", "localhost", "[::1]:8080", "127.0.1.1"])
def test_bu_bilgisayarin_adlari_her_zaman_izinli(test_ayarlari, host):
    ayarlar = dataclasses.replace(test_ayarlari, izinli_sunucu_adlari=())
    with TestClient(uygulama_olustur(ayarlar, analiz=False)) as istemci:
        assert istemci.get("/saglik", headers={"host": host}).status_code == 200


def test_geri_donus_gibi_gorunen_alan_adi_izinli_degil(test_ayarlari):
    """'127.' ile başlayan bir ALAN ADI saldırganın olabilir; geri döngü
    kararı gerçek IP ayrıştırmasıyla verilir, önek bakılarak değil."""
    with _istemci(test_ayarlari, "") as istemci:
        yanit = istemci.get("/saglik", headers={"host": "127.saldirgan.example"})
        assert yanit.status_code == 421


def test_izinli_ad_listesi_ve_sunucu_adresi(test_ayarlari):
    ayarlar = dataclasses.replace(
        test_ayarlari,
        izinli_sunucu_adlari=("isg.dalsan.local", "192.168.1.50"),
        sunucu_adresi="10.0.0.7",
    )
    with TestClient(uygulama_olustur(ayarlar, analiz=False)) as istemci:
        for host in ("ISG.dalsan.local:8080", "192.168.1.50:8080", "10.0.0.7:8080"):
            assert istemci.get("/saglik", headers={"host": host}).status_code == 200, host
        assert istemci.get("/saglik", headers={"host": "192.168.1.51"}).status_code == 421


def test_ret_sayfasi_ne_yapilacagini_soyler_ve_adi_kacirir(test_ayarlari):
    with _istemci(test_ayarlari, "") as istemci:
        sayfa = istemci.get("/", headers={"host": "fabrika-pc:9000", "accept": "text/html"}).text
        assert "<code>fabrika-pc</code>" in sayfa
        assert "http://127.0.0.1:9000" in sayfa
        assert "İzinli sunucu" in sayfa and "Tanımadığınız bir adsa eklemeyin" in sayfa
        # Stil dosyası istenmez: o da aynı izinsiz adla reddedilirdi.
        assert "/static/" not in sayfa

        kotu = istemci.get(
            "/", headers={"host": "<script>alert(1)</script>", "accept": "text/html"}
        )
        assert kotu.status_code == 421
        assert "<script>" not in kotu.text

        # fetch çağrısı JSON alır (hatalar.py ile aynı ölçüt)
        assert "hata" in istemci.get("/api/x", headers={"host": "fabrika-pc"}).json()


@pytest.mark.parametrize("yol", ["/docs", "/redoc", "/openapi.json"])
def test_api_belge_uclari_kapali(test_ayarlari, yol):
    """Bu uçlar sistemin bütün rotalarını ve form alanlarını giriş
    istemeden listeliyordu."""
    with _istemci(test_ayarlari, "") as istemci:
        assert istemci.get(yol).status_code == 404


# ------------------------------------------------ R8: izinli ad ayarı


def test_izinli_adlar_ayari_ayrilir_ve_temizlenir(tmp_path):
    from app.ayarlar import ayarlari_coz

    ayarlar = ayarlari_coz(
        tmp_path,
        {"IZINLI_SUNUCU_ADLARI": " 192.168.1.50, http://ISG.dalsan.local:8080/ ; [fe80::1]:80,"},
    )
    assert ayarlar.izinli_sunucu_adlari == ("192.168.1.50", "isg.dalsan.local", "fe80::1")


def test_turkce_harfli_ad_tarayicinin_yazdigi_bicimde_saklanir(tmp_path, test_ayarlari):
    """Tarayıcı 'işg.dalsan.local' adını Host başlığına punycode yazar."""
    from app.ayarlar import ayarlari_coz

    ayarlar = ayarlari_coz(tmp_path, {"IZINLI_SUNUCU_ADLARI": "işg.dalsan.local"})
    punycode = "işg.dalsan.local".encode("idna").decode("ascii")
    assert punycode.startswith("xn--")
    assert ayarlar.izinli_sunucu_adlari == (punycode,)
    izinli = dataclasses.replace(test_ayarlari, izinli_sunucu_adlari=ayarlar.izinli_sunucu_adlari)
    with TestClient(uygulama_olustur(izinli, analiz=False)) as istemci:
        assert istemci.get("/saglik", headers={"host": punycode + ":8080"}).status_code == 200


@pytest.mark.parametrize("deger", ["*", "fabrika pc", "kullanici@192.168.1.50", "null"])
def test_ad_olmayan_izinli_deger_acilisi_durdurur(tmp_path, deger):
    from app.ayarlar import ayarlari_coz
    from app.hatalar import AyarHatasi

    with pytest.raises(AyarHatasi) as hata:
        ayarlari_coz(tmp_path, {"IZINLI_SUNUCU_ADLARI": deger})
    assert "IZINLI_SUNUCU_ADLARI" in hata.value.kullanici_mesaji


def test_izinli_adlar_ayarlar_sayfasindan_yazilir(test_ayarlari):
    with _istemci(test_ayarlari, "", "SUNUCU_ADRESI=127.0.0.1\n") as istemci:
        sayfa = istemci.get("/ayarlar").text
        assert 'name="IZINLI_SUNUCU_ADLARI" value="testserver"' in sayfa
        istemci.post(
            "/ayarlar/kaydet",
            data={**TAM_FORM, "IZINLI_SUNUCU_ADLARI": "192.168.1.50, isg.dalsan.local"},
        )
        # Boşluklu değer tırnakla yazılır; sistemin kendi okuyucusuyla okunur.
        degerler = env_degerlerini_oku(test_ayarlari.env_yolu)
        assert degerler["IZINLI_SUNUCU_ADLARI"] == "192.168.1.50, isg.dalsan.local"

        yanit = istemci.post(
            "/ayarlar/kaydet",
            data={**TAM_FORM, "IZINLI_SUNUCU_ADLARI": "*"},
            follow_redirects=False,
        )
        assert yanit.status_code == 400
        assert env_degerlerini_oku(test_ayarlari.env_yolu) == degerler

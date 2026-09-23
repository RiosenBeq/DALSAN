"""Adresteki kullanıcı adı ve şifre: formda maskeli, günlükte maskeli
(docs/17 §10.5 R18; Faz 5d).

Eskiden kamera düzenleme formu RTSP adresini şifresiyle birlikte sayfaya
basıyordu (sayfa kaynağı, tarayıcı önbelleği, ekran görüntüsü); hoparlör
formu ve Ayarlar'daki anons adresi de öyle. Anons HTTP hatası da tam adresi
günlüğe yazıyordu. Şimdi:

- formlar •••• basar; •••• olduğu gibi gelirse kayıtlı kimlik korunur,
  adresin geri kalanı değişse de;
- anons hatası ne günlüğe ne ekrana şifre yazar; günlük biçimleyicisi de
  son savunma olarak maskeler.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app import loglama, veritabani
from app.hatalar import DogrulamaHatasi
from app.olaylar import anons
from app.uygulama import uygulama_olustur
from app.web.ortak import maskeyi_coz, rtsp_maskele

SIFRELI = "rtsp://admin:gizli123@10.0.0.5:554/ana"


# ------------------------------------------------------------------ desen


@pytest.mark.parametrize(
    ("adres", "beklenen"),
    [
        (SIFRELI, "rtsp://••••@10.0.0.5:554/ana"),
        # Şifrede ham "@": eskiden "rtsp://••••@ss@host" kalıp şifrenin bir parçası görünürdü
        ("rtsp://admin:p@ss@10.0.0.5/ana", "rtsp://••••@10.0.0.5/ana"),
        ("http://10.0.0.9/api?to=a@b", "http://10.0.0.9/api?to=a@b"),  # yoldaki @ kimlik değil
        ("rtsp://10.0.0.5/ana", "rtsp://10.0.0.5/ana"),
        ("/Users/x/test.mp4", "/Users/x/test.mp4"),
    ],
)
def test_maske_deseni(adres, beklenen):
    assert rtsp_maskele(adres) == beklenen


@pytest.mark.parametrize(
    ("gonderilen", "beklenen"),
    [
        ("rtsp://••••@10.0.0.5:554/ana", SIFRELI),  # dokunulmadı
        ("rtsp://••••@10.0.0.7:554/yan", "rtsp://admin:gizli123@10.0.0.7:554/yan"),  # ip değişti
        ("rtsp://yeni:sifre@10.0.0.5/ana", "rtsp://yeni:sifre@10.0.0.5/ana"),  # yeni kimlik
        ("rtsp://10.0.0.5/ana", "rtsp://10.0.0.5/ana"),  # kimlik kaldırıldı
    ],
)
def test_maskeyi_coz(gonderilen, beklenen):
    assert maskeyi_coz(gonderilen, SIFRELI) == beklenen


def test_kimliksiz_kayitta_maske_reddedilir():
    with pytest.raises(DogrulamaHatasi, match="•••• yerine"):
        maskeyi_coz("rtsp://••••@10.0.0.5/ana", "rtsp://10.0.0.5/ana")
    with pytest.raises(DogrulamaHatasi):
        maskeyi_coz("rtsp://admin:••••@10.0.0.5/ana", SIFRELI)  # maskenin bir kısmı


# ------------------------------------------------------------------ kamera formu


def _kamera_ekle(istemci, url: str = SIFRELI) -> int:
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "K1", "area": "Sevkiyat", "source_type": "rtsp", "source_url": url},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return int(yanit.headers["location"].rsplit("/", 1)[1])


def _duzenle(istemci, kamera_id: int, url: str):
    return istemci.post(
        f"/kameralar/{kamera_id}/duzenle",
        data={"name": "K1", "source_type": "rtsp", "source_url": url, "enabled": "1"},
        follow_redirects=False,
    )


def _kayitli_adres(test_ayarlari, kamera_id: int) -> str:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return baglanti.execute(
            "SELECT source_url FROM cameras WHERE id = ?", (kamera_id,)
        ).fetchone()[0]
    finally:
        baglanti.close()


def test_kamera_formu_sifreyi_sayfaya_basmaz(istemci):
    kamera_id = _kamera_ekle(istemci)
    for yol in (f"/kameralar/{kamera_id}", f"/kameralar/{kamera_id}?duzenle=1"):
        metin = istemci.get(yol).text
        assert "gizli123" not in metin, yol
    assert 'value="rtsp://••••@10.0.0.5:554/ana"' in metin


def test_maskeli_adresle_kaydetmek_sifreyi_korur(istemci, test_ayarlari):
    kamera_id = _kamera_ekle(istemci)
    assert _duzenle(istemci, kamera_id, "rtsp://••••@10.0.0.5:554/ana").status_code == 303
    assert _kayitli_adres(test_ayarlari, kamera_id) == SIFRELI
    # Yalnız ip değişti: kimlik yeni adrese taşınır
    assert _duzenle(istemci, kamera_id, "rtsp://••••@10.0.0.8:554/ana").status_code == 303
    assert _kayitli_adres(test_ayarlari, kamera_id) == "rtsp://admin:gizli123@10.0.0.8:554/ana"


def test_yeni_sifre_yazilinca_o_gecerli(istemci, test_ayarlari):
    kamera_id = _kamera_ekle(istemci)
    _duzenle(istemci, kamera_id, "rtsp://admin:yeni456@10.0.0.5:554/ana")
    assert _kayitli_adres(test_ayarlari, kamera_id) == "rtsp://admin:yeni456@10.0.0.5:554/ana"


def test_kimliksiz_kamerada_maske_anlasilir_hata(istemci, test_ayarlari):
    kamera_id = _kamera_ekle(istemci, "rtsp://10.0.0.5:554/ana")
    yanit = _duzenle(istemci, kamera_id, "rtsp://••••@10.0.0.5:554/ana")
    assert yanit.status_code == 400
    assert "•••• yerine" in yanit.json()["hata"]
    assert _kayitli_adres(test_ayarlari, kamera_id) == "rtsp://10.0.0.5:554/ana"


# ------------------------------------------------------------------ hoparlör formu

HOPARLOR = "http://anons:hoparlor-sifresi@10.0.0.9:8080/anons"


def _hoparlor_kaydet(istemci, adres: str, hoparlor_id: int = 0):
    return istemci.post(
        "/hoparlorler/kaydet",
        data={
            "hoparlor_id": str(hoparlor_id),
            "name": "Rampa",
            "area": "",
            "address": adres,
            "enabled": "1",
        },
        follow_redirects=False,
    )


def _hoparlor_adresi(test_ayarlari) -> tuple[int, str]:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute("SELECT id, address FROM speaker_zones").fetchone()
        return int(satir[0]), satir[1]
    finally:
        baglanti.close()


def test_hoparlor_formu_maskeli_ve_kaydederken_korur(istemci, test_ayarlari):
    assert _hoparlor_kaydet(istemci, HOPARLOR).status_code == 303
    metin = istemci.get("/komuta/anons").text
    assert "hoparlor-sifresi" not in metin
    assert 'value="http://••••@10.0.0.9:8080/anons"' in metin

    hoparlor_id, _ = _hoparlor_adresi(test_ayarlari)
    assert (
        _hoparlor_kaydet(istemci, "http://••••@10.0.0.9:8080/anons", hoparlor_id).status_code == 303
    )
    assert _hoparlor_adresi(test_ayarlari) == (hoparlor_id, HOPARLOR)


def test_yeni_hoparlorde_maske_reddedilir(istemci):
    yanit = _hoparlor_kaydet(istemci, "http://••••@10.0.0.9/anons")
    assert yanit.status_code == 400


# ------------------------------------------------------------------ Ayarlar

ANONS_ADRESI = "http://kul:ayar-sifresi@10.0.0.9/anons"


@pytest.fixture
def anonslu_istemci(test_ayarlari):
    """Eski kurulum: IP hoparlör adresi .env'de, kullanıcı adı ve şifresiyle.
    İlk açılışta "Tüm fabrika" kanalına aktarılır (docs/17 K22)."""
    test_ayarlari.env_yolu.write_text(
        f"ANONS=http\nANONS_HTTP_ADRESI={ANONS_ADRESI}\n", encoding="utf-8"
    )
    with TestClient(uygulama_olustur(test_ayarlari, analiz=False)) as istemci:
        yield istemci, test_ayarlari


@pytest.mark.parametrize("yol", ["/ayarlar", "/anons", "/komuta/anons"])
def test_aktarilan_anons_adresi_hicbir_sayfada_sifreli_basilmaz(anonslu_istemci, yol):
    istemci, _ = anonslu_istemci
    assert "ayar-sifresi" not in istemci.get(yol).text


def test_aktarilan_adres_kanal_listesinde_maskeli(anonslu_istemci, test_ayarlari):
    istemci, _ = anonslu_istemci
    assert "http://••••@10.0.0.9/anons" in istemci.get("/komuta/anons").text
    # Maskeli adresle kaydetmek kayıtlı kimliği korur (formdaki •••• geri çözülür)
    kanal_id, adres = _hoparlor_adresi(test_ayarlari)
    assert adres == ANONS_ADRESI
    yanit = _hoparlor_kaydet(istemci, "http://••••@10.0.0.9/anons", hoparlor_id=kanal_id)
    assert yanit.status_code == 303
    assert _hoparlor_adresi(test_ayarlari) == (kanal_id, ANONS_ADRESI)


# ------------------------------------------------------------------ günlük


class _Toplayici(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.mesajlar: list[str] = []

    def emit(self, kayit: logging.LogRecord) -> None:
        self.mesajlar.append(kayit.getMessage())


@pytest.fixture
def anons_gunlugu():
    toplayici = _Toplayici()
    gunluk = logging.getLogger("dalsan.anons")
    gunluk.addHandler(toplayici)
    try:
        yield toplayici.mesajlar
    finally:
        gunluk.removeHandler(toplayici)


@pytest.mark.parametrize(
    "adres",
    [
        # Bağlantı reddedilir (URLError; aşağıda sahte urlopen, ağa çıkılmaz)
        "http://kul:anons-sifresi@10.0.0.9:9/anons",
        # urllib'in "unknown url type" hatası adresi OLDUĞU GİBİ yazar (ValueError)
        "//kul:anons-sifresi@10.0.0.9/anons",
        # R30: bu bilgisayarı gösteren adres gönderilmeden reddedilir
        "http://kul:anons-sifresi@127.0.0.1:9/anons",
    ],
)
def test_anons_hatasi_sifreyi_gunluge_ve_ekrana_yazmaz(adres, anons_gunlugu, monkeypatch):
    import urllib.error
    import urllib.request

    def _reddet(*_a, **_k):
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(urllib.request, "urlopen", _reddet)
    with pytest.raises(anons.AnonsHatasi) as hata:
        anons.http_gonder(adres, "helmet", "Baret", "json")
    assert "anons-sifresi" not in str(hata.value)
    assert hata.value.__cause__ is None, "zincirdeki ham hata yığın izinden sızardı"
    assert anons_gunlugu, "hata günlüğe yazılmalı"
    assert not any("anons-sifresi" in m for m in anons_gunlugu)
    assert any("••••@" in m for m in anons_gunlugu)


def test_gunluk_bicimleyicisi_son_savunma(test_ayarlari):
    loglama.kur(test_ayarlari)
    try:
        raise ValueError("bağlanamadı: rtsp://admin:yigin-sifresi@10.0.0.5/ana")
    except ValueError as hata:
        loglama.log_al("deneme").error(
            "Kamera rtsp://admin:mesaj-sifresi@10.0.0.5/ana açılmadı", exc_info=hata
        )
    satirlar = test_ayarlari.log_dosyasi.read_text(encoding="utf-8").splitlines()
    satir = json.loads(next(s for s in satirlar if "açılmadı" in s))
    assert "mesaj-sifresi" not in satir["mesaj"]
    assert "yigin-sifresi" not in satir.get("ayrinti", "")
    assert "rtsp://••••@10.0.0.5/ana" in satir["mesaj"]

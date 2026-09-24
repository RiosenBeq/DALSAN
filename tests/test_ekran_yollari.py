"""Ekranda söylenen dosya yerleri kuruluma göre doğru mu (app/kaynaklar.py).

Hata mesajları ve sayfalar kullanıcıya günlüğün, ayar dosyasının, yedeklerin
ve anons seslerinin yerini söyler. Eskiden hepsi "program klasöründeki ..."
diyordu; Windows ve Mac uygulamasında veri kullanıcı klasöründedir ve
programın klasöründe aranan dosya yoktur.
"""

from __future__ import annotations

import ssl
import sys
import urllib.error
from pathlib import Path

import pytest

from app import hatalar, kaynaklar, veritabani
from app.analiz import model_indir, tespit
from app.hatalar import VeritabaniHatasi

KOK = Path(__file__).resolve().parents[1]

MAC_KLASORU = "~/Library/Application Support/NextGen Detector"
WIN_GUNLUK = "%LOCALAPPDATA%\\NextGen Detector\\veri\\loglar\\sistem.log"


@pytest.fixture(autouse=True)
def _kapsayici_disinda(monkeypatch):
    """Testler Docker'da koşsa da kurulum türü ölçülen şey olsun."""
    monkeypatch.delenv("DALSAN_KAPSAYICI", raising=False)


@pytest.fixture
def windows_uygulamasi(tmp_path, monkeypatch):
    """Windows uygulaması gibi çalışır: veri %LOCALAPPDATA%\\NextGen Detector'da."""
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "paket_icerigi"), raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    program = tmp_path / "program"
    program.mkdir()
    monkeypatch.setattr(sys, "executable", str(program / "NextGen Detector.exe"))
    return program


def test_gelistirme_kurulumunda_program_klasoru_denir():
    assert kaynaklar.kurulum_turu() == "kaynak"
    assert kaynaklar.veri_klasoru_metni() is None
    assert kaynaklar.kok_klasoru_adi() == "program"
    assert str(kaynaklar.gunluk_dosyasi()) == "program klasöründeki veri/loglar/sistem.log"
    assert str(kaynaklar.ayar_dosyasi()) == "program klasöründeki .env"


def test_dockerda_ayar_dosyasi_sunucudaki_ayar_klasorunde(monkeypatch):
    monkeypatch.setenv("DALSAN_KAPSAYICI", "1")
    assert kaynaklar.kurulum_turu() == "docker"
    assert str(kaynaklar.ayar_dosyasi()) == "program klasöründeki ayar/.env"
    # veri/ sunucudaki program klasörüne bağlıdır (docker-compose.yml)
    assert str(kaynaklar.gunluk_dosyasi()) == "program klasöründeki veri/loglar/sistem.log"


def test_windows_uygulamasinda_yol_yapistirilabilir_ve_kullanici_adi_icermez(
    windows_uygulamasi, tmp_path
):
    gunluk = kaynaklar.gunluk_dosyasi()
    assert kaynaklar.kurulum_turu() == "paket"
    assert gunluk.onek == ""
    assert gunluk.yol == WIN_GUNLUK
    assert str(kaynaklar.ayar_dosyasi()) == "%LOCALAPPDATA%\\NextGen Detector\\.env"
    assert kaynaklar.kok_klasoru_adi() == "%LOCALAPPDATA%\\NextGen Detector"
    assert str(tmp_path) not in str(gunluk)


def test_mac_uygulamasinda_yol_finderin_klasore_gitine_uyar(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "paket_icerigi"), raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda _sinif: tmp_path))
    icerik = tmp_path / "Uygulamalar" / "NextGen Detector.app" / "Contents" / "MacOS"
    icerik.mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(icerik / "NextGen Detector"))

    assert str(kaynaklar.gunluk_dosyasi()) == f"{MAC_KLASORU}/veri/loglar/sistem.log"
    assert str(kaynaklar.ekran_yolu("veri", "sesler")) == f"{MAC_KLASORU}/veri/sesler"


def test_eski_duzende_veri_programin_yanindaysa_program_klasoru_denir(windows_uygulamasi):
    """veri_konumu eski kayıtları taşımaz, programın yanından okur; ekran da
    orayı söylemeli."""
    (windows_uygulamasi / "veri").mkdir()
    (windows_uygulamasi / "veri" / "dalsan.db").write_bytes(b"eski kayitlar")

    assert kaynaklar.veri_klasoru_metni() is None
    assert str(kaynaklar.gunluk_dosyasi()) == "program klasöründeki veri/loglar/sistem.log"


def test_disk_okunamazsa_yer_metni_hata_yolunu_dusurmez(windows_uygulamasi, monkeypatch):
    """Yer, hata mesajı yazılırken hesaplanır (kamera iş parçacığının son
    çaresi, 500 sayfası). Disk okunamıyorsa mesaj yine yazılmalı."""

    def okunamaz(*_a, **_k):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(kaynaklar, "veri_konumu", okunamaz)
    assert kaynaklar.veri_klasoru_metni() is None
    assert "program klasöründeki veri/loglar/sistem.log" in hatalar._beklenmeyen_mesaj()


def test_hata_mesajlari_gunlugun_gercek_yerini_soyler(windows_uygulamasi):
    hata = tespit._uyumsuz_model(Path("nextgen_ai_hizli.onnx"), "teknik")
    assert f"{WIN_GUNLUK} dosyasını" in hata.kullanici_mesaji
    assert "program klasörü" not in hata.kullanici_mesaji
    assert WIN_GUNLUK in hatalar._beklenmeyen_mesaj()


def test_bozuk_kayit_dosyasi_geri_yukleme_dugmesine_ve_dogru_klasore_yollar(
    windows_uygulamasi, tmp_path
):
    """Yedek elle programın klasörüne konursa uygulama onu hiç okumaz."""
    bozuk = tmp_path / "bozuk.db"
    bozuk.write_bytes(b"bu bir veritabani degil" * 64)

    with pytest.raises(VeritabaniHatasi) as hata:
        veritabani.baglanti_ac(bozuk)

    mesaj = hata.value.kullanici_mesaji
    assert "'Yedekten Geri Yükle'" in mesaj
    assert "%LOCALAPPDATA%\\NextGen Detector\\veri\\yedekler klasöründedir" in mesaj
    assert "%LOCALAPPDATA%\\NextGen Detector\\veri\\dalsan.db dosyasının" in mesaj
    assert "program klasörü" not in mesaj.lower()


def test_uygulamada_eksik_sema_yeniden_kurulumla_cozulur(windows_uygulamasi, tmp_path):
    bos = tmp_path / "sema"
    bos.mkdir()
    baglanti = veritabani.baglanti_ac(tmp_path / "dalsan.db")
    try:
        with pytest.raises(VeritabaniHatasi) as hata:
            veritabani.semayi_uygula(baglanti, bos)
    finally:
        baglanti.close()
    assert "Uygulamayı yeniden kurun" in hata.value.kullanici_mesaji
    assert "Program klasörünü" not in hata.value.kullanici_mesaji


def _sertifika_hatasi():
    return urllib.error.URLError(
        ssl.SSLCertVerificationError(
            1, "[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate"
        )
    )


def test_sertifika_hatasinda_python_org_tarifi_yalniz_kaynak_kurulumda(monkeypatch):
    model = Path("nextgen_ai_hizli.onnx")
    kaynak, _ = model_indir._indirme_hata_metinleri("https://ornek", model, _sertifika_hatasi())
    assert "Install Certificates.command" in kaynak

    monkeypatch.setattr(kaynaklar, "paketlenmis_mi", lambda: True)
    paket, _ = model_indir._indirme_hata_metinleri("https://ornek", model, _sertifika_hatasi())
    # Uygulamanın Python'u paketin içindedir: o dosya orada yoktur
    assert "Install Certificates" not in paket
    assert "güvenlik duvarı" in paket

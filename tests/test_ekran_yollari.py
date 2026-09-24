"""Ekranda söylenen dosya yerleri kuruluma göre doğru mu (app/kaynaklar.py).

Hata mesajları ve sayfalar kullanıcıya günlüğün, ayar dosyasının, yedeklerin
ve anons seslerinin yerini söyler. Eskiden hepsi "program klasöründeki ..."
diyordu; Windows ve Mac uygulamasında veri kullanıcı klasöründedir ve
programın klasöründe aranan dosya yoktur.
"""

from __future__ import annotations

import ast
import dataclasses
import re
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


# ------------------------------------------------- elle yazılmış yer yakalayıcı

# Kullanıcıya gidebilecek metinde bir dosyanın yerini elle söyleyen kalıplar.
# Yer app/kaynaklar.py'den gelir; "veri/sesler/baret.wav" gibi Anons
# formuna YAZILACAK göreli yol örneği yer iddiası değildir, serbesttir.
_ELLE_YER_KALIPLARI = (
    re.compile(r"(program|proje|kök) klasör\w*\s+(veri\b|\.env)"),
    re.compile(r"proje klasör"),
    re.compile(r"veri/(loglar|yedekler)"),
)


def _kullaniciya_giden_metin(yol: Path) -> str:
    """.py'de belge dizesi dışındaki metin sabitleri, şablonda yorum dışı
    metin; kalın yazı etiketleri atılır ("klasöründeki <b>veri/...</b>")."""
    kaynak = yol.read_text(encoding="utf-8")
    if yol.suffix == ".py":
        agac = ast.parse(kaynak)
        belge_dizeleri = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                ilk = dugum.body[0] if dugum.body else None
                if isinstance(ilk, ast.Expr) and isinstance(ilk.value, ast.Constant):
                    belge_dizeleri.add(id(ilk.value))
        metin = "\n".join(
            d.value
            for d in ast.walk(agac)
            if isinstance(d, ast.Constant)
            and isinstance(d.value, str)
            and id(d) not in belge_dizeleri
        )
    else:
        metin = re.sub(r"\{#.*?#\}", "", kaynak, flags=re.S)
    return re.sub(r"</?b>", "", metin)


def test_dosya_yerleri_tek_yerden_soylenir():
    """Yeni bir metin yeri elle yazarsa uygulamada yine yanlış olur."""
    for yol in sorted((KOK / "backend" / "app").rglob("*")):
        if yol.suffix not in {".py", ".html", ".js"} or yol.name == "kaynaklar.py":
            continue
        metin = _kullaniciya_giden_metin(yol)
        for kalip in _ELLE_YER_KALIPLARI:
            eslesme = kalip.search(metin)
            assert eslesme is None, f"{yol.relative_to(KOK)}: {eslesme.group(0)!r}"


def test_yakalayici_eski_metinleri_gercekten_yakalar(tmp_path):
    """Kalıplar bu değişiklikten önceki metinlerin her birini yakalamalı."""
    ornekler = {
        "a.py": 'x = ("Sorun sürerse program klasöründeki "\n     "veri/loglar/sistem.log")\n',
        "b.html": "<p>Şifre, program klasöründeki <b>.env</b> dosyasında</p>",
        "c.html": "Bu ayarlar için kök klasördeki .env dosyasını düzenleyin",
        "d.py": 'y = f"Ses dosyası proje klasörünün dışında: {1}"\n',
        "e.py": 'z = "Yedek alındı: veri/yedekler/ klasörüne kaydedildi."\n',
    }
    for ad, icerik in ornekler.items():
        dosya = tmp_path / ad
        dosya.write_text(icerik, encoding="utf-8")
        metin = _kullaniciya_giden_metin(dosya)
        assert any(k.search(metin) for k in _ELLE_YER_KALIPLARI), ad


# ------------------------------------------------------------------ sayfalar


def _paketlenmis_gibi(monkeypatch):
    """Sayfaları Mac uygulamasındaki gibi çizdirir.

    `sys._MEIPASS` kurulmaz: kaynak dosyaların (şablon, şema) yeri değişir ve
    çalışan uygulamanın kendisi bozulurdu; yalnız kurulum türü ve veri
    klasörünün metni değişir.
    """
    monkeypatch.setattr(kaynaklar, "paketlenmis_mi", lambda: True)
    monkeypatch.setattr(kaynaklar, "veri_klasoru_metni", lambda: MAC_KLASORU)


@pytest.fixture
def sifreli_istemci(test_ayarlari):
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    ayarlar = dataclasses.replace(test_ayarlari, yonetici_sifresi="dalsan2026")
    with TestClient(uygulama_olustur(ayarlar, analiz=False)) as istemci:
        yield istemci


def test_giris_sayfasi_ayar_dosyasinin_yerini_kuruluma_gore_soyler(sifreli_istemci, monkeypatch):
    sayfa = sifreli_istemci.get("/giris").text
    assert "program klasöründeki <b>.env</b> dosyasında" in sayfa

    _paketlenmis_gibi(monkeypatch)
    sayfa = sifreli_istemci.get("/giris").text
    assert f"<b>{MAC_KLASORU}/.env</b> dosyasında" in sayfa
    assert "program klasörü" not in sayfa


def test_kilavuz_gelistirme_kurulumunda_baslat_betigini_anlatir(istemci):
    sayfa = istemci.get("/komuta/kilavuz").text
    assert "Baslat-Mac.command" in sayfa
    assert "İlk Kurulumu Yap" in sayfa
    assert "Install Certificates.command" in sayfa
    assert "program klasöründeki <b>veri/loglar/sistem.log</b>" in sayfa
    assert "program klasöründeki <b>docs/15-UZAKTAN-ERISIM.md</b> belgesindedir." in sayfa
    # Ekran tarayıcı sekmesinde değil, kendi penceresinde açılır (docs/11)
    assert "izleme ekranı kendi penceresinde açılır" in sayfa
    assert "Tarayıcı sekmesini" not in sayfa


def test_kilavuz_uygulamada_betik_ve_ilk_kurulum_anlatmaz(istemci, monkeypatch):
    """Windows ve Mac uygulamasında Başlat betiği ve "İlk Kurulumu Yap"
    düğmesi yoktur, sistem kendiliğinden başlar (masaustu/dalsan_launcher.py);
    belgeler ve python.org'un sertifika dosyası pakete girmez."""
    _paketlenmis_gibi(monkeypatch)
    sayfa = istemci.get("/komuta/kilavuz").text

    assert "<b>NextGen Detector</b> uygulamasına" in sayfa
    assert "sistem kendiliğinden" in sayfa
    assert "Baslat-Mac.command" not in sayfa
    assert "İlk Kurulumu Yap" not in sayfa
    assert "Install Certificates" not in sayfa
    assert f"<b>{MAC_KLASORU}/veri/loglar/sistem.log</b>" in sayfa
    assert f"<b>{MAC_KLASORU}/veri/sesler</b>" in sayfa
    assert (
        "<b>docs/15-UZAKTAN-ERISIM.md</b> belgesindedir (uygulamayla gelmez, destek "
        "ekibinden isteyin)." in sayfa
    )
    assert "program klasörü" not in sayfa


def test_teshis_sayfasi_ayar_dosyasini_ve_yedek_klasorunu_dogru_soyler(istemci, monkeypatch):
    sayfa = istemci.get("/").text
    assert "program klasöründeki <b>.env</b> dosyasını düzenleyip" in sayfa
    assert "program klasöründeki <b>veri</b> klasörünü harici diske" in sayfa

    _paketlenmis_gibi(monkeypatch)
    sayfa = istemci.get("/?yedek=ok").text
    assert f"<b>{MAC_KLASORU}/.env</b> dosyasını düzenleyip" in sayfa
    assert f"<b>{MAC_KLASORU}/veri</b> klasörünü harici diske" in sayfa
    assert f"Yedek alındı: {MAC_KLASORU}/veri/yedekler klasörüne kaydedildi." in sayfa
    assert "kök klasör" not in sayfa


def test_anons_sayfasi_ses_yolunun_neye_gore_oldugunu_soyler(istemci, monkeypatch):
    assert "program klasörüne göredir" in istemci.get("/anons").text

    _paketlenmis_gibi(monkeypatch)
    assert f"{MAC_KLASORU} klasörüne göredir" in istemci.get("/anons").text


# --------------------------------------------- sunucu kurulumu (Docker, systemd)


def test_sunucu_kurulumu_acik_isaretle_taninir(monkeypatch):
    assert kaynaklar.sunucu_kurulumu_mu() is False
    monkeypatch.setenv("DALSAN_HIZMET", "1")
    assert kaynaklar.kurulum_turu() == "hizmet" and kaynaklar.sunucu_kurulumu_mu()
    monkeypatch.delenv("DALSAN_HIZMET")
    monkeypatch.setenv("DALSAN_KAPSAYICI", "1")
    assert kaynaklar.kurulum_turu() == "docker" and kaynaklar.sunucu_kurulumu_mu()


def test_yeniden_baslatma_tarifi_kuruluma_gore(monkeypatch):
    assert kaynaklar.baslatma_tarifi() == (
        "Kontrol Paneli'nde Durdur'a, sonra Sistemi Başlat'a basın"
    )
    assert kaynaklar.baslatma_tarifi(yeniden=False) == "Kontrol Paneli'nde Sistemi Başlat'a basın"
    monkeypatch.setenv("DALSAN_HIZMET", "1")
    assert kaynaklar.baslatma_tarifi() == "Sistemi sunucuda yeniden başlatın"
    assert kaynaklar.baslatma_tarifi(cumle_basi=False) == "sistemi sunucuda yeniden başlatın"
    assert kaynaklar.baslatma_tarifi(yeniden=False) == "Sistemi sunucuda başlatın"


def test_sunucuda_hata_mesajlari_kontrol_panelini_anmaz(monkeypatch, tmp_path):
    """Docker ve systemd kurulumunda Kontrol Paneli yoktur; "Durdur'a basın"
    diyen mesaj kullanıcıyı olmayan bir düğmeyi aramaya yollardı."""
    monkeypatch.setenv("DALSAN_HIZMET", "1")
    bozuk = tmp_path / "bozuk.db"
    bozuk.write_bytes(b"bu bir veritabani degil" * 64)
    with pytest.raises(VeritabaniHatasi) as hata:
        veritabani.baglanti_ac(bozuk)
    mesaj = hata.value.kullanici_mesaji
    assert "Kontrol Paneli" not in mesaj
    assert "Sistemi sunucuda durdurup" in mesaj and "docs/06 §1.2.2" in mesaj

    indirme, _ = model_indir._indirme_hata_metinleri(
        "https://ornek", Path("yolox_tiny.onnx"), urllib.error.URLError("yok")
    )
    assert "Kontrol Panel" not in indirme and "sistemi sunucuda yeniden başlatın" in indirme
    hazir = tespit._uyumsuz_model(Path("yolox_tiny.onnx"), "teknik").kullanici_mesaji
    assert "Kontrol Paneli" not in hazir

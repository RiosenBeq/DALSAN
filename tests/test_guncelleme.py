"""GitHub'dan güncelleme (masaustu/dalsan_launcher.py).

Kullanıcı kodu kendi bilgisayarında güncelleyip GitHub'a gönderiyor; fabrika
sunucusunun o değişikliği alması gerekiyor. Bu, Kontrol Paneli'nde bir
DÜĞMEDİR — kullanıcıya "terminal aç, git pull yaz" denmez (CLAUDE.md §8).

Sınanan sözler:
  · Güncelleme öncesi veritabanının yedeği alınır (şema göçleri ileri
    yönlüdür; yedeksiz "güncelledim, bozuldu" durumu geri alınamaz).
  · Kaydedilmemiş yerel değişikliklerin üstüne YAZILMAZ.
  · Paket listesi değiştiyse haber verilir.

Testler GERÇEK git deposu kurar; ağa çıkılmaz, "uzak depo" yerel bir klasördür.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BASLATICI = KOK / "masaustu" / "dalsan_launcher.py"

git_gerekli = pytest.mark.skipif(
    shutil.which("git") is None, reason="git kurulu değil; güncelleme yalnız git ile yapılır"
)


def _git(dizin: Path, *argumanlar: str) -> str:
    return subprocess.run(
        ["git", "-C", str(dizin), *argumanlar],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout


@pytest.fixture
def panel_fabrikasi(tmp_path):
    """Verilen köke bakan bir Kontrol Paneli modülü üretir."""

    def kur(kok: Path):
        tanim = importlib.util.spec_from_file_location(f"panel_{kok.name}", BASLATICI)
        modul = importlib.util.module_from_spec(tanim)
        tanim.loader.exec_module(modul)
        # Modül kendi konumundan kök çıkarır; testte geçici depoya yönlendirilir.
        modul.ROOT = kok
        modul.BACKEND = kok / "backend"
        modul.REQUIREMENTS = kok / "backend" / "requirements.txt"
        modul.ENV_FILE = kok / ".env"
        modul.DATA_DIR = kok / "veri"
        modul.VERITABANI = kok / "veri" / "dalsan.db"
        modul.YEDEK_DIZINI = kok / "veri" / "yedekler"
        return modul

    return kur


@pytest.fixture
def depolar(tmp_path):
    """(uzak, yerel) — yerel depo uzağı takip eder. Ağ YOK."""
    uzak = tmp_path / "uzak"
    uzak.mkdir()
    _git(uzak, "init", "--quiet", "--initial-branch=main")
    _git(uzak, "config", "user.email", "test@ornek")
    _git(uzak, "config", "user.name", "Test")
    (uzak / "backend").mkdir()
    (uzak / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (uzak / "dosya.txt").write_text("ilk\n", encoding="utf-8")
    # Gerçek depodaki gibi: veri/ klasörü git'e girmez.
    (uzak / ".gitignore").write_text("veri/\n.env\n", encoding="utf-8")
    _git(uzak, "add", "-A")
    _git(uzak, "commit", "--quiet", "-m", "ilk")

    yerel = tmp_path / "yerel"
    subprocess.run(["git", "clone", "--quiet", str(uzak), str(yerel)], check=True, timeout=60)
    _git(yerel, "config", "user.email", "test@ornek")
    _git(yerel, "config", "user.name", "Test")
    (yerel / "veri" / "yedekler").mkdir(parents=True)
    (yerel / "veri" / "dalsan.db").write_bytes(b"veritabani icerigi")
    return uzak, yerel


def _uzakta_degisiklik(uzak: Path, metin: str = "yeni\n") -> None:
    (uzak / "dosya.txt").write_text(metin, encoding="utf-8")
    _git(uzak, "add", "-A")
    _git(uzak, "commit", "--quiet", "-m", "guncelleme")


# --------------------------------------------------------------- durum


@git_gerekli
def test_guncel_depoda_guncelleme_yok(panel_fabrikasi, depolar):
    _, yerel = depolar
    panel = panel_fabrikasi(yerel)
    durum, mesaj = panel.guncelleme_durumu()
    assert durum == "guncel", mesaj


@git_gerekli
def test_uzakta_degisiklik_varsa_haber_verilir(panel_fabrikasi, depolar):
    uzak, yerel = depolar
    _uzakta_degisiklik(uzak)
    panel = panel_fabrikasi(yerel)
    durum, mesaj = panel.guncelleme_durumu()
    assert durum == "var"
    assert "1" in mesaj  # kaç değişiklik olduğu yazar


@git_gerekli
def test_git_deposu_olmayan_klasor_anlasilir_cevap_verir(panel_fabrikasi, tmp_path):
    """Paketlenmiş programda git deposu yoktur; kullanıcı ne yapacağını
    öğrenmeli (docs/13 §5)."""
    duz = tmp_path / "duz"
    duz.mkdir()
    panel = panel_fabrikasi(duz)
    durum, _ = panel.guncelleme_durumu()
    assert durum == "depo-degil"
    assert panel.git_deposu_mu() is False


# --------------------------------------------------------------- güncelleme


@git_gerekli
def test_guncelleme_kodu_getirir(panel_fabrikasi, depolar):
    uzak, yerel = depolar
    _uzakta_degisiklik(uzak, "guncellenmis\n")
    panel = panel_fabrikasi(yerel)

    basarili, _ = panel.guncelle()

    assert basarili
    assert (yerel / "dosya.txt").read_text(encoding="utf-8") == "guncellenmis\n"


@git_gerekli
def test_guncellemeden_once_yedek_alinir(panel_fabrikasi, depolar):
    """Şema göçleri ileri yönlüdür: yedeksiz 'güncelledim, bozuldu' geri alınamaz."""
    uzak, yerel = depolar
    _uzakta_degisiklik(uzak)
    panel = panel_fabrikasi(yerel)

    basarili, satirlar = panel.guncelle()

    assert basarili
    yedekler = list((yerel / "veri" / "yedekler").glob("guncelleme-oncesi-*.db"))
    assert len(yedekler) == 1
    assert yedekler[0].read_bytes() == b"veritabani icerigi"
    assert any("Yedek alindi" in s for s in satirlar)


@git_gerekli
def test_kaydedilmemis_degisikligin_ustune_yazilmaz(panel_fabrikasi, depolar):
    """Sunucuda elle düzeltilmiş bir dosya sessizce kaybolmamalı."""
    uzak, yerel = depolar
    _uzakta_degisiklik(uzak)
    (yerel / "dosya.txt").write_text("ELLE DEGISTIRILDI\n", encoding="utf-8")
    panel = panel_fabrikasi(yerel)

    basarili, satirlar = panel.guncelle()

    assert not basarili
    assert (yerel / "dosya.txt").read_text(encoding="utf-8") == "ELLE DEGISTIRILDI\n"
    assert any("kaydedilmemis" in s.lower() for s in satirlar)


@git_gerekli
def test_paket_listesi_degisince_haber_verilir(panel_fabrikasi, depolar):
    """requirements.txt değiştiyse paketler de güncellenmeli; yoksa sistem
    eksik paketle açılmaya çalışır."""
    uzak, yerel = depolar
    (uzak / "backend" / "requirements.txt").write_text("fastapi\nyeni-paket\n", encoding="utf-8")
    _git(uzak, "add", "-A")
    _git(uzak, "commit", "--quiet", "-m", "yeni paket")
    panel = panel_fabrikasi(yerel)

    basarili, satirlar = panel.guncelle()

    assert basarili
    assert "__PAKET_KUR__" in satirlar


@git_gerekli
def test_paket_listesi_degismezse_kurulum_yapilmaz(panel_fabrikasi, depolar):
    """Her güncellemede pip çalıştırmak dakikalar alır ve gereksizdir."""
    uzak, yerel = depolar
    _uzakta_degisiklik(uzak)
    panel = panel_fabrikasi(yerel)

    _, satirlar = panel.guncelle()

    assert "__PAKET_KUR__" not in satirlar


@git_gerekli
def test_yedeksiz_guncelleme_istenirse_yedek_alinmaz(panel_fabrikasi, depolar):
    uzak, yerel = depolar
    _uzakta_degisiklik(uzak)
    panel = panel_fabrikasi(yerel)

    panel.guncelle(yedek_al=False)

    assert list((yerel / "veri" / "yedekler").glob("*.db")) == []


# --------------------------------------------------------------- arayüz


def test_kontrol_panelinde_guncelle_dugmesi_var():
    kaynak = BASLATICI.read_text(encoding="utf-8")
    assert '"Güncelle"' in kaynak
    assert "guncellemeyi_yap" in kaynak


def test_sistem_calisirken_guncelleme_reddedilir():
    """Çalışan süreç kendi kodunu değiştiremez; önce durdurulmalı."""
    kaynak = BASLATICI.read_text(encoding="utf-8")
    govde = kaynak.split("def guncellemeyi_yap():", 1)[1].split("def yedekten_don():", 1)[0]
    assert "sunucu_ayakta()" in govde
    assert "Durdur" in govde


def test_paketlenmis_programda_dugme_konmaz():
    """Paketlenmiş programda git deposu yoktur; çalışmayan bir düğme
    konmamalı (docs/13 §5)."""
    kaynak = BASLATICI.read_text(encoding="utf-8")
    assert "if not PAKETLENMIS else None" in kaynak

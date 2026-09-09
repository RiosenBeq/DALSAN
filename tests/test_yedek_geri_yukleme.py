"""Yedekten geri yükleme (masaustu/dalsan_launcher.py).

K7 (docs/01): "Yedek alma ve geri yükleme dokümante edilmiş ve EN AZ BİR KEZ
PROVA EDİLMİŞ." Prova edilmemiş bir yedek, yedek değildir — bu dosya provanın
kendisidir.

Sınanan sözler:
  · Geri yükleme, geri ALINABİLİR olmalı (önce güvenlik kopyası).
  · Bayat WAL dosyaları silinmeli — kalırlarsa SQLite eski WAL'i yeni
    veritabanının üstüne uygular ve dosya bozulur.
  · Geri yüklenen veritabanı gerçekten AÇILABİLİR olmalı.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BASLATICI = KOK / "masaustu" / "dalsan_launcher.py"


@pytest.fixture
def panel():
    """Kontrol Paneli modülü — tkinter penceresi AÇILMADAN import edilir."""
    tanim = importlib.util.spec_from_file_location("panel_geri_yukleme", BASLATICI)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


def _veritabani_yaz(yol: Path, kamera_adi: str) -> None:
    """İçinde tanınabilir tek satır olan gerçek bir SQLite dosyası üretir."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(yol)
    try:
        baglanti.execute("CREATE TABLE IF NOT EXISTS cameras (id INTEGER PRIMARY KEY, name TEXT)")
        baglanti.execute("DELETE FROM cameras")
        baglanti.execute("INSERT INTO cameras (name) VALUES (?)", (kamera_adi,))
        baglanti.commit()
    finally:
        baglanti.close()


def _kamera_adi(yol: Path) -> str:
    baglanti = sqlite3.connect(yol)
    try:
        return baglanti.execute("SELECT name FROM cameras").fetchone()[0]
    finally:
        baglanti.close()


def test_yedek_geri_yuklenir(panel, tmp_path):
    hedef = tmp_path / "veri" / "dalsan.db"
    yedek = tmp_path / "veri" / "yedekler" / "eski.db"
    _veritabani_yaz(hedef, "BUGUNKU")
    _veritabani_yaz(yedek, "YEDEKTEKI")

    panel.yedekten_geri_yukle(yedek, hedef)

    assert _kamera_adi(hedef) == "YEDEKTEKI"


def test_once_guvenlik_kopyasi_alinir(panel, tmp_path):
    """Yanlış yedeği geri yükleyen kullanıcının dönecek bir yeri olmalı."""
    hedef = tmp_path / "veri" / "dalsan.db"
    yedek = tmp_path / "veri" / "yedekler" / "eski.db"
    _veritabani_yaz(hedef, "BUGUNKU")
    _veritabani_yaz(yedek, "YEDEKTEKI")

    guvenlik = panel.yedekten_geri_yukle(yedek, hedef)

    assert guvenlik is not None and guvenlik.is_file()
    assert _kamera_adi(guvenlik) == "BUGUNKU"
    assert "geri-yukleme-oncesi" in guvenlik.name


def test_bayat_wal_dosyalari_silinir(panel, tmp_path):
    """WAL kalırsa SQLite onu YENİ veritabanının üstüne uygular ve bozar."""
    hedef = tmp_path / "veri" / "dalsan.db"
    yedek = tmp_path / "veri" / "yedekler" / "eski.db"
    _veritabani_yaz(hedef, "BUGUNKU")
    _veritabani_yaz(yedek, "YEDEKTEKI")
    wal = hedef.with_name(hedef.name + "-wal")
    shm = hedef.with_name(hedef.name + "-shm")
    wal.write_bytes(b"bayat wal")
    shm.write_bytes(b"bayat shm")

    panel.yedekten_geri_yukle(yedek, hedef)

    assert not wal.exists(), "bayat WAL silinmedi"
    assert not shm.exists(), "bayat SHM silinmedi"


def test_geri_yuklenen_veritabani_acilabilir(panel, tmp_path):
    """Dosyayı kopyalamak yetmez: sonuç gerçekten çalışan bir veritabanı olmalı."""
    hedef = tmp_path / "veri" / "dalsan.db"
    yedek = tmp_path / "veri" / "yedekler" / "eski.db"
    _veritabani_yaz(hedef, "BUGUNKU")
    _veritabani_yaz(yedek, "YEDEKTEKI")

    panel.yedekten_geri_yukle(yedek, hedef)

    baglanti = sqlite3.connect(hedef)
    try:
        assert baglanti.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        baglanti.close()


def test_veritabani_yokken_de_geri_yuklenir(panel, tmp_path):
    """İlk kurulumda ya da dosya silinmişken geri yükleme yine çalışmalı."""
    hedef = tmp_path / "veri" / "dalsan.db"
    yedek = tmp_path / "veri" / "yedekler" / "eski.db"
    _veritabani_yaz(yedek, "YEDEKTEKI")

    guvenlik = panel.yedekten_geri_yukle(yedek, hedef)

    assert guvenlik is None  # kopyalanacak bir şey yoktu
    assert _kamera_adi(hedef) == "YEDEKTEKI"


def test_olmayan_yedek_anlasilir_hata_verir(panel, tmp_path):
    with pytest.raises(FileNotFoundError):
        panel.yedekten_geri_yukle(tmp_path / "yok.db", tmp_path / "dalsan.db")


def test_veritabaninin_kendisi_geri_yuklenemez(panel, tmp_path):
    """Kullanıcı dosya seçicide yanlışlıkla dalsan.db'yi seçerse, kendi
    üstüne kopyalama yapılıp güvenlik kopyası boşa alınmamalı."""
    hedef = tmp_path / "veri" / "dalsan.db"
    _veritabani_yaz(hedef, "BUGUNKU")
    with pytest.raises(ValueError):
        panel.yedekten_geri_yukle(hedef, hedef)


def test_yedekler_yeniden_eskiye_siralanir(panel, tmp_path):
    import os
    import time

    dizin = tmp_path / "yedekler"
    dizin.mkdir()
    for ad, zaman in (("eski.db", 1_000_000), ("yeni.db", 2_000_000)):
        _veritabani_yaz(dizin / ad, ad)
        os.utime(dizin / ad, (zaman, zaman))
    time.sleep(0)  # dosya zaman damgaları yazıldı

    sirali = panel.yedekleri_listele(dizin)

    assert [y.name for y in sirali] == ["yeni.db", "eski.db"]


def test_yedek_klasoru_yoksa_bos_liste(panel, tmp_path):
    assert panel.yedekleri_listele(tmp_path / "olmayan") == []


def test_kontrol_panelinde_dugme_var():
    """Kullanıcıya terminal komutu verilmez; geri yükleme bir düğmedir
    (CLAUDE.md §8)."""
    kaynak = BASLATICI.read_text(encoding="utf-8")
    assert "Yedekten Geri Yükle" in kaynak
    assert "yedekten_don" in kaynak


def test_sistem_calisirken_geri_yukleme_reddedilir():
    """Açık bir SQLite dosyasının altından dosya değiştirmek veri kaybıdır."""
    kaynak = BASLATICI.read_text(encoding="utf-8")
    # Düğmenin ilk yaptığı iş sunucunun ayakta olup olmadığını sormaktır.
    govde = kaynak.split("def yedekten_don():", 1)[1].split("def sistemi_durdur():", 1)[0]
    assert "sunucu_ayakta()" in govde
    assert "Durdur" in govde

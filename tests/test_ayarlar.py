"""Ayar yükleme testleri: eksik/bozuk ayar anlaşılır Türkçe hatayla durdurmalı."""

from __future__ import annotations

import pytest

from app.ayarlar import ayarlari_yukle
from app.hatalar import AyarHatasi


def _env_yaz(kok, icerik: str) -> None:
    (kok / ".env").write_text(icerik, encoding="utf-8")


def test_env_yoksa_anlasilir_hata(tmp_path):
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert ".env.example" in hata.value.kullanici_mesaji


def test_bos_env_varsayilanlarla_yuklenir(tmp_path):
    # Giriş şifresi yok; .env'de hiçbir satır olmasa da sistem açılır
    _env_yaz(tmp_path, "")
    ayarlar = ayarlari_yukle(tmp_path)
    assert ayarlar.olay_saklama_gun == 180
    assert not hasattr(ayarlar, "yonetici_sifresi")


def test_sayi_bozuksa_hata(tmp_path):
    _env_yaz(tmp_path, "KARE_ORNEKLEME_FPS=alti\n")
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert "KARE_ORNEKLEME_FPS" in hata.value.kullanici_mesaji
    assert "alti" in hata.value.kullanici_mesaji


def test_anons_http_secilip_adres_bos_ise_hata(tmp_path):
    _env_yaz(tmp_path, "ANONS=http\n")
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert "ANONS_HTTP_ADRESI" in hata.value.kullanici_mesaji


def test_gecersiz_secenek_hata(tmp_path):
    _env_yaz(tmp_path, "CIKARIM_CIHAZI=gpu\n")
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert "CIKARIM_CIHAZI" in hata.value.kullanici_mesaji


def test_gecerli_env_yukleniyor_ve_klasorler_olusuyor(tmp_path):
    _env_yaz(tmp_path, "OLAY_SAKLAMA_GUN=30\n")
    ayarlar = ayarlari_yukle(tmp_path)
    assert ayarlar.olay_saklama_gun == 30
    assert ayarlar.goruntu_saklama_gun == 90  # varsayılan
    assert ayarlar.veritabani_yolu == tmp_path / "veri" / "dalsan.db"
    assert ayarlar.veritabani_yolu.parent.is_dir()
    assert ayarlar.goruntu_klasoru.is_dir()
    assert ayarlar.log_dosyasi.parent.is_dir()


def test_bos_birakilan_yol_varsayilana_dusuyor(tmp_path):
    # "VERITABANI_YOLU=" (değeri boş) yazılırsa yol depo kökü OLMAMALI —
    # boş değer, hiç yazılmamış gibi varsayılana düşer.
    _env_yaz(tmp_path, "VERITABANI_YOLU=\nGORUNTU_KLASORU=\n")
    ayarlar = ayarlari_yukle(tmp_path)
    assert ayarlar.veritabani_yolu == tmp_path / "veri" / "dalsan.db"
    assert ayarlar.goruntu_klasoru == tmp_path / "veri" / "goruntuler"

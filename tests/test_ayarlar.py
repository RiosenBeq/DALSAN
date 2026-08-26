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


def test_sifre_bos_ise_hata(tmp_path):
    _env_yaz(tmp_path, "YONETICI_SIFRESI=\n")
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert "YONETICI_SIFRESI" in hata.value.kullanici_mesaji


def test_sayi_bozuksa_hata(tmp_path):
    _env_yaz(tmp_path, "YONETICI_SIFRESI=test\nKARE_ORNEKLEME_FPS=alti\n")
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert "KARE_ORNEKLEME_FPS" in hata.value.kullanici_mesaji
    assert "alti" in hata.value.kullanici_mesaji


def test_anons_http_secilip_adres_bos_ise_hata(tmp_path):
    _env_yaz(tmp_path, "YONETICI_SIFRESI=test\nANONS=http\n")
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert "ANONS_HTTP_ADRESI" in hata.value.kullanici_mesaji


def test_gecersiz_secenek_hata(tmp_path):
    _env_yaz(tmp_path, "YONETICI_SIFRESI=test\nCIKARIM_CIHAZI=gpu\n")
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert "CIKARIM_CIHAZI" in hata.value.kullanici_mesaji


def test_gecerli_env_yukleniyor_ve_klasorler_olusuyor(tmp_path):
    _env_yaz(tmp_path, "YONETICI_SIFRESI=gizli\n")
    ayarlar = ayarlari_yukle(tmp_path)
    assert ayarlar.yonetici_sifresi == "gizli"
    assert ayarlar.olay_saklama_gun == 180  # varsayılan
    assert ayarlar.veritabani_yolu == tmp_path / "veri" / "dalsan.db"
    assert ayarlar.veritabani_yolu.parent.is_dir()
    assert ayarlar.goruntu_klasoru.is_dir()
    assert ayarlar.log_dosyasi.parent.is_dir()


def test_bos_birakilan_yol_varsayilana_dusuyor(tmp_path):
    # "VERITABANI_YOLU=" (değeri boş) yazılırsa yol depo kökü OLMAMALI —
    # boş değer, hiç yazılmamış gibi varsayılana düşer.
    _env_yaz(tmp_path, "YONETICI_SIFRESI=gizli\nVERITABANI_YOLU=\nGORUNTU_KLASORU=\n")
    ayarlar = ayarlari_yukle(tmp_path)
    assert ayarlar.veritabani_yolu == tmp_path / "veri" / "dalsan.db"
    assert ayarlar.goruntu_klasoru == tmp_path / "veri" / "goruntuler"

""".env'deki anons kanalının "Tüm fabrika" satırına tek seferlik aktarımı (docs/17 K22, §7.3-1).

Söz: güncellemeden önce anons nereden duyuluyorsa, sonra da oradan duyulur;
aktarım bir kez yapılır ve operatörün sonradan sildiği satır geri gelmez.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import veritabani, zaman
from app.olaylar.kanallar import AKTARIM_ADIMI, TUM_FABRIKA, env_anonsunu_aktar


@pytest.fixture
def baglanti(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    try:
        yield baglanti
    finally:
        baglanti.close()


def _env(test_ayarlari, **degerler) -> None:
    test_ayarlari.env_yolu.write_text(
        "".join(f"{anahtar}={deger}\n" for anahtar, deger in degerler.items()), encoding="utf-8"
    )


def _hoparlor(baglanti, ad: str, alan: str = "", adres: str = "http://10.0.0.5/a") -> None:
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO speaker_zones (name, area, address, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, 1, ?, ?)",
        (ad, alan, adres, simdi, simdi),
    )
    baglanti.commit()


def _satirlar(baglanti) -> list[dict]:
    return [
        dict(s)
        for s in baglanti.execute(
            "SELECT name, area, address, kind, device, enabled FROM speaker_zones ORDER BY id"
        )
    ]


def test_http_adresi_tum_fabrika_satiri_olur_bir_kez(baglanti, test_ayarlari):
    _env(test_ayarlari, ANONS="http", ANONS_HTTP_ADRESI="http://kul:sifre@10.0.0.9/anons")
    mesajlar = env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu)
    assert _satirlar(baglanti) == [
        {
            "name": TUM_FABRIKA,
            "area": "",
            "address": "http://kul:sifre@10.0.0.9/anons",
            "kind": "http",
            "device": "",
            "enabled": 1,
        }
    ]
    assert mesajlar and "sifre" not in " ".join(mesajlar)  # günlüğe maskeli
    # İkinci açılış: aktarım yapılmıştır, hiçbir şey değişmez
    assert env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu) == []
    assert len(_satirlar(baglanti)) == 1


def test_http_tum_fabrika_zaten_varsa_eklenmez(baglanti, test_ayarlari):
    """Bugün .env adresi yalnız "Tüm fabrika" satırı YOKKEN kullanılıyordu."""
    _hoparlor(baglanti, "Genel", alan="")
    _hoparlor(baglanti, "Sevkiyat", alan="Sevkiyat")
    _env(test_ayarlari, ANONS="http", ANONS_HTTP_ADRESI="http://10.0.0.9/anons")
    env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu)
    assert [(s["name"], s["enabled"]) for s in _satirlar(baglanti)] == [
        ("Genel", 1),
        ("Sevkiyat", 1),
    ]


def test_ses_karti_cikisi_tum_fabrika_olur_eski_satirlar_kapanir(baglanti, test_ayarlari):
    """ANONS=ses_karti iken hoparlör bölgeleri KULLANILMIYORDU: açık kalsalar
    aktarımdan sonra kendi bölümlerinde çalmaya başlardı."""
    _hoparlor(baglanti, "Sevkiyat", alan="Sevkiyat")
    _env(test_ayarlari, ANONS="ses_karti", ANONS_SES_CIHAZI="bluez_output.AA_BB.1")
    mesajlar = env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu)
    satirlar = _satirlar(baglanti)
    assert [(s["name"], s["kind"], s["device"], s["enabled"]) for s in satirlar] == [
        ("Sevkiyat", "http", "", 0),
        (TUM_FABRIKA, "ses_karti", "bluez_output.AA_BB.1", 1),
    ]
    assert any("kapalı aktarıldı" in m for m in mesajlar)


def test_anons_kapaliyken_satir_eklenmez_eskiler_kapanir(baglanti, test_ayarlari):
    _hoparlor(baglanti, "Sevkiyat", alan="Sevkiyat")
    _env(test_ayarlari, ANONS="null")
    env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu)
    assert [(s["name"], s["enabled"]) for s in _satirlar(baglanti)] == [("Sevkiyat", 0)]


def test_env_yoksa_kapali_sayilir(baglanti, test_ayarlari):
    assert not test_ayarlari.env_yolu.exists()
    assert env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu) == []
    assert _satirlar(baglanti) == []
    kayit = baglanti.execute(
        "SELECT COUNT(*) FROM sema_surumu WHERE surum = ?", (AKTARIM_ADIMI,)
    ).fetchone()
    assert kayit[0] == 1


def test_silinen_satir_geri_gelmez(baglanti, test_ayarlari):
    _env(test_ayarlari, ANONS="http", ANONS_HTTP_ADRESI="http://10.0.0.9/anons")
    env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu)
    baglanti.execute("DELETE FROM speaker_zones")
    baglanti.commit()
    env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu)
    assert _satirlar(baglanti) == []


def test_adim_semanin_surumunu_degistirmez(baglanti, test_ayarlari):
    env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu)
    assert veritabani.mevcut_surum(baglanti).endswith(".sql")


def test_acilista_aktarilir(test_ayarlari):
    """Sistem açılırken (lifespan) aktarım kendiliğinden yapılır."""
    from app.uygulama import uygulama_olustur

    _env(test_ayarlari, ANONS="http", ANONS_HTTP_ADRESI="http://10.0.0.9/anons")
    with TestClient(uygulama_olustur(test_ayarlari, analiz=False)):
        pass
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        assert [(s["name"], s["address"]) for s in _satirlar(baglanti)] == [
            (TUM_FABRIKA, "http://10.0.0.9/anons")
        ]
    finally:
        baglanti.close()

"""Zaman yönetimi testleri: UTC saklanır, Europe/Istanbul gösterilir."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app import zaman


def test_simdi_utc_gecerli_iso_ve_utc():
    metin = zaman.simdi_utc()
    an = datetime.fromisoformat(metin)
    assert an.tzinfo is not None
    assert an.utcoffset().total_seconds() == 0
    # Sabit uzunlukta metin — SQLite'ta metin olarak doğru sıralanmasının şartı
    assert len(metin) == len("2026-08-26T13:05:41+00:00")


def test_ekranda_goster_istanbul_kis():
    # Türkiye = UTC+3
    assert zaman.ekranda_goster("2026-01-10T12:00:00+00:00") == "10.01.2026 15:00:00"


def test_ekranda_goster_istanbul_yaz():
    # Türkiye 2016'dan beri yaz saati uygulamaz — yazın da UTC+3
    assert zaman.ekranda_goster("2026-07-10T12:00:00+00:00") == "10.07.2026 15:00:00"


def test_ekranda_goster_z_soneki_ve_tzsiz_metin():
    assert zaman.ekranda_goster("2026-01-10T12:00:00Z") == "10.01.2026 15:00:00"
    # Saat dilimi belirtilmemişse UTC kabul edilir
    assert zaman.ekranda_goster("2026-01-10T12:00:00") == "10.01.2026 15:00:00"


def test_ekranda_goster_bozuk_metin_hata_veriyor():
    with pytest.raises(ValueError):
        zaman.ekranda_goster("dun aksam")


def test_gidis_donus_tutarli():
    metin = zaman.simdi_utc()
    gosterim = zaman.ekranda_goster(metin)
    utc_saat = datetime.fromisoformat(metin).astimezone(UTC)
    beklenen = f"{(utc_saat.hour + 3) % 24:02d}:{utc_saat.minute:02d}:{utc_saat.second:02d}"
    assert gosterim.endswith(beklenen)

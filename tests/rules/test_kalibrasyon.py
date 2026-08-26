"""Homografi (4 nokta zemin kalibrasyonu) testleri."""

from __future__ import annotations

import pytest

from app.rules.kalibrasyon import KalibrasyonHatasi, dunyaya_cevir, homografi_hesapla


def test_kare_esleme_dogru():
    # Görüntünün tamamı (0-1) zeminde 10x10 metrelik alana eşlensin
    h = homografi_hesapla(
        [(0, 0), (1, 0), (1, 1), (0, 1)],
        [(0, 0), (10, 0), (10, 10), (0, 10)],
    )
    x, y = dunyaya_cevir(h, (0.5, 0.5))
    assert abs(x - 5.0) < 1e-6 and abs(y - 5.0) < 1e-6
    x, y = dunyaya_cevir(h, (0.25, 0.75))
    assert abs(x - 2.5) < 1e-6 and abs(y - 7.5) < 1e-6


def test_perspektifli_esleme():
    # Kameradan uzaklaştıkça daralan tipik yamuk görünüm
    h = homografi_hesapla(
        [(0.3, 0.3), (0.7, 0.3), (0.9, 0.9), (0.1, 0.9)],
        [(0, 10), (6, 10), (6, 0), (0, 0)],
    )
    # Köşeler birebir eşlenmeli
    x, y = dunyaya_cevir(h, (0.3, 0.3))
    assert abs(x - 0) < 1e-6 and abs(y - 10) < 1e-6
    x, y = dunyaya_cevir(h, (0.9, 0.9))
    assert abs(x - 6) < 1e-6 and abs(y - 0) < 1e-6


def test_ayni_dogru_uzerindeki_noktalar_anlasilir_hata():
    with pytest.raises(KalibrasyonHatasi) as hata:
        homografi_hesapla(
            [(0.1, 0.1), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4)],
            [(0, 0), (1, 1), (2, 2), (3, 3)],
        )
    assert "4 ayrı nokta" in hata.value.kullanici_mesaji


def test_eksik_nokta_hata():
    with pytest.raises(KalibrasyonHatasi):
        homografi_hesapla([(0, 0), (1, 0)], [(0, 0), (10, 0)])

"""Forklift veri toplama testleri: süpervizörün örnekleme mantığı,
kamera ve model olmadan doğrudan çağrılarak doğrulanır (docs/08 R1).
"""

from __future__ import annotations

import numpy as np
import pytest

from app import veritabani
from app.rules.tipler import SINIF_INSAN, SINIF_TIR, Tespit


@pytest.fixture
def supervizor(test_ayarlari):
    from app.analiz.supervizor import AnalizSupervizoru

    return AnalizSupervizoru(test_ayarlari)  # baslat() ÇAĞRILMAZ — iş parçacığı yok


@pytest.fixture
def baglanti(test_ayarlari):
    b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(b)
    yield b
    b.close()


def _kare() -> np.ndarray:
    return np.full((240, 320, 3), 90, dtype=np.uint8)


def _arac(x1=32.0, y1=48.0, x2=160.0, y2=192.0) -> Tespit:
    return Tespit(sinif=SINIF_TIR, kutu=(x1, y1, x2, y2), takip_id=1)


def test_arac_gorulen_kare_kaydedilir(supervizor, baglanti, test_ayarlari):
    supervizor._forklift_ornekle(baglanti, 1, _kare(), [_arac()], simdi=10_000.0)

    satir = baglanti.execute("SELECT * FROM forklift_samples").fetchone()
    assert satir is not None
    assert satir["source"] == "auto"
    assert satir["label"] is None
    # bbox normalize edilir: 320x240 karede (32,48,160,192) → (0.1, 0.2, 0.5, 0.8)
    assert satir["bbox"] == "[0.1, 0.2, 0.5, 0.8]"
    # Tam kare diske gerçek JPEG olarak yazılır
    dosya = test_ayarlari.goruntu_klasoru / satir["frame_path"]
    assert dosya.is_file()
    assert dosya.stat().st_size > 500


def test_arac_yoksa_kaydedilmez(supervizor, baglanti):
    insan = Tespit(sinif=SINIF_INSAN, kutu=(10, 10, 50, 120), takip_id=2)
    supervizor._forklift_ornekle(baglanti, 1, _kare(), [insan], simdi=10_000.0)
    assert baglanti.execute("SELECT COUNT(*) AS n FROM forklift_samples").fetchone()["n"] == 0


def test_saatlik_limit_uygulanir(supervizor, baglanti, test_ayarlari):
    # conftest: saatte 30 örnek → örnekler arası en az 120 sn
    supervizor._forklift_ornekle(baglanti, 1, _kare(), [_arac()], simdi=10_000.0)
    supervizor._forklift_ornekle(baglanti, 1, _kare(), [_arac()], simdi=10_050.0)  # erken
    assert baglanti.execute("SELECT COUNT(*) AS n FROM forklift_samples").fetchone()["n"] == 1

    supervizor._forklift_ornekle(baglanti, 1, _kare(), [_arac()], simdi=10_121.0)  # süre doldu
    assert baglanti.execute("SELECT COUNT(*) AS n FROM forklift_samples").fetchone()["n"] == 2


def test_limit_kamera_bazlidir(supervizor, baglanti):
    supervizor._forklift_ornekle(baglanti, 1, _kare(), [_arac()], simdi=10_000.0)
    supervizor._forklift_ornekle(baglanti, 2, _kare(), [_arac()], simdi=10_000.0)
    assert baglanti.execute("SELECT COUNT(*) AS n FROM forklift_samples").fetchone()["n"] == 2


def test_etiketsiz_eski_kareler_bakimda_silinir(supervizor, baglanti, test_ayarlari):
    supervizor._forklift_ornekle(baglanti, 1, _kare(), [_arac()], simdi=10_000.0)
    satir = baglanti.execute("SELECT id, frame_path FROM forklift_samples").fetchone()
    dosya = test_ayarlari.goruntu_klasoru / satir["frame_path"]

    # Kayıt, saklama süresinin dışına itilir; etiketlenmemiş → silinmeli
    baglanti.execute(
        "UPDATE forklift_samples SET captured_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
        (satir["id"],),
    )
    baglanti.commit()
    silinen = supervizor._forklift_hamlarini_sil(baglanti)
    assert silinen == 1
    assert not dosya.exists()
    assert baglanti.execute("SELECT COUNT(*) AS n FROM forklift_samples").fetchone()["n"] == 0


def test_etiketli_kareler_bakimda_korunur(supervizor, baglanti, test_ayarlari):
    supervizor._forklift_ornekle(baglanti, 1, _kare(), [_arac()], simdi=10_000.0)
    baglanti.execute(
        "UPDATE forklift_samples SET captured_at = '2000-01-01T00:00:00+00:00', "
        "label = 'yes', labeled_at = '2000-01-02T00:00:00+00:00'"
    )
    baglanti.commit()
    assert supervizor._forklift_hamlarini_sil(baglanti) == 0
    assert baglanti.execute("SELECT COUNT(*) AS n FROM forklift_samples").fetchone()["n"] == 1

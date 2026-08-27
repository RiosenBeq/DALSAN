"""Forklift eğitim hattı testleri (docs/08 R1).

Gerçek saha verisi olmadan hattın uçtan uca doğruluğu, SENTETİK karelerle
doğrulanır: "forklift" kareleri sarı-turuncu dolgulu, "değil" kareleri
gri-mavi dolgulu üretilir. Amaç modelin gücünü ölçmek değil; eğitimin
çalıştığını, karşılaştırmanın dürüst yapıldığını ve yalnızca daha iyi
modelin devreye alındığını kanıtlamaktır.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from app import veritabani, zaman
from app.egitim.forklift_egitim import EN_AZ_NEGATIF, EN_AZ_POZITIF, egit

BBOX = "[0.2, 0.2, 0.8, 0.8]"


@pytest.fixture
def baglanti(test_ayarlari):
    b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(b)
    yield b
    b.close()


def _kare_yaz(test_ayarlari, ad: str, renk: tuple[int, int, int], tohum: int) -> str:
    import cv2

    rng = np.random.default_rng(tohum)
    kare = rng.integers(30, 70, (120, 160, 3), dtype=np.uint8)
    # bbox bölgesine sınıfa özgü renk: sentetik ama öğrenilebilir bir işaret
    kare[24:96, 32:128] = np.array(renk, dtype=np.uint8)
    goreli = f"forklift-ornekler/{ad}.jpg"
    yol = test_ayarlari.goruntu_klasoru / goreli
    yol.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(yol), kare)
    return goreli


def _veri_uret(baglanti, test_ayarlari, pozitif: int, negatif: int) -> None:
    """Zamana yayılmış, etiketli sentetik kareler (dönüşümlü — iki sınıf da
    hem eğitim hem test diliminde bulunsun)."""
    kayitlar = []
    for i in range(max(pozitif, negatif)):
        if i < pozitif:
            kayitlar.append((f"fk-{i:03d}", (0, 165, 255), "yes"))  # turuncu (BGR)
        if i < negatif:
            kayitlar.append((f"tir-{i:03d}", (140, 90, 60), "no"))  # gri-mavi
    for sira, (ad, renk, etiket) in enumerate(kayitlar):
        goreli = _kare_yaz(test_ayarlari, ad, renk, tohum=sira)
        baglanti.execute(
            "INSERT INTO forklift_samples "
            "(captured_at, frame_path, bbox, source, label, labeled_at) "
            "VALUES (?, ?, ?, 'auto', ?, ?)",
            (
                f"2026-08-{10 + sira // 40:02d}T{sira % 24:02d}:00:00+00:00",
                goreli,
                BBOX,
                etiket,
                zaman.simdi_utc(),
            ),
        )
    baglanti.commit()


def test_yetersiz_veriyle_egitim_reddedilir(baglanti, test_ayarlari):
    _veri_uret(baglanti, test_ayarlari, pozitif=5, negatif=5)
    sonuc = egit(baglanti, test_ayarlari)
    assert sonuc.hata is not None
    assert str(EN_AZ_POZITIF) in sonuc.hata
    assert not sonuc.devreye_alindi
    assert not (test_ayarlari.forklift_model_klasoru / "aktif.json").exists()


def test_egitim_calisir_karsilastirir_ve_devreye_alir(baglanti, test_ayarlari):
    _veri_uret(baglanti, test_ayarlari, pozitif=EN_AZ_POZITIF + 10, negatif=EN_AZ_NEGATIF + 10)
    sonuc = egit(baglanti, test_ayarlari)

    assert sonuc.hata is None
    assert sonuc.surum == "v001"
    assert sonuc.test_sayisi >= 20
    # Ayrılabilir sentetik veride yeni model, "hiçbir şey forklift değil"
    # diyen eski sistemden iyi olmalı ve devreye alınmalı
    assert sonuc.yeni_isabet > sonuc.eski_isabet
    assert sonuc.devreye_alindi
    assert "mevcut sistem" in sonuc.eski_ad

    klasor = test_ayarlari.forklift_model_klasoru
    assert (klasor / "v001.npz").is_file()
    assert (klasor / "v001.json").is_file()
    aktif = json.loads((klasor / "aktif.json").read_text(encoding="utf-8"))
    assert aktif["surum"] == "v001"
    assert 0 < aktif["esik"] < 1


def test_ikinci_egitim_devredeki_modelle_karsilastirilir(baglanti, test_ayarlari):
    _veri_uret(baglanti, test_ayarlari, pozitif=EN_AZ_POZITIF + 10, negatif=EN_AZ_NEGATIF + 10)
    ilk = egit(baglanti, test_ayarlari)
    assert ilk.devreye_alindi

    ikinci = egit(baglanti, test_ayarlari)
    assert ikinci.surum == "v002"
    # Karşılaştırma artık modelsiz sisteme karşı değil, devredeki v001'e karşı
    assert "v001" in ikinci.eski_ad
    # Aynı veriyle eğitilen v002 daha iyi OLAMAZ → devreye alınmaz, v001 devrede kalır
    assert not ikinci.devreye_alindi
    aktif = json.loads(
        (test_ayarlari.forklift_model_klasoru / "aktif.json").read_text(encoding="utf-8")
    )
    assert aktif["surum"] == "v001"
    # Ama v002 yine de kayıt altında (docs/04 §9: her sürüm saklanır)
    assert (test_ayarlari.forklift_model_klasoru / "v002.npz").is_file()


def test_devredeki_model_araci_forklift_yapar(baglanti, test_ayarlari):
    """Eğitilen model boru hattına bağlanınca araç sınıfı gerçekten değişiyor."""
    from app.analiz.boru_hatti import KameraHatti
    from app.analiz.forklift_siniflandirici import ForkliftSiniflandirici
    from app.rules.tipler import SINIF_FORKLIFT, SINIF_TIR, Tespit

    _veri_uret(baglanti, test_ayarlari, pozitif=EN_AZ_POZITIF + 10, negatif=EN_AZ_NEGATIF + 10)
    assert egit(baglanti, test_ayarlari).devreye_alindi

    model = ForkliftSiniflandirici(test_ayarlari.forklift_model_klasoru)
    assert model.model_var and model.surum == "v001"

    # Eğitimdekiyle aynı desende, eğitimde HİÇ GÖRÜLMEMİŞ iki yeni kare
    import cv2

    kok = test_ayarlari.goruntu_klasoru
    forklift_kare = cv2.imread(str(kok / _kare_yaz(test_ayarlari, "yeni-fk", (0, 165, 255), 999)))
    tir_kare = cv2.imread(str(kok / _kare_yaz(test_ayarlari, "yeni-tir", (140, 90, 60), 998)))
    kutu = (32.0, 24.0, 128.0, 96.0)  # _kare_yaz'daki bbox bölgesi, piksel

    hat = KameraHatti(kamera_id=1, fps=5)
    tespitler = [Tespit(sinif=SINIF_TIR, kutu=kutu, takip_id=1)]
    hat._forklift_siniflandir(forklift_kare, tespitler, model)
    assert tespitler[0].sinif == SINIF_FORKLIFT

    tespitler = [Tespit(sinif=SINIF_TIR, kutu=kutu, takip_id=2)]
    hat._forklift_siniflandir(tir_kare, tespitler, model)
    assert tespitler[0].sinif == SINIF_TIR

    # Model yokken sınıf asla değişmez (sahte karar üretilmez)
    modelsiz = ForkliftSiniflandirici(test_ayarlari.kok_dizin / "olmayan-klasor")
    tespitler = [Tespit(sinif=SINIF_TIR, kutu=kutu, takip_id=3)]
    hat._forklift_siniflandir(forklift_kare, tespitler, modelsiz)
    assert tespitler[0].sinif == SINIF_TIR


def test_egitim_dugmesi_sonucu_sayfada_gosterir(istemci, test_ayarlari):
    """Web akışı: veri yokken düğme dürüst bir açıklama sayfası döndürür."""
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
    finally:
        baglanti.close()
    yanit = istemci.post("/forklift/egit")
    assert yanit.status_code == 200
    assert "Eğitim çalıştırılamadı" in yanit.text
    assert "etiketli kare gerekli" in yanit.text

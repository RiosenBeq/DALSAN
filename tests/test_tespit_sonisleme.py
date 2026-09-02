"""Tespit son-işleme testleri: sınıf farkındalıklı seçim, sınıf başına eşik,
en küçük kutu süzgeci ve NMS. Model DOSYASI GEREKMEZ — saf matematik sınanır.

Neden önemli: bu katman yanlışsa sistem sessizce insan kaçırır ya da gölgeyi
forklift sanar. Kamerasız test edilebilen tek tespit katmanı burasıdır.
"""

from __future__ import annotations

import numpy as np

from app.analiz.tespit import MODEL_SINIF_ESLEME, Tespitci


def _tespitci(guven=0.35, insan_guven=0.28, nms=0.45, en_kucuk=12) -> Tespitci:
    """Model yüklemeden yalnızca son-işleme alanları kurulmuş bir Tespitci."""
    t = Tespitci.__new__(Tespitci)
    t._girdi_boyu = 416
    t.guven_esigi = guven
    t.insan_guven_esigi = insan_guven
    t.nms_esigi = nms
    t.en_kucuk_kenar_px = en_kucuk
    return t


def _ham_cikti(satirlar: list[tuple[float, float, float, float, float, dict[int, float]]]):
    """YOLOX ham çıktısı üretir: (cx, cy, w, h, nesnelik, {sinif: skor}).

    Kutular ızgara açılımından SONRAKİ piksel değerleridir; testte ızgarayı
    etkisiz kılmak için ilk satır (stride 8, grid 0,0) kullanılır.
    """
    cikti = np.zeros((len(satirlar), 85), dtype=np.float32)
    for i, (cx, cy, w, h, nesnelik, siniflar) in enumerate(satirlar):
        # ızgara (0,0) ve stride 8 için: (raw + 0) * 8 = cx  →  raw = cx / 8
        cikti[i, 0] = cx / 8.0
        cikti[i, 1] = cy / 8.0
        cikti[i, 2] = np.log(w / 8.0)
        cikti[i, 3] = np.log(h / 8.0)
        cikti[i, 4] = nesnelik
        for sinif, skor in siniflar.items():
            cikti[i, 5 + sinif] = skor
    return cikti


def _tek_satir_cikti(satir):
    """Tek tespit + kalan tüm ızgara noktaları boş."""
    toplam = sum((416 // adim) ** 2 for adim in (8, 16, 32))
    cikti = np.zeros((toplam, 85), dtype=np.float32)
    ham = _ham_cikti([satir])
    cikti[0] = ham[0]
    return cikti


def test_insan_daha_dusuk_esikle_gecer():
    """0.30 güvenli bir insan, genel eşik 0.35 iken bile tespit edilmeli."""
    t = _tespitci(guven=0.35, insan_guven=0.28)
    cikti = _tek_satir_cikti((100, 100, 40, 90, 1.0, {0: 0.30}))
    kutular, guvenler, adlar = t._son_isle(cikti, 1.0, 640, 480)
    assert list(adlar) == ["person"], (kutular, guvenler)
    assert 0.29 < guvenler[0] < 0.31


def test_araca_genel_esik_uygulanir():
    """Aynı 0.30 güven bir araçta yetmez: araçta yanlış alarm daha maliyetli."""
    t = _tespitci(guven=0.35, insan_guven=0.28)
    cikti = _tek_satir_cikti((100, 100, 60, 60, 1.0, {7: 0.30}))
    _, _, adlar = t._son_isle(cikti, 1.0, 640, 480)
    assert list(adlar) == []


def test_ilgisiz_sinif_baskin_olsa_bile_insan_kaybolmaz():
    """ESKİ HATA: 80 sınıf üzerinde argmax alınıyordu; 'sırt çantası' 0.40 ile
    'insan' 0.35'i bastırınca insan TAMAMEN düşüyordu. Sahada kaçırılan insan."""
    t = _tespitci(guven=0.35, insan_guven=0.28)
    # 24 = backpack (ilgilenmediğimiz sınıf), skoru insandan yüksek
    cikti = _tek_satir_cikti((100, 100, 40, 90, 1.0, {0: 0.35, 24: 0.80}))
    _, _, adlar = t._son_isle(cikti, 1.0, 640, 480)
    assert list(adlar) == ["person"]


def test_cok_kucuk_kutu_elenir():
    """Uzaktaki birkaç piksellik gürültü insan sanılıp yanlış alarm üretmemeli."""
    t = _tespitci(en_kucuk=12)
    cikti = _tek_satir_cikti((100, 100, 6, 8, 1.0, {0: 0.90}))
    _, _, adlar = t._son_isle(cikti, 1.0, 640, 480)
    assert list(adlar) == []


def test_en_kucuk_kenar_ayarlanabilir():
    t = _tespitci(en_kucuk=4)
    cikti = _tek_satir_cikti((100, 100, 6, 8, 1.0, {0: 0.90}))
    _, _, adlar = t._son_isle(cikti, 1.0, 640, 480)
    assert list(adlar) == ["person"]


def test_ayni_yerdeki_insan_ve_arac_birbirini_bastirmaz():
    """Forkliftin YANINDAKİ insan, tam da uyarı üretilmesi gereken durumdur;
    NMS sınıf farkındalıklı olmazsa biri diğerini yutardı."""
    t = _tespitci(guven=0.30, insan_guven=0.25)
    toplam = sum((416 // adim) ** 2 for adim in (8, 16, 32))
    cikti = np.zeros((toplam, 85), dtype=np.float32)
    ham = _ham_cikti(
        [
            (200, 200, 80, 160, 1.0, {0: 0.80}),  # insan
            (205, 205, 90, 150, 1.0, {7: 0.85}),  # neredeyse aynı yerde araç
        ]
    )
    cikti[0], cikti[1] = ham[0], ham[1]
    _, _, adlar = t._son_isle(cikti, 1.0, 640, 480)
    assert sorted(adlar) == ["person", "truck"]


def test_ayni_sinifta_ust_uste_kutular_birlesir():
    t = _tespitci(guven=0.30, insan_guven=0.25, nms=0.45)
    toplam = sum((416 // adim) ** 2 for adim in (8, 16, 32))
    cikti = np.zeros((toplam, 85), dtype=np.float32)
    ham = _ham_cikti(
        [
            (200, 200, 80, 160, 1.0, {0: 0.80}),
            (203, 202, 82, 158, 1.0, {0: 0.75}),  # aynı insanın ikinci kutusu
        ]
    )
    cikti[0], cikti[1] = ham[0], ham[1]
    _, _, adlar = t._son_isle(cikti, 1.0, 640, 480)
    assert list(adlar) == ["person"]


def test_bos_cikti_hata_vermez():
    t = _tespitci()
    toplam = sum((416 // adim) ** 2 for adim in (8, 16, 32))
    kutular, guvenler, adlar = t._son_isle(np.zeros((toplam, 85), np.float32), 1.0, 640, 480)
    assert len(kutular) == 0 and len(guvenler) == 0 and len(adlar) == 0


def test_sinif_eslemesi_yalnizca_bilinen_siniflari_uretir():
    """Eşleme tablosu tek kaynaktır; buradan çıkan her ad kural motorunun bildiği
    bir sınıf olmalı (aksi halde kurallar sessizce eşleşmez)."""
    from app.rules.tipler import SINIF_INSAN, SINIF_TIR

    assert set(MODEL_SINIF_ESLEME.values()) <= {SINIF_INSAN, SINIF_TIR}

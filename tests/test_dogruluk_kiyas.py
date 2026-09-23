"""Tespit doğruluk takımının metrikleri (docs/17 §14; tests/dogruluk_kiyas).

Takımın kendisi saha verisiyle elle koşulur; burada yalnız hesabı sınanır:
yanlış bir AP formülü "hedef tuttu" diye yanlış bir kabul üretirdi.
"""

from __future__ import annotations

import pytest

from tests.dogruluk_kiyas import etiket
from tests.dogruluk_kiyas.olcum import Kutu, iou, sinif_olcumu

A = (0.0, 0.0, 10.0, 10.0)
B = (100.0, 100.0, 110.0, 110.0)


def test_iou():
    assert iou(A, A) == 1.0
    assert iou(A, B) == 0.0
    assert iou(A, (5.0, 0.0, 15.0, 10.0)) == pytest.approx(50 / 150)


def test_kusursuz_tahmin_recall_ve_ap_bir():
    gercek = [[Kutu("person", A), Kutu("person", B)]]
    tahmin = [[Kutu("person", A, 0.9), Kutu("person", B, 0.8)]]
    s = sinif_olcumu(gercek, tahmin, "person")
    assert (s["tp"], s["fp"], s["fn"]) == (2, 0, 0)
    assert s["recall"] == s["precision"] == s["ap50"] == 1.0


def test_kacan_kutu_ve_ikinci_kutu_yanlis_pozitif():
    """Aynı kişiye ikinci kutu doğru sayılmaz; kaçan kutu recall'u düşürür."""
    gercek = [[Kutu("person", A), Kutu("person", B)]]
    tahmin = [[Kutu("person", A, 0.9), Kutu("person", A, 0.8)]]
    s = sinif_olcumu(gercek, tahmin, "person")
    assert (s["tp"], s["fp"], s["fn"]) == (1, 1, 1)
    assert s["recall"] == 0.5 and s["precision"] == 0.5


def test_ap_her_nokta_enterpolasyonu():
    """Sıra: doğru (0,9), yanlış (0,8), doğru (0,7); 2 gerçek kutu.
    Eğri: R 0,5 → P 1; R 1 → P 2/3. AP = 0,5 × 1 + 0,5 × 2/3."""
    gercek = [[Kutu("truck", A)], [Kutu("truck", B)]]
    tahmin = [
        [Kutu("truck", A, 0.9), Kutu("truck", (50.0, 50.0, 60.0, 60.0), 0.8)],
        [Kutu("truck", B, 0.7)],
    ]
    s = sinif_olcumu(gercek, tahmin, "truck")
    assert s["ap50"] == pytest.approx(0.5 + 0.5 * 2 / 3)


def test_tahmin_yoksa_recall_ve_ap_sifir():
    s = sinif_olcumu([[Kutu("person", A)]], [[]], "person")
    assert s["recall"] == 0.0 and s["ap50"] == 0.0 and s["precision"] is None
    assert isinstance(s["ap50"], float)


def test_gercek_kutu_yoksa_olculmedi():
    s = sinif_olcumu([[]], [[Kutu("forklift", A, 0.9)]], "forklift")
    assert s["recall"] is None and s["ap50"] is None and s["fp"] == 1


def test_baska_karedeki_kutuyla_eslesmez():
    gercek = [[Kutu("person", A)], []]
    tahmin = [[], [Kutu("person", A, 0.9)]]
    s = sinif_olcumu(gercek, tahmin, "person")
    assert (s["tp"], s["fp"], s["fn"]) == (0, 1, 1)


def test_yolo_etiketi_piksele_cevrilir(tmp_path):
    (tmp_path / "siniflar.txt").write_text("person\ncar=truck\n", encoding="utf-8")
    adlar = etiket.sinif_adlari(tmp_path)
    assert adlar == ["person", "truck"]
    kutular = etiket.yolo_satirlarini_oku("0 0.5 0.5 0.2 0.4\n1 0.1 0.1 0.2 0.2\n", adlar, 100, 50)
    assert kutular[0] == Kutu("person", (40.0, 15.0, 60.0, 35.0))
    assert kutular[1].sinif == "truck"

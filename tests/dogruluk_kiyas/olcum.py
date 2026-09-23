"""Doğruluk metrikleri (saf; görüntü ya da model bilmez).

Eşleştirme PASCAL VOC usulüdür: tahminler güvene göre sıralanır, her tahmin
aynı karedeki henüz eşleşmemiş en yüksek IoU'lu gerçek kutuya bağlanır; IoU
eşiğin altındaysa ya da o gerçek kutu zaten alındıysa yanlış pozitiftir
(aynı kişiye ikinci kutu doğru sayılmaz). AP, hassasiyet eğrisinin "her nokta"
enterpolasyonuyla alanıdır (VOC 2010 sonrası; COCO'nun 101 noktası değil).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Kutu:
    sinif: str
    kutu: tuple[float, float, float, float]  # x1, y1, x2, y2 (piksel)
    guven: float = 1.0


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    kesisim = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    alan_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    alan_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    birlesim = alan_a + alan_b - kesisim
    return kesisim / birlesim if birlesim > 0 else 0.0


def sinif_olcumu(
    gercekler: list[list[Kutu]], tahminler: list[list[Kutu]], sinif: str, iou_esigi: float = 0.5
) -> dict:
    """Bir sınıfın ölçümü. `gercekler[i]` ve `tahminler[i]` aynı karedir.

    Döner: n_gercek, n_tahmin, tp, fp, fn, recall, precision, ap50. Gerçek kutu
    yoksa recall ve AP tanımsızdır (None): "ölçülmedi" "%0" değildir.
    """
    if len(gercekler) != len(tahminler):
        raise ValueError("gerçek ve tahmin listeleri aynı karelerden oluşmalı")
    gercek_kutular = [[g.kutu for g in kare if g.sinif == sinif] for kare in gercekler]
    n_gercek = sum(len(k) for k in gercek_kutular)
    sirali = sorted(
        (
            (t.guven, kare_no, t.kutu)
            for kare_no, kare in enumerate(tahminler)
            for t in kare
            if t.sinif == sinif
        ),
        key=lambda x: -x[0],
    )
    alinan = [[False] * len(k) for k in gercek_kutular]
    isaretler: list[bool] = []
    for _, kare_no, kutu in sirali:
        en_iyi, en_iyi_no = 0.0, -1
        for no, gercek in enumerate(gercek_kutular[kare_no]):
            deger = iou(kutu, gercek)
            if deger > en_iyi:
                en_iyi, en_iyi_no = deger, no
        if en_iyi >= iou_esigi and not alinan[kare_no][en_iyi_no]:
            alinan[kare_no][en_iyi_no] = True
            isaretler.append(True)
        else:
            isaretler.append(False)
    tp = sum(isaretler)
    fp = len(isaretler) - tp
    return {
        "sinif": sinif,
        "n_gercek": n_gercek,
        "n_tahmin": len(isaretler),
        "tp": tp,
        "fp": fp,
        "fn": n_gercek - tp,
        "recall": tp / n_gercek if n_gercek else None,
        "precision": tp / len(isaretler) if isaretler else None,
        "ap50": _ortalama_hassasiyet(isaretler, n_gercek) if n_gercek else None,
    }


def _ortalama_hassasiyet(isaretler: list[bool], n_gercek: int) -> float:
    """Güvene göre sıralı TP/FP işaretlerinden her-nokta enterpolasyonlu AP."""
    recall, precision = [0.0], [1.0]
    tp = fp = 0
    for dogru in isaretler:
        tp += dogru
        fp += not dogru
        recall.append(tp / n_gercek)
        precision.append(tp / (tp + fp))
    # Enterpolasyon: her recall düzeyinde o düzey ve sonrasının en iyi hassasiyeti
    for i in range(len(precision) - 2, -1, -1):
        precision[i] = max(precision[i], precision[i + 1])
    return float(
        sum(
            (recall[i] - recall[i - 1]) * precision[i]
            for i in range(1, len(recall))
            if recall[i] > recall[i - 1]
        )
    )

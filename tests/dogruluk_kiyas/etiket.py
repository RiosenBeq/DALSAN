"""Etiketli kare klasörünü okur (YOLO dışa aktarım biçimi).

Klasör düzeni (CVAT, Label Studio ve Roboflow'un "YOLO" dışa aktarımı):

    <klasör>/siniflar.txt        her satır bir sınıf adı; sıra = sınıf numarası
    <klasör>/<ad>.jpg|.png       saha karesi
    <klasör>/<ad>.txt            her satır: <sınıf no> <cx> <cy> <g> <y> (0..1)

`siniflar.txt` satırı "etiket=sistem" biçiminde de yazılabilir: etiketçi
"car" ya da "bus" işaretlediyse ama sistem bunları "truck" diye raporluyorsa
`car=truck` yazılır (analiz/tespit.py MODEL_SINIF_ESLEME). Sistemin tanımadığı
sınıf ölçüme girmez ve raporda sayısıyla yazılır.
"""

from __future__ import annotations

from pathlib import Path

from .olcum import Kutu

RESIM_UZANTILARI = (".jpg", ".jpeg", ".png")


def sinif_adlari(klasor: Path) -> list[str]:
    """siniflar.txt → sınıf numarası sırasıyla sistem sınıf adları."""
    dosya = klasor / "siniflar.txt"
    if not dosya.is_file():
        raise FileNotFoundError(f"{dosya} yok: her satıra bir sınıf adı yazın")
    adlar = []
    for satir in dosya.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if satir:
            adlar.append(satir.split("=", 1)[-1].strip())
    return adlar


def yolo_satirlarini_oku(metin: str, adlar: list[str], genislik: int, yukseklik: int) -> list[Kutu]:
    """YOLO etiket dosyasının içeriği → piksel koordinatlı gerçek kutular."""
    kutular = []
    for satir in metin.splitlines():
        parca = satir.split()
        if len(parca) < 5:
            continue
        no = int(parca[0])
        cx, cy, g, y = (float(p) for p in parca[1:5])
        kutular.append(
            Kutu(
                sinif=adlar[no] if 0 <= no < len(adlar) else f"#{no}",
                kutu=(
                    (cx - g / 2) * genislik,
                    (cy - y / 2) * yukseklik,
                    (cx + g / 2) * genislik,
                    (cy + y / 2) * yukseklik,
                ),
            )
        )
    return kutular


def kareler(klasor: Path) -> list[tuple[Path, Path]]:
    """(resim, etiket) çiftleri; etiketi olmayan kare "içinde nesne yok" sayılır."""
    return [
        (resim, resim.with_suffix(".txt"))
        for resim in sorted(klasor.iterdir())
        if resim.suffix.lower() in RESIM_UZANTILARI
    ]

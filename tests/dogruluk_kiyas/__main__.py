"""Tespit doğruluğunu etiketli saha karelerinde ölçer ve tabloyu basar.

Çalıştırma (depo kökünden):

    .venv/bin/python -m tests.dogruluk_kiyas --klasor veri/dogruluk
    .venv/bin/python -m tests.dogruluk_kiyas --klasor veri/dogruluk --json sonuc.json

Klasör biçimi tests/dogruluk_kiyas/etiket.py'dedir (YOLO dışa aktarımı).
Motoru DEĞİŞTİRMEZ; sahada çalışan `Tespitci`'yi .env'deki eşiklerle çağırır.
Hedefler GÖREV §4.8'den: insan recall ≥ 0,95; forklift ve tır AP50 ≥ 0,90.
Ölçüm yalnız o karelere aittir: kaç kare, kaç kutu olduğu her satırda yazar;
az kutuyla çıkan yüzde, "hedef tuttu" demek değildir.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_KOK = Path(__file__).resolve().parents[2]
if str(_KOK / "backend") not in sys.path:
    sys.path.insert(0, str(_KOK / "backend"))

import cv2  # noqa: E402

from app.analiz.tespit import Tespitci  # noqa: E402
from app.ayarlar import ayarlari_yukle  # noqa: E402
from app.rules.tipler import TANINAN_SINIFLAR  # noqa: E402

from . import etiket, olcum  # noqa: E402

# GÖREV §4.8 hedefleri: (ölçüt, alt sınır)
HEDEFLER = {"person": ("recall", 0.95), "forklift": ("ap50", 0.90), "truck": ("ap50", 0.90)}
# Bu sayının altında kutu varsa satır "az örnek" diye işaretlenir
AZ_ORNEK = 50


def _yuzde(deger: float | None) -> str:
    return "ölçülmedi" if deger is None else f"%{deger * 100:.1f}"


def main() -> int:
    ayristirici = argparse.ArgumentParser(
        prog="python -m tests.dogruluk_kiyas",
        description="Etiketli saha karelerinde tespit recall ve AP50 ölçer.",
    )
    ayristirici.add_argument("--klasor", required=True, type=Path, help="Etiketli kareler")
    ayristirici.add_argument("--iou", type=float, default=0.5, help="Eşleşme IoU eşiği")
    ayristirici.add_argument("--json", type=Path, help="Ham sonuçların yazılacağı dosya")
    secenekler = ayristirici.parse_args()

    ayarlar = ayarlari_yukle(_KOK)
    tespitci = Tespitci(
        model_dosyasi=ayarlar.model_dosyasi,
        cihaz=ayarlar.cikarim_cihazi,
        guven_esigi=ayarlar.tespit_guven_esigi,
        insan_guven_esigi=ayarlar.tespit_insan_guven_esigi,
        nms_esigi=ayarlar.tespit_nms_esigi,
        en_kucuk_kenar_px=ayarlar.tespit_en_kucuk_kenar_px,
    )
    adlar = etiket.sinif_adlari(secenekler.klasor)
    gercekler: list[list[olcum.Kutu]] = []
    tahminler: list[list[olcum.Kutu]] = []
    tanimayan: dict[str, int] = {}
    baslangic = time.time()
    for resim, etiket_dosyasi in etiket.kareler(secenekler.klasor):
        kare = cv2.imread(str(resim))
        if kare is None:
            print(f"okunamadı, atlandı: {resim.name}")
            continue
        yukseklik, genislik = kare.shape[:2]
        metin = etiket_dosyasi.read_text(encoding="utf-8") if etiket_dosyasi.is_file() else ""
        kutular = etiket.yolo_satirlarini_oku(metin, adlar, genislik, yukseklik)
        for k in kutular:
            if k.sinif not in TANINAN_SINIFLAR:
                tanimayan[k.sinif] = tanimayan.get(k.sinif, 0) + 1
        gercekler.append([k for k in kutular if k.sinif in TANINAN_SINIFLAR])
        xyxy, guvenler, siniflar = tespitci.tespit_et(kare)
        tahminler.append(
            [
                olcum.Kutu(sinif=str(s), kutu=tuple(float(v) for v in b), guven=float(g))
                for b, g, s in zip(xyxy, guvenler, siniflar, strict=True)
            ]
        )

    sonuclar = [
        olcum.sinif_olcumu(gercekler, tahminler, sinif, secenekler.iou)
        for sinif in TANINAN_SINIFLAR
    ]
    print(
        f"Tespit doğruluğu - {len(gercekler)} kare, model {ayarlar.model_dosyasi.name}, "
        f"IoU ≥ {secenekler.iou:g}, {time.time() - baslangic:.0f} sn"
    )
    print(
        f"{'sınıf':10} {'kutu':>6} {'tahmin':>7} {'recall':>10} {'precision':>10} "
        f"{'AP50':>10}  hedef"
    )
    for s in sonuclar:
        hedef = HEDEFLER.get(s["sinif"])
        hedef_metni = ""
        if hedef:
            olcut, sinir = hedef
            deger = s[olcut]
            durum = "ölçülmedi" if deger is None else ("tuttu" if deger >= sinir else "tutmadı")
            hedef_metni = f"{olcut} ≥ {sinir:g}: {durum}"
            if s["n_gercek"] and s["n_gercek"] < AZ_ORNEK:
                hedef_metni += f" (az örnek: {s['n_gercek']} kutu)"
        print(
            f"{s['sinif']:10} {s['n_gercek']:>6} {s['n_tahmin']:>7} {_yuzde(s['recall']):>10} "
            f"{_yuzde(s['precision']):>10} {_yuzde(s['ap50']):>10}  {hedef_metni}"
        )
    if tanimayan:
        print(
            "Sistemin tanımadığı etiketler (ölçüme girmedi): "
            + ", ".join(f"{ad} {sayi}" for ad, sayi in sorted(tanimayan.items()))
        )
    if secenekler.json:
        secenekler.json.write_text(
            json.dumps(
                {
                    "kare": len(gercekler),
                    "model": ayarlar.model_dosyasi.name,
                    "iou": secenekler.iou,
                    "siniflar": sonuclar,
                    "tanimayan": tanimayan,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

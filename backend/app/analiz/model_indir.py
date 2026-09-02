"""Tespit modelini ilk açılışta otomatik indirir (models/indir.sh ile aynı kaynak).

Model ağırlıkları depoya girmez (CLAUDE.md §7). Kullanıcı terminal komutu
çalıştırmasın diye (CLAUDE.md §8) eksik model, sistem açılırken BİR KEZ
indirilir. Yalnızca YOLOX'un resmi yayın dosyaları bilinir; başka bir ad
verilmişse indirilmez, kullanıcıya dosyayı kendisinin koyması söylenir.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from app.hatalar import DalsanHata

# ADR-002: Apache-2.0 lisanslı YOLOX resmi yayınları (models/indir.sh ile aynı)
_YAYIN_ADRESI = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/"
BILINEN_MODELLER = ("yolox_tiny.onnx", "yolox_s.onnx")


class ModelIndirmeHatasi(DalsanHata):
    """İnternet yok / adres erişilemez — sistem tespitsiz devam eder."""


def indirilebilir_mi(model_dosyasi: Path) -> bool:
    return model_dosyasi.name in BILINEN_MODELLER


def modeli_indir(model_dosyasi: Path, ilerleme: Callable[[int, int], None] | None = None) -> None:
    """Modeli `.part` dosyasına indirip bitince adını değiştirir — yarım
    kalan indirme asla 'geçerli model' sanılmaz."""
    if not indirilebilir_mi(model_dosyasi):
        raise ModelIndirmeHatasi(
            f"{model_dosyasi.name} otomatik indirilemez (bilinen modeller: "
            f"{', '.join(BILINEN_MODELLER)}). Dosyayı models/ klasörüne kendiniz koyun "
            "ya da .env dosyasında MODEL_DOSYASI=models/yolox_tiny.onnx yazın."
        )
    adres = _YAYIN_ADRESI + model_dosyasi.name
    gecici = model_dosyasi.with_suffix(model_dosyasi.suffix + ".part")
    try:
        model_dosyasi.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(adres, timeout=30) as yanit, gecici.open("wb") as hedef:
            toplam = int(yanit.headers.get("Content-Length") or 0)
            inen = 0
            while True:
                parca = yanit.read(1024 * 256)
                if not parca:
                    break
                hedef.write(parca)
                inen += len(parca)
                if ilerleme is not None:
                    ilerleme(inen, toplam)
        if gecici.stat().st_size < 1024 * 1024:
            raise ModelIndirmeHatasi(
                f"İndirilen model dosyası beklenmedik biçimde küçük ({gecici.stat().st_size} bayt)."
            )
        gecici.replace(model_dosyasi)
    except (urllib.error.URLError, TimeoutError, OSError) as hata:
        gecici.unlink(missing_ok=True)
        raise ModelIndirmeHatasi(
            f"Tespit modeli indirilemedi ({adres}): {hata}. "
            "İnternet bağlantısını kontrol edip sistemi yeniden başlatın; "
            "ya da dosyayı models/ klasörüne elle koyun (bash models/indir.sh)."
        ) from hata

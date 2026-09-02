"""rules/ saflık bekçisi (CLAUDE.md §6).

rules/ içindeki bir dosya cv2, torch, ultralytics, sqlite3 veya fastapi'ye
ulaşırsa bu test KIRMIZI olur. Kural mantığının kamerasız, sahte veriyle,
saniyeler içinde test edilebilir kalmasının tek güvencesi budur.

Dört sızma yolu birden denetlenir:
1. Doğrudan import (import cv2 / from torch import ...)
2. Dinamik import (importlib.import_module("cv2"), __import__("sqlite3"))
3. Dolaylı import: app.rules dışındaki app modülleri (ör. app.veritabani
   sqlite3'ü, app.web fastapi'yi içeri taşır) — rules/ yalnızca kendi
   paketinden import yapabilir.
4. Göreli import: `from ..veritabani import baglanti_ac` ve `from .. import web`
   de 3. maddedeki sızmayı yapar; dosyanın paketine göre mutlak ada çevrilip
   aynı ölçütle denetlenir.
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
BACKEND_DIZINI = KOK / "backend"
RULES_DIZINI = BACKEND_DIZINI / "app" / "rules"

# importlib de yasak: saf kural mantığında dinamik import'a yer yok ve
# yasaklı modüllerin "tembel yükleme" ile arka kapıdan girmesini önler.
YASAKLI_MODULLER = {"cv2", "torch", "torchvision", "ultralytics", "sqlite3", "fastapi", "importlib"}

# app.hatalar İZİNLİ: modül seviyesinde hiçbir şey import etmez (FastAPI importu
# bilerek fonksiyon içindedir) — hata sınıflarının ortak olması için gerekli.
IZINLI_APP_MODULLERI = ("app.rules", "app.hatalar")


def _paket_adi(dosya: Path) -> str:
    """backend/app/rules/mesafe.py → app.rules

    Göreli import'ların hangi pakete göre çözüleceğini verir. `__init__.py`
    için de doğru sonucu üretir: app/rules/__init__.py → app.rules.
    """
    goreli = dosya.relative_to(BACKEND_DIZINI)
    return ".".join(goreli.parts[:-1])


def _kaynak_ihlalleri(kaynak: str, paket: str = "app.rules") -> set[str]:
    """Verilen Python kaynağındaki saflık ihlallerini döndürür.

    `paket`, göreli import'ların çözüleceği paket adıdır (dosyanın kendi paketi).
    """
    agac = ast.parse(kaynak)
    ihlaller: set[str] = set()

    def _modul_denetle(modul_adi: str) -> None:
        kok_ad = modul_adi.split(".")[0]
        if kok_ad in YASAKLI_MODULLER:
            ihlaller.add(kok_ad)
        # Dolaylı sızma: izinli listede olmayan her app modülü yasak
        # (app.veritabani sqlite3'ü, app.web fastapi'yi içeri taşırdı).
        if kok_ad == "app" and not modul_adi.startswith(IZINLI_APP_MODULLERI):
            ihlaller.add(modul_adi)

    def _goreli_denetle(seviye: int, modul: str | None, adlar: list[str]) -> None:
        """Göreli import'u mutlak modül adına çevirip aynı ölçütle denetler.

        app.rules içinde: `from ..veritabani import x` → app.veritabani (yasak),
        `from .geometri import y` → app.rules.geometri (izinli).
        """
        parcalar = paket.split(".") if paket else []
        cikilan = seviye - 1  # `.` kendi paketi, `..` bir üstü, ...
        if cikilan >= len(parcalar):
            ihlaller.add(f"paket kökünün dışına çıkan göreli import ({'.' * seviye}{modul or ''})")
            return
        taban = parcalar[: len(parcalar) - cikilan]
        if modul:
            _modul_denetle(".".join([*taban, modul]))
            return
        # `from .. import veritabani` — içeri alınan adlar alt modül adıdır
        for ad in adlar:
            _modul_denetle(".".join([*taban, ad]))

    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            for ad in dugum.names:
                _modul_denetle(ad.name)
        elif isinstance(dugum, ast.ImportFrom):
            if dugum.level == 0:
                if dugum.module:
                    _modul_denetle(dugum.module)
            else:
                _goreli_denetle(dugum.level, dugum.module, [ad.name for ad in dugum.names])
        elif isinstance(dugum, ast.Call):
            # __import__("x") ve <her şey>.import_module("x") çağrıları
            hedef = dugum.func
            dinamik = (isinstance(hedef, ast.Name) and hedef.id == "__import__") or (
                isinstance(hedef, ast.Attribute) and hedef.attr == "import_module"
            )
            if dinamik and dugum.args:
                ilk = dugum.args[0]
                if isinstance(ilk, ast.Constant) and isinstance(ilk.value, str):
                    _modul_denetle(ilk.value)
    return ihlaller


def test_rules_klasoru_var():
    assert RULES_DIZINI.is_dir(), f"rules/ klasörü bulunamadı: {RULES_DIZINI}"


def test_rules_yasakli_modullere_ulasmiyor():
    ihlaller = []
    for dosya in sorted(RULES_DIZINI.rglob("*.py")):
        bulunanlar = _kaynak_ihlalleri(dosya.read_text(encoding="utf-8"), _paket_adi(dosya))
        if bulunanlar:
            ihlaller.append(f"{dosya.relative_to(KOK)} → {', '.join(sorted(bulunanlar))}")
    assert not ihlaller, (
        "rules/ SAF kalmalı (CLAUDE.md §6) — yasaklı erişim bulundu:\n" + "\n".join(ihlaller)
    )


# --- Bekçinin kendisinin testleri: aşağıdaki kalıpların hepsi yakalanmalı ---


def test_bekci_dogrudan_importu_yakaliyor():
    assert "cv2" in _kaynak_ihlalleri("import cv2 as goruntu")
    assert "torch" in _kaynak_ihlalleri("def f():\n    from torch.nn import functional")
    assert "sqlite3" in _kaynak_ihlalleri("import sqlite3")


def test_bekci_dinamik_importu_yakaliyor():
    assert "importlib" in _kaynak_ihlalleri("import importlib")
    assert "cv2" in _kaynak_ihlalleri("x = importlib.import_module('cv2')")
    assert "sqlite3" in _kaynak_ihlalleri("db = __import__('sqlite3')")


def test_bekci_dolayli_app_importunu_yakaliyor():
    # app.veritabani sqlite3'ü içeri taşırdı — rules/ yalnız kendi paketini kullanabilir
    assert "app.veritabani" in _kaynak_ihlalleri("from app.veritabani import baglanti_ac")
    assert "app.web.rotalar" in _kaynak_ihlalleri("from app.web.rotalar import router")
    assert not _kaynak_ihlalleri("from app.rules.geometri import nokta_iceride_mi")
    # app.hatalar izinlidir: modül seviyesinde framework importu yoktur
    assert not _kaynak_ihlalleri("from app.hatalar import DalsanHata")


def test_bekci_goreli_importu_yakaliyor():
    # `from ..veritabani import ...` mutlak yazımıyla birebir aynı sızmadır
    assert "app.veritabani" in _kaynak_ihlalleri("from ..veritabani import baglanti_ac")
    assert "app.web.rotalar" in _kaynak_ihlalleri("from ..web.rotalar import router")
    # `from .. import veritabani` biçimi de aynı kapıyı açar
    assert "app.veritabani" in _kaynak_ihlalleri("from .. import veritabani")
    assert "app.analiz" in _kaynak_ihlalleri("from .. import analiz, hatalar")
    # Fonksiyon içine gizlenmiş göreli import de yakalanır
    assert "app.veritabani" in _kaynak_ihlalleri("def f():\n    from ..veritabani import ac")


def test_bekci_izinli_goreli_importa_ses_cikarmiyor():
    # Kendi paketi içinde göreli import serbesttir
    assert not _kaynak_ihlalleri("from .geometri import nokta_iceride_mi")
    assert not _kaynak_ihlalleri("from . import geometri")
    # app.hatalar göreli yazıldığında da izinlidir
    assert not _kaynak_ihlalleri("from ..hatalar import DalsanHata")


def test_bekci_paket_disina_cikan_goreli_importu_yakaliyor():
    # app.rules içinden `from ... import x` paket kökünü aşar — Python'da da hatadır
    assert _kaynak_ihlalleri("from ... import bir_sey")
    assert _kaynak_ihlalleri("from ...disarisi import bir_sey")


def test_bekci_alt_paketteki_goreli_importu_dogru_cozuyor():
    # backend/app/rules/alt/x.py → paket app.rules.alt; bir üstü hâlâ app.rules
    assert not _kaynak_ihlalleri("from ..geometri import oklid_mesafe", paket="app.rules.alt")
    assert "app.veritabani" in _kaynak_ihlalleri(
        "from ...veritabani import baglanti_ac", paket="app.rules.alt"
    )


def test_paket_adi_dosya_yolundan_cikariliyor():
    assert _paket_adi(RULES_DIZINI / "mesafe.py") == "app.rules"
    assert _paket_adi(RULES_DIZINI / "__init__.py") == "app.rules"
    assert _paket_adi(RULES_DIZINI / "alt" / "x.py") == "app.rules.alt"


def test_bekci_izinli_modullere_ses_cikarmiyor():
    assert not _kaynak_ihlalleri("import math\nfrom dataclasses import dataclass")

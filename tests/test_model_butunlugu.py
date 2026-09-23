"""Model bütünlüğü (docs/17 §10.5 R17): özeti tutmayan model kullanılmaz.

Model dosyası kendiliğinden internetten iner (analiz/model_indir.py) ya da
elle `bash models/indir.sh` ile indirilir. İkisi de dosyayı eskiden yalnızca
boyutuna bakıp kabul ediyordu: yolda değiştirilmiş ya da bozuk inmiş bir
model sessizce yüklenirdi. Özetler üç yerde durur ve AYNI kalmalıdır:
model_indir.BILINEN_MODELLER, models/SHA256SUMS (indir.sh ve Dockerfile).
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from app.analiz import model_indir
from app.analiz.model_indir import BILINEN_MODELLER, ModelIndirmeHatasi, modeli_indir

KOK = Path(__file__).resolve().parents[1]
OZETLER = KOK / "models" / "SHA256SUMS"


def _ozet_dosyasi() -> dict[str, str]:
    satirlar = OZETLER.read_text(encoding="utf-8").splitlines()
    return {ad: ozet for ozet, ad in (satir.split("  ", 1) for satir in satirlar if satir)}


def test_uc_kaynaktaki_ozetler_ayni():
    assert _ozet_dosyasi() == BILINEN_MODELLER
    assert all(len(ozet) == 64 for ozet in BILINEN_MODELLER.values())
    betik = (KOK / "models" / "indir.sh").read_text(encoding="utf-8")
    assert "SHA256SUMS" in betik
    for ad in BILINEN_MODELLER:
        assert f"indir {ad}" in betik, ad
    assert "sha256sum -c --ignore-missing SHA256SUMS" in (KOK / "Dockerfile").read_text(
        encoding="utf-8"
    )


# ------------------------------------------------- otomatik indirme (Python)


class _SahteYanit:
    def __init__(self, veri: bytes) -> None:
        self._akis = io.BytesIO(veri)
        self.headers = {"Content-Length": str(len(veri))}

    def read(self, boyut: int) -> bytes:
        return self._akis.read(boyut)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _sunucu(monkeypatch, veri: bytes) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _SahteYanit(veri))


def test_ozeti_tutmayan_indirme_kullanilmaz(tmp_path, monkeypatch):
    """Yolda değiştirilmiş dosya: boyutu tutsa bile kabul edilmez."""
    _sunucu(monkeypatch, b"x" * (2 * 1024 * 1024))
    hedef = tmp_path / "models" / "yolox_tiny.onnx"
    with pytest.raises(ModelIndirmeHatasi) as hata:
        modeli_indir(hedef)
    assert "doğrulanamadı" in hata.value.kullanici_mesaji
    assert "yolox" not in hata.value.kullanici_mesaji.lower()  # ekranda alt bileşen adı yok
    assert "SHA-256" in hata.value.teknik_ayrinti  # günlükte ayrıntı var
    assert not hedef.exists()
    assert not hedef.with_suffix(".onnx.part").exists()


def test_eksik_inen_dosya_da_kullanilmaz(tmp_path, monkeypatch):
    _sunucu(monkeypatch, b"")
    hedef = tmp_path / "models" / "yolox_s.onnx"
    with pytest.raises(ModelIndirmeHatasi):
        modeli_indir(hedef)
    assert not hedef.exists()


def test_ozeti_tutan_indirme_yerine_konur(tmp_path, monkeypatch):
    veri = b"gercek-model" * 1000
    monkeypatch.setitem(
        model_indir.BILINEN_MODELLER, "yolox_tiny.onnx", hashlib.sha256(veri).hexdigest()
    )
    _sunucu(monkeypatch, veri)
    hedef = tmp_path / "models" / "yolox_tiny.onnx"
    modeli_indir(hedef)
    assert hedef.read_bytes() == veri


# ------------------------------------------------- elle indirme (models/indir.sh)

bash_gerekli = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None or shutil.which("sha256sum") is None,
    reason="indir.sh bir bash betiğidir; Linux/Mac'te çalışır.",
)


def _betik_kur(tmp_path: Path, sunulan: bytes) -> tuple[Path, dict]:
    """indir.sh'i geçici klasöre kopyalar; `curl` sahtedir, `sunulan`ı yazar.

    SHA256SUMS'taki tiny satırı `sunulan`ın özetine çevrilir; böylece
    'doğru dosya' ve 'değiştirilmiş dosya' iki durumu da gerçek model
    indirmeden sınanır. s modeli zaten "var ve doğru" kurulur.
    """
    klasor = tmp_path / "models"
    klasor.mkdir()
    shutil.copy(KOK / "models" / "indir.sh", klasor / "indir.sh")
    s_verisi = b"s-model"
    (klasor / "yolox_s.onnx").write_bytes(s_verisi)
    (klasor / "SHA256SUMS").write_text(
        f"{hashlib.sha256(b'dogru-tiny').hexdigest()}  yolox_tiny.onnx\n"
        f"{hashlib.sha256(s_verisi).hexdigest()}  yolox_s.onnx\n",
        encoding="utf-8",
    )
    bin_klasoru = tmp_path / "bin"
    bin_klasoru.mkdir()
    (tmp_path / "sunulan").write_bytes(sunulan)
    sahte_curl = bin_klasoru / "curl"
    # Argümanlardaki '-o <dosya>' ile yazılacak yeri bulur.
    sahte_curl.write_text(
        '#!/bin/bash\nwhile [ $# -gt 0 ]; do [ "$1" = "-o" ] && cikti="$2"; shift; done\n'
        f'cat "{tmp_path / "sunulan"}" > "$cikti"\n',
        encoding="utf-8",
    )
    sahte_curl.chmod(0o755)
    ortam = {**os.environ, "PATH": f"{bin_klasoru}{os.pathsep}{os.environ['PATH']}"}
    return klasor, ortam


def _calistir(klasor: Path, ortam: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(klasor / "indir.sh")], env=ortam, capture_output=True, text=True, timeout=60
    )


@bash_gerekli
def test_betik_degistirilmis_dosyayi_reddeder(tmp_path):
    klasor, ortam = _betik_kur(tmp_path, b"degistirilmis-tiny")
    sonuc = _calistir(klasor, ortam)
    assert sonuc.returncode != 0
    assert "doğrulanamadı" in sonuc.stderr
    assert not (klasor / "yolox_tiny.onnx").exists()
    assert not (klasor / "yolox_tiny.onnx.part").exists()


@bash_gerekli
def test_betik_dogru_dosyayi_kabul_eder_ve_var_olani_dogrular(tmp_path):
    klasor, ortam = _betik_kur(tmp_path, b"dogru-tiny")
    sonuc = _calistir(klasor, ortam)
    assert sonuc.returncode == 0, sonuc.stderr
    assert (klasor / "yolox_tiny.onnx").read_bytes() == b"dogru-tiny"
    assert "yolox_tiny.onnx indirildi ve doğrulandı" in sonuc.stdout
    assert "yolox_s.onnx zaten var ve doğrulandı" in sonuc.stdout


@bash_gerekli
def test_betik_bozuk_eski_dosyayi_silmeden_kenara_alir(tmp_path):
    klasor, ortam = _betik_kur(tmp_path, b"dogru-tiny")
    (klasor / "yolox_tiny.onnx").write_bytes(b"bozuk-eski")
    sonuc = _calistir(klasor, ortam)
    assert sonuc.returncode == 0, sonuc.stderr
    assert (klasor / "yolox_tiny.onnx.eski").read_bytes() == b"bozuk-eski"
    assert (klasor / "yolox_tiny.onnx").read_bytes() == b"dogru-tiny"

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
        yer = model_indir.DALSAN_MODELLERI.get(ad)
        # DALSAN yayınındaki model yayındaki yeriyle, YOLOX modeli yalnız adıyla indirilir
        satir = f"indir {ad} {yer}\n" if yer else f"indir {ad}\n"
        assert satir in betik, ad
    assert set(model_indir.DALSAN_MODELLERI) <= set(BILINEN_MODELLER)
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


def test_forklift_modeli_dalsan_yayinindan_iner(tmp_path, monkeypatch):
    """Forklift modeli bu deponun kendi yayınındadır (egitim/forklift); adres
    etiketten kurulur, özet yine zorunludur. Hazır YOLOX modeli değişmez."""
    veri = b"forklift-model" * 1000
    ad = "nextgen_forklift_tiny_r0.onnx"
    monkeypatch.setitem(model_indir.BILINEN_MODELLER, ad, hashlib.sha256(veri).hexdigest())
    monkeypatch.setitem(model_indir.DALSAN_MODELLERI, ad, "forklift-r0/tiny-v1-k1.onnx")
    istenen = []

    def _ac(adres, **_):
        istenen.append(adres)
        return _SahteYanit(veri)

    monkeypatch.setattr(urllib.request, "urlopen", _ac)
    modeli_indir(tmp_path / "models" / ad)
    assert istenen == [
        "https://github.com/RiosenBeq/DALSAN/releases/download/forklift-r0/tiny-v1-k1.onnx"
    ]
    assert model_indir.indirme_adresi("yolox_tiny.onnx").startswith(
        "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/"
    )


def test_ozeti_tutan_indirme_yerine_konur(tmp_path, monkeypatch):
    veri = b"gercek-model" * 1000
    monkeypatch.setitem(
        model_indir.BILINEN_MODELLER, "yolox_tiny.onnx", hashlib.sha256(veri).hexdigest()
    )
    _sunucu(monkeypatch, veri)
    hedef = tmp_path / "models" / "yolox_tiny.onnx"
    modeli_indir(hedef)
    assert hedef.read_bytes() == veri


def test_forklift_modellerinin_tabani_bilinen_hazir_modeldir():
    """Kurulum listesi ve Ayarlar, forklift modelini insanı ve aracı onunla aynı
    tanıyan hazır modelin karşılığı olarak sunar: kayıt tutarlı olmalı."""
    for ad, taban in model_indir.FORKLIFT_TABANI.items():
        assert ad in model_indir.DALSAN_MODELLERI, ad  # bu deponun yayınından iner
        assert taban in BILINEN_MODELLER and taban not in model_indir.DALSAN_MODELLERI, ad
        assert taban not in model_indir.FORKLIFT_TABANI, ad


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
    # tiny dışındaki her bilinen model (s, forklift modelleri) "var ve doğru" kurulur
    satirlar = [f"{hashlib.sha256(b'dogru-tiny').hexdigest()}  yolox_tiny.onnx\n"]
    for ad in BILINEN_MODELLER:
        if ad == "yolox_tiny.onnx":
            continue
        verisi = f"{ad}-model".encode()
        (klasor / ad).write_bytes(verisi)
        satirlar.append(f"{hashlib.sha256(verisi).hexdigest()}  {ad}\n")
    (klasor / "SHA256SUMS").write_text("".join(satirlar), encoding="utf-8")
    bin_klasoru = tmp_path / "bin"
    bin_klasoru.mkdir()
    (tmp_path / "sunulan").write_bytes(sunulan)
    sahte_curl = bin_klasoru / "curl"
    # Argümanlardaki '-o <dosya>' ile yazılacak yeri bulur; istenen adresi
    # (son argüman) adresler dosyasına ekler.
    sahte_curl.write_text(
        "#!/bin/bash\nfor son; do :; done\n"
        f'echo "$son" >> "{tmp_path / "adresler"}"\n'
        'while [ $# -gt 0 ]; do [ "$1" = "-o" ] && cikti="$2"; shift; done\n'
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


@bash_gerekli
@pytest.mark.parametrize(("ad", "yer"), sorted(model_indir.DALSAN_MODELLERI.items()))
def test_betik_forklift_modelini_dalsan_yayinindan_indirir(tmp_path, ad, yer):
    """indir.sh ile uygulamanın otomatik indirmesi aynı adrese gider."""
    veri = b"forklift"
    klasor, ortam = _betik_kur(tmp_path, veri)
    (klasor / "yolox_tiny.onnx").write_bytes(b"dogru-tiny")  # yalnız forklift insin
    (klasor / ad).unlink()
    ozetler = (klasor / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    ozetler = [s for s in ozetler if not s.endswith(f"  {ad}")]
    ozetler.append(f"{hashlib.sha256(veri).hexdigest()}  {ad}")
    (klasor / "SHA256SUMS").write_text("\n".join(ozetler) + "\n", encoding="utf-8")
    sonuc = _calistir(klasor, ortam)
    adresler = (tmp_path / "adresler").read_text(encoding="utf-8").splitlines()
    assert model_indir.DALSAN_YAYINI + yer in adresler, sonuc.stdout + sonuc.stderr
    assert (klasor / ad).read_bytes() == veri

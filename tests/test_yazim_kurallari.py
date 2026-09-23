"""Yazım kuralı: çizgi işareti olarak yalnız düz tire (-) kullanılır.

Operatör kararı (23.09.2026, docs/17 §16 karar kaydı): kod, yorum, arayüz
metni, belge, günlük iletisi ve commit mesajı dahil sistemin HİÇBİR yerinde
uzun çizgi (U+2014), orta çizgi (U+2013), eksi işareti (U+2212) ya da benzeri
tipografik çizgi kullanılmaz; yerine ASCII tire yazılır. CLAUDE.md §7'deki
kuralın bekçisi bu testtir.

Yasak karakterler bu dosyada bilerek kaçış dizisiyle yazılır: dosyanın
kendisi de kurala uyar.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]

YASAK = {
    "\u2010": "tire (U+2010)",
    "\u2011": "bölünmez tire (U+2011)",
    "\u2012": "rakam çizgisi (U+2012)",
    "\u2013": "orta çizgi (U+2013)",
    "\u2014": "uzun çizgi (U+2014)",
    "\u2015": "yatay çubuk (U+2015)",
    "\u2212": "eksi işareti (U+2212)",
    "\u2e3a": "iki uzun çizgi (U+2E3A)",
    "\u2e3b": "üç uzun çizgi (U+2E3B)",
    "\ufe58": "küçük uzun çizgi (U+FE58)",
    "\ufe63": "küçük tire (U+FE63)",
    "\uff0d": "tam genişlikte tire (U+FF0D)",
}

# git yoksa taranmayacak klasörler: sanal ortam, kullanıcı verisi, önbellekler
_ATLANAN_KLASORLER = {
    ".git",
    ".venv",
    "venv",
    "veri",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "node_modules",
}
# Kullanıcının kendi ayar dosyası kaynak değildir (eski .env.example'dan kopya olabilir)
_ATLANAN_DOSYALAR = {".env"}


def _depo_dosyalari() -> list[Path]:
    """Depodaki dosyalar: git varsa izlenenler, yoksa klasör taraması."""
    if shutil.which("git") and (KOK / ".git").exists():
        cikti = subprocess.run(["git", "ls-files", "-z"], cwd=KOK, capture_output=True, check=False)
        if cikti.returncode == 0:
            return [KOK / ad for ad in cikti.stdout.decode("utf-8").split("\0") if ad]
    dosyalar = []
    for kok, klasorler, adlar in os.walk(KOK):
        klasorler[:] = [k for k in klasorler if k not in _ATLANAN_KLASORLER]
        dosyalar.extend(Path(kok) / ad for ad in adlar if ad not in _ATLANAN_DOSYALAR)
    return dosyalar


def test_sistemde_tipografik_cizgi_yok():
    ihlaller = []
    for yol in _depo_dosyalari():
        if not yol.is_file():
            continue
        try:
            metin = yol.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue  # ikili dosya (görsel, yazı tipi, model)
        if not any(karakter in metin for karakter in YASAK):
            continue
        for no, satir in enumerate(metin.splitlines(), 1):
            for karakter, ad in YASAK.items():
                if karakter in satir:
                    ihlaller.append(f"{yol.relative_to(KOK)}:{no}: {ad}")
    assert not ihlaller, (
        "Çizgi işareti olarak yalnız düz tire (-) kullanılır (CLAUDE.md §7). "
        f"{len(ihlaller)} yer:\n" + "\n".join(ihlaller[:40])
    )

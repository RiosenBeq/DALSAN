"""Proje belgeleri (docs/*.md) uygulamanın içinde.

Sayfalar ve mesajlar "docs/15-UZAKTAN-ERISIM.md" gibi belgelere gönderir.
Windows ve Mac uygulamasında program klasörü yoktur, Docker kapsayıcısında da
belgeler sunucunun klasöründe kalırdı: gönderme bir yere çıkmazdı. Belgeler
bu yüzden programla gelir (paketleme/paketleme_ortak.py, Dockerfile) ve burada
düz metin olarak gösterilir. Markdown düz metin olarak da okunur; ayrı bir
çözümleyici bağımlılığı eklenmedi.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app import kaynaklar
from app.web.komuta import kabuk_baglami
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()

# Yalnız docs/ içindeki düz dosya adları: alt klasör, ".." ya da mutlak yol yok
BELGE_ADI = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]*\.md")


def belgeler_dizini():
    return kaynaklar.kaynak_yolu("docs")


def _baslik(metin: str, yedek: str) -> str:
    for satir in metin.splitlines():
        if satir.startswith("# "):
            return satir[2:].strip()
    return yedek


def _oku(ad: str) -> str | None:
    """Belgenin metni; ad geçersizse, dosya yoksa ya da okunamıyorsa None."""
    if not BELGE_ADI.fullmatch(ad):
        return None
    dizin = belgeler_dizini().resolve()
    yol = (dizin / ad).resolve()
    if yol.parent != dizin or not yol.is_file():
        return None
    try:
        return yol.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


@router.get("/komuta/belgeler", response_class=HTMLResponse)
def belge_listesi(istek: Request, baglanti=Depends(baglanti_al)):
    baglam = kabuk_baglami(istek, baglanti, "belgeler")
    dizin = belgeler_dizini()
    belgeler = []
    if dizin.is_dir():
        for yol in sorted(dizin.glob("*.md")):
            metin = _oku(yol.name)
            if metin is not None:
                belgeler.append({"ad": yol.name, "baslik": _baslik(metin, yol.stem)})
    baglam.update({"belgeler": belgeler, "belge": None, "mesaj": ""})
    return sablonlar.TemplateResponse(istek, "komuta_belge.html", baglam)


@router.get("/komuta/belgeler/{ad}", response_class=HTMLResponse)
def belge_goster(istek: Request, ad: str, baglanti=Depends(baglanti_al)):
    baglam = kabuk_baglami(istek, baglanti, "belgeler")
    metin = _oku(ad)
    if metin is None:
        baglam.update(
            {"belgeler": [], "belge": None, "mesaj": f"“{ad}” adlı belge bu kurulumda yok."}
        )
        return sablonlar.TemplateResponse(istek, "komuta_belge.html", baglam, status_code=404)
    baglam.update(
        {
            "belgeler": [],
            "belge": {"ad": ad, "baslik": _baslik(metin, ad), "metin": metin},
            "mesaj": "",
        }
    )
    return sablonlar.TemplateResponse(istek, "komuta_belge.html", baglam)

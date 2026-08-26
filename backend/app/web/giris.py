"""Giriş / oturum: tek yönetici şifresi (.env), imzalı çerez (docs/01 §3.6).

Kural değiştirebilen ve anons tetikleyen sistem LAN'da bile şifresiz olmaz.
Yetki kontrolü TEK dependency'dedir (`oturum_gerekli`) — ileride kullanıcı
tablosuna geçiş yalnızca bu dosyayı değiştirir (docs/01 §4).
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.hatalar import YetkiHatasi
from app.web.rotalar import sablonlar

router = APIRouter()

_CEREZ_ADI = "dalsan_oturum"
_OTURUM_SURESI_SN = 12 * 3600  # bir vardiya + pay; dolunca yeniden giriş


def _anahtar(sifre: str) -> bytes:
    return hashlib.sha256(("dalsan-oturum:" + sifre).encode("utf-8")).digest()


def _imzala(veri: str, sifre: str) -> str:
    return hmac.new(_anahtar(sifre), veri.encode("utf-8"), hashlib.sha256).hexdigest()


def cerez_uret(sifre: str, simdi: float | None = None) -> str:
    son = int((time.time() if simdi is None else simdi) + _OTURUM_SURESI_SN)
    return f"{son}.{_imzala(str(son), sifre)}"


def cerez_gecerli(cerez: str | None, sifre: str, simdi: float | None = None) -> bool:
    if not cerez or "." not in cerez:
        return False
    son_metni, imza = cerez.rsplit(".", 1)
    if not hmac.compare_digest(imza, _imzala(son_metni, sifre)):
        return False
    try:
        return int(son_metni) > (time.time() if simdi is None else simdi)
    except ValueError:
        return False


def oturum_gerekli(istek: Request) -> None:
    """Korunan her rotanın TEK yetki kapısı."""
    sifre = istek.app.state.ayarlar.yonetici_sifresi
    if not cerez_gecerli(istek.cookies.get(_CEREZ_ADI), sifre):
        raise YetkiHatasi(sonraki_yol=str(istek.url.path))


@router.get("/giris", response_class=HTMLResponse)
def giris_sayfasi(istek: Request, sonra: str = "/", hata: str = ""):
    return sablonlar.TemplateResponse(istek, "giris.html", {"sonra": sonra, "hata": hata})


@router.post("/giris")
def giris_yap(istek: Request, sifre: str = Form(...), sonra: str = Form("/")):
    ayarlar = istek.app.state.ayarlar
    if not hmac.compare_digest(sifre, ayarlar.yonetici_sifresi):
        return RedirectResponse(f"/giris?sonra={sonra}&hata=1", status_code=303)
    if not sonra.startswith("/"):
        sonra = "/"  # açık yönlendirme (open redirect) engeli
    yanit = RedirectResponse(sonra, status_code=303)
    yanit.set_cookie(
        _CEREZ_ADI,
        cerez_uret(ayarlar.yonetici_sifresi),
        max_age=_OTURUM_SURESI_SN,
        httponly=True,
        samesite="lax",
    )
    return yanit


@router.post("/cikis")
def cikis_yap():
    yanit = RedirectResponse("/giris", status_code=303)
    yanit.delete_cookie(_CEREZ_ADI)
    return yanit

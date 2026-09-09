"""Giriş / oturum: tek yönetici şifresi (.env → YONETICI_SIFRESI).

ŞİFRE İSTEĞE BAĞLIDIR:
  · boş  → giriş sorulmaz. Tek makinede, yalnız 127.0.0.1'den açılan kurulum.
  · dolu → her sayfa giriş ister.

Neden ayar, neden iki ayrı sürüm değil: kullanıcı sistemi kendi bilgisayarında
denerken her açılışta şifre yazmak zorunda kalmamalı; fabrika sunucusuna
çıkarken de kod değiştirmek zorunda kalmamalı. Tek satır .env değişir.

Şifre BOŞKEN sistem bunu saklamaz: ana sayfada ve kurulum listesinde
"şifre yok" uyarısı görünür. Sessiz bir güvenlik açığı, olmayan bir güvenlikten
kötüdür.

Yetki kontrolü TEK dependency'dedir (`oturum_gerekli`). İleride kullanıcı
tablosuna geçilirse (docs/07 #5) yalnızca bu dosya değişir.

Çerez, şifrenin kendisini TAŞIMAZ: son kullanma zamanı + o zamanın şifreyle
imzası tutulur. Şifre değişince eski çerezlerin imzası tutmaz ve tüm oturumlar
kendiliğinden düşer.
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


def sifre_kurulu_mu(ayarlar) -> bool:
    """Şifre tanımlı mı — ekranlardaki uyarı bunu sorar."""
    return bool(ayarlar.yonetici_sifresi)


def oturum_gerekli(istek: Request) -> None:
    """Korunan her rotanın TEK yetki kapısı.

    Şifre tanımlı değilse hiçbir şey sormaz: bugünkü yerel kullanım aynen
    devam eder.
    """
    ayarlar = istek.app.state.ayarlar
    if not ayarlar.yonetici_sifresi:
        return
    if not cerez_gecerli(istek.cookies.get(_CEREZ_ADI), ayarlar.yonetici_sifresi):
        raise YetkiHatasi(sonraki_yol=str(istek.url.path))


def _guvenli_yol(sonra: str) -> str:
    """Açık yönlendirme (open redirect) engeli.

    Yalnızca site içi, TEK '/' ile başlayan yollar kabul edilir: '//evil.com'
    ve '/\\evil.com' tarayıcıda dış adrese gider ve giriş sayfası bir kimlik
    avı sıçrama tahtasına dönerdi.
    """
    if not sonra.startswith("/") or sonra.startswith("//") or "\\" in sonra:
        return "/"
    return sonra


@router.get("/giris", response_class=HTMLResponse)
def giris_sayfasi(istek: Request, sonra: str = "/", hata: str = ""):
    # Şifre tanımlı değilken giriş sayfası anlamsızdır: kullanıcı boş bir
    # kutuya bakıp ne yazacağını arar. Doğrudan ana sayfaya alınır.
    if not istek.app.state.ayarlar.yonetici_sifresi:
        return RedirectResponse("/", status_code=303)
    return sablonlar.TemplateResponse(
        istek, "giris.html", {"sonra": _guvenli_yol(sonra), "hata": hata}
    )


@router.post("/giris")
def giris_yap(istek: Request, sifre: str = Form(...), sonra: str = Form("/")):
    ayarlar = istek.app.state.ayarlar
    sonra = _guvenli_yol(sonra)
    if not ayarlar.yonetici_sifresi:
        return RedirectResponse(sonra, status_code=303)
    if not hmac.compare_digest(sifre, ayarlar.yonetici_sifresi):
        return RedirectResponse(f"/giris?sonra={sonra}&hata=1", status_code=303)
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

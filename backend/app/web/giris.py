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

Çerez, şifrenin kendisini TAŞIMAZ: son kullanma zamanı + o zamanın imzası
tutulur. İmza anahtarı şifre ile KURULUMA ÖZGÜ rastgele bir sırdan türer
(`veri/oturum.anahtar`, docs/17 §10.5 R16). Şifre değişince eski çerezlerin
imzası tutmaz ve tüm oturumlar kendiliğinden düşer. Sır olmasaydı anahtar
yalnız şifreden türerdi: ele geçen tek bir çerezle şifre, sunucuya hiç
dokunmadan (kaba kuvvet kilidine takılmadan) çevrimdışı denenebilirdi.

KABA KUVVET KORUMASI: tek şifreli bir sistemde sınırsız deneme, şifreyi
fiilen yok sayar - saniyede yüzlerce deneme yapan bir betik altı haneli bir
şifreyi kısa sürede bulur. Aynı adresten arka arkaya birkaç yanlış denemeden
sonra o adres bir süre kilitlenir. Kilit ADRES BAZLIDIR: fabrikadaki bir
kişinin yanlış yazması, başka bir bilgisayardan girişi engellemez. Adres,
istemcinin yazabildiği başlıklardan değil bağlantının kendisinden okunur
(`_istemci_adresi`).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.hatalar import YetkiHatasi
from app.loglama import log_al
from app.web.rotalar import sablonlar

router = APIRouter()
_log = log_al("giris")

_CEREZ_ADI = "dalsan_oturum"
_OTURUM_SURESI_SN = 12 * 3600  # bir vardiya + pay; dolunca yeniden giriş

# Kaba kuvvet: bu kadar yanlış denemeden sonra adres kilitlenir.
# 5 deneme, şifresini yanlış hatırlayan kullanıcıya yeter; saniyede yüzlerce
# deneme yapan bir betiği ise fiilen durdurur.
_EN_COK_DENEME = 5
_KILIT_SURESI_SN = 300  # 5 dakika
# Kilit defteri sınırsız büyümesin (7x24 çalışma): bu sayıya ulaşınca en eski
# kayıtlar atılır. Aynı anda bu kadar farklı adresten deneme, zaten kendisi
# bir saldırı işaretidir ve günlüğe düşer.
_EN_COK_ADRES = 1000

# adres -> (yanlış deneme sayısı, son deneme zamanı)
_denemeler: dict[str, tuple[int, float]] = {}


# Kuruluma özgü sır (R16): veri klasöründe, ilk girişte üretilir. Silinirse
# yenisi üretilir ve açık oturumlar bir kez düşer; başka bir zararı yoktur.
SIR_DOSYASI = "oturum.anahtar"
_SIR_BAYT = 32
_sirlar: dict[Path, bytes] = {}  # her istekte dosya okunmasın
_sir_kilidi = threading.Lock()


def oturum_sirri(ayarlar) -> bytes:
    """Bu kurulumun imza sırrı; yoksa ya da bozuksa üretir."""
    yol = Path(ayarlar.veri_dizini) / SIR_DOSYASI
    sir = _sirlar.get(yol)
    if sir is None:
        with _sir_kilidi:  # aynı anda iki ilk giriş iki ayrı sır üretmesin
            sir = _sirlar.get(yol) or _sirri_oku_ya_da_uret(yol)
            _sirlar[yol] = sir
    return sir


def _sirri_oku_ya_da_uret(yol: Path) -> bytes:
    try:
        sir = bytes.fromhex(yol.read_text(encoding="ascii").strip())
        if len(sir) >= _SIR_BAYT:
            return sir
        _log.warning("Oturum anahtarı dosyası bozuk; yenisi üretildi, açık oturumlar kapandı.")
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as hata:
        _log.warning(
            f"Oturum anahtarı okunamadı ({hata}); yenisi üretildi, açık oturumlar kapandı."
        )
    sir = secrets.token_bytes(_SIR_BAYT)
    gecici = yol.with_name(yol.name + ".yeni")
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        # Yalnız sahibi okuyabilir (0600); yarım yazılmış dosya asıl adı almaz
        tanimlayici = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(tanimlayici, "w", encoding="ascii") as dosya:
            dosya.write(sir.hex())
        os.replace(gecici, yol)
    except OSError as hata:
        # Giriş yine çalışır; yalnız oturumlar yeniden başlatmada düşer
        _log.error(
            f"Oturum anahtarı kaydedilemedi ({hata}); yalnız bu çalışma boyunca geçerli.",
            extra={"ayrinti": str(yol)},
        )
    return sir


def _anahtar(sifre: str, sir: bytes) -> bytes:
    return hmac.new(sir, ("dalsan-oturum:" + sifre).encode("utf-8"), hashlib.sha256).digest()


def _imzala(veri: str, sifre: str, sir: bytes) -> str:
    return hmac.new(_anahtar(sifre, sir), veri.encode("utf-8"), hashlib.sha256).hexdigest()


def cerez_uret(sifre: str, *, sir: bytes, simdi: float | None = None) -> str:
    son = int((time.time() if simdi is None else simdi) + _OTURUM_SURESI_SN)
    return f"{son}.{_imzala(str(son), sifre, sir)}"


def _esit(birinci: str, ikinci: str) -> bool:
    """Sabit süreli karşılaştırma - Türkçe karakterle de çalışır.

    `hmac.compare_digest` iki METİN alınca ASCII dışı bir karakterde TypeError
    fırlatır: "ş" içeren bir şifre kurulduğunda ya da giriş kutusuna Türkçe
    harf yazıldığında kullanıcı 500 hatası görürdü (docs/AUDIT.md R15). Bayt
    olarak karşılaştırmak bu sınırı kaldırır; `surrogatepass` hiçbir metinde
    kodlama hatası vermez.
    """
    return hmac.compare_digest(
        birinci.encode("utf-8", "surrogatepass"), ikinci.encode("utf-8", "surrogatepass")
    )


def cerez_gecerli(cerez: str | None, sifre: str, *, sir: bytes, simdi: float | None = None) -> bool:
    if not cerez or "." not in cerez:
        return False
    son_metni, imza = cerez.rsplit(".", 1)
    if not _esit(imza, _imzala(son_metni, sifre, sir)):
        return False
    try:
        return int(son_metni) > (time.time() if simdi is None else simdi)
    except ValueError:
        return False


def _istemci_adresi(istek: Request) -> str:
    """İsteğin geldiği adres - kaba kuvvet kilidi bu adrese uygulanır.

    `X-Forwarded-For` burada BİLEREK okunmaz. O başlığın ilk değerini
    istemcinin kendisi yazar: her denemede farklı bir değer gönderen bir
    betik, adres başına kilidi hiç tetiklemeden sınırsız şifre deneyebilirdi
    (docs/AUDIT.md R7).

    Ters vekil (nginx/Caddy) arkasında gerçek adresi uvicorn kendisi yazar:
    vekil başlıkları varsayılan olarak işlenir ama YALNIZ güvenilen vekilden
    gelen bağlantıda. Varsayılan güvenilen vekil aynı makinedir (127.0.0.1,
    ::1); vekil başka bir makinedeyse onun adresi `FORWARDED_ALLOW_IPS` ortam
    değişkenine yazılır (docs/15 §4.3).
    """
    return istek.client.host if istek.client else "bilinmeyen"


def kilit_kalan_sn(adres: str, simdi: float | None = None) -> int:
    """Bu adres kilitliyse kalan saniye, değilse 0."""
    kayit = _denemeler.get(adres)
    if kayit is None:
        return 0
    sayi, son = kayit
    if sayi < _EN_COK_DENEME:
        return 0
    an = time.time() if simdi is None else simdi
    kalan = int(_KILIT_SURESI_SN - (an - son))
    return max(kalan, 0)


def _yanlis_deneme_kaydet(adres: str, simdi: float | None = None) -> None:
    an = time.time() if simdi is None else simdi
    sayi, son = _denemeler.get(adres, (0, an))
    # Kilit süresi dolduysa sayaç sıfırdan başlar: kullanıcı beklediyse
    # cezasını çekmiştir, bir sonraki hatasında yeniden kilitlenmemeli.
    if sayi >= _EN_COK_DENEME and (an - son) >= _KILIT_SURESI_SN:
        sayi = 0
    _denemeler[adres] = (sayi + 1, an)
    if len(_denemeler) > _EN_COK_ADRES:
        for eski in sorted(_denemeler, key=lambda a: _denemeler[a][1])[: _EN_COK_ADRES // 2]:
            del _denemeler[eski]


def denemeleri_sifirla(adres: str | None = None) -> None:
    """Başarılı girişte (ya da testte) deneme sayacını temizler."""
    if adres is None:
        _denemeler.clear()
    else:
        _denemeler.pop(adres, None)


def sifre_kurulu_mu(ayarlar) -> bool:
    """Şifre tanımlı mı - ekranlardaki uyarı bunu sorar."""
    return bool(ayarlar.yonetici_sifresi)


def oturum_gecerli_mi(istek: Request) -> bool:
    """İsteğin geçerli bir oturumu var mı (şifre tanımlı değilse her zaman evet).

    Kimliksiz uçların kendi içinde ayrıntıyı oturuma bağlaması için
    (/saglik?ayrinti=1); korunan rotalar `oturum_gerekli`'yi kullanır.
    """
    ayarlar = istek.app.state.ayarlar
    if not ayarlar.yonetici_sifresi:
        return True
    return cerez_gecerli(
        istek.cookies.get(_CEREZ_ADI), ayarlar.yonetici_sifresi, sir=oturum_sirri(ayarlar)
    )


def oturum_gerekli(istek: Request) -> None:
    """Korunan her rotanın TEK yetki kapısı.

    Şifre tanımlı değilse hiçbir şey sormaz: bugünkü yerel kullanım aynen
    devam eder.
    """
    if not oturum_gecerli_mi(istek):
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
def giris_sayfasi(istek: Request, sonra: str = "/", hata: str = "", kilit: str = ""):
    # Şifre tanımlı değilken giriş sayfası anlamsızdır: kullanıcı boş bir
    # kutuya bakıp ne yazacağını arar. Doğrudan ana sayfaya alınır.
    if not istek.app.state.ayarlar.yonetici_sifresi:
        return RedirectResponse("/", status_code=303)
    # Kilit süresi ADRESTEN yeniden okunur; sorgu dizesindeki sayı yalnızca
    # yönlendirmeyi taşır ve kullanıcı tarafından değiştirilebilir.
    kalan = kilit_kalan_sn(_istemci_adresi(istek))
    return sablonlar.TemplateResponse(
        istek,
        "giris.html",
        {
            "sonra": _guvenli_yol(sonra),
            "hata": hata and not kalan,
            "kilit_sn": kalan,
            "kilit_dk": (kalan + 59) // 60,
        },
    )


@router.post("/giris")
def giris_yap(istek: Request, sifre: str = Form(...), sonra: str = Form("/")):
    ayarlar = istek.app.state.ayarlar
    sonra = _guvenli_yol(sonra)
    if not ayarlar.yonetici_sifresi:
        return RedirectResponse(sonra, status_code=303)

    adres = _istemci_adresi(istek)
    kalan = kilit_kalan_sn(adres)
    if kalan > 0:
        return RedirectResponse(f"/giris?sonra={sonra}&kilit={kalan}", status_code=303)

    if not _esit(sifre, ayarlar.yonetici_sifresi):
        _yanlis_deneme_kaydet(adres)
        kalan = kilit_kalan_sn(adres)
        _log.warning(
            f"Yanlış şifre denemesi ({adres})"
            + (f" - adres {kalan} sn kilitlendi." if kalan else "")
        )
        if kalan > 0:
            return RedirectResponse(f"/giris?sonra={sonra}&kilit={kalan}", status_code=303)
        return RedirectResponse(f"/giris?sonra={sonra}&hata=1", status_code=303)

    denemeleri_sifirla(adres)
    yanit = RedirectResponse(sonra, status_code=303)
    yanit.set_cookie(
        _CEREZ_ADI,
        cerez_uret(ayarlar.yonetici_sifresi, sir=oturum_sirri(ayarlar)),
        max_age=_OTURUM_SURESI_SN,
        httponly=True,
        samesite="lax",
        # HTTPS üzerinden gelindiyse çerez YALNIZ HTTPS'te gönderilir. Uzaktan
        # erişimde araya giren biri çerezi düz HTTP'de yakalayamaz. Ters vekil
        # arkasında şema X-Forwarded-Proto ile bildirilir.
        secure=_https_mi(istek),
    )
    return yanit


def _https_mi(istek: Request) -> bool:
    if istek.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https":
        return True
    return istek.url.scheme == "https"


@router.post("/cikis")
def cikis_yap():
    yanit = RedirectResponse("/giris", status_code=303)
    yanit.delete_cookie(_CEREZ_ADI)
    return yanit

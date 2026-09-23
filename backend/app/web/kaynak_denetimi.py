"""İstek kaynağı denetimi: DNS yeniden bağlama ve siteler arası form (R8).

İKİ KURAL, TEK ARA KATMAN (docs/17 §10.5 R8):

1. **HOST İZİN LİSTESİ - her istekte.** Tarayıcı, başka bir sitenin sayfasında
   çalışan betiğin bu sistemin yanıtlarını okumasını aynı-köken kuralıyla
   engeller. Ama saldırganın alan adı sonradan bu makinenin adresine
   çözülürse (DNS yeniden bağlama) tarayıcı için köken DEĞİŞMEMİŞTİR ve betik
   kamera görüntüsünü, olay listesini okuyabilir. O istekteki `Host` başlığı
   saldırganın adını taşır: izinli adlar dışında bir `Host` gelirse istek 421
   ile reddedilir. `Origin`'i `Host`'la karşılaştırmak burada işe yaramaz -
   ikisi de aynı sahte adı taşır.
2. **DURUM DEĞİŞTİREN İSTEKTE KÖKEN - GET/HEAD/OPTIONS dışında.** Başka bir
   sitenin sayfası, oturumu açık tarayıcı üzerinden buraya form gönderebilir
   (CSRF): kamera sil, anons çal. `Origin` (yoksa `Referer`) izinli bir ad
   taşımıyorsa, `Origin: null` ise ya da tarayıcı `Sec-Fetch-Site` ile
   `cross-site` / `same-site` diyorsa istek 403 ile reddedilir. **Üç başlığın üçü de
   yoksa istek geçer:** CSRF'in aracı her zaman bir tarayıcıdır ve güncel
   tarayıcılar POST'ta `Origin`'i hep gönderir; başlıksız istek tarayıcı
   dışı bir istemcidir (curl, Kontrol Paneli, testler).

İzinli adlar: geri döngü adresleri (127.x, ::1, localhost), SUNUCU_ADRESI ve
.env'deki IZINLI_SUNUCU_ADLARI. Uzaktan erişimde kullanılan ad oraya
yazılmalıdır (docs/15); yazılmamışsa sayfa ne yapılacağını söyler.

Port karşılaştırılmaz: ters vekil arkasında tarayıcının gördüğü port (443)
ile sistemin portu (8080) farklıdır. Bunun bıraktığı tek boşluk - aynı
makinede BAŞKA bir porttaki sayfanın (127.0.0.1:8100) form göndermesi -
`Sec-Fetch-Site: same-site` ile kapanır: tarayıcı aynı adın başka portunu
'same-site' sayar, sistemin kendi sayfası ise her zaman 'same-origin'dir
(vekil arkasında da: sayfa ve form aynı vekil adresinden gelir).

Yalnız HTTP isteklerine uygulanır. Sistemde WebSocket ucu yoktur - eklenirse
bu denetim ona da uygulanmalıdır.
"""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.ayarlar import Ayarlar, geri_donus_adi_mi, sunucu_adi
from app.loglama import log_al

# Sunucuda hiçbir şeyi değiştirmeyen yöntemler: köken denetimi yalnız
# bunların DIŞINDAKİLERE uygulanır.
GUVENLI_YONTEMLER = frozenset({"GET", "HEAD", "OPTIONS"})


def izinli_mi(ad: str, ayarlar: Ayarlar) -> bool:
    """Ad bu sisteme erişmek için kullanılabilir mi?"""
    if not ad:
        return False
    return (
        geri_donus_adi_mi(ad)
        or ad == sunucu_adi(ayarlar.sunucu_adresi)
        or ad in ayarlar.izinli_sunucu_adlari
    )


# Sec-Fetch-Site'ı sayfa değiştiremez; tarayıcı yazar. Sistemin kendi
# formları 'same-origin' gönderir, adres çubuğundan gelen istek 'none'.
REDDEDILEN_FETCH_SITE = frozenset({"cross-site", "same-site"})


def kokeni_reddet_mi(basliklar: Headers, ayarlar: Ayarlar) -> bool:
    """Durum değiştiren istek başka bir siteden mi geliyor?"""
    if basliklar.get("sec-fetch-site", "").strip().lower() in REDDEDILEN_FETCH_SITE:
        return True
    koken = basliklar.get("origin")
    if koken is not None:
        # Sandbox'lı iframe, file:// sayfası ve bazı yönlendirmeler 'null'
        # gönderir; hiçbiri bu sistemin kendi sayfası değildir.
        return koken.strip().lower() == "null" or not izinli_mi(sunucu_adi(koken), ayarlar)
    yonlendiren = basliklar.get("referer")
    if yonlendiren is not None:
        return not izinli_mi(sunucu_adi(yonlendiren), ayarlar)
    return False


class KaynakDenetimi:
    """Saf ASGI ara katmanı: istek uygulamaya ulaşmadan önce denetlenir.

    Ayarlar her istekte `app.state.ayarlar`'dan okunur (uygulama fabrikası
    oraya koyar); sabit bir kopya tutulmaz.
    """

    def __init__(self, uygulama: ASGIApp) -> None:
        self.uygulama = uygulama

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.uygulama(scope, receive, send)
            return
        ayarlar: Ayarlar = scope["app"].state.ayarlar
        basliklar = Headers(scope=scope)

        ham_host = basliklar.get("host", "")
        ad = sunucu_adi(ham_host)
        if not izinli_mi(ad, ayarlar):
            log_al("guvenlik").warning(
                "İzinsiz sunucu adıyla gelen istek reddedildi.",
                extra={"ayrinti": f"Host={ham_host!r} {scope['method']} {scope['path']}"},
            )
            await _host_reddi(basliklar, ad, ham_host)(scope, receive, send)
            return

        if scope["method"] not in GUVENLI_YONTEMLER and kokeni_reddet_mi(basliklar, ayarlar):
            log_al("guvenlik").warning(
                "Başka bir siteden gönderilmiş görünen istek reddedildi.",
                extra={
                    "ayrinti": (
                        f"Origin={basliklar.get('origin')!r} "
                        f"Referer={basliklar.get('referer')!r} "
                        f"Sec-Fetch-Site={basliklar.get('sec-fetch-site')!r} "
                        f"{scope['method']} {scope['path']}"
                    )
                },
            )
            await _koken_reddi(basliklar)(scope, receive, send)
            return

        await self.uygulama(scope, receive, send)


# ------------------------------------------------------------------ yanıtlar
#
# Ret sayfası KENDİ İÇİNDE TAMDIR: stil dosyası bile istenmez. 421'de tarayıcı
# /static/stil.css'i de aynı izinsiz adla isterdi ve o da reddedilirdi -
# kullanıcı biçimsiz bir sayfa görürdü. Şablon motoru da kullanılmaz: ara
# katman, uygulamanın hata yakalayıcılarından ÖNCE çalışır.

_SAYFA = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{baslik} - DALSAN İSG</title>
<style>
body {{ margin: 0; padding: 48px 16px; background: #f1f3f6; color: #16181d;
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width: 620px; margin: 0 auto; padding: 26px 28px; background: #fff;
  border: 1px solid #dde1e8; border-radius: 14px; }}
h1 {{ margin: 0 0 12px; font-size: 20px; }}
p {{ margin: 0 0 12px; }}
code {{ padding: 1px 6px; border-radius: 6px; background: #eef1f5; overflow-wrap: anywhere; }}
</style></head>
<body><main><h1>{baslik}</h1>{govde}</main></body></html>"""


def _html_ister(basliklar: Headers) -> bool:
    """hatalar.py'deki ölçüt: sayfa isteği HTML, fetch çağrısı JSON alır."""
    return (
        "text/html" in basliklar.get("accept", "") or basliklar.get("sec-fetch-mode") == "navigate"
    )


def _yanit(basliklar: Headers, kod: int, baslik: str, govde: str, duz: str) -> Response:
    if _html_ister(basliklar):
        return HTMLResponse(_SAYFA.format(baslik=baslik, govde=govde), status_code=kod)
    return JSONResponse({"hata": duz}, status_code=kod)


def _host_reddi(basliklar: Headers, ad: str, ham_host: str) -> Response:
    # Port, kullanıcıya tarif edilen yerel adrese taşınır: sistem 8080'de
    # değilse "127.0.0.1:8080'i açın" demek yanlış olurdu.
    try:
        port = urlsplit("//" + ham_host.strip()).port if ad else None
    except ValueError:
        port = None
    yerel = f"http://127.0.0.1:{port}" if port else "http://127.0.0.1"
    if ad:
        kim = f"<code>{escape(ad)}</code> adıyla"
        ne_yazilir = f"<code>{escape(ad)}</code> yazıp"
    else:
        kim = "tanınmayan bir adla"
        ne_yazilir = "tarayıcıdaki adresin sunucu adını yazıp"
    govde = (
        f"<p>Sistem bu isteği {kim} aldı. Bu ad, sistemin izinli sunucu adları "
        "arasında değil.</p>"
        "<p>Bu bir güvenlik önlemidir: başka bir internet sitesi, kendi adını bu "
        "bilgisayarın adresine yönlendirerek tarayıcınız üzerinden sisteme "
        "ulaşmaya çalışabilir (DNS yeniden bağlama). İzin listesi bunu durdurur.</p>"
        "<p><b>Bu adresi siz kullanıyorsanız:</b> sunucu bilgisayarının kendisinde "
        f"<code>{yerel}</code> adresini açın, <b>Ayarlar → Güvenlik → İzinli sunucu "
        f"adları</b> kutusuna {ne_yazilir} kaydedin ve sistemi yeniden başlatın.</p>"
        # Bu sayfanın kendisi de bir tuzağın parçası olabilir: saldırgan
        # operatörü kendi adına yönlendirip "şunu listeye ekle" dedirtebilir.
        "<p><b>Tanımadığınız bir adsa eklemeyin</b> - sizi bu adrese bir internet "
        "sitesi ya da e-posta yönlendirmiş olabilir. Yalnız şirketinizin kendi "
        "adlarını ve sunucunun IP adresini ekleyin.</p>"
    )
    duz = (
        f"Bu adrese izin verilmiyor: '{ad or ham_host}' izinli sunucu adları arasında "
        "değil. Ayarlar → Güvenlik → İzinli sunucu adları."
    )
    return _yanit(basliklar, 421, "Bu adrese izin verilmiyor", govde, duz)


def _koken_reddi(basliklar: Headers) -> Response:
    govde = (
        "<p>Bu istek başka bir internet sitesinden gönderilmiş görünüyor. Sistem "
        "kamera silmek, kural değiştirmek ya da anons çaldırmak gibi işlemleri "
        "yalnız kendi sayfalarından kabul eder.</p>"
        "<p>Sayfayı sistemin kendi adresinden açıp işlemi tekrar deneyin. Sistemi "
        "bir ters vekil ya da tünel üzerinden kullanıyorsanız o adın <b>Ayarlar → "
        "Güvenlik → İzinli sunucu adları</b> kutusunda yazılı olması gerekir.</p>"
    )
    duz = (
        "İstek reddedildi: başka bir siteden gönderilmiş görünüyor. Sayfayı "
        "sistemin kendi adresinden açıp tekrar deneyin."
    )
    return _yanit(basliklar, 403, "İstek reddedildi", govde, duz)

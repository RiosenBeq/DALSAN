"""Tiplenmiş hata sınıfları ve FastAPI'nin merkezi hata yakalayıcısı.

Kural (CLAUDE.md §7): çıplak `except:` / `except Exception: pass` YASAK.
Beklenen her hata, buradaki sınıflardan biriyle ve kullanıcıya olduğu gibi
gösterilebilecek, anlaşılır Türkçe bir mesajla fırlatılır.

FastAPI importları bilerek fonksiyonun İÇİNDEDİR: bu modül framework'süz kalır,
böylece saf katmanlar (ör. rules/) da bu hata sınıflarını kullanabilir.
"""

from __future__ import annotations


class DalsanHata(Exception):
    """Tüm bilinçli hataların atası. Mesajı kullanıcıya gösterilir.

    `kullanici_mesaji` EKRANA çıkar: kısa, sade Türkçe; adres/yığın izi içermez.
    `teknik_ayrinti` yalnızca veri/loglar/sistem.log'a yazılır — destek akışı
    oradan kopyalandığı için tam adres ve özgün hata metni orada durur.
    Verilmezse kullanıcı mesajının aynısıdır (eski davranış korunur).
    """

    http_kodu = 500

    def __init__(self, kullanici_mesaji: str, teknik_ayrinti: str | None = None) -> None:
        super().__init__(kullanici_mesaji)
        self.kullanici_mesaji = kullanici_mesaji
        self.teknik_ayrinti = teknik_ayrinti or kullanici_mesaji


class AyarHatasi(DalsanHata):
    """.env eksik/bozuk — program açılışta durur, yarım çalışmaz."""


class VeritabaniHatasi(DalsanHata):
    """SQLite bağlantısı veya şema uygulaması başarısız."""


class YetkiHatasi(DalsanHata):
    """Oturum yok/geçersiz. Tarayıcı isteği giriş sayfasına yönlendirilir.

    Yetki kontrolü TEK yerdedir (web/giris.py → oturum_gerekli); ileride
    kullanıcı tablosuna geçilirse yalnızca orası değişir.
    """

    http_kodu = 401

    def __init__(self, sonraki_yol: str = "/") -> None:
        super().__init__("Bu sayfa için giriş yapmanız gerekiyor.")
        self.sonraki_yol = sonraki_yol


class DogrulamaHatasi(DalsanHata):
    """Kullanıcı girdisi geçersiz (form/parametre) — 400 döner, mesaj yol gösterir."""

    http_kodu = 400


# Form alanlarının kullanıcıya görünen adları (422 mesajı Türkçe olsun diye)
_ALAN_ADLARI = {
    "name": "Ad",
    "area": "Alan",
    "source_type": "Kaynak tipi",
    "source_url": "Kaynak adresi",
    "sample_fps": "Örnekleme hızı (fps)",
    "zone_type": "Bölge tipi",
    "zone_id": "Bölge",
    "polygon": "Bölge çizimi",
    "enabled": "Açık/kapalı",
    "image_points": "Kalibrasyon noktaları",
    "world_points": "Metre karşılıkları",
    "durum": "Olay durumu",
    "alan": "Etiket alanı",
    "deger": "Etiket değeri",
}

_BEKLENMEYEN_MESAJ = (
    "Beklenmeyen bir hata oluştu. Ayrıntılar veri/loglar/sistem.log "
    "dosyasında — kırmızı satırları kopyalayıp Claude Code'a yapıştırın."
)


def hata_yakalayicilari_kur(app) -> None:
    """Uygulamadaki TEK hata yakalama noktası.

    Bilinçli hatalar (DalsanHata) kullanıcı mesajıyla, beklenmeyenler
    log'a tam ayrıntıyla + ekrana genel bir Türkçe mesajla döner.

    Tarayıcıdan gelen sayfa/form istekleri (Accept: text/html) Türkçe bir
    HATA SAYFASI görür — ham JSON değil. JS/fetch istekleri JSON alır.
    """
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    from app.loglama import log_al

    log = log_al("hata")

    def _html_ister(istek: Request) -> bool:
        return "text/html" in istek.headers.get("accept", "")

    def _yanit(istek: Request, kod: int, mesaj: str, baslik: str):
        if _html_ister(istek):
            # Import burada: app.web.rotalar → veritabani → hatalar döngüsü
            # modül yüklenirken değil, ilk hata anında çözülür.
            from app.web.rotalar import sablonlar

            return sablonlar.TemplateResponse(
                istek,
                "hata.html",
                {"baslik": baslik, "mesaj": mesaj},
                status_code=kod,
            )
        return JSONResponse(status_code=kod, content={"hata": mesaj})

    @app.exception_handler(DalsanHata)
    async def dalsan_hatasi(istek: Request, hata: DalsanHata):
        # Günlüğe TAM ayrıntı, ekrana sade mesaj
        log.error(hata.teknik_ayrinti)
        baslik = "Girdi hatası" if hata.http_kodu == 400 else "Hata"
        return _yanit(istek, hata.http_kodu, hata.kullanici_mesaji, baslik)

    @app.exception_handler(YetkiHatasi)
    async def yetki_hatasi(istek: Request, hata: YetkiHatasi):
        # Tarayıcıdan gelen SAYFA isteği giriş ekranına yönlenir; JS/fetch
        # istekleri 401 JSON alır — yönlendirme onların akışını bozardı
        # (önizleme ve durum sorguları sessizce HTML almaya başlardı).
        from urllib.parse import quote

        from fastapi.responses import RedirectResponse

        # `Accept: text/html` TEK ölçüt değildir: bazı tarayıcı/vekil sunucu
        # birleşimleri üst düzey gezinmede `*/*` gönderir ve kullanıcı giriş
        # formu yerine ham JSON görürdü. Modern tarayıcılar gezinmeyi ayrıca
        # `Sec-Fetch-Mode: navigate` ile bildirir; fetch çağrıları bildirmez.
        gezinme = istek.headers.get("sec-fetch-mode") == "navigate"
        if _html_ister(istek) or gezinme:
            return RedirectResponse(f"/giris?sonra={quote(hata.sonraki_yol)}", status_code=303)
        return JSONResponse(status_code=401, content={"hata": hata.kullanici_mesaji})

    @app.exception_handler(RequestValidationError)
    async def form_hatasi(istek: Request, hata: RequestValidationError):
        # FastAPI'nin İngilizce 422 JSON'u yerine: hangi alan, Türkçe.
        alanlar = []
        for sorun in hata.errors():
            alan = str(sorun.get("loc", ("",))[-1])
            alanlar.append(_ALAN_ADLARI.get(alan, alan))
        mesaj = "Form eksik veya hatalı doldurulmuş. Kontrol edilecek alanlar: " + (
            ", ".join(dict.fromkeys(alanlar)) or "bilinmiyor"
        )
        log.error(f"{mesaj} ({istek.method} {istek.url.path})")
        return _yanit(istek, 400, mesaj, "Girdi hatası")

    @app.exception_handler(Exception)
    async def beklenmeyen_hata(istek: Request, hata: Exception):
        log.error(f"Beklenmeyen hata: {hata}", exc_info=hata)
        return _yanit(istek, 500, _BEKLENMEYEN_MESAJ, "Beklenmeyen hata")

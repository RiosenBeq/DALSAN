"""Tiplenmiş hata sınıfları ve FastAPI'nin merkezi hata yakalayıcısı.

Kural (CLAUDE.md §7): çıplak `except:` / `except Exception: pass` YASAK.
Beklenen her hata, buradaki sınıflardan biriyle ve kullanıcıya olduğu gibi
gösterilebilecek, anlaşılır Türkçe bir mesajla fırlatılır.

FastAPI importları bilerek fonksiyonun İÇİNDEDİR: bu modül framework'süz kalır,
böylece saf katmanlar (ör. rules/) da bu hata sınıflarını kullanabilir.
"""

from __future__ import annotations


class DalsanHata(Exception):
    """Tüm bilinçli hataların atası. Mesajı kullanıcıya gösterilir."""

    http_kodu = 500

    def __init__(self, kullanici_mesaji: str) -> None:
        super().__init__(kullanici_mesaji)
        self.kullanici_mesaji = kullanici_mesaji


class AyarHatasi(DalsanHata):
    """.env eksik/bozuk — program açılışta durur, yarım çalışmaz."""


class VeritabaniHatasi(DalsanHata):
    """SQLite bağlantısı veya şema uygulaması başarısız."""


def hata_yakalayicilari_kur(app) -> None:
    """Uygulamadaki TEK hata yakalama noktası.

    Bilinçli hatalar (DalsanHata) kullanıcı mesajıyla, beklenmeyenler
    log'a tam ayrıntıyla + ekrana genel bir Türkçe mesajla döner.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    from app.loglama import log_al

    log = log_al("hata")

    @app.exception_handler(DalsanHata)
    async def dalsan_hatasi(istek: Request, hata: DalsanHata) -> JSONResponse:
        log.error(hata.kullanici_mesaji)
        return JSONResponse(status_code=hata.http_kodu, content={"hata": hata.kullanici_mesaji})

    @app.exception_handler(Exception)
    async def beklenmeyen_hata(istek: Request, hata: Exception) -> JSONResponse:
        log.error(f"Beklenmeyen hata: {hata}", exc_info=hata)
        return JSONResponse(
            status_code=500,
            content={
                "hata": (
                    "Beklenmeyen bir hata oluştu. Ayrıntılar veri/loglar/sistem.log "
                    "dosyasında — kırmızı satırları kopyalayıp Claude Code'a yapıştırın."
                )
            },
        )

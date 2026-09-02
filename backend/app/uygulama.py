"""FastAPI uygulama fabrikası.

main.py'den ayrı olmasının nedeni: main.py import edildiği anda gerçek .env'i
okur ve log sistemini kurar (uvicorn böyle bekler). Testler ise uygulamayı
geçici klasöre işaret eden ayarlarla, hiçbir yan etki olmadan kurabilmeli.
Bu yüzden yan etkisiz fabrika burada, yan etkili giriş noktası main.py'de.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import loglama, veritabani
from app.ayarlar import Ayarlar
from app.hatalar import VeritabaniHatasi, hata_yakalayicilari_kur
from app.web import anons_web, kameralar, kkd_web, kurallar, olaylar_web, rotalar

STATIK_DIZINI = Path(__file__).resolve().parent / "web" / "static"


def uygulama_olustur(ayarlar: Ayarlar, analiz: bool = True) -> FastAPI:
    """Verilen ayarlarla FastAPI uygulaması kurar; şema açılışta uygulanır.

    analiz=False yalnızca testler içindir: kamera/tespit iş parçacığı başlamaz.
    """

    @asynccontextmanager
    async def yasam_dongusu(uygulama: FastAPI):
        log = loglama.log_al("sistem")
        try:
            baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
            try:
                veritabani.semayi_uygula(baglanti)
                surum = veritabani.mevcut_surum(baglanti)
            finally:
                baglanti.close()
        except VeritabaniHatasi as hata:
            # Türkçe mesaj hem günlüğe hem Kontrol Paneli çıktısına düşsün;
            # ardından açılış bilerek durdurulur — sistem yarım çalışmaz.
            log.error(hata.kullanici_mesaji)
            raise
        log.info(f"Sistem hazır — veritabanı: {ayarlar.veritabani_yolu}, şema: {surum}")

        supervizor = None
        if analiz:
            # Import bilerek burada: analiz=False testleri OpenCV/ONNX yüklemez
            from app.analiz.supervizor import AnalizSupervizoru

            supervizor = AnalizSupervizoru(ayarlar)
            uygulama.state.supervizor = supervizor
            supervizor.baslat()

        yield

        if supervizor is not None:
            supervizor.durdur()
        log.info("Sistem durduruluyor.")

    uygulama = FastAPI(title="DALSAN İSG", lifespan=yasam_dongusu)
    uygulama.state.ayarlar = ayarlar
    hata_yakalayicilari_kur(uygulama)

    # Giriş/şifre bilerek yok (docs/07 #0): sistem tek makinede 127.0.0.1'e
    # bağlı çalışır. Fabrika sunucusuna çıkmadan önce tek yetki kapısı geri eklenir.
    uygulama.include_router(rotalar.router)
    uygulama.include_router(kameralar.router)
    uygulama.include_router(kurallar.router)
    uygulama.include_router(olaylar_web.router)
    uygulama.include_router(kkd_web.router)
    uygulama.include_router(anons_web.router)

    uygulama.mount("/static", StaticFiles(directory=str(STATIK_DIZINI)), name="static")
    return uygulama

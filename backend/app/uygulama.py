"""FastAPI uygulama fabrikası.

main.py'den ayrı olmasının nedeni: main.py import edildiği anda gerçek .env'i
okur ve log sistemini kurar (uvicorn böyle bekler). Testler ise uygulamayı
geçici klasöre işaret eden ayarlarla, hiçbir yan etki olmadan kurabilmeli.
Bu yüzden yan etkisiz fabrika burada, yan etkili giriş noktası main.py'de.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import kaynaklar, loglama, veritabani
from app.ayarlar import Ayarlar
from app.hatalar import VeritabaniHatasi, hata_yakalayicilari_kur
from app.web import (
    alan_rotalari,
    anons_web,
    ayar_rotalari,
    hoparlorler,
    kameralar,
    kkd_web,
    komuta,
    kurallar,
    nesne_rotalari,
    olaylar_web,
    rotalar,
)

# Stil/betik dosyalarının yeri app/kaynaklar.py'den çözülür (paketlenmiş
# programda dosyalar depoda değil, paketin açıldığı geçici klasördedir).
STATIK_DIZINI = kaynaklar.kaynak_yolu("backend", "app", "web", "static")


def uygulama_olustur(ayarlar: Ayarlar, analiz: bool = True) -> FastAPI:
    """Verilen ayarlarla FastAPI uygulaması kurar; şema açılışta uygulanır.

    analiz=False yalnızca testler içindir: kamera/tespit iş parçacığı başlamaz.
    """

    @asynccontextmanager
    async def yasam_dongusu(uygulama: FastAPI):
        log = loglama.log_al("sistem")
        # Kayıtların olağandışı bir klasörden okunduğu durum (paketlenmiş
        # programda eski konumda veri bulunması) SESSİZ kalmamalı: kullanıcı
        # yedeğini ararken hangi klasöre bakacağını bilmeli. Tam yol ekrana
        # değil, günlük dosyasındaki `ayrinti` alanına yazılır.
        if ayarlar.veri_konumu_notu:
            log.info(
                ayarlar.veri_konumu_notu,
                extra={"ayrinti": ayarlar.veri_konumu_ayrintisi},
            )
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
        # Veritabanının tam yolu Kontrol Paneli penceresinde görünmesin; destek
        # için günlük dosyasındaki `ayrinti` alanında durur (loglama.py).
        log.info(
            "Sistem hazır.",
            extra={"ayrinti": f"veritabanı: {ayarlar.veritabani_yolu}, şema: {surum}"},
        )

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
    # Alan tanıma ("Alanları Otomatik Bul"): kamera sayfasının yanında durur.
    # Yüklenen ekran görüntüsü DİSKE YAZILMAZ; ayrıntısı alan_rotalari.py'de.
    uygulama.include_router(alan_rotalari.router)
    uygulama.include_router(kurallar.router)
    uygulama.include_router(olaylar_web.router)
    uygulama.include_router(kkd_web.router)
    uygulama.include_router(anons_web.router)
    # Hoparlör bölgeleri (şema 002): anonsun hangi adrese gideceğini
    # belirler; ekranı Anons sistemi sayfasındadır.
    uygulama.include_router(hoparlorler.router)
    # Komuta kabuğu (/komuta…): tasarımın altı ekranı. Ana sayfa ve
    # kurulum sayfaları eski kabukta kalır; ikisi bağlantıyla geçer.
    uygulama.include_router(komuta.router)
    # Nesne kütüphanesi (şema 003): kullanıcının kendi nesnesini fotoğrafla
    # tanıtması. Komuta kabuğunu kullanır ama CANLI ANALİZE GİRMEZ — arama
    # yalnızca o sayfaya yüklenen fotoğraflarda yapılır.
    uygulama.include_router(nesne_rotalari.router)
    # Ayarlar sayfası: .env'in ekrandaki karşılığı. Paketlenmiş programda ayar
    # dosyası kullanıcı profilindedir ve elle açılamaz; eşik/anons ayarı için
    # tek yol budur.
    uygulama.include_router(ayar_rotalari.router)

    uygulama.mount("/static", StaticFiles(directory=str(STATIK_DIZINI)), name="static")
    return uygulama

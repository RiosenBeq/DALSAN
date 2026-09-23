"""FastAPI uygulama fabrikası.

main.py'den ayrı olmasının nedeni: main.py import edildiği anda gerçek .env'i
okur ve log sistemini kurar (uvicorn böyle bekler). Testler ise uygulamayı
geçici klasöre işaret eden ayarlarla, hiçbir yan etki olmadan kurabilmeli.
Bu yüzden yan etkisiz fabrika burada, yan etkili giriş noktası main.py'de.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app import kaynaklar, loglama, veritabani
from app.ayarlar import Ayarlar, geri_donus_adi_mi, sunucu_adi
from app.hatalar import VeritabaniHatasi, hata_yakalayicilari_kur
from app.web import (
    alan_rotalari,
    anons_web,
    ayar_rotalari,
    giris,
    hoparlorler,
    kameralar,
    kkd_web,
    komuta,
    kurallar,
    nesne_rotalari,
    olaylar_web,
    rapor,
    rotalar,
    videolar,
)
from app.web.kaynak_denetimi import KaynakDenetimi

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
        # Ağa açık kurulumda izinli ad yoksa başka cihazdan gelen her istek
        # 421 alır (web/kaynak_denetimi.py). Kullanıcı bunu sahada "sistem
        # açılmıyor" diye yaşamasın: Kontrol Paneli'nde ne yapacağı yazsın.
        if not geri_donus_adi_mi(sunucu_adi(ayarlar.sunucu_adresi)) and not (
            ayarlar.izinli_sunucu_adlari
        ):
            log.warning(
                "Sistem ağa açık ama İzinli sunucu adları boş: başka bir cihazdan "
                'sunucunun IP adresiyle açıldığında sayfa "Bu adrese izin verilmiyor" '
                "der. O adresi Ayarlar → Güvenlik → İzinli sunucu adları kutusuna "
                "yazıp sistemi yeniden başlatın (docs/15-UZAKTAN-ERISIM.md)."
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

    # /docs, /redoc ve /openapi.json KAPALI: bu uçlar sistemin bütün rotalarını
    # ve form alanlarını giriş istemeden listeliyordu (docs/17 §10.5). Bu
    # sistemin API tüketicisi yok; arayüzün kendisi belgedir.
    uygulama = FastAPI(
        title="DALSAN İSG",
        lifespan=yasam_dongusu,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    uygulama.state.ayarlar = ayarlar
    hata_yakalayicilari_kur(uygulama)
    # İSTEK KAYNAĞI — her şeyden önce: izinsiz sunucu adıyla gelen istek (DNS
    # yeniden bağlama) 421, başka siteden gönderilen form (CSRF) 403 alır.
    # Giriş kapısından da önce çalışır; ayrıntı web/kaynak_denetimi.py.
    uygulama.add_middleware(KaynakDenetimi)

    # YETKİ — tek kapı. .env'deki YONETICI_SIFRESI boşsa `oturum_gerekli`
    # hiçbir şey sormaz (tek makinede çalışan kurulum); doluysa aşağıdaki
    # routerların HEPSİ giriş ister. Ayrıntı: web/giris.py.
    #
    # Giriş sayfasının kendisi ve /saglik korumasızdır: birincisi olmadan
    # giriş yapılamaz, ikincisi Docker'ın sağlık yoklaması (docker-compose.yml)
    # ve sistem bilgisi taşımaz.
    korumali = [Depends(giris.oturum_gerekli)]
    uygulama.include_router(giris.router)
    uygulama.include_router(rotalar.acik_router)  # /saglik ve /favicon.ico
    uygulama.include_router(rotalar.router, dependencies=korumali)
    uygulama.include_router(kameralar.router, dependencies=korumali)
    # Video ile test (/videolar): yüklenen video, source_type='file' olan
    # sıradan bir kameraya dönüşür — bu yüzden kameraların hemen yanında durur.
    uygulama.include_router(videolar.router, dependencies=korumali)
    # Alan tanıma ("Alanları Otomatik Bul"): kamera sayfasının yanında durur.
    # Yüklenen ekran görüntüsü DİSKE YAZILMAZ; ayrıntısı alan_rotalari.py'de.
    uygulama.include_router(alan_rotalari.router, dependencies=korumali)
    uygulama.include_router(kurallar.router, dependencies=korumali)
    uygulama.include_router(olaylar_web.router, dependencies=korumali)
    uygulama.include_router(kkd_web.router, dependencies=korumali)
    uygulama.include_router(anons_web.router, dependencies=korumali)
    # Hoparlör bölgeleri (şema 002): anonsun hangi adrese gideceğini
    # belirler; ekranı Anons sistemi sayfasındadır.
    uygulama.include_router(hoparlorler.router, dependencies=korumali)
    # Komuta kabuğu (/komuta…): tasarımın altı ekranı. Ana sayfa ve
    # kurulum sayfaları eski kabukta kalır; ikisi bağlantıyla geçer.
    uygulama.include_router(komuta.router, dependencies=korumali)
    # Dönem raporu (/komuta/rapor): komuta kabuğunun içindedir ama veri
    # hazırlığı ayrı dosyadadır — komuta.py zaten altı ekranın verisini taşıyor.
    uygulama.include_router(rapor.router, dependencies=korumali)
    # Nesne kütüphanesi (şema 003): kullanıcının kendi nesnesini fotoğrafla
    # tanıtması. Komuta kabuğunu kullanır ama CANLI ANALİZE GİRMEZ — arama
    # yalnızca o sayfaya yüklenen fotoğraflarda yapılır.
    uygulama.include_router(nesne_rotalari.router, dependencies=korumali)
    # Ayarlar sayfası: .env'in ekrandaki karşılığı. Paketlenmiş programda ayar
    # dosyası kullanıcı profilindedir ve elle açılamaz; eşik/anons ayarı için
    # tek yol budur.
    uygulama.include_router(ayar_rotalari.router, dependencies=korumali)

    uygulama.mount("/static", StaticFiles(directory=str(STATIK_DIZINI)), name="static")
    return uygulama

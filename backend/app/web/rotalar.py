"""Ana sayfa (teşhis ekranı) ve veritabanı yedeği."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.templating import Jinja2Templates

from app import kaynaklar, veritabani, zaman
from app.analiz.model_adi import gorunen_model_adi
from app.hatalar import VeritabaniHatasi
from app.loglama import log_al
from app.olaylar.kanallar import acik_kanal_sayisi, kanal_ozeti
from app.rules.olay_kodu import IHLAL_ONEMLERI, ONEM_ADLARI
from app.web.kilavuz import kalibrasyon_bekleyen_kurallar
from app.web.ortak import (
    ANONS_OGELERI,
    BOLGE_SIMGELERI,
    OGE_IHLAL_ADLARI,
    OGELER,
    OLAY_DURUMLARI,
    SAGLIK_SORUN_METINLERI,
    SINIF_OGELERI,
    SINIFLAR,
    baglanti_al,
    sayi_eki,
)

router = APIRouter()

# Şablonların yeri app/kaynaklar.py'den çözülür (paketlenmiş programda
# dosyalar depoda değil, paketin açıldığı geçici klasördedir).
SABLON_DIZINI = kaynaklar.kaynak_yolu("backend", "app", "web", "templates")
sablonlar = Jinja2Templates(directory=str(SABLON_DIZINI))
# Türkçe ek süzgeci: "%{{ x }}{{ x|sayi_eki }}" → "%36'sı". Ek sabit yazılamaz,
# sayının okunuşuna göre değişir (bkz. web/ortak.py sayi_eki).
sablonlar.env.filters["sayi_eki"] = sayi_eki


def _sifre_kurulu(istek) -> bool:
    """Şablonlar için: giriş şifresi tanımlı mı?

    Jinja globali olarak verilir; böylece çıkış düğmesini ve "şifre yok"
    uyarısını göstermek için yirmi rotanın bağlamına alan eklemek gerekmez.
    Şifrenin KENDİSİ şablona hiç geçmez — yalnızca doğru/yanlış.
    """
    return bool(getattr(istek.app.state.ayarlar, "yonetici_sifresi", ""))


sablonlar.env.globals["sifre_kurulu"] = _sifre_kurulu

# Öğe dili (web/ortak.py → OGELER): her şablon aynı tablodan okur, böylece
# forklift her ekranda aynı simge ve renkle görünür. Bileşen makroları
# templates/bilesen.html'dedir.
sablonlar.env.globals["OGELER"] = OGELER
sablonlar.env.globals["SINIF_OGELERI"] = SINIF_OGELERI
sablonlar.env.globals["ANONS_OGELERI"] = ANONS_OGELERI
sablonlar.env.globals["BOLGE_SIMGELERI"] = BOLGE_SIMGELERI
# Kılavuzun simge sözlüğü bu iki tablodan üretilir; elle yazılmış bir
# liste, yeni öğe eklendiğinde kılavuzda eksik kalırdı.
sablonlar.env.globals["OGE_IHLAL_ADLARI"] = OGE_IHLAL_ADLARI
sablonlar.env.globals["OLAY_DURUMLARI"] = OLAY_DURUMLARI
# Önem hapları kılavuzda da aynı makroyla çizilir (bilesen.html onem_hapi)
sablonlar.env.globals["IHLAL_ONEMLERI"] = IHLAL_ONEMLERI
sablonlar.env.globals["ONEM_ADLARI"] = ONEM_ADLARI
# Komuta şeridinin sorun metinleri (static/sistem_seridi.js); "hazır değil"i
# açıklayan kodlar HAZIRLIGI_BOZAN_SORUNLAR'ın yanında globale verilir.
sablonlar.env.globals["SAGLIK_SORUN_METINLERI"] = SAGLIK_SORUN_METINLERI

# GİRİŞ İSTEMEYEN rotalar. Yalnız iki tane vardır ve ikisi de sistem bilgisi
# taşımaz: tarayıcı simgesi ve canlılık yoklaması. Ayrı bir router olmalarının
# nedeni, uygulama fabrikasının (uygulama.py) diğer her şeyi tek satırda yetki
# kapısının arkasına koyabilmesidir — "hangi rota korumasızdı" sorusunun
# cevabı tek yerde durur.
acik_router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def ana_sayfa(istek: Request, yedek: str = "", baglanti=Depends(baglanti_al)):
    ayarlar = istek.app.state.ayarlar
    surum = veritabani.mevcut_surum(baglanti)
    tablolar = veritabani.tablo_adlari(baglanti)
    kamera_sayisi = baglanti.execute("SELECT COUNT(*) AS n FROM cameras").fetchone()["n"]

    disk = shutil.disk_usage(ayarlar.veri_dizini)

    # Son 24 saatin olay sayıları — "sistem gerçekten çalışıyor mu" sorusunun
    # ekrandaki tek cevabı (docs/01 §3.5)
    gun_siniri = zaman.gun_once_utc(1)
    ihlal_24s = baglanti.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'violation' AND occurred_at >= ?",
        (gun_siniri,),
    ).fetchone()["n"]
    yeni_ihlal = baglanti.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'violation' AND status = 'new'"
    ).fetchone()["n"]

    supervizor = getattr(istek.app.state, "supervizor", None)
    if supervizor is None:
        model_durumu, model_hatasi = "kapali", "analiz başlatılmadı"
        # Analiz kapalıyken de kanal durumu bilinir: tanım veritabanındadır
        anons_durumu = kanal_ozeti(acik_kanal_sayisi(baglanti))
    else:
        # yukleniyor | indiriliyor | hazir | hata (supervizor.model_durumu)
        model_durumu = supervizor.model_durumu
        model_hatasi = supervizor.tespit_hatasi or ""
        anons_durumu = supervizor._anons.ad

    canli_sayim = supervizor.toplam_canli_sayim() if supervizor is not None else {}

    return sablonlar.TemplateResponse(
        istek,
        "ana_sayfa.html",
        {
            "aktif_sekme": "ana",
            "sunucu_saati": zaman.ekranda_goster(zaman.simdi_utc()),
            "sema_surumu": surum or "uygulanmamış",
            "tablo_sayisi": len(tablolar),
            "veritabani_yolu": _kokten_yol(ayarlar.veritabani_yolu, ayarlar.kok_dizin),
            "kamera_sayisi": kamera_sayisi,
            "ayar_satirlari": _ayar_satirlari(ayarlar),
            # Sessiz bozulmayı görünür kılar (analiz/ortam.py). Olağan
            # kurulumda boştur ve ekranda hiçbir şey çizilmez.
            "ortam_uyarisi": _ortam_uyarisi(),
            "veri_boyutu": _okunur_boyut(_klasor_boyutu(ayarlar.veri_dizini)),
            "disk_bos": _okunur_boyut(disk.free),
            "disk_toplam": _okunur_boyut(disk.total),
            "model_durumu": model_durumu,
            "model_hatasi": model_hatasi,
            "cihaz_uyarisi": getattr(supervizor, "cihaz_uyarisi", "") if supervizor else "",
            "canli_sayim": [
                (SINIFLAR.get(sinif, sinif), adet) for sinif, adet in sorted(canli_sayim.items())
            ],
            "ihlal_24s": ihlal_24s,
            "yeni_ihlal": yeni_ihlal,
            "model_adi": gorunen_model_adi(ayarlar.model_dosyasi.name),
            "anons_durumu": anons_durumu,
            "son_yedek": _son_yedek(ayarlar),
            "yedek_sonucu": "Yedek alındı: veri/yedekler/ klasörüne kaydedildi."
            if yedek == "ok"
            else "",
        },
    )


@acik_router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Tarayıcının kök dizinden istediği simge.

    Sayfa şablonları simgeyi zaten <link rel="icon"> ile bildiriyor, ama
    tarayıcı HTML OLMAYAN yanıtlarda (ör. /saglik'in JSON'u) o etiketi
    göremez ve /favicon.ico'yu dener. Bu rota olmadan her böyle istekte
    tarayıcı konsoluna 404 düşüyordu — sistemde bir arıza olduğu izlenimi
    veren, aslında olmayan bir hata.
    """
    simge = kaynaklar.kaynak_yolu("backend", "app", "web", "static", "logo.svg")
    if not simge.is_file():
        return Response(status_code=204)
    return FileResponse(simge, media_type="image/svg+xml")


# "hazir" değerini bozan sorunlar (docs/17 §9.1). Öbürleri (ör.
# kritik_kural_pasif, ort_paket_cakismasi) listede görünür ama hazırlığı
# bozmaz: yapılandırma eksiğidir, hizmet arızası değil — Docker healthcheck'i
# "unhealthy" yapmamalı. Ekran yine kırmızı gösterir.
HAZIRLIGI_BOZAN_SORUNLAR = frozenset(
    {
        "analiz_takildi",
        "analiz_olu",
        "model_yuklenemedi",
        "veritabani_acilamadi",
        "olay_yazilamadi",
    }
)
sablonlar.env.globals["HAZIRLIGI_BOZAN_SORUNLAR"] = sorted(HAZIRLIGI_BOZAN_SORUNLAR)


@acik_router.get("/saglik")
def saglik(istek: Request, ayrinti: int = 0, hazirlik: int = 0):
    """Docker healthcheck, Kontrol Paneli ve komuta şeridi için sağlık (docs/17 §9.1).

    Her koşulda 200 ve `durum: "calisiyor"` döner: Kontrol Paneli'nin "bu
    port bizim sunucumuz mu" sorusu (`bizim_sunucumuz_mu`) buna bakar. Tek
    istisna `?hazirlik=1`: sistem hazır değilse 503 (Docker healthcheck).

    Kimliksiz gövde DARDIR: durum, analiz, model, hazır ve sorun KODLARI.
    Kamera ölçümleri, disk ve analiz tur yaşı yalnız `?ayrinti=1` ve geçerli
    oturumla gelir (şifre tanımlı değilse oturum gerekmez). Ucuzdur: ana
    sayfanın aksine veri/ klasörünü taramaz.
    """
    from app.web.giris import oturum_gecerli_mi  # döngüsel içe aktarma: giris → rotalar

    ayarlar = istek.app.state.ayarlar
    supervizor = getattr(istek.app.state, "supervizor", None)
    model = getattr(supervizor, "model_durumu", "kapali") if supervizor else "kapali"
    sorunlar = _saglik_sorunlari(ayarlar)
    # Sağlık ucu hiçbir durumda düşmemeli: yöntemi olmayan nesne boş liste sayılır
    sorunlar += getattr(supervizor, "sorunlar", list)()
    # Hazırlığı bozanlar başa: şerit ve Kontrol Paneli metinleri bu sırayla
    # birleştirir; "model yüklenemedi" bir yapılandırma notunun arkasında kalmasın.
    sorunlar.sort(key=lambda kod: kod not in HAZIRLIGI_BOZAN_SORUNLAR)
    hazir = (
        supervizor is not None
        and model == "hazir"
        and not HAZIRLIGI_BOZAN_SORUNLAR.intersection(sorunlar)
    )
    govde = {
        "durum": "calisiyor",
        "analiz": supervizor is not None,
        "model": model,
        "hazir": hazir,
        "sorunlar": sorunlar,
    }
    if ayrinti and oturum_gecerli_mi(istek):
        govde.update(_saglik_ayrintisi(ayarlar, supervizor))
    if hazirlik and not hazir:
        return JSONResponse(govde, status_code=503)
    return govde


def _saglik_sorunlari(ayarlar) -> list[str]:
    try:
        baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
        try:
            bekleyen = kalibrasyon_bekleyen_kurallar(baglanti)
        finally:
            baglanti.close()
    except (sqlite3.Error, VeritabaniHatasi) as hata:
        # Sağlık ucu her durumda cevap verir; veritabanı okunamıyorsa bu da
        # bir sorundur ve söylenir.
        log_al("sistem").warning(f"Sağlık denetimi veritabanını okuyamadı: {hata}")
        return ["veritabani_acilamadi"]
    return ["kritik_kural_pasif"] if bekleyen else []


def _saglik_ayrintisi(ayarlar, supervizor) -> dict:
    """Oturumlu ayrıntı: kamera ölçümleri (id ile, ad yok), boş disk, tur yaşı."""
    ayrinti: dict = {"bos_disk_gb": None, "analiz_tur_yasi_sn": None, "kameralar": []}
    try:
        ayrinti["bos_disk_gb"] = round(shutil.disk_usage(ayarlar.veri_dizini).free / 1024**3, 1)
    except OSError as hata:
        log_al("sistem").warning(f"Boş disk alanı okunamadı: {hata}")
    if supervizor is not None:
        try:
            ayrinti["analiz_tur_yasi_sn"] = supervizor.analiz_tur_yasi()
            ayrinti["kameralar"] = supervizor.kamera_saglik_ozeti()
        except Exception as hata:  # noqa: BLE001 — sağlık ucu 200 dönmeye devam etmeli
            log_al("sistem").error(f"Sağlık ayrıntısı toplanamadı: {hata}", exc_info=hata)
    return ayrinti


@router.post("/yedekle")
def yedekle(istek: Request):
    """Veritabanının güvenli anlık kopyası (SQLite backup API — WAL uyumlu)."""
    ayarlar = istek.app.state.ayarlar
    hedef_dizin = ayarlar.veri_dizini / "yedekler"
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    damga = zaman.simdi_utc().replace(":", "-").replace("+", "Z")
    hedef = hedef_dizin / f"dalsan-{damga}.db"
    try:
        kaynak = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
        try:
            yedek_baglanti = sqlite3.connect(str(hedef))
            try:
                kaynak.backup(yedek_baglanti)
            finally:
                yedek_baglanti.close()
        finally:
            kaynak.close()
    except sqlite3.Error as hata:
        raise VeritabaniHatasi(f"Yedek alınamadı: {hata}") from hata
    return RedirectResponse("/?yedek=ok", status_code=303)


def _son_yedek(ayarlar) -> str:
    yedekler = sorted((ayarlar.veri_dizini / "yedekler").glob("dalsan-*.db"))
    if not yedekler:
        return "Henüz yedek alınmadı"
    return yedekler[-1].name


def _ayar_satirlari(ayarlar) -> list[tuple[str, str]]:
    """Ana sayfada gösterilecek aktif ayarlar."""
    kok = ayarlar.kok_dizin
    return [
        ("Veritabanı dosyası", _kokten_yol(ayarlar.veritabani_yolu, kok)),
        ("Görüntü klasörü", _kokten_yol(ayarlar.goruntu_klasoru, kok)),
        ("Log dosyası", _kokten_yol(ayarlar.log_dosyasi, kok)),
        ("Olay saklama", f"{ayarlar.olay_saklama_gun} gün"),
        ("Görüntü saklama", f"{ayarlar.goruntu_saklama_gun} gün"),
        ("KKD ham veri saklama", f"{ayarlar.kkd_ham_veri_saklama_gun} gün"),
        ("Çıkarım cihazı", ayarlar.cikarim_cihazi),
        ("Kare örnekleme", f"{ayarlar.kare_ornekleme_fps} fps"),
        ("Tespit modeli", gorunen_model_adi(ayarlar.model_dosyasi.name)),
        ("Anons tekrar aralığı", f"{ayarlar.anons_bekleme_sn} sn"),
    ]


def _ortam_uyarisi() -> str:
    """Kurulu OpenCV sürümü beklenenden farklıysa tek satırlık uyarı.

    Import BİLEREK fonksiyonun içinde: bu modül testlerde OpenCV kurulu
    olmadan da import edilebilmeli (analiz=False kurulumu).
    """
    from app.analiz.ortam import opencv_uyarisi

    return opencv_uyarisi()


def _kokten_yol(yol: Path, kok: Path) -> str:
    try:
        return str(yol.relative_to(kok))
    except ValueError:
        return str(yol)


def _klasor_boyutu(klasor: Path) -> int:
    toplam = 0
    for dosya in klasor.rglob("*"):
        try:
            if dosya.is_file():
                toplam += dosya.stat().st_size
        except FileNotFoundError:
            # Tarama sırasında silinen dosya (SQLite -wal/-shm, log rotasyonu) — atla.
            continue
    return toplam


def _okunur_boyut(bayt: float) -> str:
    for birim in ("B", "KB", "MB", "GB"):
        if bayt < 1024:
            sayi = f"{bayt:.0f}" if birim == "B" else f"{bayt:.1f}".replace(".", ",")
            return f"{sayi} {birim}"
        bayt /= 1024
    return f"{bayt:.1f}".replace(".", ",") + " TB"

"""Ana sayfa (teşhis ekranı) ve veritabanı yedeği."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import veritabani, zaman
from app.hatalar import VeritabaniHatasi
from app.web.ortak import SINIFLAR, baglanti_al

router = APIRouter()

SABLON_DIZINI = Path(__file__).resolve().parent / "templates"
sablonlar = Jinja2Templates(directory=str(SABLON_DIZINI))


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
        anons_durumu = "—"
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
            "model_adi": ayarlar.model_dosyasi.name,
            "anons_durumu": anons_durumu,
            "son_yedek": _son_yedek(ayarlar),
            "yedek_sonucu": "Yedek alındı: veri/yedekler/ klasörüne kaydedildi."
            if yedek == "ok"
            else "",
        },
    )


@router.get("/saglik")
def saglik(istek: Request):
    """Docker healthcheck ve Kontrol Paneli için UCUZ canlılık kontrolü.

    Ana sayfa veri/ klasörünün tamamını tarayıp boyut hesaplar; 30 saniyede bir
    onu çağırmak, olay fotoğrafları biriktikçe diski gereksiz yere okur.
    """
    supervizor = getattr(istek.app.state, "supervizor", None)
    return {
        "durum": "calisiyor",
        "analiz": supervizor is not None,
        "model": getattr(supervizor, "model_durumu", "kapali") if supervizor else "kapali",
    }


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
        ("Tespit modeli", ayarlar.model_dosyasi.name),
        ("Anons", ayarlar.anons),
    ]


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

"""Web rotaları. Şimdilik tek sayfa: teşhis amaçlı ana sayfa."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import veritabani, zaman

router = APIRouter()

SABLON_DIZINI = Path(__file__).resolve().parent / "templates"
sablonlar = Jinja2Templates(directory=str(SABLON_DIZINI))


@router.get("/", response_class=HTMLResponse)
def ana_sayfa(istek: Request) -> HTMLResponse:
    ayarlar = istek.app.state.ayarlar

    baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
    try:
        surum = veritabani.mevcut_surum(baglanti)
        tablolar = veritabani.tablo_adlari(baglanti)
        kamera_sayisi = baglanti.execute("SELECT COUNT(*) AS n FROM cameras").fetchone()["n"]
    finally:
        baglanti.close()

    disk = shutil.disk_usage(ayarlar.veri_dizini)

    return sablonlar.TemplateResponse(
        istek,
        "ana_sayfa.html",
        {
            "sunucu_saati": zaman.ekranda_goster(zaman.simdi_utc()),
            "sema_surumu": surum or "uygulanmamış",
            "tablo_sayisi": len(tablolar),
            "tablolar": ", ".join(tablolar),
            "veritabani_yolu": _kokten_yol(ayarlar.veritabani_yolu, ayarlar.kok_dizin),
            "kamera_sayisi": kamera_sayisi,
            "ayar_satirlari": _ayar_satirlari(ayarlar),
            "veri_boyutu": _okunur_boyut(_klasor_boyutu(ayarlar.veri_dizini)),
            "disk_bos": _okunur_boyut(disk.free),
            "disk_toplam": _okunur_boyut(disk.total),
        },
    )


def _ayar_satirlari(ayarlar) -> list[tuple[str, str]]:
    """Ana sayfada gösterilecek aktif ayarlar. Şifre MASKELİ (KVKK/hijyen).

    İleride kamera RTSP adresleri de aynı kuralla maskelenecek
    (docs/01 §3.6: RTSP kimlik bilgisi maskeleme).
    """
    kok = ayarlar.kok_dizin
    return [
        ("Yönetici şifresi", "••••••••  (maskeli)"),
        ("Veritabanı dosyası", _kokten_yol(ayarlar.veritabani_yolu, kok)),
        ("Görüntü klasörü", _kokten_yol(ayarlar.goruntu_klasoru, kok)),
        ("Log dosyası", _kokten_yol(ayarlar.log_dosyasi, kok)),
        ("Olay saklama", f"{ayarlar.olay_saklama_gun} gün"),
        ("Görüntü saklama", f"{ayarlar.goruntu_saklama_gun} gün"),
        ("KKD ham veri saklama", f"{ayarlar.kkd_ham_veri_saklama_gun} gün"),
        ("Çıkarım cihazı", ayarlar.cikarim_cihazi),
        ("Kare örnekleme", f"{ayarlar.kare_ornekleme_fps} fps"),
        ("Anons", ayarlar.anons),
    ]


def _kokten_yol(yol: Path, kok: Path) -> str:
    """Yolu depo köküne göre kısaltır; kök dışındaysa olduğu gibi gösterir."""
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

"""Nesneler sayfası: kendi nesneni fotoğrafla tanıt, yüklediğin fotoğrafta ara.

KAPSAM — ekranda da yazan cümle: burada tanıtılan nesne CANLI KAMERALARDA
ARANMAZ. Kural motoru, canlı boru hattı ve olay kayıtları bu sayfadan
etkilenmez; arama yalnızca bu sayfaya yüklenen fotoğraflarda yapılır. Bu sınır
bilinçlidir ve kullanıcı "tanıttım ama kamera görmüyor" demesin diye hem
sayfanın en üstünde hem kılavuzda yazılıdır (canlı arama: docs/07).

ALAN mı NESNE mi: yaya yolu, yükleme alanı gibi YERLER kamera sayfasında bölge
çizilerek tanıtılır ve canlı kurallara girer. Bu sayfa ise TAŞINABİLİR EŞYALAR
içindir ve canlıya girmez.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from app.hatalar import DogrulamaHatasi
from app.nesneler import arama, depo
from app.web.komuta import kabuk_baglami
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()

# Dosya okunurken bellekte tutulacak parça boyutu
_PARCA = 1024 * 1024


@router.get("/nesneler", response_class=HTMLResponse)
def nesneler_sayfasi(
    istek: Request, hata: str = "", mesaj: str = "", baglanti=Depends(baglanti_al)
):
    return sablonlar.TemplateResponse(
        istek, "komuta_nesneler.html", _sayfa_baglami(istek, baglanti, hata=hata, mesaj=mesaj)
    )


def _sayfa_baglami(
    istek: Request,
    baglanti,
    hata: str = "",
    mesaj: str = "",
    sonuclar: list | None = None,
    esik: float | None = None,
) -> dict:
    ayarlar = istek.app.state.ayarlar
    baglam = kabuk_baglami(istek, baglanti, "nesneler")
    baglam.update(
        {
            "nesneler": depo.nesneleri_listele(baglanti),
            "hata": hata,
            "mesaj": mesaj,
            "sonuclar": sonuclar or [],
            "esik_yuzde": round((esik if esik is not None else ayarlar.nesne_eslesme_esigi) * 100),
            "en_cok_dosya": ayarlar.nesne_tarama_en_cok_dosya,
            "en_buyuk_mb": ayarlar.nesne_foto_en_buyuk_mb,
            "izinli_uzantilar": ", ".join(
                u.lstrip(".").upper() for u in ayarlar.nesne_izinli_uzantilar
            ),
            "kabul_ozniteligi": ",".join(
                f"image/{u.lstrip('.').replace('jpg', 'jpeg')}"
                for u in ayarlar.nesne_izinli_uzantilar
            ),
        }
    )
    return baglam


def _sayfaya_don(hata: str = "", mesaj: str = "") -> RedirectResponse:
    if hata:
        return RedirectResponse(f"/nesneler?hata={quote(hata)}", status_code=303)
    if mesaj:
        return RedirectResponse(f"/nesneler?mesaj={quote(mesaj)}", status_code=303)
    return RedirectResponse("/nesneler", status_code=303)


async def _oku(dosya: UploadFile, en_buyuk_mb: int) -> bytes | None:
    """Yüklenen dosyayı sınırlı okur. Sınır aşılırsa None (bellek dolmasın)."""
    sinir = en_buyuk_mb * 1024 * 1024
    veri = bytearray()
    while parca := await dosya.read(_PARCA):
        veri.extend(parca)
        if len(veri) > sinir:
            return None
    return bytes(veri)


async def _fotograflari_kaydet(
    istek: Request, baglanti, nesne_id: int, dosyalar
) -> tuple[int, list[str]]:
    """Fotoğrafları tek tek kaydeder; biri bozuksa diğerleri yine de eklenir."""
    ayarlar = istek.app.state.ayarlar
    eklendi, atlanan = 0, []
    for dosya in dosyalar:
        icerik = await _oku(dosya, ayarlar.nesne_foto_en_buyuk_mb)
        if icerik is None:
            atlanan.append(
                f"'{dosya.filename}' çok büyük (en fazla {ayarlar.nesne_foto_en_buyuk_mb} MB)."
            )
            continue
        try:
            depo.fotograf_ekle(
                baglanti,
                ayarlar.nesne_klasoru,
                nesne_id,
                dosya.filename,
                icerik,
                ayarlar.nesne_izinli_uzantilar,
                ayarlar.nesne_foto_en_buyuk_mb,
            )
            eklendi += 1
        except DogrulamaHatasi as hata:
            atlanan.append(hata.kullanici_mesaji)
    return eklendi, atlanan


def _ozet_mesaji(eklendi: int, atlanan: list[str], on_ek: str = "") -> str:
    mesaj = f"{on_ek}{eklendi} fotoğraf eklendi."
    if atlanan:
        mesaj += f" {len(atlanan)} dosya alınamadı: {atlanan[0]}"
    return mesaj


@router.post("/nesneler/ekle")
async def nesne_olustur(
    istek: Request,
    ad: str = Form(...),
    aciklama: str = Form(""),
    fotograflar: list[UploadFile] = None,  # noqa: RUF013 — FastAPI çoklu dosya deyimi
    baglanti=Depends(baglanti_al),
):
    dosyalar = [d for d in fotograflar or [] if d.filename]
    if not dosyalar:
        return _sayfaya_don(
            hata="Fotoğraf seçilmedi. Nesneyi tanıtmak için farklı açılardan 3-8 fotoğraf yükleyin."
        )
    try:
        nesne_id = depo.nesne_ekle(baglanti, ad, aciklama)
    except DogrulamaHatasi as hata:
        return _sayfaya_don(hata=hata.kullanici_mesaji)

    eklendi, atlanan = await _fotograflari_kaydet(istek, baglanti, nesne_id, dosyalar)
    if eklendi == 0:
        # Hiç fotoğraf kaydedilemediyse yarım nesne bırakma: adı olan ama izi
        # olmayan nesne, taramada hiçbir işe yaramaz ve kullanıcıyı yanıltır.
        depo.nesne_sil(baglanti, istek.app.state.ayarlar.nesne_klasoru, nesne_id)
        return _sayfaya_don(hata=atlanan[0])
    return _sayfaya_don(mesaj=_ozet_mesaji(eklendi, atlanan, on_ek=f"'{ad.strip()}' eklendi: "))


@router.post("/nesneler/{nesne_id}/fotograf")
async def fotograf_yukle(
    istek: Request,
    nesne_id: int,
    fotograflar: list[UploadFile] = None,  # noqa: RUF013
    baglanti=Depends(baglanti_al),
):
    dosyalar = [d for d in fotograflar or [] if d.filename]
    if not dosyalar:
        return _sayfaya_don(hata="Fotoğraf seçilmedi. Farklı açılardan 3-8 fotoğraf önerilir.")
    eklendi, atlanan = await _fotograflari_kaydet(istek, baglanti, nesne_id, dosyalar)
    if eklendi == 0:
        return _sayfaya_don(hata=atlanan[0])
    return _sayfaya_don(mesaj=_ozet_mesaji(eklendi, atlanan))


@router.post("/nesneler/{nesne_id}/sil")
def nesne_sil(istek: Request, nesne_id: int, baglanti=Depends(baglanti_al)):
    depo.nesne_sil(baglanti, istek.app.state.ayarlar.nesne_klasoru, nesne_id)
    return _sayfaya_don(mesaj="Nesne ve fotoğrafları silindi.")


@router.post("/nesneler/fotograf/{foto_id}/sil")
def foto_sil(istek: Request, foto_id: int, baglanti=Depends(baglanti_al)):
    depo.fotograf_sil(baglanti, istek.app.state.ayarlar.nesne_klasoru, foto_id)
    return _sayfaya_don(mesaj="Fotoğraf kaldırıldı.")


@router.get("/nesneler/foto/{ad}")
def nesne_fotografi(istek: Request, ad: str):
    return _guvenli_dosya(istek.app.state.ayarlar.nesne_klasoru, ad)


@router.get("/nesneler/tarama-foto/{ad}")
def tarama_fotografi(istek: Request, ad: str):
    return _guvenli_dosya(istek.app.state.ayarlar.nesne_tarama_klasoru, ad)


def _guvenli_dosya(kok: Path, ad: str) -> Response:
    """Yalnızca kendi klasörünün İÇİNDEKİ dosyayı sunar (../ ile dışarı çıkılamaz)."""
    kok = kok.resolve()
    dosya = (kok / ad).resolve()
    if not dosya.is_relative_to(kok) or not dosya.is_file():
        return Response(status_code=404)
    tur = "image/png" if dosya.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(dosya, media_type=tur)


@router.post("/nesneler/tara", response_class=HTMLResponse)
async def tarama_yap(
    istek: Request,
    kareler: list[UploadFile] = None,  # noqa: RUF013
    esik_yuzde: str = Form(""),
    baglanti=Depends(baglanti_al),
):
    """Yüklenen fotoğraflarda kütüphanedeki nesneleri arar.

    Ağır iş (kod çözme + pencere taraması) iş parçacığı havuzunda koşar; yoksa
    tarama sürerken sistemin bütün sayfaları donardı.
    """
    ayarlar = istek.app.state.ayarlar
    dosyalar = [d for d in (kareler or []) if d.filename]
    if not dosyalar:
        return _sayfaya_don(hata="Dosya seçilmedi. Aranacak fotoğrafları yükleyin.")
    if len(dosyalar) > ayarlar.nesne_tarama_en_cok_dosya:
        return _sayfaya_don(
            hata=f"Bir taramada en fazla {ayarlar.nesne_tarama_en_cok_dosya} fotoğraf "
            f"işlenir; {len(dosyalar)} dosya seçilmiş."
        )

    esik = _esigi_coz(esik_yuzde, ayarlar.nesne_eslesme_esigi)

    yukler: list[tuple[str, bytes | None]] = []
    for dosya in dosyalar:
        yukler.append((dosya.filename, await _oku(dosya, ayarlar.nesne_foto_en_buyuk_mb)))

    def _isle():
        nesneler = depo.nesneleri_yukle(baglanti, ayarlar.nesne_klasoru)
        sonuclar = []
        for ad, veri in yukler:
            if veri is None:
                sonuclar.append(
                    arama.TaramaSonucu(
                        dosya_adi=ad,
                        uyari=f"'{ad}' çok büyük (en fazla {ayarlar.nesne_foto_en_buyuk_mb} MB).",
                    )
                )
                continue
            gorsel = cv2.imdecode(np.frombuffer(veri, np.uint8), cv2.IMREAD_COLOR)
            if gorsel is None:
                sonuclar.append(
                    arama.TaramaSonucu(
                        dosya_adi=ad,
                        uyari=f"'{ad}' bir fotoğraf olarak açılamadı "
                        "(bozuk ya da desteklenmeyen tür).",
                    )
                )
                continue
            sonuclar.append(arama.tara(gorsel, ad, nesneler, ayarlar.nesne_tarama_klasoru, esik))
        arama.eski_taramalari_temizle(ayarlar.nesne_tarama_klasoru)
        return sonuclar

    sonuclar = await run_in_threadpool(_isle)
    return sablonlar.TemplateResponse(
        istek, "komuta_nesneler.html", _sayfa_baglami(istek, baglanti, sonuclar=sonuclar, esik=esik)
    )


def _esigi_coz(ham: str, varsayilan: float) -> float:
    """Formdaki yüzdeyi 0-1 arası orana çevirir; boş/bozuksa .env değerine düşer."""
    metin = (ham or "").replace(",", ".").strip()
    if not metin:
        return varsayilan
    try:
        yuzde = float(metin)
    except ValueError:
        return varsayilan
    return min(max(yuzde, 5.0), 95.0) / 100

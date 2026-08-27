"""Forklift veri sayfası: araç görülen kareleri etiketleme (docs/08 R1).

Hazır modelde forklift sınıfı yoktur; sistem araç tespit edilen karelerden
otomatik örnek biriktirir. Kullanıcı her karedeki aday kutuyu üç düğmeyle
etiketler: Forklift / Değil / Belirsiz. 300-800 etiketli kare birikince
modele ince ayar yapılır (3-4. hafta işi).

Düzen bilerek KKD etiketleme sayfasıyla birebirdir — kullanıcı ikinci bir
arayüz öğrenmesin.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()

_ETIKETLER = ("yes", "no", "unknown")

# docs/08 R1: ince ayar için hedeflenen etiketli kare aralığı
HEDEF_EN_AZ = 300
HEDEF_EN_COK = 800


def _aktif_model(istek: Request) -> dict | None:
    """Devredeki forklift modelinin kaydı (models/forklift/aktif.json) — yoksa None."""
    aktif = istek.app.state.ayarlar.forklift_model_klasoru / "aktif.json"
    if not aktif.is_file():
        return None
    try:
        return json.loads(aktif.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _kutu_stili(bbox_json: str) -> str | None:
    """Normalize bbox'ı, kare görüntüsünün üzerine bindirilecek yüzde
    konumlu CSS'e çevirir. Bozuk kayıtta None — kart kutusuz gösterilir."""
    try:
        x1, y1, x2, y2 = (float(v) for v in json.loads(bbox_json))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        return None
    return (
        f"left:{x1 * 100:.1f}%;top:{y1 * 100:.1f}%;"
        f"width:{(x2 - x1) * 100:.1f}%;height:{(y2 - y1) * 100:.1f}%"
    )


@router.get("/forklift", response_class=HTMLResponse)
def forklift_sayfasi(istek: Request, baglanti=Depends(baglanti_al)):
    sayilar = baglanti.execute(
        "SELECT COUNT(*) AS toplam, "
        "SUM(CASE WHEN labeled_at IS NOT NULL THEN 1 ELSE 0 END) AS etiketli, "
        "SUM(CASE WHEN label = 'yes' THEN 1 ELSE 0 END) AS forklift, "
        "SUM(CASE WHEN label = 'no' THEN 1 ELSE 0 END) AS degil, "
        "SUM(CASE WHEN label = 'unknown' THEN 1 ELSE 0 END) AS belirsiz "
        "FROM forklift_samples"
    ).fetchone()

    ornekler = []
    for satir in baglanti.execute(
        "SELECT s.*, c.name AS kamera_adi FROM forklift_samples s "
        "LEFT JOIN cameras c ON c.id = s.camera_id "
        "WHERE s.labeled_at IS NULL ORDER BY s.captured_at DESC LIMIT 24"
    ):
        ornek = dict(satir)
        ornek["yerel_zaman"] = zaman.ekranda_goster(ornek["captured_at"])
        ornek["kutu_stili"] = _kutu_stili(ornek["bbox"])
        ornekler.append(ornek)

    from app.egitim.forklift_egitim import EN_AZ_NEGATIF, EN_AZ_POZITIF

    etiketli = sayilar["etiketli"] or 0
    return sablonlar.TemplateResponse(
        istek,
        "forklift.html",
        {
            "aktif_sekme": "forklift",
            "sayilar": dict(sayilar),
            "ornekler": ornekler,
            "hedef_en_az": HEDEF_EN_AZ,
            "hedef_en_cok": HEDEF_EN_COK,
            "ilerleme_yuzde": min(100, round(etiketli * 100 / HEDEF_EN_AZ)),
            "aktif_model": _aktif_model(istek),
            "egitim_hazir": (sayilar["forklift"] or 0) >= EN_AZ_POZITIF
            and (sayilar["degil"] or 0) >= EN_AZ_NEGATIF,
            "egitim_en_az_pozitif": EN_AZ_POZITIF,
            "egitim_en_az_negatif": EN_AZ_NEGATIF,
        },
    )


@router.post("/forklift/egit", response_class=HTMLResponse)
def egitimi_calistir(istek: Request, baglanti=Depends(baglanti_al)):
    """Eğitimi çalıştırır, eski/yeni karşılaştırmasını sayılarla gösterir.

    Birkaç yüz kareyle eğitim saniyeler sürer; bu yüzden istek içinde
    eşzamanlı çalışır — ayrı iş kuyruğu eklemeye değmez (CLAUDE.md §3).
    """
    from app.egitim.forklift_egitim import egit

    sonuc = egit(baglanti, istek.app.state.ayarlar)
    return sablonlar.TemplateResponse(
        istek,
        "forklift_egitim_sonuc.html",
        {"aktif_sekme": "forklift", "sonuc": sonuc},
    )


@router.post("/forklift/{ornek_id}/etiket")
def etiketle(
    ornek_id: int,
    deger: str = Form(...),  # yes | no | unknown
    baglanti=Depends(baglanti_al),
):
    if deger not in _ETIKETLER:
        raise DogrulamaHatasi(f"Geçersiz etiket: {deger}")
    guncellenen = baglanti.execute(
        "UPDATE forklift_samples SET label = ?, labeled_at = ? WHERE id = ?",
        (deger, zaman.simdi_utc(), ornek_id),
    ).rowcount
    baglanti.commit()
    if guncellenen == 0:
        return Response(status_code=404)
    return Response(status_code=204)  # sayfadaki JS kartı günceller


@router.get("/forklift/ornek/{ornek_id}.jpg")
def ornek_goruntusu(istek: Request, ornek_id: int, baglanti=Depends(baglanti_al)):
    satir = baglanti.execute(
        "SELECT frame_path FROM forklift_samples WHERE id = ?", (ornek_id,)
    ).fetchone()
    if satir is None:
        return Response(status_code=404)
    kok = istek.app.state.ayarlar.goruntu_klasoru.resolve()
    dosya = (kok / satir["frame_path"]).resolve()
    if not dosya.is_relative_to(kok) or not dosya.is_file():
        return Response(status_code=404)
    return FileResponse(dosya, media_type="image/jpeg")

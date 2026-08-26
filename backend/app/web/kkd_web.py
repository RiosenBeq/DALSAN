"""KKD veri sayfası: toplanan kişi görüntülerini etiketleme (docs/09 karar #5 —
ayrı etiketleme aracı YOK, üç düğme: Var / Yok / Belirsiz).

Etiketleme kuralı (docs/04 §5.2): ŞÜPHE VARSA HER ZAMAN 'BELİRSİZ'.
Emin olunamayan görüntüye 'yok' demek, veri setini baştan bozar.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()

_ETIKETLER = ("yes", "no", "unknown")
_ALANLAR = {"helmet": "helmet_label", "vest": "vest_label"}


@router.get("/kkd", response_class=HTMLResponse)
def kkd_sayfasi(istek: Request, baglanti=Depends(baglanti_al)):
    sayilar = baglanti.execute(
        "SELECT COUNT(*) AS toplam, "
        "SUM(CASE WHEN labeled_at IS NOT NULL THEN 1 ELSE 0 END) AS etiketli, "
        "SUM(CASE WHEN helmet_label = 'no' THEN 1 ELSE 0 END) AS baret_yok, "
        "SUM(CASE WHEN vest_label = 'no' THEN 1 ELSE 0 END) AS yelek_yok "
        "FROM ppe_samples"
    ).fetchone()

    ornekler = []
    for satir in baglanti.execute(
        "SELECT s.*, c.name AS kamera_adi FROM ppe_samples s "
        "LEFT JOIN cameras c ON c.id = s.camera_id "
        "WHERE s.labeled_at IS NULL ORDER BY s.captured_at DESC LIMIT 24"
    ):
        ornek = dict(satir)
        ornek["yerel_zaman"] = zaman.ekranda_goster(ornek["captured_at"])
        ornekler.append(ornek)

    return sablonlar.TemplateResponse(
        istek,
        "kkd.html",
        {
            "aktif_sekme": "kkd",
            "sayilar": dict(sayilar),
            "ornekler": ornekler,
        },
    )


@router.post("/kkd/{ornek_id}/etiket")
def etiketle(
    ornek_id: int,
    alan: str = Form(...),  # helmet | vest
    deger: str = Form(...),  # yes | no | unknown
    baglanti=Depends(baglanti_al),
):
    if alan not in _ALANLAR or deger not in _ETIKETLER:
        raise DogrulamaHatasi(f"Geçersiz etiket: {alan}={deger}")
    kolon = _ALANLAR[alan]
    baglanti.execute(f"UPDATE ppe_samples SET {kolon} = ? WHERE id = ?", (deger, ornek_id))
    # İki etiket de verildiyse örnek 'etiketlendi' sayılır ve listeden düşer
    baglanti.execute(
        "UPDATE ppe_samples SET labeled_at = ? "
        "WHERE id = ? AND helmet_label IS NOT NULL AND vest_label IS NOT NULL "
        "AND labeled_at IS NULL",
        (zaman.simdi_utc(), ornek_id),
    )
    baglanti.commit()
    return Response(status_code=204)  # sayfadaki JS kartı günceller


@router.post("/kkd/{ornek_id}/sil")
def ornek_sil(istek: Request, ornek_id: int, baglanti=Depends(baglanti_al)):
    satir = baglanti.execute(
        "SELECT crop_path FROM ppe_samples WHERE id = ?", (ornek_id,)
    ).fetchone()
    if satir is not None:
        dosya = istek.app.state.ayarlar.goruntu_klasoru / satir["crop_path"]
        dosya.unlink(missing_ok=True)
        baglanti.execute("DELETE FROM ppe_samples WHERE id = ?", (ornek_id,))
        baglanti.commit()
    return RedirectResponse("/kkd", status_code=303)


@router.get("/kkd/ornek/{ornek_id}.jpg")
def ornek_goruntusu(istek: Request, ornek_id: int, baglanti=Depends(baglanti_al)):
    satir = baglanti.execute(
        "SELECT crop_path FROM ppe_samples WHERE id = ?", (ornek_id,)
    ).fetchone()
    if satir is None:
        return Response(status_code=404)
    kok = istek.app.state.ayarlar.goruntu_klasoru.resolve()
    dosya = (kok / satir["crop_path"]).resolve()
    if not str(dosya).startswith(str(kok)) or not dosya.is_file():
        return Response(status_code=404)
    return FileResponse(dosya, media_type="image/jpeg")

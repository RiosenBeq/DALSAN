"""Kamera yönetimi: liste, ekleme/düzenleme, canlı önizleme, bölgeler, kalibrasyon."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.rules.kalibrasyon import homografi_hesapla
from app.web.ortak import BOLGE_TIPLERI, KURAL_TIPLERI, baglanti_al, rtsp_maskele
from app.web.rotalar import sablonlar

router = APIRouter()


class KameraBulunamadi(DogrulamaHatasi):
    http_kodu = 404


def _kamera_getir(baglanti, kamera_id: int) -> dict:
    satir = baglanti.execute("SELECT * FROM cameras WHERE id = ?", (kamera_id,)).fetchone()
    if satir is None:
        raise KameraBulunamadi(f"Kamera bulunamadı (id {kamera_id}). Silinmiş olabilir.")
    return dict(satir)


@router.get("/kameralar", response_class=HTMLResponse)
def kamera_listesi(istek: Request, baglanti=Depends(baglanti_al)):
    kameralar = []
    for satir in baglanti.execute("SELECT * FROM cameras ORDER BY name"):
        kamera = dict(satir)
        kamera["maskeli_url"] = rtsp_maskele(kamera["source_url"])
        kamera["son_kare"] = (
            zaman.ekranda_goster(kamera["last_frame_at"]) if kamera["last_frame_at"] else "—"
        )
        kameralar.append(kamera)
    return sablonlar.TemplateResponse(
        istek,
        "kameralar.html",
        {"aktif_sekme": "kameralar", "kameralar": kameralar},
    )


@router.get("/kameralar/yeni", response_class=HTMLResponse)
def kamera_yeni_form(istek: Request):
    return sablonlar.TemplateResponse(
        istek,
        "kamera_form.html",
        {"aktif_sekme": "kameralar", "kamera": None},
    )


@router.post("/kameralar/yeni")
def kamera_ekle(
    istek: Request,
    name: str = Form(...),
    area: str = Form(""),
    source_type: str = Form(...),
    source_url: str = Form(...),
    sample_fps: float = Form(6),
    baglanti=Depends(baglanti_al),
):
    _kamera_dogrula(name, source_type, source_url, sample_fps)
    simdi = zaman.simdi_utc()
    imlec = baglanti.execute(
        "INSERT INTO cameras (name, area, source_type, source_url, sample_fps, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name.strip(), area.strip(), source_type, source_url.strip(), sample_fps, simdi, simdi),
    )
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{imlec.lastrowid}", status_code=303)


@router.get("/kameralar/{kamera_id}", response_class=HTMLResponse)
def kamera_detay(istek: Request, kamera_id: int, baglanti=Depends(baglanti_al)):
    kamera = _kamera_getir(baglanti, kamera_id)
    kamera["maskeli_url"] = rtsp_maskele(kamera["source_url"])

    bolgeler = []
    for satir in baglanti.execute(
        "SELECT * FROM zones WHERE camera_id = ? ORDER BY id", (kamera_id,)
    ):
        bolge = dict(satir)
        bolge["tip_adi"] = BOLGE_TIPLERI.get(bolge["zone_type"], bolge["zone_type"])
        bolgeler.append(bolge)

    kurallar = []
    for satir in baglanti.execute(
        "SELECT * FROM rules WHERE camera_id = ? ORDER BY id", (kamera_id,)
    ):
        kural = dict(satir)
        kural["tip_adi"] = KURAL_TIPLERI.get(kural["rule_type"], kural["rule_type"])
        kurallar.append(kural)

    kalibrasyon = baglanti.execute(
        "SELECT calibrated_at FROM camera_calibrations WHERE camera_id = ?", (kamera_id,)
    ).fetchone()

    return sablonlar.TemplateResponse(
        istek,
        "kamera_detay.html",
        {
            "aktif_sekme": "kameralar",
            "kamera": kamera,
            "bolgeler": bolgeler,
            "bolgeler_json": json.dumps(
                [
                    {"id": b["id"], "poligon": json.loads(b["polygon"]), "ad": b["name"]}
                    for b in bolgeler
                ]
            ),
            "kurallar": kurallar,
            "bolge_tipleri": BOLGE_TIPLERI,
            "kalibrasyon_var": kalibrasyon is not None,
            "kalibrasyon_zamani": (
                zaman.ekranda_goster(kalibrasyon["calibrated_at"]) if kalibrasyon else ""
            ),
        },
    )


@router.post("/kameralar/{kamera_id}/duzenle")
def kamera_duzenle(
    kamera_id: int,
    name: str = Form(...),
    area: str = Form(""),
    source_type: str = Form(...),
    source_url: str = Form(...),
    sample_fps: float = Form(6),
    enabled: str = Form("0"),
    baglanti=Depends(baglanti_al),
):
    _kamera_getir(baglanti, kamera_id)
    _kamera_dogrula(name, source_type, source_url, sample_fps)
    baglanti.execute(
        "UPDATE cameras SET name = ?, area = ?, source_type = ?, source_url = ?, "
        "sample_fps = ?, enabled = ?, updated_at = ? WHERE id = ?",
        (
            name.strip(),
            area.strip(),
            source_type,
            source_url.strip(),
            sample_fps,
            1 if enabled == "1" else 0,
            zaman.simdi_utc(),
            kamera_id,
        ),
    )
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{kamera_id}", status_code=303)


@router.post("/kameralar/{kamera_id}/sil")
def kamera_sil(kamera_id: int, baglanti=Depends(baglanti_al)):
    # Bölge/kural/kalibrasyon ON DELETE CASCADE ile birlikte silinir;
    # olay geçmişi korunur (events.camera_id → SET NULL)
    baglanti.execute("DELETE FROM cameras WHERE id = ?", (kamera_id,))
    # updated_at değişmediği için süpervizörün fark etmesi adına sayaç damgası:
    baglanti.commit()
    return RedirectResponse("/kameralar", status_code=303)


@router.get("/kameralar/{kamera_id}/onizleme.jpg")
def kamera_onizleme(istek: Request, kamera_id: int):
    supervizor = getattr(istek.app.state, "supervizor", None)
    jpeg = supervizor.onizleme_jpeg(kamera_id) if supervizor else None
    if jpeg is None:
        # 1x1 gri piksel yerine anlaşılır durum: 204 → JS 'henüz kare yok' yazar
        return Response(status_code=204)
    return Response(content=jpeg, media_type="image/jpeg")


# ---- bölgeler ----


@router.post("/kameralar/{kamera_id}/bolgeler")
def bolge_ekle(
    kamera_id: int,
    name: str = Form(...),
    zone_type: str = Form(...),
    polygon: str = Form(...),  # JSON: [[x,y], ...] normalize 0-1
    baglanti=Depends(baglanti_al),
):
    _kamera_getir(baglanti, kamera_id)
    noktalar = _poligon_dogrula(polygon)
    if zone_type not in BOLGE_TIPLERI:
        raise DogrulamaHatasi(f"Geçersiz bölge tipi: {zone_type}")
    baglanti.execute(
        "INSERT INTO zones (camera_id, name, zone_type, polygon, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (kamera_id, name.strip(), zone_type, json.dumps(noktalar), zaman.simdi_utc()),
    )
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{kamera_id}", status_code=303)


@router.post("/bolgeler/{bolge_id}/sil")
def bolge_sil(bolge_id: int, baglanti=Depends(baglanti_al)):
    satir = baglanti.execute("SELECT camera_id FROM zones WHERE id = ?", (bolge_id,)).fetchone()
    if satir is None:
        return RedirectResponse("/kameralar", status_code=303)
    baglanti.execute("DELETE FROM zones WHERE id = ?", (bolge_id,))
    # zones.updated_at MAX'ı değişmeyebilir; kameranın damgasını tazele ki
    # süpervizör değişikliği restart'sız görsün
    baglanti.execute(
        "UPDATE cameras SET updated_at = ? WHERE id = ?",
        (zaman.simdi_utc(), satir["camera_id"]),
    )
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{satir['camera_id']}", status_code=303)


# ---- kalibrasyon ----


@router.post("/kameralar/{kamera_id}/kalibrasyon")
def kalibrasyon_kaydet(
    kamera_id: int,
    image_points: str = Form(...),  # JSON: 4 x [x,y] normalize
    world_points: str = Form(...),  # JSON: 4 x [metreX, metreY]
    baglanti=Depends(baglanti_al),
):
    _kamera_getir(baglanti, kamera_id)
    try:
        goruntu = [tuple(map(float, n)) for n in json.loads(image_points)]
        dunya = [tuple(map(float, n)) for n in json.loads(world_points)]
    except (json.JSONDecodeError, TypeError, ValueError) as hata:
        raise DogrulamaHatasi(f"Kalibrasyon noktaları okunamadı: {hata}") from hata
    homografi = homografi_hesapla(goruntu, dunya)  # hata mesajı zaten Türkçe
    baglanti.execute(
        "INSERT INTO camera_calibrations (camera_id, image_points, world_points, "
        "homography, calibrated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(camera_id) DO UPDATE SET image_points = excluded.image_points, "
        "world_points = excluded.world_points, homography = excluded.homography, "
        "calibrated_at = excluded.calibrated_at",
        (
            kamera_id,
            json.dumps(goruntu),
            json.dumps(dunya),
            json.dumps(homografi),
            zaman.simdi_utc(),
        ),
    )
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{kamera_id}", status_code=303)


@router.post("/kameralar/{kamera_id}/kalibrasyon/sil")
def kalibrasyon_sil(kamera_id: int, baglanti=Depends(baglanti_al)):
    baglanti.execute("DELETE FROM camera_calibrations WHERE camera_id = ?", (kamera_id,))
    baglanti.execute(
        "UPDATE cameras SET updated_at = ? WHERE id = ?", (zaman.simdi_utc(), kamera_id)
    )
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{kamera_id}", status_code=303)


# ---- doğrulama ----


def _kamera_dogrula(name: str, source_type: str, source_url: str, sample_fps: float) -> None:
    if not name.strip():
        raise DogrulamaHatasi("Kamera adı boş olamaz.")
    if source_type not in ("rtsp", "file"):
        raise DogrulamaHatasi("Kaynak tipi 'rtsp' veya 'file' olmalı.")
    if not source_url.strip():
        raise DogrulamaHatasi(
            "Kaynak adresi boş olamaz. RTSP örneği: rtsp://kullanici:sifre@192.168.1.64:554/... "
            "— Video dosyası örneği: veri/test-videolari/ornek.mp4"
        )
    if source_type == "rtsp" and not source_url.strip().startswith("rtsp://"):
        raise DogrulamaHatasi("RTSP adresi rtsp:// ile başlamalı.")
    if not 0.5 <= sample_fps <= 30:
        raise DogrulamaHatasi("Örnekleme hızı 0,5 ile 30 fps arasında olmalı.")


def _poligon_dogrula(polygon: str) -> list[list[float]]:
    try:
        noktalar = json.loads(polygon)
        noktalar = [[float(x), float(y)] for x, y in noktalar]
    except (json.JSONDecodeError, TypeError, ValueError) as hata:
        raise DogrulamaHatasi(f"Bölge çizimi okunamadı: {hata}") from hata
    if len(noktalar) < 3:
        raise DogrulamaHatasi("Bölge en az 3 nokta içermeli. Görüntü üzerine tıklayarak çizin.")
    if not all(0 <= x <= 1 and 0 <= y <= 1 for x, y in noktalar):
        raise DogrulamaHatasi("Bölge noktaları görüntünün içinde olmalı.")
    return noktalar

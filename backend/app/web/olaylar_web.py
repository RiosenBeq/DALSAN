"""Olay listesi, canlı akış (SSE), durum işaretleme, CSV ve kanıt fotoğrafları."""

from __future__ import annotations

import asyncio
import csv
import io
import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

from app import veritabani, zaman
from app.hatalar import DogrulamaHatasi
from app.web.ortak import KURAL_TIPLERI, OLAY_DURUMLARI, baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()


def _filtre_sorgusu(istek: Request) -> tuple[str, list]:
    kosullar, degerler = [], []
    p = istek.query_params
    if p.get("kamera"):
        kosullar.append("e.camera_id = ?")
        degerler.append(int(p["kamera"]))
    if p.get("tip") in ("violation", "system"):
        kosullar.append("e.event_type = ?")
        degerler.append(p["tip"])
    if p.get("durum") in OLAY_DURUMLARI:
        kosullar.append("e.status = ?")
        degerler.append(p["durum"])
    if p.get("baslangic"):
        kosullar.append("e.occurred_at >= ?")
        degerler.append(p["baslangic"] + "T00:00:00+00:00")
    if p.get("bitis"):
        kosullar.append("e.occurred_at <= ?")
        degerler.append(p["bitis"] + "T23:59:59+00:00")
    if p.get("alan"):
        kosullar.append("c.area = ?")
        degerler.append(p["alan"])
    return (" WHERE " + " AND ".join(kosullar)) if kosullar else "", degerler


_OLAY_SORGUSU = (
    "SELECT e.*, c.name AS kamera_adi, c.area AS kamera_alani "
    "FROM events e LEFT JOIN cameras c ON c.id = e.camera_id"
)


def _olay_hazirla(satir) -> dict:
    olay = dict(satir)
    olay["yerel_zaman"] = zaman.ekranda_goster(olay["occurred_at"])
    olay["durum_adi"] = OLAY_DURUMLARI.get(olay["status"], olay["status"])
    try:
        olay["detaylar"] = json.loads(olay["details"]) if olay["details"] else {}
    except json.JSONDecodeError:
        olay["detaylar"] = {"ham": olay["details"]}
    try:
        kural = json.loads(olay["rule_snapshot"]) if olay["rule_snapshot"] else {}
    except json.JSONDecodeError:
        kural = {}
    olay["kural_tipi_adi"] = KURAL_TIPLERI.get(kural.get("rule_type", ""), "")
    if olay["event_type"] == "system":
        olay["ozet"] = olay["detaylar"].get("mesaj", "Sistem olayı")
    else:
        olay["ozet"] = olay["kural_tipi_adi"] or "İhlal"
        if olay["detaylar"].get("eksik_kkd"):
            eksik = {"helmet": "baret", "vest": "yelek"}
            olay["ozet"] += (
                " — " + ", ".join(eksik.get(k, k) for k in olay["detaylar"]["eksik_kkd"]) + " yok"
            )
        elif olay["detaylar"].get("mesafe_m") is not None:
            olay["ozet"] += f" — {olay['detaylar']['mesafe_m']} m"
    return olay


@router.get("/olaylar", response_class=HTMLResponse)
def olay_listesi(istek: Request, baglanti=Depends(baglanti_al)):
    kosul, degerler = _filtre_sorgusu(istek)
    satirlar = baglanti.execute(
        f"{_OLAY_SORGUSU}{kosul} ORDER BY e.occurred_at DESC LIMIT 200", degerler
    ).fetchall()
    olaylar = [_olay_hazirla(s) for s in satirlar]
    kameralar = [dict(s) for s in baglanti.execute("SELECT id, name FROM cameras ORDER BY name")]
    alanlar = [
        s["area"]
        for s in baglanti.execute(
            "SELECT DISTINCT area FROM cameras WHERE area != '' ORDER BY area"
        )
    ]
    return sablonlar.TemplateResponse(
        istek,
        "olaylar.html",
        {
            "aktif_sekme": "olaylar",
            "olaylar": olaylar,
            "kameralar": kameralar,
            "alanlar": alanlar,
            "durumlar": OLAY_DURUMLARI,
            "filtre": dict(istek.query_params),
            # CSV bağlantısı ekrandaki filtreyi aynen taşısın
            "istek_sorgusu": istek.url.query,
        },
    )


@router.get("/olaylar/akis")
async def olay_akisi(istek: Request):
    """SSE: yeni olayları ekrana anlık iter (docs/02 §4 — saniyede bir sorgu)."""
    ayarlar = istek.app.state.ayarlar

    async def uret():
        baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
        try:
            son = baglanti.execute("SELECT COALESCE(MAX(id), 0) AS m FROM events").fetchone()
            son_id = son["m"]
            while True:
                if await istek.is_disconnected():
                    return
                satirlar = baglanti.execute(
                    f"{_OLAY_SORGUSU} WHERE e.id > ? ORDER BY e.id LIMIT 20", (son_id,)
                ).fetchall()
                for satir in satirlar:
                    olay = _olay_hazirla(satir)
                    son_id = olay["id"]
                    veri = json.dumps(
                        {
                            "id": olay["id"],
                            "zaman": olay["yerel_zaman"],
                            "kamera": olay["kamera_adi"] or "—",
                            "ozet": olay["ozet"],
                            "tip": olay["event_type"],
                        },
                        ensure_ascii=False,
                    )
                    yield f"data: {veri}\n\n"
                yield ": ping\n\n"  # ara bağlantı canlı tutma
                await asyncio.sleep(1.0)
        finally:
            baglanti.close()

    return StreamingResponse(
        uret(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/olaylar/disa-aktar.csv")
def csv_disa_aktar(istek: Request, baglanti=Depends(baglanti_al)):
    kosul, degerler = _filtre_sorgusu(istek)
    satirlar = baglanti.execute(
        f"{_OLAY_SORGUSU}{kosul} ORDER BY e.occurred_at DESC LIMIT 10000", degerler
    ).fetchall()
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";")  # Türkçe Excel noktalı virgül bekler
    yazici.writerow(["Zaman", "Tip", "Kamera", "Alan", "Özet", "Durum", "Not"])
    for satir in satirlar:
        olay = _olay_hazirla(satir)
        yazici.writerow(
            [
                olay["yerel_zaman"],
                "İhlal" if olay["event_type"] == "violation" else "Sistem",
                olay["kamera_adi"] or "",
                olay["kamera_alani"] or "",
                olay["ozet"],
                olay["durum_adi"],
                olay["note"] or "",
            ]
        )
    return Response(
        content="﻿" + tampon.getvalue(),  # BOM: Excel'de Türkçe karakterler için
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=dalsan-olaylar.csv"},
    )


@router.get("/olaylar/{olay_id}", response_class=HTMLResponse)
def olay_detay(istek: Request, olay_id: int, baglanti=Depends(baglanti_al)):
    satir = baglanti.execute(f"{_OLAY_SORGUSU} WHERE e.id = ?", (olay_id,)).fetchone()
    if satir is None:
        return RedirectResponse("/olaylar", status_code=303)
    olay = _olay_hazirla(satir)
    olay["detay_metni"] = json.dumps(olay["detaylar"], ensure_ascii=False, indent=2)
    return sablonlar.TemplateResponse(
        istek,
        "olay_detay.html",
        {"aktif_sekme": "olaylar", "olay": olay, "durumlar": OLAY_DURUMLARI},
    )


@router.post("/olaylar/{olay_id}/durum")
def olay_durumu(
    olay_id: int,
    durum: str = Form(...),
    not_metni: str = Form(""),
    baglanti=Depends(baglanti_al),
):
    """Yeni / İncelendi / Yanlış alarm — K11 precision ölçümünün veri kaynağı."""
    if durum not in OLAY_DURUMLARI:
        raise DogrulamaHatasi(f"Geçersiz olay durumu: {durum}")
    baglanti.execute(
        "UPDATE events SET status = ?, note = ?, reviewed_at = ? WHERE id = ?",
        (
            durum,
            not_metni.strip() or None,
            zaman.simdi_utc() if durum != "new" else None,
            olay_id,
        ),
    )
    baglanti.commit()
    return RedirectResponse(f"/olaylar/{olay_id}", status_code=303)


@router.get("/goruntuler/{yol:path}")
def kanit_fotografi(istek: Request, yol: str):
    """Kanıt fotoğrafları YALNIZCA oturumla servis edilir — snapshot dizini
    dışarıdan doğrudan erişime kapalıdır (docs/00 KVKK)."""
    kok = istek.app.state.ayarlar.goruntu_klasoru.resolve()
    dosya = (kok / yol).resolve()
    # is_relative_to: metin ön-eki karşılaştırması '/veri/goruntuler-x' gibi
    # kardeş klasörleri yanlışlıkla kabul ederdi (yol kaçışı)
    if not dosya.is_relative_to(kok) or not dosya.is_file():
        return Response(status_code=404)
    return FileResponse(dosya, media_type="image/jpeg")

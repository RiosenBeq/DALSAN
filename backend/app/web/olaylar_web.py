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
from app.web.ortak import OLAY_DURUMLARI, OLAY_SORGUSU, baglanti_al, olay_hazirla
from app.web.rotalar import sablonlar

router = APIRouter()


def _filtre_sorgusu(istek: Request) -> tuple[str, list]:
    kosullar, degerler = [], []
    p = istek.query_params
    if p.get("kamera"):
        try:
            degerler.append(int(p["kamera"]))
        except ValueError:
            raise DogrulamaHatasi(
                f"Kamera filtresi sayı olmalı; '{p['kamera']}' yazılmış. Filtreyi listeden seçin."
            ) from None
        kosullar.append("e.camera_id = ?")
    if p.get("tip") in ("violation", "system"):
        kosullar.append("e.event_type = ?")
        degerler.append(p["tip"])
    if p.get("durum") in OLAY_DURUMLARI:
        kosullar.append("e.status = ?")
        degerler.append(p["durum"])
    # Tarihler ekranda TÜRKİYE saatiyle gösterilir; sınırlar da Türkiye gününe
    # göre kurulmalı. UTC sanılırsa gece 00:00-03:00 arası olaylar bir önceki
    # güne düşer ve kullanıcı "olay kayboldu" der (docs/08 R7).
    if p.get("baslangic"):
        kosullar.append("e.occurred_at >= ?")
        degerler.append(_tarih_siniri(p["baslangic"], gun_sonu=False))
    if p.get("bitis"):
        kosullar.append("e.occurred_at < ?")
        degerler.append(_tarih_siniri(p["bitis"], gun_sonu=True))
    if p.get("alan"):
        kosullar.append("c.area = ?")
        degerler.append(p["alan"])
    return (" WHERE " + " AND ".join(kosullar)) if kosullar else "", degerler


def _tarih_siniri(tarih: str, gun_sonu: bool) -> str:
    try:
        return (
            zaman.yerel_gun_sonu_utc(tarih) if gun_sonu else zaman.yerel_gun_baslangici_utc(tarih)
        )
    except ValueError as hata:
        raise DogrulamaHatasi(f"Tarih okunamadı: {hata}") from hata


@router.get("/olaylar", response_class=HTMLResponse)
def olay_listesi(istek: Request, baglanti=Depends(baglanti_al)):
    kosul, degerler = _filtre_sorgusu(istek)
    satirlar = baglanti.execute(
        f"{OLAY_SORGUSU}{kosul} ORDER BY e.occurred_at DESC LIMIT 200", degerler
    ).fetchall()
    olaylar = [olay_hazirla(s) for s in satirlar]
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
                    f"{OLAY_SORGUSU} WHERE e.id > ? ORDER BY e.id LIMIT 20", (son_id,)
                ).fetchall()
                for satir in satirlar:
                    olay = olay_hazirla(satir)
                    son_id = olay["id"]
                    veri = json.dumps(
                        {
                            "id": olay["id"],
                            "zaman": olay["yerel_zaman"],
                            "kamera": olay["kamera_adi"] or "—",
                            "ozet": olay["ozet"],
                            "tip": olay["event_type"],
                            "kural": olay["kural_tipi_adi"],
                            # Gölge moddaki kuralın olayı listeye düşer ama
                            # ekranda uyarı bandı ÇIKMAZ (static/uyari.js):
                            # gölge mod "sessizce dene" demektir.
                            "golge": olay["golge_mod"],
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
        f"{OLAY_SORGUSU}{kosul} ORDER BY e.occurred_at DESC LIMIT 10000", degerler
    ).fetchall()
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";")  # Türkçe Excel noktalı virgül bekler
    yazici.writerow(["Zaman", "Tip", "Kamera", "Alan", "Özet", "Durum", "Not"])
    for satir in satirlar:
        olay = olay_hazirla(satir)
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
    satir = baglanti.execute(f"{OLAY_SORGUSU} WHERE e.id = ?", (olay_id,)).fetchone()
    if satir is None:
        return RedirectResponse("/olaylar", status_code=303)
    olay = olay_hazirla(satir)
    olay["detay_metni"] = json.dumps(olay["detaylar"], ensure_ascii=False, indent=2)
    return sablonlar.TemplateResponse(
        istek,
        "olay_detay.html",
        {"aktif_sekme": "olaylar", "olay": olay, "durumlar": OLAY_DURUMLARI},
    )


# İşaretlemeden sonra kullanıcının döneceği ekran. Formdan HAM YOL almak
# yerine anahtar alınır: dışarıdan verilen bir adrese yönlendirme (açık
# yönlendirme açığı) hiç mümkün olmasın. İnceleme ekranından işaretlenen olay
# yine inceleme ekranında kalır — kuyruğun sırası kaybolmasın.
DONUS_YOLLARI = {
    "olay": "/olaylar/{id}",
    "inceleme": "/komuta/inceleme?olay={id}",
}


@router.post("/olaylar/{olay_id}/durum")
def olay_durumu(
    olay_id: int,
    durum: str = Form(...),
    not_metni: str = Form(""),
    donus: str = Form("olay"),
    baglanti=Depends(baglanti_al),
):
    """Yeni / İncelendi / Yanlış alarm — K11 precision ölçümünün veri kaynağı.

    Olayı işaretleyen TEK yol burasıdır: olay detay sayfası da komuta inceleme
    ekranı da bu uca yazar. İkinci bir yazma yolu açılsaydı iki ekran zamanla
    farklı davranır (biri reviewed_at yazar, diğeri yazmaz) ve K11 ölçümü
    güvenilmez olurdu.
    """
    if durum not in OLAY_DURUMLARI:
        raise DogrulamaHatasi(f"Geçersiz olay durumu: {durum}")
    if donus not in DONUS_YOLLARI:
        raise DogrulamaHatasi(f"Bilinmeyen dönüş ekranı: {donus}")
    # reviewed_at YALNIZCA gerçek bir inceleme kararında damgalanır. Sadece not
    # eklendiğinde eski damga KORUNUR: bu alan K11 isabet ölçümünün ve "ihlal ne
    # kadar sürede incelendi" sorusunun veri kaynağı. Günler sonra not yazmak,
    # olayı bugün incelenmiş gibi göstermemeli.
    # SQLite'ta UPDATE'in sağ tarafındaki sütunlar satırın ESKİ değerini verir;
    # bu yüzden "status <> :durum" karşılaştırması önceki durumu görür.
    baglanti.execute(
        """
        UPDATE events
           SET note = :not_metni,
               reviewed_at = CASE
                   WHEN :durum = 'new' THEN NULL
                   WHEN status <> :durum OR reviewed_at IS NULL THEN :simdi
                   ELSE reviewed_at
               END,
               status = :durum
         WHERE id = :olay_id
        """,
        {
            "durum": durum,
            "not_metni": not_metni.strip() or None,
            "simdi": zaman.simdi_utc(),
            "olay_id": olay_id,
        },
    )
    baglanti.commit()
    return RedirectResponse(DONUS_YOLLARI[donus].format(id=olay_id), status_code=303)


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

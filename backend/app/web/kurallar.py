"""Kural yönetimi: üç kural tipi için liste + form (docs/03).

Parametreler kaydedilmeden ÖNCE rules/parametreler.py şemalarıyla doğrulanır;
geçersiz parametre veritabanına asla girmez.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.rules.parametreler import params_dogrula
from app.web.ortak import BOLGE_TIPLERI, KURAL_TIPLERI, SINIFLAR, baglanti_al, guvenli_json
from app.web.rotalar import sablonlar

router = APIRouter()


@router.get("/kurallar", response_class=HTMLResponse)
def kural_listesi(istek: Request, baglanti=Depends(baglanti_al)):
    kurallar = []
    for satir in baglanti.execute(
        "SELECT r.*, c.name AS kamera_adi, z.name AS bolge_adi "
        "FROM rules r JOIN cameras c ON c.id = r.camera_id "
        "LEFT JOIN zones z ON z.id = r.zone_id ORDER BY c.name, r.id"
    ):
        kural = dict(satir)
        kural["tip_adi"] = KURAL_TIPLERI.get(kural["rule_type"], kural["rule_type"])
        kural["kalibrasyon_bekliyor"] = False
        if kural["rule_type"] == "safe_distance":
            kalibre = baglanti.execute(
                "SELECT 1 FROM camera_calibrations WHERE camera_id = ?",
                (kural["camera_id"],),
            ).fetchone()
            # Kalibre edilmemiş kamerada mesafe kuralı PASİFTİR (docs/03 §2)
            kural["kalibrasyon_bekliyor"] = kalibre is None
        kurallar.append(kural)

    kameralar = [dict(s) for s in baglanti.execute("SELECT id, name FROM cameras ORDER BY name")]
    return sablonlar.TemplateResponse(
        istek,
        "kurallar.html",
        {"aktif_sekme": "kurallar", "kurallar": kurallar, "kameralar": kameralar},
    )


@router.get("/kurallar/yeni", response_class=HTMLResponse)
def kural_yeni_form(istek: Request, kamera: int = 0, baglanti=Depends(baglanti_al)):
    return _kural_formu(istek, baglanti, kural=None, secili_kamera=kamera)


@router.get("/kurallar/{kural_id}/duzenle", response_class=HTMLResponse)
def kural_duzenle_form(istek: Request, kural_id: int, baglanti=Depends(baglanti_al)):
    satir = baglanti.execute("SELECT * FROM rules WHERE id = ?", (kural_id,)).fetchone()
    if satir is None:
        return RedirectResponse("/kurallar", status_code=303)
    kural = dict(satir)
    kural["params"] = json.loads(kural["params"])
    kural["target_classes"] = json.loads(kural["target_classes"])
    return _kural_formu(istek, baglanti, kural=kural, secili_kamera=kural["camera_id"])


def _kural_formu(istek: Request, baglanti, kural: dict | None, secili_kamera: int):
    kameralar = [dict(s) for s in baglanti.execute("SELECT id, name FROM cameras ORDER BY name")]
    if not kameralar:
        raise DogrulamaHatasi("Kural tanımlamak için önce bir kamera ekleyin (Kameralar sekmesi).")
    bolgeler = [
        dict(s)
        for s in baglanti.execute(
            "SELECT z.id, z.name, z.zone_type, z.camera_id FROM zones z ORDER BY z.name"
        )
    ]
    for bolge in bolgeler:
        bolge["tip_adi"] = BOLGE_TIPLERI.get(bolge["zone_type"], bolge["zone_type"])
    anonslar = [
        dict(s) for s in baglanti.execute("SELECT id, key, text FROM announcement_messages")
    ]
    return sablonlar.TemplateResponse(
        istek,
        "kural_form.html",
        {
            "aktif_sekme": "kurallar",
            "kural": kural,
            "kameralar": kameralar,
            "bolgeler": bolgeler,
            "bolgeler_json": guvenli_json(bolgeler),
            "anonslar": anonslar,
            "secili_kamera": secili_kamera or (kural or {}).get("camera_id") or kameralar[0]["id"],
            "siniflar": SINIFLAR,
        },
    )


@router.post("/kurallar/kaydet")
async def kural_kaydet(istek: Request, baglanti=Depends(baglanti_al)):
    form = await istek.form()
    # Senkron SQLite işi threadpool'da koşar: event loop'ta koşarsa, yazma
    # kilidi beklenirken TÜM arayüz (SSE dahil) donar.
    return await run_in_threadpool(_kural_kaydet_islemi, baglanti, form)


def _kural_kaydet_islemi(baglanti, form):
    kural_id = int(form.get("kural_id") or 0)
    kamera_id = int(form.get("camera_id") or 0)
    kural_tipi = form.get("rule_type", "")
    if kural_tipi not in KURAL_TIPLERI:
        raise DogrulamaHatasi(f"Geçersiz kural tipi: {kural_tipi}")

    zone_id = int(form.get("zone_id") or 0) or None
    if kural_tipi in ("zone_intrusion", "ppe_violation") and zone_id is None:
        raise DogrulamaHatasi(
            f"'{KURAL_TIPLERI[kural_tipi]}' kuralı bölgesiz tanımlanamaz. "
            "Önce kamera sayfasında bölge çizin, sonra burada seçin."
        )
    if zone_id is not None:
        bolge = baglanti.execute(
            "SELECT camera_id, zone_type FROM zones WHERE id = ?", (zone_id,)
        ).fetchone()
        if bolge is None or bolge["camera_id"] != kamera_id:
            raise DogrulamaHatasi("Seçilen bölge bu kameraya ait değil.")
        # KKD kuralı yalnızca 'KKD zorunlu alan' bölgesinde çalışır: veri toplama
        # ve değerlendirme bu tipe bakar. Başka tipte bölge seçilirse kural
        # kaydedilir ama HİÇBİR ZAMAN çalışmazdı — sessiz başarısızlık.
        if kural_tipi == "ppe_violation" and bolge["zone_type"] != "ppe_required":
            raise DogrulamaHatasi(
                "KKD kuralı yalnızca 'KKD zorunlu alan' tipindeki bir bölgeye bağlanabilir. "
                "Kamera sayfasında bu tipte bir bölge çizip burada onu seçin."
            )

    params, hedefler = _formdan_params(kural_tipi, form)
    params = params_dogrula(kural_tipi, params)  # Türkçe hatayla reddeder

    cooldown = _sayi(
        form,
        "cooldown_s",
        {"zone_intrusion": 120, "safe_distance": 90, "ppe_violation": 180}[kural_tipi],
    )
    if not 5 <= cooldown <= 86400:
        raise DogrulamaHatasi(
            "Cooldown 5 saniye ile 86400 saniye (24 saat) arasında olmalı; "
            f"şu an {cooldown:g} yazılmış."
        )
    anons_id = int(form.get("announcement_id") or 0) or None
    aktif = 1 if form.get("enabled") == "1" else 0
    simdi = zaman.simdi_utc()

    if kural_id:
        baglanti.execute(
            "UPDATE rules SET camera_id=?, rule_type=?, zone_id=?, target_classes=?, "
            "params=?, cooldown_s=?, announcement_id=?, enabled=?, updated_at=? WHERE id=?",
            (
                kamera_id,
                kural_tipi,
                zone_id,
                json.dumps(hedefler),
                json.dumps(params),
                cooldown,
                anons_id,
                aktif,
                simdi,
                kural_id,
            ),
        )
    else:
        baglanti.execute(
            "INSERT INTO rules (camera_id, rule_type, zone_id, target_classes, params, "
            "cooldown_s, announcement_id, enabled, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                kamera_id,
                kural_tipi,
                zone_id,
                json.dumps(hedefler),
                json.dumps(params),
                cooldown,
                anons_id,
                aktif,
                simdi,
            ),
        )
    baglanti.commit()
    return RedirectResponse("/kurallar", status_code=303)


# Yaya yolu kuralının varsayılanları (docs/03 §1). Kısa süreli sapmalar ihlal
# sayılmasın diye kalış süresi bilerek uzun: yolun kenarına bir adım atan kişi
# değil, yolu KULLANMAYAN kişi uyarı üretmeli.
YAYA_YOLU_VARSAYILANLARI = {"mode": "outside", "min_dwell_s": 5.0}
YAYA_YOLU_COOLDOWN_SN = 180


@router.post("/kurallar/yaya-yolu")
def yaya_yolu_kurali(
    zone_id: int = Form(...),
    baglanti=Depends(baglanti_al),
):
    """Tek tıkla 'yaya yolunu kullanmayan kişi' kuralı.

    Fabrikada çizili yürüyüş yolu vardır ve insanların oradan yürümesi beklenir.
    Bu kural, yaya yolu bölgesinin DIŞINDA belirli süreden uzun kalan kişiyi
    uyarır. Elle kurmak için Kurallar sayfasında 'Bölge DIŞINDA olmak ihlal'
    seçeneği de vardır; bu düğme aynı kuralı doğru varsayılanlarla kurar.
    """
    bolge = baglanti.execute(
        "SELECT id, camera_id, zone_type, name FROM zones WHERE id = ?", (zone_id,)
    ).fetchone()
    if bolge is None:
        raise DogrulamaHatasi("Bölge bulunamadı.")
    if bolge["zone_type"] != "pedestrian_path":
        raise DogrulamaHatasi(
            "Yaya yolu kuralı yalnızca 'Yaya yolu' tipindeki bir bölgeye kurulabilir. "
            "Kamera sayfasında bölgeyi bu tiple çizin."
        )
    mevcut = baglanti.execute(
        "SELECT 1 FROM rules WHERE zone_id = ? AND rule_type = 'zone_intrusion'", (zone_id,)
    ).fetchone()
    if mevcut is not None:
        raise DogrulamaHatasi(
            f"'{bolge['name']}' bölgesinde zaten bir kural var. Kurallar sayfasından düzenleyin."
        )

    anons = baglanti.execute(
        "SELECT id FROM announcement_messages WHERE key = 'pedestrian_path'"
    ).fetchone()
    baglanti.execute(
        "INSERT INTO rules (camera_id, rule_type, zone_id, target_classes, params, "
        "cooldown_s, announcement_id, enabled, updated_at) VALUES (?,?,?,?,?,?,?,1,?)",
        (
            bolge["camera_id"],
            "zone_intrusion",
            zone_id,
            json.dumps(["person"]),
            json.dumps(params_dogrula("zone_intrusion", dict(YAYA_YOLU_VARSAYILANLARI))),
            YAYA_YOLU_COOLDOWN_SN,
            anons["id"] if anons else None,
            zaman.simdi_utc(),
        ),
    )
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{bolge['camera_id']}", status_code=303)


@router.post("/kurallar/{kural_id}/sil")
def kural_sil(kural_id: int, baglanti=Depends(baglanti_al)):
    # Olay geçmişi korunur: events.rule_id → SET NULL, rule_snapshot zaten kayıtlı
    satir = baglanti.execute("SELECT camera_id FROM rules WHERE id = ?", (kural_id,)).fetchone()
    baglanti.execute("DELETE FROM rules WHERE id = ?", (kural_id,))
    if satir is not None:
        baglanti.execute(
            "UPDATE cameras SET updated_at = ? WHERE id = ?",
            (zaman.simdi_utc(), satir["camera_id"]),
        )
    baglanti.commit()
    return RedirectResponse("/kurallar", status_code=303)


def _formdan_params(kural_tipi: str, form) -> tuple[dict, list[str]]:
    """Form alanlarını kural tipine göre params sözlüğüne çevirir."""
    if kural_tipi == "zone_intrusion":
        hedefler = form.getlist("target_classes")
        if not hedefler:
            raise DogrulamaHatasi("En az bir hedef sınıf seçin (insan / forklift / tır).")
        return (
            {"mode": form.get("mode", "inside"), "min_dwell_s": _sayi(form, "min_dwell_s", 2.0)},
            hedefler,
        )
    if kural_tipi == "safe_distance":
        nesneler = form.getlist("object_classes") or ["forklift", "truck"]
        params = {
            "subject_classes": ["person"],
            "object_classes": nesneler,
            "distance_m": _sayi(form, "distance_m", 3.0),
            "min_frames": int(_sayi(form, "min_frames", 5)),
            "require_moving_vehicle": form.get("require_moving_vehicle") == "1",
            "min_speed_mps": _sayi(form, "min_speed_mps", 0.3),
        }
        return params, ["person", *nesneler]
    # ppe_violation
    kkdler = form.getlist("required_ppe")
    if not kkdler:
        raise DogrulamaHatasi("En az bir KKD seçin (baret / yelek).")
    params = {
        "required_ppe": kkdler,
        "min_person_height_px": int(_sayi(form, "min_person_height_px", 120)),
        "min_vest_height_px": int(_sayi(form, "min_vest_height_px", 80)),
        "min_confidence": _sayi(form, "min_confidence", 0.70),
        "window_size": int(_sayi(form, "window_size", 15)),
        "min_valid_observations": int(_sayi(form, "min_valid_observations", 8)),
        "violation_ratio": _sayi(form, "violation_ratio", 0.75),
        "min_dwell_s": _sayi(form, "min_dwell_s", 3.0),
        "require_full_bbox": form.get("require_full_bbox") == "1",
    }
    return params, ["person"]


def _sayi(form, alan: str, varsayilan: float) -> float:
    ham = (form.get(alan) or "").strip().replace(",", ".")
    if not ham:
        return varsayilan
    try:
        return float(ham)
    except ValueError:
        raise DogrulamaHatasi(f"'{alan}' alanı sayı olmalı; '{ham}' yazılmış.") from None

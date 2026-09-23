"""KKD veri sayfası: toplanan kişi görüntülerini etiketleme (docs/09 karar #5 -
ayrı etiketleme aracı YOK, üç düğme: Var / Yok / Belirsiz).

Etiketleme kuralı (docs/04 §5.2): ŞÜPHE VARSA HER ZAMAN 'BELİRSİZ'.
Emin olunamayan görüntüye 'yok' demek, veri setini baştan bozar.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from starlette.background import BackgroundTask

from app import zaman
from app.egitim import veri_seti
from app.hatalar import DogrulamaHatasi
from app.loglama import log_al
from app.olaylar.yazici import sistem_olayi_yaz
from app.web import kkd_karnesi
from app.web.erisim_izi import erisim_yaz
from app.web.ortak import OGELER, baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()
_log = log_al("kkd")

# docs/04 §4.5 "Minimum" sütunu: model eğitimine başlamak için ASGARİ miktar
# (hedef bunun üstündedir). Durum kartlarının çubukları bu sayılara göre dolar;
# sayı belgeden gelir, burada uydurulmaz. Belge değişirse burası da değişir.
KKD_ASGARI = {"toplam": 2500, "baret_yok": 500, "yelek_yok": 500, "belirsiz": 300}

# "Belirsiz" bir öğe değil, bir karardır; rozeti nötr sistem rengini alır.
_BELIRSIZ = {"anahtar": "sistem", "ad": "Belirsiz", "simge": "belirsiz"}


def _hedef_kartlari(sayilar: dict) -> list[dict]:
    kalemler = (
        ("toplam", "Toplanan kişi görüntüsü", OGELER["insan"]),
        ("baret_yok", "“Baret yok” örneği", OGELER["baret"]),
        ("yelek_yok", "“Yelek yok” örneği", OGELER["yelek"]),
        ("belirsiz", "“Belirsiz” örneği", _BELIRSIZ),
    )
    kartlar = []
    for anahtar, ad, oge in kalemler:
        deger = int(sayilar.get(anahtar) or 0)
        asgari = KKD_ASGARI[anahtar]
        kartlar.append(
            {
                "ad": ad,
                "oge": oge,
                "deger": deger,
                "asgari": asgari,
                # Çubuk %100'de durur; asgari aşıldıysa sayı zaten söyler.
                "yuzde": min(100, round(100 * deger / asgari)),
            }
        )
    return kartlar


# Veri toplamayı açmak için istenen onayın metni (docs/17 §5.8). Olayın
# ayrıntısına ve kapının notuna olduğu gibi yazılır.
TOPLAMA_ONAY_METNI = "Rev.02 ek protokolü imzalandı ve çalışanlara aydınlatma yapıldı"


def toplama_durumu(baglanti) -> dict:
    """KKD veri toplama kapısı (ppe_collection_gate, şema 007)."""
    satir = baglanti.execute(
        "SELECT enabled, changed_at, note FROM ppe_collection_gate WHERE id = 1"
    ).fetchone()
    if satir is None:
        return {"acik": False, "degisti": "", "not": ""}
    return {
        "acik": bool(satir["enabled"]),
        "degisti": zaman.ekranda_goster(satir["changed_at"]) if satir["changed_at"] else "",
        "not": satir["note"] or "",
    }


def kkd_model_durumu(istek: Request) -> dict:
    """KKD modelinin durumu, sayfanın dilinde (docs/17 §5.10)."""
    supervizor = getattr(istek.app.state, "supervizor", None)
    if supervizor is None:
        return {
            "durum": "bilinmiyor",
            "metin": "Analiz çalışmıyor: KKD modelinin durumu bilinmiyor.",
        }
    if getattr(supervizor, "kkd_hatasi", None):
        return {"durum": "hata", "metin": supervizor.kkd_hatasi}
    kkd = supervizor.kkd
    if kkd.model_var:
        return {
            "durum": "hazir",
            "metin": f"Model: {kkd.model_surumu}, doğrulandı (sha256).",
            "kart": kkd.kart,
        }
    return {
        "durum": "yok",
        "metin": "Model yüklü değil: KKD kuralı olay üretmez. Model, toplanan veriyle ürün "
        "dışında eğitilip özetiyle birlikte models/ klasörüne konunca yeniden başlatmada "
        "yüklenir (docs/04 §6).",
    }


_ETIKETLER = ("yes", "no", "unknown")
_ALANLAR = {"helmet": "helmet_label", "vest": "vest_label"}


@router.get("/kkd", response_class=HTMLResponse)
def kkd_sayfasi(istek: Request, baglanti=Depends(baglanti_al)):
    sayilar = baglanti.execute(
        "SELECT COUNT(*) AS toplam, "
        "SUM(CASE WHEN labeled_at IS NOT NULL THEN 1 ELSE 0 END) AS etiketli, "
        "SUM(CASE WHEN helmet_label = 'no' THEN 1 ELSE 0 END) AS baret_yok, "
        "SUM(CASE WHEN vest_label = 'no' THEN 1 ELSE 0 END) AS yelek_yok, "
        "SUM(CASE WHEN helmet_label = 'unknown' OR vest_label = 'unknown' "
        "THEN 1 ELSE 0 END) AS belirsiz "
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
            "hedefler": _hedef_kartlari(dict(sayilar)),
            "ornekler": ornekler,
            "toplama": toplama_durumu(baglanti),
            "toplama_onay_metni": TOPLAMA_ONAY_METNI,
            "saat_limiti": istek.app.state.ayarlar.kkd_ornek_saat_limit,
            "zor_ornekler": veri_seti.ZOR_ORNEKLER,
            "model": kkd_model_durumu(istek),
            # Gölge karnesi ve anons kapısı (docs/17 §5.7): yüklü sürüm başına
            "karne": kkd_karnesi.karne_hesapla(
                baglanti, istek.app.state.ayarlar, kkd_karnesi.yuklu_surum(istek)
            ),
            "veri_seti": veri_seti.ozet(veri_seti.etiketli_ornekler(baglanti)),
        },
    )


@router.post("/kkd/toplama")
def kkd_toplama_degistir(
    istek: Request,
    ac: str = Form(...),
    onay: str = Form(""),
    baglanti=Depends(baglanti_al),
):
    """Veri toplamayı açar ya da kapatır - yeniden başlatmadan (docs/17 §5.8).

    Açmak onay ister: kişi kırpığı toplamak kişisel veri işlemektir ve ancak
    Rev.02 ek protokolü imzalanıp çalışanlara aydınlatma yapıldıktan sonra
    açılır. Kapatmak onaysızdır ve hemen geçerlidir: örnekleme kapıyı her
    örnekten önce okur. Her değişiklik Olaylar'a PPE_COLLECTION_CHANGED yazar.
    """
    acilsin = ac == "1"
    if acilsin and onay != "1":
        raise DogrulamaHatasi(
            f"Veri toplamayı açmak için onay kutusunu işaretleyin: “{TOPLAMA_ONAY_METNI}”."
        )
    if toplama_durumu(baglanti)["acik"] == acilsin:
        return RedirectResponse("/kkd", status_code=303)  # zaten öyle: olay yazılmaz
    baglanti.execute(
        "UPDATE ppe_collection_gate SET enabled = ?, changed_at = ?, note = ? WHERE id = 1",
        (1 if acilsin else 0, zaman.simdi_utc(), TOPLAMA_ONAY_METNI if acilsin else None),
    )
    baglanti.commit()
    sistem_olayi_yaz(
        baglanti,
        f"KKD veri toplama açıldı ({TOPLAMA_ONAY_METNI})."
        if acilsin
        else "KKD veri toplama kapatıldı; kişi görüntüsü toplanmıyor.",
        detaylar={"toplama": "acik" if acilsin else "kapali"},
        kod="PPE_COLLECTION_CHANGED",
    )
    erisim_yaz(baglanti, istek, "ppe_collection_gate", "acik" if acilsin else "kapali")
    return RedirectResponse("/kkd", status_code=303)


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


@router.post("/kkd/{ornek_id}/zor")
def zor_ornek_isaretle(ornek_id: int, kod: str = Form(""), baglanti=Depends(baglanti_al)):
    """Zor örnek kodu (docs/17 §5.8): veri setinde ve değerlendirmede ayrı
    kırılım olur. Boş kod işareti kaldırır."""
    if kod and kod not in veri_seti.ZOR_ORNEKLER:
        raise DogrulamaHatasi(f"Geçersiz zor örnek kodu: {kod}")
    baglanti.execute("UPDATE ppe_samples SET hard_case = ? WHERE id = ?", (kod or None, ornek_id))
    baglanti.commit()
    return Response(status_code=204)


@router.get("/kkd/veri-seti.zip")
def veri_seti_indir(istek: Request, baglanti=Depends(baglanti_al)):
    """Etiketli örneklerin veri seti (docs/17 §5.8): güne göre bölünmüş kırpıklar,
    etiketler, bölme ve sha256 manifest'i. Model ürün dışında bununla eğitilir.

    Zip geçici dosyaya yazılır (binlerce kırpık belleğe sığmayabilir) ve
    gönderildikten sonra silinir.
    """
    ornekler = veri_seti.etiketli_ornekler(baglanti)
    if not ornekler:
        raise DogrulamaHatasi(
            "Dışa aktarılacak etiketli örnek yok. Örnekler, Baret ve Yelek etiketinin ikisi "
            "de verilince veri setine girer."
        )
    tanimlayici, gecici = tempfile.mkstemp(prefix="dalsan-kkd-", suffix=".zip")
    os.close(tanimlayici)
    try:
        manifest = veri_seti.disa_aktar(
            ornekler, istek.app.state.ayarlar.goruntu_klasoru, Path(gecici)
        )
    except BaseException:
        Path(gecici).unlink(missing_ok=True)
        raise
    # Kişi görüntüsü dışarı çıkıyor: kaç tane olduğu günlükte ve erişim izinde
    # kalsın (KVKK m.12, docs/17 §10.4)
    erisim_yaz(baglanti, istek, "export_dataset", f"kkd ({manifest['ornek_sayisi']} örnek)")
    _log.info(
        f"KKD veri seti dışa aktarıldı: {manifest['ornek_sayisi']} örnek, "
        f"{manifest['eksik_dosya']} eksik dosya."
    )
    return FileResponse(
        gecici,
        media_type="application/zip",
        filename=f"dalsan-kkd-veri-seti-{zaman.yerel_tarih_iso()}.zip",
        background=BackgroundTask(os.unlink, gecici),
    )


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
    if not dosya.is_relative_to(kok) or not dosya.is_file():
        return Response(status_code=404)
    erisim_yaz(baglanti, istek, "view_ppe_crop", f"sample:{ornek_id}")
    return FileResponse(dosya, media_type="image/jpeg")

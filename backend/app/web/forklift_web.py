"""Forklift sayfası: sahadan kare toplama, etiketleme, eğitim verisi ve model kurma.

Operatör, 24.09.2026: "gidip fabrikadan daha çok görüntü çekip mi yükleyeyim ve
sadece yüklesem yeter mi". Cevap bu sayfadır: kapı açılınca (KVKK onayıyla)
program forklift görünen kareleri kameralardan kendisi toplar; kullanıcı her
karede önerilen kutuları "Forklift / Transpalet / Değil" diye işaretler, eksik
forklifti fareyle çizer; eğitim verisi tek düğmeyle zip olarak iner. Kapalı
bilgisayardaki eğitimin (egitim/forklift/yerel.py) çıkardığı model yine bu
sayfadan, denetlenerek kurulur (app/egitim/forklift_kurulum.py).
Ayrıntılar ve saklama kuralları: app/egitim/forklift_verisi.py.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app import kaynaklar, zaman
from app.analiz.model_adi import YEREL_FORKLIFT_ADI, gorunen_model_adi
from app.analiz.tespit import ModelHatasi, Tespitci
from app.egitim import forklift_kurulum as fk
from app.egitim import forklift_verisi as fv
from app.hatalar import DogrulamaHatasi
from app.loglama import log_al
from app.olaylar.yazici import sistem_olayi_yaz
from app.web.erisim_izi import erisim_yaz
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()
_log = log_al("forklift")

# Tümünü silme onayı: yanlışlıkla basılan düğme haftaların etiketini silmesin.
SILME_ONAY_METNI = "Toplanan bütün forklift karelerini ve etiketlerini sil"
_PARCA = 1024 * 1024


def modeller_klasoru(ayarlar) -> Path:
    """Hazır modellerin klasörü (MODEL_DOSYASI=models/...); yerel model de oraya kurulur."""
    return ayarlar.kok_dizin / "models"


def _kurulum_mesaji(kuruldu: str, zaten: str) -> str:
    """Kurulumdan dönüşte tek satır. Ad, yerel model adı değilse yazılmaz."""
    ad = kuruldu or zaten
    if not YEREL_FORKLIFT_ADI.fullmatch(ad):
        return ""
    gorunen = gorunen_model_adi(ad)
    if zaten:
        return f"“{gorunen}” zaten kurulu."
    return (
        f"“{gorunen}” kuruldu. Kullanmak için Ayarlar'daki “Tanıma modeli” listesinden "
        f"seçip kaydedin; sonra {kaynaklar.baslatma_tarifi(cumle_basi=False)}. Açılamazsa "
        "sistem hazır modelle çalışmayı sürdürür."
    )


@router.get("/forklift", response_class=HTMLResponse)
def forklift_sayfasi(
    istek: Request, kuruldu: str = "", zaten: str = "", baglanti=Depends(baglanti_al)
):
    ayarlar = istek.app.state.ayarlar
    ozet = fv.ozet(baglanti)
    kareler = fv.etiketli_kareler(baglanti)
    bolme = fv.gun_bolmesi(k.gun for k in kareler)
    supervizor = getattr(istek.app.state, "supervizor", None)
    calisan = getattr(supervizor, "calisan_model", None)
    return sablonlar.TemplateResponse(
        istek,
        "forklift.html",
        {
            "aktif_sekme": "forklift",
            "toplama": fv.toplama_durumu(baglanti),
            "toplama_onay_metni": fv.TOPLAMA_ONAY_METNI,
            "silme_onay_metni": SILME_ONAY_METNI,
            "ozet": ozet,
            "saat_limiti": ayarlar.forklift_ornek_saat_limit,
            "en_cok": ayarlar.forklift_ornek_en_cok,
            "saklama_gun": ayarlar.forklift_ham_veri_saklama_gun,
            "sinir_doldu": ozet["toplam"] >= ayarlar.forklift_ornek_en_cok,
            "uyarilar": fv.uyarilar(kareler, bolme) if kareler else [],
            "test_gunu": sum(1 for kume in bolme.values() if kume == "test"),
            "kurulum_mesaji": _kurulum_mesaji(kuruldu, zaten),
            "modeller": fk.kurulu_modeller(modeller_klasoru(ayarlar), ayarlar.model_dosyasi),
            "calisan_model": calisan.name if calisan is not None else None,
        },
    )


async def _sinirli_yaz(dosya: UploadFile, hedef: Path, sinir: int, ne: str) -> None:
    """Yüklemeyi parça parça yazar; sınır aşılırsa ya da dosya boşsa durur."""
    yazilan = 0
    with hedef.open("wb") as cikti:
        while parca := await dosya.read(_PARCA):
            yazilan += len(parca)
            if yazilan > sinir:
                raise fk.KurulumHatasi(
                    f"{ne} beklenenden çok büyük (en fazla {sinir // (1024 * 1024)} MB). "
                    "KURULACAK klasöründeki dosyayı seçtiğinizden emin olun."
                )
            cikti.write(parca)
    if yazilan == 0:
        raise fk.KurulumHatasi(f"{ne} boş. KURULACAK klasöründeki dosyayı seçin.")


@router.post("/forklift/model")
async def model_kur(
    istek: Request,
    model: UploadFile | None = None,
    olcum: UploadFile | None = None,
    baglanti=Depends(baglanti_al),
):
    """Kapalı bilgisayardaki eğitimin modelini (.onnx) ve ölçümünü (.olcum.json)
    denetleyip kurar (app/egitim/forklift_kurulum.py). Seçim değişmez."""
    if model is None or olcum is None or not model.filename or not olcum.filename:
        raise fk.KurulumHatasi(
            "İki dosyayı da seçin: model (.onnx) ve ölçümü (.olcum.json). İkisi de eğitim "
            "klasöründeki KURULACAK'ta yan yanadır."
        )
    ayarlar = istek.app.state.ayarlar
    klasor = modeller_klasoru(ayarlar)
    klasor.mkdir(parents=True, exist_ok=True)
    gecici = klasor / f".kurulum-{secrets.token_hex(4)}.onnx.part"
    gecici_olcum = gecici.with_suffix(".json.part")

    def modeli_ac(yol: Path) -> Tespitci:
        # Ürünün kendi motoru, çalışan analizi yormasın diye tek iş parçacığıyla
        return Tespitci(yol, "cpu", is_parcacigi=1)

    try:
        await _sinirli_yaz(model, gecici, fk.EN_BUYUK_MODEL_BAYT, "Model dosyası")
        await _sinirli_yaz(olcum, gecici_olcum, fk.EN_BUYUK_OLCUM_BAYT, "Ölçüm dosyası")
        olcum_baytlari = gecici_olcum.read_bytes()
        try:
            ad, yeni = await run_in_threadpool(fk.kur, gecici, olcum_baytlari, klasor, modeli_ac)
        except ModelHatasi as hata:
            raise fk.KurulumHatasi(
                f"Model dosyası açılamadı; kurulmadı. {hata.kullanici_mesaji}",
                hata.teknik_ayrinti,
            ) from hata
    except OSError as hata:
        raise fk.KurulumHatasi(
            f"Model kaydedilemedi: {hata.strerror or 'disk hatası'}. Diskte yer olduğundan "
            "emin olun.",
            f"forklift modeli yazılamadı: {hata!r}",
        ) from hata
    finally:
        gecici.unlink(missing_ok=True)
        gecici_olcum.unlink(missing_ok=True)
    if not yeni:
        return RedirectResponse(f"/forklift?zaten={ad}#model", status_code=303)
    gorunen = gorunen_model_adi(ad)
    sistem_olayi_yaz(
        baglanti,
        f"Forklift modeli kuruldu: {gorunen}. Ayarlar'daki “Tanıma modeli” listesinden "
        "seçilebilir; seçilmedikçe çalışan model değişmez.",
        detaylar={"model": ad},
        kod="FORKLIFT_MODEL_INSTALLED",
    )
    _log.info(f"Forklift modeli kuruldu: {gorunen}", extra={"ayrinti": f"dosya: {klasor / ad}"})
    return RedirectResponse(f"/forklift?kuruldu={ad}#model", status_code=303)


@router.post("/forklift/toplama")
def toplama_degistir(
    istek: Request,
    ac: str = Form(...),
    onay: str = Form(""),
    baglanti=Depends(baglanti_al),
):
    """Toplamayı açar ya da kapatır, yeniden başlatmadan.

    Açmak onay ister: tam karede çalışanlar da görünür ve kişisel veri işlenir.
    Kapatmak onaysızdır ve hemen geçerlidir: örnekleme kapıyı her kareden önce
    okur. Her değişiklik Olaylar'a FORKLIFT_COLLECTION_CHANGED yazar.
    """
    acilsin = ac == "1"
    if acilsin and onay != "1":
        raise DogrulamaHatasi(
            f"Veri toplamayı açmak için onay kutusunu işaretleyin: “{fv.TOPLAMA_ONAY_METNI}”."
        )
    if fv.toplama_durumu(baglanti)["acik"] == acilsin:
        return RedirectResponse("/forklift", status_code=303)
    baglanti.execute(
        "UPDATE forklift_collection_gate SET enabled = ?, changed_at = ?, note = ? WHERE id = 1",
        (1 if acilsin else 0, zaman.simdi_utc(), fv.TOPLAMA_ONAY_METNI if acilsin else None),
    )
    baglanti.commit()
    sistem_olayi_yaz(
        baglanti,
        "Forklift eğitimi için kare toplama açıldı."
        if acilsin
        else "Forklift eğitimi için kare toplama kapatıldı; kare saklanmıyor.",
        detaylar={"toplama": "acik" if acilsin else "kapali"},
        kod="FORKLIFT_COLLECTION_CHANGED",
    )
    erisim_yaz(baglanti, istek, "forklift_collection_gate", "acik" if acilsin else "kapali")
    return RedirectResponse("/forklift", status_code=303)


@router.get("/forklift/etiket", response_class=HTMLResponse)
def etiket_sayfasi(
    istek: Request,
    id: int | None = None,
    sonra: int | None = None,
    baglanti=Depends(baglanti_al),
):
    """Tek karenin etiketleme ekranı. `id` o kare; `sonra` "Atla" düğmesidir
    (ondan sonraki etiketsiz kare, sona gelince baştan); ikisi de yoksa sıradaki
    etiketlenmemiş kare."""
    if id is not None:
        kimlik = id
    elif sonra is not None:
        kimlik = fv.sonraki_etiketsiz(baglanti, sonra=sonra) or fv.sonraki_etiketsiz(baglanti)
    else:
        kimlik = fv.sonraki_etiketsiz(baglanti)
    satir = None
    if kimlik is not None:
        satir = baglanti.execute(
            "SELECT s.*, c.name AS kamera_adi FROM forklift_samples s "
            "LEFT JOIN cameras c ON c.id = s.camera_id WHERE s.id = ?",
            (kimlik,),
        ).fetchone()
    kare = None
    if satir is not None:
        kare = {
            "id": satir["id"],
            "genislik": satir["width"],
            "yukseklik": satir["height"],
            "kamera": satir["kamera_adi"] or "silinmiş kamera",
            "zaman": zaman.ekranda_goster(satir["captured_at"]),
            "oneriler": json.loads(satir["proposals"] or "[]"),
            "etiketler": json.loads(satir["labels"]) if satir["labels"] is not None else None,
        }
    return sablonlar.TemplateResponse(
        istek,
        "forklift_etiket.html",
        {"aktif_sekme": "forklift", "kare": kare, "ozet": fv.ozet(baglanti)},
    )


@router.post("/forklift/{ornek_id}/etiket")
async def etiket_kaydet(ornek_id: int, istek: Request, baglanti=Depends(baglanti_al)):
    """Gövde: {"kutular": [{"kutu": [x1, y1, x2, y2], "sinif": "forklift"}]}.

    Boş liste "karede forklift yok" demektir. Döner: sıradaki kare.
    """
    try:
        govde = await istek.json()
    except ValueError as hata:
        raise DogrulamaHatasi("Etiket okunamadı; sayfayı yenileyin.") from hata
    kutular = govde.get("kutular") if isinstance(govde, dict) else None
    try:
        fv.etiketle(baglanti, ornek_id, kutular)
    except fv.EtiketHatasi as hata:
        raise DogrulamaHatasi(str(hata)) from hata
    return JSONResponse({"sonraki": fv.sonraki_etiketsiz(baglanti)})


@router.post("/forklift/{ornek_id}/sil")
def kare_sil(ornek_id: int, istek: Request, baglanti=Depends(baglanti_al)):
    """Kareyi dosyasıyla siler (işe yaramayan ya da mahremiyet gereği)."""
    if fv.ornek_sil(baglanti, istek.app.state.ayarlar.goruntu_klasoru, ornek_id):
        erisim_yaz(baglanti, istek, "forklift_frames_deleted", f"frame:{ornek_id}")
    return JSONResponse({"sonraki": fv.sonraki_etiketsiz(baglanti)})


@router.post("/forklift/hepsini-sil")
def hepsini_sil(istek: Request, onay: str = Form(""), baglanti=Depends(baglanti_al)):
    if onay != "1":
        raise DogrulamaHatasi(f"Silmek için onay kutusunu işaretleyin: “{SILME_ONAY_METNI}”.")
    sayi = fv.hepsini_sil(baglanti, istek.app.state.ayarlar.goruntu_klasoru)
    erisim_yaz(baglanti, istek, "forklift_frames_deleted", f"hepsi ({sayi} kare)")
    _log.info(f"Forklift eğitim kareleri silindi: {sayi} kare.")
    return RedirectResponse("/forklift", status_code=303)


@router.get("/forklift/kare/{ornek_id}.jpg")
def kare_goruntusu(istek: Request, ornek_id: int, baglanti=Depends(baglanti_al)):
    satir = baglanti.execute(
        "SELECT frame_path FROM forklift_samples WHERE id = ?", (ornek_id,)
    ).fetchone()
    if satir is None:
        return Response(status_code=404)
    kok = istek.app.state.ayarlar.goruntu_klasoru.resolve()
    dosya = (kok / satir["frame_path"]).resolve()
    if not dosya.is_relative_to(kok) or not dosya.is_file():
        return Response(status_code=404)
    erisim_yaz(baglanti, istek, "view_forklift_frame", f"frame:{ornek_id}")
    return FileResponse(dosya, media_type="image/jpeg")


@router.get("/forklift/veri-seti.zip")
def veri_seti_indir(istek: Request, baglanti=Depends(baglanti_al)):
    """Etiketli karelerin eğitim verisi (COCO, güne göre bölünmüş).

    Zip geçici dosyaya yazılır (binlerce kare belleğe sığmayabilir) ve
    gönderildikten sonra silinir.
    """
    kareler = fv.etiketli_kareler(baglanti)
    if not kareler:
        raise DogrulamaHatasi(
            "Dışa aktarılacak etiketli kare yok. Önce Forklift sayfasında kareleri etiketleyin."
        )
    tanimlayici, gecici = tempfile.mkstemp(prefix="dalsan-forklift-", suffix=".zip")
    os.close(tanimlayici)
    try:
        manifest = fv.disa_aktar(kareler, istek.app.state.ayarlar.goruntu_klasoru, Path(gecici))
    except BaseException:
        Path(gecici).unlink(missing_ok=True)
        raise
    # Çalışanları da gösteren kareler dışarı çıkıyor: sayı erişim izinde kalsın.
    erisim_yaz(baglanti, istek, "export_dataset", f"forklift ({manifest['kare_sayisi']} kare)")
    _log.info(
        f"Forklift eğitim verisi dışa aktarıldı: {manifest['kare_sayisi']} kare, "
        f"{manifest['eksik_dosya']} eksik dosya."
    )
    return FileResponse(
        gecici,
        media_type="application/zip",
        filename=f"dalsan-forklift-veri-seti-{zaman.yerel_tarih_iso()}.zip",
        background=BackgroundTask(os.unlink, gecici),
    )

"""Kural yönetimi: dört kural tipi için liste + form (docs/03).

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
from app.rules.motor import KALIBRASYON_GEREKTIREN
from app.rules.olay_kodu import (
    IHLAL_ONEMLERI,
    KURAL_VARSAYILAN_ONEMI,
    OLAY_KODLARI,
    ONEM_ADLARI,
    kural_olay_kodlari,
    kural_varsayilan_onemi,
    olay_onemi,
    onem_daha_hafif,
)
from app.rules.parametreler import KuralParametreHatasi, params_dogrula, varsayilan_params
from app.web.ortak import (
    BOLGE_TIPLERI,
    BOLGE_ZORUNLU_KURALLAR,
    EK_HAZIR_KURALLAR,
    HAZIR_KURALLAR,
    KURAL_TIPLERI,
    SINIFLAR,
    VARSAYILAN_COOLDOWN_SN,
    ayni_hazir_kural_var,
    baglanti_al,
    guvenli_json,
    hazir_kural_cooldown,
    hazir_kural_params,
)
from app.web.rotalar import sablonlar

router = APIRouter()


@router.get("/kurallar", response_class=HTMLResponse)
def kural_listesi(istek: Request, baglanti=Depends(baglanti_al)):
    kurallar = []
    for satir in baglanti.execute(
        "SELECT r.*, c.name AS kamera_adi, z.name AS bolge_adi, z.zone_type AS bolge_tipi "
        "FROM rules r JOIN cameras c ON c.id = r.camera_id "
        "LEFT JOIN zones z ON z.id = r.zone_id ORDER BY c.name, r.id"
    ):
        kural = dict(satir)
        kural["tip_adi"] = KURAL_TIPLERI.get(kural["rule_type"], kural["rule_type"])
        kural.update(_listedeki_onem(kural))
        kural["kalibrasyon_bekliyor"] = False
        if kural["rule_type"] in KALIBRASYON_GEREKTIREN:
            kalibre = baglanti.execute(
                "SELECT 1 FROM camera_calibrations WHERE camera_id = ?",
                (kural["camera_id"],),
            ).fetchone()
            # Kalibre edilmemiş kamerada mesafe ve hız kuralı PASİFTİR
            # (docs/03 §2 ve §4) — rozet bunu söylemezse ekran çalışmayan
            # bir kuralı "aktif" gösterirdi.
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
    # Her tipin alanları kendi değerleriyle dolar: düzenlenen kuralın tipi
    # kaydındaki değerlerle, öbür tipler şemanın varsayılanlarıyla (R25).
    # Eskiden form sayıların ikinci bir kopyasını tutuyordu ve başka tipin
    # alanı düzenlenen kuralın değerini gösterebiliyordu (KKD'nin kalış
    # süresi bölge kuralınınkini).
    degerler = {tip: varsayilan_params(tip) for tip in KURAL_TIPLERI}
    onem_bilgisi = None  # yeni kuralda tarayıcı /kurallar/onem'den sorar
    if kural is not None and kural["rule_type"] in degerler:
        tip = kural["rule_type"]
        try:
            degerler[tip] = params_dogrula(tip, kural["params"])
        except KuralParametreHatasi:
            degerler[tip] = {**degerler[tip], **kural["params"]}
        bolge = next((b for b in bolgeler if b["id"] == kural["zone_id"]), None)
        onem_bilgisi = _onem_bilgisi(
            tip, bolge["zone_type"] if bolge else None, degerler[tip], kural["target_classes"]
        )
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
            "degerler": degerler,
            "cooldown_varsayilanlari": VARSAYILAN_COOLDOWN_SN,
            "cooldown_json": guvenli_json(VARSAYILAN_COOLDOWN_SN),
            "onem_secimi": (kural or {}).get("severity") or KURAL_VARSAYILAN_ONEMI,
            "onem": onem_bilgisi,
        },
    )


def _onem_bilgisi(kural_tipi: str, bolge_tipi, params: dict, hedefler) -> dict:
    """Kuralın varsayılan önemi ve hangi olaydan geldiği (form ve /kurallar/onem)."""
    kodlar = kural_olay_kodlari(kural_tipi, bolge_tipi, params, hedefler)
    parcalar = []
    for kod in kodlar:
        tanim = OLAY_KODLARI[kod]
        metin = f"{tanim.ad}: {ONEM_ADLARI[tanim.onem]}"
        yukselmis = olay_onemi(kod, arac_ayni_bolgede=True)
        if yukselmis != tanim.onem:
            metin += f", aynı bölgede araç varken {ONEM_ADLARI[yukselmis]}"
        parcalar.append(metin)
    varsayilan = kural_varsayilan_onemi(kural_tipi, bolge_tipi, params, hedefler)
    return {
        "varsayilan": varsayilan,
        "varsayilan_adi": ONEM_ADLARI[varsayilan],
        "aciklama": "; ".join(parcalar),
    }


def _listedeki_onem(kural: dict) -> dict:
    """Kurallar listesinin Önem sütunu: açık seçim ya da olay kodunun varsayılanı."""
    if kural.get("severity") in IHLAL_ONEMLERI:
        return {
            "onem": kural["severity"],
            "onem_adi": ONEM_ADLARI[kural["severity"]],
            "onem_varsayilan": False,
        }
    try:
        params = json.loads(kural["params"])
        hedefler = json.loads(kural["target_classes"])
        bilgi = _onem_bilgisi(kural["rule_type"], kural.get("bolge_tipi"), params, hedefler)
    except (ValueError, TypeError, AttributeError):
        # Bozuk JSON ya da bilinmeyen tip: liste yine açılır, sütun boş kalır
        return {"onem": "", "onem_adi": "", "onem_varsayilan": True}
    return {
        "onem": bilgi["varsayilan"],
        "onem_adi": bilgi["varsayilan_adi"],
        "onem_varsayilan": True,
    }


@router.get("/kurallar/onem")
def kural_onem_varsayilani(
    istek: Request,
    rule_type: str,
    zone_id: int = 0,
    mode: str = "inside",
    baglanti=Depends(baglanti_al),
):
    """Formda seçilenlere göre "Varsayılan" önemin ne olduğu (JSON).

    Hesap burada, rules/olay_kodu.py'de yapılır: tarayıcıda eşlemenin ikinci
    bir kopyası tutulmaz. Kaydederken aynı hesap yeniden yapılır; bu uç
    yalnız formu bilgilendirir.
    """
    if rule_type not in KURAL_TIPLERI:
        raise DogrulamaHatasi(f"Geçersiz kural tipi: {rule_type}")
    bolge_tipi = None
    if zone_id:
        satir = baglanti.execute("SELECT zone_type FROM zones WHERE id = ?", (zone_id,)).fetchone()
        bolge_tipi = satir["zone_type"] if satir else None
    # Çok değerli alanlar (onay kutuları): ?hedef=person&hedef=forklift
    params = {"mode": mode, "required_ppe": istek.query_params.getlist("kkd")}
    return _onem_bilgisi(rule_type, bolge_tipi, params, istek.query_params.getlist("hedef"))


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
    if kural_tipi in BOLGE_ZORUNLU_KURALLAR and zone_id is None:
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

    # Düzenlemede formda OLMAYAN parametreler korunur: form yalnız gösterdiği
    # alanları gönderir; kaydetmek, formun bilmediği bir değeri (ileride
    # eklenecek bir alan, elle ayarlanmış bir eşik) sessizce varsayılana
    # döndürmemeli. Tip değiştiyse eski tipin parametreleri taşınmaz.
    onceki_params: dict = {}
    if kural_id:
        eski = baglanti.execute(
            "SELECT rule_type, params FROM rules WHERE id = ?", (kural_id,)
        ).fetchone()
        if eski is None:
            raise DogrulamaHatasi(
                "Kural bulunamadı. Silinmiş olabilir; Kurallar sayfasını yenileyin."
            )
        if eski["rule_type"] == kural_tipi:
            try:
                onceki_params = json.loads(eski["params"])
            except ValueError:
                onceki_params = {}
            if not isinstance(onceki_params, dict):
                onceki_params = {}
    params, hedefler = _formdan_params(kural_tipi, form)
    params = params_dogrula(kural_tipi, {**onceki_params, **params})  # Türkçe hatayla reddeder
    onem = _formdan_onem(
        form, kural_tipi, bolge["zone_type"] if zone_id is not None else None, params, hedefler
    )

    cooldown = _sayi(form, "cooldown_s", VARSAYILAN_COOLDOWN_SN[kural_tipi])
    if not 5 <= cooldown <= 86400:
        raise DogrulamaHatasi(
            "Cooldown 5 saniye ile 86400 saniye (24 saat) arasında olmalı; "
            f"şu an {cooldown:g} yazılmış."
        )
    anons_id = int(form.get("announcement_id") or 0) or None
    aktif = 1 if form.get("enabled") == "1" else 0
    # Gölge mod: kural çalışır ve olay yazar, ama anons çalmaz / ekranda uyarı
    # bandı çıkmaz (docs/04 §8.2). Yeni kuralın güvenli deneme yoludur.
    golge = 1 if form.get("shadow_mode") == "1" else 0
    simdi = zaman.simdi_utc()

    if kural_id:
        baglanti.execute(
            "UPDATE rules SET camera_id=?, rule_type=?, zone_id=?, target_classes=?, "
            "params=?, cooldown_s=?, announcement_id=?, enabled=?, shadow_mode=?, "
            "severity=?, updated_at=? WHERE id=?",
            (
                kamera_id,
                kural_tipi,
                zone_id,
                json.dumps(hedefler),
                json.dumps(params),
                cooldown,
                anons_id,
                aktif,
                golge,
                onem,
                simdi,
                kural_id,
            ),
        )
    else:
        baglanti.execute(
            "INSERT INTO rules (camera_id, rule_type, zone_id, target_classes, params, "
            "cooldown_s, announcement_id, enabled, shadow_mode, severity, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                kamera_id,
                kural_tipi,
                zone_id,
                json.dumps(hedefler),
                json.dumps(params),
                cooldown,
                anons_id,
                aktif,
                golge,
                onem,
                simdi,
            ),
        )
    baglanti.commit()
    return RedirectResponse("/kurallar", status_code=303)


@router.post("/kurallar/hazir")
def hazir_kural_ekle(
    zone_id: int = Form(...),
    ek: str = Form(""),
    baglanti=Depends(baglanti_al),
):
    """Tek tıkla, bölge tipine uygun kuralı kurar (docs/03 eşlemesi).

    Kullanıcı bölgeyi çizip "hiçbir şey olmuyor" durumunda kalmasın diye HER
    bölge tipinin bir karşılığı vardır: yaya yolu → yolun DIŞINDA kalan kişi,
    yasak bölge / yükleme alanı → bölgede kalan kişi, tır park alanı → alanın
    dışında duran tır, araç sahası → güvenli mesafe, KKD alanı → baret/yelek.
    Eşleme app/web/ortak.py'deki HAZIR_KURALLAR tablosunda; eşikler
    app/rules/parametreler.py'den gelir (docs/03 tabloları, tek kaynak).

    Kurulan kural sıradan bir kuraldır: Kurallar sayfasından düzenlenebilir.
    `ek` verilirse bölge tipinin EK hazır kuralı kurulur (EK_HAZIR_KURALLAR:
    yaya yolunda araç, araç yolunda yaya); ekler gölge modda doğar.
    """
    bolge = baglanti.execute(
        "SELECT id, camera_id, zone_type, name FROM zones WHERE id = ?", (zone_id,)
    ).fetchone()
    if bolge is None:
        raise DogrulamaHatasi("Bölge bulunamadı. Silinmiş olabilir; sayfayı yenileyin.")
    if ek:
        hazir = next(
            (h for h in EK_HAZIR_KURALLAR.get(bolge["zone_type"], ()) if h.anahtar == ek), None
        )
    else:
        hazir = HAZIR_KURALLAR.get(bolge["zone_type"])
    if hazir is None:
        raise DogrulamaHatasi(
            f"'{BOLGE_TIPLERI.get(bolge['zone_type'], bolge['zone_type'])}' tipindeki bölge "
            "için bu hazır kural yok. Kurallar sayfasından elle tanımlayabilirsiniz."
        )
    if ayni_hazir_kural_var(baglanti, zone_id, hazir):
        raise DogrulamaHatasi(
            f"'{bolge['name']}' bölgesinde zaten bir kural var: {hazir.kisa_ad}. "
            "Kurallar sayfasından düzenleyin."
        )

    anons_id = None
    if hazir.anons_anahtari:
        anons = baglanti.execute(
            "SELECT id FROM announcement_messages WHERE key = ?", (hazir.anons_anahtari,)
        ).fetchone()
        anons_id = anons["id"] if anons else None

    baglanti.execute(
        "INSERT INTO rules (camera_id, rule_type, zone_id, target_classes, params, "
        "cooldown_s, announcement_id, enabled, shadow_mode, updated_at) "
        "VALUES (?,?,?,?,?,?,?,1,?,?)",
        (
            bolge["camera_id"],
            hazir.kural_tipi,
            zone_id,
            json.dumps(list(hazir.hedef_siniflar)),
            json.dumps(hazir_kural_params(hazir)),
            hazir_kural_cooldown(hazir),
            anons_id,
            1 if hazir.golge else 0,
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


def _formdan_onem(form, kural_tipi: str, bolge_tipi, params: dict, hedefler) -> str:
    """Formdaki önem seçimi (docs/17 §6.2). "Varsayılan" = olay kodunun önemi.

    Varsayılanın ALTINA inmek (Yüksek bir olayı Orta yazmak) onay ister: ekran
    rengi, sıra ve kuyruk önemden gelir; yanlışlıkla düşürülen önem gerçek bir
    tehlikeyi listenin gerisine iter. Onay kutusu formda sarı uyarıyla çıkar;
    burada yeniden denetlenir — tarayıcıya güvenilmez.
    """
    onem = form.get("severity") or KURAL_VARSAYILAN_ONEMI
    if onem == KURAL_VARSAYILAN_ONEMI:
        return onem
    if onem not in IHLAL_ONEMLERI:
        raise DogrulamaHatasi(f"Geçersiz önem: {onem}")
    varsayilan = kural_varsayilan_onemi(kural_tipi, bolge_tipi, params, hedefler)
    if onem_daha_hafif(onem, varsayilan) and form.get("onem_onay") != "1":
        raise DogrulamaHatasi(
            f"Seçilen önem ({ONEM_ADLARI[onem]}) bu kuralın varsayılanından "
            f"({ONEM_ADLARI[varsayilan]}) düşük. Böyle kaydetmek için formdaki "
            "“Önemi varsayılanın altına indirdiğimi biliyorum” kutusunu işaretleyin; "
            "emin değilseniz “Varsayılan”ı seçin."
        )
    return onem


# Formun gösterdiği alanlar, tipe göre. Sayı alanı boş bırakılırsa sözlüğe
# girmez: değeri önceki kayıttan ya da şemanın varsayılanından gelir (R25 —
# formda varsayılan sayıların ikinci bir kopyası tutulmaz). Onay kutusu
# işaretsizse False'tur; bu yüzden her kutu formda gerçekten bulunmalı
# (tests/test_kural_formu.py hepsini arar).
_SAYI_ALANLARI: dict[str, tuple[str, ...]] = {
    "zone_intrusion": ("min_dwell_s", "bitis_s"),
    "safe_distance": ("distance_m", "min_frames", "min_speed_mps", "bitis_s", "histerezis_m"),
    "ppe_violation": (
        "min_person_height_px",
        "min_vest_height_px",
        "min_confidence",
        "window_size",
        "min_valid_observations",
        "violation_ratio",
        "min_dwell_s",
        "bitis_s",
        "surucu_ortusme_orani",
    ),
    "vehicle_speed": ("speed_limit_mps", "window_size", "bitis_s"),
}
# Boş bırakılınca KAPALI (None) olan eşikler: öbür sayı alanlarında boş,
# "önceki değer ya da varsayılan" demektir; bunlarda "kapat" demektir.
_BOS_KAPALI_ALANLAR: dict[str, tuple[str, ...]] = {
    "ppe_violation": ("max_kisi_ortusmesi", "min_netlik"),
}
_KUTU_ALANLARI: dict[str, tuple[str, ...]] = {
    "zone_intrusion": ("gecit_haric",),
    "safe_distance": ("require_moving_vehicle",),
    "ppe_violation": ("require_full_bbox", "surucu_muaf"),
    "vehicle_speed": (),
}
_TAM_SAYI_ALANLARI = frozenset(
    {
        "min_frames",
        "window_size",
        "min_person_height_px",
        "min_vest_height_px",
        "min_valid_observations",
    }
)


def _formdan_params(kural_tipi: str, form) -> tuple[dict, list[str]]:
    """Form alanlarını kural tipine göre params sözlüğüne çevirir."""
    params: dict = {}
    for alan in _SAYI_ALANLARI[kural_tipi]:
        deger = _sayi(form, alan, None)
        if deger is not None:
            params[alan] = int(deger) if alan in _TAM_SAYI_ALANLARI else deger
    for alan in _KUTU_ALANLARI[kural_tipi]:
        params[alan] = form.get(alan) == "1"
    for alan in _BOS_KAPALI_ALANLAR.get(kural_tipi, ()):
        params[alan] = _sayi(form, alan, None)

    if kural_tipi == "zone_intrusion":
        hedefler = form.getlist("target_classes")
        if not hedefler:
            raise DogrulamaHatasi("En az bir hedef sınıf seçin (insan / forklift / tır).")
        params["mode"] = form.get("mode", "inside")
        return params, hedefler
    if kural_tipi == "safe_distance":
        nesneler = form.getlist("object_classes") or ["forklift", "truck"]
        params["subject_classes"] = ["person"]
        params["object_classes"] = nesneler
        return params, ["person", *nesneler]
    if kural_tipi == "vehicle_speed":
        return params, form.getlist("speed_classes") or ["forklift", "truck"]
    # ppe_violation
    kkdler = form.getlist("required_ppe")
    if not kkdler:
        raise DogrulamaHatasi("En az bir KKD seçin (baret / yelek).")
    params["required_ppe"] = kkdler
    return params, ["person"]


def _sayi(form, alan: str, varsayilan: float | None) -> float | None:
    ham = (form.get(alan) or "").strip().replace(",", ".")
    if not ham:
        return varsayilan
    try:
        return float(ham)
    except ValueError:
        raise DogrulamaHatasi(f"'{alan}' alanı sayı olmalı; '{ham}' yazılmış.") from None

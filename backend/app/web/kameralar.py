"""Kamera yönetimi: liste, ekleme/düzenleme, canlı önizleme, bölgeler, kalibrasyon."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.rules.kalibrasyon import homografi_hesapla
from app.web.ortak import (
    BOLGE_TIPLERI,
    HAZIR_KURALLAR,
    KURAL_TIPLERI,
    SINIFLAR,
    baglanti_al,
    guvenli_json,
    hazir_kural_aciklamasi,
    rtsp_maskele,
)
from app.web.rotalar import sablonlar

router = APIRouter()


class KameraBulunamadi(DogrulamaHatasi):
    http_kodu = 404


class BolgeBulunamadi(DogrulamaHatasi):
    http_kodu = 404


# Kullanıcıya görünen durum rozeti: (metin, renk sınıfı)
DURUM_ROZETLERI = {
    "online": ("çevrimiçi", "yesil"),
    "connecting": ("bağlanıyor", "sari"),
    "offline": ("çevrimdışı", "kirmizi"),
}


def _kamera_getir(baglanti, kamera_id: int) -> dict:
    satir = baglanti.execute("SELECT * FROM cameras WHERE id = ?", (kamera_id,)).fetchone()
    if satir is None:
        raise KameraBulunamadi(f"Kamera bulunamadı (id {kamera_id}). Silinmiş olabilir.")
    return dict(satir)


def _rozet(kamera: dict) -> tuple[str, str]:
    if not kamera["enabled"]:
        return ("pasif", "gri")
    return DURUM_ROZETLERI.get(kamera["status"], DURUM_ROZETLERI["offline"])


@router.get("/kameralar", response_class=HTMLResponse)
def kamera_listesi(istek: Request, baglanti=Depends(baglanti_al)):
    kameralar = []
    for satir in baglanti.execute("SELECT * FROM cameras ORDER BY name"):
        kamera = dict(satir)
        kamera["maskeli_url"] = rtsp_maskele(kamera["source_url"])
        kamera["son_kare"] = (
            zaman.ekranda_goster(kamera["last_frame_at"]) if kamera["last_frame_at"] else "—"
        )
        kamera["rozet"], kamera["rozet_rengi"] = _rozet(kamera)
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
    source_url = _kamera_dogrula(name, source_type, source_url, sample_fps)
    simdi = zaman.simdi_utc()
    imlec = baglanti.execute(
        "INSERT INTO cameras (name, area, source_type, source_url, sample_fps, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name.strip(), area.strip(), source_type, source_url, sample_fps, simdi, simdi),
    )
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{imlec.lastrowid}", status_code=303)


@router.get("/kameralar/{kamera_id}", response_class=HTMLResponse)
def kamera_detay(istek: Request, kamera_id: int, duzenle: int = 0, baglanti=Depends(baglanti_al)):
    """Kamera sayfası. `?duzenle=<bölge id>` çizim kutusunu DÜZENLEME kipinde açar:
    bölgenin adı/tipi forma, poligonu da tuvale yüklenir."""
    kamera = _kamera_getir(baglanti, kamera_id)
    kamera["maskeli_url"] = rtsp_maskele(kamera["source_url"])
    kamera["rozet"], kamera["rozet_rengi"] = _rozet(kamera)

    bolgeler = []
    for satir in baglanti.execute(
        "SELECT * FROM zones WHERE camera_id = ? ORDER BY id", (kamera_id,)
    ):
        bolge = dict(satir)
        bolge["tip_adi"] = BOLGE_TIPLERI.get(bolge["zone_type"], bolge["zone_type"])
        bolge["noktalar"] = json.loads(bolge["polygon"])
        bolge["kurali_var"] = (
            baglanti.execute("SELECT 1 FROM rules WHERE zone_id = ?", (bolge["id"],)).fetchone()
            is not None
        )
        # Bölge tipinin tek tıkla kurulabilen kural karşılığı (docs/03 eşlemesi)
        hazir = HAZIR_KURALLAR.get(bolge["zone_type"])
        bolge["hazir_kisa_ad"] = hazir.kisa_ad if hazir else ""
        bolge["hazir_aciklama"] = hazir_kural_aciklamasi(hazir) if hazir else ""
        bolge["hazir_kural_tipi"] = hazir.kural_tipi if hazir else ""
        bolgeler.append(bolge)

    # Düzenlenen bölge tuvale "çizilmekte olan bölge" olarak yüklenir; kayıtlı
    # bölgeler listesinden ÇIKARILIR, yoksa aynı bölge iki kez çizilir.
    duzenlenen = next((b for b in bolgeler if b["id"] == duzenle), None)

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
            "bolgeler_json": guvenli_json(
                [
                    {
                        "id": b["id"],
                        "poligon": b["noktalar"],
                        "ad": b["name"],
                        # Görüntüde bölgeye tıklanınca çıkan kutu tipi de yazar:
                        # "Rampa önü · Yükleme alanı" (kamera_detay.js).
                        "tip_adi": b["tip_adi"],
                        "aktif": bool(b["enabled"]),
                    }
                    for b in bolgeler
                    if duzenlenen is None or b["id"] != duzenlenen["id"]
                ]
            ),
            "duzenlenen": duzenlenen,
            "duzenlenen_json": (
                guvenli_json(
                    {
                        "id": duzenlenen["id"],
                        "ad": duzenlenen["name"],
                        "tip": duzenlenen["zone_type"],
                        "poligon": duzenlenen["noktalar"],
                    }
                )
                if duzenlenen
                else "null"
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
    source_url = _kamera_dogrula(name, source_type, source_url, sample_fps)
    baglanti.execute(
        "UPDATE cameras SET name = ?, area = ?, source_type = ?, source_url = ?, "
        "sample_fps = ?, enabled = ?, updated_at = ? WHERE id = ?",
        (
            name.strip(),
            area.strip(),
            source_type,
            source_url,
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


@router.get("/kameralar/{kamera_id}/durum.json")
def kamera_durumu(istek: Request, kamera_id: int, baglanti=Depends(baglanti_al)):
    """Kamera sayfasının canlı durum satırı: bağlanıyor / çevrimiçi / çevrimdışı
    + bağlanamama SEBEBİ. Kullanıcı günlük dosyasına bakmak zorunda kalmaz."""
    kamera = _kamera_getir(baglanti, kamera_id)
    if not kamera["enabled"]:
        return {
            "durum": "pasif",
            "mesaj": "Kamera pasif — izlenmiyor. Aşağıdaki 'Kamera aktif' kutusunu "
            "işaretleyip Kaydet'e basın.",
        }
    supervizor = getattr(istek.app.state, "supervizor", None)
    if supervizor is None:
        return {
            "durum": "kapali",
            "mesaj": "Analiz başlatılmadı.",
            "sayim": {},
            "bolge_sayimlari": [],
        }
    durum = supervizor.kamera_durumu(kamera_id)
    durum["sayim_tr"] = {SINIFLAR.get(s, s): n for s, n in durum.get("sayim", {}).items()}
    durum["bolge_sayimlari"] = _sayimlari_adlandir(
        baglanti, kamera_id, durum.get("bolge_sayimlari", [])
    )
    return durum


def _sayimlari_adlandir(baglanti, kamera_id: int, sayimlar: list[dict]) -> list[dict]:
    """Sayım tablosuna bölge ADINI ve Türkçe sınıf adlarını ekler.

    Analiz katmanı bölgeyi yalnızca id ile bilir; ekranda id gösterilemez.
    Adlar burada, ekrana en yakın yerde eklenir — böylece bir bölgenin adı
    değişince analiz iş parçacığının yeniden yüklenmesi gerekmez.
    """
    if not sayimlar:
        return []
    adlar = {
        satir["id"]: (satir["name"], satir["zone_type"])
        for satir in baglanti.execute(
            "SELECT id, name, zone_type FROM zones WHERE camera_id = ?", (kamera_id,)
        )
    }
    zenginlestirilmis = []
    for sayim in sayimlar:
        ad, tip = adlar.get(sayim["bolge_id"], ("", ""))
        if not ad:
            continue  # bölge bu arada silinmiş: adsız satır ekranda anlamsızdır
        zenginlestirilmis.append(
            {
                **sayim,
                "ad": ad,
                "tip_adi": BOLGE_TIPLERI.get(tip, tip),
                "anlik_tr": {SINIFLAR.get(s, s): n for s, n in sayim.get("anlik", {}).items()},
                "giren_tr": {SINIFLAR.get(s, s): n for s, n in sayim.get("giren", {}).items()},
            }
        )
    return zenginlestirilmis


@router.post("/kameralar/{kamera_id}/sayac-sifirla")
def sayaci_sifirla(istek: Request, kamera_id: int, baglanti=Depends(baglanti_al)):
    """Vardiya başı: 'kaç tane girdi' sayaçlarını sıfırlar.

    ANLIK sayı sıfırlanmaz — o, o anda görülen gerçektir (rules/sayim.py).
    """
    _kamera_getir(baglanti, kamera_id)
    supervizor = getattr(istek.app.state, "supervizor", None)
    yapildi = supervizor.sayaci_sifirla(kamera_id) if supervizor is not None else False
    return {
        "tamam": yapildi,
        "mesaj": (
            "Giriş sayaçları sıfırlandı. Bölgede o anda bulunanlar sayılmaya devam eder."
            if yapildi
            else "Sayaç sıfırlanamadı: bu kameranın analizi çalışmıyor. Kontrol "
            "Paneli'nde Sistemi Başlat'a basın."
        ),
    }


@router.get("/kameralar/{kamera_id}/onizleme.jpg")
def kamera_onizleme(istek: Request, kamera_id: int, bolgesiz: bool = False):
    """Canlı önizleme karesi.

    bolgesiz=1 → kayıtlı bölgeler görüntünün İÇİNE çizilmez. Bölge çizim
    sayfası bölgeleri kendi tuvaline çizer; sunucu da çizerse tek bölgenin iki
    ayrı çizgisi görünür ve kullanıcı sistemin bölgeyi yanlış gördüğünü sanır.
    """
    supervizor = getattr(istek.app.state, "supervizor", None)
    jpeg = supervizor.onizleme_jpeg(kamera_id, bolgeler_dahil=not bolgesiz) if supervizor else None
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
    ad = _bolge_adi_dogrula(name)
    _bolge_tipi_dogrula(zone_type)
    noktalar = _poligon_dogrula(polygon)
    baglanti.execute(
        "INSERT INTO zones (camera_id, name, zone_type, polygon, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (kamera_id, ad, zone_type, json.dumps(noktalar), zaman.simdi_utc()),
    )
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{kamera_id}", status_code=303)


@router.post("/bolgeler/{bolge_id}/duzenle")
def bolge_guncelle(
    bolge_id: int,
    name: str = Form(...),
    zone_type: str = Form(...),
    polygon: str = Form(""),  # boş → mevcut çizim korunur (yalnız ad/tip değişir)
    baglanti=Depends(baglanti_al),
):
    """Bölgenin adını, tipini ve çizimini DEĞİŞTİRİR — silmeden.

    Bu uç nokta olmadan, adını düzeltmek isteyen kullanıcının tek yolu bölgeyi
    silmekti; silme ise (şemadaki ON DELETE CASCADE yüzünden) o bölgeye bağlı
    KURALLARI da götürüyordu. Güncelleme kuralların hiçbirine dokunmaz.
    """
    bolge = _bolge_getir(baglanti, bolge_id)
    ad = _bolge_adi_dogrula(name)
    _bolge_tipi_dogrula(zone_type)
    # Boş poligon "çizimi değiştirmedim" demektir: kayıtlı çizim korunur.
    # Kayıtlı çizim de aynı doğrulamadan geçer; bozuksa Türkçe hata verir.
    noktalar = _poligon_dogrula(polygon if polygon.strip() else bolge["polygon"])

    # KKD kuralı YALNIZCA 'KKD zorunlu alan' bölgesinde çalışır. Tip değişirse
    # kural kayıtta kalır ama hiçbir zaman uyarı üretmezdi — sessiz başarısızlık.
    if zone_type != "ppe_required" and bolge["zone_type"] == "ppe_required":
        kkd_kurali = baglanti.execute(
            "SELECT 1 FROM rules WHERE zone_id = ? AND rule_type = 'ppe_violation'",
            (bolge_id,),
        ).fetchone()
        if kkd_kurali is not None:
            raise DogrulamaHatasi(
                f"'{bolge['name']}' bölgesine bağlı bir KKD (baret/yelek) kuralı var; bu yüzden "
                "tipi 'KKD zorunlu alan' dışına çevrilemez. Önce Kurallar sayfasından o kuralı "
                "silin, sonra tipi değiştirin."
            )

    baglanti.execute(
        "UPDATE zones SET name = ?, zone_type = ?, polygon = ?, updated_at = ? WHERE id = ?",
        (ad, zone_type, json.dumps(noktalar), zaman.simdi_utc(), bolge_id),
    )
    _kamera_damgasi_tazele(baglanti, bolge["camera_id"])
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{bolge['camera_id']}", status_code=303)


@router.post("/bolgeler/{bolge_id}/durum")
def bolge_durumu_degistir(
    bolge_id: int,
    enabled: str = Form(...),  # "1" = aç, "0" = kapat
    baglanti=Depends(baglanti_al),
):
    """Bölgeyi SİLMEDEN geçici olarak kapatır/açar.

    Bakım, tadilat ya da yanlış alarm avı sırasında bölgeyi kapatmak gerekir;
    silmek gerekmez. Kapalı bölge görüntüde çizilmez ve bölge kuralları
    çalışmaz. Bölgeye bağlı kurallar tanımlı kalır, açınca aynen döner.
    """
    bolge = _bolge_getir(baglanti, bolge_id)
    baglanti.execute(
        "UPDATE zones SET enabled = ?, updated_at = ? WHERE id = ?",
        (1 if enabled == "1" else 0, zaman.simdi_utc(), bolge_id),
    )
    _kamera_damgasi_tazele(baglanti, bolge["camera_id"])
    baglanti.commit()
    return RedirectResponse(f"/kameralar/{bolge['camera_id']}", status_code=303)


@router.post("/bolgeler/{bolge_id}/sil")
def bolge_sil(bolge_id: int, baglanti=Depends(baglanti_al)):
    satir = baglanti.execute("SELECT camera_id FROM zones WHERE id = ?", (bolge_id,)).fetchone()
    if satir is None:
        return RedirectResponse("/kameralar", status_code=303)
    baglanti.execute("DELETE FROM zones WHERE id = ?", (bolge_id,))
    _kamera_damgasi_tazele(baglanti, satir["camera_id"])
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


def dosya_yolu_duzelt(ham: str) -> str:
    """Kullanıcının yapıştırdığı dosya yolunu OpenCV'nin açabileceği hale getirir.

    Karşılanan biçimler: tırnaklı yol (Windows "Yol olarak kopyala"),
    file:// adresi (tarayıcıdan sürükleme), Terminal'den sürüklemede boşlukların
    önüne gelen ters bölü kaçışları (Mac) ve ~ kısaltması.
    """
    yol = ham.strip().strip('"').strip("'").strip()
    if yol.lower().startswith("file://"):
        yol = unquote(yol[7:])
        if re.match(r"^/[A-Za-z]:", yol):  # file:///C:/... → C:/...
            yol = yol[1:]
    yol = yol.replace("\\ ", " ")
    return os.path.expanduser(yol)


def _kamera_dogrula(name: str, source_type: str, source_url: str, sample_fps: float) -> str:
    """Formu doğrular; kaydedilecek (temizlenmiş) kaynak adresini döndürür."""
    if not name.strip():
        raise DogrulamaHatasi("Kamera adı boş olamaz.")
    if source_type not in ("rtsp", "file"):
        raise DogrulamaHatasi("Kaynak tipi 'rtsp' veya 'file' olmalı.")
    if not 0.5 <= sample_fps <= 30:
        raise DogrulamaHatasi("Örnekleme hızı 0,5 ile 30 fps arasında olmalı.")
    adres = source_url.strip()
    if not adres:
        raise DogrulamaHatasi(
            "Kaynak adresi boş olamaz. RTSP örneği: rtsp://kullanici:sifre@192.168.1.64:554/... "
            "— Video dosyası örneği: /Users/adiniz/Desktop/test.mp4"
        )
    if source_type == "rtsp":
        if not adres.lower().startswith("rtsp://"):
            raise DogrulamaHatasi(
                "RTSP adresi rtsp:// ile başlamalı. Örnek: "
                "rtsp://kullanici:sifre@192.168.1.64:554/Streaming/Channels/102 — "
                "Bilgisayardaki bir video dosyasını izlemek için kaynak tipini "
                "'Video dosyası' yapın."
            )
        if not urlsplit(adres).hostname:
            raise DogrulamaHatasi(
                "RTSP adresinde kamera IP'si okunamadı. Biçim: rtsp://kullanici:sifre@IP:554/yol"
            )
        return adres
    yol = dosya_yolu_duzelt(adres)
    if not Path(yol).is_file():
        raise DogrulamaHatasi(
            f"Video dosyası bulunamadı: {yol} — Dosyanın TAM yolunu yazın. "
            "Mac'te: dosyayı Finder'da seçip Option+Command+C ile yolu kopyalayın. "
            "Windows'ta: dosyaya Shift + sağ tık → 'Yol olarak kopyala'."
        )
    return yol


def _bolge_getir(baglanti, bolge_id: int) -> dict:
    satir = baglanti.execute("SELECT * FROM zones WHERE id = ?", (bolge_id,)).fetchone()
    if satir is None:
        raise BolgeBulunamadi(f"Bölge bulunamadı (id {bolge_id}). Silinmiş olabilir.")
    return dict(satir)


def _kamera_damgasi_tazele(baglanti, kamera_id: int) -> None:
    """Kameranın updated_at damgasını tazeler.

    Süpervizör konfigürasyonu damgaya bakarak yeniden yükler; bölge silinince
    zones tablosunun MAX(updated_at) değeri değişmeyebilir. Damga tazelenmezse
    değişiklik program yeniden başlatılana kadar görülmez.
    """
    baglanti.execute(
        "UPDATE cameras SET updated_at = ? WHERE id = ?", (zaman.simdi_utc(), kamera_id)
    )


def _bolge_adi_dogrula(name: str) -> str:
    ad = name.strip()
    if not ad:
        raise DogrulamaHatasi("Bölge adı boş olamaz. Örnek: 'Ana yaya yolu'.")
    return ad


def _bolge_tipi_dogrula(zone_type: str) -> None:
    if zone_type not in BOLGE_TIPLERI:
        raise DogrulamaHatasi(f"Geçersiz bölge tipi: {zone_type}")


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

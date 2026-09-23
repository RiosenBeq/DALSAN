"""Video yükleyip kamerasız deneme: "Kameralar → Video Yükle".

NE İŞE YARAR - sistemi bir fabrika kamerasına bağlamadan, elinizdeki bir
video dosyasıyla baştan sona denemek. Video yüklenir, üzerine bölgeler
çizilir, kurallar kurulur; kural motoru, takip ve olay kaydı CANLI KAMERADAKİ
YOLUN AYNISINI yürütür. Denenen şey gerçekten sistemin kendisidir, taklidi
değil.

NEDEN AYRI BİR SAYFA - kamera formu bugün de "Video dosyası" kabul ediyordu,
ama dosyanın TAM YOLUNUN elle yazılmasını istiyordu ("Mac'te Option+Command+C,
Windows'ta Shift + sağ tık…"). Yazılım bilmeyen bir kullanıcı için bu, işin
başladığı yerde biten bir adımdır. Burada dosya normal bir "Gözat" kutusuyla
seçilir, sunucuya yüklenir ve gerisi kendiliğinden kurulur.

YENİ TABLO YOKTUR (CLAUDE.md §3). Yüklenen video, `source_type='file'` olan
SIRADAN BİR KAMERA satırıdır; bu sayfa yalnızca `veri/videolar` klasöründen
beslenen kameraları listeler. Böylece bölge çizimi, kural kurma, önizleme,
sayım, olay kaydı ve rapor - hepsi hiç değişmeden çalışır.

TEK GEÇİŞ / DÖNGÜ (şema 006) - kullanıcının iki farklı niyeti vardır ve
formdaki tek kutu bunları ayırır:

  * "Video bitince dursun" (varsayılan): videonun TEK geçişi analiz edilir.
    "Bu videoda kaç ihlal var" sorusunun cevabı budur.
  * İşaret kaldırılırsa video başa sarıp döner: eşik ve bölge ayarı denerken
    görüntünün hiç kesilmemesi istenir.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import zaman
from app.analiz.kamera import DURUM_BITTI
from app.hatalar import DogrulamaHatasi
from app.loglama import log_al
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()
_log = log_al("video")


class VideoBulunamadi(DogrulamaHatasi):
    http_kodu = 404


# Yükleme diske PARÇA PARÇA yazılır. Bir saatlik kamera kaydı gigabaytı bulur;
# `await dosya.read()` ile tamamını belleğe almak, tam da en çok işe yarayacağı
# dosyada sistemi düşürürdü.
_PARCA = 1024 * 1024

# Kamera sayfasındaki durum rozetinin bu sayfadaki karşılığı.
DURUM_ROZETLERI = {
    "online": ("analiz ediliyor", "yesil"),
    "connecting": ("başlatılıyor", "sari"),
    DURUM_BITTI: ("analiz tamamlandı", "mavi"),
    "offline": ("durdu", "gri"),
}


def _sayfaya_don(hata: str = "", mesaj: str = "") -> RedirectResponse:
    if hata:
        return RedirectResponse(f"/videolar?hata={quote(hata)}", status_code=303)
    if mesaj:
        return RedirectResponse(f"/videolar?mesaj={quote(mesaj)}", status_code=303)
    return RedirectResponse("/videolar", status_code=303)


# Türkçeye özgü harflerin ASCII karşılığı. NFKD bunların ÜÇÜNÜ (ı, ş, ğ)
# düşürüp siler - 'Şırınga' dosyası klasörde 'Srnga' diye görünürdü ve
# kullanıcı kendi dosyasını tanıyamazdı.
_TURKCE_HARFLER = str.maketrans(
    {
        "ı": "i",
        "İ": "I",
        "ş": "s",
        "Ş": "S",
        "ğ": "g",
        "Ğ": "G",
        "ç": "c",
        "Ç": "C",
        "ö": "o",
        "Ö": "O",
        "ü": "u",
        "Ü": "U",
    }
)


def dosya_adini_sadelestir(ham: str) -> str:
    """Yüklenen dosyanın adından GÜVENLİ bir dosya adı gövdesi üretir.

    Kullanıcının seçtiği ad diske olduğu gibi yazılamaz. İki ayrı sebep:

    1. GÜVENLİK - ad istemciden gelir. '../../.env' ya da 'C:\\Windows\\x'
       gibi bir ad, dosyayı video klasörünün DIŞINA yazdırabilirdi. Bu
       yüzden addan yalnızca son parçanın harf/rakamları alınır; bölü, ters
       bölü, iki nokta ve nokta dizileri hiç geçemez.
    2. TAŞINABİLİRLİK - Türkçe harf ve boşluk içeren adlar Windows ile Mac
       arasında kopyalanırken bozulabiliyor. Ad ASCII'ye indirgenir.

    Ad tamamen eleniyorsa boş döner; çağıran taraf yerine 'video' koyar. Adın
    kendisi zaten kimlik DEĞİLDİR: benzersizliği ekteki uuid sağlar.
    """
    gövde = Path(ham.replace("\\", "/")).name
    gövde = Path(gövde).stem
    gövde = gövde.translate(_TURKCE_HARFLER)
    gövde = unicodedata.normalize("NFKD", gövde).encode("ascii", "ignore").decode("ascii")
    gövde = re.sub(r"[^A-Za-z0-9._-]+", "-", gövde).strip("-._")
    return gövde[:60]


@router.get("/videolar", response_class=HTMLResponse)
def video_sayfasi(istek: Request, mesaj: str = "", hata: str = "", baglanti=Depends(baglanti_al)):
    ayarlar = istek.app.state.ayarlar
    return sablonlar.TemplateResponse(
        istek,
        "videolar.html",
        {
            "aktif_sekme": "kameralar",
            "videolar": _videolari_listele(baglanti, ayarlar.video_klasoru),
            "izinli_uzantilar": ", ".join(
                u.lstrip(".").upper() for u in ayarlar.video_izinli_uzantilar
            ),
            "kabul_listesi": ",".join(ayarlar.video_izinli_uzantilar),
            "en_buyuk_mb": ayarlar.video_en_buyuk_mb,
            "varsayilan_fps": ayarlar.kare_ornekleme_fps,
            "mesaj": mesaj,
            "hata": hata,
        },
    )


def _videolari_listele(baglanti, video_klasoru: Path) -> list[dict]:
    """Bu sayfaya ait kameralar: kaynağı video klasörünün İÇİNDE olanlar.

    Kullanıcının kendi elle girdiği bir dosya yolu (kamera formundaki eski
    yol) burada GÖRÜNMEZ ve dolayısıyla buradan SİLİNEMEZ: bu sayfanın silme
    düğmesi dosyayı da siliyor, başkasının masaüstündeki bir dosyayı silmeye
    hakkımız yok.
    """
    klasor = video_klasoru.resolve()
    videolar = []
    for satir in baglanti.execute(
        "SELECT * FROM cameras WHERE source_type = 'file' ORDER BY id DESC"
    ):
        kamera = dict(satir)
        dosya = Path(kamera["source_url"])
        if not _klasorun_icinde(dosya, klasor):
            continue
        kamera["dosya_adi"] = dosya.name
        kamera["boyut"] = _boyut_metni(dosya)
        kamera["dosya_var"] = dosya.is_file()
        kamera["tek_gecis"] = not kamera.get("loop_video", 1)
        kamera["rozet"], kamera["rozet_rengi"] = (
            DURUM_ROZETLERI.get(kamera["status"], DURUM_ROZETLERI["offline"])
            if kamera["enabled"]
            else ("duraklatıldı", "gri")
        )
        kamera["olay_sayisi"] = baglanti.execute(
            "SELECT COUNT(*) AS n FROM events WHERE camera_id = ? AND event_type = 'violation'",
            (kamera["id"],),
        ).fetchone()["n"]
        kamera["bolge_sayisi"] = baglanti.execute(
            "SELECT COUNT(*) AS n FROM zones WHERE camera_id = ?", (kamera["id"],)
        ).fetchone()["n"]
        videolar.append(kamera)
    return videolar


def _klasorun_icinde(dosya: Path, klasor: Path) -> bool:
    """`dosya` gerçekten `klasor`ün altında mı? (metin karşılaştırması DEĞİL)

    'veri/videolar-eski/x.mp4' adı 'veri/videolar' ile BAŞLAR; düz metin
    karşılaştırması bu dosyayı yanlışlıkla bu sayfaya ait sayar ve silme
    düğmesi başka bir klasördeki dosyayı silerdi.
    """
    try:
        dosya.resolve().relative_to(klasor)
    except (ValueError, OSError):
        return False
    return True


def _boyut_metni(dosya: Path) -> str:
    try:
        mb = dosya.stat().st_size / (1024 * 1024)
    except OSError:
        return "-"
    return f"{mb:.0f} MB" if mb >= 1 else "1 MB'tan küçük"


@router.post("/videolar/yukle")
async def video_yukle(
    istek: Request,
    video: UploadFile | None = None,
    name: str = Form(""),
    sample_fps: float | None = Form(None),
    tek_gecis: str = Form("0"),
    baglanti=Depends(baglanti_al),
):
    """Videoyu diske yazar ve onu izleyecek kamerayı kurar."""
    ayarlar = istek.app.state.ayarlar
    if sample_fps is None:  # alan gönderilmediyse .env'deki varsayılan (KARE_ORNEKLEME_FPS)
        sample_fps = float(ayarlar.kare_ornekleme_fps)
    if video is None or not video.filename:
        return _sayfaya_don(hata="Dosya seçilmedi. 'Gözat' düğmesiyle bir video dosyası seçin.")
    if not 0.5 <= sample_fps <= 30:
        return _sayfaya_don(hata="Örnekleme hızı 0,5 ile 30 fps arasında olmalı.")

    uzanti = Path(video.filename).suffix.lower()
    if uzanti not in ayarlar.video_izinli_uzantilar:
        okunur = ", ".join(u.lstrip(".").upper() for u in ayarlar.video_izinli_uzantilar)
        return _sayfaya_don(
            hata=f"'{video.filename}' desteklenmiyor. Şu türde bir video yükleyin: {okunur}"
        )

    govde = dosya_adini_sadelestir(video.filename) or "video"
    hedef = ayarlar.video_klasoru / f"{govde}-{uuid.uuid4().hex[:8]}{uzanti}"
    try:
        await _diske_yaz(video, hedef, ayarlar.video_en_buyuk_mb)
    except DogrulamaHatasi as hata:
        _log.warning(hata.kullanici_mesaji, extra={"ayrinti": hata.teknik_ayrinti})
        return _sayfaya_don(hata=hata.kullanici_mesaji)

    ad = name.strip() or Path(video.filename).stem.strip() or hedef.stem
    simdi = zaman.simdi_utc()
    imlec = baglanti.execute(
        "INSERT INTO cameras (name, area, source_type, source_url, sample_fps, "
        "loop_video, created_at, updated_at) VALUES (?, ?, 'file', ?, ?, ?, ?, ?)",
        (
            ad[:120],
            "Test videosu",
            str(hedef),
            sample_fps,
            0 if tek_gecis == "1" else 1,
            simdi,
            simdi,
        ),
    )
    baglanti.commit()
    _log.info(f"Test videosu yüklendi: {ad}", extra={"ayrinti": f"dosya: {hedef}"})
    # Doğrudan kamera sayfasına gidilir: sıradaki iş bölgeleri ÇİZMEKtir ve
    # kullanıcı o sayfayı kendi bulmak zorunda kalmamalı (CLAUDE.md §8).
    return RedirectResponse(f"/kameralar/{imlec.lastrowid}", status_code=303)


async def _diske_yaz(video: UploadFile, hedef: Path, en_buyuk_mb: int) -> None:
    """Yüklemeyi parça parça diske yazar; sınır aşılırsa YARIM DOSYA BIRAKMAZ.

    Yarım kalan bir dosya, açılabilen ama bir yerinde biten bir videodur:
    analiz onu sorunsuz oynatır ve kullanıcı eksik sonucu doğru sanar.
    """
    sinir = en_buyuk_mb * 1024 * 1024
    yazilan = 0
    try:
        hedef.parent.mkdir(parents=True, exist_ok=True)
        with open(hedef, "wb") as dosya:
            while parca := await video.read(_PARCA):
                yazilan += len(parca)
                if yazilan > sinir:
                    raise DogrulamaHatasi(
                        f"Video çok büyük (en fazla {en_buyuk_mb} MB). Daha kısa bir "
                        "bölüm yükleyin ya da Ayarlar sayfasından sınırı yükseltin.",
                        f"yükleme sınırı aşıldı: {hedef.name}",
                    )
                dosya.write(parca)
    except OSError as hata:
        hedef.unlink(missing_ok=True)
        raise DogrulamaHatasi(
            f"Video kaydedilemedi: {hata.strerror or 'disk hatası'}. Diskte yer "
            "olduğundan emin olun.",
            f"video yazılamadı: {hedef} - {hata!r}",
        ) from hata
    except DogrulamaHatasi:
        hedef.unlink(missing_ok=True)
        raise
    if yazilan == 0:
        hedef.unlink(missing_ok=True)
        raise DogrulamaHatasi("Seçilen dosya boş. Başka bir video deneyin.")


@router.post("/videolar/{kamera_id}/yeniden")
def videoyu_yeniden_calistir(kamera_id: int, baglanti=Depends(baglanti_al)):
    """Biten (ya da duraklatılan) videoyu baştan oynatır.

    Damganın tazelenmesi ŞARTTIR: analiz süpervizörü biten bir videonun
    kaynağını yalnızca kameranın `updated_at` damgası değiştiğinde yeniden
    kurar (analiz/supervizor.py). Damga yazılmazsa düğme hiçbir şey yapmaz.
    """
    _kamerayi_getir(baglanti, kamera_id)
    baglanti.execute(
        "UPDATE cameras SET enabled = 1, status = 'connecting', measured_fps = NULL, "
        "updated_at = ? WHERE id = ?",
        (zaman.simdi_utc(), kamera_id),
    )
    baglanti.commit()
    return _sayfaya_don(
        mesaj="Video baştan çalıştırılıyor. Birkaç saniye içinde analiz başlar; "
        "bu sayfayı yenileyerek durumu görebilirsiniz."
    )


@router.post("/videolar/{kamera_id}/duraklat")
def videoyu_duraklat(kamera_id: int, baglanti=Depends(baglanti_al)):
    """Analizi durdurur ama videoyu ve bulunan olayları SAKLAR."""
    _kamerayi_getir(baglanti, kamera_id)
    baglanti.execute(
        "UPDATE cameras SET enabled = 0, updated_at = ? WHERE id = ?",
        (zaman.simdi_utc(), kamera_id),
    )
    baglanti.commit()
    return _sayfaya_don(mesaj="Video duraklatıldı. Bulunan olaylar Olaylar sayfasında duruyor.")


@router.post("/videolar/{kamera_id}/sil")
def videoyu_sil(istek: Request, kamera_id: int, baglanti=Depends(baglanti_al)):
    """Kamerayı ve YÜKLENEN DOSYAYI siler.

    Olay geçmişi korunur (events.camera_id → SET NULL): kullanıcı videoyu
    silince o videoda bulunmuş ihlallerin de kaybolmasını beklemez.
    """
    kamera = _kamerayi_getir(baglanti, kamera_id)
    dosya = Path(kamera["source_url"])
    klasor = istek.app.state.ayarlar.video_klasoru.resolve()
    baglanti.execute("DELETE FROM cameras WHERE id = ?", (kamera_id,))
    baglanti.commit()
    # Dosya ancak GERÇEKTEN video klasörünün altındaysa silinir: kamera formuna
    # elle yazılmış bir yol, kullanıcının kendi dosyasıdır.
    if _klasorun_icinde(dosya, klasor):
        try:
            dosya.unlink(missing_ok=True)
        except OSError as hata:
            _log.warning(
                "Yüklenen video dosyası silinemedi; kamera kaydı kaldırıldı.",
                extra={"ayrinti": f"{dosya} - {hata!r}"},
            )
    return _sayfaya_don(mesaj="Video ve kamerası silindi. Bulunan olaylar duruyor.")


def _kamerayi_getir(baglanti, kamera_id: int) -> dict:
    satir = baglanti.execute(
        "SELECT * FROM cameras WHERE id = ? AND source_type = 'file'", (kamera_id,)
    ).fetchone()
    if satir is None:
        raise VideoBulunamadi("Video bulunamadı; silinmiş olabilir. Sayfayı yenileyin.")
    return dict(satir)

"""Alan tanıma rotaları: "Alanları Otomatik Bul" düğmesinin sunucu tarafı.

İKİ KAYNAK, TEK AKIŞ:
  · Kamera canlıysa → o anki kare kullanılır (dosya seçmeye gerek yok).
  · Kamera henüz bağlı değilse → kullanıcı bir EKRAN GÖRÜNTÜSÜ yükler
    (NVR'dan alınmış bir kare, telefonla çekilmiş bir fotoğraf).

İkinci yol, sistemin kurulumdan ÖNCE hazırlanabilmesini sağlar: kamera daha
takılmamışken bile bölgeler çizilip kurallar kurulabilir.

YÜKLENEN GÖRÜNTÜ DİSKE YAZILMAZ. Bellekte çözülür, alanlar bulunur, görüntü
tarayıcıya geri döner ve orada kalır. Nedeni iki tanedir:
  1. KVKK — fabrika karesinde çalışanlar vardır; saklamadığımız görüntü,
     saklama süresi, yedekleme ve silme sorusu doğurmaz (docs/00).
  2. En az parça (CLAUDE.md §3) — kalıcı olsaydı yeni bir tablo, yeni bir
     klasör ve bakım döngüsüne yeni bir istisna gerekirdi.

Kalıcı olan tek şey, kullanıcının KABUL ETTİĞİ bölgedir; o zaten `zones`
tablosuna normal yoldan yazılır.
"""

from __future__ import annotations

import base64

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.analiz import alan_bulucu
from app.loglama import log_al
from app.web.ortak import baglanti_al

router = APIRouter()
_log = log_al("alan")

# Yüklenen dosya bu boyutu aşarsa okunmaz (bellek dolmasın). Nesne
# fotoğraflarıyla aynı sınır kullanılır — kullanıcı iki ayrı sınır öğrenmesin.
_PARCA = 1024 * 1024

# Tarayıcıya geri dönen görüntünün kalitesi ve en büyük genişliği. Tuvalde
# arka plan olarak kullanılacak; 4K bir ekran görüntüsünü olduğu gibi geri
# yollamak sayfayı yavaşlatır.
_GERI_DONUS_GENISLIGI = 1280
_JPEG_KALITE = [int(cv2.IMWRITE_JPEG_QUALITY), 82]


@router.post("/kameralar/{kamera_id}/alan-bul")
async def alan_bul(
    istek: Request,
    kamera_id: int,
    gorsel: UploadFile | None = None,
    baglanti=Depends(baglanti_al),
):
    """Karedeki boyalı alanları bulup öneri listesi döner (JSON).

    Yanıt her zaman 200'dür ve `tamam` alanı taşır: tarayıcı tarafında tek bir
    yol vardır ve hata durumları da kullanıcıya Türkçe cümleyle gösterilir.
    """
    kamera = baglanti.execute("SELECT id FROM cameras WHERE id = ?", (kamera_id,)).fetchone()
    if kamera is None:
        return _yanit(False, "Kamera bulunamadı.")

    ayarlar = istek.app.state.ayarlar
    yuklendi = gorsel is not None and bool(gorsel.filename)

    if yuklendi:
        icerik = await _oku(gorsel, ayarlar.nesne_foto_en_buyuk_mb)
        if icerik is None:
            return _yanit(
                False,
                f"Dosya çok büyük (en fazla {ayarlar.nesne_foto_en_buyuk_mb} MB). "
                "Ekran görüntüsünü küçültüp yeniden deneyin.",
            )
        kare = _goruntuyu_coz(icerik)
        if kare is None:
            return _yanit(
                False,
                "Bu dosya bir görüntü olarak açılamadı. JPG veya PNG bir ekran görüntüsü seçin.",
            )
    else:
        kare = _canli_kare(istek, kamera_id)
        if kare is None:
            return _yanit(
                False,
                "Kameradan henüz görüntü gelmedi. Kamera bağlanana kadar "
                "beklemek yerine bir ekran görüntüsü yükleyip alanları şimdi "
                "çizebilirsiniz.",
            )

    # Morfoloji ve kontur bulma CPU işidir; olay döngüsünü bloklamasın.
    oneriler = await run_in_threadpool(alan_bulucu.alanlari_bul, kare)

    if not oneriler:
        # TEŞHİS: sistemin "boya" saydığı pikseller işaretlenmiş bir görsel
        # döner. Kullanıcı "neden bulamadı" sorusunun cevabını ekranda görür —
        # boya soluksa maske boş çıkar ve bu, eşik oynamaktan daha açık bir
        # yanıttır. Yalnızca bulunamadığında üretilir: bulunduğunda kimse
        # sormaz ve her istekte ikinci bir JPEG kodlamak boşa işlemcidir.
        return _yanit(
            False,
            "Zeminde boyalı bir alan bulunamadı. Bu, sistemin bozuk olduğu "
            "anlamına gelmez: her fabrika zemininde boya yoktur ya da boya "
            "solmuş olabilir. Alanı görüntü üzerine tıklayarak elle çizin. "
            "Aşağıdaki teşhis görüntüsü, sistemin boya saydığı yerleri "
            "işaretler — hiçbir yer işaretli değilse zemindeki boya tanınmıyor "
            "demektir.",
            gorsel_verisi=_veri_adresi(kare) if yuklendi else None,
            teshis_verisi=_veri_adresi(await run_in_threadpool(alan_bulucu.maske_onizlemesi, kare)),
        )

    _log.info(
        f"Alan önerisi üretildi (kamera {kamera_id}): {len(oneriler)} aday, "
        f"kaynak: {'yüklenen görüntü' if yuklendi else 'canlı kare'}"
    )
    return _yanit(
        True,
        _ozet_mesaji(len(oneriler)),
        oneriler=[
            {
                "poligon": [[round(x, 5), round(y, 5)] for x, y in o.poligon],
                "tip": o.tip,
                "tip_adi": o.tip_adi,
                "guven_yuzde": round(o.guven * 100),
                "alan_yuzdesi": o.alan_yuzdesi,
                "aciklama": o.aciklama,
            }
            for o in oneriler
        ],
        # Yüklenen görüntü tuvalin arka planı olur; canlı kare zaten
        # önizleme akışından geliyor, ikinci kez yollamaya gerek yok.
        gorsel_verisi=_veri_adresi(kare) if yuklendi else None,
    )


# ---------------------------------------------------------------------------
# iç
# ---------------------------------------------------------------------------


def _ozet_mesaji(adet: int) -> str:
    if adet == 1:
        return (
            "Zeminde boyalı 1 alan bulundu. Aşağıdaki karta tıklayınca çizim "
            "tuvale yüklenir; kaydetmeden önce köşeleri sürükleyip düzeltebilirsiniz."
        )
    return (
        f"Zeminde boyalı {adet} alan bulundu. Hangisini kullanacağınıza karar verip "
        "kartına tıklayın; çizim tuvale yüklenir ve köşelerini düzeltebilirsiniz."
    )


async def _oku(dosya: UploadFile, en_buyuk_mb: int) -> bytes | None:
    """Yüklenen dosyayı sınırlı okur; sınır aşılırsa None (bellek dolmasın)."""
    sinir = en_buyuk_mb * 1024 * 1024
    veri = bytearray()
    while parca := await dosya.read(_PARCA):
        veri.extend(parca)
        if len(veri) > sinir:
            return None
    return bytes(veri)


def _goruntuyu_coz(icerik: bytes) -> np.ndarray | None:
    """Bayt dizisini BGR kareye çevirir. Bozuk/desteklenmeyen dosyada None.

    `imdecode` bozuk dosyada istisna fırlatmaz, None döner; yine de sarmalanır
    çünkü çok büyük bir dosyada bellek hatası verebilir ve o hata, bu sayfayı
    çökertmek yerine kullanıcıya cümle olarak dönmelidir.
    """
    try:
        dizi = np.frombuffer(icerik, dtype=np.uint8)
        kare = cv2.imdecode(dizi, cv2.IMREAD_COLOR)
    except (cv2.error, ValueError, MemoryError) as hata:
        _log.error(f"Yüklenen görüntü çözülemedi: {hata!r}")
        return None
    if kare is None or kare.size == 0:
        return None
    return kare


def _canli_kare(istek: Request, kamera_id: int) -> np.ndarray | None:
    """Süpervizörün son önizleme JPEG'ini kareye çevirir.

    Bölgesiz sürüm istenir: üzerine çizilmiş mor bölge çizgileri, boya
    maskesine "beyaz/sarı olmayan ama belirgin" bir çizgi olarak girmez ama
    alan sınırlarını bozabilir. Sistemin ham gördüğüne bakılır.
    """
    supervizor = getattr(istek.app.state, "supervizor", None)
    if supervizor is None:
        return None
    jpeg = supervizor.onizleme_jpeg(kamera_id, bolgeler_dahil=False)
    if not jpeg:
        return None
    return _goruntuyu_coz(jpeg)


def _veri_adresi(kare: np.ndarray | None) -> str | None:
    """Kareyi tarayıcıda gösterilebilecek bir data: adresine çevirir."""
    if kare is None or kare.size == 0:
        return None
    yukseklik, genislik = kare.shape[:2]
    if genislik > _GERI_DONUS_GENISLIGI:
        olcek = _GERI_DONUS_GENISLIGI / float(genislik)
        kare = cv2.resize(
            kare,
            (_GERI_DONUS_GENISLIGI, max(int(yukseklik * olcek), 1)),
            interpolation=cv2.INTER_AREA,
        )
    tamam, jpeg = cv2.imencode(".jpg", kare, _JPEG_KALITE)
    if not tamam:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode("ascii")


def _yanit(
    tamam: bool,
    mesaj: str,
    oneriler: list | None = None,
    gorsel_verisi: str | None = None,
    teshis_verisi: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        {
            "tamam": tamam,
            "mesaj": mesaj,
            "oneriler": oneriler or [],
            "gorsel": gorsel_verisi,
            # Yalnızca alan bulunamadığında dolu olur (teşhis görüntüsü).
            "teshis": teshis_verisi,
        }
    )

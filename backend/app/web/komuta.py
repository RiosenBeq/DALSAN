"""Komuta kabuğu: altı ekranın ortak çerçevesi (sol raf + üst başlık).

Bu aşamada YALNIZCA kabuk vardır; ekran içerikleri sonraki aşamalarda gelir.
Kabuğun gösterdiği her sayı GERÇEK veritabanından okunur — tasarımdaki
"24 kamera / 6 bölüm" örnek değerleri buraya taşınmaz. Veri yoksa sayı
uydurulmaz, kullanıcıya ne yapması gerektiği söylenir.

Ana sayfa ("/") ve Kameralar/Kurallar/KKD sayfaları eski kabukta (temel.html)
kalır; iki kabuk birbirine bağlantıyla geçer.
"""

from __future__ import annotations

import json
import math

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.olaylar.anons import bolge_sec
from app.rules.motor import KALIBRASYON_GEREKTIREN
from app.web.kilavuz import EKRAN_ACIKLAMALARI, kurulum_durumu
from app.web.ortak import (
    ANONS_KISA_ADLARI,
    BOLGE_TIPLERI,
    KKD_ADLARI,
    KURAL_TIPLERI,
    OLAY_SORGUSU,
    SINIFLAR,
    baglanti_al,
    olay_hazirla,
    rtsp_maskele,
    sayi_metni,
)
from app.web.rotalar import sablonlar

router = APIRouter()

# Ekran adları tasarımdan BİREBİR alınmıştır (DALSAN Komuta.dc.html, basliklar).
EKRAN_BASLIKLARI = {
    "ana": "Komuta ekranı",
    "duvar": "Canlı duvar",
    "inceleme": "Olay inceleme",
    "saglik": "Kamera sağlığı",
    "uyari": "Uyarı ve anons",
    "anons": "Anons sistemi",
    # Tasarımda olmayan yedinci ekran: sistemi ilk kez açan kişi için
    # kurulumun ve günlük kullanımın tek sayfalık anlatımı.
    "kilavuz": "Kullanım kılavuzu",
    # Sekizinci ekran: kullanıcının kendi nesnesini fotoğrafla tanıtması.
    # CANLI ANALİZE GİRMEZ — yalnızca yüklenen fotoğrafta arar (nesne_rotalari.py).
    "nesneler": "Nesneler",
    # Dokuzuncu ekran: .env dosyasının ekrandaki karşılığı (ayar_rotalari.py).
    # Paketlenmiş programda ayar dosyası elle açılamaz; tek yol burasıdır.
    "ayarlar": "Sistem ayarları",
}

# Alt başlıklar da tasarımdan birebirdir — ANCAK içinde sayı geçenler
# (Komuta ve Anons) burada değil, aşağıdaki fonksiyonda gerçek veriyle
# üretilir: "6 bölüm · 24 kamera" ve "7 bölge" bu kurulumda YANLIŞ olurdu.
EKRAN_ALT_BASLIKLARI = {
    "duvar": "Tüm kameralar tek ekranda",
    "inceleme": "Kuyruktaki ihlalleri sırayla işaretleyin",
    "saglik": "Bağlantı, örnekleme ve kalibrasyon durumu",
    "uyari": "Kural, hoparlör ve bildirim zinciri",
    "kilavuz": "Sistemi kurma, çalıştırma ve uyarıları değerlendirme",
    "ayarlar": "Anons, tespit hassasiyeti ve saklama süreleri",
}


def _kamera_sayilari(baglanti) -> tuple[int, int, int]:
    """(toplam kamera, canlı kamera, bölüm sayısı) — hepsi veritabanından."""
    satir = baglanti.execute(
        "SELECT COUNT(*) AS toplam, "
        "SUM(CASE WHEN enabled = 1 AND status = 'online' THEN 1 ELSE 0 END) AS canli, "
        "COUNT(DISTINCT CASE WHEN area <> '' THEN area END) AS bolum "
        "FROM cameras"
    ).fetchone()
    # SUM boş tabloda NULL döner; 0'a çevrilmezse şablonda "None" yazardı.
    return satir["toplam"], satir["canli"] or 0, satir["bolum"] or 0


def _kamera_hapi(toplam: int, canli: int) -> dict:
    """Başlıktaki canlı kamera göstergesi.

    Kamera yokken yeşil bir rozet göstermek "her şey yolunda" yalanı olurdu;
    o durumda ne yapılacağını söyleyen nötr bir hap görünür.
    """
    if toplam == 0:
        return {"metin": "Henüz kamera eklenmedi", "renk": "", "nabiz": False}
    if canli == 0:
        return {"metin": f"Canlı kamera 0 / {toplam}", "renk": "sari", "nabiz": False}
    return {
        "metin": f"Canlı kamera {canli} / {toplam}",
        "renk": "yesil" if canli == toplam else "sari",
        "nabiz": True,
    }


def _alt_baslik(ekran: str, istek: Request, baglanti, toplam: int, bolum: int) -> str:
    if ekran == "ana":
        # Tasarımda "Vardiya 08:00 – 16:00 · 6 bölüm · 24 kamera" yazıyor.
        # Vardiya tanımı sistemde YOK, sayılar da bu kuruluma ait değil.
        tarih = zaman.ekranda_tarih(zaman.simdi_utc())
        if toplam == 0:
            return f"{tarih} · henüz kamera eklenmedi"
        return f"{tarih} · {bolum} bölüm · {toplam} kamera"
    if ekran == "anons":
        # Tasarımdaki "IP hoparlör · 7 bölge · Türkçe seslendirme" yerine
        # .env'deki gerçek anons yolu ve veritabanındaki gerçek mesaj sayısı.
        ayarlar = istek.app.state.ayarlar
        yol = ANONS_KISA_ADLARI.get(ayarlar.anons, ayarlar.anons)
        mesaj = baglanti.execute(
            "SELECT COUNT(*) AS n FROM announcement_messages WHERE enabled = 1"
        ).fetchone()["n"]
        return f"Anons yolu: {yol} · {mesaj} hazır mesaj"
    if ekran == "nesneler":
        # Gerçek sayılar: kaç nesne tanıtıldı, toplam kaç referans fotoğraf var.
        sayi = baglanti.execute(
            "SELECT (SELECT COUNT(*) FROM library_objects) AS nesne, "
            "(SELECT COUNT(*) FROM library_object_photos) AS foto"
        ).fetchone()
        if sayi["nesne"] == 0:
            return "Yüklenen fotoğrafta aranır · henüz nesne tanıtılmadı"
        return f"Yüklenen fotoğrafta aranır · {sayi['nesne']} nesne · {sayi['foto']} fotoğraf"
    return EKRAN_ALT_BASLIKLARI[ekran]


def kabuk_baglami(istek: Request, baglanti, ekran: str) -> dict:
    """Altı ekranın da paylaştığı kabuk verisi."""
    toplam, canli, bolum = _kamera_sayilari(baglanti)
    return {
        "ekran": ekran,
        "ekran_basligi": EKRAN_BASLIKLARI[ekran],
        "ekran_alt_basligi": _alt_baslik(ekran, istek, baglanti, toplam, bolum),
        "kamera_hapi": _kamera_hapi(toplam, canli),
        "sunucu_saati": zaman.ekranda_goster_kisa(zaman.simdi_utc()),
        # Ekranın üstündeki kapatılabilir açıklama şeridi. Kılavuz sayfasının
        # kendisinde şerit yoktur: sayfanın tamamı zaten açıklamadır.
        "ekran_aciklamasi": EKRAN_ACIKLAMALARI.get(ekran),
    }


@router.get("/komuta", response_class=HTMLResponse)
def komuta_panosu(istek: Request, baglanti=Depends(baglanti_al)):
    baglam = kabuk_baglami(istek, baglanti, "ana")
    baglam.update(pano_baglami(baglanti))
    # İlk kurulum kontrol listesi: sistem hazır DEĞİLSE panonun en üstünde
    # sıradaki adımı gösterir, hazırsa küçük bir rozete iner.
    baglam["kurulum"] = kurulum_durumu(
        baglanti, getattr(istek.app.state, "supervizor", None), istek.app.state.ayarlar
    )
    return sablonlar.TemplateResponse(istek, "komuta_ana.html", baglam)


@router.get("/komuta/kilavuz", response_class=HTMLResponse)
def kullanim_kilavuzu(istek: Request, baglanti=Depends(baglanti_al)):
    """Tek sayfalık kullanım kılavuzu.

    Metin ekran görüntüsü GEREKTİRMEZ: her adım, ekranda görünen düğme adıyla
    tarif edilir. Böylece arayüz küçük değiştiğinde kılavuz yanlış olmaz.
    """
    baglam = kabuk_baglami(istek, baglanti, "kilavuz")
    baglam["kurulum"] = kurulum_durumu(
        baglanti, getattr(istek.app.state, "supervizor", None), istek.app.state.ayarlar
    )
    return sablonlar.TemplateResponse(istek, "komuta_kilavuz.html", baglam)


@router.get("/komuta/duvar", response_class=HTMLResponse)
def canli_duvar(istek: Request, baglanti=Depends(baglanti_al)):
    baglam = kabuk_baglami(istek, baglanti, "duvar")
    baglam.update(duvar_baglami(baglanti))
    return sablonlar.TemplateResponse(istek, "komuta_duvar.html", baglam)


@router.get("/komuta/inceleme", response_class=HTMLResponse)
def olay_inceleme(istek: Request, olay: int | None = None, baglanti=Depends(baglanti_al)):
    """`?olay=` verilmezse kuyruğun başındaki (en yeni bekleyen) olay açılır."""
    baglam = kabuk_baglami(istek, baglanti, "inceleme")
    baglam.update(inceleme_baglami(baglanti, olay))
    return sablonlar.TemplateResponse(istek, "komuta_inceleme.html", baglam)


@router.get("/komuta/saglik", response_class=HTMLResponse)
def kamera_sagligi(istek: Request, baglanti=Depends(baglanti_al)):
    baglam = kabuk_baglami(istek, baglanti, "saglik")
    baglam.update(saglik_baglami(baglanti, istek.app.state.ayarlar))
    return sablonlar.TemplateResponse(istek, "komuta_saglik.html", baglam)


@router.get("/komuta/uyari", response_class=HTMLResponse)
def uyari_zinciri(istek: Request, baglanti=Depends(baglanti_al)):
    baglam = kabuk_baglami(istek, baglanti, "uyari")
    baglam.update(uyari_baglami(baglanti, istek.app.state.ayarlar))
    return sablonlar.TemplateResponse(istek, "komuta_uyari.html", baglam)


@router.post("/komuta/uyari/golge")
def golge_modu_degistir(
    golge: str = Form(...),
    kural_idler: list[int] = Form(...),
    baglanti=Depends(baglanti_al),
):
    """Zincirdeki bir satırı gölge moda alır ya da anonsu açar.

    Satır birden çok kuralı temsil edebilir (aynı tip + aynı eşik + aynı anons,
    farklı kameralar); hepsi birlikte değişir — ekranda tek satır görünüp
    kameraların yarısı gölge modda kalsaydı rozet yalan söylerdi.

    Kural motoruna DOKUNULMAZ: yalnızca rules.shadow_mode yazılır, kararı yine
    kural motoru verir. updated_at da yazılır ki süpervizör değişikliği
    5 saniye içinde yeniden başlatmadan alsın.
    """
    if golge not in ("0", "1"):
        raise DogrulamaHatasi(f"Geçersiz gölge mod değeri: {golge}")
    if not kural_idler:
        raise DogrulamaHatasi("Değiştirilecek kural seçilmedi.")
    baglanti.executemany(
        "UPDATE rules SET shadow_mode = ?, updated_at = ? WHERE id = ?",
        [(int(golge), zaman.simdi_utc(), kural_id) for kural_id in kural_idler],
    )
    baglanti.commit()
    return RedirectResponse("/komuta/uyari", status_code=303)


@router.get("/komuta/anons", response_class=HTMLResponse)
def anons_sistemi(istek: Request, sonuc: str = "", baglanti=Depends(baglanti_al)):
    baglam = kabuk_baglami(istek, baglanti, "anons")
    baglam.update(anons_baglami(istek, baglanti))
    baglam["sonuc_mesaji"] = ANONS_SONUCLARI.get(sonuc, "")
    return sablonlar.TemplateResponse(istek, "komuta_anons.html", baglam)


# =====================================================================
# KOMUTA PANOSU (/komuta)
# =====================================================================
#
# Buradaki her sayı veritabanından okunur. Tasarımdaki "34 ihlal", "%94 KKD
# uyumu", "24 kamera" ÖRNEKTİR ve hiçbiri koda taşınmamıştır. Veri yoksa sıfır
# yazmak yerine ne yapılacağını söyleyen bir boş durum gösterilir.

# Alan çubuklarının ve saat sütunlarının penceresi.
# Tasarımın "son 7 gün" notu korundu: tek günlük pencerede yeni kurulmuş bir
# sistemde neredeyse hep boş bir grafik görünürdü.
ALAN_PENCERESI_GUN = 7

# Renk eşiği SAYIYA değil, o listedeki EN YÜKSEK değere ORANLA verilir:
# 4 ihlalli küçük bir kurulumda da 400 ihlalli büyük bir kurulumda da "en yoğun
# alan" kırmızı görünsün. Sabit bir "20 ihlal = kırmızı" eşiği kurulumdan
# kuruluma yanlış olurdu.
YOGUN_ORANI = 0.66
ORTA_ORANI = 0.33

# Canlı akışta ve öne çıkan kameralarda gösterilecek satır/kutu sayısı.
AKIS_SATIRI = 6
ONE_CIKAN_KAMERA = 4

# Canlı kare tazeleme aralığı (milisaniye).
# Kamera sayfasındaki tek önizleme 1 sn'de bir yenilenir. Komuta panosunda 4,
# canlı duvarda ise TÜM kameralar aynı anda yenilenir; her istek sunucuda ayrı
# bir JPEG kodlaması demektir. 2 sn hareketi izlemeye yeter ama istek sayısını
# yarıya indirir — 24 kameralı bir kurulumda saniyede 24 yerine 12 kare.
KARE_TAZELEME_MS = 2000


# Olay satırının rengi.
# Tasarımdaki kırmızı/sarı/nötr üçlüsü korundu, ama anlamı ŞU ANKİ veriye
# bağlandı: kurallardaki `severity` alanı bu kurulumda her zaman 'warning' —
# ona göre renk verseydik bütün satırlar aynı renk olurdu.
#   kırmızı = incelenmemiş ihlal (ilgi bekliyor)
#   sarı    = incelenmiş ihlal
#   nötr    = yanlış alarm ya da sistem olayı (kamera koptu/geldi gibi)
def _olay_rengi(olay: dict) -> str:
    if olay["event_type"] != "violation":
        return "notr"
    return {"new": "kirmizi", "reviewed": "sari"}.get(olay["status"], "notr")


def _olay_yeri(olay: dict) -> str:
    """Olayın yeri: "Sevkiyat Rampası · Sevkiyat".

    Kamera silinmiş olabilir (olay kanıttır, kamerasıyla birlikte silinmez);
    o zaman boş bir satır yerine ne olduğu yazılır.
    """
    yer = olay["kamera_adi"] or "Kamerası silinmiş"
    if olay["kamera_alani"]:
        yer += f" · {olay['kamera_alani']}"
    return yer


def _yogunluk_sinifi(deger: int, en_yuksek: int) -> str:
    if en_yuksek <= 0:
        return ""
    oran = deger / en_yuksek
    if oran >= YOGUN_ORANI:
        return "yogun"
    if oran >= ORTA_ORANI:
        return "orta"
    return ""


def _yuzde(deger: int, en_yuksek: int) -> str:
    """Çubuk genişliği/yüksekliği — en yüksek değere oranla."""
    if en_yuksek <= 0:
        return "0%"
    return f"{round(deger / en_yuksek * 100)}%"


def _sayi_kartlari(baglanti) -> list[dict]:
    """Üst satırdaki dört özet kutusu."""
    bugun = zaman.gun_basi_utc(0)
    dun = zaman.gun_basi_utc(1)

    bugunku = baglanti.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'violation' AND occurred_at >= ?",
        (bugun,),
    ).fetchone()["n"]
    dunku = baglanti.execute(
        "SELECT COUNT(*) AS n FROM events "
        "WHERE event_type = 'violation' AND occurred_at >= ? AND occurred_at < ?",
        (dun, bugun),
    ).fetchone()["n"]
    bekleyen = baglanti.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'violation' AND status = 'new'"
    ).fetchone()["n"]
    toplam, canli, _ = _kamera_sayilari(baglanti)
    kural = baglanti.execute("SELECT COUNT(*) AS n FROM rules WHERE enabled = 1").fetchone()["n"]

    return [
        {
            "etiket": "Bugünkü ihlal",
            "deger": bugunku,
            "renk": "",
            "alt": _dune_gore(bugunku, dunku),
            "bag": "",
            "bag_yazi": "",
        },
        {
            "etiket": "İncelenmeyi bekleyen",
            "deger": bekleyen,
            "renk": "dikkat" if bekleyen else "",
            "alt": "" if bekleyen else "kuyruk boş",
            "bag": "/olaylar?durum=new" if bekleyen else "",
            "bag_yazi": "olayları aç →",
        },
        {
            "etiket": "Canlı kamera",
            "deger": canli,
            "renk": "" if canli == toplam else "dikkat",
            "alt": f"toplam {toplam} kamera",
            "bag": "/komuta/duvar",
            "bag_yazi": "canlı duvara geç →",
        },
        {
            "etiket": "Aktif kural",
            "deger": kural,
            "renk": "" if kural else "dikkat",
            "alt": "" if kural else "kural kurulmadan ihlal üretilmez",
            "bag": "/kurallar",
            "bag_yazi": "kuralları aç →",
        },
    ]


def _dune_gore(bugunku: int, dunku: int) -> str:
    """Karşılaştırma cümlesi. Dün hiç veri yoksa 'iyileşti' izlenimi verilmez."""
    if dunku == 0 and bugunku == 0:
        return "dün de ihlal yoktu"
    if dunku == 0:
        return "dün ihlal yoktu"
    fark = bugunku - dunku
    if fark == 0:
        return "dünkü ile aynı"
    return f"düne göre {'+' if fark > 0 else '−'}{abs(fark)}"


def _alan_yogunlugu(baglanti) -> list[dict]:
    """cameras.area ile gruplanmış ihlal sayıları — çubuk listesi."""
    sinir = zaman.gun_basi_utc(ALAN_PENCERESI_GUN - 1)
    satirlar = baglanti.execute(
        "SELECT c.area AS alan, COUNT(*) AS n "
        "FROM events e JOIN cameras c ON c.id = e.camera_id "
        "WHERE e.event_type = 'violation' AND e.occurred_at >= ? "
        "GROUP BY c.area ORDER BY n DESC, c.area",
        (sinir,),
    ).fetchall()
    if not satirlar:
        return []
    en_yuksek = satirlar[0]["n"]
    return [
        {
            # Alanı boş bırakılmış kameralar da bir grup oluşturur; "" yazmak
            # yerine ne olduğu söylenir (Kameralar sayfasından doldurulur).
            "ad": s["alan"] or "Bölüm girilmemiş",
            "deger": s["n"],
            "genislik": _yuzde(s["n"], en_yuksek),
            "sinif": _yogunluk_sinifi(s["n"], en_yuksek),
        }
        for s in satirlar
    ]


def _canli_akis(baglanti) -> list[dict]:
    """Son olaylar — ihlaller ve sistem olayları birlikte (tasarımdaki gibi)."""
    satirlar = baglanti.execute(
        f"{OLAY_SORGUSU} ORDER BY e.occurred_at DESC, e.id DESC LIMIT ?", (AKIS_SATIRI,)
    ).fetchall()
    akis = []
    for satir in satirlar:
        olay = olay_hazirla(satir)
        akis.append(
            {
                "id": olay["id"],
                "baslik": olay["ozet"],
                "yer": _olay_yeri(olay),
                "saat": zaman.ekranda_saat(olay["occurred_at"]),
                "renk": _olay_rengi(olay),
                "durum_kucuk": olay["durum_kucuk"],
            }
        )
    return akis


def _saat_sutunlari(zamanlar, birim: str) -> dict:
    """UTC damga listesini 00-23 arası 24 sütuna böler (histogram).

    Kovalama SQL'de değil Python'da yapılır: veritabanındaki damgalar UTC'dir,
    SQLite'ın saat dilimi bilgisi yoktur ve sütunlar 3 saat kayardı.

    Hem ihlal hem anons dağılımı bu fonksiyonu kullanır: iki ayrı kovalama
    kodu olsaydı aynı olay iki grafikte farklı saate düşebilirdi.
    """
    kovalar = [0] * 24
    for damga in zamanlar:
        kovalar[zaman.yerel_saat(damga)] += 1

    toplam = sum(kovalar)
    en_yuksek = max(kovalar) if toplam else 0
    sutunlar = [
        {
            "etiket": f"{saat:02d}",
            "deger": adet,
            "yukseklik": _yuzde(adet, en_yuksek),
            "sinif": _yogunluk_sinifi(adet, en_yuksek),
        }
        for saat, adet in enumerate(kovalar)
    ]
    tepe = ""
    if toplam:
        saat = kovalar.index(en_yuksek)
        tepe = f"En yoğun {saat:02d}:00 – {(saat + 1) % 24:02d}:00 · {en_yuksek} {birim}"
    return {"sutunlar": sutunlar, "toplam": toplam, "tepe": tepe}


def _saatlik_dagilim(baglanti) -> dict:
    """Bugünün ihlallerinin saate göre dağılımı."""
    satirlar = baglanti.execute(
        "SELECT occurred_at FROM events "
        "WHERE event_type = 'violation' AND occurred_at >= ? ORDER BY occurred_at",
        (zaman.gun_basi_utc(0),),
    ).fetchall()
    return _saat_sutunlari([s["occurred_at"] for s in satirlar], "ihlal")


def _one_cikan_kameralar(baglanti) -> list[dict]:
    """En çok ihlal üreten kameralar — canlı kare + rozet."""
    sinir = zaman.gun_basi_utc(ALAN_PENCERESI_GUN - 1)
    satirlar = baglanti.execute(
        "SELECT c.id, c.name, c.area, c.enabled, c.status, COUNT(*) AS n "
        "FROM events e JOIN cameras c ON c.id = e.camera_id "
        "WHERE e.event_type = 'violation' AND e.occurred_at >= ? "
        "GROUP BY c.id ORDER BY n DESC, c.name LIMIT ?",
        (sinir, ONE_CIKAN_KAMERA),
    ).fetchall()
    return [
        {
            "id": s["id"],
            "ad": s["name"],
            "alan": s["area"],
            "ihlal": s["n"],
            "rozet": _kamera_durumu(s)[0],
        }
        for s in satirlar
    ]


def pano_baglami(baglanti) -> dict:
    toplam, _, _ = _kamera_sayilari(baglanti)
    saatler = _saatlik_dagilim(baglanti)
    return {
        "kamera_var": toplam > 0,
        "sayi_kartlari": _sayi_kartlari(baglanti),
        "alanlar": _alan_yogunlugu(baglanti),
        "alan_penceresi": ALAN_PENCERESI_GUN,
        "akis": _canli_akis(baglanti),
        "saat_sutunlari": saatler["sutunlar"],
        "saat_toplami": saatler["toplam"],
        "saat_tepesi": saatler["tepe"],
        "one_cikan": _one_cikan_kameralar(baglanti),
        "tazeleme_ms": KARE_TAZELEME_MS,
    }


# =====================================================================
# CANLI DUVAR (/komuta/duvar)
# =====================================================================

# Izgaranın en fazla sütun sayısı. Daha dar kutuda kamera adı okunmaz olur.
DUVAR_EN_COK_SUTUN = 6

# Kamera kutusunun durum metni ve noktası (tasarımdaki "canlı kare" /
# "yeniden bağlanıyor" ikilisi, gerçek dört duruma açıldı).
KAMERA_DURUMLARI = {
    "online": ("canlı kare", "yesil"),
    "connecting": ("yeniden bağlanıyor", "sari"),
    "offline": ("bağlantı yok", "kirmizi"),
}


def _kamera_durumu(satir) -> tuple[str, str]:
    if not satir["enabled"]:
        return ("pasif", "")
    return KAMERA_DURUMLARI.get(satir["status"], KAMERA_DURUMLARI["offline"])


def duvar_sutun_sayisi(kamera_sayisi: int) -> int:
    """Izgara sütun sayısı — kamera SAYISINA uyar.

    Tasarım 24 kamerayı 6 sütuna diziyor. Gerçek kurulumda 3-4 kamera var;
    6 sütun bırakılsaydı kutular pul boyutuna iner, ekranın üçte ikisi boş
    kalırdı. Kareye yakın bir ızgara (√n) 4 kamerayı 2x2 büyük kutuya,
    24 kamerayı da 5 sütuna yerleştirir. Boş kutu ASLA eklenmez.
    """
    if kamera_sayisi <= 0:
        return 1
    return min(DUVAR_EN_COK_SUTUN, math.ceil(math.sqrt(kamera_sayisi)))


def duvar_baglami(baglanti) -> dict:
    """Tüm kameralar + açık ihlal sayıları.

    KIRMIZI ÇERÇEVE = o kamerada henüz incelenmemiş ('new') ihlal var.
    Tasarımdaki "şu an ihlal var" durumu için uydurma bir zaman penceresi
    (son 5 dk gibi) kurmak yerine kullanıcının kendi kapatabildiği bir işaret
    seçildi: olay incelendi olarak işaretlenince çerçeve söner.
    """
    satirlar = baglanti.execute(
        "SELECT c.*, ("
        "  SELECT COUNT(*) FROM events e "
        "  WHERE e.camera_id = c.id AND e.event_type = 'violation' AND e.status = 'new'"
        ") AS acik_ihlal "
        "FROM cameras c ORDER BY c.area, c.name"
    ).fetchall()

    kameralar = []
    for satir in satirlar:
        durum, nokta = _kamera_durumu(satir)
        kameralar.append(
            {
                "id": satir["id"],
                "ad": satir["name"],
                "alan": satir["area"],
                "durum": durum,
                "nokta": nokta,
                "acik_ihlal": satir["acik_ihlal"],
                # Pasif kameradan kare gelmez; boş bir kutuyu boşuna sormayalım.
                "canli": bool(satir["enabled"]),
            }
        )
    bolumler = len({k["alan"] for k in kameralar if k["alan"]})
    return {
        "kameralar": kameralar,
        "duvar_sutun": duvar_sutun_sayisi(len(kameralar)),
        "duvar_bolum": bolumler,
        "tazeleme_ms": KARE_TAZELEME_MS,
        "tazeleme_sn": round(KARE_TAZELEME_MS / 1000),
    }


# =====================================================================
# OLAY İNCELEME (/komuta/inceleme)
# =====================================================================
#
# Amaç tek cümle: kuyruktaki ihlalleri sırayla işaretlemek. Ekran YENİ bir
# yazma yolu açmaz — işaretleme, olay detay sayfasının da kullandığı
# /olaylar/{id}/durum ucuna POST eder (web/olaylar_web.py). İki ayrı yazma
# yolu olsaydı iki ekran zamanla farklı davranır ve "yanlış alarm" sayıları
# güvenilmez olurdu.

# Kuyrukta gösterilen en çok satır. Bekleyen olaylar HER ZAMAN üstte sıralanır
# (aşağıdaki ORDER BY), böylece işaretlenmemiş bir olay bu sınırın altında
# kalıp gözden kaçamaz.
KUYRUK_SATIRI = 40

# Seçili olayın başlığındaki durum rozeti (renk sınıfları stil.css'te).
INCELEME_ROZETLERI = {
    "new": ("İhlal · Yeni", "kirmizi"),
    "reviewed": ("İhlal · İncelendi", "yesil"),
    "false_alarm": ("İhlal · Yanlış alarm", "gri"),
}

# KKD kararı üç durumludur: "belirsiz" ihlal SAYILMAZ (CLAUDE.md §7).
KKD_KARARLARI = {"yes": "var", "no": "yok", "unknown": "belirsiz"}


def _kkd_karari(ppe: dict) -> str:
    """'baret yok · yelek var' — kuralın istediği her parça için tek tek."""
    parcalar = []
    for anahtar in ppe.get("required", []):
        karar = ppe.get(anahtar)
        if not isinstance(karar, dict):
            continue
        durum = KKD_KARARLARI.get(karar.get("decision", ""), "belirsiz")
        parcalar.append(f"{KKD_ADLARI.get(anahtar, anahtar)} {durum}")
    return " · ".join(parcalar)


def _olcum_sayisi(detay: dict, params: dict) -> str:
    """'5 ölçüm' — hız kararı kaç ölçümün ortancasına dayandı."""
    sayi = detay.get("olcum_sayisi") or params.get("window_size")
    return "" if sayi is None else f"{sayi} ölçüm"


def _gozlem_penceresi(params: dict) -> str:
    """'8 / 15 gözlem' — KKD kararı kaç gözleme bakılarak verildi."""
    pencere = params.get("window_size")
    en_az = params.get("min_valid_observations")
    if pencere is None or en_az is None:
        return ""
    return f"{en_az} / {pencere} gözlem"


def _inceleme_kutulari(olay: dict) -> list[dict]:
    """Seçili olayın ölçülen değerleri + olay anındaki kural eşiği.

    Tasarımda dört SABİT kutu vardı (Mesafe / Araç hızı / Kare sayısı / KKD);
    bunlar yalnızca güvenli mesafe olayında anlamlıdır. Burada kutular olayın
    KURAL TİPİNE göre üretilir ve kaynak veri yoksa kutu hiç çizilmez.

    Eşik değerleri kuralın BUGÜNKÜ halinden değil, olay anındaki anlık
    görüntüsünden (events.rule_snapshot) okunur: kural sonradan değiştiyse
    ekranda geçmişi yanlış açıklayan bir sayı görünmesin.
    """
    detay = olay["detaylar"]
    params = olay["kural_kaydi"].get("params")
    if not isinstance(params, dict):
        params = {}
    tip = olay["kural_kaydi"].get("rule_type", "")
    kutular: list[tuple[str, str]] = []

    if tip == "safe_distance":
        kutular = [
            ("Ölçülen mesafe", sayi_metni(detay.get("mesafe_m"), "m", 2)),
            ("Kural eşiği", sayi_metni(params.get("distance_m"), "m")),
            ("Araç", SINIFLAR.get(detay.get("arac_sinifi", ""), "")),
            ("Araç hızı", sayi_metni(detay.get("arac_hiz_mps"), "m/s", 2)),
        ]
    elif tip == "zone_intrusion":
        yonler = {"inside": "bölgenin içinde", "outside": "bölgenin dışında"}
        kutular = [
            ("Kalış süresi", sayi_metni(detay.get("kalis_s"), "sn")),
            ("Kural eşiği", sayi_metni(params.get("min_dwell_s"), "sn")),
            ("Görülen", SINIFLAR.get(detay.get("sinif", ""), "")),
            ("Kural yönü", yonler.get(detay.get("mode") or params.get("mode", ""), "")),
        ]
    elif tip == "vehicle_speed":
        kutular = [
            ("Ölçülen hız", sayi_metni(detay.get("hiz_kmh"), "km/sa", 1)),
            ("Hız sınırı", sayi_metni(detay.get("limit_kmh"), "km/sa", 1)),
            ("Araç", SINIFLAR.get(detay.get("arac_sinifi", ""), "")),
            ("Kaç ölçümün ortancası", _olcum_sayisi(detay, params)),
        ]
    elif tip == "ppe_violation":
        ppe = detay.get("ppe") or {}
        eksikler = detay.get("eksik_kkd") or []
        kutular = [
            ("Eksik KKD", ", ".join(KKD_ADLARI.get(k, k) for k in eksikler)),
            ("KKD kararı", _kkd_karari(ppe)),
            ("Kalış süresi", sayi_metni(ppe.get("dwell_s"), "sn")),
            ("Gözlem penceresi", _gozlem_penceresi(params)),
        ]
    return [{"etiket": etiket, "deger": deger} for etiket, deger in kutular if deger]


def inceleme_baglami(baglanti, secili_id: int | None) -> dict:
    """Kuyruk + seçili olayın kanıtı ve kural özeti."""
    satirlar = baglanti.execute(
        # Bekleyenler ÖNCE: kuyruk penceresi dolsa bile işaretlenmemiş hiçbir
        # olay listeden düşmez. (e.status <> 'new') SQLite'ta 0/1 üretir.
        f"{OLAY_SORGUSU} WHERE e.event_type = 'violation' "
        "ORDER BY (e.status <> 'new'), e.occurred_at DESC, e.id DESC LIMIT ?",
        (KUYRUK_SATIRI,),
    ).fetchall()

    kuyruk = []
    for satir in satirlar:
        olay = olay_hazirla(satir)
        kuyruk.append(
            {
                "id": olay["id"],
                "baslik": olay["ozet"],
                "yer": _olay_yeri(olay),
                "saat": zaman.ekranda_saat(olay["occurred_at"]),
                "durum_kucuk": olay["durum_kucuk"],
                "renk": _olay_rengi(olay),
            }
        )

    bekleyen = baglanti.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'violation' AND status = 'new'"
    ).fetchone()["n"]

    # Seçili olay ayrıca sorgulanır: işaretlendikten sonra kuyruğun dibine
    # düşüp pencerenin dışında kalabilir; kullanıcı yine de baktığı olayda
    # kalmalı, başka bir olaya fırlatılmamalıdır.
    secili = None
    if secili_id is not None:
        satir = baglanti.execute(
            f"{OLAY_SORGUSU} WHERE e.id = ? AND e.event_type = 'violation'", (secili_id,)
        ).fetchone()
        if satir is not None:
            secili = olay_hazirla(satir)
    if secili is None and satirlar:
        secili = olay_hazirla(satirlar[0])

    sirali = [k["id"] for k in kuyruk]
    onceki = sonraki = None
    if secili is not None and secili["id"] in sirali:
        yer = sirali.index(secili["id"])
        onceki = sirali[yer - 1] if yer > 0 else None
        sonraki = sirali[yer + 1] if yer + 1 < len(sirali) else None
    elif sirali:
        sonraki = sirali[0]

    if secili is not None:
        secili["rozet"], secili["rozet_rengi"] = INCELEME_ROZETLERI.get(
            secili["status"], ("İhlal", "gri")
        )
        secili["kutular"] = _inceleme_kutulari(secili)
        secili["yer"] = _olay_yeri(secili)
        secili["zaman_kisa"] = zaman.ekranda_goster_kisa(secili["occurred_at"])

    return {
        "kuyruk": kuyruk,
        # Kuyruk penceresi dolduysa şablon "hepsi bu değil" notunu gösterir;
        # sınır sayısı iki yere yazılmasın diye karar burada verilir.
        "kuyruk_dolu": len(kuyruk) >= KUYRUK_SATIRI,
        "bekleyen": bekleyen,
        "olay": secili,
        "onceki_id": onceki,
        "sonraki_id": sonraki,
    }


# =====================================================================
# KAMERA SAĞLIĞI (/komuta/saglik)
# =====================================================================

# Satır rozetleri. Tasarımda dört rozet vardı (bağlı / kalibrasyon bekliyor /
# yeniden bağlanıyor / pasif); "bağlantı yok" beşinci olarak eklendi: gerçek
# sistemde kamera durumu üç değer alabiliyor (online / connecting / offline)
# ve kopuk kamerayı "yeniden bağlanıyor" diye göstermek yanlış olurdu.
SAGLIK_ROZETLERI = {
    "connecting": ("yeniden bağlanıyor", "sari"),
    "offline": ("bağlantı yok", "kirmizi"),
}


def _saglik_rozeti(satir) -> tuple[str, str]:
    """Öncelik sırası: kapalı > bağlantı > kalibrasyon.

    Kapalı bir kameranın kalibrasyonunu istemek anlamsızdır; bağlantısı kopuk
    bir kameraya "kalibrasyon bekliyor" demek de kullanıcıyı yanlış işe yollar.
    """
    if not satir["enabled"]:
        return ("pasif", "gri")
    if satir["status"] != "online":
        return SAGLIK_ROZETLERI.get(satir["status"], SAGLIK_ROZETLERI["offline"])
    if satir["calibrated_at"] is None:
        return ("kalibrasyon bekliyor", "sari")
    return ("bağlı", "yesil")


def _fps_metni(deger) -> str:
    """Ölçülen hız: '5,8'. Ölçüm yoksa '—' (kamera kapalı ya da kopuk)."""
    if deger is None:
        return "—"
    return f"{float(deger):.1f}".replace(".", ",")


def _fps_dusuk_mu(satir, oran: float) -> bool:
    """Ölçülen hız, ayarlanan hızın .env'deki oranının altında mı?

    Eşik koda gömülmez: 6 fps'e ayarlı kamerada 3 fps yarı hız demektir,
    2 fps'e ayarlı kamerada aynı sayı normaldir (ayarlar.fps_uyari_orani).
    """
    olculen, ayarlanan = satir["measured_fps"], satir["sample_fps"]
    if olculen is None or not ayarlanan:
        return False
    return float(olculen) < float(ayarlanan) * oran


def saglik_baglami(baglanti, ayarlar) -> dict:
    """Üç özet kutusu + kamera başına bir satır."""
    satirlar = baglanti.execute(
        "SELECT c.*, k.calibrated_at FROM cameras c "
        "LEFT JOIN camera_calibrations k ON k.camera_id = c.id "
        # Bölümler alfabetik; bölümü girilmemiş kameralar listenin SONUNA
        # düşer, yoksa boş bir başlık listenin en üstünde dururdu.
        "ORDER BY (c.area = ''), c.area, c.name"
    ).fetchall()

    kameralar = []
    bagli = sorunlu = pasif = yavas = kalibrasyonsuz = 0
    for satir in satirlar:
        if not satir["enabled"]:
            pasif += 1
        elif satir["status"] == "online":
            bagli += 1
        else:
            sorunlu += 1

        rozet, rozet_rengi = _saglik_rozeti(satir)
        fps_dusuk = _fps_dusuk_mu(satir, ayarlar.fps_uyari_orani)
        yavas += 1 if fps_dusuk else 0
        kalibrasyonsuz += 0 if satir["calibrated_at"] else 1

        kameralar.append(
            {
                "id": satir["id"],
                "ad": satir["name"],
                "alan": satir["area"] or "Bölüm girilmemiş",
                "fps": _fps_metni(satir["measured_fps"]),
                "ayarlanan_fps": _fps_metni(satir["sample_fps"]),
                "fps_dusuk": fps_dusuk,
                # last_frame_at kamera koptuğunda da KORUNUR: "en son ne zaman
                # görüntü geldi" bilgisi asıl o zaman lazım olur.
                "son_kare": (
                    zaman.ne_kadar_once(satir["last_frame_at"]) if satir["last_frame_at"] else "—"
                ),
                "kalibrasyon": (
                    zaman.ekranda_tarih(satir["calibrated_at"]) if satir["calibrated_at"] else ""
                ),
                "rozet": rozet,
                "rozet_rengi": rozet_rengi,
            }
        )

    return {
        "saglik_kameralari": kameralar,
        "saglik_sayilari": [
            {
                "etiket": "Bağlı",
                "deger": bagli,
                "renk": "",
                "alt": "görüntü akıyor",
            },
            {
                "etiket": "Sorunlu",
                "deger": sorunlu,
                "renk": "dikkat" if sorunlu else "",
                "alt": "bağlantı koptu ya da yeniden kuruluyor",
            },
            {
                "etiket": "Pasif",
                "deger": pasif,
                "renk": "",
                "alt": "kapalı kameradan görüntü alınmaz",
            },
        ],
        "yavas_kamera": yavas,
        "kalibrasyonsuz_kamera": kalibrasyonsuz,
        # Ekranda "%60" yazabilmek için: eşiğin kendisi .env'den gelir.
        "fps_uyari_yuzdesi": round(ayarlar.fps_uyari_orani * 100),
    }


# =====================================================================
# UYARI ZİNCİRİ (/komuta/uyari)
# =====================================================================
#
# Tek soruya cevap verir: "bir kural çiğnenince ne oluyor?"
# Zincir: kural → anons metni → hangi hoparlör → bildirim.
#
# Tasarımdaki dördüncü satır ("Ani hareket · forklift hızı") ve telefon
# bildirimi ekranı BU SİSTEMDE YOK. Uydurulmadı: dördüncü kural tipi
# docs/07 yol haritasına yazıldı, bildirim kanalları da ekranda dürüstçe
# "kurulmadı" diye gösteriliyor.

# Bildirim (e-posta/SMS/push) altyapısı yok — docs/07 Phase 2 #4.
BILDIRIM_METNI = "kurulmadı"


def _kural_esigi(tip: str, params: dict) -> str:
    """Kuralın insan diliyle eşiği: '3 m', '5 sn kalış', 'baret, yelek'.

    Eşik SABİT DEĞİL: her kuralın kendi params JSON'ından okunur. Tasarımdaki
    "3 m" / "2,5 m/s" örnek değerlerdir ve koda taşınmamıştır.
    """
    if tip == "safe_distance":
        return sayi_metni(params.get("distance_m"), "m")
    if tip == "zone_intrusion":
        yon = {"inside": "bölge içinde", "outside": "bölge dışında"}.get(params.get("mode", ""), "")
        sure = sayi_metni(params.get("min_dwell_s"), "sn kalış")
        return " · ".join(parca for parca in (yon, sure) if parca)
    if tip == "ppe_violation":
        return ", ".join(KKD_ADLARI.get(k, k) for k in params.get("required_ppe", []))
    if tip == "vehicle_speed":
        limit = params.get("speed_limit_mps")
        return "" if limit is None else sayi_metni(limit * 3.6, "km/sa", 1)
    return ""


def _zincir_rozeti(satir) -> tuple[str, str]:
    """Satırın durumu. Öncelik: kapalı > gölge mod > aktif.

    Kapalı bir kuralın gölge modda olması anlamsızdır; gölge moddaki kural da
    "aktif" diye gösterilemez — kullanıcı hoparlörün çaldığını sanır.
    """
    if not satir["enabled"]:
        return ("kapalı", "gri")
    if satir["shadow_mode"]:
        return ("gölge mod", "sari")
    return ("aktif", "yesil")


def _anons_yolu_metni(ayarlar, bolge: dict | None) -> str:
    """Anonsun bu kural için NEREDEN çalacağı.

    .env'deki ANONS ayarı ile hoparlör bölgesi birlikte okunur: ANONS=null iken
    hoparlör bölgesi tanımlı olsa bile ses ÇIKMAZ, bunu söylemek zorundayız.
    """
    if ayarlar.anons == "null":
        return "anons sistemi kapalı"
    if ayarlar.anons == "ses_karti":
        return "bu bilgisayarın ses kartı"
    if bolge is not None:
        return f"IP hoparlör · {bolge['name']}"
    return "IP hoparlör · .env'deki tek adres"


def _ses_metni(ayarlar, ses_dosyasi: str | None) -> str:
    """Ses dosyası bilgisi YALNIZCA ses kartı yolunda anlamlıdır.

    IP hoparlöre metin gönderilir (JSON), WAV dosyası kullanılmaz; orada ses
    dosyası yazmak kullanıcıyı boş yere dosya aramaya gönderirdi.
    """
    if ayarlar.anons != "ses_karti":
        return ""
    return ses_dosyasi or "ses dosyası bağlanmamış"


def _zincir(baglanti, ayarlar, hoparlorler: list[dict]) -> list[dict]:
    """rules + announcement_messages + zones + cameras → zincir satırları.

    Satırlar GRUPLANIR: aynı tip, aynı eşik, aynı anons ve aynı durumdaki
    kurallar tek satırda "N kamera" olarak görünür (tasarımdaki "12 kamera ·
    3 m"). Gruplamasaydık 24 kameralı kurulumda 24 satır çıkardı ve zincir
    okunmaz olurdu. Kamera sayısı azken adlar da yazılır — 3-4 kameralı bir
    kurulumda "2 kamera" tek başına hangi kameralar olduğunu söylemez.
    """
    satirlar = baglanti.execute(
        "SELECT r.id, r.rule_type, r.params, r.enabled, r.shadow_mode, r.cooldown_s, "
        "       c.name AS kamera_adi, c.area AS kamera_alani, "
        "       z.zone_type, a.id AS anons_id, a.text AS anons_metni, "
        "       a.audio_file, a.enabled AS anons_aktif, "
        "       (SELECT 1 FROM camera_calibrations k WHERE k.camera_id = c.id) AS kalibre "
        "FROM rules r "
        "JOIN cameras c ON c.id = r.camera_id "
        "LEFT JOIN zones z ON z.id = r.zone_id "
        "LEFT JOIN announcement_messages a ON a.id = r.announcement_id "
        "ORDER BY r.rule_type, r.id"
    ).fetchall()

    gruplar: dict[tuple, dict] = {}
    for satir in satirlar:
        try:
            params = json.loads(satir["params"])
        except (json.JSONDecodeError, TypeError):
            params = {}
        esik = _kural_esigi(satir["rule_type"], params)
        rozet, rozet_rengi = _zincir_rozeti(satir)
        anahtar = (
            satir["rule_type"],
            satir["zone_type"] or "",
            esik,
            satir["anons_id"],
            rozet,
        )
        grup = gruplar.get(anahtar)
        if grup is None:
            bolge_tipi = BOLGE_TIPLERI.get(satir["zone_type"] or "", "")
            baslik = KURAL_TIPLERI.get(satir["rule_type"], satir["rule_type"])
            if bolge_tipi:
                baslik += f" · {bolge_tipi}"
            grup = gruplar[anahtar] = {
                "kural": baslik,
                "esik": esik,
                "kamera_adlari": [],
                "alanlar": [],
                "kural_idler": [],
                "kalibrasyonsuz": 0,
                "anons": satir["anons_metni"] or "anons yok",
                "anons_kapali": bool(satir["anons_id"]) and not satir["anons_aktif"],
                "ses": _ses_metni(ayarlar, satir["audio_file"]),
                "bildirim": BILDIRIM_METNI,
                "rozet": rozet,
                "rozet_rengi": rozet_rengi,
                "golge": bool(satir["shadow_mode"]),
                "kapali": not satir["enabled"],
            }
        grup["kural_idler"].append(satir["id"])
        grup["kamera_adlari"].append(satir["kamera_adi"])
        if satir["kamera_alani"] and satir["kamera_alani"] not in grup["alanlar"]:
            grup["alanlar"].append(satir["kamera_alani"])
        # Kalibre edilmemiş kamerada güvenli mesafe ve araç hızı kuralları
        # BİLEREK pasiftir (docs/03 §2 ve §4): ikisi de metre ölçüsüne dayanır.
        # "Aktif" rozetiyle birlikte bunu söylemezsek ekran çalışmayan bir
        # zinciri çalışıyor gösterir.
        if satir["rule_type"] in KALIBRASYON_GEREKTIREN and not satir["kalibre"]:
            grup["kalibrasyonsuz"] += 1

    zincir = []
    for grup in gruplar.values():
        adet = len(grup["kural_idler"])
        parcalar = [f"{adet} kamera"]
        if grup["esik"]:
            parcalar.append(grup["esik"])
        if adet <= 3:
            parcalar.append(", ".join(grup["kamera_adlari"]))
        grup["kapsam"] = " · ".join(parcalar)

        # Anonsun hangi hoparlörden çalacağı kameranın BÖLÜMÜNE bağlıdır ve
        # seçim kuralı anons katmanıyla AYNIDIR (olaylar/anons.py → bolge_sec):
        # ekranda bir hoparlör yazıp başkasından ses çıkmasın.
        adlar: list[str] = []
        for alan in grup["alanlar"] or [""]:
            bolge = bolge_sec(hoparlorler, alan)
            ad = bolge["name"] if bolge else ""
            if ad not in adlar:
                adlar.append(ad)
        if ayarlar.anons != "http" or len(adlar) <= 1:
            secili = {"name": adlar[0]} if adlar and adlar[0] else None
            grup["yol"] = _anons_yolu_metni(ayarlar, secili)
        else:
            # Grup birden çok bölüme yayılmış: her bölüm kendi hoparlöründen
            # duyurulur, hepsi tek satırda yazılır.
            grup["yol"] = "IP hoparlör · " + ", ".join(ad or ".env'deki tek adres" for ad in adlar)
        zincir.append(grup)
    return zincir


def uyari_baglami(baglanti, ayarlar) -> dict:
    hoparlorler = [
        dict(satir) for satir in baglanti.execute("SELECT * FROM speaker_zones ORDER BY id")
    ]
    zincir = _zincir(baglanti, ayarlar, hoparlorler)
    return {
        "zincir": zincir,
        "golge_sayisi": sum(1 for z in zincir if z["golge"]),
        "anonssuz_sayisi": sum(1 for z in zincir if z["anons"] == "anons yok"),
        "anons_yolu": ANONS_KISA_ADLARI.get(ayarlar.anons, ayarlar.anons),
        "anons_kapali": ayarlar.anons == "null",
        "anons_bekleme_sn": ayarlar.anons_bekleme_sn,
    }


# =====================================================================
# ANONS SİSTEMİ (/komuta/anons)
# =====================================================================

# POST sonrası dönen kısa sonuç anahtarları. Ham metin URL'den GEÇMEZ:
# adres çubuğundan gelen bir cümle ekrana basılmasın.
ANONS_SONUCLARI = {
    "kaydedildi": "Hoparlör bölgesi kaydedildi.",
    "silindi": "Hoparlör bölgesi silindi. O bölümün anonsu artık .env dosyasındaki adrese gider.",
    "denendi": "Deneme yayını gönderildi. Hoparlörden ses gelmediyse adresi kontrol edin.",
}


def _anons_tetikleyen_olaylar(baglanti) -> tuple[dict[int, int], list[str]]:
    """Bugün hangi anons mesajını kaç ihlal tetikledi + damgaları.

    Sayım, olayın KURAL ANLIK GÖRÜNTÜSÜNDEN (events.rule_snapshot) okunur:
    kuralın anonsu sonradan değiştirilmişse geçmiş olaylar eski mesaja yazılı
    kalır. Gölge moddaki kuralın olayı SAYILMAZ — o kural hoparlörü hiç
    çalıştırmamıştır.

    DİKKAT — bu sayı "hoparlör kaç kez bağırdı" DEĞİLDİR: aynı kamera ve mesaj
    için ANONS_BEKLEME_SN dolmadan tekrar çalınmaz, yani gerçek anons sayısı
    bundan azdır. Ekranda da öyle yazar; hoparlör kayıt defteri tutulmuyor.
    """
    satirlar = baglanti.execute(
        "SELECT occurred_at, rule_snapshot FROM events "
        "WHERE event_type = 'violation' AND occurred_at >= ? ORDER BY occurred_at",
        (zaman.gun_basi_utc(0),),
    ).fetchall()

    sayilar: dict[int, int] = {}
    damgalar: list[str] = []
    for satir in satirlar:
        try:
            kural = json.loads(satir["rule_snapshot"]) if satir["rule_snapshot"] else {}
        except json.JSONDecodeError:
            continue
        if kural.get("shadow_mode"):
            continue
        anons_id = kural.get("announcement_id")
        if not anons_id:
            continue
        sayilar[anons_id] = sayilar.get(anons_id, 0) + 1
        damgalar.append(satir["occurred_at"])
    return sayilar, damgalar


def _anons_mesajlari(baglanti, ayarlar, sayilar: dict[int, int]) -> list[dict]:
    """announcement_messages + bu mesaja bağlı kurallar ve bölümler."""
    satirlar = baglanti.execute(
        "SELECT a.*, "
        "  (SELECT COUNT(*) FROM rules r WHERE r.announcement_id = a.id) AS kural_sayisi "
        "FROM announcement_messages a ORDER BY a.id"
    ).fetchall()

    mesajlar = []
    for satir in satirlar:
        kural_satirlari = baglanti.execute(
            "SELECT r.rule_type, r.enabled, r.shadow_mode, c.area FROM rules r "
            "JOIN cameras c ON c.id = r.camera_id WHERE r.announcement_id = ?",
            (satir["id"],),
        ).fetchall()
        tipler = sorted(
            {KURAL_TIPLERI.get(k["rule_type"], k["rule_type"]) for k in kural_satirlari}
        )
        alanlar = sorted({k["area"] for k in kural_satirlari if k["area"]})
        calisanlar = [k for k in kural_satirlari if k["enabled"]]

        # Rozet, mesajın GERÇEKTEN çalıp çalmayacağını söyler. Yalnızca
        # announcement_messages.enabled'a bakmak yetmez: mesaj açık olsa bile
        # bağlı kuralların hepsi kapalıysa ya da gölge moddaysa hoparlör susar.
        if not satir["enabled"]:
            rozet, rozet_rengi = "kapalı", "gri"
        elif not satir["kural_sayisi"]:
            rozet, rozet_rengi = "kurala bağlı değil", "gri"
        elif not calisanlar:
            rozet, rozet_rengi = "kuralları kapalı", "gri"
        elif all(k["shadow_mode"] for k in calisanlar):
            rozet, rozet_rengi = "gölge modda", "sari"
        elif ayarlar.anons == "ses_karti" and not satir["audio_file"]:
            rozet, rozet_rengi = "ses dosyası yok", "sari"
        else:
            rozet, rozet_rengi = "açık", "yesil"

        mesajlar.append(
            {
                "id": satir["id"],
                "metin": satir["text"],
                "kural": (
                    f"{', '.join(tipler)} · {satir['kural_sayisi']} kural"
                    if tipler
                    else "hiçbir kurala bağlı değil"
                ),
                "bolum": ", ".join(alanlar),
                "ses": _ses_metni(ayarlar, satir["audio_file"]),
                "bugun": sayilar.get(satir["id"], 0),
                "rozet": rozet,
                "rozet_rengi": rozet_rengi,
            }
        )
    return mesajlar


def _hoparlor_satirlari(baglanti, ayarlar) -> list[dict]:
    """speaker_zones satırları — adres MASKELİ, son anons insan diliyle."""
    satirlar = baglanti.execute(
        "SELECT * FROM speaker_zones ORDER BY (area = ''), area, name"
    ).fetchall()
    hoparlorler = []
    for satir in satirlar:
        if not satir["enabled"]:
            rozet, rozet_rengi = "kapalı", "gri"
        elif ayarlar.anons != "http":
            # Bölge tanımlı ama .env'de IP hoparlör seçili değil: adres
            # kullanılmıyor. "Açık" demek yanlış olurdu.
            rozet, rozet_rengi = "beklemede", "sari"
        else:
            rozet, rozet_rengi = "açık", "yesil"
        hoparlorler.append(
            {
                "id": satir["id"],
                "ad": satir["name"],
                "alan": satir["area"],
                "alan_adi": satir["area"] or "Tüm fabrika",
                # Adreste kullanıcı adı/şifre varsa maskelenir (kamera RTSP
                # adresiyle aynı desen); cihazın kendisi görünür kalır.
                "adres": rtsp_maskele(satir["address"]),
                "adres_ham": satir["address"],
                "aciklama": satir["description"],
                "aktif": bool(satir["enabled"]),
                "son_anons": (
                    zaman.ne_kadar_once(satir["last_announced_at"])
                    if satir["last_announced_at"]
                    else "—"
                ),
                "rozet": rozet,
                "rozet_rengi": rozet_rengi,
            }
        )
    return hoparlorler


def _anons_kartlari(ayarlar, hoparlorler: list[dict], bugun: int) -> list[dict]:
    """Üstteki dört özet kutusu — hepsi .env ve veritabanından."""
    acik = sum(1 for h in hoparlorler if h["aktif"])
    if not hoparlorler:
        hoparlor_deger, hoparlor_alt = "Tanımlanmadı", "anons .env'deki tek adrese gider"
    else:
        hoparlor_deger = f"{acik} / {len(hoparlorler)} açık"
        hoparlor_alt = "anons yalnızca ihlalin olduğu bölümde çalar"

    yol_alt = {
        "null": ".env dosyasında ANONS=null — hoparlörden ses çıkmaz",
        "ses_karti": "hoparlör/amfi doğrudan bu bilgisayara bağlı",
    }.get(ayarlar.anons, rtsp_maskele(ayarlar.anons_http_adresi))

    return [
        {
            "etiket": "Anons yolu",
            "deger": ANONS_KISA_ADLARI.get(ayarlar.anons, ayarlar.anons),
            "yazi": True,
            "renk": "dikkat" if ayarlar.anons == "null" else "",
            "alt": yol_alt,
        },
        {
            "etiket": "Hoparlör bölgesi",
            "deger": hoparlor_deger,
            "yazi": True,
            "renk": "",
            "alt": hoparlor_alt,
        },
        {
            "etiket": "Bugün anons tetikleyen ihlal",
            "deger": bugun,
            "yazi": False,
            "renk": "",
            # Dürüstlük: bu sayı hoparlörün kaç kez bağırdığı DEĞİL, üst sınırı.
            "alt": f"hoparlör aynı uyarıyı {ayarlar.anons_bekleme_sn} sn'de bir tekrarlar",
        },
        {
            "etiket": "Tekrar aralığı",
            "deger": f"{ayarlar.anons_bekleme_sn} sn",
            "yazi": True,
            "renk": "",
            "alt": "hoparlör üst üste bağırmaz (.env → ANONS_BEKLEME_SN)",
        },
    ]


def anons_baglami(istek: Request, baglanti) -> dict:
    ayarlar = istek.app.state.ayarlar
    sayilar, damgalar = _anons_tetikleyen_olaylar(baglanti)
    hoparlorler = _hoparlor_satirlari(baglanti, ayarlar)
    saatler = _saat_sutunlari(damgalar, "anons")
    supervizor = getattr(istek.app.state, "supervizor", None)
    return {
        "anons_kartlari": _anons_kartlari(ayarlar, hoparlorler, len(damgalar)),
        "anons_mesajlari": _anons_mesajlari(baglanti, ayarlar, sayilar),
        "hoparlorler": hoparlorler,
        # Bölüm listesi kameralardan gelir: kullanıcı hoparlörün bölümünü
        # elle yazıp yanlış eşleştirmesin (ADR-007 — alan düz metindir).
        "bolumler": [
            satir["area"]
            for satir in baglanti.execute(
                "SELECT DISTINCT area FROM cameras WHERE area != '' ORDER BY area"
            )
        ],
        "anons_saatleri": saatler["sutunlar"],
        "anons_saat_toplami": saatler["toplam"],
        "anons_saat_tepesi": saatler["tepe"],
        "anons_yolu": ANONS_KISA_ADLARI.get(ayarlar.anons, ayarlar.anons),
        "anons_kapali": ayarlar.anons == "null",
        "anons_http": ayarlar.anons == "http",
        "anons_bekleme_sn": ayarlar.anons_bekleme_sn,
        "analiz_calisiyor": supervizor is not None,
        "son_sonuc": getattr(supervizor, "_anons", None) and supervizor._anons.son_sonuc,
    }

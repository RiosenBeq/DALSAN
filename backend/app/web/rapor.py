"""İSG raporu: seçilen dönemin özeti + kırılımlar (docs/07 #3).

YENİ KÜTÜPHANE YOK (CLAUDE.md §3). PDF için ayrı bir üretim motoru kurmak
yerine sayfa YAZDIRMAYA hazır tasarlandı: tarayıcının "Yazdır → PDF olarak
kaydet" adımı Windows'ta da Mac'te de çalışır, kurulum istemez ve kullanıcıya
öğrenmesi gereken yeni bir parça çıkarmaz. Excel çıktısı da aynı sebeple
CSV'dir - noktalı virgül + BOM, Türkçe Excel'in beklediği biçim.

KOVALAMA NEDEN PYTHON'DA: veritabanındaki damgalar UTC'dir ve SQLite'ın saat
dilimi bilgisi yoktur. GROUP BY ile gün/saat kırılımı yapılsaydı sütunlar
Türkiye saatine göre 3 saat kayardı ve gece vardiyası yanlış güne düşerdi
(docs/08 R7).

KURAL TİPİ NEREDEN OKUNUR: olayın `rule_snapshot` alanından, kuralın BUGÜNKÜ
halinden değil. Kural silinmiş ya da tipi değişmiş olsa bile geçmiş rapor
aynı sayıyı vermeye devam eder - rapor bir kanıt belgesidir, her açılışta
farklı sayı gösteremez.
"""

from __future__ import annotations

import io
import json
import math
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.rules.olay_kodu import OLAY_KODLARI
from app.web.erisim_izi import erisim_yaz
from app.web.komuta import kabuk_baglami
from app.web.ortak import (
    KURAL_TIPLERI,
    CsvYazici,
    baglanti_al,
    cubuk_yuzdesi,
    saat_sutunlari,
    sayi_metni,
)
from app.web.rotalar import sablonlar

router = APIRouter()

# Varsayılan dönem. Bir ay, vardiya ve hafta düzenini görmeye yeter; daha
# uzun varsayılan, ilk açılışta sayfayı yavaşlatır ve kimse okumaz.
VARSAYILAN_GUN = 30

# Emniyet sınırı: bundan çok olay varsa rapor en YENİ bu kadarını sayar ve
# ekranda bunu YAZAR. Sessizce kesilen bir rapor yanlış rapordur.
EN_COK_OLAY = 200_000

# Gün çubuğu bu sayıdan fazlaysa etiketler okunmaz olur; yalnız her N'inci
# günün etiketi yazılır (çubuklar yine hepsi çizilir).
GUN_ETIKET_SINIRI = 14

# docs/17 §4.8 hedefi: kamera başına saatte en çok 2 yanlış alarm. Rapor
# yalnız gösterir; sayı ölçülemiyorsa hedef "tuttu" denmez.
HEDEF_YANLIS_ALARM_SAAT = 2.0

_SILINMIS_KAMERA = "Kamerası silinmiş"
_BOLGESIZ = "Bölgesiz (tüm kare)"
_BOLUMSUZ = "Bölüm girilmemiş"


# =====================================================================
# VERİ
# =====================================================================


def _donem(sorgu) -> tuple[str, str]:
    """(başlangıç, bitiş) - Türkiye tarihleri, 'YYYY-AA-GG'."""
    bitis = (sorgu.get("bitis") or "").strip() or zaman.yerel_tarih_iso()
    baslangic = (sorgu.get("baslangic") or "").strip()
    if not baslangic:
        baslangic = zaman.yerel_tarih_iso(zaman.gun_basi_utc(VARSAYILAN_GUN - 1))
    for tarih in (baslangic, bitis):
        try:
            zaman.yerel_gun_baslangici_utc(tarih)
        except ValueError as hata:
            raise DogrulamaHatasi(f"Tarih okunamadı: {hata}") from hata
    if baslangic > bitis:
        raise DogrulamaHatasi(
            "Başlangıç tarihi bitiş tarihinden sonra olamaz. "
            f"Girilen: {zaman.ekranda_tarih(zaman.yerel_gun_baslangici_utc(baslangic))} → "
            f"{zaman.ekranda_tarih(zaman.yerel_gun_baslangici_utc(bitis))}"
        )
    return baslangic, bitis


def _olaylari_getir(baglanti, baslangic: str, bitis: str, alan: str) -> list[dict]:
    """Dönemdeki İHLAL olayları - rapora giren tek olay tipi.

    Sistem olayları (kamera koptu, disk azaldı) bilerek dışarıdadır: bunlar
    işletme değil bakım göstergesidir ve İSG performansı sayısını şişirirdi.
    """
    kosullar = ["e.event_type = 'violation'", "e.occurred_at >= ?", "e.occurred_at < ?"]
    degerler: list = [
        zaman.yerel_gun_baslangici_utc(baslangic),
        zaman.yerel_gun_sonu_utc(bitis),
    ]
    if alan:
        kosullar.append("c.area = ?")
        degerler.append(alan)
    satirlar = baglanti.execute(
        "SELECT e.occurred_at, e.status, e.rule_snapshot, e.camera_id, e.event_code, "
        "       c.name AS kamera_adi, c.area AS kamera_alani "
        "FROM events e LEFT JOIN cameras c ON c.id = e.camera_id "
        f"WHERE {' AND '.join(kosullar)} "
        "ORDER BY e.occurred_at DESC LIMIT ?",
        [*degerler, EN_COK_OLAY],
    ).fetchall()
    return [dict(s) for s in satirlar]


def _kural_bilgisi(olay: dict, bolge_adlari: dict[int, str]) -> tuple[str, str]:
    """(kural tipi adı, bölge adı) - olay anındaki kural görüntüsünden."""
    try:
        kural = json.loads(olay["rule_snapshot"]) if olay["rule_snapshot"] else {}
    except json.JSONDecodeError:
        kural = {}
    tip = KURAL_TIPLERI.get(kural.get("rule_type", ""), "") or "Kuralı silinmiş"
    bolge_id = kural.get("zone_id")
    if bolge_id is None:
        bolge = _BOLGESIZ
    else:
        bolge = bolge_adlari.get(bolge_id, "Bölgesi silinmiş")
    olay["golge"] = bool(kural.get("shadow_mode"))
    return tip, bolge


def _kod_adi(olay: dict, tip: str) -> str:
    """Olay kodunun Türkçe adı ("Baret yok"). 007 öncesi kodsuz olay kural
    tipinin adıyla, eski kayıt olduğu söylenerek görünür (ortak.py ile aynı)."""
    tanim = OLAY_KODLARI.get(olay.get("event_code") or "")
    return tanim.ad if tanim else f"{tip} (eski kayıt)"


def _kirilim(sayaclar: dict[str, Counter], baslik: str, sutun: str) -> dict:
    """Bir kırılım tablosu: ad · adet · pay · yanlış alarm oranı · kapsama.

    Satırlar adede göre sıralanır; eşitlikte ada göre - aynı veri her açılışta
    aynı sırada çıksın, rapor iki kez alındığında "değişmiş" görünmesin.
    """
    toplam = sum(s["adet"] for s in sayaclar.values())
    en_yuksek = max((s["adet"] for s in sayaclar.values()), default=0)
    satirlar = []
    for ad, sayac in sorted(sayaclar.items(), key=lambda ikili: (-ikili[1]["adet"], ikili[0])):
        isaretli = sayac["dogru"] + sayac["yanlis"]
        satirlar.append(
            {
                "ad": ad,
                "adet": sayac["adet"],
                "pay": _oran_metni(sayac["adet"], toplam),
                "genislik": cubuk_yuzdesi(sayac["adet"], en_yuksek),
                # İşaretlenmemiş olay "doğru uyarı" DEĞİLDİR: oran yalnızca
                # işaretlenmişler üzerinden verilir, yoksa "-" yazılır.
                "yanlis_alarm": _oran_metni(sayac["yanlis"], isaretli) if isaretli else "-",
                "isaretli": isaretli,
                # Oranın yanında inceleme kapsamı (docs/17 §5.9): düşük kapsamda
                # oran temsil edici değildir. AŞAĞI yuvarlanır: %99,6 "%100"
                # görünüp incelenmemiş olayı gizlemesin.
                "kapsama": _kapsama_orani(isaretli, sayac["adet"]),
            }
        )
    return {"baslik": baslik, "sutun": sutun, "satirlar": satirlar, "toplam": toplam}


def _oran_metni(pay: int, payda: int) -> str:
    if payda <= 0:
        return "-"
    return f"%{round(pay / payda * 100)}"


def _kapsama_orani(isaretli: int, adet: int) -> str:
    if adet <= 0:
        return "-"
    return f"%{isaretli * 100 // adet}"


def _gun_sutunlari(gunler: Counter, baslangic: str, bitis: str) -> dict:
    """Dönemin HER günü için bir çubuk - olay olmayan günler de çizilir.

    Boş günleri atlarsak grafik yalan söyler: üç günü boş geçen bir hafta,
    yan yana üç dolu çubuk gibi görünür.
    """
    gun_listesi = _gun_araligi(baslangic, bitis)
    en_yuksek = max((gunler.get(g, 0) for g in gun_listesi), default=0)
    seyreltme = max(1, (len(gun_listesi) + GUN_ETIKET_SINIRI - 1) // GUN_ETIKET_SINIRI)
    sutunlar = []
    for sira, gun in enumerate(gun_listesi):
        adet = gunler.get(gun, 0)
        gg, aa = gun[8:10], gun[5:7]
        sutunlar.append(
            {
                "etiket": f"{gg}.{aa}" if sira % seyreltme == 0 else "",
                "baslik": f"{gg}.{aa}.{gun[0:4]} · {adet} ihlal",
                "deger": adet,
                "yukseklik": cubuk_yuzdesi(adet, en_yuksek),
            }
        )
    en_yogun = ""
    if en_yuksek:
        gun = max(gun_listesi, key=lambda g: (gunler.get(g, 0), g))
        en_yogun = f"{gun[8:10]}.{gun[5:7]}.{gun[0:4]} · {en_yuksek} ihlal"
    return {"sutunlar": sutunlar, "gun_sayisi": len(gun_listesi), "en_yogun": en_yogun}


def _gun_araligi(baslangic: str, bitis: str) -> list[str]:
    """['2026-08-01', '2026-08-02', ...] - iki tarih dahil.

    Gün eklemesi zaman.py üzerinden yapılır; burada elle takvim aritmetiği
    yapılsaydı ikinci bir zaman kaynağı doğardı (docs/08 R7).
    """
    gunler = []
    gun = baslangic
    while gun <= bitis and len(gunler) <= 3660:  # ~10 yıl: sonsuz döngü emniyeti
        gunler.append(gun)
        gun = zaman.yerel_tarih_iso(zaman.yerel_gun_sonu_utc(gun))
    return gunler


def rapor_verisi(baglanti, sorgu) -> dict:
    """Raporun TÜM sayıları. Ekran da CSV de bunu kullanır: iki ayrı hesap
    olsaydı yazdırılan rapor ile Excel dosyası farklı sayı gösterebilirdi."""
    baslangic, bitis = _donem(sorgu)
    alan = (sorgu.get("alan") or "").strip()
    olaylar = _olaylari_getir(baglanti, baslangic, bitis, alan)
    bolge_adlari = {s["id"]: s["name"] for s in baglanti.execute("SELECT id, name FROM zones")}

    def _yeni() -> Counter:
        return Counter()

    kural_sayaci: dict[str, Counter] = defaultdict(_yeni)
    kod_sayaci: dict[str, Counter] = defaultdict(_yeni)
    kamera_sayaci: dict[str, Counter] = defaultdict(_yeni)
    bolum_sayaci: dict[str, Counter] = defaultdict(_yeni)
    bolge_sayaci: dict[str, Counter] = defaultdict(_yeni)
    gunler: Counter = Counter()
    durumlar: Counter = Counter()
    golge_adedi = 0

    for olay in olaylar:
        tip, bolge = _kural_bilgisi(olay, bolge_adlari)
        kamera = olay["kamera_adi"] or _SILINMIS_KAMERA
        bolum = olay["kamera_alani"] or _BOLUMSUZ
        durum = olay["status"]
        durumlar[durum] += 1
        golge_adedi += 1 if olay["golge"] else 0
        gunler[zaman.yerel_tarih_iso(olay["occurred_at"])] += 1
        for sayac, anahtar in (
            (kural_sayaci, tip),
            (kod_sayaci, _kod_adi(olay, tip)),
            (kamera_sayaci, kamera),
            (bolum_sayaci, bolum),
            (bolge_sayaci, bolge),
        ):
            sayac[anahtar]["adet"] += 1
            if durum == "false_alarm":
                sayac[anahtar]["yanlis"] += 1
            elif durum == "reviewed":
                sayac[anahtar]["dogru"] += 1

    toplam = len(olaylar)
    isaretli = durumlar["reviewed"] + durumlar["false_alarm"]
    # Olay sınırına dayanıldıysa en eski gün eksik okundu (sorgu yeniden eskiye)
    kesim_gunu = (
        zaman.yerel_tarih_iso(olaylar[-1]["occurred_at"]) if toplam >= EN_COK_OLAY else None
    )
    analiz_saatleri = _analiz_saatleri(baglanti, baslangic, bitis, alan, olaylar, kesim_gunu)
    saatler = saat_sutunlari([o["occurred_at"] for o in olaylar], "ihlal")
    gun_grafigi = _gun_sutunlari(gunler, baslangic, bitis)

    return {
        "baslangic": baslangic,
        "bitis": bitis,
        "alan": alan,
        "donem_metni": (
            f"{zaman.ekranda_tarih(zaman.yerel_gun_baslangici_utc(baslangic))} - "
            f"{zaman.ekranda_tarih(zaman.yerel_gun_baslangici_utc(bitis))}"
        ),
        "uretim_zamani": zaman.ekranda_goster_kisa(zaman.simdi_utc()),
        "toplam": toplam,
        "kartlar": _kartlar(toplam, gun_grafigi, saatler, durumlar, isaretli),
        "kirilimlar": [
            _kirilim(kural_sayaci, "Kural tipine göre", "Kural"),
            # Baret ve yelek burada AYRI satırdır: yanlış alarm oranları ayrı
            # okunur (docs/17 §13 3e)
            _kirilim(kod_sayaci, "Olay koduna göre", "Olay"),
            _kirilim(kamera_sayaci, "Kameraya göre", "Kamera"),
            _kirilim(bolum_sayaci, "Bölüme göre", "Bölüm"),
            _kirilim(bolge_sayaci, "Bölgeye göre", "Bölge"),
        ],
        "analiz_saatleri": analiz_saatleri,
        "hedef_yanlis_alarm": sayi_metni(HEDEF_YANLIS_ALARM_SAAT),
        "saat_sutunlari": saatler["sutunlar"],
        "saat_tepesi": saatler["tepe"],
        "gun_sutunlari": gun_grafigi["sutunlar"],
        "gun_sayisi": gun_grafigi["gun_sayisi"],
        "notlar": _notlar(toplam, isaretli, golge_adedi),
        "sinira_dayandi": toplam >= EN_COK_OLAY,
        "en_cok_olay": EN_COK_OLAY,
    }


def _saat_metni(saniye: float) -> str:
    """Analiz süresi, Türkçe: '12,5 sa'; hiç yoksa '-'. Birkaç dakikalık süre
    "0,0 sa" yazılmaz: sıfır sanılırdı."""
    if saniye <= 0:
        return "-"
    if saniye < 180:
        return "< 0,1 sa"
    return f"{saniye / 3600:.1f}".replace(".", ",") + " sa"


def _yanlis_orani_metni(oran: float | None) -> str:
    """'1,25 / sa'; ölçülemediyse söylenir. İki basamak: 25 saatte 1 yanlış
    alarm (0,04) sıfıra yuvarlanmasın; daha küçüğü de "0" değil "< 0,01"."""
    if oran is None:
        return "ölçülemedi"
    if 0 < oran < 0.005:
        return "< 0,01 / sa"
    return f"{sayi_metni(oran, basamak=2)} / sa"


def _kapsama_metni(olculen_s: float, analiz_s: float) -> str:
    """Analiz edilen sürenin incelemesi tam kısmı. AŞAĞI yuvarlanır: %99,6
    "%100" görünüp eksik bir günü gizlemesin."""
    if analiz_s <= 0:
        return "-"
    return f"%{math.floor(olculen_s / analiz_s * 100)}"


def _analiz_saatleri(
    baglanti, baslangic: str, bitis: str, alan: str, olaylar, kesim_gunu: str | None
) -> list[dict]:
    """Kamera başına analiz edilen süre ve yanlış alarm / saat (docs/17 §14).

    Payda OLAY değil SAAT'tir (analysis_hours: model yüklüyken işlenen kareler
    arası süre; kopukluk ve model yokluğu sayılmaz). Oran yalnız inceleme
    kapsamı TAM olan kamera × gün dilimlerinden hesaplanır: o günün gölgede
    olmayan her ihlali "İncelendi" ya da "Yanlış alarm" işaretli olmalı.
    Eksik dilim hesaba girseydi, işaretlenmemiş olaylar paydan düşerken saat
    paydada kalır ve oran yapay olarak düşük (hedef "tuttu") görünürdü.
    Gölge moddaki olaylar operatöre ulaşmadığı için orana girmez, ayrı sayılır.

    Olaylarını bilemediğimiz dilim TAM sayılmaz - "olaysız gün" sanılıp oranı
    sıfıra çekerdi: silinmiş kameranın dilimleri (olayları kamerasız kaldı,
    ON DELETE SET NULL) ve olay sınırına dayanınca eksik okunan en eski günler
    (`kesim_gunu` ve öncesi). `olaylar` _kural_bilgisi'nden geçmiştir
    (olay["golge"] dolu).
    """
    kosullar = ["h.hour_utc >= ?", "h.hour_utc < ?"]
    # Türkiye saati tam saat farkıdır: gün sınırları saat başına düşer
    degerler: list = [
        zaman.yerel_gun_baslangici_utc(baslangic)[:13],
        zaman.yerel_gun_sonu_utc(bitis)[:13],
    ]
    if alan:
        kosullar.append("c.area = ?")
        degerler.append(alan)
    # Kamera anahtarı (kimlik, silinmiş mi): kimlik yeniden kullanılabilir
    # (INTEGER PRIMARY KEY), silinen kameranın saatleri yenisine yazılmasın
    sureler: dict[tuple[tuple[int, bool], str], float] = defaultdict(float)
    adlar: dict[tuple[int, bool], str] = {}
    for satir in baglanti.execute(
        "SELECT h.camera_id, h.hour_utc, h.analyzed_s, c.name AS kamera_adi "
        "FROM analysis_hours h LEFT JOIN cameras c "
        "  ON c.id = h.camera_id AND h.hour_utc >= substr(c.created_at, 1, 13) "
        f"WHERE {' AND '.join(kosullar)} ORDER BY h.camera_id, h.hour_utc",
        degerler,
    ):
        silinmis = satir["kamera_adi"] is None
        kamera = (satir["camera_id"], silinmis)
        gun = zaman.yerel_tarih_iso(satir["hour_utc"] + ":00:00+00:00")
        sureler[(kamera, gun)] += satir["analyzed_s"]
        adlar[kamera] = (
            f"{_SILINMIS_KAMERA} (#{satir['camera_id']})" if silinmis else satir["kamera_adi"]
        )

    dilimler: dict[tuple[tuple[int, bool], str], Counter] = defaultdict(Counter)
    for olay in olaylar:
        if olay["camera_id"] is None:
            continue  # kamerası silinmiş: hangi kameranın olayı olduğu bilinmez
        kamera = (olay["camera_id"], False)
        adlar.setdefault(kamera, olay["kamera_adi"] or _SILINMIS_KAMERA)
        sayac = dilimler[(kamera, zaman.yerel_tarih_iso(olay["occurred_at"]))]
        if olay["golge"]:
            sayac["golge_yanlis"] += 1 if olay["status"] == "false_alarm" else 0
            continue
        sayac["adet"] += 1
        sayac["isaretli"] += 1 if olay["status"] in ("reviewed", "false_alarm") else 0
        sayac["yanlis"] += 1 if olay["status"] == "false_alarm" else 0

    kameralar: dict[tuple[int, bool], Counter] = defaultdict(Counter)
    # Sıralı gezilir: kayan nokta toplamı her açılışta aynı çıksın
    for kamera, gun in sorted(set(sureler) | set(dilimler)):
        sure = sureler.get((kamera, gun), 0.0)
        sayac = dilimler.get((kamera, gun), Counter())
        toplam = kameralar[kamera]
        toplam["analiz_s"] += sure
        toplam["golge_yanlis"] += sayac["golge_yanlis"]
        tam = (
            sure > 0
            and not kamera[1]
            and (kesim_gunu is None or gun > kesim_gunu)
            and sayac["isaretli"] == sayac["adet"]
        )
        if tam:
            toplam["olculen_s"] += sure
            toplam["yanlis"] += sayac["yanlis"]

    satirlar = []
    for kamera, toplam in kameralar.items():
        olculen_saat = toplam["olculen_s"] / 3600
        oran = toplam["yanlis"] / olculen_saat if olculen_saat > 0 else None
        satirlar.append(
            {
                "kamera": adlar[kamera],
                "analiz": _saat_metni(toplam["analiz_s"]),
                "olculen": _saat_metni(toplam["olculen_s"]),
                "kapsama": _kapsama_metni(toplam["olculen_s"], toplam["analiz_s"]),
                "oran": _yanlis_orani_metni(oran),
                "yanlis": toplam["yanlis"],
                "hedef_asildi": oran is not None and oran > HEDEF_YANLIS_ALARM_SAAT,
                "golge_yanlis": toplam["golge_yanlis"],
            }
        )
    return sorted(satirlar, key=lambda s: s["kamera"])


def _kartlar(toplam: int, gun_grafigi: dict, saatler: dict, durumlar, isaretli: int) -> list[dict]:
    gun_sayisi = max(gun_grafigi["gun_sayisi"], 1)
    return [
        {
            "etiket": "Toplam ihlal",
            "deger": str(toplam),
            "alt": f"{gun_sayisi} günde",
            "sinif": "",
        },
        {
            "etiket": "Günlük ortalama",
            "deger": sayi_metni(toplam / gun_sayisi) or "0",
            "alt": "ihlal / gün",
            "sinif": "",
        },
        {
            "etiket": "En yoğun gün",
            "deger": gun_grafigi["en_yogun"].split(" · ")[0] if gun_grafigi["en_yogun"] else "-",
            "alt": gun_grafigi["en_yogun"].split(" · ")[-1] if gun_grafigi["en_yogun"] else "",
            # Tarih ve saat aralığı METİNDİR: sayı kutusunun 46 px'lik rakam
            # ölçüsünde kutuya sığmaz, taşar (ölçüldü).
            "sinif": "metin",
        },
        {
            "etiket": "En yoğun saat",
            "deger": saatler["tepe"].split("·")[0].replace("En yoğun ", "").strip()
            if saatler["tepe"]
            else "-",
            "alt": saatler["tepe"].split("·")[-1].strip() if saatler["tepe"] else "",
            "sinif": "metin",
        },
        {
            "etiket": "İşaretlenen",
            "deger": _oran_metni(isaretli, toplam),
            "alt": f"{isaretli} / {toplam} olay",
            "sinif": "",
        },
        {
            "etiket": "Yanlış alarm",
            "deger": _oran_metni(durumlar["false_alarm"], isaretli),
            "alt": "işaretlenenler içinde",
            "sinif": "",
        },
    ]


def _notlar(toplam: int, isaretli: int, golge: int) -> list[str]:
    """Sayının NE OLMADIĞINI söyleyen cümleler.

    Rapor dışarıya (yönetime, denetime) gidecek bir belgedir; bir oranın hangi
    kümede hesaplandığını yazmayan rapor, iyi niyetle yanlış okunur.
    """
    notlar = [
        "Rapor yalnızca İHLAL olaylarını sayar. Kamera koptu / disk azaldı gibi "
        "sistem olayları dahil değildir.",
    ]
    if toplam and isaretli < toplam:
        notlar.append(
            f"Yanlış alarm oranı yalnızca İŞARETLENMİŞ {isaretli} olay üzerinden "
            f"hesaplanmıştır; {toplam - isaretli} olay henüz incelenmemiştir "
            "(Komuta → İnceleme). İşaretlenmemiş olay 'doğru uyarı' sayılmaz. "
            "Tablolarda oranın yanındaki kapsama, o satırdaki olayların yüzde "
            "kaçının işaretlendiğidir: kapsama düşükse oran o satırı temsil etmez."
        )
    elif toplam:
        notlar.append("Dönemdeki olayların tamamı incelenip işaretlenmiştir.")
    if golge:
        notlar.append(
            f"{golge} olay GÖLGE MODDAKİ bir kuraldan gelmiştir: kayda geçmiş ama "
            "hoparlörden anons ÇALMAMIŞ, ekranda uyarı bandı çıkmamıştır."
        )
    notlar.append(
        "Yanlış alarm / saat, kameranın ANALİZ EDİLEN süresine bölünür (kamera koptuğunda "
        "ya da tespit modeli yokken geçen süre sayılmaz) ve yalnız incelemesi TAM olan "
        "günlerden hesaplanır: o günün gölgede olmayan her ihlali işaretlenmiş olmalı. "
        "Kapsama, analiz edilen sürenin ne kadarının bu ölçüme girdiğini söyler; hiç tam "
        'gün yoksa "ölçülemedi" yazar. Hedef: kamera başına saatte en çok '
        f"{sayi_metni(HEDEF_YANLIS_ALARM_SAAT)} yanlış alarm. Kuralı olmayan ya da yalnız "
        'gölgede kuralı olan kamerada "0 / sa" bir başarı değildir: o kamera operatöre '
        "uyarı üretmemiştir."
    )
    notlar.append(
        "Sayılar olay anındaki kural görüntüsünden okunur. Kural sonradan "
        "değiştirilse ya da silinse bile geçmiş dönem raporu aynı kalır."
    )
    return notlar


# =====================================================================
# ROTALAR
# =====================================================================


@router.get("/komuta/rapor", response_class=HTMLResponse)
def rapor_ekrani(istek: Request, baglanti=Depends(baglanti_al)):
    baglam = kabuk_baglami(istek, baglanti, "rapor")
    baglam.update(rapor_verisi(baglanti, istek.query_params))
    baglam["alanlar"] = [
        s["area"]
        for s in baglanti.execute(
            "SELECT DISTINCT area FROM cameras WHERE area != '' ORDER BY area"
        )
    ]
    baglam["istek_sorgusu"] = istek.url.query
    return sablonlar.TemplateResponse(istek, "komuta_rapor.html", baglam)


@router.get("/komuta/rapor/ozet.csv")
def rapor_csv(istek: Request, baglanti=Depends(baglanti_al)):
    """Ekrandaki rapor, Excel'in açabildiği biçimde.

    Olay olay döküm İSTEMEZ - o zaten /olaylar/disa-aktar.csv'dedir. Buradaki
    dosya raporun ÖZETİDİR: aynı sayılar, satır satır.
    """
    veri = rapor_verisi(baglanti, istek.query_params)
    erisim_yaz(baglanti, istek, "export_csv", f"rapor ({veri['donem_metni']})")
    tampon = io.StringIO()
    yazici = CsvYazici(tampon)  # formül kaçışlı, noktalı virgüllü (R31)
    yazici.writerow(["DALSAN İSG - Dönem Raporu"])
    yazici.writerow(["Dönem", veri["donem_metni"]])
    yazici.writerow(["Bölüm", veri["alan"] or "tüm fabrika"])
    yazici.writerow(["Rapor zamanı", veri["uretim_zamani"]])
    yazici.writerow([])

    yazici.writerow(["Özet"])
    for kart in veri["kartlar"]:
        yazici.writerow([kart["etiket"], kart["deger"], kart["alt"]])
    yazici.writerow([])

    for kirilim in veri["kirilimlar"]:
        yazici.writerow([kirilim["baslik"]])
        yazici.writerow([kirilim["sutun"], "İhlal", "Pay", "İşaretli", "Kapsama", "Yanlış alarm"])
        for satir in kirilim["satirlar"]:
            yazici.writerow(
                [
                    satir["ad"],
                    satir["adet"],
                    satir["pay"],
                    satir["isaretli"],
                    satir["kapsama"],
                    satir["yanlis_alarm"],
                ]
            )
        yazici.writerow([])

    yazici.writerow(["Analiz edilen süre ve yanlış alarm / saat"])
    yazici.writerow(
        [
            "Kamera",
            "Analiz edilen",
            "İncelemesi tam",
            "Kapsama",
            "Yanlış alarm / saat",
            "Gölgede yanlış alarm",
        ]
    )
    for satir in veri["analiz_saatleri"]:
        yazici.writerow(
            [
                satir["kamera"],
                satir["analiz"],
                satir["olculen"],
                satir["kapsama"],
                satir["oran"],
                satir["golge_yanlis"],
            ]
        )
    yazici.writerow([])

    yazici.writerow(["Saatlik dağılım"])
    yazici.writerow(["Saat", "İhlal"])
    for sutun in veri["saat_sutunlari"]:
        yazici.writerow([f"{sutun['etiket']}:00", sutun["deger"]])
    yazici.writerow([])

    yazici.writerow(["Günlük dağılım"])
    yazici.writerow(["Gün", "İhlal"])
    for sutun in veri["gun_sutunlari"]:
        yazici.writerow([sutun["baslik"].split(" · ")[0], sutun["deger"]])
    yazici.writerow([])

    yazici.writerow(["Notlar"])
    for not_metni in veri["notlar"]:
        yazici.writerow([not_metni])

    dosya_adi = f"dalsan-rapor-{veri['baslangic']}_{veri['bitis']}.csv"
    return Response(
        content="﻿" + tampon.getvalue(),  # BOM: Excel'de Türkçe karakterler için
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={dosya_adi}"},
    )

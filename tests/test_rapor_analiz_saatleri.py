"""Raporda analiz edilen süre ve yanlış alarm / saat (docs/17 §14; Faz 2e-3).

Hedef "kamera başına saatte en çok 2 yanlış alarm"dır ve payda OLAY değil
SAAT'tir. Bu yüzden testler şunları sorar:

  · Oran yalnız incelemesi TAM olan kamera × gün dilimlerinden mi geliyor?
    Eksik dilim girseydi, işaretlenmemiş olaylar paydan düşerken saat
    paydada kalır ve hedef yapay olarak "tuttu" görünürdü.
  · Hiç tam dilim yoksa sayı uydurulmuyor, "ölçülemedi" mi yazıyor?
  · Olaylarını bilemediğimiz dilim (silinmiş kamera, olay sınırında eksik
    okunan günler) "olaysız tam gün" sanılıp oranı sıfıra çekiyor mu?
  · Gün, analiz saatinin TÜRKİYE saatine göre hangi güne düştüğüdür.
"""

from __future__ import annotations

import json

import pytest

from app import veritabani, zaman
from app.web import rapor
from app.web.rapor import rapor_verisi

AGUSTOS = {"baslangic": "2026-08-01", "bitis": "2026-08-31"}


@pytest.fixture
def db(test_ayarlari, istemci):
    """İstemci fixture'ı şemayı uygular; bağlantı ondan sonra açılır."""
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        yield baglanti
    finally:
        baglanti.close()


def _kamera(
    db, ad: str = "K1", alan: str = "Sevkiyat", kurulus: str = "2026-07-01T00:00:00+00:00"
) -> int:
    imlec = db.execute(
        "INSERT INTO cameras (name, area, source_type, source_url, created_at, updated_at) "
        "VALUES (?, ?, 'file', 'v.mp4', ?, ?)",
        (ad, alan, kurulus, kurulus),
    )
    db.commit()
    return int(imlec.lastrowid)


def _saatler(db, kamera_id: int, gun_utc: str, saatler, saniye: float = 3600.0) -> None:
    """`gun_utc` gününün verilen UTC saatlerinde tam analiz."""
    db.executemany(
        "INSERT INTO analysis_hours (camera_id, hour_utc, analyzed_s, frames_processed) "
        "VALUES (?, ?, ?, ?)",
        [(kamera_id, f"{gun_utc}T{saat:02d}", saniye, int(saniye * 5)) for saat in saatler],
    )
    db.commit()


def _olay(db, kamera_id: int, zaman_utc: str, durum: str = "new", golge: bool = False) -> None:
    kayit = {"rule_type": "zone_intrusion", "zone_id": None, "shadow_mode": int(golge)}
    db.execute(
        "INSERT INTO events (occurred_at, event_type, camera_id, rule_snapshot, "
        "details, status) VALUES (?, 'violation', ?, ?, '{}', ?)",
        (zaman_utc, kamera_id, json.dumps(kayit), durum),
    )
    db.commit()


def _satir(db, kamera: str, **sorgu) -> dict:
    veri = rapor_verisi(db, sorgu or AGUSTOS)
    return next(s for s in veri["analiz_saatleri"] if s["kamera"] == kamera)


# 10 Ağustos, Türkiye saatiyle 09:00-18:59 (UTC 06-15): tam on saat
GUNDUZ = range(6, 16)


# ------------------------------------------------------------ oran ve kapsama


def test_tam_gunde_yanlis_alarm_analiz_saatine_bolunur(db):
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", GUNDUZ)
    for dakika in ("00", "10"):
        _olay(db, kamera, f"2026-08-10T09:{dakika}:00+00:00", durum="false_alarm")
    for dakika in ("20", "30", "40"):
        _olay(db, kamera, f"2026-08-10T09:{dakika}:00+00:00", durum="reviewed")

    satir = _satir(db, "K1")
    assert satir["analiz"] == "10,0 sa"
    assert satir["olculen"] == "10,0 sa"
    assert satir["kapsama"] == "%100"
    assert satir["oran"] == "0,2 / sa"  # 2 yanlış alarm / 10 saat
    assert satir["yanlis"] == 2
    assert satir["hedef_asildi"] is False


def test_incelemesi_eksik_gun_orana_girmez_kapsama_yazilir(db):
    """11 Ağustos'ta bir olay işaretlenmemiş: o günün 10 saati ve yanlış
    alarmı hesaba GİRMEZ. Girseydi oran 3/20 = 0,15 olur, gerçekte
    bilinmeyen bir günü "iyi" gösterirdi."""
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", GUNDUZ)
    _saatler(db, kamera, "2026-08-11", GUNDUZ)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", durum="false_alarm")
    _olay(db, kamera, "2026-08-10T10:00:00+00:00", durum="false_alarm")
    _olay(db, kamera, "2026-08-11T09:00:00+00:00", durum="false_alarm")
    _olay(db, kamera, "2026-08-11T10:00:00+00:00", durum="new")

    satir = _satir(db, "K1")
    assert satir["analiz"] == "20,0 sa"
    assert satir["olculen"] == "10,0 sa"
    assert satir["kapsama"] == "%50"
    assert satir["oran"] == "0,2 / sa"
    assert satir["yanlis"] == 2


def test_hic_tam_gun_yoksa_olculemedi_yazar(db):
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", GUNDUZ)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", durum="false_alarm")
    _olay(db, kamera, "2026-08-10T10:00:00+00:00", durum="new")

    satir = _satir(db, "K1")
    assert satir["oran"] == "ölçülemedi"
    assert satir["olculen"] == "-"
    assert satir["kapsama"] == "%0"
    assert satir["hedef_asildi"] is False, "ölçülemeyen sayı hedefi aşmış da sayılmaz"


def test_ihlalsiz_gun_tam_sayilir(db):
    """Hiç ihlal yoksa işaretlenecek olay da yoktur: gün tamdır, oran sıfırdır."""
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", GUNDUZ)
    satir = _satir(db, "K1")
    assert satir["oran"] == "0 / sa"
    assert satir["kapsama"] == "%100"


def test_hedef_asilinca_isaretlenir(db):
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", [6, 7])
    for dakika in range(5):
        _olay(db, kamera, f"2026-08-10T06:0{dakika}:00+00:00", durum="false_alarm")
    satir = _satir(db, "K1")
    assert satir["oran"] == "2,5 / sa"
    assert satir["hedef_asildi"] is True


def test_hedefin_tam_ustu_asim_sayilmaz(db):
    """Hedef "en çok 2": saatte tam 2 yanlış alarm hedefi tutturur."""
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", [6])
    _olay(db, kamera, "2026-08-10T06:00:00+00:00", durum="false_alarm")
    _olay(db, kamera, "2026-08-10T06:30:00+00:00", durum="false_alarm")
    satir = _satir(db, "K1")
    assert satir["oran"] == "2 / sa"
    assert satir["hedef_asildi"] is False


def test_cok_kucuk_oran_sifir_gorunmez(db):
    """300 saatte 1 yanlış alarm (0,0033) "0 / sa" yazılsaydı yanlış alarm
    hiç yokmuş gibi okunurdu."""
    kamera = _kamera(db)
    for gun in range(1, 14):  # 13 gün × 24 saat = 312 saat
        _saatler(db, kamera, f"2026-08-{gun:02d}", range(24))
    _olay(db, kamera, "2026-08-05T09:00:00+00:00", durum="false_alarm")
    assert _satir(db, "K1")["oran"] == "< 0,01 / sa"


def test_kapsama_asagi_yuvarlanir(db):
    """%99,6 kapsama "%100" görünüp eksik günü gizlememeli."""
    kamera = _kamera(db)
    for gun in range(1, 11):
        _saatler(db, kamera, f"2026-08-{gun:02d}", range(24))  # 240 saat
    # 1 saat, incelemesi eksik. Ayrı bir gün: 10 Ağustos 21-23 UTC saatleri
    # Türkiye'de 11 Ağustos'a düşer, eksik gün onlara bitişik olmasın.
    _saatler(db, kamera, "2026-08-20", [6])
    _olay(db, kamera, "2026-08-20T06:10:00+00:00", durum="new")
    assert _satir(db, "K1")["kapsama"] == "%99"


# ------------------------------------------------------------ gölge mod


def test_golgedeki_olay_orana_girmez_ayri_sayilir(db):
    """Gölge moddaki kural operatöre ulaşmaz: yanlış alarmı hedefe girmez,
    işaretlenmemiş olması da günü eksik yapmaz; ama ayrı sütunda görünür."""
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", GUNDUZ)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", durum="false_alarm", golge=True)
    _olay(db, kamera, "2026-08-10T09:10:00+00:00", durum="false_alarm", golge=True)
    _olay(db, kamera, "2026-08-10T09:20:00+00:00", durum="new", golge=True)
    _olay(db, kamera, "2026-08-10T09:30:00+00:00", durum="false_alarm")

    satir = _satir(db, "K1")
    assert satir["kapsama"] == "%100"
    assert satir["oran"] == "0,1 / sa"  # yalnız gölgede olmayan 1 yanlış alarm
    assert satir["golge_yanlis"] == 2


# ------------------------------------------------------------ gün ve dönem


def test_analiz_saati_turkiye_gunune_gore_dilimlenir(db):
    """20:00 UTC = 23:00 Türkiye (10 Ağustos); 21:00 UTC = 00:00 Türkiye
    (11 Ağustos). 11'inde işaretlenmemiş bir olay var: 21:00 UTC saati o
    güne düşer ve ölçüme girmez."""
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", [20, 21])
    _olay(db, kamera, "2026-08-10T21:30:00+00:00", durum="new")  # 11 Ağustos 00:30
    satir = _satir(db, "K1")
    assert satir["analiz"] == "2,0 sa"
    assert satir["olculen"] == "1,0 sa"


def test_donem_sinirlari_turkiye_saatine_gore(db):
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", [20, 21])  # 10 Ağu 23:00 · 11 Ağu 00:00
    satir = _satir(db, "K1", baslangic="2026-08-11", bitis="2026-08-11")
    assert satir["analiz"] == "1,0 sa"
    satir = _satir(db, "K1", baslangic="2026-08-10", bitis="2026-08-10")
    assert satir["analiz"] == "1,0 sa"


def test_varsayilan_donem_supervizorun_yazdigi_saati_kapsar(db):
    """Süpervizör saat kovasını zaman.simdi_utc()[:13] ile yazar; rapor o
    biçimi okuyabilmeli (iki uç ayrı ayrı test edilip birbirini tutmayabilir)."""
    kamera = _kamera(db, kurulus=zaman.simdi_utc())
    db.execute(
        "INSERT INTO analysis_hours (camera_id, hour_utc, analyzed_s) VALUES (?, ?, 1800)",
        (kamera, zaman.simdi_utc()[:13]),
    )
    db.commit()
    assert _satir(db, "K1", baslangic="", bitis="")["analiz"] == "0,5 sa"


def test_birkac_dakikalik_analiz_sifir_yazilmaz(db):
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", [6], saniye=90)
    assert _satir(db, "K1")["analiz"] == "< 0,1 sa"


# ------------------------------------------------------------ olayını bilemediğimiz dilim


def test_silinmis_kameranin_saatleri_olculmez(db):
    """Kamera silinince olayları kamerasız kalır (ON DELETE SET NULL). Saatleri
    "olaysız tam gün" sayılsaydı oran sıfıra çekilirdi."""
    kamera = _kamera(db)
    _saatler(db, kamera, "2026-08-10", GUNDUZ)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", durum="false_alarm")
    db.execute("DELETE FROM cameras WHERE id = ?", (kamera,))
    db.commit()

    satir = _satir(db, f"Kamerası silinmiş (#{kamera})")
    assert satir["analiz"] == "10,0 sa"
    assert satir["oran"] == "ölçülemedi"


def test_yeniden_kullanilan_kimlik_eski_saatleri_devralmaz(db):
    """INTEGER PRIMARY KEY kimliği yeniden kullanır: en son eklenen kamera
    silinip yenisi eklenince yeni kamera AYNI kimliği alır. Eski kameranın
    saatleri (olayları kamerasız kalmıştır) yenisine yazılmamalı."""
    eski = _kamera(db, "Eski")
    _saatler(db, eski, "2026-08-10", GUNDUZ)
    _olay(db, eski, "2026-08-10T09:00:00+00:00", durum="false_alarm")
    db.execute("DELETE FROM cameras WHERE id = ?", (eski,))
    db.commit()
    yeni = _kamera(db, "Yeni", kurulus="2026-08-20T08:15:00+00:00")
    assert yeni == eski, "SQLite kimliği yeniden kullanmadı; test kurgusu geçersiz"
    _saatler(db, yeni, "2026-08-20", range(8, 12))

    assert _satir(db, "Yeni")["analiz"] == "4,0 sa"
    assert _satir(db, "Yeni")["oran"] == "0 / sa"
    assert _satir(db, f"Kamerası silinmiş (#{eski})")["oran"] == "ölçülemedi"


def test_olay_sinirina_dayaninca_eksik_okunan_gunler_olculmez(db, monkeypatch):
    """Sorgu en yeniden eskiye okur; sınıra dayanınca en eski günün olayları
    eksik kalır, daha eskiler hiç okunmaz. O günler "olaysız tam gün" değildir."""
    monkeypatch.setattr(rapor, "EN_COK_OLAY", 3)
    kamera = _kamera(db)
    for gun in ("09", "10", "11"):
        _saatler(db, kamera, f"2026-08-{gun}", [6])
    _olay(db, kamera, "2026-08-09T06:10:00+00:00", durum="false_alarm")
    _olay(db, kamera, "2026-08-10T06:10:00+00:00", durum="false_alarm")
    _olay(db, kamera, "2026-08-10T06:20:00+00:00", durum="reviewed")
    _olay(db, kamera, "2026-08-11T06:10:00+00:00", durum="reviewed")
    _olay(db, kamera, "2026-08-11T06:20:00+00:00", durum="reviewed")

    satir = _satir(db, "K1")
    assert satir["analiz"] == "3,0 sa"
    assert satir["olculen"] == "1,0 sa"  # yalnız 11 Ağustos
    assert satir["oran"] == "0 / sa"


# ------------------------------------------------------------ filtre, ekran, CSV


def test_alan_filtresi_analiz_saatlerine_de_uygulanir(db):
    sevkiyat = _kamera(db, "K1", "Sevkiyat")
    dokum = _kamera(db, "K2", "Döküm")
    _saatler(db, sevkiyat, "2026-08-10", GUNDUZ)
    _saatler(db, dokum, "2026-08-10", GUNDUZ)
    veri = rapor_verisi(db, {**AGUSTOS, "alan": "Döküm"})
    assert [s["kamera"] for s in veri["analiz_saatleri"]] == ["K2"]


def test_kameralar_ada_gore_sirali(db):
    for ad in ("Rampa", "Avlu", "Kapı"):
        _saatler(db, _kamera(db, ad), "2026-08-10", [6])
    veri = rapor_verisi(db, AGUSTOS)
    assert [s["kamera"] for s in veri["analiz_saatleri"]] == ["Avlu", "Kapı", "Rampa"]


def test_notlar_paydayi_ve_hedefi_soyler(db):
    notlar = " ".join(rapor_verisi(db, AGUSTOS)["notlar"])
    assert "ANALİZ EDİLEN süresine" in notlar
    assert "incelemesi TAM olan" in notlar
    assert "saatte en çok 2 yanlış alarm" in notlar
    assert '"0 / sa" bir başarı değildir' in notlar


def test_ekranda_bos_durum_ve_tablo(istemci, test_ayarlari):
    sorgu = "baslangic=2026-08-01&bitis=2026-08-31"
    metin = istemci.get(f"/komuta/rapor?{sorgu}").text
    assert 'id="analiz-saatleri"' in metin
    assert "Bu dönemde analiz saati kaydı yok" in metin

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera = _kamera(baglanti, "Rampa kamerası")
        _saatler(baglanti, kamera, "2026-08-10", [6, 7])
        for dakika in range(5):
            _olay(baglanti, kamera, f"2026-08-10T06:0{dakika}:00+00:00", durum="false_alarm")
    finally:
        baglanti.close()
    metin = istemci.get(f"/komuta/rapor?{sorgu}").text
    bolum = metin[metin.index('id="analiz-saatleri"') :]
    bolum = bolum[: bolum.index("</section>")]
    assert "Rampa kamerası" in bolum
    assert "2,5 / sa" in bolum and "hedef-asildi" in bolum
    assert "(5 yanlış alarm)" in bolum
    assert "Bu dönemde analiz saati kaydı yok" not in bolum


def test_csv_ekranla_ayni_satirlari_verir(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera = _kamera(baglanti, "K1")
        _saatler(baglanti, kamera, "2026-08-10", GUNDUZ)
        _saatler(baglanti, kamera, "2026-08-11", GUNDUZ)
        _olay(baglanti, kamera, "2026-08-10T09:00:00+00:00", durum="false_alarm")
        _olay(baglanti, kamera, "2026-08-10T09:30:00+00:00", durum="false_alarm", golge=True)
        _olay(baglanti, kamera, "2026-08-11T09:00:00+00:00", durum="new")
    finally:
        baglanti.close()

    yanit = istemci.get("/komuta/rapor/ozet.csv?baslangic=2026-08-01&bitis=2026-08-31")
    satirlar = yanit.content.decode("utf-8").splitlines()
    baslik = satirlar.index("Analiz edilen süre ve yanlış alarm / saat")
    assert satirlar[baslik + 1] == (
        "Kamera;Analiz edilen;İncelemesi tam;Kapsama;Yanlış alarm / saat;Gölgede yanlış alarm"
    )
    assert satirlar[baslik + 2] == "K1;20,0 sa;10,0 sa;%50;0,1 / sa;1"

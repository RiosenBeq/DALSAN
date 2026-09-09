"""Dönem raporu (/komuta/rapor) — docs/07 #3.

Rapor dışarıya (yönetime, denetime) gidecek bir belgedir. Bu yüzden testler
"sayfa açılıyor mu"dan fazlasını sorar:

  · Sayı DOĞRU mu — dönem dışındaki olay sayılmıyor mu?
  · Gün ve saat kovaları TÜRKİYE saatine göre mi (UTC'ye göre 3 saat kayma
    gece vardiyasını yanlış güne düşürürdü)?
  · Kural tipi, kuralın BUGÜNKÜ halinden değil olay anındaki görüntüsünden mi
    okunuyor — kural silinince geçmiş rapor değişiyor mu?
  · Yanlış alarm oranı hangi küme üzerinden veriliyor, bunu ekran YAZIYOR mu?
  · Excel çıktısı ekrandaki sayının AYNISINI mı veriyor?
"""

from __future__ import annotations

import json

import pytest

from app import veritabani, zaman
from app.web.rapor import rapor_verisi


@pytest.fixture
def db(test_ayarlari, istemci):
    """İstemci fixture'ı şemayı uygular; bağlantı ondan sonra açılır."""
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        yield baglanti
    finally:
        baglanti.close()


def _kamera(db, ad: str = "K1", alan: str = "Sevkiyat") -> int:
    simdi = zaman.simdi_utc()
    imlec = db.execute(
        "INSERT INTO cameras (name, area, source_type, source_url, created_at, updated_at) "
        "VALUES (?, ?, 'file', 'v.mp4', ?, ?)",
        (ad, alan, simdi, simdi),
    )
    db.commit()
    return int(imlec.lastrowid)


def _bolge(db, kamera_id: int, ad: str = "Rampa") -> int:
    imlec = db.execute(
        "INSERT INTO zones (camera_id, name, zone_type, polygon, updated_at) "
        "VALUES (?, ?, 'loading_area', '[[0,0],[1,0],[1,1]]', ?)",
        (kamera_id, ad, zaman.simdi_utc()),
    )
    db.commit()
    return int(imlec.lastrowid)


def _olay(
    db,
    kamera_id: int,
    zaman_utc: str,
    kural_tipi: str = "zone_intrusion",
    durum: str = "new",
    bolge_id: int | None = None,
    golge: bool = False,
    tip: str = "violation",
) -> None:
    kayit = {"rule_type": kural_tipi, "zone_id": bolge_id, "shadow_mode": int(golge)}
    db.execute(
        "INSERT INTO events (occurred_at, event_type, camera_id, rule_snapshot, "
        "details, status) VALUES (?, ?, ?, ?, '{}', ?)",
        (zaman_utc, tip, kamera_id, json.dumps(kayit), durum),
    )
    db.commit()


def _veri(db, **sorgu):
    return rapor_verisi(db, sorgu)


def _satir(kirilim: dict, ad: str) -> dict | None:
    return next((s for s in kirilim["satirlar"] if s["ad"] == ad), None)


# ------------------------------------------------------------------ dönem


def test_donem_disindaki_olay_sayilmaz(db):
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00")
    _olay(db, kamera, "2026-08-20T09:00:00+00:00")  # dönem dışı
    veri = _veri(db, baslangic="2026-08-01", bitis="2026-08-15")
    assert veri["toplam"] == 1


def test_gun_siniri_turkiye_saatine_gore(db):
    """Türkiye UTC+3'tür. 31 Temmuz 22:00 UTC = 1 Ağustos 01:00 Türkiye saati;
    olay AĞUSTOS raporuna girmelidir. Sınır UTC'ye göre kurulsaydı gece
    vardiyası her ay bir önceki aya düşerdi (docs/08 R7)."""
    kamera = _kamera(db)
    _olay(db, kamera, "2026-07-31T22:00:00+00:00")
    assert _veri(db, baslangic="2026-08-01", bitis="2026-08-31")["toplam"] == 1
    assert _veri(db, baslangic="2026-07-01", bitis="2026-07-31")["toplam"] == 0


def test_saat_kovasi_turkiye_saatine_gore(db):
    """22:30 UTC → 01:30 Türkiye. Sütun 01'e düşmeli, 22'ye değil."""
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-10T22:30:00+00:00")
    veri = _veri(db, baslangic="2026-08-01", bitis="2026-08-31")
    sutunlar = {s["etiket"]: s["deger"] for s in veri["saat_sutunlari"]}
    assert sutunlar["01"] == 1
    assert sutunlar["22"] == 0


def test_bitis_baslangictan_once_olamaz(db):
    from app.hatalar import DogrulamaHatasi

    with pytest.raises(DogrulamaHatasi):
        _veri(db, baslangic="2026-08-20", bitis="2026-08-01")


def test_bozuk_tarih_anlasilir_hata_verir(istemci):
    yanit = istemci.get("/komuta/rapor?baslangic=20-08-2026&bitis=2026-08-31")
    assert yanit.status_code == 400
    assert "Tarih" in yanit.text


def test_varsayilan_donem_bugunu_kapsar(db):
    kamera = _kamera(db)
    _olay(db, kamera, zaman.simdi_utc())
    veri = _veri(db)
    assert veri["toplam"] == 1
    assert veri["bitis"] == zaman.yerel_tarih_iso()


# --------------------------------------------------------------- kapsam


def test_sistem_olayi_rapora_girmez(db):
    """Kamera koptu / disk azaldı bakım göstergesidir; İSG performansı
    sayısını şişirmemeli."""
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", tip="system")
    _olay(db, kamera, "2026-08-10T10:00:00+00:00", tip="violation")
    assert _veri(db, baslangic="2026-08-01", bitis="2026-08-31")["toplam"] == 1


def test_alan_filtresi_yalniz_o_bolumu_sayar(db):
    sevkiyat = _kamera(db, "K1", "Sevkiyat")
    dokum = _kamera(db, "K2", "Döküm")
    _olay(db, sevkiyat, "2026-08-10T09:00:00+00:00")
    _olay(db, dokum, "2026-08-10T09:00:00+00:00")
    assert _veri(db, baslangic="2026-08-01", bitis="2026-08-31")["toplam"] == 2
    dar = _veri(db, baslangic="2026-08-01", bitis="2026-08-31", alan="Döküm")
    assert dar["toplam"] == 1
    assert _satir(dar["kirilimlar"][1], "K2")["adet"] == 1


# ------------------------------------------------------------- kırılımlar


def test_kural_tipi_olay_anindaki_goruntuden_okunur(db):
    """Kural sonradan silinse bile geçmiş rapor aynı sayıyı vermelidir —
    rapor bir kanıt belgesidir, her açılışta değişemez."""
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", kural_tipi="ppe_violation")
    _olay(db, kamera, "2026-08-10T10:00:00+00:00", kural_tipi="vehicle_speed")
    kirilim = _veri(db, baslangic="2026-08-01", bitis="2026-08-31")["kirilimlar"][0]
    assert kirilim["baslik"] == "Kural tipine göre"
    assert _satir(kirilim, "KKD (baret/yelek)")["adet"] == 1
    assert _satir(kirilim, "Araç hız sınırı")["adet"] == 1
    # rules tablosu BOŞ; sayı yine de doğru
    assert db.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 0


def test_silinmis_kamera_ve_bolge_satirda_gorunur(db):
    """Olay kanıttır: kamerası silinse de rapordan düşmez, ama hangi satıra
    girdiği kullanıcıya söylenmelidir."""
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", bolge_id=999)
    db.execute("DELETE FROM cameras WHERE id = ?", (kamera,))
    db.commit()
    veri = _veri(db, baslangic="2026-08-01", bitis="2026-08-31")
    assert _satir(veri["kirilimlar"][1], "Kamerası silinmiş")["adet"] == 1
    assert _satir(veri["kirilimlar"][3], "Bölgesi silinmiş")["adet"] == 1


def test_bolgesiz_kural_kendi_satirinda(db):
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", kural_tipi="safe_distance")
    veri = _veri(db, baslangic="2026-08-01", bitis="2026-08-31")
    assert _satir(veri["kirilimlar"][3], "Bölgesiz (tüm kare)")["adet"] == 1


def test_kirilim_adete_gore_sirali(db):
    kamera = _kamera(db)
    for _ in range(3):
        _olay(db, kamera, "2026-08-10T09:00:00+00:00", kural_tipi="ppe_violation")
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", kural_tipi="zone_intrusion")
    satirlar = _veri(db, baslangic="2026-08-01", bitis="2026-08-31")["kirilimlar"][0]["satirlar"]
    assert [s["ad"] for s in satirlar] == ["KKD (baret/yelek)", "Bölge ihlali"]
    assert satirlar[0]["pay"] == "%75"


# ------------------------------------------------------- yanlış alarm oranı


def test_yanlis_alarm_orani_yalniz_isaretlenenler_uzerinden(db):
    """İşaretlenmemiş olay 'doğru uyarı' DEĞİLDİR. 4 olaydan 2'si işaretli,
    1'i yanlış alarm → oran %50 (işaretlenenler içinde), %25 değil."""
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", durum="false_alarm")
    _olay(db, kamera, "2026-08-10T09:10:00+00:00", durum="reviewed")
    _olay(db, kamera, "2026-08-10T09:20:00+00:00", durum="new")
    _olay(db, kamera, "2026-08-10T09:30:00+00:00", durum="new")
    veri = _veri(db, baslangic="2026-08-01", bitis="2026-08-31")
    kart = next(k for k in veri["kartlar"] if k["etiket"] == "Yanlış alarm")
    assert kart["deger"] == "%50"
    assert kart["alt"] == "işaretlenenler içinde"
    assert _satir(veri["kirilimlar"][0], "Bölge ihlali")["yanlis_alarm"] == "%50"


def test_hic_isaretlenmemisse_oran_yerine_cizgi(db):
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00")
    veri = _veri(db, baslangic="2026-08-01", bitis="2026-08-31")
    assert _satir(veri["kirilimlar"][0], "Bölge ihlali")["yanlis_alarm"] == "—"
    assert any("henüz incelenmemiştir" in n for n in veri["notlar"])


def test_golge_moddaki_olaylar_notta_soylenir(db):
    """Gölge modda olay kaydedilir ama HOPARLÖR SUSAR. Rapor bunu yazmazsa
    okuyan kişi 'bu kadar uyarı anons edildi' sanır."""
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-10T09:00:00+00:00", golge=True)
    _olay(db, kamera, "2026-08-10T10:00:00+00:00", golge=False)
    veri = _veri(db, baslangic="2026-08-01", bitis="2026-08-31")
    assert any("GÖLGE MODDAKİ" in n and "1 olay" in n for n in veri["notlar"])


def test_sistem_olaylarinin_disarida_kaldigi_yazilir(db):
    veri = _veri(db, baslangic="2026-08-01", bitis="2026-08-31")
    assert any("sistem olayları dahil değildir" in n for n in veri["notlar"])


# ---------------------------------------------------------- gün grafiği


def test_olaysiz_gunler_de_cizilir(db):
    """Boş günler atlansaydı grafik yalan söylerdi: üç günü boş geçen bir
    hafta, yan yana üç dolu çubuk gibi görünürdü."""
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-01T09:00:00+00:00")
    _olay(db, kamera, "2026-08-05T09:00:00+00:00")
    veri = _veri(db, baslangic="2026-08-01", bitis="2026-08-05")
    assert veri["gun_sayisi"] == 5
    assert [s["deger"] for s in veri["gun_sutunlari"]] == [1, 0, 0, 0, 1]


def test_en_yogun_gun_karti_dogru(db):
    kamera = _kamera(db)
    _olay(db, kamera, "2026-08-01T09:00:00+00:00")
    for _ in range(3):
        _olay(db, kamera, "2026-08-03T09:00:00+00:00")
    kart = next(
        k
        for k in _veri(db, baslangic="2026-08-01", bitis="2026-08-05")["kartlar"]
        if k["etiket"] == "En yoğun gün"
    )
    assert kart["deger"] == "03.08.2026"
    assert kart["alt"] == "3 ihlal"


def test_gunluk_ortalama_gun_sayisina_bolunur(db):
    kamera = _kamera(db)
    for _ in range(5):
        _olay(db, kamera, "2026-08-01T09:00:00+00:00")
    kart = next(
        k
        for k in _veri(db, baslangic="2026-08-01", bitis="2026-08-10")["kartlar"]
        if k["etiket"] == "Günlük ortalama"
    )
    assert kart["deger"] == "0,5"  # 5 ihlal / 10 gün, Türkçe ondalık


# ------------------------------------------------------------- ekran / CSV


def test_bos_donemde_ne_yapilacagi_yazar(istemci):
    metin = istemci.get("/komuta/rapor?baslangic=2026-08-01&bitis=2026-08-05").text
    assert "Bu dönemde ihlal kaydedilmedi" in metin
    assert "/kurallar" in metin


def test_ekranda_yazdirma_ve_excel_dugmeleri_var(istemci):
    """Kullanıcıya terminal komutu değil DÜĞME verilir (CLAUDE.md §8)."""
    metin = istemci.get("/komuta/rapor").text
    assert "Yazdır / PDF yap" in metin
    assert "window.print()" in metin
    assert "/komuta/rapor/ozet.csv" in metin


def test_yazdirma_duzeni_stil_dosyasinda(istemci):
    """@media print olmadan kâğıda sol raf ve filtre kutusu da basılır."""
    from pathlib import Path

    css = Path(__file__).resolve().parents[1] / "backend/app/web/static/komuta.css"
    metin = css.read_text(encoding="utf-8")
    assert "@media print" in metin
    assert ".yazdirma-gizle" in metin


def test_csv_turkce_excel_icin_hazirlanir(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera = _kamera(baglanti, "K1", "Sevkiyat")
        _olay(baglanti, kamera, "2026-08-10T09:00:00+00:00", durum="false_alarm")
    finally:
        baglanti.close()

    yanit = istemci.get("/komuta/rapor/ozet.csv?baslangic=2026-08-01&bitis=2026-08-31")
    assert yanit.status_code == 200
    metin = yanit.content.decode("utf-8")
    assert metin.startswith("﻿")  # BOM: Excel Türkçe karakterleri doğru okusun
    assert ";" in metin  # Türkçe Excel noktalı virgül bekler
    assert "dalsan-rapor-2026-08-01_2026-08-31.csv" in yanit.headers["content-disposition"]
    assert "Kural tipine göre" in metin
    assert "Bölge ihlali" in metin


def test_csv_ekranla_ayni_sayilari_verir(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera = _kamera(baglanti, "K1", "Sevkiyat")
        for _ in range(7):
            _olay(baglanti, kamera, "2026-08-10T09:00:00+00:00")
    finally:
        baglanti.close()

    sorgu = "baslangic=2026-08-01&bitis=2026-08-31"
    ekran = istemci.get(f"/komuta/rapor?{sorgu}").text
    csv_metni = istemci.get(f"/komuta/rapor/ozet.csv?{sorgu}").content.decode("utf-8")
    assert "Toplam ihlal" in ekran
    assert "Toplam ihlal;7;" in csv_metni
    assert "Bölge ihlali;7;%100" in csv_metni


def test_bolge_adi_raporda_gorunur(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera = _kamera(baglanti, "K1", "Sevkiyat")
        bolge = _bolge(baglanti, kamera, "Yükleme rampası")
        _olay(baglanti, kamera, "2026-08-10T09:00:00+00:00", bolge_id=bolge)
    finally:
        baglanti.close()
    metin = istemci.get("/komuta/rapor?baslangic=2026-08-01&bitis=2026-08-31").text
    assert "Yükleme rampası" in metin
    assert "Bölgeye göre" in metin

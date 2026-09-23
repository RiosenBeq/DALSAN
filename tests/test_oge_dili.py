"""Öğe dili: sistemin tanıdığı öğeler her ekranda aynı simge ve renkle görünür.

İlk istekteki öğeler (insan, forklift, tır, yaya yolu, baret, yelek) olay
listesinde, canlı akışta ve komuta ekranında BAKINCA ayırt edilmeli.
Tablolar web/ortak.py'de, makrolar templates/bilesen.html'de, görünüş
stil.css → ÖĞE DİLİ bölümündedir.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.rules.tipler import TANINAN_SINIFLAR
from app.uygulama import uygulama_olustur
from app.web.ortak import (
    ANONS_OGELERI,
    BOLGE_SIMGELERI,
    BOLGE_TIPLERI,
    OGE_IHLAL_ADLARI,
    OGELER,
    SINIF_OGELERI,
    olay_ogesi,
)

KOK = Path(__file__).resolve().parents[1]
SPRITE = (KOK / "backend/app/web/static/vendor/simgeler.svg").read_text(encoding="utf-8")
STIL = (KOK / "backend/app/web/static/stil.css").read_text(encoding="utf-8")
SPRITE_IDLERI = set(re.findall(r'id="s-([\w-]+)"', SPRITE))


# ------------------------------------------------------------ tablolar tutarlı


def test_her_ogenin_simgesi_spritete_var():
    """Şablon simgeyi değişkenle çağırır (simge(oge.simge)); sabit adlı
    çağrıları yakalayan test bunu göremez, burada ayrıca sınanır."""
    eksik = {o.anahtar: o.simge for o in OGELER.values() if o.simge not in SPRITE_IDLERI}
    assert not eksik, f"sprite'ta olmayan öğe simgeleri: {eksik}"


def test_her_bolge_tipinin_simgesi_var():
    assert set(BOLGE_SIMGELERI) == set(BOLGE_TIPLERI)
    assert set(BOLGE_SIMGELERI.values()) <= SPRITE_IDLERI


def test_her_ogenin_css_rengi_var():
    """Rengi tanımlanmamış öğe gri kalır ve diğerlerinden ayırt edilemez."""
    for anahtar in OGELER:
        assert f".oge-{anahtar}" in STIL, f".oge-{anahtar} stil.css'te yok"


def test_her_ihlal_adi_bir_ogeye_ait():
    assert set(OGE_IHLAL_ADLARI) <= set(OGELER)


def test_taninan_her_sinifin_ogesi_var():
    assert set(TANINAN_SINIFLAR) <= set(SINIF_OGELERI)
    assert set(SINIF_OGELERI.values()) <= set(OGELER)


def test_semadaki_her_anons_mesajinin_ogesi_var(test_ayarlari):
    """Anons sayfasında her mesaj satırı kendi öğesiyle görünür."""
    from app import veritabani

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        anahtarlar = {r["key"] for r in baglanti.execute("SELECT key FROM announcement_messages")}
    finally:
        baglanti.close()
    assert anahtarlar, "şemada anons mesajı yok"
    assert anahtarlar <= set(ANONS_OGELERI), anahtarlar - set(ANONS_OGELERI)
    assert set(ANONS_OGELERI.values()) <= set(OGELER)


# ------------------------------------------------------ olay → öğe eşlemesi


def _bolge(hedef, yon):
    """Bölge ihlali kuralının olay anındaki kaydı (hazır kurallardaki gibi)."""
    return {"rule_type": "zone_intrusion", "target_classes": hedef, "params": {"mode": yon}}


@pytest.mark.parametrize(
    ("kural", "detay", "beklenen"),
    [
        ({"rule_type": "safe_distance"}, {"mesafe_m": 1.2}, "forklift"),
        ({"rule_type": "vehicle_speed"}, {"hiz_kmh": 14}, "hiz"),
        ({"rule_type": "ppe_violation"}, {"eksik_kkd": ["helmet"]}, "baret"),
        ({"rule_type": "ppe_violation"}, {"eksik_kkd": ["vest"]}, "yelek"),
        ({"rule_type": "ppe_violation"}, {"eksik_kkd": ["helmet", "vest"]}, "kkd"),
        ({"rule_type": "ppe_violation"}, {}, "kkd"),
        # Yaya yolu kuralı: yolun DIŞINDA kalan kişi (hazır kural, docs/03)
        (_bolge(["person"], "outside"), {}, "yaya-yolu"),
        # Yasak bölge / yükleme alanı: alanın İÇİNDE kalan kişi
        (_bolge(["person"], "inside"), {}, "alan"),
        # Tır park yeri: alanın dışında duran tır
        (_bolge(["truck"], "outside"), {}, "park"),
        # Kural kaydında alanlar ham JSON metni olarak da gelebilir
        (
            {
                "rule_type": "zone_intrusion",
                "target_classes": '["person"]',
                "params": '{"mode": "outside"}',
            },
            {},
            "yaya-yolu",
        ),
        # Eski kayıt: yalnız kural tipi. Simgesiz kalmaz.
        ({"rule_type": "zone_intrusion"}, {}, "alan"),
        ({}, {}, "alan"),
    ],
)
def test_ihlalin_ogesi(kural, detay, beklenen):
    assert olay_ogesi("violation", kural, detay) == beklenen


def test_sistem_olaylari_kamera_ve_sistem_olarak_ayrilir():
    assert olay_ogesi("system", {}, {"mesaj": "Kamera çevrimdışı: Rampa"}) == "kamera"
    assert olay_ogesi("system", {}, {"mesaj": "Disk azalıyor"}) == "sistem"


# ---------------------------------------------------------- ekranda görünür


@pytest.fixture
def istemci(test_ayarlari):
    with TestClient(uygulama_olustur(test_ayarlari, analiz=False)) as istemci:
        yield istemci


def _kurulum(istemci, test_ayarlari) -> None:
    import json

    from app import veritabani, zaman

    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Rampa",
            "area": "Sevkiyat",
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.5:554/1",
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    kamera = int(yanit.headers["location"].rsplit("/", 1)[1])
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        for kural, detay in (
            ({"rule_type": "safe_distance"}, {"mesafe_m": 1.4}),
            ({"rule_type": "safe_distance"}, {"mesafe_m": 2.0}),
            ({"rule_type": "ppe_violation"}, {"eksik_kkd": ["vest"]}),
        ):
            baglanti.execute(
                "INSERT INTO events (occurred_at, event_type, camera_id, rule_snapshot, details) "
                "VALUES (?, 'violation', ?, ?, ?)",
                (zaman.simdi_utc(), kamera, json.dumps(kural), json.dumps(detay)),
            )
        baglanti.commit()
    finally:
        baglanti.close()


def test_canli_akista_her_olay_ogesiyle_gorunur(istemci, test_ayarlari):
    _kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta").text
    assert 'class="oge-rozeti oge-forklift" title="Forklift"' in metin
    assert 'class="oge-rozeti oge-yelek" title="Reflektörlü yelek"' in metin
    assert "#s-yelek" in metin and "#s-forklift" in metin


def test_komuta_ekrani_ihlalleri_ogeye_gore_sayar(istemci, test_ayarlari):
    """Alan yoğunluğu NEREDE sorusunu, öğe dağılımı NE sorusunu cevaplar."""
    _kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta").text
    assert "Öğelere göre ihlaller" in metin
    kartlar = re.findall(
        r'class="oge-karti-deger">(\d+)</span>\s*<span class="oge-karti-ad">([^<]+)</span>', metin
    )
    assert kartlar == [("2", "Araç-yaya yakınlığı"), ("1", "Yelek yok")]


def test_ihlal_yokken_oge_paneli_cikmaz(istemci):
    istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Rampa",
            "area": "",
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.5:554/1",
            "sample_fps": "6",
        },
    )
    assert "Öğelere göre ihlaller" not in istemci.get("/komuta").text


def test_sayi_kartlarinda_simge_var(istemci):
    istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Rampa",
            "area": "",
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.5:554/1",
            "sample_fps": "6",
        },
    )
    metin = istemci.get("/komuta").text
    for ad in ("siren", "inceleme", "kamera", "kural"):
        assert f"#s-{ad}" in metin


# ------------------------------------------------ öğe dili diğer ekranlarda da


def _olay_idleri(test_ayarlari) -> list[int]:
    from app import veritabani

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return [satir[0] for satir in baglanti.execute("SELECT id FROM events ORDER BY id")]
    finally:
        baglanti.close()


def test_olay_listesi_ogeyi_ve_durumu_gosterir(istemci, test_ayarlari):
    _kurulum(istemci, test_ayarlari)
    metin = istemci.get("/olaylar").text
    assert metin.count('class="oge-rozeti oge-forklift kucuk"') == 2
    assert metin.count('class="oge-rozeti oge-yelek kucuk"') == 1
    assert metin.count('class="durum-hapi durum-new"') == 3


def test_olay_listesi_telefonda_karta_doner(istemci, test_ayarlari):
    """Altı sütunlu tablo 375 px'e sığmıyordu; asıl bilgi (özet, durum,
    kanıt) yatay kaydırmanın arkasında kalıyordu. Kart kuralı dar ekran
    bloğunda durmalı, tablo da o sınıfı taşımalı."""
    _kurulum(istemci, test_ayarlari)
    assert 'class="liste olay-tablosu"' in istemci.get("/olaylar").text
    bloklar = [b.split("\n}\n", 1)[0] for b in STIL.split("@media (max-width: 620px)")[1:]]
    assert any("table.olay-tablosu tr" in b and "grid-template-areas" in b for b in bloklar)


def test_olay_detayi_ve_inceleme_kuyrugu_ogeyi_gosterir(istemci, test_ayarlari):
    _kurulum(istemci, test_ayarlari)
    detay = istemci.get(f"/olaylar/{_olay_idleri(test_ayarlari)[0]}").text
    assert 'class="oge-rozeti oge-forklift" title="Forklift"' in detay
    assert 'class="durum-hapi durum-new"' in detay
    kuyruk = istemci.get("/komuta/inceleme").text
    assert 'class="oge-rozeti oge-forklift kucuk"' in kuyruk
    assert 'class="oge-rozeti oge-yelek kucuk"' in kuyruk


def test_kkd_durumu_asgari_hedeflere_gore_sayar(istemci, test_ayarlari):
    """Asgari miktarlar docs/04 §4.5 "Minimum" sütunundandır."""
    from app import veritabani, zaman

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        for baret, yelek in (("no", "yes"), ("no", "unknown"), ("yes", "no"), (None, None)):
            baglanti.execute(
                "INSERT INTO ppe_samples (captured_at, crop_path, helmet_label, vest_label, "
                "source) VALUES (?, 'kkd-ornekler/x.jpg', ?, ?, 'auto')",
                (zaman.simdi_utc(), baret, yelek),
            )
        baglanti.commit()
    finally:
        baglanti.close()
    metin = istemci.get("/kkd").text
    degerler = re.findall(r'class="kkd-hedef-deger"><b>(\d+)</b> / asgari (\d+)<', metin)
    assert degerler == [("4", "2500"), ("2", "500"), ("1", "500"), ("1", "300")]


def test_kkd_cubugu_asgariyi_asinca_tasmaz():
    from app.web.kkd_web import _hedef_kartlari

    kartlar = _hedef_kartlari({"toplam": 3000, "baret_yok": 250})
    assert [k["yuzde"] for k in kartlar] == [100, 50, 0, 0]


def test_anons_mesajlari_ogesiyle_gorunur(istemci):
    metin = istemci.get("/anons").text
    for anahtar in sorted(set(ANONS_OGELERI.values())):
        assert f'class="oge-rozeti oge-{anahtar}"' in metin, anahtar


def test_kamera_sayfasinda_bolge_cipi_ve_kural_rozeti(istemci, test_ayarlari):
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Rampa",
            "area": "",
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.5:554/1",
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    kamera = int(yanit.headers["location"].rsplit("/", 1)[1])
    istemci.post(
        f"/kameralar/{kamera}/bolgeler",
        data={
            "name": "Ana yaya yolu",
            "zone_type": "pedestrian_path",
            "polygon": "[[0.1,0.1],[0.9,0.1],[0.9,0.9]]",
        },
        follow_redirects=False,
    )
    from app import veritabani

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        bolge = baglanti.execute("SELECT id FROM zones").fetchone()[0]
    finally:
        baglanti.close()
    # Hazır yaya yolu kuralı: yolun DIŞINDAKİ kişi → öğesi "yaya yolu".
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge)}, follow_redirects=False)
    metin = istemci.get(f"/kameralar/{kamera}").text
    assert 'class="bolge-cipi bolge-pedestrian-path"' in metin
    assert 'class="oge-rozeti oge-yaya-yolu kucuk" title="Yaya yolu"' in metin
    assert "#s-yaya-yolu" in metin


def test_kilavuz_her_ogeyi_aciklamasiyla_gosterir(istemci):
    """Sözlük OGELER'den üretilir: yeni öğe eklenince kılavuzda eksik kalmaz,
    ama açıklaması yoksa boş satır çıkar - bu test onu yakalar."""
    metin = istemci.get("/komuta/kilavuz").text
    sozluk = metin.split('class="simge-sozlugu"', 1)[1].split('class="durum-ornekleri"', 1)[0]
    for oge in OGELER.values():
        assert f'class="oge-rozeti oge-{oge.anahtar}" title="{oge.ad}"' in sozluk, oge.anahtar
    aciklamalar = re.findall(r'<span class="soluk-metin">([^<]*)</span>', sozluk)
    assert len(aciklamalar) == len(OGELER)
    assert all(a.strip() for a in aciklamalar)
    for durum in ("new", "reviewed", "false-alarm"):
        assert f'class="durum-hapi durum-{durum}"' in metin

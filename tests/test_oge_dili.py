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
    assert kartlar == [("2", "Forklift–insan yakınlığı"), ("1", "Yelek yok")]


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

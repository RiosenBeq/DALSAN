"""Olay ekranlarında kod, önem ve süreç (docs/17 §11; Faz 2c-2b).

Sınanan: olayın başlığı kodun adıdır, eski (kodsuz) olayın yazısı değişmez;
süren olay "sürüyor", biten olay süresiyle görünür; önem ve "yalnız sürenler"
filtreleri; CSV'nin yeni sütunları sonda; komuta ekranında renk önemden gelir;
canlı akış önemi ve seslendirilecek adı taşır.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from app import veritabani, zaman
from app.web.komuta import _olay_rengi
from app.web.olaylar_web import akis_yuku
from app.web.ortak import OLAY_SORGUSU, olay_hazirla


def _utc(saniye_once: float) -> str:
    return (datetime.now(UTC) - timedelta(seconds=saniye_once)).isoformat(timespec="seconds")


@pytest.fixture
def baglanti(test_ayarlari):
    bag = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(bag)
    simdi = zaman.simdi_utc()
    bag.execute(
        "INSERT INTO cameras (id, name, source_type, source_url, created_at, updated_at) "
        "VALUES (1, 'Rampa', 'rtsp', 'rtsp://x', ?, ?)",
        (simdi, simdi),
    )
    bag.commit()
    yield bag
    bag.close()


def _olay_ekle(
    baglanti,
    *,
    kod=None,
    onem=None,
    baslangic=None,
    bitis="anlik",
    detay=None,
    kural_tipi="zone_intrusion",
    tip="violation",
    durum="new",
) -> int:
    baslangic = baslangic or _utc(60)
    bitis = baslangic if bitis == "anlik" else bitis
    imlec = baglanti.execute(
        "INSERT INTO events (occurred_at, event_type, camera_id, rule_snapshot, details, "
        "status, event_code, severity, resolved_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)",
        (
            baslangic,
            tip,
            json.dumps({"rule_type": kural_tipi}),
            json.dumps(detay or {}),
            durum,
            kod,
            onem,
            bitis,
        ),
    )
    baglanti.commit()
    return imlec.lastrowid


def _hazirla(baglanti, olay_id: int) -> dict:
    return olay_hazirla(baglanti.execute(f"{OLAY_SORGUSU} WHERE e.id = ?", (olay_id,)).fetchone())


# ------------------------------------------------------------------ olay_hazirla


def test_kodlu_ihlalin_basligi_kodun_adi(baglanti):
    olay = _hazirla(baglanti, _olay_ekle(baglanti, kod="RESTRICTED_ENTRY", onem="high"))
    assert olay["ozet"] == "Yasak alana giriş"
    assert (olay["onem"], olay["onem_adi"]) == ("high", "Yüksek")


def test_kodlu_kkd_olayi_eksik_kalemleri_yazar(baglanti):
    iki = _olay_ekle(
        baglanti,
        kod="PPE_NO_HELMET",
        onem="high",
        kural_tipi="ppe_violation",
        detay={"eksik_kkd": ["helmet", "vest"]},
    )
    tek = _olay_ekle(
        baglanti,
        kod="PPE_NO_VEST",
        onem="medium",
        kural_tipi="ppe_violation",
        detay={"eksik_kkd": ["vest"]},
    )
    assert _hazirla(baglanti, iki)["ozet"] == "Baret ve yelek yok"
    assert _hazirla(baglanti, tek)["ozet"] == "Yelek yok"


def test_olcum_kodun_adina_eklenir(baglanti):
    olay = _hazirla(
        baglanti,
        _olay_ekle(
            baglanti,
            kod="VEHICLE_PERSON_PROXIMITY",
            onem="critical",
            kural_tipi="safe_distance",
            detay={"mesafe_m": 1.42},
        ),
    )
    assert olay["ozet"] == "Araç-yaya yakınlığı - 1,42 m"


def test_yedek_kodda_bolge_tipi_yazilir(baglanti):
    olay = _hazirla(
        baglanti,
        _olay_ekle(
            baglanti, kod="ZONE_INTRUSION", onem="medium", detay={"bolge_tipi": "ppe_required"}
        ),
    )
    assert olay["ozet"] == "Bölge ihlali - KKD zorunlu alan"


def test_eski_olayin_yazisi_degismez(baglanti):
    """Şema 007 öncesi olay: kod ve önem yok, bitiş başlangıca eşit."""
    olay = _hazirla(
        baglanti,
        _olay_ekle(baglanti, kural_tipi="ppe_violation", detay={"eksik_kkd": ["helmet"]}),
    )
    assert olay["ozet"] == "KKD (baret/yelek) - baret yok"
    assert olay["onem"] == "" and not olay["suruyor"] and olay["sure_metni"] == ""


def test_suren_olay_gecen_sureyle_biten_olay_suresiyle(baglanti):
    suren = _hazirla(
        baglanti,
        _olay_ekle(baglanti, kod="RESTRICTED_ENTRY", onem="high", baslangic=_utc(125), bitis=None),
    )
    assert suren["suruyor"] and suren["sure_metni"].startswith("2 dk")
    biten = _hazirla(
        baglanti,
        _olay_ekle(
            baglanti,
            kod="RESTRICTED_ENTRY",
            onem="high",
            baslangic=_utc(300),
            bitis=_utc(288),
            detay={"kapanis_sebebi": "kosul_bitti"},
        ),
    )
    assert not biten["suruyor"] and biten["sure_metni"] == "12 sn"
    assert biten["kapanis_sebebi_adi"] == "Durum sona erdi"
    anlik = _hazirla(baglanti, _olay_ekle(baglanti, kod="DISK_LOW", onem="system", tip="system"))
    assert not anlik["suruyor"] and anlik["sure_metni"] == ""


@pytest.mark.parametrize(
    ("saniye", "beklenen"),
    [
        (0, "0 sn"),
        (59.9, "59 sn"),
        (60, "1 dk"),
        (185, "3 dk 5 sn"),
        (3600, "1 sa"),
        (7810, "2 sa 10 dk"),
        (90000, "1 gün 1 sa"),
        (-5, "0 sn"),
    ],
)
def test_sure_metni(saniye, beklenen):
    assert zaman.sure_metni(saniye) == beklenen


# ------------------------------------------------------------------ sayfalar


def test_olaylar_sayfasi_onem_ve_sureci_gosterir(istemci, baglanti):
    _olay_ekle(baglanti, kod="RESTRICTED_ENTRY", onem="high", bitis=None)
    _olay_ekle(
        baglanti,
        kod="VEHICLE_PERSON_PROXIMITY",
        onem="critical",
        kural_tipi="safe_distance",
        baslangic=_utc(400),
        bitis=_utc(394),
        detay={"mesafe_m": 1.2},
    )
    sayfa = istemci.get("/olaylar").text
    assert 'class="onem-hapi onem-high">Yüksek' in sayfa
    assert 'class="onem-hapi onem-critical">Kritik' in sayfa
    assert "sürüyor · 1 dk" in sayfa
    assert "bitti · 6 sn" in sayfa


def test_onem_ve_surec_filtreleri(istemci, baglanti):
    _olay_ekle(baglanti, kod="RESTRICTED_ENTRY", onem="high", bitis=None)
    _olay_ekle(baglanti, kod="PERSON_OFF_WALKWAY", onem="medium")
    kritik_yok = istemci.get("/olaylar?onem=critical").text
    assert "Yasak alana giriş" not in kritik_yok and "Yaya yolu dışında" not in kritik_yok
    orta = istemci.get("/olaylar?onem=medium").text
    assert "Yaya yolu dışında" in orta and "Yasak alana giriş" not in orta
    suren = istemci.get("/olaylar?surec=suruyor").text
    assert "Yasak alana giriş" in suren and "Yaya yolu dışında" not in suren
    # Bilinmeyen önem değeri süzgeç kurmaz (SQL'e girmez)
    assert "Yaya yolu dışında" in istemci.get("/olaylar?onem=DROP").text


def test_csv_yeni_sutunlari_sonda(istemci, baglanti):
    _olay_ekle(
        baglanti,
        kod="RESTRICTED_ENTRY",
        onem="high",
        baslangic=_utc(100),
        bitis=_utc(88),
    )
    _olay_ekle(baglanti, kod="CAMERA_DOWN", onem="system", tip="system", bitis=None)
    metin = istemci.get("/olaylar/disa-aktar.csv").text.lstrip("\ufeff")
    satirlar = list(csv.reader(io.StringIO(metin), delimiter=";"))
    assert satirlar[0][:7] == ["Zaman", "Tip", "Kamera", "Alan", "Özet", "Durum", "Not"]
    assert satirlar[0][7:] == ["Önem", "Olay kodu", "Bitiş", "Süre (sn)"]
    kopukluk, ihlal = satirlar[1], satirlar[2]  # en yeni önce
    assert kopukluk[7:] == ["Sistem", "CAMERA_DOWN", "sürüyor", ""]
    assert ihlal[7:9] == ["Yüksek", "RESTRICTED_ENTRY"] and ihlal[10] == "12"


def test_olay_detayi_bitisi_ve_sebebi_gosterir(istemci, baglanti):
    olay_id = _olay_ekle(
        baglanti,
        kod="CAMERA_DOWN",
        onem="system",
        tip="system",
        baslangic=_utc(700),
        bitis=_utc(100),
        detay={"mesaj": "Kamera çevrimdışı: Rampa", "kapanis_sebebi": "yeniden_baslama"},
    )
    sayfa = istemci.get(f"/olaylar/{olay_id}").text
    assert "bitti · 10 dk" in sayfa
    assert "Sistem yeniden başladı; olay açık kalmıştı" in sayfa
    assert "<code>CAMERA_DOWN</code>" in sayfa


# ------------------------------------------------------------------ komuta ve canlı akış


@pytest.mark.parametrize(
    ("olay", "renk"),
    [
        ({"event_type": "violation", "status": "new", "onem": "critical"}, "kirmizi kritik"),
        ({"event_type": "violation", "status": "reviewed", "onem": "high"}, "kirmizi"),
        ({"event_type": "violation", "status": "new", "onem": "medium"}, "sari"),
        ({"event_type": "violation", "status": "new", "onem": "low"}, "notr"),
        # İncelenmiş kritik olay yine kritiktir; yanlış alarm nötr
        ({"event_type": "violation", "status": "reviewed", "onem": "critical"}, "kirmizi kritik"),
        ({"event_type": "violation", "status": "false_alarm", "onem": "critical"}, "notr"),
        ({"event_type": "system", "status": "new", "onem": "system"}, "notr"),
        # Şema 007 öncesi: eski kural (incelenmemiş kırmızı, incelenmiş sarı)
        ({"event_type": "violation", "status": "new", "onem": ""}, "kirmizi"),
        ({"event_type": "violation", "status": "reviewed", "onem": ""}, "sari"),
    ],
)
def test_komuta_satir_rengi_onemden(olay, renk):
    assert _olay_rengi(olay) == renk


def test_canli_akis_onemi_ve_seslendirilecek_adi_tasir(baglanti):
    kodlu = _hazirla(baglanti, _olay_ekle(baglanti, kod="RESTRICTED_ENTRY", onem="high"))
    yuk = akis_yuku(kodlu)
    assert (yuk["onem"], yuk["onem_adi"], yuk["kod"], yuk["kural"]) == (
        "high",
        "Yüksek",
        "RESTRICTED_ENTRY",
        "Yasak alana giriş",
    )
    eski = akis_yuku(_hazirla(baglanti, _olay_ekle(baglanti)))
    assert (eski["onem"], eski["kural"]) == ("", "Bölge ihlali")
    json.dumps(yuk)  # SSE satırına yazılabilir olmalı


def test_uyari_bandi_sinifa_yalniz_bilinen_onemi_yazar():
    """Önem değeri sınıf adına girer; bilinen liste dışındaki değer yazılmaz."""
    from pathlib import Path

    statik = Path(__file__).resolve().parents[1] / "backend" / "app" / "web" / "static"
    for dosya in ("uyari.js", "canli.js"):
        metin = (statik / dosya).read_text(encoding="utf-8")
        assert 'var ONEMLER = ["critical", "high", "medium", "low"];' in metin, dosya
        assert "ONEMLER.indexOf(veri.onem) !== -1" in metin, dosya


def test_kilavuz_onem_haplarini_ve_sureci_aciklar(istemci):
    sayfa = istemci.get("/komuta/kilavuz").text
    for onem, ad in (
        ("critical", "Kritik"),
        ("high", "Yüksek"),
        ("medium", "Orta"),
        ("low", "Düşük"),
    ):
        assert f'class="onem-hapi onem-{onem}">{ad}' in sayfa
    assert "Yalnız sürenler" in sayfa

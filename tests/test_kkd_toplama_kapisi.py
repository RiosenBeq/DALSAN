"""KKD veri toplama kapısı ve örnek sınırları (docs/17 §5.5, §5.8, §10.2; Faz 2e-1).

- Kapı varsayılan KAPALI; açmak Rev.02 onayı ister, kapatmak ister değil; her
  değişiklik PPE_COLLECTION_CHANGED yazar; yeniden başlatma gerekmez.
- Kapı kapalıyken ppe_samples'a satır eklenmez; kapatıldıktan sonraki İLK
  denemede de yazılmaz (gecikme yok).
- KKD kuralının en küçük kişi boyundan kısa kişiden ve muaf alandaki kişiden
  örnek alınmaz.
- Şemada yüz, gömme, kişi adı/sicil, iz→personel eşlemesi taşıyabilecek sütun yok.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from app import veritabani, zaman
from app.analiz.boru_hatti import KameraHatti
from app.analiz.supervizor import AnalizSupervizoru
from app.rules.parametreler import varsayilan_params
from app.rules.tipler import Bolge, Kural, Tespit

ZORUNLU = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
MUAF = [(0.6, 0.6), (0.9, 0.6), (0.9, 0.9), (0.6, 0.9)]


def _satirlar(test_ayarlari, sorgu: str) -> list[dict]:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return [dict(s) for s in baglanti.execute(sorgu)]
    finally:
        baglanti.close()


def _kapi(test_ayarlari) -> int:
    return _satirlar(test_ayarlari, "SELECT enabled FROM ppe_collection_gate")[0]["enabled"]


# ------------------------------------------------------------------ ekran ve olay


def test_kapi_varsayilan_kapali_ve_sayfanin_ustunde(istemci, test_ayarlari):
    metin = istemci.get("/kkd").text
    assert "Veri toplama: KAPALI — Rev.02 onayı bekleniyor" in metin
    assert metin.index("Veri toplama:") < metin.index("Etiketlenecek örnekler")
    assert _kapi(test_ayarlari) == 0


def test_onaysiz_acilmaz(istemci, test_ayarlari):
    yanit = istemci.post("/kkd/toplama", data={"ac": "1"}, follow_redirects=False)
    assert yanit.status_code == 400 and "Rev.02" in yanit.json()["hata"]
    assert _kapi(test_ayarlari) == 0


def test_ac_kapat_olay_yazar_yeniden_baslatmadan(istemci, test_ayarlari):
    yanit = istemci.post("/kkd/toplama", data={"ac": "1", "onay": "1"}, follow_redirects=False)
    assert yanit.status_code == 303 and _kapi(test_ayarlari) == 1
    assert "Veri toplama: AÇIK" in istemci.get("/kkd").text

    istemci.post("/kkd/toplama", data={"ac": "0"}, follow_redirects=False)
    istemci.post("/kkd/toplama", data={"ac": "0"}, follow_redirects=False)  # zaten kapalı
    assert _kapi(test_ayarlari) == 0

    olaylar = _satirlar(
        test_ayarlari,
        "SELECT details FROM events WHERE event_code = 'PPE_COLLECTION_CHANGED' ORDER BY id",
    )
    mesajlar = [json.loads(o["details"])["mesaj"] for o in olaylar]
    assert len(mesajlar) == 2, "aynı duruma geçiş olay yazmaz"
    assert mesajlar[0].startswith("KKD veri toplama açıldı (Rev.02")
    assert mesajlar[1].startswith("KKD veri toplama kapatıldı")


# ------------------------------------------------------------------ örnekleme


def _kural(**params) -> Kural:
    return Kural(
        id=1,
        kamera_id=1,
        tip="ppe_violation",
        bolge_id=1,
        hedef_siniflar=["person"],
        params={**varsayilan_params("ppe_violation"), **params},
        cooldown_s=180.0,
    )


def _kisi(ayak=(0.4, 0.5), boy_px: float = 300.0) -> Tespit:
    x, y = ayak[0] * 1000, ayak[1] * 1000
    return Tespit(sinif="person", kutu=(x - 50, y - boy_px, x + 50, y), takip_id=1, guven=0.9)


@pytest.fixture
def ornekleme(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO cameras (id, name, area, source_type, source_url, enabled, created_at, "
        "updated_at) VALUES (1, 'Hat', 'Üretim', 'rtsp', 'rtsp://a/1', 0, ?, ?)",
        (simdi, simdi),
    )
    baglanti.commit()
    supervizor = AnalizSupervizoru(test_ayarlari)
    hat = KameraHatti(1, 6)
    hat.yapilandir(
        [
            Bolge(id=1, tip="ppe_required", poligon=list(ZORUNLU)),
            Bolge(id=2, tip="ppe_exempt", poligon=list(MUAF)),
        ],
        [_kural(min_person_height_px=150)],
        None,
    )
    kare = np.full((1000, 1000, 3), 128, dtype=np.uint8)
    an = [0.0]

    def dene(*tespitler) -> None:
        an[0] += 100_000.0  # saatlik sınırın çok ötesi: her çağrı ayrı bir deneme
        supervizor._kkd_ornekle(baglanti, 1, kare, list(tespitler), hat, an[0])

    def kapi(acik: bool) -> None:
        baglanti.execute("UPDATE ppe_collection_gate SET enabled = ? WHERE id = 1", (int(acik),))
        baglanti.commit()

    def ornek_sayisi() -> int:
        return baglanti.execute("SELECT COUNT(*) FROM ppe_samples").fetchone()[0]

    try:
        yield dene, kapi, ornek_sayisi
    finally:
        baglanti.close()


def test_kapi_kapaliyken_ornek_yazilmaz(ornekleme):
    dene, _, ornek_sayisi = ornekleme
    dene(_kisi())
    assert ornek_sayisi() == 0


def test_kapi_aciginca_yazilir_kapaninca_ilk_denemede_durur(ornekleme):
    dene, kapi, ornek_sayisi = ornekleme
    kapi(True)
    dene(_kisi())
    assert ornek_sayisi() == 1
    kapi(False)
    dene(_kisi())  # kapatıldıktan sonraki İLK deneme
    assert ornek_sayisi() == 1, "kapatma gecikmesiz olmalı"


def test_kural_boyundan_kisa_kisiden_ornek_alinmaz(ornekleme):
    dene, kapi, ornek_sayisi = ornekleme
    kapi(True)
    dene(_kisi(boy_px=140))  # kuralın min_person_height_px'i 150
    assert ornek_sayisi() == 0
    dene(_kisi(boy_px=160))
    assert ornek_sayisi() == 1


def test_muaf_alandaki_kisiden_ornek_alinmaz(ornekleme):
    dene, kapi, ornek_sayisi = ornekleme
    kapi(True)
    dene(_kisi(ayak=(0.75, 0.75)))  # zorunlu alanda ama muaf köşede
    assert ornek_sayisi() == 0
    dene(_kisi(ayak=(0.3, 0.5)))
    assert ornek_sayisi() == 1


def test_kural_yokken_esik_semanin_varsayilani():
    hat = KameraHatti(1, 6)
    hat.yapilandir([], [], None)
    assert (
        hat.kkd_ornek_en_kucuk_boy() == varsayilan_params("ppe_violation")["min_person_height_px"]
    )


# ------------------------------------------------------------------ saklanmayanlar


# docs/17 §10.2: yüz kırpığı, yüz gömmesi, kişi adı/sicil, iz → personel
# eşlemesi, ses. Bunları taşıyabilecek bir sütun adı şemada bulunmamalı.
YASAK_SUTUN_PARCALARI = (
    "face",
    "embedding",
    "gomme",
    "employee",
    "personnel",
    "personel",
    "worker",
    "sicil",
    "badge",
    "tckn",
    "national_id",
    "full_name",
    "person_name",
    "audio_clip",
    "voice",
)


def test_semada_kisisel_veri_tasiyabilecek_sutun_yok(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        tablolar = [
            s["name"]
            for s in baglanti.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        sutunlar = {
            f"{tablo}.{s['name']}".lower()
            for tablo in tablolar
            for s in baglanti.execute(f"PRAGMA table_info({tablo})")
        }
    finally:
        baglanti.close()
    assert sutunlar, "şema boş okunamamalı"
    bulunan = sorted(s for s in sutunlar for p in YASAK_SUTUN_PARCALARI if p in s)
    assert bulunan == [], f"kişisel veri taşıyabilecek sütun: {bulunan}"

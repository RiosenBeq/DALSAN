"""Forklift eğitimi için saha karesi (app/egitim/forklift_verisi.py, şema 012).

Operatör, 24.09.2026: "gidip fabrikadan daha çok görüntü çekip mi yükleyeyim ve
sadece yüklesem yeter mi". Sınananlar:

- Kapı varsayılan KAPALI; kapalıyken kare saklanmaz, kapatınca ilk denemede durur.
- Araçlı kare kamera başına saatte en çok FORKLIFT_ORNEK_SAAT_LIMIT, araçsız
  kare bunun altıda biri; toplam sınır dolunca durur ve bir kez günlüğe yazar.
- Kare uzun kenarı 1280'e küçülür, öneri kutuları aynı oranla ölçeklenir.
- Etiket doğrulama: sınıf, kutu, görüntünün içine kırpma, çok küçük kutu.
- Güne göre kronolojik bölme; dışa aktarılan zip egitim/forklift'in LOCO
  düzeniyle aynı (COCO, 1 forklift, 2 pallet_jack, xywh kutular).
- Etiketsiz kare saklama süresi dolunca silinir; genel fotoğraf temizliği
  forklift klasörüne dokunmaz; imha kaydı sayıyı tutar.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import sqlite3
import zipfile
from pathlib import Path

import numpy as np
import pytest

from app import veritabani, zaman
from app.analiz.supervizor import AnalizSupervizoru
from app.egitim import forklift_verisi as fv
from app.rules.tipler import Tespit

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture
def baglanti(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO cameras (id, name, area, source_type, source_url, enabled, created_at, "
        "updated_at) VALUES (1, 'Rampa', 'Depo', 'rtsp', 'rtsp://a/1', 0, ?, ?)",
        (simdi, simdi),
    )
    baglanti.commit()
    try:
        yield baglanti
    finally:
        baglanti.close()


def _tir(x1=100.0, y1=200.0, x2=700.0, y2=900.0, guven=0.61) -> Tespit:
    return Tespit(sinif="truck", kutu=(x1, y1, x2, y2), takip_id=7, guven=guven)


def _kisi() -> Tespit:
    return Tespit(sinif="person", kutu=(10.0, 10.0, 60.0, 200.0), takip_id=1, guven=0.9)


def _kapi(baglanti, acik: bool) -> None:
    baglanti.execute("UPDATE forklift_collection_gate SET enabled = ? WHERE id = 1", (int(acik),))
    baglanti.commit()


def _sayi(baglanti) -> int:
    return baglanti.execute("SELECT COUNT(*) FROM forklift_samples").fetchone()[0]


# --------------------------------------------------------------- şema, sabitler


def test_kapi_varsayilan_kapali_ve_imha_kaydinda_sutun_var(baglanti):
    assert fv.toplama_acik_mi(baglanti) is False
    sutunlar = {s["name"] for s in baglanti.execute("PRAGMA table_info(purge_log)")}
    assert "forklift_samples_deleted" in sutunlar


def test_kapi_okunamazsa_kapali_sayilir():
    bos = sqlite3.connect(":memory:")
    bos.row_factory = sqlite3.Row
    assert fv.toplama_acik_mi(bos) is False


def test_siniflar_egitim_hattiyla_ayni():
    tanim = importlib.util.spec_from_file_location(
        "forklift_ortak_test", KOK / "egitim" / "forklift" / "ortak.py"
    )
    ortak = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(ortak)
    assert fv.SINIFLAR == tuple(ortak.EK_SINIFLAR)


# --------------------------------------------------------------- kaydetme


def test_oneriler_kisiyi_almaz():
    assert fv.oneriler([_kisi(), _tir()]) == [
        {"kutu": [100.0, 200.0, 700.0, 900.0], "sinif": "truck", "puan": 0.61}
    ]


def test_kare_kucultulur_ve_oneriler_olceklenir(baglanti, test_ayarlari):
    kare = np.zeros((1080, 1920, 3), dtype=np.uint8)
    yol = fv.kareyi_kaydet(
        baglanti, test_ayarlari.goruntu_klasoru, 1, kare, fv.oneriler([_tir(0, 0, 960, 540)])
    )
    assert yol.startswith("forklift-ornekler/")
    dosya = test_ayarlari.goruntu_klasoru / yol
    assert dosya.read_bytes()[:2] == b"\xff\xd8"  # JPEG
    satir = baglanti.execute("SELECT * FROM forklift_samples").fetchone()
    assert (satir["width"], satir["height"]) == (1280, 720)
    assert json.loads(satir["proposals"])[0]["kutu"] == [0.0, 0.0, 640.0, 360.0]
    assert satir["camera_id"] == 1 and satir["labels"] is None


def test_kucuk_kare_buyutulmez_silinmis_kamera_bos_kalir(baglanti, test_ayarlari):
    kare = np.zeros((480, 640, 3), dtype=np.uint8)
    fv.kareyi_kaydet(baglanti, test_ayarlari.goruntu_klasoru, 99, kare, [])
    satir = baglanti.execute("SELECT width, height, camera_id FROM forklift_samples").fetchone()
    assert (satir["width"], satir["height"], satir["camera_id"]) == (640, 480, None)


# --------------------------------------------------------------- örnekleme (analiz)


@pytest.fixture
def ornekleme(baglanti, test_ayarlari):
    supervizor = AnalizSupervizoru(test_ayarlari)
    kare = np.full((720, 1280, 3), 90, dtype=np.uint8)

    def dene(an: float, *tespitler) -> None:
        supervizor._forklift_ornekle(baglanti, 1, kare, list(tespitler), an)

    return supervizor, dene


def test_kapi_kapaliyken_kare_saklanmaz_kapatinca_ilk_denemede_durur(baglanti, ornekleme):
    _, dene = ornekleme
    dene(0.0, _tir())
    assert _sayi(baglanti) == 0
    _kapi(baglanti, True)
    dene(10_000.0, _tir())
    assert _sayi(baglanti) == 1
    _kapi(baglanti, False)
    dene(20_000.0, _tir())
    assert _sayi(baglanti) == 1, "kapatma gecikmesiz olmalı"


def test_aracli_kare_saatlik_sinirla_aracsiz_alti_kat_seyrek(baglanti, ornekleme, test_ayarlari):
    _, dene = ornekleme
    _kapi(baglanti, True)
    aralik = 3600.0 / test_ayarlari.forklift_ornek_saat_limit  # varsayılan 12: 300 sn
    dene(1000.0, _tir())
    dene(1000.0 + aralik - 1, _tir())  # aralık dolmadı
    assert _sayi(baglanti) == 1
    dene(1000.0 + aralik, _tir())
    assert _sayi(baglanti) == 2
    # Araçsız kare kendi sayacıyla: ilki hemen, sonraki 6 kat aralıkla
    dene(1000.0, _kisi())
    dene(1000.0 + aralik, _kisi())
    assert _sayi(baglanti) == 3
    dene(1000.0 + 6 * aralik, _kisi())
    assert _sayi(baglanti) == 4
    bos = baglanti.execute(
        "SELECT COUNT(*) FROM forklift_samples WHERE proposals = '[]'"
    ).fetchone()[0]
    assert bos == 2


def test_toplam_sinir_dolunca_durur_ve_bir_kez_yazar(
    baglanti, ornekleme, test_ayarlari, monkeypatch, caplog
):
    supervizor, dene = ornekleme
    _kapi(baglanti, True)
    monkeypatch.setattr(
        supervizor, "ayarlar", dataclasses.replace(test_ayarlari, forklift_ornek_en_cok=2)
    )
    for i in range(5):
        dene(10_000.0 * (i + 1), _tir())
    assert _sayi(baglanti) == 2
    uyarilar = [k for k in caplog.records if "sınırı doldu" in k.getMessage()]
    assert len(uyarilar) == 1


# --------------------------------------------------------------- etiket


def test_etiket_dogrulama():
    temiz = fv.etiketleri_dogrula(
        [
            {"kutu": [-5, 10, 50, 900], "sinif": "forklift"},  # görüntü dışı kırpılır
            {"kutu": [300, 300, 302, 400], "sinif": "pallet_jack"},  # 2 px: yanlış tıklama
            {"kutu": [80, 60, 20, 10], "sinif": "pallet_jack"},  # ters çizilmiş
        ],
        640,
        480,
    )
    assert temiz == [
        {"kutu": [0.0, 10.0, 50.0, 480.0], "sinif": "forklift"},
        {"kutu": [20.0, 10.0, 80.0, 60.0], "sinif": "pallet_jack"},
    ]
    assert fv.etiketleri_dogrula([], 640, 480) == [], "karede forklift yok"
    for bozuk in (
        {"kutu": [0, 0, 10, 10]},
        [{"kutu": [0, 0, 10, 10], "sinif": "truck"}],
        [{"kutu": [0, 0, 10], "sinif": "forklift"}],
        [{"kutu": ["a", 0, 10, 10], "sinif": "forklift"}],
        [{"kutu": [0, 0, 10, 10], "sinif": "forklift"}] * (fv.EN_COK_KUTU + 1),
    ):
        with pytest.raises(fv.EtiketHatasi):
            fv.etiketleri_dogrula(bozuk, 640, 480)


def _kaydet(baglanti, klasor, kac=1) -> list[int]:
    kare = np.zeros((480, 640, 3), dtype=np.uint8)
    for _ in range(kac):
        fv.kareyi_kaydet(baglanti, klasor, 1, kare, fv.oneriler([_tir(10, 10, 300, 400)]))
    return [s["id"] for s in baglanti.execute("SELECT id FROM forklift_samples ORDER BY id")]


def test_etiketle_sirayla_ilerler_ve_siler(baglanti, test_ayarlari):
    klasor = test_ayarlari.goruntu_klasoru
    ilk, ikinci, ucuncu = _kaydet(baglanti, klasor, 3)
    assert fv.sonraki_etiketsiz(baglanti) == ilk
    fv.etiketle(baglanti, ilk, [{"kutu": [10, 10, 300, 400], "sinif": "forklift"}])
    assert fv.sonraki_etiketsiz(baglanti) == ikinci
    assert fv.sonraki_etiketsiz(baglanti, sonra=ikinci) == ucuncu, "Atla"
    with pytest.raises(fv.EtiketHatasi):
        fv.etiketle(baglanti, 12345, [])
    yol = baglanti.execute("SELECT frame_path FROM forklift_samples WHERE id = ?", (ikinci,))
    dosya = klasor / yol.fetchone()[0]
    assert fv.ornek_sil(baglanti, klasor, ikinci) and not dosya.exists()
    assert fv.hepsini_sil(baglanti, klasor) == 2 and _sayi(baglanti) == 0


def test_ozet(baglanti, test_ayarlari):
    a, b, _ = _kaydet(baglanti, test_ayarlari.goruntu_klasoru, 3)
    fv.etiketle(
        baglanti,
        a,
        [
            {"kutu": [10, 10, 300, 400], "sinif": "forklift"},
            {"kutu": [400, 10, 500, 100], "sinif": "pallet_jack"},
        ],
    )
    fv.etiketle(baglanti, b, [])
    assert fv.ozet(baglanti) == {
        "toplam": 3,
        "etiketli": 2,
        "bekleyen": 1,
        "forklift_kutusu": 1,
        "transpalet_kutusu": 1,
        "forkliftsiz_kare": 1,
        "gun": 1,
    }


# --------------------------------------------------------------- bölme, dışa aktarım


def test_gun_bolmesi_kronolojik():
    assert fv.gun_bolmesi(["2026-10-01"]) == {"2026-10-01": "egitim"}
    assert fv.gun_bolmesi(["2026-10-02", "2026-10-01"]) == {
        "2026-10-01": "egitim",
        "2026-10-02": "test",
    }
    sekiz = fv.gun_bolmesi([f"2026-10-{g:02d}" for g in range(1, 9)])
    assert [sekiz[f"2026-10-{g:02d}"] for g in range(1, 9)] == ["egitim"] * 6 + ["test"] * 2


def _etiketli_kareler(baglanti, klasor) -> None:
    """Üç ayrı günün kareleri: 1. ve 2. gün eğitim, 3. gün test."""
    ids = _kaydet(baglanti, klasor, 3)
    for gun, kimlik in zip(("2026-10-01", "2026-10-02", "2026-10-03"), ids, strict=True):
        baglanti.execute(
            "UPDATE forklift_samples SET captured_at = ? WHERE id = ?",
            (f"{gun}T09:00:00+00:00", kimlik),
        )
    baglanti.commit()
    fv.etiketle(baglanti, ids[0], [{"kutu": [10, 20, 110, 220], "sinif": "forklift"}])
    fv.etiketle(baglanti, ids[1], [{"kutu": [5, 5, 55, 45], "sinif": "pallet_jack"}])
    fv.etiketle(baglanti, ids[2], [{"kutu": [100, 100, 200, 300], "sinif": "forklift"}])


def test_disa_aktarim_loco_duzeninde(baglanti, test_ayarlari, tmp_path):
    klasor = test_ayarlari.goruntu_klasoru
    _etiketli_kareler(baglanti, klasor)
    zip_yolu = tmp_path / "veri.zip"
    manifest = fv.disa_aktar(fv.etiketli_kareler(baglanti), klasor, zip_yolu)
    with zipfile.ZipFile(zip_yolu) as arsiv:
        adlar = set(arsiv.namelist())
        egitim = json.loads(arsiv.read("annotations/egitim.json"))
        test = json.loads(arsiv.read("annotations/test.json"))
        ozet_tutuyor = all(
            hashlib.sha256(arsiv.read(ad)).hexdigest() == ozet
            for ad, ozet in manifest["sha256"].items()
        )
    assert {"egitim/saha-000001.jpg", "egitim/saha-000002.jpg", "test/saha-000003.jpg"} <= adlar
    assert {"manifest.json", "BENIOKU.txt"} <= adlar
    assert egitim["categories"] == [{"id": 1, "name": "forklift"}, {"id": 2, "name": "pallet_jack"}]
    assert [g["file_name"] for g in egitim["images"]] == ["saha-000001.jpg", "saha-000002.jpg"]
    kutular = {e["image_id"]: (e["category_id"], e["bbox"]) for e in egitim["annotations"]}
    assert kutular == {1: (1, [10.0, 20.0, 100.0, 200.0]), 2: (2, [5.0, 5.0, 50.0, 40.0])}
    assert [g["gun"] for g in test["images"]] == ["2026-10-03"]
    assert ozet_tutuyor
    assert manifest["kumeler"]["egitim"]["forklift_kutusu"] == 1
    assert manifest["kumeler"]["test"]["kare"] == 1
    # tek test karesi kutulu: yanlış alarm ölçülemez; test günlerinde tek forklift
    # kutusu var. Yalnız bu ikisi söylenir.
    assert len(manifest["uyarilar"]) == 2
    assert "forkliftsiz (boş) kare yok" in manifest["uyarilar"][1]
    assert "yalnız 1 forklift kutusu var (en az 50" in manifest["uyarilar"][0]


def test_tek_gun_ve_forkliftsiz_veri_uyarilir(baglanti, test_ayarlari, tmp_path):
    (kimlik,) = _kaydet(baglanti, test_ayarlari.goruntu_klasoru, 1)
    fv.etiketle(baglanti, kimlik, [])
    manifest = fv.disa_aktar(
        fv.etiketli_kareler(baglanti), test_ayarlari.goruntu_klasoru, tmp_path / "v.zip"
    )
    assert any("Test kümesi boş" in u for u in manifest["uyarilar"])
    assert any("forklift kutusu yok" in u for u in manifest["uyarilar"])


def test_test_gunlerinde_bos_kare_yoksa_uyarilir(baglanti, test_ayarlari, tmp_path):
    """Yanlış forklift alarmının paydası kutusuz karedir: yoksa o kapı ölçülemez."""
    _etiketli_kareler(baglanti, test_ayarlari.goruntu_klasoru)  # 3. gün test, kutulu
    kareler = fv.etiketli_kareler(baglanti)
    uyarilar = fv.uyarilar(kareler, fv.gun_bolmesi(k.gun for k in kareler))
    assert any("forkliftsiz (boş) kare yok" in u for u in uyarilar)
    fv.etiketle(baglanti, kareler[-1].id, [])  # test gününün karesi: "Forklift yok"
    kareler = fv.etiketli_kareler(baglanti)
    uyarilar = fv.uyarilar(kareler, fv.gun_bolmesi(k.gun for k in kareler))
    assert not any("forkliftsiz (boş) kare yok" in u for u in uyarilar)


def test_test_gunlerinde_az_forklift_kutusu_uyarilir():
    """Forklift bulma oranı test günlerindeki kutularla ölçülür: 50'nin altı uyarılır."""

    def kare(no: int, gun: str, forklift: int) -> fv.Kare:
        return fv.Kare(
            id=no,
            kamera_id=1,
            alinma_utc=f"{gun}T09:00:00+00:00",
            gun=gun,
            dosya=f"{fv.KLASOR}/{no}.jpg",
            genislik=64,
            yukseklik=48,
            etiketler=({"kutu": [0, 0, 10, 10], "sinif": "forklift"},) * forklift,
        )

    def az_kutu_uyarisi(kareler: list[fv.Kare]) -> list[str]:
        bolme = fv.gun_bolmesi(k.gun for k in kareler)
        return [u for u in fv.uyarilar(kareler, bolme) if "forklift kutusu var (en az" in u]

    egitim = kare(1, "2026-10-01", 3)  # iki gün: 2. gün test
    (uyari,) = az_kutu_uyarisi([egitim, kare(2, "2026-10-02", fv.AZ_TEST_KUTUSU - 1)])
    assert f"yalnız {fv.AZ_TEST_KUTUSU - 1} forklift kutusu" in uyari
    assert not az_kutu_uyarisi([egitim, kare(2, "2026-10-02", fv.AZ_TEST_KUTUSU)])
    # hiç forklift yoksa "forklift kutusu yok" uyarısı yeter; ikincisi yazılmaz
    assert not az_kutu_uyarisi([kare(1, "2026-10-01", 0), kare(2, "2026-10-02", 0)])


def test_diskte_olmayan_kare_eksik_sayilir(baglanti, test_ayarlari, tmp_path):
    klasor = test_ayarlari.goruntu_klasoru
    _etiketli_kareler(baglanti, klasor)
    ilk = baglanti.execute("SELECT frame_path FROM forklift_samples ORDER BY id").fetchone()[0]
    (klasor / ilk).unlink()
    manifest = fv.disa_aktar(fv.etiketli_kareler(baglanti), klasor, tmp_path / "v.zip")
    assert manifest["eksik_dosya"] == 1 and manifest["kare_sayisi"] == 2


# --------------------------------------------------------------- saklama


def test_etiketsiz_eski_kare_silinir_etiketli_kalir(baglanti, test_ayarlari):
    klasor = test_ayarlari.goruntu_klasoru
    eski_etiketsiz, eski_etiketli, yeni = _kaydet(baglanti, klasor, 3)
    eski = zaman.gun_once_utc(40)
    baglanti.execute(
        "UPDATE forklift_samples SET captured_at = ? WHERE id IN (?, ?)",
        (eski, eski_etiketsiz, eski_etiketli),
    )
    baglanti.commit()
    fv.etiketle(baglanti, eski_etiketli, [])
    assert fv.hamlari_sil(baglanti, klasor, 30) == 1
    kalan = {s["id"] for s in baglanti.execute("SELECT id FROM forklift_samples")}
    assert kalan == {eski_etiketli, yeni}


def test_genel_fotograf_temizligi_forklift_klasorune_dokunmaz(test_ayarlari):
    import os
    import time

    klasor = test_ayarlari.goruntu_klasoru
    forklift = klasor / fv.KLASOR / "2026-01" / "a.jpg"
    olay = klasor / "2026-01" / "b.jpg"
    for dosya in (forklift, olay):
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_bytes(b"x")
        eski = time.time() - 400 * 86400
        os.utime(dosya, (eski, eski))
    supervizor = AnalizSupervizoru(test_ayarlari)
    silinen = supervizor._eski_dosyalari_sil(klasor, 90, test_ayarlari.nesne_klasoru)
    assert silinen == 1 and forklift.exists() and not olay.exists()


def test_imha_kaydi_forklift_sayisini_tutar(baglanti, test_ayarlari):
    supervizor = AnalizSupervizoru(test_ayarlari)
    supervizor._imha_kaydi_yaz(baglanti, 0, 0, 0, 0, None, 5)
    satir = baglanti.execute(
        "SELECT forklift_samples_deleted, policy FROM purge_log ORDER BY id DESC"
    ).fetchone()
    assert satir["forklift_samples_deleted"] == 5
    assert json.loads(satir["policy"])["forklift_ham_veri_gun"] == 30

"""LOCO + fabrikanın kendi verisi: egitim/forklift/veri.py `birlestir`.

Operatör, 24.09.2026: "gidip fabrikadan daha çok görüntü çekip mi yükleyeyim
ve sadece yüklesem yeter mi". Fabrika paketi burada ürünün GERÇEK dışa
aktarımıyla (backend/app/egitim/forklift_verisi.disa_aktar) üretilir; LOCO
tarafı, `hazirla` çıktısının küçük bir kopyasıdır. Böylece iki yarının
sözleşmesi (dosya adları, kategoriler, manifest, gün bölmesi) birlikte sınanır.
Ürün ortamında (torch'suz) koşar ve internete çıkmaz.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.egitim import forklift_verisi as fv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egitim" / "forklift"))

import degerlendir  # egitim/forklift/degerlendir.py
import ortak  # egitim/forklift/ortak.py
import veri  # egitim/forklift/veri.py


def _jpeg(genislik: int, yukseklik: int, ton: int = 90) -> bytes:
    kare = np.full((yukseklik, genislik, 3), ton, dtype=np.uint8)
    tamam, kodlu = cv2.imencode(".jpg", kare)
    assert tamam
    return kodlu.tobytes()


def _goruntu_ozeti(klasor: Path) -> str:
    """hazirlik.json goruntu_sha256'nın tanımı (veri._bolumu_yaz): ad sırasıyla."""
    ozet = hashlib.sha256()
    for yol in sorted(klasor.iterdir()):
        ozet.update(f"{yol.name} {hashlib.sha256(yol.read_bytes()).hexdigest()}\n".encode())
    return ozet.hexdigest()


def _sahte_loco(klasor: Path) -> Path:
    """`hazirla` çıktısının küçük kopyası: iki görüntü, forkliftli olan iki kez listeli."""
    (klasor / "egitim").mkdir(parents=True)
    (klasor / "annotations").mkdir()
    kayitlar = [
        veri.Kayit(
            dosya_adi="000001.jpg",
            genislik=128,
            yukseklik=72,
            alt_kume="subset-2",
            kaynak_yol="/dataset/subset-2/a.jpg",
            kutular=(veri.Kutu("forklift", 10.0, 10.0, 20.0, 30.0),),
        ),
        veri.Kayit(
            dosya_adi="000002.jpg",
            genislik=128,
            yukseklik=72,
            alt_kume="subset-3",
            kaynak_yol="/dataset/subset-3/b.jpg",
            kutular=(veri.Kutu("pallet_jack", 5.0, 5.0, 10.0, 10.0),),
        ),
    ]
    for kayit in kayitlar:
        (klasor / "egitim" / kayit.dosya_adi).write_bytes(_jpeg(128, 72))
    belge = veri.coco_belgesi(kayitlar, forklift_tekrar=2, bilgi={"bolum": "egitim"})
    ozet = veri._json_yaz(klasor / "annotations" / "egitim.json", belge)
    (klasor / veri.HAZIRLIK_KAYDI).write_text(
        json.dumps(
            {
                "surum": 1,
                "json_sha256": {"egitim.json": ozet},
                "goruntu_sha256": {"egitim": _goruntu_ozeti(klasor / "egitim")},
            }
        ),
        encoding="utf-8",
    )
    (klasor / veri.LISANS_DOSYASI).write_text("CC0", encoding="utf-8")
    return klasor


def _kare(no: int, gun: str, etiketler=(), kamera: int | None = 3) -> fv.Kare:
    return fv.Kare(
        id=no,
        kamera_id=kamera,
        alinma_utc=f"{gun}T09:00:00+00:00",
        gun=gun,
        dosya=f"{fv.KLASOR}/{no}.jpg",
        genislik=320,
        yukseklik=180,
        etiketler=tuple(etiketler),
    )


FORKLIFT = {"kutu": [10.0, 20.0, 110.0, 150.0], "sinif": "forklift"}
TRANSPALET = {"kutu": [200.0, 100.0, 260.0, 170.0], "sinif": "pallet_jack"}


def _saha_zip(klasor: Path, kareler: list[fv.Kare]) -> Path:
    """Ürünün kendi dışa aktarımıyla fabrika paketi (Forklift sayfasının zip'i)."""
    goruntuler = klasor / "goruntuler"
    (goruntuler / fv.KLASOR).mkdir(parents=True)
    for kare in kareler:
        (goruntuler / kare.dosya).write_bytes(_jpeg(kare.genislik, kare.yukseklik, 40 + kare.id))
    zip_yolu = klasor / "saha.zip"
    fv.disa_aktar(kareler, goruntuler, zip_yolu)
    return zip_yolu


@pytest.fixture
def ornek(tmp_path):
    """LOCO + dört günlük fabrika verisi (son gün test): 4 eğitim, 2 test karesi."""
    loco = _sahte_loco(tmp_path / "loco")
    kareler = [
        _kare(1, "2026-10-01", [FORKLIFT]),
        _kare(2, "2026-10-01", []),
        _kare(3, "2026-10-02", [FORKLIFT, TRANSPALET]),
        _kare(4, "2026-10-03", [], kamera=None),
        _kare(5, "2026-10-04", [FORKLIFT], kamera=7),
        _kare(6, "2026-10-04", []),
    ]
    return loco, _saha_zip(tmp_path, kareler)


def _oku(yol: Path) -> dict:
    return json.loads(yol.read_text(encoding="utf-8"))


def test_birlestirme_duzeni_tekrar_ve_kayit(ornek, tmp_path, capsys):
    loco, saha = ornek
    hedef = tmp_path / "birlesik"
    rapor = veri.birlestir(loco, saha, hedef, saha_tekrar=3)

    egitim = _oku(hedef / "annotations" / "egitim.json")
    # LOCO: 2 görüntü + forkliftlinin 1 tekrarı; fabrika: 4 eğitim karesi x 3
    assert len(egitim["images"]) == 3 + 4 * 3
    assert [g["id"] for g in egitim["images"]] == list(range(1, 16))
    kimlikler = {g["id"]: g for g in egitim["images"]}
    for giris in egitim["images"]:
        if "asil_id" in giris:
            asil = kimlikler[giris["asil_id"]]
            assert asil["file_name"] == giris["file_name"] and "asil_id" not in asil
    saha_girdileri = [g for g in egitim["images"] if g["alt_kume"] == "saha"]
    assert len(saha_girdileri) == 12
    assert {g["file_name"] for g in saha_girdileri} == {f"saha-{no:06d}.jpg" for no in (1, 2, 3, 4)}
    # etiketler yeni kimliklere bağlı: forklift = LOCO 2 kayıt + fabrika (1 + 1) x 3
    sayim = {"forklift": 0, "pallet_jack": 0}
    for etiket in egitim["annotations"]:
        assert etiket["image_id"] in kimlikler
        sayim[{1: "forklift", 2: "pallet_jack"}[etiket["category_id"]]] += 1
    assert sayim == {"forklift": 2 + 2 * 3, "pallet_jack": 1 + 1 * 3}
    assert egitim["categories"] == [{"id": 1, "name": "forklift"}, {"id": 2, "name": "pallet_jack"}]

    test = _oku(hedef / "annotations" / "test.json")
    assert [g["file_name"] for g in test["images"]] == ["saha-000005.jpg", "saha-000006.jpg"]
    assert [g["alt_kume"] for g in test["images"]] == ["kamera-7", "kamera-3"]
    assert test["info"]["kaynak"] == "saha"

    assert sorted(p.name for p in (hedef / "egitim").iterdir()) == [
        "000001.jpg",
        "000002.jpg",
        *(f"saha-{no:06d}.jpg" for no in (1, 2, 3, 4)),
    ]
    assert sorted(p.name for p in (hedef / "test").iterdir()) == [
        "saha-000005.jpg",
        "saha-000006.jpg",
    ]
    # LOCO görüntüsü kopyalanmadı, bağlandı (aynı disk)
    assert (hedef / "egitim" / "000001.jpg").stat().st_ino == (
        loco / "egitim" / "000001.jpg"
    ).stat().st_ino
    assert rapor["loco_goruntu_baglantisi"] == {"sabit_baglanti": 2, "kopya": 0}

    kayit = _oku(hedef / veri.BIRLESTIRME_KAYDI)
    assert kayit == rapor
    assert kayit["saha"]["egitim"] == {"kare": 4, "kutu": {"forklift": 2, "pallet_jack": 1}}
    assert kayit["saha"]["test"] == {"kare": 2, "kutu": {"forklift": 1, "pallet_jack": 0}}
    for ad, ozet in kayit["json_sha256"].items():
        assert hashlib.sha256((hedef / "annotations" / ad).read_bytes()).hexdigest() == ozet
    assert any("yalnız 1 forklift kutusu" in u for u in kayit["uyarilar"])
    assert "KVKK" in (hedef / veri.SAHA_BENIOKU).read_text(encoding="utf-8")
    assert (hedef / veri.LISANS_DOSYASI).is_file()
    assert "BIRLESTIRME_OZETI" in capsys.readouterr().out
    assert not list(tmp_path.glob(".birlesik-birlestirme-*")), "geçici klasör kalmadı"


def test_olcum_betigi_fabrika_testini_okur(ornek, tmp_path):
    loco, saha = ornek
    hedef = tmp_path / "birlesik"
    veri.birlestir(loco, saha, hedef)
    goruntuler = degerlendir.olcum_setini_oku(hedef)
    assert [(g.yol.name, g.alt_kume, len(g.forkliftler)) for g in goruntuler] == [
        ("saha-000005.jpg", "kamera-7", 1),
        ("saha-000006.jpg", "kamera-3", 0),
    ]
    # xyxy ölçümde, xywh COCO'da: 10,20 - 110,150
    assert goruntuler[0].forkliftler == ((10.0, 20.0, 110.0, 150.0),)


def test_acilmis_klasor_de_kabul_edilir(ornek, tmp_path):
    loco, saha = ornek
    klasor = tmp_path / "acilmis"
    with zipfile.ZipFile(saha) as arsiv:
        arsiv.extractall(klasor)
    rapor = veri.birlestir(loco, klasor, tmp_path / "birlesik", saha_tekrar=1)
    assert rapor["egitim_goruntu_kaydi"] == 3 + 4


def _json_degistir(klasor: Path, ad: str, degistir) -> None:
    """Açılmış paketteki bir JSON'u değiştirir ve manifest'teki özetini günceller:
    böylece özetten sonraki denetim sınanır."""
    yol = klasor / ad
    belge = json.loads(yol.read_text(encoding="utf-8"))
    degistir(belge)
    yol.write_text(json.dumps(belge), encoding="utf-8")
    manifest_yolu = klasor / veri.SAHA_MANIFESTI
    manifest = json.loads(manifest_yolu.read_text(encoding="utf-8"))
    manifest["sha256"][ad] = hashlib.sha256(yol.read_bytes()).hexdigest()
    manifest_yolu.write_text(json.dumps(manifest), encoding="utf-8")


def _test_gunune_egitim_gunu_koy(belge: dict) -> None:
    belge["images"][0]["gun"] = "2026-10-01"


def _ad_klasor_disina(belge: dict) -> None:
    belge["images"][0]["file_name"] = "../../disari.jpg"


def _kutu_tasiyor(belge: dict) -> None:
    belge["annotations"][0]["bbox"] = [300.0, 20.0, 100.0, 50.0]


def _kategori_farkli(belge: dict) -> None:
    belge["categories"] = [{"id": 1, "name": "truck"}, {"id": 2, "name": "pallet_jack"}]


@pytest.mark.parametrize(
    ("ad", "degistir", "ileti"),
    [
        ("annotations/test.json", _test_gunune_egitim_gunu_koy, "hem eğitimde hem testte"),
        ("annotations/test.json", _ad_klasor_disina, "dosya adı geçersiz"),
        ("annotations/egitim.json", _kutu_tasiyor, "geçersiz kutu"),
        ("annotations/egitim.json", _kategori_farkli, "kategorileri beklenmedik"),
    ],
)
def test_tutarsiz_paket_reddedilir_ve_yarim_klasor_kalmaz(
    ornek, tmp_path, capsys, ad, degistir, ileti
):
    loco, saha = ornek
    klasor = tmp_path / "acilmis"
    with zipfile.ZipFile(saha) as arsiv:
        arsiv.extractall(klasor)
    _json_degistir(klasor, ad, degistir)
    hedef = tmp_path / "birlesik"
    kod = veri.main(
        ["birlestir", "--loco", str(loco), "--saha", str(klasor), "--hedef", str(hedef)]
    )
    assert kod == 2
    assert ileti in capsys.readouterr().err
    assert not hedef.exists() and not list(tmp_path.glob(".birlesik-birlestirme-*"))


def test_ozet_tutmayan_goruntu_ve_json_reddedilir(ornek, tmp_path):
    loco, saha = ornek
    klasor = tmp_path / "acilmis"
    with zipfile.ZipFile(saha) as arsiv:
        arsiv.extractall(klasor)
    (klasor / "egitim" / "saha-000003.jpg").write_bytes(_jpeg(320, 180, 7))
    with pytest.raises(veri.ButunlukHatasi, match="saha-000003.jpg manifest'teki özetle"):
        veri.birlestir(loco, klasor, tmp_path / "birlesik")
    assert not (tmp_path / "birlesik").exists()

    with zipfile.ZipFile(saha) as arsiv:
        arsiv.extractall(klasor)  # görüntüyü geri getirir
    (klasor / "annotations" / "test.json").write_text("{}", encoding="utf-8")
    with pytest.raises(veri.ButunlukHatasi, match="test.json manifest'teki özetle tutmuyor"):
        veri.birlestir(loco, klasor, tmp_path / "birlesik")


def test_paket_ve_loco_girdi_hatalari(ornek, tmp_path):
    loco, saha = ornek
    with pytest.raises(veri.ButunlukHatasi, match="bulunamadı"):
        veri.birlestir(loco, tmp_path / "yok.zip", tmp_path / "b1")
    bozuk = tmp_path / "bozuk.zip"
    bozuk.write_bytes(b"zip degil")
    with pytest.raises(veri.ButunlukHatasi, match="zip olarak açılamadı"):
        veri.birlestir(loco, bozuk, tmp_path / "b2")

    klasor = tmp_path / "acilmis"
    with zipfile.ZipFile(saha) as arsiv:
        arsiv.extractall(klasor)
    manifest = json.loads((klasor / veri.SAHA_MANIFESTI).read_text(encoding="utf-8"))
    manifest["surum"] = 99
    (klasor / veri.SAHA_MANIFESTI).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(veri.ButunlukHatasi, match="paket sürümü 99"):
        veri.birlestir(loco, klasor, tmp_path / "b3")

    dolu = tmp_path / "dolu"
    dolu.mkdir()
    (dolu / "eski.txt").write_text("x", encoding="utf-8")
    with pytest.raises(veri.ButunlukHatasi, match="boş değil"):
        veri.birlestir(loco, saha, dolu)

    (loco / "annotations" / "egitim.json").write_text("{}", encoding="utf-8")
    with pytest.raises(veri.ButunlukHatasi, match="hazırlık kaydındaki özetle tutmuyor"):
        veri.birlestir(loco, saha, tmp_path / "b4")
    with pytest.raises(veri.ButunlukHatasi, match="hazirla"):
        veri.birlestir(tmp_path / "loco-yok", saha, tmp_path / "b5")


def test_tek_gunluk_paket_uyarir(tmp_path):
    loco = _sahte_loco(tmp_path / "loco")
    saha = _saha_zip(tmp_path, [_kare(1, "2026-10-01", [FORKLIFT]), _kare(2, "2026-10-01")])
    rapor = veri.birlestir(loco, saha, tmp_path / "birlesik")
    assert rapor["saha"]["test"]["kare"] == 0
    assert any("Fabrika test günü yok" in u for u in rapor["uyarilar"])
    assert any("Test kümesi boş" in u for u in rapor["uyarilar"]), "paketin kendi uyarısı da"


def test_saha_paketi_sozlesmesi_uygulamayla_ayni():
    """Uygulamanın yazdığı paket, eğitim betiğinin beklediğiyle aynı sözleşmede."""
    assert fv.MANIFEST_SURUMU == veri.SAHA_MANIFEST_SURUMU
    assert fv.SINIFLAR == ortak.EK_SINIFLAR
    assert veri._SAHA_DOSYA_ADI.fullmatch(_kare(123456789, "2026-10-01").cikti_adi)
    assert veri._SAHA_DOSYA_ADI.fullmatch(_kare(7, "2026-10-01").cikti_adi)
    varsayilan = veri._ayristirici().parse_args(["hazirla", "--kaynak", "a", "--hedef", "b"])
    assert fv.EN_UZUN_KENAR == varsayilan.en_uzun_kenar


def test_birlesik_belge_saf_islev():
    loco = {
        "images": [
            {"id": 10, "file_name": "000001.jpg", "width": 8, "height": 8},
            {"id": 11, "file_name": "000001.jpg", "width": 8, "height": 8, "asil_id": 10},
        ],
        "annotations": [
            {"id": 1, "image_id": 10, "category_id": 1, "bbox": [0, 0, 4, 4]},
            {"id": 2, "image_id": 11, "category_id": 1, "bbox": [0, 0, 4, 4]},
        ],
        "categories": [dict(k) for k in veri.KATEGORILER],
    }
    saha = {
        "images": [{"id": 1, "file_name": "saha-000001.jpg", "width": 8, "height": 8}],
        "annotations": [],
        "categories": [dict(k) for k in veri.KATEGORILER],
    }
    belge = veri.birlesik_egitim_belgesi(loco, saha, saha_tekrar=2)
    assert [(g["id"], g.get("asil_id")) for g in belge["images"]] == [
        (1, None),
        (2, 1),
        (3, None),
        (4, 3),
    ]
    assert [e["image_id"] for e in belge["annotations"]] == [1, 2]
    with pytest.raises(ValueError):
        veri.birlesik_egitim_belgesi(loco, saha, saha_tekrar=0)
    ters = dict(loco, images=list(reversed(loco["images"])))
    with pytest.raises(veri.ButunlukHatasi, match="asılından önce"):
        veri.birlesik_egitim_belgesi(ters, saha)


def test_bozuk_ya_da_eksik_loco_goruntusu_reddedilir(ornek, tmp_path):
    """Eğitimde saatler sonra "file not found" yerine birleştirmede, hemen."""
    loco, saha = ornek
    (loco / "egitim" / "000002.jpg").write_bytes(b"bozuk dosya")
    with pytest.raises(veri.LocoBozukHatasi, match="hazırlık kaydıyla tutmuyor"):
        veri.birlestir(loco, saha, tmp_path / "b1")
    (loco / "egitim" / "000002.jpg").unlink()
    with pytest.raises(veri.LocoBozukHatasi, match="okunamadı"):
        veri.birlestir(loco, saha, tmp_path / "b2")
    assert not (tmp_path / "b1").exists() and not (tmp_path / "b2").exists()


def test_test_gunlerinde_bos_kare_yoksa_uyarir(tmp_path):
    loco = _sahte_loco(tmp_path / "loco")
    saha = _saha_zip(
        tmp_path,
        [_kare(1, "2026-10-01", [FORKLIFT]), _kare(2, "2026-10-02", [FORKLIFT, TRANSPALET])],
    )
    rapor = veri.birlestir(loco, saha, tmp_path / "birlesik")
    bos = [u for u in rapor["uyarilar"] if "forkliftsiz (boş) kare yok" in u]
    assert len(bos) == 1, "paketin uyarısı varken ikinci kez yazılmaz"

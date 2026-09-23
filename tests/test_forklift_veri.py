"""Forklift eğitim verisi: egitim/forklift/veri.py (docs/17 §12.3).

Ürün ortamında (torch'suz) koşar ve internete çıkmaz. Sahte LOCO: gerçek
etiket dosyasının biçiminde küçük bir JSON ve JPEG'lerden bir zip tmp_path'e
yazılır; üyeler gerçek arşivdeki adlarla durur (dataset/subset-N/...).
İndirici yerel bir http.server'a karşı sınanır: yönlendirme, HTML sayfası,
zip olmayan içerik, yanlış özet, kopan bağlantıdan kaldığı yerden devam.
"""

from __future__ import annotations

import hashlib
import http.server
import io
import json
import sys
import threading
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egitim" / "forklift"))

import veri  # egitim/forklift/veri.py

LOCO_KATEGORILERI = [
    {"id": 3, "name": "small_load_carrier", "supercategory": ""},
    {"id": 5, "name": "forklift", "supercategory": ""},
    {"id": 7, "name": "pallet", "supercategory": ""},
    {"id": 10, "name": "stillage", "supercategory": ""},
    {"id": 11, "name": "pallet_truck", "supercategory": ""},
]
LOCO_KIMLIGI = {k["name"]: k["id"] for k in LOCO_KATEGORILERI}

# Dört alt küme: 2 ve 3 eğitim, 1 ve 4 test. Virgüllü ve derinliği farklı yollar
# gerçek JSON'dan örnek alındı. --en-uzun-kenar 128 ile 192x108 -> 128x72 (2/3).
ORNEK = [
    {
        "yol": "/dataset/subset-2/2019-12-17_10/Cam1/a.jpg",
        "w": 192,
        "h": 108,
        "kutular": [("forklift", [96, 54, 19.2, 10.8]), ("pallet", [0, 0, 10, 10])],
    },
    {
        "yol": "/dataset/subset-2/2019-12-17_10/Cam1/b.jpg",
        "w": 192,
        "h": 108,
        # 1 piksel genişliğindeki forklift kutusu atılır
        "kutular": [("pallet_truck", [30, 30, 60, 30]), ("forklift", [5, 5, 1, 20])],
    },
    {
        "yol": "/dataset/subset-3/2019-12-18_09/Kinect/color/3402166,3564.jpg",
        "w": 64,
        "h": 48,
        "kutular": [("forklift", [10, 10, 20, 20]), ("forklift", [30, 20, 10, 10])],
    },
    {"yol": "/dataset/subset-3/2019-12-18_09/cam2/c.jpg", "w": 64, "h": 48, "kutular": []},
    {
        "yol": "/dataset/subset-1/1564565315.0281892.jpg",
        "w": 64,
        "h": 48,
        "kutular": [("pallet_truck", [1, 2, 3, 4])],
    },
    {
        "yol": "/dataset/subset-4/2020-01-16_16/RealSense/color/0/1579166141001,7.jpg",
        "w": 192,
        "h": 108,
        "kutular": [("forklift", [0, 0, 96, 54]), ("stillage", [100, 50, 20, 20])],
    },
    {"yol": "/dataset/subset-4/2020-01-16_17/cam2/d.jpg", "w": 64, "h": 48, "kutular": []},
]


def _sha(veri_: bytes) -> str:
    return hashlib.sha256(veri_).hexdigest()


def _jpeg(genislik: int, yukseklik: int, kutular=()) -> bytes:
    """Siyah zemin üstünde beyaz dolu kutular: kutuların yeri pikselden okunur."""
    resim = np.zeros((yukseklik, genislik, 3), np.uint8)
    for _, (x, y, w, h) in kutular:
        bas = (round(x), round(y))
        son = (round(x + w) - 1, round(y + h) - 1)
        cv2.rectangle(resim, bas, son, (255, 255, 255), -1)
    tamam, kodlu = cv2.imencode(".jpg", resim, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert tamam
    return kodlu.tobytes()


def _sahte_loco(klasor: Path, goruntuler: list[dict], *, onek: str = "dataset/") -> Path:
    """Gerçek LOCO biçiminde klasor/loco-all-v1.json ve klasor/loco.zip yazar.

    Görüntü sözlüğü: yol, w, h, kutular [(LOCO sınıfı, [x, y, w, h])]. İsteğe
    bağlı: "arsivde": False (zip'e girmez), "bozuk": True (JPEG değil),
    "arsiv_boyutu": (w, h) (arşivdeki JPEG JSON'dakinden farklı boyutta).
    Zip üyeleri gerçek arşivdeki gibi saklanır (sıkıştırmasız).
    """
    klasor.mkdir(parents=True, exist_ok=True)
    images: list[dict] = []
    annotations: list[dict] = []
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_STORED) as arsiv:
        if onek:
            arsiv.writestr(onek, b"")  # klasör girdisi
        for no, goruntu in enumerate(goruntuler):
            kimlik = 31834 + no
            images.append(
                {
                    "id": kimlik,
                    "dataset_id": 32,
                    "path": goruntu["yol"],
                    "width": goruntu["w"],
                    "height": goruntu["h"],
                    "file_name": goruntu["yol"].rsplit("/", 1)[-1],
                }
            )
            for sinif, kutu in goruntu["kutular"]:
                annotations.append(
                    {
                        "id": 387068 + len(annotations),
                        "image_id": kimlik,
                        "category_id": LOCO_KIMLIGI[sinif],
                        "segmentation": [],
                        "area": kutu[2] * kutu[3],
                        "bbox": list(kutu),
                        "iscrowd": False,
                        "isbbox": True,
                        "color": "#f8c718",
                        "metadata": {},
                    }
                )
            if not goruntu.get("arsivde", True):
                continue
            if goruntu.get("bozuk"):
                icerik = b"bu bir JPEG degil"
            else:
                w, h = goruntu.get("arsiv_boyutu", (goruntu["w"], goruntu["h"]))
                oran = w / goruntu["w"]
                kutular = [(s, [v * oran for v in k]) for s, k in goruntu["kutular"]]
                icerik = _jpeg(w, h, kutular)
            arsiv.writestr(onek + goruntu["yol"].removeprefix("/dataset/"), icerik)
    (klasor / "loco.zip").write_bytes(tampon.getvalue())
    belge = {"images": images, "categories": LOCO_KATEGORILERI, "annotations": annotations}
    (klasor / "loco-all-v1.json").write_text(json.dumps(belge), encoding="utf-8")
    return klasor


def _hazirla(kaynak: Path, hedef: Path, *ek: str) -> int:
    return veri.main(
        ["hazirla", "--kaynak", str(kaynak), "--hedef", str(hedef), "--en-uzun-kenar", "128", *ek]
    )


def _oku(yol: Path) -> dict:
    return json.loads(yol.read_text(encoding="utf-8"))


def _duz_goruntuler(adet: int, alt_kume: str = "subset-2") -> list[dict]:
    return [
        {"yol": f"/dataset/{alt_kume}/cam/{no:03d}.jpg", "w": 16, "h": 12, "kutular": []}
        for no in range(adet)
    ]


# ---------------------------------------------------------------------------
# Saf işlevler
# ---------------------------------------------------------------------------


def test_alt_kume_yoldan_okunur():
    assert veri.alt_kume_bul("/dataset/subset-3/2019-12-17_10/Cam1/x.jpg") == "subset-3"
    assert veri.alt_kume_bul("/dataset/subset-1/1564565315.0281892.jpg") == "subset-1"
    assert veri.alt_kume_bul("/dataset/subset-4/a/RealSense/color/0/15791,7.jpg") == "subset-4"
    for bozuk in ("dataset/subset-1/x.jpg", "/dataset/x.jpg", "/dataset//x/y.jpg", ""):
        with pytest.raises(veri.ButunlukHatasi):
            veri.alt_kume_bul(bozuk)


def test_zip_uyesi_tam_addan_ya_da_sonekten_bulunur():
    dizin = veri.uye_dizini(
        [
            "dataset/",
            "dataset/subset-1/a.jpg",
            "LOCO/v1/dataset/subset-2/b,1.jpg",
            "x\\subset-3\\c.jpg",
            "subset-4/d.jpg",
            "b/c/dataset/subset-5/e.jpg",
            "a/dataset/subset-5/e.jpg",
            "baska/xsubset-1/f.jpg",
        ]
    )
    assert veri.uye_bul(dizin, "/dataset/subset-1/a.jpg") == "dataset/subset-1/a.jpg"
    assert veri.uye_bul(dizin, "/dataset/subset-2/b,1.jpg") == "LOCO/v1/dataset/subset-2/b,1.jpg"
    assert veri.uye_bul(dizin, "/dataset/subset-3/c.jpg") == "x\\subset-3\\c.jpg"
    assert veri.uye_bul(dizin, "/dataset/subset-4/d.jpg") == "subset-4/d.jpg"
    # Aynı sonekli iki üye: en kısa ad (arşiv sırasından bağımsız), ama sessiz
    # değil: ikisi de cakisan_uyeler'de (hazirla içerikleri farklıysa durur)
    assert veri.uye_bul(dizin, "/dataset/subset-5/e.jpg") == "a/dataset/subset-5/e.jpg"
    assert veri.cakisan_uyeler(dizin, "/dataset/subset-5/e.jpg") == (
        "a/dataset/subset-5/e.jpg",
        "b/c/dataset/subset-5/e.jpg",
    )
    # Tek üyeye uyan ve tam adla bulunan yol belirsiz değildir
    assert veri.cakisan_uyeler(dizin, "/dataset/subset-2/b,1.jpg") == ()
    assert veri.cakisan_uyeler(dizin, "/dataset/subset-1/a.jpg") == ()
    # Sonek yalnız "/" sınırında eşleşir; klasör girdisi üye değildir
    assert veri.uye_bul(dizin, "/dataset/subset-1/f.jpg") is None
    assert veri.uye_bul(dizin, "/dataset/subset-9/a.jpg") is None
    # Denetçinin örneği: önizleme ağacı daha kısa adlı olduğu için seçilirdi
    onizleme = veri.uye_dizini(["LOCO/v1/dataset/subset-2/a/x.jpg", "prv/subset-2/a/x.jpg"])
    assert veri.cakisan_uyeler(onizleme, "/dataset/subset-2/a/x.jpg") == (
        "LOCO/v1/dataset/subset-2/a/x.jpg",
        "prv/subset-2/a/x.jpg",
    )


def test_loco_siniflari_eslenir_kucuk_ve_baska_kutular_atilir():
    belge = {
        "categories": LOCO_KATEGORILERI,
        "images": [
            {"id": 7, "path": "/dataset/subset-2/c/a.jpg", "width": 640, "height": 480},
            {"id": 9, "path": "/dataset/subset-4/c/b.jpg", "width": 640, "height": 480},
        ],
        "annotations": [
            {"image_id": 7, "category_id": 5, "bbox": [1, 2, 30, 40]},
            {"image_id": 7, "category_id": 11, "bbox": [5, 6, 7, 8]},
            {"image_id": 7, "category_id": 7, "bbox": [5, 6, 70, 80]},  # palet: atılır
            {"image_id": 7, "category_id": 5, "bbox": [5, 6, 1, 80]},  # 1 px: atılır
            {"image_id": 9, "category_id": 11, "bbox": [5, 6, 50, 0.5]},  # 0,5 px: atılır
        ],
    }
    goruntuler, atilan = veri.loco_goruntuleri(belge)
    assert [g.alt_kume for g in goruntuler] == ["subset-2", "subset-4"]
    assert goruntuler[0].kutular == (
        veri.Kutu("forklift", 1.0, 2.0, 30.0, 40.0),
        veri.Kutu("pallet_jack", 5.0, 6.0, 7.0, 8.0),
    )
    assert goruntuler[0].forklift_var and goruntuler[1].kutular == ()
    assert atilan == {"baska_sinif": 1, "kucuk_kutu": 2}
    with pytest.raises(veri.ButunlukHatasi):
        veri.loco_goruntuleri({"images": [], "annotations": []})


def test_olcek_kucultur_buyutmez_ve_en_boy_oranini_denetler():
    assert veri.olcek_hesapla(1920, 1080, 1920, 1080, 1280) == (1280, 720, 2 / 3, 2 / 3)
    assert veri.olcek_hesapla(640, 480, 640, 480, 1280) == (640, 480, 1.0, 1.0)
    assert veri.olcek_hesapla(1280, 960, 1280, 960, 1280) == (1280, 960, 1.0, 1.0)
    # Arşivdeki görüntü aynı oranda ama küçükse kutular yine doğru yere düşer
    assert veri.olcek_hesapla(1920, 1080, 960, 540, 1280) == (960, 540, 0.5, 0.5)
    with pytest.raises(veri.GoruntuHatasi):
        veri.olcek_hesapla(1280, 720, 640, 480, 1280)
    kutu = veri.Kutu("forklift", 960, 540, 192, 108)
    assert veri.kutulari_olcekle([kutu], 2 / 3, 2 / 3) == (
        veri.Kutu("forklift", 640.0, 360.0, 128.0, 72.0),
    )


def test_coco_belgesi_forklift_goruntulerini_tekrarlar():
    fk = veri.Kutu("forklift", 1.0, 2.0, 3.0, 4.0)
    pj = veri.Kutu("pallet_jack", 5.0, 6.0, 7.0, 8.0)
    kayitlar = [
        veri.Kayit("000001.jpg", 64, 48, "subset-2", "/dataset/subset-2/a.jpg", (fk, pj)),
        veri.Kayit("000002.jpg", 64, 48, "subset-2", "/dataset/subset-2/b.jpg", (pj,)),
        veri.Kayit("000003.jpg", 64, 48, "subset-3", "/dataset/subset-3/c.jpg", ()),
    ]
    belge = veri.coco_belgesi(kayitlar, forklift_tekrar=3)
    assert belge["categories"] == [{"id": 1, "name": "forklift"}, {"id": 2, "name": "pallet_jack"}]
    assert [g["id"] for g in belge["images"]] == [1, 2, 3, 4, 5]
    assert [g["file_name"] for g in belge["images"]][3:] == ["000001.jpg", "000001.jpg"]
    assert [g.get("asil_id") for g in belge["images"]] == [None, None, None, 1, 1]
    etiketler = belge["annotations"]
    assert [e["id"] for e in etiketler] == [1, 2, 3, 4, 5, 6, 7]
    assert [(e["image_id"], e["category_id"]) for e in etiketler] == [
        (1, 1),
        (1, 2),
        (2, 2),
        (4, 1),
        (4, 2),
        (5, 1),
        (5, 2),
    ]
    assert etiketler[0] == {
        "id": 1,
        "image_id": 1,
        "category_id": 1,
        "bbox": [1.0, 2.0, 3.0, 4.0],
        "area": 12.0,
        "iscrowd": 0,
    }
    tekrarsiz = veri.coco_belgesi(kayitlar)
    assert len(tekrarsiz["images"]) == 3 and len(tekrarsiz["annotations"]) == 3
    assert tekrarsiz["images"][0]["alt_kume"] == "subset-2"
    assert tekrarsiz["images"][0]["kaynak_yol"] == "/dataset/subset-2/a.jpg"


def test_sinir_once_forkliftli_goruntuleri_alir_ve_kararlidir():
    fk = (veri.Kutu("forklift", 1, 1, 5, 5),)
    goruntuler = [
        veri.LocoGoruntu(f"/dataset/{alt}/c/{no}.jpg", alt, 64, 48, fk if no == 3 else ())
        for alt in ("subset-3", "subset-2")
        for no in (3, 2, 1, 0)
    ]
    secilen = veri.sinirla(goruntuler, 2)
    assert [g.yol for g in secilen] == [
        "/dataset/subset-2/c/0.jpg",
        "/dataset/subset-2/c/3.jpg",
        "/dataset/subset-3/c/0.jpg",
        "/dataset/subset-3/c/3.jpg",
    ]
    assert veri.sinirla(list(reversed(goruntuler)), 2) == secilen
    assert [g.yol for g in veri.sinirla(goruntuler, None)] == sorted(g.yol for g in goruntuler)


# ---------------------------------------------------------------------------
# hazirla
# ---------------------------------------------------------------------------


def test_hazirla_bolme_tekrar_olcekleme_ve_kayit(tmp_path, capsys):
    kaynak = _sahte_loco(tmp_path / "ham", ORNEK)
    (kaynak / "LICENSE").write_text("CC0 1.0 Universal\n", encoding="utf-8")
    hedef = tmp_path / "veri-seti"
    assert _hazirla(kaynak, hedef) == 0

    egitim = _oku(hedef / "annotations" / "egitim.json")
    test = _oku(hedef / "annotations" / "test.json")
    assert sorted(p.name for p in (hedef / "egitim").iterdir()) == [
        f"{no:06d}.jpg" for no in range(1, 5)
    ]
    assert sorted(p.name for p in (hedef / "test").iterdir()) == [
        f"{no:06d}.jpg" for no in range(1, 4)
    ]
    assert egitim["categories"] == [{"id": 1, "name": "forklift"}, {"id": 2, "name": "pallet_jack"}]
    # Eğitim: subset-2 ve 3, yol sırasıyla; forklift içeren 1 ve 3 toplam 3 kez
    assert [(g["id"], g["file_name"], g["alt_kume"]) for g in egitim["images"]] == [
        (1, "000001.jpg", "subset-2"),
        (2, "000002.jpg", "subset-2"),
        (3, "000003.jpg", "subset-3"),
        (4, "000004.jpg", "subset-3"),
        (5, "000001.jpg", "subset-2"),
        (6, "000003.jpg", "subset-3"),
        (7, "000001.jpg", "subset-2"),
        (8, "000003.jpg", "subset-3"),
    ]
    assert egitim["images"][0]["kaynak_yol"] == ORNEK[0]["yol"]
    assert (egitim["images"][0]["width"], egitim["images"][0]["height"]) == (128, 72)
    assert (egitim["images"][2]["width"], egitim["images"][2]["height"]) == (64, 48)
    kutular = {}
    for etiket in egitim["annotations"]:
        kutular.setdefault(etiket["image_id"], []).append((etiket["category_id"], etiket["bbox"]))
    assert kutular[1] == [(1, [64.0, 36.0, 12.8, 7.2])]  # 2/3 ölçek, palet atıldı
    assert kutular[2] == [(2, [20.0, 20.0, 40.0, 20.0])]  # 1 px forklift atıldı
    assert kutular[3] == [(1, [10.0, 10.0, 20.0, 20.0]), (1, [30.0, 20.0, 10.0, 10.0])]
    assert 4 not in kutular
    assert kutular[5] == kutular[7] == kutular[1] and kutular[6] == kutular[8] == kutular[3]
    assert len({e["id"] for e in egitim["annotations"]}) == len(egitim["annotations"]) == 10
    assert all(e["iscrowd"] == 0 and e["area"] > 0 for e in egitim["annotations"])

    # Test: subset-1 ve 4, tekrarsız, alt küme ve kaynak yolu görüntüde
    assert [(g["alt_kume"], g["kaynak_yol"]) for g in test["images"]] == [
        ("subset-1", ORNEK[4]["yol"]),
        ("subset-4", ORNEK[5]["yol"]),
        ("subset-4", ORNEK[6]["yol"]),
    ]
    assert [(e["image_id"], e["category_id"], e["bbox"]) for e in test["annotations"]] == [
        (1, 2, [1.0, 2.0, 3.0, 4.0]),
        (2, 1, [0.0, 0.0, 64.0, 36.0]),
    ]

    # Kutular yazılan görüntüde gerçekten o piksellerde (beyaz kutu, siyah zemin)
    ilk = cv2.imread(str(hedef / "egitim" / "000001.jpg"))
    assert ilk.shape == (72, 128, 3)
    assert ilk[39, 70].min() > 200 and ilk[68, 124].max() < 50
    kinect = cv2.imread(str(hedef / "egitim" / "000003.jpg"))
    assert kinect[20, 20].min() > 200 and kinect[25, 35].min() > 200 and kinect[5, 60].max() < 50
    realsense = cv2.imread(str(hedef / "test" / "000002.jpg"))
    assert realsense[18, 32].min() > 200 and realsense[60, 100].max() < 50

    hazirlik = _oku(hedef / "hazirlik.json")
    egitim_ham = (hedef / "annotations" / "egitim.json").read_bytes()
    test_ham = (hedef / "annotations" / "test.json").read_bytes()
    assert hazirlik["json_sha256"] == {"egitim.json": _sha(egitim_ham), "test.json": _sha(test_ham)}
    assert egitim_ham.isascii() and test_ham.isascii()  # pycocotools kodlama varsaymasın
    assert hazirlik["loco_etiket_sha256"] == _sha((kaynak / "loco-all-v1.json").read_bytes())
    assert hazirlik["loco_etiket_sabitlenen"] is False  # sahte etiket dosyası
    assert hazirlik["loco_arsiv_sha256"] is None  # indirme.json yok
    assert (hazirlik["en_uzun_kenar"], hazirlik["sinir"], hazirlik["forklift_tekrar"]) == (
        128,
        None,
        3,
    )
    assert (hazirlik["listelenen_goruntu"], hazirlik["secilen_goruntu"]) == (7, 7)
    assert (hazirlik["eksik_goruntu"], hazirlik["kullanilamayan_goruntu"]) == (0, 0)
    assert (hazirlik["cok_uyeli_goruntu"], hazirlik["cok_uyeli_ornekler"]) == (0, [])
    assert hazirlik["atilan_kutu"] == {"baska_sinif": 2, "kucuk_kutu": 1}
    bolum = hazirlik["bolumler"]["egitim"]
    assert (bolum["goruntu"], bolum["goruntu_kaydi"], bolum["forklift_goruntu"]) == (4, 8, 2)
    assert bolum["kutu"] == {"forklift": 3, "pallet_jack": 1}
    assert bolum["kutu_kaydi"] == {"forklift": 9, "pallet_jack": 1}
    assert bolum["alt_kumeler"]["subset-3"] == {
        "goruntu": 2,
        "forklift_goruntu": 1,
        "forklift": 2,
        "pallet_jack": 0,
    }
    assert bolum["alt_kumeler"]["subset-5"]["goruntu"] == 0
    assert hazirlik["bolumler"]["test"]["kutu"] == {"forklift": 1, "pallet_jack": 1}
    assert (hedef / "LICENSE").read_text(encoding="utf-8") == "CC0 1.0 Universal\n"
    assert [p.name for p in tmp_path.iterdir() if "hazirlik" in p.name] == []

    satirlar = capsys.readouterr().out.splitlines()
    ozet = json.loads(next(s for s in satirlar if s.startswith("HAZIRLIK_OZETI ")).split(" ", 1)[1])
    assert ozet["egitim"]["goruntu_kaydi"] == 8 and ozet["test"]["goruntu"] == 3


def test_hazirla_kararli_ve_arsiv_kok_klasorunden_bagimsiz(tmp_path):
    """Aynı girdi aynı baytları verir; zip'teki kök klasör ("LOCO/v1/") fark etmez."""
    birinci = _sahte_loco(tmp_path / "ham1", ORNEK)
    ikinci = _sahte_loco(tmp_path / "ham2", ORNEK, onek="LOCO/v1/dataset/")
    assert _hazirla(birinci, tmp_path / "a") == 0
    assert _hazirla(ikinci, tmp_path / "b") == 0
    for ad in (
        "annotations/egitim.json",
        "annotations/test.json",
        "hazirlik.json",
        "egitim/000001.jpg",
        "test/000003.jpg",
    ):
        assert (tmp_path / "a" / ad).read_bytes() == (tmp_path / "b" / ad).read_bytes(), ad


def _uye_ekle(zip_yolu: Path, uyeler: dict[str, bytes]) -> None:
    with zipfile.ZipFile(zip_yolu, "a", zipfile.ZIP_STORED) as arsiv:
        for ad, icerik in uyeler.items():
            arsiv.writestr(ad, icerik)


def test_hazirla_icerigi_farkli_cok_uyeli_yolda_durur(tmp_path, capsys):
    """Kök "LOCO/v1/dataset/" (tam ad tutmaz, sonekle bulunur) ve yanında daha
    kısa adlı bir önizleme ağacı: en kısa ad sessizce seçilseydi eğitim düşük
    çözünürlüklü görüntüyü görürdü. Hiçbir şey yazılmadan çıkış kodu 2."""
    goruntuler = _duz_goruntuler(5)
    kaynak = _sahte_loco(tmp_path / "ham", goruntuler, onek="LOCO/v1/dataset/")
    _uye_ekle(kaynak / "loco.zip", {"prv/subset-2/cam/001.jpg": _jpeg(8, 6)})
    assert _hazirla(kaynak, tmp_path / "veri-seti") == 2
    hata = capsys.readouterr().err
    assert "1 tanesinin yolu arşivde içeriği FARKLI" in hata
    assert "/dataset/subset-2/cam/001.jpg" in hata and "prv/subset-2/cam/001.jpg" in hata
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ham"]


def test_hazirla_ayni_icerikli_kopya_uyeyi_kaydeder(tmp_path, capsys):
    goruntuler = _duz_goruntuler(5)
    kaynak = _sahte_loco(tmp_path / "ham", goruntuler, onek="LOCO/v1/dataset/")
    with zipfile.ZipFile(kaynak / "loco.zip") as arsiv:
        asil = arsiv.read("LOCO/v1/dataset/subset-2/cam/002.jpg")
    _uye_ekle(kaynak / "loco.zip", {"kopya/subset-2/cam/002.jpg": asil})
    assert _hazirla(kaynak, tmp_path / "veri-seti") == 0
    assert "UYARI: 1 görüntünün yolu arşivde birden çok üyeye uyuyor" in capsys.readouterr().out
    hazirlik = _oku(tmp_path / "veri-seti" / "hazirlik.json")
    assert hazirlik["cok_uyeli_goruntu"] == 1
    assert hazirlik["cok_uyeli_ornekler"] == [
        "/dataset/subset-2/cam/002.jpg: "
        "LOCO/v1/dataset/subset-2/cam/002.jpg | kopya/subset-2/cam/002.jpg"
    ]
    assert hazirlik["bolumler"]["egitim"]["goruntu"] == 5


def test_hazirla_eksik_goruntu_fazlaysa_yarim_veri_birakmaz(tmp_path, capsys):
    goruntuler = _duz_goruntuler(10)
    goruntuler[4]["arsivde"] = False  # %10 eksik
    kaynak = _sahte_loco(tmp_path / "ham", goruntuler)
    assert _hazirla(kaynak, tmp_path / "veri-seti") == 2
    hata = capsys.readouterr().err
    # İleti iki tarafı da gösterir: eksik JSON yolu ve arşivdeki gerçek üye adları
    assert "arşivde yok" in hata and goruntuler[4]["yol"] in hata
    assert "dataset/subset-2/cam/000.jpg" in hata
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ham"]


def test_hazirla_az_eksik_ve_bozuk_goruntuyu_sayar(tmp_path):
    goruntuler = _duz_goruntuler(100)
    goruntuler[3]["arsivde"] = False
    goruntuler[7]["bozuk"] = True  # 2/100: sınırda, geçer
    kaynak = _sahte_loco(tmp_path / "ham", goruntuler)
    assert _hazirla(kaynak, tmp_path / "veri-seti") == 0
    hazirlik = _oku(tmp_path / "veri-seti" / "hazirlik.json")
    assert (hazirlik["eksik_goruntu"], hazirlik["kullanilamayan_goruntu"]) == (1, 1)
    assert hazirlik["eksik_ornekler"] == [goruntuler[3]["yol"]]
    assert hazirlik["kullanilamayan_ornekler"][0].startswith(goruntuler[7]["yol"])
    assert hazirlik["bolumler"]["egitim"]["goruntu"] == 98
    assert len(list((tmp_path / "veri-seti" / "egitim").iterdir())) == 98

    # Üçüncü sorunlu görüntü sınırı aşar: görüntüler yazıldıktan sonra da durur, iz bırakmaz
    goruntuler[9]["bozuk"] = True
    kaynak = _sahte_loco(tmp_path / "ham3", goruntuler)
    assert _hazirla(kaynak, tmp_path / "veri-seti-3") == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ham", "ham3", "veri-seti"]


def test_hazirla_arsivdeki_boyut_farkini_isler(tmp_path):
    goruntuler = _duz_goruntuler(60)
    goruntuler.append(
        {  # arşivde yarı çözünürlükte, aynı oran: kutu 0,5 ile ölçeklenir
            "yol": "/dataset/subset-2/cam/yari.jpg",
            "w": 128,
            "h": 96,
            "kutular": [("forklift", [64, 48, 32, 24])],
            "arsiv_boyutu": (64, 48),
        }
    )
    goruntuler.append(
        {  # oran farklı: kutular oturmaz, görüntü kullanılmaz
            "yol": "/dataset/subset-2/cam/kare.jpg",
            "w": 64,
            "h": 48,
            "kutular": [("forklift", [10, 10, 20, 20])],
            "arsiv_boyutu": (64, 64),
        }
    )
    kaynak = _sahte_loco(tmp_path / "ham", goruntuler)
    assert _hazirla(kaynak, tmp_path / "veri-seti") == 0
    hazirlik = _oku(tmp_path / "veri-seti" / "hazirlik.json")
    assert hazirlik["olcegi_farkli_goruntu"] == 1
    assert hazirlik["kullanilamayan_goruntu"] == 1
    assert "boyut" in hazirlik["kullanilamayan_ornekler"][0]
    egitim = _oku(tmp_path / "veri-seti" / "annotations" / "egitim.json")
    yari = next(g for g in egitim["images"] if g["kaynak_yol"].endswith("yari.jpg"))
    assert (yari["width"], yari["height"]) == (64, 48)
    (etiket,) = [e for e in egitim["annotations"] if e["image_id"] == yari["id"]]
    assert etiket["bbox"] == [32.0, 24.0, 16.0, 12.0]
    resim = cv2.imread(str(tmp_path / "veri-seti" / "egitim" / yari["file_name"]))
    assert resim[30, 40].min() > 200 and resim[5, 5].max() < 50


def test_hazirla_sinir_alt_kume_basina_forklift_once(tmp_path):
    goruntuler = []
    for alt in ("subset-2", "subset-3", "subset-4"):
        for no in range(4):
            kutular = [("forklift", [2, 2, 8, 6])] if no == 3 else []
            goruntuler.append(
                {"yol": f"/dataset/{alt}/c/{no}.jpg", "w": 16, "h": 12, "kutular": kutular}
            )
    kaynak = _sahte_loco(tmp_path / "ham", goruntuler)
    assert _hazirla(kaynak, tmp_path / "veri-seti", "--sinir", "2", "--forklift-tekrar", "1") == 0
    egitim = _oku(tmp_path / "veri-seti" / "annotations" / "egitim.json")
    test = _oku(tmp_path / "veri-seti" / "annotations" / "test.json")
    assert [g["kaynak_yol"] for g in egitim["images"]] == [
        "/dataset/subset-2/c/0.jpg",
        "/dataset/subset-2/c/3.jpg",
        "/dataset/subset-3/c/0.jpg",
        "/dataset/subset-3/c/3.jpg",
    ]
    assert [g["kaynak_yol"] for g in test["images"]] == [
        "/dataset/subset-4/c/0.jpg",
        "/dataset/subset-4/c/3.jpg",
    ]
    hazirlik = _oku(tmp_path / "veri-seti" / "hazirlik.json")
    assert (hazirlik["sinir"], hazirlik["secilen_goruntu"], hazirlik["listelenen_goruntu"]) == (
        2,
        6,
        12,
    )


def test_hazirla_girdi_hatalarinda_durur(tmp_path, capsys):
    kaynak = _sahte_loco(tmp_path / "ham", ORNEK)
    dolu = tmp_path / "dolu"
    dolu.mkdir()
    (dolu / "eski.txt").write_text("eski hazırlık", encoding="utf-8")
    assert _hazirla(kaynak, dolu) == 2
    assert (dolu / "eski.txt").exists() and "boş değil" in capsys.readouterr().err
    assert _hazirla(tmp_path / "yok", tmp_path / "veri-seti") == 2
    assert "indir --hedef" in capsys.readouterr().err
    (tmp_path / "bos").mkdir()
    assert _hazirla(kaynak, tmp_path / "bos") == 0  # boş klasör hedef olabilir
    with pytest.raises(SystemExit):
        _hazirla(kaynak, tmp_path / "x", "--sinir", "0")


# ---------------------------------------------------------------------------
# indir: yerel http.server
# ---------------------------------------------------------------------------


class _Isleyici(http.server.BaseHTTPRequestHandler):
    """Yol -> davranış tablosuyla yanıt verir, gelen istekleri kaydeder."""

    def do_GET(self) -> None:
        self.server.istekler.append((self.path, self.headers.get("Range")))
        davranis = self.server.yollar.get(self.path)
        if davranis is None:
            self.send_error(404)
            return
        davranis(self)

    def log_message(self, format, *args) -> None:
        """Test çıktısı sessiz kalsın."""


def _govde(govde: bytes, tur: str, *, kesik_ilk: bool = False):
    """Range destekli yanıt. `kesik_ilk`: ilk yanıtta gövdenin yarısı gidip
    bağlantı kapanır (HTTP/1.0), sonraki istekler kaldığı yerden alabilir."""
    sayac = [0]

    def ver(isleyici) -> None:
        sayac[0] += 1
        aralik = isleyici.headers.get("Range")
        baslangic = int(aralik.removeprefix("bytes=").removesuffix("-")) if aralik else 0
        parca = govde[baslangic:]
        isleyici.send_response(206 if aralik else 200)
        isleyici.send_header("Content-Type", tur)
        isleyici.send_header("Content-Length", str(len(parca)))
        isleyici.send_header("Accept-Ranges", "bytes")
        if aralik:
            isleyici.send_header(
                "Content-Range", f"bytes {baslangic}-{len(govde) - 1}/{len(govde)}"
            )
        isleyici.end_headers()
        isleyici.wfile.write(parca[: len(parca) // 2] if kesik_ilk and sayac[0] == 1 else parca)

    return ver


def _yonlendir(hedef: str):
    def ver(isleyici) -> None:
        isleyici.send_response(302)
        isleyici.send_header("Location", hedef)
        isleyici.send_header("Content-Length", "0")
        isleyici.end_headers()

    return ver


@pytest.fixture
def sunucu(monkeypatch):
    for ad in ("http_proxy", "HTTP_PROXY"):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    yerel = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Isleyici)
    yerel.yollar = {}
    yerel.istekler = []
    is_parcacigi = threading.Thread(target=yerel.serve_forever, daemon=True)
    is_parcacigi.start()
    yield yerel
    yerel.shutdown()
    yerel.server_close()
    is_parcacigi.join(timeout=5)


def _adres(yerel, yol: str) -> str:
    return f"http://127.0.0.1:{yerel.server_address[1]}{yol}"


def _zip_govdesi() -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_STORED) as arsiv:
        arsiv.writestr("dataset/subset-1/a.jpg", _jpeg(32, 24))
        arsiv.writestr("dataset/subset-2/b,1.jpg", bytes(range(256)) * 64)
    return tampon.getvalue()


HIZLI = {"deneme_sayisi": 2, "bekleme_sn": 0.0, "zaman_asimi_sn": 10.0}


def test_arsiv_yonlendirmeden_iner_ve_kaydedilir(sunucu, tmp_path, capsys):
    govde = _zip_govdesi()
    sunucu.yollar["/kisa"] = _yonlendir("/Handlers/dataset.zip")
    sunucu.yollar["/Handlers/dataset.zip"] = _govde(govde, "application/zip")
    kayit = veri.arsivi_indir([_adres(sunucu, "/kisa")], tmp_path, **HIZLI)
    assert (tmp_path / "loco.zip").read_bytes() == govde
    assert not (tmp_path / "loco.zip.part").exists()
    assert kayit == _oku(tmp_path / "indirme.json")
    assert kayit["adres"] == _adres(sunucu, "/Handlers/dataset.zip")
    assert (kayit["boyut"], kayit["sha256"]) == (len(govde), _sha(govde))
    assert kayit["zaman"].endswith("+00:00")
    cikti = capsys.readouterr().out
    assert f"yönlendirme 302: {_adres(sunucu, '/kisa')} -> {kayit['adres']}" in cikti
    assert "Content-Type: application/zip" in cikti
    assert f"Content-Length: {len(govde)}" in cikti
    assert f"LOCO_ARSIV_SHA256={_sha(govde)}" in cikti.splitlines()


def test_html_sayfasi_ve_zip_olmayan_icerik_reddedilir(sunucu, tmp_path, capsys):
    sunucu.yollar["/sayfa"] = _govde(b"<html><body>Oturum acin</body></html>", "text/html")
    sunucu.yollar["/ikili"] = _govde(b"\x00" * 5000, "application/octet-stream")
    adresler = [_adres(sunucu, "/sayfa"), _adres(sunucu, "/ikili")]
    with pytest.raises(veri.IndirmeHatasi) as hata:
        veri.arsivi_indir(adresler, tmp_path, **HIZLI)
    assert hata.value.cikis_kodu == 1
    assert "HTML" in str(hata.value) and "zip değil" in str(hata.value)
    assert [yol for yol, _ in sunucu.istekler] == ["/sayfa", "/ikili"] * 2
    assert sorted(p.name for p in tmp_path.iterdir()) == []
    assert "reddedildi" in capsys.readouterr().out


def test_ilk_adres_html_verirse_ikincisi_kullanilir(sunucu, tmp_path):
    govde = _zip_govdesi()
    sunucu.yollar["/sayfa"] = _govde(b"<!doctype html><p>kapali</p>", "text/html; charset=utf-8")
    sunucu.yollar["/zip"] = _govde(govde, "application/zip")
    adresler = [_adres(sunucu, "/sayfa"), _adres(sunucu, "/zip")]
    kayit = veri.arsivi_indir(adresler, tmp_path, beklenen_sha256=_sha(govde), **HIZLI)
    assert kayit["adres"] == _adres(sunucu, "/zip")
    assert (tmp_path / "loco.zip").read_bytes() == govde


def test_sabitlenen_ozet_tutmazsa_arsiv_reddedilir(sunucu, tmp_path):
    sunucu.yollar["/zip"] = _govde(_zip_govdesi(), "application/zip")
    with pytest.raises(veri.ButunlukHatasi) as hata:
        veri.arsivi_indir([_adres(sunucu, "/zip")], tmp_path, beklenen_sha256="0" * 64, **HIZLI)
    assert hata.value.cikis_kodu == 2
    assert len(sunucu.istekler) == 1  # yeniden denenmez: başka dosya, bozulma değil
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_kopan_baglanti_kaldigi_yerden_surer(sunucu, tmp_path):
    govde = _zip_govdesi()
    sunucu.yollar["/zip"] = _govde(govde, "application/zip", kesik_ilk=True)
    kayit = veri.arsivi_indir([_adres(sunucu, "/zip")], tmp_path, **HIZLI)
    assert sunucu.istekler == [("/zip", None), ("/zip", f"bytes={len(govde) // 2}-")]
    assert (tmp_path / "loco.zip").read_bytes() == govde
    assert kayit["sha256"] == _sha(govde)


def test_html_veren_adres_yarim_dosyayi_silmez(sunucu, tmp_path):
    """Önceki adresten kalan yarım dosya, HTML veren adres yüzünden kaybolmaz."""
    govde = _zip_govdesi()
    yarim = f"bytes={len(govde) // 2}-"
    sunucu.yollar["/sayfa"] = _govde(b"<html>bakim</html>", "text/html")
    sunucu.yollar["/zip"] = _govde(govde, "application/zip", kesik_ilk=True)
    adresler = [_adres(sunucu, "/sayfa"), _adres(sunucu, "/zip")]
    veri.arsivi_indir(adresler, tmp_path, **HIZLI)
    assert sunucu.istekler == [("/sayfa", None), ("/zip", None), ("/sayfa", yarim), ("/zip", yarim)]
    assert (tmp_path / "loco.zip").read_bytes() == govde


def test_crc_tutmayan_zip_reddedilir_ve_silinir(sunucu, tmp_path):
    govde = bytearray(_zip_govdesi())
    uye = bytes(range(256)) * 64
    govde[govde.index(uye) + 1000] ^= 0xFF  # merkez dizini sağlam, üye verisi bozuk
    sunucu.yollar["/zip"] = _govde(bytes(govde), "application/zip")
    with pytest.raises(veri.IndirmeHatasi) as hata:
        veri.arsivi_indir([_adres(sunucu, "/zip")], tmp_path, **HIZLI)
    assert "b,1.jpg" in str(hata.value)
    assert sunucu.istekler == [("/zip", None), ("/zip", None)]  # bozuk tam dosyadan sürülmez
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_tek_dosya_indirme_ozeti_denetlenir(sunucu, tmp_path):
    icerik = b'{"images": []}'
    sunucu.yollar["/etiket.json"] = _govde(icerik, "application/json")
    adres = _adres(sunucu, "/etiket.json")
    hedef = tmp_path / "loco-all-v1.json"
    with pytest.raises(veri.ButunlukHatasi):
        veri.dosya_indir(adres, hedef, "f" * 64, **HIZLI)
    assert sorted(p.name for p in tmp_path.iterdir()) == []
    assert veri.dosya_indir(adres, hedef, _sha(icerik), **HIZLI) == _sha(icerik)
    assert hedef.read_bytes() == icerik
    istek_sayisi = len(sunucu.istekler)
    veri.dosya_indir(adres, hedef, _sha(icerik), **HIZLI)  # zaten var: inmez
    assert len(sunucu.istekler) == istek_sayisi
    with pytest.raises(veri.IndirmeHatasi):
        veri.dosya_indir(_adres(sunucu, "/yok"), tmp_path / "x", _sha(icerik), **HIZLI)


def test_agirlik_komutu_resmi_pth_indirir(sunucu, tmp_path, monkeypatch):
    agirlik = b"sahte agirlik"
    sunucu.yollar["/0.1.1rc0/yolox_tiny.pth"] = _govde(agirlik, "application/octet-stream")
    adres = _adres(sunucu, "/0.1.1rc0/yolox_tiny.pth")
    monkeypatch.setattr(veri.ortak, "RESMI_AGIRLIKLAR", {"tiny": (adres, _sha(agirlik))})
    assert veri.main(["agirlik", "--boy", "tiny", "--hedef", str(tmp_path / "w")]) == 0
    assert (tmp_path / "w" / "yolox_tiny.pth").read_bytes() == agirlik  # klasör: yayın adıyla
    assert veri.main(["agirlik", "--boy", "tiny", "--hedef", str(tmp_path / "t.pth")]) == 0
    assert (tmp_path / "t.pth").read_bytes() == agirlik
    monkeypatch.setattr(veri.ortak, "RESMI_AGIRLIKLAR", {"tiny": (adres, "2" * 64)})
    assert veri.main(["agirlik", "--boy", "tiny", "--hedef", str(tmp_path / "y.pth")]) == 2
    assert not (tmp_path / "y.pth").exists()


def test_indir_komutu_ve_ardindan_hazirla(sunucu, tmp_path, monkeypatch, capsys):
    sahte = _sahte_loco(tmp_path / "sahte", ORNEK)
    etiket = (sahte / "loco-all-v1.json").read_bytes()
    lisans = b"Creative Commons Legal Code\n\nCC0 1.0 Universal\n"
    arsiv = (sahte / "loco.zip").read_bytes()
    sunucu.yollar.update(
        {
            "/rgb/loco-all-v1.json": _govde(etiket, "text/plain; charset=utf-8"),
            "/LICENSE": _govde(lisans, "text/plain; charset=utf-8"),
            "/239870": _yonlendir("/Handlers/AnonymousDownload.ashx"),
            "/Handlers/AnonymousDownload.ashx": _govde(arsiv, "application/zip"),
        }
    )
    ortak = veri.ortak
    monkeypatch.setattr(
        ortak, "LOCO_ETIKET", (_adres(sunucu, "/rgb/loco-all-v1.json"), _sha(etiket))
    )
    monkeypatch.setattr(ortak, "LOCO_LISANS", (_adres(sunucu, "/LICENSE"), _sha(lisans)))
    monkeypatch.setattr(ortak, "LOCO_ARSIV_ADRESLERI", (_adres(sunucu, "/239870"),))
    monkeypatch.setattr(ortak, "LOCO_ARSIV_SHA256", None)
    ham = tmp_path / "ham"
    assert veri.main(["indir", "--hedef", str(ham)]) == 0
    assert (ham / "loco-all-v1.json").read_bytes() == etiket
    assert (ham / "LICENSE").read_bytes() == lisans
    assert (ham / "loco.zip").read_bytes() == arsiv
    cikti = capsys.readouterr().out
    assert f"LOCO_ARSIV_SHA256={_sha(arsiv)}" in cikti.splitlines()
    assert "UYARI: boyut" in cikti  # sahte arşiv 23.09.2026'daki boyutta değil

    # Özet sabitlenince aynı klasörde yeniden çalışmak hiçbir şeyi yeniden indirmez
    monkeypatch.setattr(ortak, "LOCO_ARSIV_SHA256", _sha(arsiv))
    istek_sayisi = len(sunucu.istekler)
    assert veri.main(["indir", "--hedef", str(ham)]) == 0
    assert len(sunucu.istekler) == istek_sayisi

    assert _hazirla(ham, tmp_path / "veri-seti") == 0
    hazirlik = _oku(tmp_path / "veri-seti" / "hazirlik.json")
    assert hazirlik["loco_arsiv_sha256"] == _sha(arsiv)
    assert hazirlik["loco_etiket_sabitlenen"] is True
    assert (tmp_path / "veri-seti" / "LICENSE").read_bytes() == lisans

    # Sabitlenen özeti tutmayan arşiv ve etiket: çıkış kodu 2, dosya bırakılmaz
    monkeypatch.setattr(ortak, "LOCO_ARSIV_SHA256", "0" * 64)
    assert veri.main(["indir", "--hedef", str(tmp_path / "ham2")]) == 2
    assert "SHA-256" in capsys.readouterr().err
    assert not (tmp_path / "ham2" / "loco.zip").exists()
    assert not (tmp_path / "ham2" / "indirme.json").exists()
    monkeypatch.setattr(ortak, "LOCO_ETIKET", (_adres(sunucu, "/rgb/loco-all-v1.json"), "1" * 64))
    istek_sayisi = len(sunucu.istekler)
    assert veri.main(["indir", "--hedef", str(tmp_path / "ham3")]) == 2
    assert [yol for yol, _ in sunucu.istekler[istek_sayisi:]] == ["/rgb/loco-all-v1.json"]

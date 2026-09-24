"""Forklift adayının ölçümü: egitim/forklift/degerlendir.py (docs/17 §12.3).

Ürün ortamında (.venv, torch yok) koşar ve internete çıkmaz. Üç katman:

* Saf ölçüm fonksiyonları (IoU, birebir eşleştirme, VOC AP, kapılar) elle
  hesaplanmış örneklerle. Yanlış bir AP ya da eşleştirme "aday geçti" diye
  yanlış bir yayın üretirdi.
* Bütün akış SAHTE bir ONNX oturumuyla: onnxruntime.InferenceSession yerine,
  karenin rengine göre bilinen tespitler döndüren bir oturum konur. Ürünün
  Tespitci'si gerçekten çalışır (ön işleme, sınıf eşlemesi, eşikler, NMS);
  her metriğin beklenen değeri aşağıda elle hesaplanmıştır.
* Gerçek models/yolox_tiny.onnx hem aday hem resmi model olarak (dosya yoksa
  atlanır; bash models/indir.sh): gerçek bir fotoğrafta (matplotlib'in örnek
  verisindeki portre; supervision üzerinden ürün ortamında kurulu) hiçbir
  insan kaybolmaz, forklift bulunmaz.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import onnxruntime
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egitim" / "forklift"))

import degerlendir  # egitim/forklift/degerlendir.py
from ortak import DALSAN_SINIFLARI

KOK = Path(__file__).resolve().parents[1]
FORKLIFT_KLASORU = KOK / "egitim" / "forklift"
RESMI_ONNX = KOK / "models" / "yolox_tiny.onnx"

Tespit = degerlendir.Tespit


def _t(sinif: str, kutu, puan: float = 0.9) -> Tespit:
    return Tespit(sinif, tuple(float(v) for v in kutu), puan)


A = (0.0, 0.0, 10.0, 10.0)
B = (100.0, 100.0, 110.0, 110.0)


# ---------------------------------------------------------------------------
# IoU ve eşleştirme
# ---------------------------------------------------------------------------


def test_iou():
    assert degerlendir.iou(A, A) == 1.0
    assert degerlendir.iou(A, B) == 0.0
    assert degerlendir.iou(A, (5.0, 0.0, 15.0, 10.0)) == pytest.approx(50 / 150)
    # Yalnız köşesi değen kutular kesişmez; alanı sıfır kutu hiçbir şeyle örtüşmez
    assert degerlendir.iou(A, (10.0, 10.0, 20.0, 20.0)) == 0.0
    assert degerlendir.iou((0.0, 0.0, 0.0, 10.0), (0.0, 0.0, 0.0, 10.0)) == 0.0


def test_eslestirme_puan_sirasiyla_birebir():
    """İki tahmin aynı kutuya: yüksek puanlı alır, öteki boşta kalır (ikinci kutu doğru değil)."""
    tahminler = [_t("forklift", (0, 0, 10, 11), 0.6), _t("forklift", A, 0.9)]
    assert degerlendir.eslestir(tahminler, [A]) == [-1, 0]


def test_eslestirme_en_yuksek_iou_ve_alinmamis_kutu():
    g1, g2 = (0.0, 0.0, 10.0, 10.0), (4.0, 0.0, 14.0, 10.0)  # birbirleriyle IoU 0,43
    t1 = _t("forklift", (0, 0, 10, 10), 0.9)  # g1: 1,0  g2: 0,43
    t2 = _t("forklift", (1, 0, 11, 10), 0.8)  # g1: 0,82 (alınmış)  g2: 0,54
    # t2 en iyi kutusu alınmış diye boşa düşmez: eşiği geçen öteki kutuyu alır
    assert degerlendir.eslestir([t2, t1], [g1, g2]) == [1, 0]


def test_eslestirme_esigi_dahil():
    esikte = _t("forklift", (0, 0, 10, 20))  # IoU tam 0,5
    altinda = _t("forklift", (0, 0, 10, 21))  # 100 / 210
    assert degerlendir.eslestir([esikte], [A]) == [0]
    assert degerlendir.eslestir([altinda], [A]) == [-1]


def test_eslestirme_yok_sayilan_kutu():
    buyuk, kucuk = (0.0, 0.0, 20.0, 20.0), (0.0, 0.0, 16.0, 16.0)
    tahmin = _t("forklift", (0, 0, 17, 17))  # küçükle IoU 0,89, büyükle 0,72
    # Değerlendirilen kutu, IoU'su daha düşük olsa da yok sayılana tercih edilir
    assert degerlendir.eslestir([tahmin], [kucuk, buyuk], yoksayilan=[True, False]) == [1]
    # Yok sayılan kutu birden çok tahmini karşılayabilir
    ikiz = [_t("forklift", kucuk, 0.9), _t("forklift", kucuk, 0.8)]
    assert degerlendir.eslestir(ikiz, [kucuk], yoksayilan=[True]) == [0, 0]
    with pytest.raises(ValueError):
        degerlendir.eslestir(ikiz, [kucuk], yoksayilan=[])


def test_degerlendirilen_forklift_kisa_kenari_girdide_16_piksel():
    # 1280x720 kare, 640 girdi: ölçek 0,5 -> kısa kenar 32 px tam sınırda
    assert degerlendir.degerlendirilir_mi((0, 0, 32, 200), 1280, 720, 640)
    assert not degerlendir.degerlendirilir_mi((0, 0, 31.9, 200), 1280, 720, 640)
    assert not degerlendir.degerlendirilir_mi((0, 0, 200, 31.9), 1280, 720, 640)


# ---------------------------------------------------------------------------
# AP
# ---------------------------------------------------------------------------


def test_ap_elle_hesaplanan_ornek():
    """3 gerçek kutu; puan sırasıyla doğru, yanlış, doğru, yanlış, doğru.

    recall 1/3, 2/3, 1; her düzeydeki en iyi hassasiyet 1, 2/3, 3/5:
    AP = 1/3 * 1 + 1/3 * 2/3 + 1/3 * 3/5 = 34/45.
    """
    isaretler = [(0.9, True), (0.8, False), (0.7, True), (0.6, False), (0.5, True)]
    assert degerlendir.ortalama_hassasiyet(isaretler, 3) == pytest.approx(34 / 45)
    # Sıra karışık verilse de puana göre sıralanır
    assert degerlendir.ortalama_hassasiyet(isaretler[::-1], 3) == pytest.approx(34 / 45)


def test_ap_eksik_recall_ve_tanimsiz_durum():
    # 4 kutudan 2'si bulunur: 1/4 * 1 + 1/4 * 1
    isaretler = [(0.9, True), (0.8, True), (0.7, False)]
    assert degerlendir.ortalama_hassasiyet(isaretler, 4) == pytest.approx(0.5)
    assert degerlendir.ortalama_hassasiyet([], 3) == 0.0
    # Gerçek kutu yoksa AP ölçülmemiştir: None, "%0" değil
    assert degerlendir.ortalama_hassasiyet([(0.9, False)], 0) is None


def test_ap_yok_sayilan_kutuya_dusen_tahmin_ne_dogru_ne_yanlis():
    buyuk, kucuk = (0.0, 0.0, 100.0, 100.0), (200.0, 200.0, 210.0, 210.0)
    tahminler = [
        _t("forklift", kucuk, 0.95),  # yok sayılan kutuda: atlanır
        _t("forklift", buyuk, 0.9),  # doğru
        _t("forklift", B, 0.8),  # hiçbir kutuda değil: yanlış
    ]
    isaretler = degerlendir.ap_isaretleri(tahminler, [buyuk, kucuk], [False, True])
    assert isaretler == [(0.9, True), (0.8, False)]
    assert degerlendir.ortalama_hassasiyet(isaretler, 1) == 1.0


def _dogruluk_kiyasi_olcumu():
    """tests/dogruluk_kiyas/olcum.py, dosya yolundan.

    `tests.dogruluk_kiyas` paket adı yalnız `python -m pytest`te (çalışma
    klasörü import yolundayken) çözülür; düz `pytest`te çözülmez.
    """
    ad = "dogruluk_kiyas_olcum"
    if ad not in sys.modules:
        yol = KOK / "tests" / "dogruluk_kiyas" / "olcum.py"
        tanim = importlib.util.spec_from_file_location(ad, yol)
        modul = importlib.util.module_from_spec(tanim)
        sys.modules[ad] = modul  # dataclass, modülünü sys.modules'ta arar
        tanim.loader.exec_module(modul)
    return sys.modules[ad]


def test_ap_dogruluk_kiyasindaki_formulle_ayni():
    """Yok sayılan kutu yokken AP, projedeki doğruluk takımının AP'siyle aynıdır."""
    olcum = _dogruluk_kiyasi_olcumu()
    rng = random.Random(7)
    for _ in range(300):
        n_gercek = rng.randint(1, 6)
        isaretler: list[bool] = []
        for _ in range(rng.randint(0, 12)):
            isaretler.append(sum(isaretler) < n_gercek and rng.random() < 0.5)
        puanli = [(1.0 - i / 100, dogru) for i, dogru in enumerate(isaretler)]
        beklenen = olcum._ortalama_hassasiyet(isaretler, n_gercek)
        assert degerlendir.ortalama_hassasiyet(puanli, n_gercek) == pytest.approx(beklenen)


def test_ap_kutularla_dogruluk_kiyasiyla_ayni():
    """Birbirinden uzak kutularda (eşleştirme belirsizliği yok) sinif_olcumu ile aynı AP."""
    olcum = _dogruluk_kiyasi_olcumu()
    gercekler = [(i * 100.0, 0.0, i * 100.0 + 40.0, 40.0) for i in range(4)]
    tahminler = [
        _t("forklift", gercekler[0], 0.9),
        _t("forklift", (300.0, 300.0, 340.0, 340.0), 0.85),
        _t("forklift", gercekler[2], 0.8),
        _t("forklift", (gercekler[2][0] + 2, 0, gercekler[2][2] + 2, 40), 0.7),  # ikinci kutu
        _t("forklift", gercekler[3], 0.6),
    ]
    beklenen = olcum.sinif_olcumu(
        [[olcum.Kutu("forklift", g) for g in gercekler]],
        [[olcum.Kutu("forklift", t.kutu, t.puan) for t in tahminler]],
        "forklift",
    )["ap50"]
    isaretler = degerlendir.ap_isaretleri(tahminler, gercekler, [False] * 4)
    assert degerlendir.ortalama_hassasiyet(isaretler, 4) == pytest.approx(beklenen)


# ---------------------------------------------------------------------------
# Koruma, görüntü ölçümü, gecikme
# ---------------------------------------------------------------------------


def test_koruma_insan_ve_arac():
    resmi = [
        _t("person", (0, 0, 10, 20), 0.9),
        _t("person", (50, 0, 60, 20), 0.4),
        _t("truck", (100, 100, 200, 200), 0.8),
    ]
    aday = [
        _t("person", (0, 0, 10, 20), 0.9),
        _t("forklift", (101, 100, 200, 200), 0.7),  # resmi araç forklift oldu
        _t("forklift", (300, 300, 400, 400), 0.6),  # resmi karşılığı yok
    ]
    insan = degerlendir.koruma(resmi, aday, {"person"}, {"person"})
    assert (insan.resmi, insan.kayip, insan.fazla, insan.forklift) == (2, 1, 0, 0)
    arac = degerlendir.koruma(resmi, aday, {"truck"}, {"truck", "forklift"})
    assert (arac.resmi, arac.kayip, arac.fazla, arac.forklift) == (1, 0, 1, 1)
    # Aynı model: hiçbir şey kaybolmaz
    ayni = degerlendir.koruma(resmi, resmi, {"person"}, {"person"})
    assert (ayni.kayip, ayni.fazla) == (0, 0)


def test_butun_kutular_ayri_eslestirmeyle_sayilir():
    """Denetçinin örneği: büyük kutu değerlendirilir, küçük olan yok sayılır.

    A (0,9) küçük kutuyla IoU 0,86, büyükle 0,7; değerlendirmede büyüğe yönelir.
    B (0,8) yalnız büyükle eşleşebilir (0,6). Tek eşleştirmeden sayılsaydı B
    boşta kalır ve "bütün kutular" 1 çıkardı; birebir eşleştirmede ikisi de bulunur.
    """
    buyuk, kucuk = (0.0, 0.0, 100.0, 100.0), (0.0, 0.0, 60.0, 100.0)
    tahminler = [_t("forklift", (0, 0, 70, 100), 0.9), _t("forklift", (40, 0, 100, 100), 0.8)]
    assert degerlendir._bulunan(tahminler, [buyuk, kucuk], [False, True]) == (1, 2)
    # Bir görüntünün ölçümünde de: fk_bulunan_tum 2, vg_bulunan_tum 2
    gercek = degerlendir.Gercek("subset-4", 1000, 1000, forkliftler=(buyuk, kucuk))
    sonuc = degerlendir.goruntuyu_olc(gercek, tahminler, [], tahminler, [], 200)
    # girdi 200: büyük 100 x 0,2 = 20 px değerlendirilir, küçük 60 x 0,2 = 12 px yok sayılır
    assert (sonuc.fk_gercek, sonuc.fk_gercek_tum) == (1, 2)
    assert (sonuc.fk_bulunan, sonuc.fk_bulunan_tum) == (1, 2)
    assert (sonuc.vg_bulunan, sonuc.vg_bulunan_tum) == (1, 2)


def test_goruntu_olcumu_ve_payda_sifirsa_olculmedi():
    gercek = degerlendir.Gercek("subset-4", 640, 640, forkliftler=((0, 0, 100, 100),))
    resmi = [_t("truck", (0, 0, 100, 100), 0.8), _t("person", (300, 300, 340, 400), 0.9)]
    sonuc = degerlendir.goruntuyu_olc(gercek, resmi, resmi, resmi, resmi, 640)
    metrikler, sayilar, alt = degerlendir.ozetle([sonuc])
    assert metrikler["insan_kaybi"] == 0.0 and metrikler["arac_kaybi"] == 0.0
    assert metrikler["fk_r"] == 0.0 and metrikler["vg_r"] == metrikler["vg_r_resmi"] == 1.0
    assert metrikler["vg_r_artisi"] == 0.0 and metrikler["vg_ap50_resmi"] == 1.0
    # Forklift tespiti yok, transpalet yok, boş görüntü yok: ölçülmedi
    assert metrikler["fk_kesinlik"] is None and metrikler["pt_fk"] is None
    assert metrikler["fk_fp_goruntu_basi"] is None
    assert sayilar["fk_gercek"] == 1 and alt["subset-4"]["fk_r"] == 0.0


def test_video_adimi():
    assert degerlendir.video_adimi(600) == 1
    assert degerlendir.video_adimi(601) == 2


def test_gecikme_ozeti():
    ozet = degerlendir.gecikme_ozeti([0.010, 0.020, 0.030, 0.040, 0.050], [0.010] * 5)
    assert ozet["gecikme_medyan_ms"] == pytest.approx(30.0)
    assert ozet["gecikme_p90_ms"] == pytest.approx(46.0)  # 40 + 0,6 x 10
    assert ozet["gecikme_p90_ms_resmi"] == pytest.approx(10.0)
    assert ozet["gecikme_orani_p90"] == pytest.approx(4.6)
    assert degerlendir.gecikme_ozeti([], [])["gecikme_orani_p90"] is None


# ---------------------------------------------------------------------------
# Kapılar ve ayarlar
# ---------------------------------------------------------------------------


def test_kapilar_gecer_kalir_ve_sinirda_gecer():
    esikler = {"insan_kaybi_en_fazla": 0.01, "fk_r_en_az": 0.6, "arac_kaybi_en_fazla": 0.0}
    gecti, kalan, ayrinti = degerlendir.kapilari_degerlendir(
        {"insan_kaybi": 0.01, "fk_r": 0.6, "arac_kaybi": 0.0}, esikler
    )
    assert gecti and kalan == []
    assert ayrinti["fk_r_en_az"] == {
        "metrik": "fk_r",
        "yon": "en_az",
        "esik": 0.6,
        "deger": 0.6,
        "gecti": True,
    }
    gecti, kalan, _ = degerlendir.kapilari_degerlendir(
        {"insan_kaybi": 0.02, "fk_r": 0.59, "arac_kaybi": 0.0}, esikler
    )
    assert not gecti and kalan == ["insan_kaybi_en_fazla", "fk_r_en_az"]


@pytest.mark.parametrize("deger", ["eksik", None, math.nan])
def test_olculemeyen_metrik_kapiyi_kaldirir(deger):
    metrikler = {"fk_r": 0.9}
    if deger != "eksik":
        metrikler["video_insan_kaybi"] = deger
    gecti, kalan, ayrinti = degerlendir.kapilari_degerlendir(
        metrikler, {"fk_r_en_az": 0.6, "video_insan_kaybi_en_fazla": 0.005}
    )
    assert not gecti and kalan == ["video_insan_kaybi_en_fazla"]
    assert ayrinti["fk_r_en_az"]["gecti"]


def test_kapi_adi():
    assert degerlendir.kapi_adini_coz("fk_r_en_az") == ("fk_r", "en_az")
    assert degerlendir.kapi_adini_coz("fk_fp_goruntu_basi_en_fazla") == (
        "fk_fp_goruntu_basi",
        "en_fazla",
    )
    for yanlis in ("fk_r", "fk_r_enaz", "_en_az", "fk_r_en_cok"):
        with pytest.raises(ValueError):
            degerlendir.kapi_adini_coz(yanlis)


def test_esikler_dosyasi_belirlenen_degerlerde():
    esikler = degerlendir.esikleri_oku(FORKLIFT_KLASORU / "esikler.json")
    assert esikler == {
        "insan_kaybi_en_fazla": 0.01,
        "arac_kaybi_en_fazla": 0.0,
        "vg_r_artisi_en_az": 0.10,
        "fk_r_en_az": 0.60,
        "fk_fp_goruntu_basi_en_fazla": 0.05,
        "pt_fk_en_fazla": 0.10,
        "fk_kesinlik_en_az": 0.50,
        "arac_seti_tr_fk_en_fazla": 0.02,
        "video_insan_kaybi_en_fazla": 0.005,
        "video_fk_kare_orani_en_fazla": 0.01,
        "gecikme_orani_p90_en_fazla": 1.25,
    }
    assert degerlendir.VARSAYILAN_ESIKLER == FORKLIFT_KLASORU / "esikler.json"


@pytest.mark.parametrize(
    "icerik",
    [
        '{"fk_r_enaz": 0.6}',  # yanlış ek
        '{"fkr_en_az": 0.6}',  # bilinmeyen metrik: kapı hiç geçemezdi
        '{"fk_r_en_az": "0.6"}',
        '{"fk_r_en_az": true}',
        "[0.6]",
        "{bozuk",
    ],
)
def test_hatali_esik_dosyasi_girdi_hatasidir(tmp_path, icerik):
    yol = tmp_path / "esikler.json"
    yol.write_text(icerik, encoding="utf-8")
    with pytest.raises(degerlendir.DegerlendirmeHatasi):
        degerlendir.esikleri_oku(yol)
    with pytest.raises(degerlendir.DegerlendirmeHatasi):
        degerlendir.esikleri_oku(tmp_path / "olmayan.json")


def test_tespit_ayarlari_env_ornegi_dosyasindan():
    ayar = degerlendir.uygulama_ayarlari()
    assert degerlendir.ENV_ORNEGI == KOK / ".env.example"
    assert (ayar.guven_esigi, ayar.insan_guven_esigi, ayar.nms_esigi) == (0.35, 0.28, 0.45)
    assert (ayar.en_kucuk_kenar_px, ayar.is_parcacigi) == (12, 0)


def test_tespit_ayarlari_koda_gomulu_degil(tmp_path):
    yol = tmp_path / ".env.example"
    yol.write_text(
        "TESPIT_GUVEN_ESIGI=0.5\nTESPIT_INSAN_GUVEN_ESIGI=0.4   # yorum\n"
        "TESPIT_NMS_ESIGI=0.6\nTESPIT_EN_KUCUK_KENAR_PX=20\nCIKARIM_IS_PARCACIGI=2\n",
        encoding="utf-8",
    )
    ayar = degerlendir.uygulama_ayarlari(yol)
    assert (ayar.guven_esigi, ayar.insan_guven_esigi, ayar.nms_esigi) == (0.5, 0.4, 0.6)
    assert (ayar.en_kucuk_kenar_px, ayar.is_parcacigi) == (20, 2)
    yol.write_text("TESPIT_GUVEN_ESIGI=0.5\n", encoding="utf-8")
    with pytest.raises(degerlendir.DegerlendirmeHatasi, match="TESPIT_INSAN_GUVEN_ESIGI"):
        degerlendir.uygulama_ayarlari(yol)


def test_sinif_adlari_uygulamanin_katalog_kodlari():
    from app.rules.tipler import SINIF_FORKLIFT, SINIF_INSAN, SINIF_TIR

    assert (degerlendir.INSAN, degerlendir.FORKLIFT, degerlendir.TIR) == (
        SINIF_INSAN,
        SINIF_FORKLIFT,
        SINIF_TIR,
    )


def test_forklift_tanisi_kutu_tavani_puan_ve_kazanma():
    """Ham çıktı tanısı: tavan en iyi çapa IoU'su, puan IoU >= 0,5 çapalardan,
    kazanma eşik ve öteki eşlenen puanlar üstünde; yok sayılan kutu atlanır."""
    kutular = np.array(
        [
            [0.0, 0.0, 10.0, 10.0],  # gerçek kutunun kendisi (IoU 1)
            [0.0, 0.0, 10.0, 20.0],  # IoU 0,5 (sınırda, sayılır)
            [50.0, 50.0, 60.0, 60.0],  # uzak
        ]
    )
    # sütunlar: 0 insan, 1 forklift, 2 tır
    puanlar = np.array([[0.0, 0.3, 0.1], [0.5, 0.6, 0.0], [0.0, 0.99, 0.0]])
    gercekler = [(0.0, 0.0, 10.0, 10.0), (100.0, 100.0, 120.0, 120.0), (0.0, 0.0, 10.0, 10.0)]
    tani = degerlendir.forklift_tanisi(
        kutular, puanlar, gercekler, [False, False, True], 1, [0, 2], 0.35
    )
    # 1. kutu: tavan 1, en iyi puan 0,6 (IoU 0,5 çapası), orada 0,6 > insan 0,5: kazanır
    # 2. kutu: hiçbir çapa yakın değil; 3. kutu yok sayılır
    assert tani == [(1.0, 0.6, True), (0.0, 0.0, False)]
    # Resmi modelin kutu tavanı: aynı gerçek kutular, yok sayılan atlanır
    resmi_kutular = np.array([[0.0, 0.0, 10.0, 30.0], [100.0, 100.0, 118.0, 120.0]])
    tavanlar = degerlendir.kutu_tavanlari(resmi_kutular, gercekler, [False, False, True])
    assert tavanlar == pytest.approx([1 / 3, 0.9])
    assert degerlendir.tani_ozeti(tani, tavanlar) == {
        "fk_kutu_tavani": 0.5,
        "fk_kutu_tavani_resmi": 0.5,
        "fk_puan50_medyan": 0.3,
        "fk_kazanir50": 0.5,
    }
    # İnsan puanı forklifti geçerse kazanmaz; eşik altı da kazanmaz
    puanlar[1] = [0.7, 0.6, 0.0]
    puanlar[0] = [0.0, 0.3, 0.1]
    assert (
        degerlendir.forklift_tanisi(kutular, puanlar, gercekler[:1], [False], 1, [0, 2], 0.35)[0][2]
        is False
    )
    assert degerlendir.tani_ozeti([], []) == {
        "fk_kutu_tavani": None,
        "fk_kutu_tavani_resmi": None,
        "fk_puan50_medyan": None,
        "fk_kazanir50": None,
    }


# ---------------------------------------------------------------------------
# Bütün akış: sahte ONNX oturumu, ürünün Tespitci'si
# ---------------------------------------------------------------------------

KARE = 128  # sahte kareler 128x128; sahte model girdisi 64 -> letterbox oranı 0,5
RENK_A, RENK_B, RENK_C, GRI = 40, 80, 160, 114  # GRI: Tespitci'nin açılış denemesi

P1 = (8.0, 8.0, 32.0, 56.0)
T1 = (64.0, 64.0, 112.0, 112.0)  # forklift kutusu (değerlendirilir: kısa kenar 48 x 0,5)
P2 = (16.0, 16.0, 48.0, 80.0)
F2 = (72.0, 8.0, 120.0, 56.0)
F3 = (8.0, 8.0, 28.0, 28.0)  # küçük forklift (kısa kenar 20 x 0,5 < 16: yok sayılır)
PT = (64.0, 64.0, 112.0, 112.0)  # el transpaleti

COCO = {"person": 0, "car": 2, "bus": 5, "truck": 7}
BIRLESIK = {"person": 0, "forklift": 1, "truck": 2, "pallet_jack": 3}

# Senaryo: renk -> model -> [(kutu, {sınıf: puan})]
#  A: insan P1 ikisinde de; resmi araç T1 adayda forklift (resmi truck puanı düşük kalır)
#  B: resmi insan P2 adayda kayıp; adayda boş görüntüde yanlış forklift F2
#  C: aday küçük forkliftte F3 ve transpalette (transpalet sütunu eşlenmez) forklift der
SENARYO = {
    RENK_A: {
        "resmi": [(P1, {"person": 0.9}), (T1, {"truck": 0.85})],
        "aday": [(P1, {"person": 0.9}), (T1, {"forklift": 0.9, "truck": 0.3})],
    },
    RENK_B: {"resmi": [(P2, {"person": 0.8})], "aday": [(F2, {"forklift": 0.95})]},
    RENK_C: {
        "resmi": [],
        "aday": [(F3, {"forklift": 0.7}), (PT, {"forklift": 0.8, "pallet_jack": 0.9})],
    },
    GRI: {"resmi": [], "aday": []},
}


def _cikti(girdi_boyu: int, senaryo: list, sutunlar: dict[str, int], sinif_sayisi: int):
    """[1, A, 5 + sınıf] ham YOLOX çıktısı: her kutu kendi ızgara hücresinde (adım 8)."""
    satir_sayisi = sum((girdi_boyu // adim) ** 2 for adim in (8, 16, 32))
    cikti = np.zeros((1, satir_sayisi, 5 + sinif_sayisi), dtype=np.float32)
    oran = girdi_boyu / KARE
    for (x1, y1, x2, y2), puanlar in senaryo:
        cx, cy = (x1 + x2) / 2 * oran, (y1 + y2) / 2 * oran
        g, y = (x2 - x1) * oran, (y2 - y1) * oran
        hx, hy = int(cx // 8), int(cy // 8)
        satir = hy * (girdi_boyu // 8) + hx
        cikti[0, satir, :5] = [cx / 8 - hx, cy / 8 - hy, math.log(g / 8), math.log(y / 8), 1.0]
        for sinif, puan in puanlar.items():
            cikti[0, satir, 5 + sutunlar[sinif]] = puan
    return cikti


class _SahteOturum:
    """Adı "aday" içeren dosya birleşik model (11 sütun, dalsan_classes), öteki resmi
    COCO modeli (85 sütun). Adında "96" geçen dosyanın girdisi 96, ötekilerin 64.
    Senaryo karenin sol üst pikselinden seçilir (MJPG'nin küçük sapmasına dayanıklı)."""

    def __init__(self, yol, providers, **_):
        self._ad = Path(yol).name
        self._aday = "aday" in self._ad
        self._boy = 96 if "96" in self._ad else 64

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def get_inputs(self):
        return [SimpleNamespace(name="images", shape=[1, 3, self._boy, self._boy])]

    def get_modelmeta(self):
        if not self._aday:
            return SimpleNamespace(custom_metadata_map={})
        kart = {"boy": "sahte", "kip": "v1", "kisi_onceligi": 1}
        return SimpleNamespace(
            custom_metadata_map={
                "dalsan_classes": json.dumps(DALSAN_SINIFLARI),
                "dalsan_model_karti": json.dumps(kart),
            }
        )

    def run(self, _adlar, besleme):
        girdi = next(iter(besleme.values()))
        renk = min(SENARYO, key=lambda r: abs(r - float(girdi[0, 0, 0, 0])))
        if self._aday:
            return [_cikti(self._boy, SENARYO[renk]["aday"], BIRLESIK, 6)]
        return [_cikti(self._boy, SENARYO[renk]["resmi"], COCO, 80)]


@pytest.fixture
def sahte_oturum(monkeypatch):
    monkeypatch.setattr(onnxruntime, "InferenceSession", _SahteOturum)


def _duz_kare(renk: int) -> np.ndarray:
    return np.full((KARE, KARE, 3), renk, dtype=np.uint8)


def _veri_seti(kok: Path, goruntuler: list[tuple[np.ndarray, str, list, list]]) -> Path:
    """veri.py test çıktısı biçiminde klasör: (kare, alt küme, forkliftler, transpaletler)."""
    (kok / "test").mkdir(parents=True)
    (kok / "annotations").mkdir()
    belge = {
        "images": [],
        "annotations": [],
        "categories": [{"id": 1, "name": "forklift"}, {"id": 2, "name": "pallet_jack"}],
    }
    for no, (kare, alt_kume, forkliftler, transpaletler) in enumerate(goruntuler, 1):
        ad = f"{no:06d}.png"  # kayıpsız: sahte oturum rengi okur
        assert cv2.imwrite(str(kok / "test" / ad), kare)
        belge["images"].append(
            {
                "id": no,
                "file_name": ad,
                "width": kare.shape[1],
                "height": kare.shape[0],
                "alt_kume": alt_kume,
                "kaynak_yol": f"/dataset/{alt_kume}/sahte/{no}.jpg",
            }
        )
        for kategori, kutular in ((1, forkliftler), (2, transpaletler)):
            for x1, y1, x2, y2 in kutular:
                belge["annotations"].append(
                    {
                        "id": len(belge["annotations"]) + 1,
                        "image_id": no,
                        "category_id": kategori,
                        "bbox": [x1, y1, x2 - x1, y2 - y1],
                        "area": (x2 - x1) * (y2 - y1),
                        "iscrowd": 0,
                    }
                )
    (kok / "annotations" / "test.json").write_text(json.dumps(belge), encoding="utf-8")
    return kok


def _video(yol: Path, kareler: list[np.ndarray]) -> Path:
    yazici = cv2.VideoWriter(
        str(yol), cv2.VideoWriter_fourcc(*"MJPG"), 5, (kareler[0].shape[1], kareler[0].shape[0])
    )
    if not yazici.isOpened():
        pytest.skip("OpenCV bu ortamda MJPG video yazamıyor")
    for kare in kareler:
        yazici.write(kare)
    yazici.release()
    return yol


@pytest.fixture
def sahte_girdiler(tmp_path):
    veri = _veri_seti(
        tmp_path / "veri",
        [
            (_duz_kare(RENK_A), "subset-1", [T1], []),
            (_duz_kare(RENK_B), "subset-4", [], []),
            (_duz_kare(RENK_C), "subset-4", [F3], [PT]),
        ],
    )
    aday, resmi = tmp_path / "aday.onnx", tmp_path / "resmi.onnx"
    aday.write_bytes(b"sahte aday")
    resmi.write_bytes(b"sahte resmi")
    video = _video(tmp_path / "deneme.avi", [_duz_kare(RENK_A)] * 3 + [_duz_kare(RENK_B)] * 3)
    # Araç seti: A (resmi araç adayda forklift, insan korunur), B (insan kaybolur),
    # C (resmide araç yok); görüntü olmayan dosya atlanır
    arac_seti = tmp_path / "arac-seti"
    arac_seti.mkdir()
    for ad, renk in (("a.png", RENK_A), ("b.png", RENK_B), ("c.png", RENK_C)):
        assert cv2.imwrite(str(arac_seti / ad), _duz_kare(renk))
    (arac_seti / "BENIOKU.txt").write_text("görüntü değil", encoding="utf-8")
    return SimpleNamespace(
        veri=veri,
        aday=aday,
        resmi=resmi,
        video=video,
        arac_seti=arac_seti,
        cikti=tmp_path / "o.json",
    )


def _calistir(g, *ek: str) -> list[str]:
    return [
        "--model",
        str(g.aday),
        "--resmi",
        str(g.resmi),
        "--veri",
        str(g.veri),
        "--cikti",
        str(g.cikti),
        *ek,
    ]


def test_butun_akis_elle_hesaplanan_metrikler(sahte_oturum, sahte_girdiler, capsys):
    g = sahte_girdiler
    kod = degerlendir.main(
        _calistir(
            g, "--video", str(g.video), "--arac-seti", str(g.arac_seti), "--etiket", "sahte-v1"
        )
    )
    cikti = capsys.readouterr().out
    assert kod == 0
    olcum = json.loads(g.cikti.read_text(encoding="utf-8"))
    m, s = olcum["metrikler"], olcum["sayilar"]

    # Koruma: A'da insan ve araç korunur (araç forklift olur), B'de insan kaybolur
    assert (s["resmi_insan"], s["kaybolan_insan"], s["fazla_insan"]) == (2, 1, 0)
    assert m["insan_kaybi"] == 0.5 and m["insan_kazanci"] == 0.0
    assert (s["resmi_arac"], s["kaybolan_arac"], s["forklifte_donen_arac"]) == (1, 0, 1)
    assert m["arac_kaybi"] == 0.0 and m["tr_fk"] == 1.0
    assert m["arac_kazanci"] == 3.0  # F2, F3 ve transpaletteki forklift
    # Recall: değerlendirilen tek kutu (T1) bulunur; küçük F3 yalnız "tum"da sayılır
    assert (s["fk_gercek"], s["fk_gercek_tum"]) == (1, 2)
    assert m["fk_r"] == m["fk_r_tum"] == m["vg_r"] == m["vg_r_tum"] == 1.0
    assert m["vg_r_resmi"] == 1.0 and m["vg_r_tum_resmi"] == 0.5 and m["vg_r_artisi"] == 0.0
    # Transpalet forklift sanıldı; 4 forklift tespitinden 2'si bir forkliftte
    assert m["pt_fk"] == 1.0 and m["fk_kesinlik"] == 0.5
    # Tek boş görüntü B: bir yanlış forklift
    assert s["bos_goruntu"] == 1
    assert m["fk_fp_goruntu_basi"] == 1.0 and m["fk_fp_goruntu_orani"] == 1.0
    # AP: F2 (0,95 yanlış), T1 (0,9 doğru), transpalet (0,8 yanlış), F3 yok sayılır -> 0,5
    assert m["fk_ap50"] == 0.5 and m["vg_ap50"] == 0.5 and m["vg_ap50_resmi"] == 1.0
    # Video: 3 A karesi (insan korunur) + 3 B karesi (insan kaybolur); her karede forklift
    assert s["video_kare"] == 6 and olcum["video"]["adim"] == 1
    assert m["video_insan_kaybi"] == 0.5 and m["video_arac_kaybi"] == 0.0
    assert m["video_fk_kare_orani"] == 1.0
    assert m["gecikme_p90_ms"] > 0 and m["gecikme_orani_p90"] > 0
    # Araç seti: tek resmi araç (A) adayda forklift; iki resmi insandan biri (B) kayıp
    assert (s["arac_seti_goruntu"], s["arac_seti_resmi_arac"]) == (3, 1)
    assert (s["arac_seti_forklifte_donen_arac"], s["arac_seti_kaybolan_arac"]) == (1, 0)
    assert (s["arac_seti_resmi_insan"], s["arac_seti_kaybolan_insan"]) == (2, 1)
    assert m["arac_seti_tr_fk"] == 1.0 and m["arac_seti_arac_kaybi"] == 0.0
    assert m["arac_seti_insan_kaybi"] == 0.5
    assert olcum["arac_seti"]["goruntu"] == 3 and olcum["arac_seti"]["klasor"] == "arac-seti"
    assert len(olcum["arac_seti"]["sha256"]) == 64
    # Tanı (ham çıktı): değerlendirilen tek forklift T1; sahte kutu onu birebir sarar
    # (resmi modelde de: tır T1), o çapada forklift 0,9 > tır 0,3 ve eşik 0,35: kazanır
    assert m["fk_kutu_tavani"] == 1.0 and m["fk_puan50_medyan"] == 0.9
    assert m["fk_kutu_tavani_resmi"] == 1.0
    assert m["fk_kazanir50"] == 1.0

    assert olcum["alt_kumeler"] == {
        "subset-1": {
            "goruntu": 1,
            "fk_gercek": 1,
            "fk_r": 1.0,
            "vg_r": 1.0,
            "vg_r_resmi": 1.0,
            "bos_goruntu": 0,
            "fk_fp_goruntu_basi": None,
            "fk_fp_goruntu_orani": None,
        },
        "subset-4": {
            "goruntu": 2,
            "fk_gercek": 0,
            "fk_r": None,
            "vg_r": None,
            "vg_r_resmi": None,
            "bos_goruntu": 1,
            "fk_fp_goruntu_basi": 1.0,
            "fk_fp_goruntu_orani": 1.0,
        },
    }
    # Kapılar esikler.json'dan: insan kaybı, vg artışı, yanlış forklift, transpalet,
    # araç setindeki forklift ve video kalır; kesinlik sınırda (0,5) geçer
    assert not olcum["gecti"]
    assert set(olcum["kalan"]) == {
        "insan_kaybi_en_fazla",
        "vg_r_artisi_en_az",
        "fk_fp_goruntu_basi_en_fazla",
        "pt_fk_en_fazla",
        "arac_seti_tr_fk_en_fazla",
        "video_insan_kaybi_en_fazla",
        "video_fk_kare_orani_en_fazla",
    } | ({"gecikme_orani_p90_en_fazla"} if m["gecikme_orani_p90"] > 1.25 else set())
    assert "arac_kaybi_en_fazla" not in olcum["kalan"] and "fk_r_en_az" not in olcum["kalan"]
    assert olcum["kapilar"]["fk_kesinlik_en_az"]["gecti"] is True

    # Çıktı sözleşmesi
    assert olcum["etiket"] == "sahte-v1" and olcum["girdi"] == 64
    assert olcum["goruntu_sayisi"] == 3
    assert olcum["model_sha256"] == degerlendir.dosya_ozeti(g.aday)
    assert olcum["resmi_sha256"] == degerlendir.dosya_ozeti(g.resmi)
    assert olcum["model_forklift_taniyor"] is True
    assert olcum["model_karti"]["kisi_onceligi"] == 1
    assert olcum["esikler"] == degerlendir.esikleri_oku(degerlendir.VARSAYILAN_ESIKLER)
    assert set(m) == set(degerlendir.METRIKLER)
    assert olcum["ayarlar"]["guven_esigi"] == 0.35 and olcum["ayarlar"]["ap_guven_esigi"] == 0.01
    satirlar = [x for x in cikti.splitlines() if x.startswith("OLCUM_JSON ")]
    assert len(satirlar) == 1 and json.loads(satirlar[0].removeprefix("OLCUM_JSON ")) == olcum
    tablo = cikti.split("OLCUM_JSON ")[0]
    assert tablo.isascii() and "SONUC: KALDI" in tablo and "insan_kaybi" in tablo
    assert "arac seti 3 goruntu" in tablo and "arac_seti_tr_fk" in tablo


def test_video_yoksa_video_kapilari_kalir_ve_sinir(sahte_oturum, sahte_girdiler, capsys):
    g = sahte_girdiler
    assert degerlendir.main(_calistir(g, "--sinir", "1")) == 0
    olcum = json.loads(g.cikti.read_text(encoding="utf-8"))
    assert olcum["goruntu_sayisi"] == 1 and olcum["video"] is None
    assert "video_insan_kaybi" not in olcum["metrikler"]
    # Araç seti de verilmedi: ölçülmedi, kapısı kalır
    assert olcum["arac_seti"] is None and "arac_seti_tr_fk" not in olcum["metrikler"]
    assert "arac_seti_tr_fk_en_fazla" in olcum["kalan"]
    assert olcum["etiket"] == "aday"  # varsayılan: model dosyasının adı
    assert {"video_insan_kaybi_en_fazla", "video_fk_kare_orani_en_fazla"} <= set(olcum["kalan"])
    assert olcum["kapilar"]["video_insan_kaybi_en_fazla"]["deger"] is None
    # Yalnız A görüntüsü: insan ve araç korunur
    assert olcum["metrikler"]["insan_kaybi"] == 0.0 and olcum["metrikler"]["fk_r"] == 1.0


def test_sinir_forklift_bos_ve_transpalet_gruplarindan_sirayla_secer(tmp_path):
    """Duman ölçümü (--sinir) forklifti ve yanlış alarmı da ölçmeli.

    LOCO test JSON'u yol sırasıdır; subset-1'in başında forklift yoktur. "İlk
    N" alınsaydı fk_r hiç ölçülmezdi (entegrasyon koşusunda --sinir 50 ile
    null çıktı). Sıra: forklift, boş, yalnız transpalet, sonra yeniden.
    """
    kare = _duz_kare(RENK_B)
    icerik = [
        ([], [PT]),  # 1 yalnız transpalet
        ([], []),  # 2 boş
        ([], []),  # 3 boş
        ([T1], []),  # 4 forklift
        ([F3], [PT]),  # 5 forklift ve transpalet: forklift grubunda
        ([], [PT]),  # 6 yalnız transpalet
    ]
    veri = _veri_seti(tmp_path / "veri", [(kare, "subset-1", f, p) for f, p in icerik])

    def secilen(sinir):
        return [g.yol.name for g in degerlendir.olcum_setini_oku(veri, sinir)]

    assert secilen(None) == [f"{no:06d}.png" for no in range(1, 7)]
    assert secilen(1) == ["000004.png"]
    assert secilen(3) == ["000001.png", "000002.png", "000004.png"]
    assert secilen(4) == ["000001.png", "000002.png", "000004.png", "000005.png"]
    assert secilen(5) == ["000001.png", "000002.png", "000003.png", "000004.png", "000005.png"]
    assert secilen(99) == secilen(None)


def test_sinir_arac_setini_de_sinirlar(sahte_oturum, sahte_girdiler, capsys):
    g = sahte_girdiler
    assert degerlendir.main(_calistir(g, "--sinir", "1", "--arac-seti", str(g.arac_seti))) == 0
    olcum = json.loads(g.cikti.read_text(encoding="utf-8"))
    # Ad sırasıyla ilk görüntü: a.png (resmi araç adayda forklift)
    assert olcum["arac_seti"]["goruntu"] == 1 and olcum["sayilar"]["arac_seti_goruntu"] == 1
    assert olcum["metrikler"]["arac_seti_tr_fk"] == 1.0
    assert [p.name for p in degerlendir.arac_setini_oku(g.arac_seti)] == [
        "a.png",
        "b.png",
        "c.png",
    ]


def test_kapilarin_hepsi_gecerse_gecti(sahte_oturum, sahte_girdiler, tmp_path, capsys):
    g = sahte_girdiler
    esikler = tmp_path / "gevsek.json"
    esikler.write_text('{"arac_kaybi_en_fazla": 0.0, "fk_r_en_az": 1.0}', encoding="utf-8")
    assert degerlendir.main(_calistir(g, "--esikler", str(esikler))) == 0
    olcum = json.loads(g.cikti.read_text(encoding="utf-8"))
    assert olcum["gecti"] is True and olcum["kalan"] == []
    assert "SONUC: GECTI" in capsys.readouterr().out


def _json_boyunu_boz(g) -> None:
    yol = g.veri / "annotations" / "test.json"
    belge = json.loads(yol.read_text(encoding="utf-8"))
    belge["images"][0]["width"] = 999
    yol.write_text(json.dumps(belge), encoding="utf-8")


@pytest.mark.parametrize(
    "bozma, beklenen",
    [
        (lambda g: (g.veri / "annotations" / "test.json").unlink(), "test.json"),
        (lambda g: (g.veri / "test" / "000002.png").unlink(), "görüntü dosyası yok"),
        (lambda g: g.aday.unlink(), "model dosyası yok"),
        (lambda g: g.video.unlink(), "video dosyası yok"),
        (lambda g: shutil.rmtree(g.arac_seti), "araç seti klasörü yok"),
        (lambda g: [p.unlink() for p in g.arac_seti.glob("*.png")], "araç setinde görüntü yok"),
        (lambda g: (g.arac_seti / "b.png").write_bytes(b"png degil"), "araç seti görüntüsü"),
        (_json_boyunu_boz, "999x128"),
        (lambda g: g.resmi.rename(g.resmi.with_name("resmi96.onnx")), "aynı boydaki"),
        (lambda g: (g.veri / "test" / "000001.png").write_bytes(b"png degil"), "okunamadı"),
    ],
)
def test_girdi_hatalari_cikis_kodu_2(sahte_oturum, sahte_girdiler, capsys, bozma, beklenen):
    g = sahte_girdiler
    bozma(g)
    resmi = g.resmi if g.resmi.exists() else g.resmi.with_name("resmi96.onnx")
    argumanlar = _calistir(g, "--video", str(g.video), "--arac-seti", str(g.arac_seti))
    argumanlar[argumanlar.index("--resmi") + 1] = str(resmi)
    assert degerlendir.main(argumanlar) == 2
    hata = capsys.readouterr().err
    assert hata.startswith("HATA: ") and beklenen in hata
    assert not g.cikti.exists()


# ---------------------------------------------------------------------------
# Gerçek model: resmi YOLOX-tiny kendisiyle karşılaştırılır
# ---------------------------------------------------------------------------


def _gercek_fotograf() -> np.ndarray:
    cbook = pytest.importorskip("matplotlib.cbook", reason="gerçek fotoğraf için matplotlib yok")
    try:
        yol = cbook.get_sample_data("grace_hopper.jpg", asfileobj=False)
    except (OSError, ValueError) as hata:
        pytest.skip(f"matplotlib örnek fotoğrafı yok: {hata}")
    kare = cv2.imread(str(yol))
    if kare is None:
        pytest.skip(f"örnek fotoğraf okunamadı: {yol}")
    return kare


@pytest.mark.skipif(
    not RESMI_ONNX.is_file(), reason="models/yolox_tiny.onnx yok (bash models/indir.sh)"
)
def test_resmi_model_kendisiyle_kiyaslaninca_hicbir_sey_kaybolmaz(tmp_path, capsys):
    foto = _gercek_fotograf()
    h, w = foto.shape[:2]
    zemin = np.full((h, w * 2, 3), 114, dtype=np.uint8)
    zemin[:, w // 2 : w // 2 + w] = foto
    veri = _veri_seti(
        tmp_path / "veri",
        [
            # uydurma forklift kutusu (değerlendirilir)
            (foto, "subset-1", [(w * 0.1, h * 0.55, w * 0.9, h * 0.95)], []),
            # etiketsiz: yanlış alarm burada sayılır
            (cv2.flip(foto, 1), "subset-4", [], []),
            # küçük forklift (yok sayılır) ve transpalet
            (zemin, "subset-4", [(4.0, 4.0, 14.0, 14.0)], [(10.0, h * 0.7, w * 0.4, h * 0.95)]),
        ],
    )
    video = _video(tmp_path / "v.avi", [foto, cv2.flip(foto, 1)] * 2)
    arac_seti = tmp_path / "arac-seti"
    arac_seti.mkdir()
    assert cv2.imwrite(str(arac_seti / "portre.jpg"), foto)
    cikti = tmp_path / "olcum.json"
    kod = degerlendir.main(
        [
            "--model",
            str(RESMI_ONNX),
            "--resmi",
            str(RESMI_ONNX),
            "--veri",
            str(veri),
            "--video",
            str(video),
            "--arac-seti",
            str(arac_seti),
            "--cikti",
            str(cikti),
        ]
    )
    assert kod == 0, capsys.readouterr().err
    olcum = json.loads(cikti.read_text(encoding="utf-8"))
    m, s = olcum["metrikler"], olcum["sayilar"]
    assert olcum["girdi"] == 416 and olcum["model_forklift_taniyor"] is False
    assert olcum["model_sha256"] == olcum["resmi_sha256"]
    assert s["resmi_insan"] >= 2  # portre ve aynası
    assert m["insan_kaybi"] == 0.0 and m["insan_kazanci"] == 0.0
    # Resmi model araç bulduysa hiçbiri kaybolmaz; bulmadıysa oran ölçülmemiştir
    beklenen_arac = 0.0 if s["resmi_arac"] else None
    assert m["arac_kaybi"] == beklenen_arac and m["tr_fk"] == beklenen_arac
    # Resmi modelde forklift sınıfı yok
    assert s["fk_gercek"] == 1 and s["fk_tespit"] == 0
    assert m["fk_r"] == 0.0 and m["fk_ap50"] == 0.0 and m["fk_kesinlik"] is None
    assert m["pt_fk"] == 0.0 and m["fk_fp_goruntu_basi"] == 0.0
    assert m["vg_r"] == m["vg_r_resmi"] and m["vg_r_artisi"] == 0.0
    assert m["vg_ap50"] == m["vg_ap50_resmi"]
    assert s["video_kare"] == 4 and s["video_resmi_insan"] >= 4
    assert m["video_insan_kaybi"] == 0.0 and m["video_fk_kare_orani"] == 0.0
    assert s["arac_seti_goruntu"] == 1 and m["arac_seti_insan_kaybi"] == 0.0
    beklenen_arac = 0.0 if s["arac_seti_resmi_arac"] else None
    assert m["arac_seti_tr_fk"] == beklenen_arac
    assert "fk_r_en_az" in olcum["kalan"]

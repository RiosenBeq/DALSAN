"""KKD model değerlendirmesi: veri seti + model → tek HTML rapor (docs/17 §5.9; Faz 3e).

Tasarımın kabul ölçütü: "Rapor üreteci sahte tahminlerle beklenen karışıklık
tablosunu verir." Gerçek model yok; uçtan uca testte sahte bir ORT oturumu
kırpığın üst yarısından baret, alt yarısından yelek kararını okur. Veri seti
gerçek dışa aktarımla (veri_seti.disa_aktar) ve gerçek JPEG'lerle kurulur.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.analiz.kkd_siniflandirici import KkdSiniflandirici
from app.egitim import degerlendirme
from app.egitim.degerlendirme import (
    DegerlendirmeHatasi,
    Kayit,
    Tahmin,
    degerlendir,
    degerlendir_zip,
    en_kotuler,
    karisiklik,
    olcumler,
    tahmin_etiketi,
)
from app.egitim.veri_seti import Ornek, disa_aktar
from app.rules.tipler import BELIRSIZ, VAR, YOK

# ------------------------------------------------------------------ saf hesap


def _kayit(ornek_id: int, baret: str, yelek: str, **ek) -> Kayit:
    alanlar = {"dosya": f"goruntuler/test/{ornek_id:07d}.jpg", "kume": "test", "kamera_id": "1"}
    alanlar |= {"gun": "2026-09-04", "zor": ""} | ek
    return Kayit(ornek_id=ornek_id, baret=baret, yelek=yelek, **alanlar)


def _tahmin(baret: str, yelek: str, guven: float = 0.9) -> Tahmin:
    return Tahmin(baret=baret, yelek=yelek, baret_guven=guven, yelek_guven=guven)


def test_guven_esigi_kuraldaki_gibi_belirsiz_yapar():
    assert tahmin_etiketi(VAR, 0.9, 0.7) == "yes"
    assert tahmin_etiketi(YOK, 0.7, 0.7) == "no"  # eşiğin kendisi geçer (rules/kkd.py: <)
    assert tahmin_etiketi(YOK, 0.69, 0.7) == "unknown"
    assert tahmin_etiketi(BELIRSIZ, 0.99, 0.7) == "unknown"


def test_sahte_tahminlerle_beklenen_karisiklik_tablosu():
    ciftler = [("yes", "yes"), ("yes", "no"), ("no", "no"), ("no", "no"), ("no", "unknown")]
    ciftler += [("unknown", "no"), ("unknown", "unknown")]
    tablo = karisiklik(ciftler)
    assert tablo == {
        "yes": {"yes": 1, "no": 1, "unknown": 0},
        "no": {"yes": 0, "no": 2, "unknown": 1},
        "unknown": {"yes": 0, "no": 1, "unknown": 1},
    }
    olcum = olcumler(tablo)
    # Precision'ın paydası "yok" TAHMİNLERİ: görünmüyor etiketine "yok" da yanlış
    assert (olcum["precision"].pay, olcum["precision"].payda) == (2, 4)
    # Recall'un paydası "yok" ETİKETLERİ: belirsiz kalan "yok" da kaçmıştır
    assert (olcum["recall"].pay, olcum["recall"].payda) == (2, 3)
    assert olcum["recall"].metin() == "0,66"  # aşağı yuvarlanır
    assert olcum["belirsiz"].metin(yuzde=True) == "%28"


def test_olculemeyen_oran_yazilmaz():
    olcum = olcumler(karisiklik([("yes", "yes")]))
    assert olcum["precision"].metin() == "ölçülemedi"
    assert olcum["recall"].metin() == "ölçülemedi"


def test_en_kotuler_once_yanlis_yok_sonra_emin_olunan():
    kayitlar = [_kayit(1, "no", "yes"), _kayit(2, "yes", "yes"), _kayit(3, "unknown", "no")]
    kayitlar += [_kayit(4, "yes", "yes")]
    tahminler = [
        _tahmin("yes", "yes", 0.95),  # kaçan yok
        _tahmin("no", "yes", 0.8),  # yanlış yok, az emin
        _tahmin("no", "unknown", 0.99),  # yanlış yok (görünmüyor → yok) + yelek belirsiz
        _tahmin("yes", "yes"),  # doğru
    ]
    sira = [(h["kayit"].ornek_id, h["kalem"], h["tur"]) for h in en_kotuler(kayitlar, tahminler)]
    assert sira == [
        (3, "Baret", "yanlis_yok"),
        (2, "Baret", "yanlis_yok"),
        (1, "Baret", "kacan_yok"),
        (3, "Yelek", "belirsiz_yok"),
    ]
    assert len(en_kotuler(kayitlar * 30, tahminler * 30)) == 50


def test_kirilimlar_kamera_gun_ve_zor_ornek():
    kayitlar = [
        _kayit(1, "yes", "yes", kamera_id="1", zor="white_cap"),
        _kayit(2, "no", "yes", kamera_id="2"),
        _kayit(3, "no", "no", kamera_id="", gun="2026-09-05"),
    ]
    tahminler = [_tahmin("no", "yes"), _tahmin("unknown", "yes"), _tahmin("yes", "no")]
    sonuc = degerlendir(kayitlar, tahminler)
    kirilimlar = dict(sonuc["kirilimlar"])
    kameralar = {s["ad"]: s for s in kirilimlar["Kameraya göre"]}
    assert set(kameralar) == {"Kamera 1", "Kamera 2", "Kamerası silinmiş"}
    assert kameralar["Kamera 1"]["kalemler"]["baret"]["yanlis_yok"] == 1
    # Belirsiz kalan "yok" kaçan sayılır: sahada ikisi de olay üretmez
    assert kameralar["Kamera 2"]["kalemler"]["baret"]["kacan_yok"] == 1
    assert kameralar["Kamera 2"]["kalemler"]["baret"]["belirsiz"].metin(yuzde=True) == "%100"
    zorlar = {s["ad"]: s["adet"] for s in kirilimlar["Zor örneğe göre"]}
    assert zorlar == {"Beyaz kep, bone ya da saç": 1, "Zor örnek değil": 2}
    assert [s["ad"] for s in kirilimlar["Güne göre"]] == ["2026-09-04", "2026-09-05"]
    assert sonuc["hata_sayilari"] == {"yanlis_yok": 1, "kacan_yok": 1, "belirsiz_yok": 1}


# ------------------------------------------------------------------ uçtan uca

MODEL_BAYTLARI = b"sahte-kkd-modeli-degerlendirme"
# Kırpığın yarısının parlaklığı → sınıf: beyaz var, siyah yok, orta gri
# görünmüyor, koyu gri düşük güvenli "yok" (0,6 < 0,7 → belirsiz)
PARLAKLIK = {"var": 255, "yok": 0, "gorunmuyor": 128, "zayif_yok": 90}


class _Oturum:
    """onnxruntime.InferenceSession'ın kullanılan yüzü; kırpığı okuyup karar verir."""

    def get_inputs(self):
        return [SimpleNamespace(name="girdi", shape=["N", 3, 256, 128])]

    def get_outputs(self):
        return [SimpleNamespace(name="baret"), SimpleNamespace(name="yelek")]

    def get_modelmeta(self):
        return SimpleNamespace(
            custom_metadata_map={"surum": "kkd-deneme", "egitim_tarihi": "2026-10"}
        )

    @staticmethod
    def _olasilik(ortalama: float) -> list[float]:
        if ortalama > 0.75:
            return [0.9, 0.05, 0.05]
        if ortalama < 0.2:
            return [0.05, 0.9, 0.05]
        if ortalama < 0.45:
            return [0.25, 0.6, 0.15]
        return [0.1, 0.1, 0.8]

    def run(self, adlar, besleme):
        girdi = next(iter(besleme.values()))
        ust = girdi[:, :, :128, :].mean(axis=(1, 2, 3))
        alt = girdi[:, :, 128:, :].mean(axis=(1, 2, 3))
        cikti = {
            "baret": np.array([self._olasilik(o) for o in ust], dtype=np.float32),
            "yelek": np.array([self._olasilik(o) for o in alt], dtype=np.float32),
        }
        return [cikti[ad] for ad in adlar]


def _kirpik(ust: str, alt: str) -> bytes:
    kirpik = np.zeros((256, 128, 3), dtype=np.uint8)
    kirpik[:128] = PARLAKLIK[ust]
    kirpik[128:] = PARLAKLIK[alt]
    return cv2.imencode(".jpg", kirpik, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()


# Test gününün örnekleri: (baret etiketi, yelek etiketi, kırpığın üstü, altı)
TEST_ORNEKLERI = [
    ("yes", "yes", "var", "var"),  # 1: ikisi de doğru
    ("no", "yes", "yok", "var"),  # 2: baret "yok" doğru
    ("yes", "no", "yok", "yok"),  # 3: baret yanlış "yok"; yelek doğru
    ("no", "no", "var", "gorunmuyor"),  # 4: baret kaçan; yelek belirsiz kaldı
    ("unknown", "unknown", "yok", "var"),  # 5: baret yanlış "yok" (görünmüyor etiketine)
    ("no", "yes", "zayif_yok", "var"),  # 6: baret düşük güven → belirsiz kaldı
]


@pytest.fixture
def model(tmp_path):
    klasor = tmp_path / "models"
    klasor.mkdir()
    dosya = klasor / "kkd.onnx"
    dosya.write_bytes(MODEL_BAYTLARI)
    ozet = hashlib.sha256(MODEL_BAYTLARI).hexdigest()
    (klasor / "SHA256SUMS").write_text(f"{ozet}  kkd.onnx\n", encoding="utf-8")
    return dosya


def _veri_seti(tmp_path, gun_sayisi: int = 4) -> tuple:
    """Dört gün: ilk üçü eğitim/doğrulama dolgusu, son gün TEST_ORNEKLERI."""
    klasor = tmp_path / "goruntuler"
    ornekler = []
    for gun in range(1, gun_sayisi + 1):
        son_gun = gun == gun_sayisi
        satirlar = TEST_ORNEKLERI if son_gun else [("yes", "yes", "var", "var")]
        for sira, (baret, yelek, ust, alt) in enumerate(satirlar, start=1):
            ornek_id = gun * 100 + sira
            goreli = f"kkd-ornekler/{ornek_id}.jpg"
            (klasor / goreli).parent.mkdir(parents=True, exist_ok=True)
            (klasor / goreli).write_bytes(_kirpik(ust, alt))
            an = f"2026-09-{gun:02d}T09:{sira:02d}:00+00:00"
            ornekler.append(
                Ornek(
                    id=ornek_id,
                    kamera_id=1 if sira % 2 else 2,
                    alinma_utc=an,
                    gun=an[:10],
                    dosya=goreli,
                    baret=baret,
                    yelek=yelek,
                    zor="white_cap" if (son_gun and sira == 5) else None,
                    kaynak="auto",
                    boy_px=180,
                    netlik=40.0,
                )
            )
    zip_yolu = tmp_path / "veri-seti.zip"
    manifest = disa_aktar(ornekler, klasor, zip_yolu)
    return zip_yolu, manifest


def test_uctan_uca_rapor_beklenen_tabloyu_verir(tmp_path, model):
    zip_yolu, _ = _veri_seti(tmp_path)
    hedef, sonuc, surum = degerlendir_zip(zip_yolu, model, oturum_kur=lambda _: _Oturum())
    assert sonuc["adet"] == len(TEST_ORNEKLERI)  # yalnız test günü
    assert sonuc["kalemler"]["baret"]["tablo"] == {
        "yes": {"yes": 1, "no": 1, "unknown": 0},
        "no": {"yes": 1, "no": 1, "unknown": 1},
        "unknown": {"yes": 0, "no": 1, "unknown": 0},
    }
    assert sonuc["kalemler"]["yelek"]["tablo"] == {
        "yes": {"yes": 3, "no": 0, "unknown": 0},
        "no": {"yes": 0, "no": 1, "unknown": 1},
        "unknown": {"yes": 1, "no": 0, "unknown": 0},
    }
    baret = sonuc["kalemler"]["baret"]["olcum"]
    assert (baret["precision"].metin(), baret["recall"].metin()) == ("0,33", "0,33")
    yelek = sonuc["kalemler"]["yelek"]["olcum"]
    assert (yelek["precision"].metin(), yelek["recall"].metin()) == ("1,00", "0,50")
    assert [(h["kayit"].ornek_id % 100, h["kalem"]) for h in sonuc["en_kotuler"]] == [
        (3, "Baret"),
        (5, "Baret"),
        (4, "Baret"),
        (4, "Yelek"),
        (6, "Baret"),
    ]

    # Tek dosya: stil ve görüntüler gömülü, dışarıya bağlantı yok
    metin = hedef.read_text(encoding="utf-8")
    assert hedef.name == f"kkd-degerlendirme-{surum}-test.html"
    assert metin.count("data:image/jpeg;base64,") == 5
    assert "http://" not in metin and "https://" not in metin and "<script" not in metin
    assert surum in metin and "kkd-deneme" in metin  # sürüm ve model kartı
    assert "Karışıklık tablosu" in metin and "Kırılımlar" in metin
    assert "Beyaz kep, bone ya da saç" in metin and "Kamera 2" in metin
    assert "0,33" in metin and "1,00" in metin


def test_komut_satiri_raporu_yazar(tmp_path, model, monkeypatch, capsys):
    zip_yolu, _ = _veri_seti(tmp_path)
    # Komut, sahadaki gibi varsayılan ORT oturumuyla kurar: sahtesi yerine konur
    monkeypatch.setattr(
        KkdSiniflandirici.__init__, "__kwdefaults__", {"oturum_kur": lambda _: _Oturum()}
    )
    cikti = tmp_path / "rapor.html"
    kod = degerlendirme.main([str(zip_yolu), "--model", str(model), "--cikti", str(cikti)])
    yazi = capsys.readouterr().out
    assert kod == 0 and cikti.is_file()
    assert "Rapor yazıldı" in yazi and "Baret: “yok” precision 0,33" in yazi


def test_kume_secilebilir(tmp_path, model):
    zip_yolu, _ = _veri_seti(tmp_path)
    hedef, sonuc, _ = degerlendir_zip(zip_yolu, model, kume="train", oturum_kur=lambda _: _Oturum())
    assert sonuc["adet"] == 2 and sonuc["en_kotuler"] == []
    assert "ezberi ölçer" in hedef.read_text(encoding="utf-8")  # test dışı küme uyarısı


# ------------------------------------------------------------------ hatalar


def test_manifestle_tutmayan_dosya_reddedilir(tmp_path, model):
    zip_yolu, manifest = _veri_seti(tmp_path)
    bozuk = tmp_path / "bozuk.zip"
    hedef_dosya = next(ad for ad in manifest["dosyalar"] if ad.startswith("goruntuler/test/"))
    with zipfile.ZipFile(zip_yolu) as kaynak, zipfile.ZipFile(bozuk, "w") as yeni:
        for ad in kaynak.namelist():
            veri = kaynak.read(ad)
            # Aynı adla BAŞKA bir kırpık: dosya değişmiş, manifest eski
            yeni.writestr(ad, _kirpik("gorunmuyor", "yok") if ad == hedef_dosya else veri)
    with pytest.raises(DegerlendirmeHatasi, match="manifest"):
        degerlendir_zip(bozuk, model, oturum_kur=lambda _: _Oturum())


def test_test_kumesi_bossa_anlasilir_hata(tmp_path, model):
    zip_yolu, _ = _veri_seti(tmp_path, gun_sayisi=1)  # tek gün: yalnız eğitim
    with pytest.raises(DegerlendirmeHatasi, match="test kümesinde örnek yok"):
        degerlendir_zip(zip_yolu, model, oturum_kur=lambda _: _Oturum())


def test_zip_olmayan_dosya_ve_eksik_model(tmp_path, model, capsys):
    sahte = tmp_path / "degil.zip"
    sahte.write_bytes(b"zip degil")
    assert degerlendirme.main([str(sahte), "--model", str(model)]) == 2
    assert "zip değil ya da bozuk" in capsys.readouterr().err

    zip_yolu, _ = _veri_seti(tmp_path)
    assert degerlendirme.main([str(zip_yolu), "--model", str(tmp_path / "yok.onnx")]) == 2
    assert "KKD modeli bulunamadı" in capsys.readouterr().err


def test_ozeti_tutmayan_model_degerlendirilmez(tmp_path, model, capsys):
    zip_yolu, _ = _veri_seti(tmp_path)
    model.write_bytes(MODEL_BAYTLARI + b"!")
    assert degerlendirme.main([str(zip_yolu), "--model", str(model)]) == 2
    assert "özetle aynı değil" in capsys.readouterr().err


def test_bilinmeyen_etiket_reddedilir(tmp_path, model):
    zip_yolu, manifest = _veri_seti(tmp_path)
    bozuk = tmp_path / "etiket.zip"
    with zipfile.ZipFile(zip_yolu) as kaynak, zipfile.ZipFile(bozuk, "w") as yeni:
        for ad in kaynak.namelist():
            veri = kaynak.read(ad)
            if ad == "etiketler.csv":
                veri = veri.replace(b",yes,", b",evet,", 1)
                manifest["dosyalar"][ad] = hashlib.sha256(veri).hexdigest()
            if ad == "manifest.json":
                continue
            yeni.writestr(ad, veri)
        yeni.writestr("manifest.json", json.dumps(manifest))
    with pytest.raises(DegerlendirmeHatasi, match="tanınmayan etiket"):
        degerlendir_zip(bozuk, model, oturum_kur=lambda _: _Oturum())

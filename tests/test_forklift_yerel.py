"""Yerel eğitim: egitim/forklift/yerel.py (fabrikanın kendi verisiyle, tek komut).

Operatör, 24.09.2026: "sadece yüklesem yeter mi ekstra kod vs. bir şey yapmam
lazım mı?" Bu betik, Forklift sayfasının veri paketinden kurulacak modele kadar
her adımı tek komutta yapar. Test torch'suz koşar: egit.py, model.py ve
degerlendir.py sahte bir çalıştırıcıyla taklit edilir (beklenen dosyaları
yazar), indirmeler sahte bir "internet"ten gelir. Fabrika paketi ürünün
GERÇEK dışa aktarımıyla, birleştirme gerçek veri.py ile yapılır.

Sınanan: adımların sırası ve argümanları, sürdürme (ikinci çalıştırma hiçbir
adımı yinelemez), kapı sonucu ve öneri sırası, duman, hatalar, kilit ve eğitim
hattıyla tutarlılık (iş akışı, esikler.json, Windows dosyası).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.analiz import model_indir
from app.egitim import forklift_verisi as fv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egitim" / "forklift"))

import degerlendir  # egitim/forklift/degerlendir.py
import ortak  # egitim/forklift/ortak.py
import veri  # egitim/forklift/veri.py
import yerel  # egitim/forklift/yerel.py

KOK = Path(__file__).resolve().parents[1]
FORKLIFT = KOK / "egitim" / "forklift"

ESIKLER = json.loads((FORKLIFT / "esikler.json").read_text(encoding="utf-8"))


def _sha(veri_: bytes) -> str:
    return hashlib.sha256(veri_).hexdigest()


def _jpeg(genislik: int, yukseklik: int, ton: int = 90) -> bytes:
    tamam, kodlu = cv2.imencode(".jpg", np.full((yukseklik, genislik, 3), ton, np.uint8))
    assert tamam
    return kodlu.tobytes()


def _goruntu_ozeti(klasor: Path) -> str:
    """hazirlik.json goruntu_sha256'nın tanımı (veri._bolumu_yaz): ad sırasıyla."""
    ozet = hashlib.sha256()
    for yol in sorted(klasor.iterdir()):
        ozet.update(f"{yol.name} {hashlib.sha256(yol.read_bytes()).hexdigest()}\n".encode())
    return ozet.hexdigest()


def _sahte_loco(klasor: Path) -> Path:
    (klasor / "egitim").mkdir(parents=True)
    (klasor / "annotations").mkdir()
    kayit = veri.Kayit(
        dosya_adi="000001.jpg",
        genislik=128,
        yukseklik=72,
        alt_kume="subset-2",
        kaynak_yol="/dataset/subset-2/a.jpg",
        kutular=(veri.Kutu("forklift", 10.0, 10.0, 20.0, 30.0),),
    )
    (klasor / "egitim" / kayit.dosya_adi).write_bytes(_jpeg(128, 72))
    ozet = veri._json_yaz(klasor / "annotations" / "egitim.json", veri.coco_belgesi([kayit]))
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
    return klasor


FORKLIFT_KUTUSU = {"kutu": [10.0, 20.0, 110.0, 150.0], "sinif": "forklift"}


def _saha_zip(klasor: Path, gunler: list[str]) -> Path:
    """Ürünün kendi dışa aktarımıyla paket: her gün bir forkliftli, bir boş kare."""
    goruntuler = klasor / "goruntuler"
    (goruntuler / fv.KLASOR).mkdir(parents=True)
    kareler = []
    for no, gun in enumerate((g for g in gunler for _ in (0, 1)), 1):
        kare = fv.Kare(
            id=no,
            kamera_id=2,
            alinma_utc=f"{gun}T09:00:00+00:00",
            gun=gun,
            dosya=f"{fv.KLASOR}/{no}.jpg",
            genislik=320,
            yukseklik=180,
            etiketler=(FORKLIFT_KUTUSU,) if no % 2 else (),
        )
        (goruntuler / kare.dosya).write_bytes(_jpeg(320, 180, 30 + no))
        kareler.append(kare)
    zip_yolu = klasor / "dalsan-forklift-veri-seti.zip"
    fv.disa_aktar(kareler, goruntuler, zip_yolu)
    return zip_yolu


class SahteSurecler:
    """egit.py, model.py ve degerlendir.py yerine: beklenen çıktıları yazar."""

    def __init__(self, gecenler=(1,), egitim_kodlari=()) -> None:
        self.komutlar: list[tuple[str, list[str]]] = []
        self.gecenler = set(gecenler)
        self.egitim_kodlari = list(egitim_kodlari)  # sıradaki eğitim çağrılarının kodu

    def betikler(self, ad: str) -> list[list[str]]:
        return [k for _, k in self.komutlar if len(k) > 1 and Path(k[1]).name == ad]

    def __call__(self, adim: str, komut) -> int:
        komut = [str(p) for p in komut]
        self.komutlar.append((adim, komut))
        if komut[1] == "-c":
            return 0

        def arg(ad: str) -> str:
            return komut[komut.index(ad) + 1]

        betik = Path(komut[1]).name
        if betik == "egit.py":
            if self.egitim_kodlari:
                return self.egitim_kodlari.pop(0)
            calisma = Path(arg("--calisma"))
            calisma.mkdir(parents=True, exist_ok=True)
            (calisma / "ek_bas.pth").write_bytes(b"ek bas")
            (calisma / "BITTI").write_text("", encoding="utf-8")
            return 0
        if betik == "model.py":
            if komut[2] == "disa-aktar":
                kart = json.loads(Path(arg("--kart")).read_text(encoding="utf-8"))
                Path(arg("--cikti")).write_bytes(
                    f"onnx k{arg('--kisi-onceligi')} {kart['calistirma_kipi']}".encode()
                )
            return 0
        if betik == "degerlendir.py":
            model = Path(arg("--model"))
            k = int(model.stem.rsplit("-k", 1)[1])
            gecti = k in self.gecenler
            kapilar = {}
            for ad, esik in ESIKLER.items():
                metrik, yon = degerlendir.kapi_adini_coz(ad)
                kaldi = not gecti and ad == "fk_r_en_az"
                kapilar[ad] = {
                    "metrik": metrik,
                    "yon": yon,
                    "esik": esik,
                    "deger": 0.41 if kaldi else esik,
                    "gecti": not kaldi,
                }
            olcum = {
                "model_sha256": _sha(model.read_bytes()),
                "esikler": ESIKLER,
                "gecti": gecti,
                "kalan": [] if gecti else ["fk_r_en_az"],
                "kapilar": kapilar,
                "metrikler": {"fk_ap50": 0.83},
                "sayilar": {"fk_gercek": 7},
                "goruntu_sayisi": 12,
            }
            Path(arg("--cikti")).write_text(json.dumps(olcum), encoding="utf-8")
            return 0
        raise AssertionError(f"beklenmedik komut: {komut}")


def _yolox_arsivi() -> tuple[bytes, str]:
    dosyalar = {"yolox/__init__.py": b'__version__ = "0.3.0"\n', "yolox/core/x.py": b"x = 1\n"}
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as arsiv:
        arsiv.writestr(f"YOLOX-{ortak.YOLOX_COMMIT}/README.md", b"readme")
        for ad, icerik in dosyalar.items():
            arsiv.writestr(f"YOLOX-{ortak.YOLOX_COMMIT}/{ad}", icerik)
    return tampon.getvalue(), yerel.kaynak_ozeti(dosyalar.items())


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Sahte internet (her kaynak kendi özetiyle), hazır LOCO ve dört günlük fabrika paketi."""
    arsiv, ozet = _yolox_arsivi()
    monkeypatch.setattr(ortak, "YOLOX_KAYNAK_OZETI", ozet)
    internet = {ortak.YOLOX_ARSIVI: arsiv}
    pth, onnx, video = b"resmi pth", b"resmi onnx", b"vtest"
    internet["https://ornek/yolox_tiny.pth"] = pth
    monkeypatch.setattr(
        ortak, "RESMI_AGIRLIKLAR", {"tiny": ("https://ornek/yolox_tiny.pth", _sha(pth))}
    )
    internet[ortak.RESMI_ONNX_ADRESI + "yolox_tiny.onnx"] = onnx
    ozetler = tmp_path / "SHA256SUMS"
    ozetler.write_text(f"{_sha(onnx)}  yolox_tiny.onnx\n", encoding="utf-8")
    monkeypatch.setattr(yerel, "MODEL_OZETLERI", ozetler)
    monkeypatch.setattr(ortak, "VIDEO", ("https://ornek/vtest.avi", _sha(video)))
    internet["https://ornek/vtest.avi"] = video
    liste = tmp_path / "arac_seti.sha256"
    satirlar = []
    for no in range(3):
        icerik = _jpeg(64, 48, no)
        internet[f"{ortak.ARAC_SETI_ADRESI}/arac{no}.jpg"] = icerik
        satirlar.append(f"{_sha(icerik)}  arac{no}.jpg")
    liste.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    monkeypatch.setattr(yerel, "ARAC_SETI_LISTESI", liste)
    monkeypatch.setattr(yerel, "GEREKEN_DISK_GB", 0.0)
    monkeypatch.setattr(yerel, "GEREKEN_DISK_GB_LOCO_HAZIR", 0.0)
    indirilen: list[str] = []

    def indir(adres: str, hedef: Path, ozet_: str | None) -> str:
        if ozet_ is not None and hedef.is_file() and _sha(hedef.read_bytes()) == ozet_:
            return ozet_
        if adres not in internet:
            raise veri.IndirmeHatasi(f"{adres} yok")
        icerik = internet[adres]
        if ozet_ is not None and _sha(icerik) != ozet_:
            raise veri.ButunlukHatasi(f"{hedef.name} tutmuyor")
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_bytes(icerik)
        indirilen.append(adres)
        return _sha(icerik)

    return {
        "internet": internet,
        "indir": indir,
        "indirilen": indirilen,
        "loco": _sahte_loco(tmp_path / "loco"),
        "saha": _saha_zip(tmp_path, ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]),
        "calisma": tmp_path / "calisma",
    }


def _calistir(ortam, surecler, *ek: str) -> int:
    secenekler = yerel.ayristirici().parse_args(
        [
            "--saha",
            str(ortam["saha"]),
            "--calisma",
            str(ortam["calisma"]),
            "--loco-veri",
            str(ortam["loco"]),
            "--oncelik",
            "normal",
            *ek,
        ]
    )
    return yerel.akisi_calistir(secenekler, calistirici=surecler, indir=ortam["indir"])


def _arg(komut: list[str], ad: str) -> str:
    return komut[komut.index(ad) + 1]


def test_tam_akis_on_deneme_egitim_uc_aday_olcum_ve_kurulacak(ortam):
    surecler = SahteSurecler(gecenler=(0, 1, 2))
    assert _calistir(ortam, surecler) == 0
    calisma = ortam["calisma"]

    egitimler = surecler.betikler("egit.py")
    assert len(egitimler) == 2, "ön deneme + tam eğitim"
    on_deneme, tam = egitimler
    assert _arg(on_deneme, "--devir") == "4" and "on-deneme-" in _arg(on_deneme, "--veri")
    istek = json.loads((FORKLIFT / "istek.json").read_text(encoding="utf-8"))
    assert _arg(tam, "--devir") == str(istek["devir"]["tiny"]), "devir istek.json'dan"
    assert Path(_arg(tam, "--veri")).name.startswith("birlesik-tiny-v3-d")
    assert _arg(tam, "--kip") == "v3" and _arg(tam, "--veri-isci") == "2"
    assert float(_arg(tam, "--sure-sn")) >= 30 * 24 * 3600, "süre bütçesi yok"

    disa = [k for k in surecler.betikler("model.py") if k[2] == "disa-aktar"]
    assert [_arg(k, "--kisi-onceligi") for k in disa] == ["1", "0", "1", "2"]
    denetim = [k for k in surecler.betikler("model.py") if k[2] == "denetle"]
    assert Path(_arg(denetim[-1], "--goruntu")).parent.name.startswith("birlesik-")

    olcumler = surecler.betikler("degerlendir.py")
    assert _arg(olcumler[0], "--sinir") == "10", "ön deneme 10 görüntüde"
    for komut in olcumler[1:]:
        assert "--sinir" not in komut
        assert Path(_arg(komut, "--esikler")) == FORKLIFT / "esikler.json"
        assert Path(_arg(komut, "--video")).name == "vtest.avi"
        assert Path(_arg(komut, "--arac-seti")).name == "arac-seti"
        assert Path(_arg(komut, "--veri")).name.startswith("birlesik-")

    sonuc = (calisma / yerel.SONUC).read_text(encoding="utf-8")
    assert "SONUÇ: GEÇTİ" in sonuc and "k=1: GEÇTİ" in sonuc
    assert "Modeli kur" in sonuc
    kurulacak = sorted(p.name for p in (calisma / yerel.KURULACAK).iterdir())
    assert len(kurulacak) == 2 and all("-k1." in ad for ad in kurulacak), "öneri k=1"

    kart = json.loads(next((calisma).glob("aday-*/kart.json")).read_text(encoding="utf-8"))
    assert kart["calistirma_kipi"] == "yerel" and kart["boy"] == "tiny"
    assert len(kart["saha_paketi"]) == 12 and "birlestirme_sha256" in kart
    assert "gunluk.txt" in {p.name for p in calisma.iterdir()}
    assert "Ön deneme geçti" in (calisma / yerel.GUNLUK).read_text(encoding="utf-8")
    assert not (calisma / yerel.KILIT).exists(), "kilit bırakıldı"


def test_ikinci_calistirma_hicbir_adimi_yinelemez(ortam):
    assert _calistir(ortam, SahteSurecler()) == 0
    indirilen = len(ortam["indirilen"])
    ikinci = SahteSurecler()
    assert _calistir(ortam, ikinci) == 0
    assert [k[1] for _, k in ikinci.komutlar] == ["-c", "-c"], "yalnız paket denetimleri"
    assert len(ortam["indirilen"]) == indirilen, "inenler yeniden inmez"


def test_kesilen_egitim_ayni_komutla_surer(ortam):
    """Tam eğitim düşerse işçisiz bir kez daha denenir; yine düşerse kod 1. Aynı komut
    yeniden çalışınca ön deneme atlanır, eğitim kaldığı yerden sürer."""
    ilk = SahteSurecler()

    def dusur(adim, komut):
        komut = [str(p) for p in komut]
        if Path(komut[1]).name == "egit.py" and "birlesik-" in _arg(komut, "--veri"):
            ilk.komutlar.append((adim, komut))
            return 1
        return ilk(adim, komut)

    with pytest.raises(yerel.AdimHatasi, match="eğitim bitmedi") as hata:
        _calistir(ortam, dusur)
    assert hata.value.cikis_kodu == 1
    tam = [k for k in ilk.betikler("egit.py") if "birlesik-" in _arg(k, "--veri")]
    assert [_arg(k, "--veri-isci") for k in tam] == ["2", "0"], "işçisiz bir kez daha denendi"
    ikinci = SahteSurecler()
    assert _calistir(ortam, ikinci) == 0
    (egitim,) = ikinci.betikler("egit.py")
    assert "birlesik-" in _arg(egitim, "--veri"), "ön deneme atlandı, eğitim sürdü"


def test_hicbiri_gecmezse_kalan_kapilar_ve_ne_yapilabilir(ortam):
    assert _calistir(ortam, SahteSurecler(gecenler=())) == 0
    sonuc = (ortam["calisma"] / yerel.SONUC).read_text(encoding="utf-8")
    assert "SONUÇ: KALDI" in sonuc and "program bu modeli kurmaz" in sonuc
    assert "Forklift bulma oranı" in sonuc and "0,41" in sonuc and "(en az 0,6)" in sonuc
    assert "Daha çok forkliftli kare etiketleyin" in sonuc
    assert "Videoda kaybolan insan" in sonuc and "(en fazla 0,005)" in sonuc, "eşik yuvarlanmaz"
    assert not (ortam["calisma"] / yerel.KURULACAK).exists()


def test_oneri_sirasi_k1_k2_k0():
    gec = {"gecti": True, "kalan": []}
    kal = {"gecti": False, "kalan": ["fk_r_en_az"]}
    assert yerel.oneri_sec({0: gec, 1: gec, 2: gec}) == 1
    assert yerel.oneri_sec({0: gec, 1: kal, 2: gec}) == 2
    assert yerel.oneri_sec({0: gec, 1: kal, 2: kal}) == 0
    assert yerel.oneri_sec({0: kal, 1: kal, 2: kal}) is None
    iki_kapi = {"gecti": False, "kalan": ["a", "b"]}
    assert yerel.en_yakin({0: kal, 1: iki_kapi, 2: kal}) == 2


def test_duman_kisa_kosar_ve_aday_kurulmaz(ortam):
    surecler = SahteSurecler(gecenler=(0, 1, 2))
    assert _calistir(ortam, surecler, "--duman") == 0
    (egitim,) = surecler.betikler("egit.py")
    assert _arg(egitim, "--devir") == "4" and "duman-veri-" in _arg(egitim, "--veri")
    olcumler = surecler.betikler("degerlendir.py")
    assert len(olcumler) == 3 and all(_arg(k, "--sinir") == "10" for k in olcumler)
    kart = json.loads(next(ortam["calisma"].glob("aday-*/kart.json")).read_text("utf-8"))
    assert kart["calistirma_kipi"] == "duman"
    sonuc = (ortam["calisma"] / yerel.SONUC).read_text(encoding="utf-8")
    assert "DUMAN SINAMASI" in sonuc and not (ortam["calisma"] / yerel.KURULACAK).exists()


def test_girdi_hatasinda_egitim_yinelenmez(ortam):
    surecler = SahteSurecler(egitim_kodlari=[2])
    with pytest.raises(yerel.YerelHata, match="girdi hatası") as hata:
        _calistir(ortam, surecler)
    assert hata.value.cikis_kodu == 2
    assert len(surecler.betikler("egit.py")) == 1


def test_tek_gunluk_paket_egitimden_once_durur(ortam, tmp_path, capsys):
    ortam["saha"] = _saha_zip(tmp_path / "tek", ["2026-10-01"])
    surecler = SahteSurecler()
    with pytest.raises(yerel.YerelHata, match="test günü yok"):
        _calistir(ortam, surecler)
    assert not surecler.betikler("egit.py") and not ortam["indirilen"], "indirme de yok"
    gunluk = (ortam["calisma"] / yerel.GUNLUK).read_text(encoding="utf-8")
    assert "DURDU: Fabrika paketinde test günü yok" in gunluk


def test_bozuk_paket_ve_yanlis_kaynak_durdurur(ortam, tmp_path):
    bozuk = tmp_path / "bozuk.zip"
    bozuk.write_bytes(b"zip degil")
    ortam["saha"] = bozuk
    with pytest.raises(veri.ButunlukHatasi, match="zip olarak açılamadı"):
        _calistir(ortam, SahteSurecler())


def test_yolox_arsivi_icerik_ozetiyle_denetlenir(ortam, tmp_path, monkeypatch):
    hedef = tmp_path / "kaynaklar" / "yolox-kaynak"
    hedef.parent.mkdir()
    yerel.yolox_kaynagini_hazirla(hedef, ortam["indir"])
    assert (hedef / "yolox" / "core" / "x.py").read_bytes() == b"x = 1\n"
    assert not (hedef / "README.md").exists(), "yalnız yolox/ paketi"
    # Python'un yazdığı önbellek özeti bozmaz, ikinci çağrı inmez
    (hedef / "yolox" / "__pycache__").mkdir()
    (hedef / "yolox" / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"pyc")
    sayi = len(ortam["indirilen"])
    yerel.yolox_kaynagini_hazirla(hedef, ortam["indir"])
    assert len(ortam["indirilen"]) == sayi

    monkeypatch.setattr(ortak, "YOLOX_KAYNAK_OZETI", "0" * 64)
    with pytest.raises(yerel.YerelHata, match="sabitlenen içerikle tutmuyor"):
        yerel.yolox_kaynagini_hazirla(tmp_path / "k2" / "yolox-kaynak", ortam["indir"])

    kotu = tmp_path / "kotu.zip"
    with zipfile.ZipFile(kotu, "w") as arsiv:
        arsiv.writestr("YOLOX-x/yolox/../../disari.py", b"x")
    with pytest.raises(yerel.YerelHata, match="beklenmedik yol"):
        yerel.arsivdeki_paket(kotu)


def test_kaynak_ozeti_tanimi_ve_sabit():
    dosyalar = [("yolox/b.py", b"b"), ("yolox/a.py", b"a")]
    beklenen = hashlib.sha256(
        "".join(sorted(f"{ad}\0{_sha(icerik)}\n" for ad, icerik in dosyalar)).encode()
    ).hexdigest()
    assert yerel.kaynak_ozeti(dosyalar) == beklenen
    assert re.fullmatch(r"[0-9a-f]{64}", ortak.YOLOX_KAYNAK_OZETI)
    assert ortak.YOLOX_COMMIT in ortak.YOLOX_ARSIVI


def test_arac_seti_eksik_kalirsa_durur(ortam, tmp_path):
    del ortam["internet"][f"{ortak.ARAC_SETI_ADRESI}/arac1.jpg"]
    with pytest.raises(yerel.AdimHatasi, match="1/3 görüntüsü inmedi"):
        yerel.arac_setini_hazirla(tmp_path / "arac", ortam["indir"], None)


def test_windows_turkce_yol_ve_disk_denetimi(tmp_path, monkeypatch):
    with pytest.raises(yerel.YerelHata, match="Türkçe"):
        yerel.calisma_yolunu_denetle(Path("C:/Kullanıcılar/Şükrü/Forklift"), windows=True)
    yerel.calisma_yolunu_denetle(Path("C:/NextGen-Forklift"), windows=True)
    yerel.calisma_yolunu_denetle(Path("/tmp/Şükrü"), windows=False)

    class Kullanim:
        free = int(1.5e9)

    monkeypatch.setattr(yerel.shutil, "disk_usage", lambda _yol: Kullanim)
    with pytest.raises(yerel.YerelHata, match="1.5 GB boş"):
        yerel.diski_denetle(tmp_path, 6.0)


def test_ayni_klasorde_ikinci_egitim_baslamaz(tmp_path, monkeypatch):
    (tmp_path / yerel.KILIT).write_text("424242\n", encoding="utf-8")
    monkeypatch.setattr(yerel, "_surec_yasiyor_mu", lambda pid: pid == 424242)
    with pytest.raises(yerel.YerelHata, match="zaten sürüyor"), yerel.kilit(tmp_path):
        pass
    monkeypatch.setattr(yerel, "_surec_yasiyor_mu", lambda pid: False)
    with yerel.kilit(tmp_path):
        assert (tmp_path / yerel.KILIT).read_text(encoding="utf-8").strip().isdigit()
    assert not (tmp_path / yerel.KILIT).exists(), "ölü sürecin kilidi devralınır ve bırakılır"


# ---- eğitim hattıyla tutarlılık ----


def test_kapi_adlari_esiklerin_hepsini_kapsar():
    metrikler = {degerlendir.kapi_adini_coz(ad)[0] for ad in ESIKLER}
    assert metrikler <= set(yerel.METRIK_ADLARI)


def test_kaynaklar_is_akisiyla_ayni():
    """Video, araç seti ve resmi ONNX adresleri tek yerde: iş akışı ve ürün aynısını kullanır."""
    is_akisi = (KOK / ".github" / "workflows" / "forklift-egit.yml").read_text(encoding="utf-8")
    assert f"VIDEO_ADRESI: {ortak.VIDEO[0]}" in is_akisi
    assert f"VIDEO_SHA256: {ortak.VIDEO[1]}" in is_akisi
    assert f"ARAC_SETI_ADRESI: {ortak.ARAC_SETI_ADRESI}" in is_akisi
    assert ortak.RESMI_ONNX_ADRESI == model_indir._YAYIN_ADRESI


def _torch_surumleri(metin: str) -> set[tuple[str, str]]:
    return set(re.findall(r"torch==([\d.]+) torchvision==([\d.]+)", metin))


def test_windows_dosyasi_ascii_crlf_ve_egitimle_ayni_torch():
    bat = FORKLIFT / "Egit-Windows.bat"
    ham = bat.read_bytes()
    metin = ham.decode("ascii")
    assert b"\r\n" in ham and b"\n" not in ham.replace(b"\r\n", b"")
    komutlar = "\n".join(
        s for s in metin.splitlines() if not s.strip().upper().startswith(("REM", "ECHO"))
    )
    assert "where python" not in komutlar and "py -3.12" in komutlar
    assert metin.count("pause") >= 3, "hata dallarında pencere açık kalır"
    assert "yerel.py" in komutlar and "gereksinimler-yerel.txt" in komutlar
    bacak = (KOK / ".github" / "workflows" / "forklift-egit-bacak.yml").read_text("utf-8")
    assert _torch_surumleri(komutlar) == _torch_surumleri(bacak) != set()
    gereksinim = (FORKLIFT / "gereksinimler-yerel.txt").read_text(encoding="utf-8")
    assert _torch_surumleri(gereksinim.replace("\n#", " ")) <= _torch_surumleri(bacak)
    assert "-r gereksinimler.txt" in gereksinim and "python-dotenv==" in gereksinim


def test_kendi_hazirladigi_loco_bozuksa_bir_kez_yeniden_hazirlar(ortam, monkeypatch):
    hazirlanan = []

    def locoyu_hazirla(klasorler, hazir):
        assert hazir is None
        hedef = klasorler.loco_veri
        if not hedef.exists():
            _sahte_loco(hedef)
            if not hazirlanan:  # ilk hazırlık yarım kalmış gibi
                (hedef / "egitim" / "000001.jpg").write_bytes(b"yarim")
            hazirlanan.append(hedef)
        return hedef

    monkeypatch.setattr(yerel, "locoyu_hazirla", locoyu_hazirla)
    secenekler = yerel.ayristirici().parse_args(
        ["--saha", str(ortam["saha"]), "--calisma", str(ortam["calisma"]), "--oncelik", "normal"]
    )
    assert yerel.akisi_calistir(secenekler, calistirici=SahteSurecler(), indir=ortam["indir"]) == 0
    assert len(hazirlanan) == 2, "bozuk LOCO silindi ve yeniden hazırlandı"
    gunluk = (ortam["calisma"] / yerel.GUNLUK).read_text(encoding="utf-8")
    assert "LOCO silinip yeniden hazırlanıyor" in gunluk


def test_verilen_hazir_loco_bozuksa_dokunmadan_durur(ortam):
    (ortam["loco"] / "egitim" / "000001.jpg").write_bytes(b"bozuk")
    with pytest.raises(veri.LocoBozukHatasi):
        _calistir(ortam, SahteSurecler())
    assert (ortam["loco"] / "egitim" / "000001.jpg").read_bytes() == b"bozuk", "dokunulmadı"

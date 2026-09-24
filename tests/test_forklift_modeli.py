"""Forklift ek başı modeli (egitim/forklift/model.py ve egit.py).

Resmi YOLOX COCO modeli donuk kalır, ek baş yalnız kendi bölümlerini öğrenir
ve dışa aktarılan tek ONNX'te eski sınıfların puanları resmi modelinkiyle
aynıdır. Bu dosya bunu sınar.

torch ve YOLOX ister: ürün ortamında (.venv, torch yok) bütün dosya ATLANIR;
eğitim ortamında ve CI'nin duman işinde çalışır. Resmi ağırlığa dayanan
testler için yolox_tiny.pth: FORKLIFT_RESMI_PTH ortam değişkeni (verilmişse
dosya bulunmalı) ya da models/yolox_tiny.pth (git'e girmez); ikisi de yoksa
o testler atlanır. Resmi ONNX: models/yolox_tiny.onnx (bash models/indir.sh).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

torch = pytest.importorskip(
    "torch", reason="torch kurulu değil: forklift eğitim testleri yalnız eğitim ortamında çalışır"
)
pytest.importorskip("yolox", reason="YOLOX yok: eğitim ortamında PYTHONPATH'e YOLOX eklenmeli")
np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
onnxruntime = pytest.importorskip("onnxruntime")
onnx = pytest.importorskip("onnx")

KOK = Path(__file__).resolve().parents[1]
FORKLIFT = KOK / "egitim" / "forklift"
if str(FORKLIFT) not in sys.path:
    sys.path.insert(0, str(FORKLIFT))

import egit  # noqa: E402
import model as forklift_modeli  # noqa: E402
from ortak import CIKIS_SINIFLARI, DALSAN_SINIFLARI, EK_SINIFLAR  # noqa: E402
from torch import nn  # noqa: E402

RESMI_ONNX = KOK / "models" / "yolox_tiny.onnx"

# YOLOX'un kendi kodu işlemcide de torch.cuda.amp çağırır (kapalı); uyarısı gürültü
pytestmark = pytest.mark.filterwarnings(
    r"ignore:.*torch\.cuda\.amp\..* is deprecated:FutureWarning"
)

# tiny (genişlik 0.375 -> 96 kanal), 3 seviye: kipin eğitilen parametreleri
_V1_ADLARI = {
    f"head.{bolum}.{k}.{ad}"
    for bolum in ("cls_preds", "obj_preds")
    for k in range(3)
    for ad in ("weight", "bias")
}
_V2_ADLARI = _V1_ADLARI | {
    f"head.cls_convs.{k}.{i}.{ad}"
    for k in range(3)
    for i in range(2)
    for ad in ("conv.weight", "bn.weight", "bn.bias")
}
_V3_ADLARI = (
    {
        f"head.reg_convs.{k}.{i}.{ad}"
        for k in range(3)
        for i in range(2)
        for ad in ("conv.weight", "bn.weight", "bn.bias")
    }
    | {f"head.{bolum}.{k}.{ad}" for bolum in ("reg_preds", "obj_preds", "cls_preds")
       for k in range(3) for ad in ("weight", "bias")}
)  # fmt: skip
BEKLENEN_EGITILENLER = {
    "v1": (_V1_ADLARI, 873),
    "v2": (_V2_ADLARI, 499_689),
    "v3": (_V3_ADLARI, 500_853),
}
# Eğitim kipinde istatistik biriktiren (kendi) BN dalı
KENDI_BN_DALI = {"v1": None, "v2": "head.cls_convs.", "v3": "head.reg_convs."}


def _resmi_pth_yolu() -> Path | None:
    ortam = os.environ.get("FORKLIFT_RESMI_PTH")
    if ortam:
        return Path(ortam)
    yerel = KOK / "models" / "yolox_tiny.pth"
    return yerel if yerel.is_file() else None


@pytest.fixture(scope="module")
def resmi_pth() -> Path:
    yol = _resmi_pth_yolu()
    if yol is None:
        pytest.skip("resmi yolox_tiny.pth yok (FORKLIFT_RESMI_PTH ya da models/yolox_tiny.pth)")
    if not yol.is_file():
        pytest.fail(f"FORKLIFT_RESMI_PTH verilmiş ama dosya yok: {yol}")
    return yol


@pytest.fixture(scope="module")
def resmi_onnx() -> Path:
    if not RESMI_ONNX.is_file():
        pytest.skip("models/yolox_tiny.onnx yok (bash models/indir.sh)")
    return RESMI_ONNX


def _sahne(rng: np.random.Generator, genislik: int, yukseklik: int) -> np.ndarray:
    """Yapay sahne: renk geçişi, gürültü ve rastgele dikdörtgenler (BGR)."""
    y, x = np.mgrid[0:yukseklik, 0:genislik]
    kare = np.stack(
        [(x * 255 // genislik), (y * 255 // yukseklik), ((x + y) * 127 // (genislik + yukseklik))],
        axis=2,
    ).astype(np.uint8)
    kare = cv2.add(kare, rng.integers(0, 40, kare.shape, dtype=np.uint8))
    for _ in range(6):
        x0, y0 = int(rng.integers(0, genislik - 20)), int(rng.integers(0, yukseklik - 20))
        x1 = int(min(genislik - 1, x0 + rng.integers(10, genislik // 2)))
        y1 = int(min(yukseklik - 1, y0 + rng.integers(10, yukseklik // 2)))
        renk = tuple(int(c) for c in rng.integers(0, 256, 3))
        cv2.rectangle(kare, (x0, y0), (x1, y1), renk, -1)
    return kare


@pytest.fixture(scope="module")
def goruntuler(tmp_path_factory) -> list[Path]:
    """Yatay, dikey, geniş ve kare dört görüntü (ön işlemenin tüm dolgu yolları)."""
    klasor = tmp_path_factory.mktemp("denetim_goruntuleri")
    rng = np.random.default_rng(0)
    yollar = []
    for i, (genislik, yukseklik) in enumerate(((640, 480), (480, 640), (1280, 720), (300, 300))):
        yol = klasor / f"{i:06d}.jpg"
        cv2.imwrite(str(yol), _sahne(rng, genislik, yukseklik))
        yollar.append(yol)
    return yollar


def _donuk(kip: str, seed: int = 0) -> forklift_modeli.DonukYOLOX:
    """Ağırlıksız (rastgele) resmi mimari üstünde eğitim modeli: yapı testleri için."""
    torch.manual_seed(seed)
    return forklift_modeli.DonukYOLOX(forklift_modeli.resmi_mimari("tiny"), "tiny", kip)


def _uygulama_sinif_eslemesi(ust: dict[str, str]) -> tuple[dict[int, str], list[str]]:
    """Uygulamanın ayrıştırıcısı; eğitim ortamında uygulamanın bağımlılıkları yoksa katalogla.

    Ürün ortamındaki tests/test_forklift_egitimi.py DALSAN_SINIFLARI'nı
    sinif_eslemesi'nin kendisiyle sınar; burada ONNX'e yazılan değerin o sabit
    olduğu ve katalog dışı kod taşımadığı sınanır.
    """
    try:
        from app.analiz.tespit import sinif_eslemesi
    except ImportError:
        from app.rules.tipler import TANINAN_SINIFLAR

        veri = json.loads(ust["dalsan_classes"])
        esleme = {int(i): kod for i, kod in veri.items() if kod in TANINAN_SINIFLAR}
        return esleme, [kod for kod in veri.values() if kod not in TANINAN_SINIFLAR]
    return sinif_eslemesi(ust)


# ---- yapı: hangi parametreler öğrenir, donuk BN eval'de kalır mı ----


@pytest.mark.parametrize("kip", ["v1", "v2", "v3"])
def test_egitilen_parametreler_kipe_gore(kip):
    donuk = _donuk(kip)
    adlar, sayi = BEKLENEN_EGITILENLER[kip]
    assert {ad for ad, p in donuk.named_parameters() if p.requires_grad} == adlar
    egitilenler = donuk.egitilen_parametreler()
    assert sum(p.numel() for p in egitilenler) == sayi
    assert {id(p) for p in egitilenler} == {
        id(p) for ad, p in donuk.named_parameters() if ad in adlar
    }
    assert not any(p.requires_grad for p in donuk.backbone.parameters())
    assert [evrisim.out_channels for evrisim in donuk.head.cls_preds] == [len(EK_SINIFLAR)] * 3
    if kip == "v1":
        # v1 çıkarımda yalnız 1x1 katman ekler
        assert all(p.dim() == 1 or p.shape[-2:] == (1, 1) for p in egitilenler)


@pytest.mark.parametrize("kip", ["v1", "v2", "v3"])
def test_donuk_bn_egitim_kipinde_eval_kalir(kip):
    donuk = _donuk(kip)
    donuk.eval()
    donuk.train()
    assert donuk.training and donuk.head.training
    assert not donuk.backbone.training
    bn_sayisi = 0
    for ad, modul in donuk.named_modules():
        if isinstance(modul, nn.BatchNorm2d):
            bn_sayisi += 1
            dal = KENDI_BN_DALI[kip]
            egitilen = dal is not None and ad.startswith(dal)
            assert modul.training is egitilen, ad
    assert bn_sayisi > 50


def test_ek_bas_resmi_bastan_baslar():
    torch.manual_seed(0)
    resmi = forklift_modeli.resmi_mimari("tiny")
    ek = forklift_modeli.ek_bas_olustur(resmi, "tiny")
    resmi_durum = resmi.head.state_dict()
    for anahtar, deger in ek.state_dict().items():
        if anahtar.startswith("cls_preds."):
            continue
        assert torch.equal(deger, resmi_durum[anahtar]), anahtar
    for evrisim in ek.cls_preds:
        assert float(evrisim.weight.detach().std()) == pytest.approx(0.01, rel=0.3)
        assert torch.allclose(evrisim.bias, torch.full_like(evrisim.bias, -4.59512), atol=1e-4)
    assert all(
        m.eps == 1e-3 and m.momentum == 0.03 for m in ek.modules() if isinstance(m, nn.BatchNorm2d)
    )


# ---- eğitim adımı: yalnız eğitilenler değişir ----


@pytest.mark.parametrize("kip", ["v1", "v2", "v3"])
def test_iki_egitim_adimi_yalniz_egitilenleri_degistirir(kip):
    donuk = _donuk(kip)
    deney = egit.EkBasDeneyi(
        veri=Path("kullanilmiyor"), boy="tiny", kip=kip, resmi_pth=Path("yok.pth"), devir=2
    )
    deney.model = donuk
    optimizer = deney.get_optimizer(batch_size=2)
    # Optimizasyona YALNIZ eğitilenler girer; ağırlık sönümü yalnız BN dışı ağırlıklarda
    grup_parametreleri = [p for grup in optimizer.param_groups for p in grup["params"]]
    assert {id(p) for p in grup_parametreleri} == {id(p) for p in donuk.egitilen_parametreler()}
    assert len(grup_parametreleri) == len(donuk.egitilen_parametreler())
    sonumlu = {id(p) for g in optimizer.param_groups if g["weight_decay"] > 0 for p in g["params"]}
    beklenen_sonumlu = {
        id(p)
        for ad, p in donuk.named_parameters()
        if p.requires_grad and ad.endswith("weight") and ".bn." not in ad
    }
    assert sonumlu == beklenen_sonumlu
    for grup in optimizer.param_groups:
        grup["lr"] = 0.01  # YOLOX ısınması lr 0'dan başlar

    once = {anahtar: deger.clone() for anahtar, deger in donuk.state_dict().items()}
    girdi = torch.rand(2, 3, 160, 160, generator=torch.Generator().manual_seed(1)) * 255
    # sınıf, cx, cy, g, y (piksel); küçük, orta ve büyük kutular: üç seviyenin
    # (adım 8, 16, 32) hepsine ön plan çapası düşsün, her eğilim gradyan alsın
    hedef = torch.zeros(2, 50, 5)
    hedef[0, :3] = torch.tensor(
        [
            [0.0, 60.0, 60.0, 50.0, 40.0],
            [1.0, 20.0, 20.0, 10.0, 12.0],
            [0.0, 115.0, 110.0, 80.0, 90.0],
        ]
    )
    hedef[1, :3] = torch.tensor(
        [
            [1.0, 100.0, 90.0, 60.0, 50.0],
            [0.0, 40.0, 120.0, 30.0, 30.0],
            [1.0, 130.0, 30.0, 12.0, 10.0],
        ]
    )
    for _ in range(2):
        cikti = donuk(girdi, hedef)
        assert set(cikti) == set(egit.KAYIP_ADLARI)  # YOLOX.forward'un kayıp sözlüğü
        assert torch.isfinite(cikti["total_loss"])
        optimizer.zero_grad()
        cikti["total_loss"].backward()
        optimizer.step()

    sonra = donuk.state_dict()
    egitilen_anahtarlar = set(donuk.egitilen_anahtarlar())
    donuk_degisen = [
        anahtar
        for anahtar, deger in once.items()
        if anahtar not in egitilen_anahtarlar and not torch.equal(sonra[anahtar], deger)
    ]
    assert donuk_degisen == []  # parametreler VE donuk BN istatistikleri bit bit aynı
    # Gradyan her eğitilen parametreye ulaşır (rastgele ağda bazı BN ölçekleri
    # float32 çözünürlüğünün altında kıpırdar; o yüzden bölüm bölüm bakılır)
    adlar = BEKLENEN_EGITILENLER[kip][0]
    assert all(p.grad is not None for ad, p in donuk.named_parameters() if ad in adlar)
    assert all(p.grad is None for p in donuk.backbone.parameters())
    degisen = {a for a in egitilen_anahtarlar if not torch.equal(sonra[a], once[a])}
    for bolum in {ad.split(".")[1] for ad in adlar}:
        assert any(a.startswith(f"head.{bolum}.") for a in degisen), bolum
    assert {a for a in adlar if a.endswith("weight") and ".bn." not in a} <= degisen
    if KENDI_BN_DALI[kip] is not None:
        # v2'nin sınıf, v3'ün kutu dalının BN'leri eğitim kipinde istatistik biriktirir
        dal = KENDI_BN_DALI[kip]
        assert any(a.startswith(dal) and a.endswith("running_mean") for a in degisen)


def test_ema_donuk_tensorlere_dokunmaz():
    donuk = _donuk("v2")
    ema = egit.EkBasEMA(donuk, egit.EMA_BOZUNMA)
    once = {anahtar: deger.clone() for anahtar, deger in ema.ema.state_dict().items()}
    with torch.no_grad():
        for parametre in donuk.egitilen_parametreler():
            parametre.add_(1.0)
    for _ in range(3):
        ema.update(donuk)
    sonra = ema.ema.state_dict()
    egitilen = set(donuk.egitilen_anahtarlar())
    assert all(torch.equal(sonra[a], once[a]) for a in once if a not in egitilen)
    assert all(
        not torch.equal(sonra[a], once[a]) for a, p in donuk.named_parameters() if p.requires_grad
    )


# ---- birleşik model: kişi önceliği ve ONNX üst verisi ----


def test_kisi_onceligi_yalniz_forklift_sutununu_bastirir():
    torch.manual_seed(0)
    resmi = forklift_modeli.resmi_mimari("tiny")
    ek = forklift_modeli.ek_bas_olustur(resmi, "tiny").eval()
    x = torch.rand(1, 3, 128, 128, generator=torch.Generator().manual_seed(2)) * 255
    with torch.no_grad():
        ciktilar = {
            k: forklift_modeli.Birlesik(resmi, ek, "v2", kisi_onceligi=k).eval()(x)[0]
            for k in (0, 1, 2)
        }
    puan = {k: c[:, 4:5] * c[:, 5:] for k, c in ciktilar.items()}
    insan = CIKIS_SINIFLARI.index("person")
    forklift = CIKIS_SINIFLARI.index("forklift")
    diger = [i for i in range(len(CIKIS_SINIFLARI)) if i != forklift]
    assert float(puan[0][:, insan].max()) > 0.05  # bastırma gerçekten sınanıyor
    for k in (1, 2):
        torch.testing.assert_close(
            puan[k][:, forklift], puan[0][:, forklift] * (1 - puan[0][:, insan]) ** k
        )
        # Diğer sütunlar aynı puan; yalnız "nesne" bölmesinin yuvarlaması (1 ulp) kadar
        torch.testing.assert_close(puan[k][:, diger], puan[0][:, diger], rtol=0, atol=1e-6)
        assert torch.equal(ciktilar[k][:, :4], ciktilar[0][:, :4])
    with pytest.raises(forklift_modeli.ForkliftHatasi):
        forklift_modeli.Birlesik(resmi, ek, "v1", kisi_onceligi=-1)


def test_birlesik_onnx_ust_verisi_uygulamaca_okunur(tmp_path):
    torch.manual_seed(0)
    resmi = forklift_modeli.resmi_mimari("tiny")
    ek = forklift_modeli.ek_bas_olustur(resmi, "tiny").eval()
    yol = forklift_modeli.disa_aktar(
        resmi, ek, "v1", "tiny", tmp_path / "birlesik.onnx", {"not": "deneme"}
    )
    assert not list(tmp_path.glob("*.part"))
    # Kartta başka bir kip yazıyorsa dışa aktarım durur (denetim karttaki kipe güvenir)
    with pytest.raises(forklift_modeli.ForkliftHatasi, match="kip"):
        forklift_modeli.disa_aktar(resmi, ek, "v1", "tiny", tmp_path / "yanlis.onnx", {"kip": "v3"})
    assert not list(tmp_path.glob("yanlis.onnx*"))
    oturum = onnxruntime.InferenceSession(str(yol), providers=["CPUExecutionProvider"])
    ust = dict(oturum.get_modelmeta().custom_metadata_map)
    assert json.loads(ust["dalsan_classes"]) == DALSAN_SINIFLARI
    assert json.loads(ust["dalsan_cikis_siniflari"]) == list(CIKIS_SINIFLARI)
    kart = {"not": "deneme", "kip": "v1", "kisi_onceligi": 1}
    assert json.loads(ust["dalsan_model_karti"]) == kart
    girdi = oturum.get_inputs()[0]
    assert girdi.name == "images" and list(girdi.shape) == [1, 3, 416, 416]
    cikti = oturum.run(None, {"images": np.zeros((1, 3, 416, 416), np.float32)})[0]
    assert cikti.shape == (1, 52 * 52 + 26 * 26 + 13 * 13, 5 + len(CIKIS_SINIFLARI))

    esleme, bilinmeyen = _uygulama_sinif_eslemesi(ust)
    assert bilinmeyen == []
    assert esleme == {0: "person", 1: "forklift", 2: "truck", 4: "truck", 5: "truck"}


# ---- resmi ağırlıklarla: birleşik ONNX resmi modelin davranışını korur ----


@pytest.mark.parametrize(
    ("kip", "kisi_onceligi"), [("v1", 1), ("v2", 1), ("v1", 0), ("v2", 2), ("v3", 1), ("v3", 0)]
)
def test_egitilmemis_disa_aktarim_denetimden_gecer(
    kip, kisi_onceligi, resmi_pth, resmi_onnx, goruntuler, tmp_path
):
    resmi = forklift_modeli.resmi_model("tiny", resmi_pth)
    torch.manual_seed(0)
    ek = forklift_modeli.ek_bas_olustur(resmi, "tiny").eval()
    yol = forklift_modeli.disa_aktar(
        resmi, ek, kip, "tiny", tmp_path / f"{kip}.onnx", {"kip": kip}, kisi_onceligi=kisi_onceligi
    )
    sonuc = forklift_modeli.denetle(yol, resmi_onnx, goruntuler, "tiny")
    assert sonuc["gecti"], sonuc["nedenler"]
    assert sonuc["goruntu"] == len(goruntuler)
    assert sonuc["en_buyuk_skor_farki"] <= forklift_modeli.SKOR_TOLERANSI
    assert sonuc["en_buyuk_kutu_farki"] <= forklift_modeli.KUTU_TOLERANSI


def _baskin_ek_bas(resmi):
    """Her yerde forklift diyen, kutusu resmi kutudan büyük bir ek baş (v3 sınaması)."""
    torch.manual_seed(0)
    ek = forklift_modeli.ek_bas_olustur(resmi, "tiny").eval()
    with torch.no_grad():
        for sinif in ek.cls_preds:
            sinif.bias[EK_SINIFLAR.index("forklift")] = 12.0
        for nesne in ek.obj_preds:
            nesne.bias += 8.0
        for kutu in ek.reg_preds:
            kutu.bias[2:4] += 0.7  # genişlik ve yükseklik (log) büyür
    return ek


def _kazanan_ve_kaybeden(cikti):
    """Forklift puanı eski puanların en büyüğünü açıkça geçiyor mu / geçmiyor mu."""
    puan = cikti[:, 4:5] * cikti[:, 5:]
    forklift = puan[:, CIKIS_SINIFLARI.index("forklift")]
    eski = puan[:, [CIKIS_SINIFLARI.index(ad) for ad in forklift_modeli.ESKI_SINIFLAR]]
    en_buyuk = eski.max(1).values
    return forklift > en_buyuk + 1e-6, forklift < en_buyuk - 1e-6


def test_v3_kutusu_yalniz_forkliftin_kazandigi_capada_ek_bastan():
    """v3: forklift kazanınca kutu ek başın kutu dalından, kazanmayınca resmi daldan;
    puan sütunları v1 ile aynı (eğitilmemiş kutu dalı resmi daldan başlar)."""
    torch.manual_seed(0)
    resmi = forklift_modeli.resmi_mimari("tiny")
    ek = _baskin_ek_bas(resmi)
    x = torch.rand(1, 3, 128, 128, generator=torch.Generator().manual_seed(3)) * 255
    with torch.no_grad():
        v3 = forklift_modeli.Birlesik(resmi, ek, "v3").eval()(x)[0]
        v1 = forklift_modeli.Birlesik(resmi, ek, "v1").eval()(x)[0]
    kazanan, kaybeden = _kazanan_ve_kaybeden(v3)
    assert int(kazanan.sum()) > 100  # sınama gerçekten kutu değiştiriyor
    torch.testing.assert_close(v3[:, 4:], v1[:, 4:])
    torch.testing.assert_close(v3[kaybeden, :4], v1[kaybeden, :4], rtol=0, atol=0)
    torch.testing.assert_close(v3[kazanan, :2], v1[kazanan, :2], rtol=0, atol=0)
    torch.testing.assert_close(v3[kazanan, 2:4], v1[kazanan, 2:4] + 0.7, rtol=0, atol=1e-5)


def _kart_kipini_sil(kaynak: Path, hedef: Path) -> Path:
    """Aynı model, kartında kip olmadan (eski ya da elle yazılmış kart)."""
    model = onnx.load(str(kaynak))
    for ozellik in model.metadata_props:
        if ozellik.key == "dalsan_model_karti":
            kart = json.loads(ozellik.value)
            del kart["kip"]
            ozellik.value = json.dumps(kart)
    onnx.save(model, str(hedef))
    return hedef


def test_v3_denetimi_kutuyu_yalniz_kart_v3_derse_gevsetir(
    resmi_pth, resmi_onnx, goruntuler, tmp_path
):
    """Kart "v3" derse forkliftin kazandığı çapaların kutusu karşılaştırılmaz ama
    sayılır; kip bilinmiyorsa denetim sıkıdır ve ek başın kutusu sapma sayılır."""
    resmi = forklift_modeli.resmi_model("tiny", resmi_pth)
    ek = _baskin_ek_bas(resmi)
    # Kart kip taşımasa da dışa aktarım onu yazar
    v3 = forklift_modeli.disa_aktar(resmi, ek, "v3", "tiny", tmp_path / "v3.onnx", {})
    sonuc = forklift_modeli.denetle(v3, resmi_onnx, goruntuler, "tiny")
    assert sonuc["gecti"], sonuc["nedenler"]
    assert sonuc["ek_kutulu_capa"] > 0
    assert sonuc["en_buyuk_skor_farki"] <= forklift_modeli.SKOR_TOLERANSI
    kartsiz = _kart_kipini_sil(v3, tmp_path / "kartsiz.onnx")
    sonuc = forklift_modeli.denetle(kartsiz, resmi_onnx, goruntuler, "tiny")
    assert not sonuc["gecti"]
    assert any("resmi modelden sapma" in neden for neden in sonuc["nedenler"])
    assert sonuc["ek_kutulu_capa"] == 0  # kip bilinmeyince sayılmaz, hepsi karşılaştırılır


def test_komut_satiri_cikis_kodlari(resmi_pth, resmi_onnx, goruntuler, tmp_path, capsys):
    klasor = goruntuler[0].parent
    aday = tmp_path / "aday.onnx"
    main = forklift_modeli.main
    disa = ["disa-aktar", "--boy", "tiny", "--kip", "v1", "--resmi-pth", str(resmi_pth)]
    disa += ["--cikti", str(aday)]
    ortak = ["--boy", "tiny", "--resmi-onnx", str(resmi_onnx), "--goruntu", str(klasor)]
    assert main(disa) == 0  # --ek-bas yok: eğitilmemiş ek baş
    assert main(["denetle", "--onnx", str(aday), *ortak, "--sinir", "2"]) == 0
    assert "DENETIM_JSON" in capsys.readouterr().out
    # Başvuru olarak birleşik modelin kendisi: çıktı biçimi resmi değil -> geçmez (1)
    yanlis = ["--boy", "tiny", "--resmi-onnx", str(aday), "--goruntu", str(klasor)]
    assert main(["denetle", "--onnx", str(aday), *yanlis]) == 1
    # Girdi hatası (2)
    assert main(["denetle", "--onnx", str(tmp_path / "yok.onnx"), *ortak]) == 2
    kart = tmp_path / "kart.json"
    kart.write_text("[1, 2]", encoding="utf-8")
    assert main([*disa, "--kart", str(kart)]) == 2  # kart bir JSON nesnesi değil


# ---- uçtan uca: egit.py (süre bütçesi + devam) -> ek_bas.pth -> ONNX -> denetim ----


def _sahte_coco(kok: Path) -> Path:
    """veri.py hazirla düzeninde küçük bir eğitim kümesi (kategori 1 forklift, 2 pallet_jack)."""
    (kok / "egitim").mkdir(parents=True)
    (kok / "annotations").mkdir()
    rng = np.random.default_rng(1)
    resimler, etiketler = [], []
    for no in range(1, 7):
        kare = _sahne(rng, 320, 240)
        kutular = [(1, 30 + 12 * no, 50, 120, 110)]
        cv2.rectangle(kare, (30 + 12 * no, 50), (150 + 12 * no, 160), (0, 200, 255), -1)
        if no % 2 == 0:
            kutular.append((2, 200, 150, 90, 60))
            cv2.rectangle(kare, (200, 150), (290, 210), (40, 40, 200), -1)
        dosya = f"{no:06d}.jpg"
        cv2.imwrite(str(kok / "egitim" / dosya), kare)
        # veri.py gibi: forklift içeren görüntü ikinci kez (yeni kimlikle) listelenir
        for _ in range(2):
            resim = {"id": len(resimler) + 1, "file_name": dosya, "width": 320, "height": 240}
            resimler.append(resim)
            for kategori, x, y, g, h in kutular:
                etiketler.append(
                    {
                        "id": len(etiketler) + 1,
                        "image_id": resim["id"],
                        "category_id": kategori,
                        "bbox": [float(x), float(y), float(g), float(h)],
                        "area": float(g * h),
                        "iscrowd": 0,
                    }
                )
    kategoriler = [{"id": 1, "name": "forklift"}, {"id": 2, "name": "pallet_jack"}]
    (kok / "annotations" / "egitim.json").write_text(
        json.dumps({"images": resimler, "annotations": etiketler, "categories": kategoriler}),
        encoding="utf-8",
    )
    return kok


def _egit_calistir(
    veri: Path, calisma: Path, kip: str, pth: Path, sure_sn: str, gecen_sn: int, devir: int = 2
) -> tuple[subprocess.CompletedProcess, dict | None]:
    import yolox

    ortam = dict(os.environ)
    yolox_kok = str(Path(yolox.__file__).resolve().parents[1])
    ortam["PYTHONPATH"] = os.pathsep.join(filter(None, [yolox_kok, ortam.get("PYTHONPATH")]))
    ortam["DALSAN_IS_BASLANGICI"] = str(int(time.time()) - gecen_sn)
    komut = [
        sys.executable,
        str(FORKLIFT / "egit.py"),
        "--veri", str(veri),
        "--boy", "tiny",
        "--kip", kip,
        "--resmi-pth", str(pth),
        "--calisma", str(calisma),
        "--devir", str(devir),
        "--parti", "4",
        "--sure-sn", sure_sn,
        "--veri-isci", "0",
        "--is-parcacigi", "2",
    ]  # fmt: skip
    sonuc = subprocess.run(komut, capture_output=True, text=True, env=ortam, timeout=600)
    ozet = None
    for satir in sonuc.stdout.splitlines():
        if satir.startswith("EGITIM_OZETI "):
            ozet = json.loads(satir.removeprefix("EGITIM_OZETI "))
    return sonuc, ozet


def test_egit_resmi_olmayan_agirligi_reddeder(tmp_path):
    # Donuk model resmi ONNX'le aynı olmalı: sabitlenmiş sha256 dışındaki ağırlık girdi hatası
    veri = _sahte_coco(tmp_path / "veri")
    sahte = tmp_path / "yolox_tiny.pth"
    sahte.write_bytes(b"resmi degil")
    sonuc, ozet = _egit_calistir(veri, tmp_path / "calisma", "v1", sahte, "19800", gecen_sn=0)
    assert sonuc.returncode == 2, sonuc.stdout + sonuc.stderr
    assert ozet is None and "sha256" in sonuc.stderr
    assert not (tmp_path / "calisma").exists()


@pytest.mark.parametrize("kip", ["v1", "v2", "v3"])
def test_egit_uctan_uca_sure_butcesi_ve_devam(kip, resmi_pth, resmi_onnx, tmp_path):
    veri = _sahte_coco(tmp_path / "veri")
    calisma = tmp_path / "calisma"

    # 1. bacak: bütçe (1 sn) çoktan dolmuş -> ilk devirden sonra durur
    sonuc, ozet = _egit_calistir(veri, calisma, kip, resmi_pth, "1", gecen_sn=100)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert ozet is not None and ozet["bitti"] is False and ozet["tamamlanan_devir"] == 1
    assert (calisma / "SURUYOR").read_text(encoding="utf-8").strip() == "2"
    assert (calisma / "son.pth").is_file()
    assert not (calisma / "BITTI").exists() and not (calisma / "ek_bas.pth").exists()

    # 2. bacak: kaldığı yerden devam eder ve biter
    sonuc, ozet = _egit_calistir(veri, calisma, kip, resmi_pth, "19800", gecen_sn=0)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert ozet["bitti"] is True and ozet["tamamlanan_devir"] == 2 and ozet["bu_calismada"] == 1
    assert ozet["resmi_pth_sha256"] == forklift_modeli.dosya_ozeti(resmi_pth)
    assert (calisma / "BITTI").is_file() and not (calisma / "SURUYOR").exists()
    ek_bas_yolu = calisma / "ek_bas.pth"
    kayit = torch.load(ek_bas_yolu, map_location="cpu", weights_only=True)
    assert (kayit["boy"], kayit["kip"], kayit["devir"]) == ("tiny", kip, 2)

    # Bitmiş iş yeniden çalıştırılırsa hiçbir şey yapmaz
    sonuc, ozet = _egit_calistir(veri, calisma, kip, resmi_pth, "19800", gecen_sn=0)
    assert sonuc.returncode == 0 and ozet.get("zaten_bitmisti") is True

    # Başka yapılandırmanın ara kaydıyla devam etmez (2)
    baska = tmp_path / "baska"
    baska.mkdir()
    (baska / "son.pth").write_bytes((calisma / "son.pth").read_bytes())
    sonuc, _ = _egit_calistir(veri, baska, kip, resmi_pth, "19800", gecen_sn=0, devir=3)
    assert sonuc.returncode == 2, sonuc.stdout + sonuc.stderr

    # Donuk tensörler (BN istatistikleri dahil) resmi değerleriyle bit bit aynı
    resmi = forklift_modeli.resmi_model("tiny", resmi_pth)
    ilk = forklift_modeli.DonukYOLOX(resmi, "tiny", kip)
    ilk_durum = ilk.state_dict()
    egitilen = set(ilk.egitilen_anahtarlar())
    ara = torch.load(calisma / "son.pth", map_location="cpu", weights_only=False)
    for ad in ("model", "ema"):
        farkli = [
            a for a in ilk_durum if a not in egitilen and not torch.equal(ara[ad][a], ilk_durum[a])
        ]
        assert farkli == [], (ad, farkli[:5])
    ek = forklift_modeli.ek_bas_yukle(resmi, "tiny", kip, ek_bas_yolu)
    baska_kip = "v2" if kip == "v1" else "v1"
    with pytest.raises(forklift_modeli.ForkliftHatasi):
        forklift_modeli.ek_bas_yukle(resmi, "tiny", baska_kip, ek_bas_yolu)

    # Eğitilmiş ek başla birleşik model: eski sınıflar yine resmi modelle aynı
    # Kart kipi taşır (iş akışının kartı gibi): v3'te kutu karşılaştırması ona göre
    aday = forklift_modeli.disa_aktar(resmi, ek, kip, "tiny", tmp_path / "aday.onnx", {"kip": kip})
    denetim = forklift_modeli.denetle(
        aday, resmi_onnx, sorted((veri / "egitim").glob("*.jpg")), "tiny"
    )
    assert denetim["gecti"], denetim["nedenler"]

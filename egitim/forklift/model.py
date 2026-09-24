"""Forklift ek başı: model kurma, birleştirme, ONNX dışa aktarımı ve denetim.

Tasarım (ortak.py): resmi YOLOX COCO modeli (0.1.1rc0) DONDURULUR ve hiç
değişmez. Yanına iki yeni sınıfı (forklift, el transpaleti) öğrenen küçük bir
"ek baş" eğitilir; ek baş, resmi başın kendi ara özniteliklerini okur.
Dışa aktarımda ikisi TEK ONNX'te birleşir:

* kutular resmi başın ham kutu çıktısıdır (reg_preds); yalnız v3'te,
  forklift puanının bütün eşlenen resmi puanları geçtiği çapada kutu ek başın
  kendi kutu dalından gelir,
* insan, tır, araba ve otobüs puanları resmi modelin nesne x sınıf puanıdır,
* forklift ve el transpaleti puanları ek baştan gelir.

Uygulamanın sözleşmesi (backend/app/analiz/tespit.py) değişmez: çıktı
[1, A, 5 + 6]; sütun 4 "nesne" = sınıf puanlarının en büyüğü, sütun 5 + i =
puan_i / nesne. Uygulama nesne x sınıf çarpımını kullandığı için eski
sınıfların puanı resmi modelinkiyle aynı kalır; tek davranış farkı, forklift
puanının eski puanları geçtiği çapalarda etiketin "forklift" olmasıdır.

Kişi önceliği (k): birleşik forklift puanı, resmi modelin o çapadaki insan
puanıyla bastırılır: forklift x (1 - insan)^k. k = 0 düz birleştirmedir;
k = 1, resmi puanı 0.5 ve üstü her insanı korur (her yerde "forklift" diyen
bozuk bir ek başla bile); k = 2 eşiği 0.382'ye indirir. Transpalet sütunu
değişmez (uygulama onu eşlemez).

Kipler: v1 yalnız iki 1x1 katman (sınıf + nesne) öğrenir; v2 ayrıca kendi
sınıf dalını (iki 3x3 evrişim, resmi daldan başlatılır) öğrenir; v3 kendi
kutu dalını (iki 3x3 evrişim + kutu ve nesne katmanı, resmi daldan
başlatılır) öğrenir, sınıf katmanı v1'deki gibi resmi sınıf özniteliğini okur.

Neden v3 (23.09.2026 tam eğitimi, çalıştırma 5): v1 ve v2'nin dört adayı LOCO
testinde (2277 görüntü) tek bir doğru forklift tespiti vermedi. İkisinde de kutu
ve nesne puanı resmi modelin DONUK kutu dalından gelir: YOLOX sınıf hedefini o
kutunun gerçek kutuyla IoU'su yapar (eşleşen çapalarda ortalama en çok ~0,57),
1x1 nesne katmanı donuk öznitelikten forklifti ayıramaz (nesne kaybı düşmedi).
Resmi kutunun iyi oturduğu Open Images forklift fotoğraflarında bile forklift
puanının medyanı 0,06 kaldı; sınıf dalını da eğiten v2 v1'den farksızdı. v3 kutu
ve nesne dalını da öğrenir (docs/ILERLEME, forklift modeli).

Komut satırı:
    python egitim/forklift/model.py disa-aktar --boy tiny --kip v1
        --resmi-pth yolox_tiny.pth [--ek-bas W/ek_bas.pth] --cikti aday.onnx
        [--kart kart.json] [--kisi-onceligi 1]
    python egitim/forklift/model.py denetle --boy tiny --onnx aday.onnx
        --resmi-onnx models/yolox_tiny.onnx --goruntu KLASOR [--sinir 20]

Çıkış kodu: 0 tamam, 1 denetimden geçmedi, 2 girdi hatası.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import pickle
import sys
import warnings
from collections.abc import Iterable, Sequence
from pathlib import Path

import cv2
import numpy as np
import onnx
import onnxruntime
import torch
from ortak import BOYLAR, CIKIS_SINIFLARI, DALSAN_SINIFLARI, EK_SINIFLAR, KIPLER, RESMI_SATIRLAR
from torch import nn
from yolox.models import YOLOPAFPN, YOLOX, YOLOXHead
from yolox.models.network_blocks import SiLU
from yolox.utils import replace_module

# YOLOX'un sabit katman genişlikleri (YOLOPAFPN / YOLOXHead in_channels)
_GIRIS_KANALLARI = [256, 512, 1024]

# YOLOX Exp.get_model'deki init_yolo ayarı
BN_EPS = 1e-3
BN_MOMENTUM = 0.03

# Yeni sınıf katmanının başlangıç olasılığı (YOLOX initialize_biases(1e-2))
ONCUL_OLASILIK = 0.01

# Her kipte ek başın eğitilen bölümleri; geri kalan her şey donuktur.
EGITILEN_BOLUMLER = {
    "v1": ("cls_preds", "obj_preds"),
    "v2": ("cls_convs", "cls_preds", "obj_preds"),
    "v3": ("reg_convs", "reg_preds", "obj_preds", "cls_preds"),
}
# Ek başın kutusunu kullanan kipler (birleşik modelde forklift kazanınca)
KENDI_KUTUSU = ("v3",)

# Kişi önceliği: forklift puanı x (1 - resmi insan puanı)^k (modül belgesi)
KISI_ONCELIGI_VARSAYILAN = 1
KISI_ONCELIGI_SECENEKLERI = (0, 1, 2)

# denetle: eski sınıf puanları ve kutular resmi ONNX'e bu kadar yakın olmalı
SKOR_TOLERANSI = 1e-5
KUTU_TOLERANSI = 1e-4
# Olasılık sütunları [0, 1] aralığında olmalı; bölmenin yuvarlama payı
_OLASILIK_PAYI = 1e-6
# v3 denetimi: forklift puanı eski puanların en büyüğüne bu kadar yakınsa çapa
# "belirsiz" sayılır (sütunlar nesne x sınıf olarak yeniden kurulduğu için
# karşılaştırma yuvarlama payı taşır); belirsiz çapanın kutusu karşılaştırılmaz.
_KAZANMA_PAYI = 1e-6

GORUNTU_UZANTILARI = (".jpg", ".jpeg", ".png", ".bmp")


class ForkliftHatasi(Exception):
    """Girdi ya da uyum hatası: eksik/bozuk dosya, yanlış boy ya da kip.

    Komut satırı bunu 2 çıkış koduna çevirir; denetimden geçmemek 1'dir.
    """


def _eski_ve_yeni_sira() -> tuple[tuple[str, ...], list[int]]:
    """Resmi modelden gelen sınıflar ve birleşik sütunların kaynak sırası.

    Birleşik model önce resmi sınıfları (CIKIS_SINIFLARI'ndaki sırayla), sonra
    ek baş sınıflarını (EK_SINIFLAR sırasıyla) hesaplar; bu fonksiyon o
    diziden CIKIS_SINIFLARI sırasını kuran indeksleri verir.
    """
    eski = tuple(ad for ad in CIKIS_SINIFLARI if ad in RESMI_SATIRLAR)
    kaynak = list(eski) + list(EK_SINIFLAR)
    eksik = [ad for ad in CIKIS_SINIFLARI if ad not in kaynak]
    if eksik:
        raise ForkliftHatasi(f"CIKIS_SINIFLARI'nda kaynağı olmayan sınıf: {eksik}")
    return eski, [kaynak.index(ad) for ad in CIKIS_SINIFLARI]


ESKI_SINIFLAR, _CIKIS_SIRASI = _eski_ve_yeni_sira()


def _boy_ayari(boy: str) -> dict:
    try:
        return BOYLAR[boy]
    except KeyError:
        raise ForkliftHatasi(f"bilinmeyen boy {boy!r}; seçenekler: {', '.join(BOYLAR)}") from None


def _kip_dogrula(kip: str) -> None:
    if kip not in KIPLER:
        raise ForkliftHatasi(f"bilinmeyen kip {kip!r}; seçenekler: {', '.join(KIPLER)}")


def bn_ayari(modul: nn.Module) -> nn.Module:
    """Her BatchNorm2d: eps 1e-3, momentum 0.03 (YOLOX init_yolo).

    Elle kurulan modelde bu ayar yapılmazsa çıktılar resmi ONNX'ten ayrılır:
    PyTorch'un varsayılan eps'i (1e-5) her BN katmanında küçük bir sapma üretir.
    """
    for alt in modul.modules():
        if isinstance(alt, nn.BatchNorm2d):
            alt.eps = BN_EPS
            alt.momentum = BN_MOMENTUM
    return modul


def resmi_mimari(boy: str, sinif_sayisi: int = 80) -> YOLOX:
    """Resmi YOLOX mimarisi, AĞIRLIKSIZ (rastgele başlangıç), BN ayarlı, eval kipinde.

    Ağırlık gerektirmeyen yapı testleri de bunu kullanır.
    """
    ayar = _boy_ayari(boy)
    omurga = YOLOPAFPN(ayar["derinlik"], ayar["genislik"], in_channels=_GIRIS_KANALLARI, act="silu")
    bas = YOLOXHead(sinif_sayisi, ayar["genislik"], in_channels=_GIRIS_KANALLARI, act="silu")
    model = YOLOX(omurga, bas)
    bn_ayari(model)
    model.eval()
    return model


def _torch_oku(yol: Path, ne: str) -> object:
    """Yalnız tensör ve düz veri içeren bir .pth dosyasını güvenle okur."""
    if not yol.is_file():
        raise ForkliftHatasi(f"{ne} bulunamadı: {yol}")
    try:
        return torch.load(yol, map_location="cpu", weights_only=True)
    except (RuntimeError, OSError, EOFError, pickle.UnpicklingError) as hata:
        raise ForkliftHatasi(f"{ne} okunamadı: {yol} ({hata})") from hata


def resmi_model(boy: str, pth: str | Path) -> YOLOX:
    """Resmi YOLOX COCO modeli (80 sınıf), ağırlıkları yüklü, eval kipinde."""
    model = resmi_mimari(boy)
    yol = Path(pth)
    kayit = _torch_oku(yol, "resmi ağırlık dosyası")
    durum = kayit.get("model") if isinstance(kayit, dict) else None
    if not isinstance(durum, dict):
        raise ForkliftHatasi(f"{yol} resmi YOLOX ağırlık dosyası değil ('model' anahtarı yok)")
    try:
        model.load_state_dict(durum)
    except RuntimeError as hata:
        raise ForkliftHatasi(f"{yol} '{boy}' boyuna uymuyor: {hata}") from hata
    model.eval()
    return model


def ek_bas_olustur(resmi: YOLOX, boy: str) -> YOLOXHead:
    """İki sınıflı ek baş; cls_preds dışındaki her tensör resmi baştan kopyalanır.

    Yeni sınıf katmanı (cls_preds) YOLOX'un kendi başlangıcını alır: ağırlık
    normal(0, 0.01), eğilim -log((1 - 0.01) / 0.01). Nesne katmanı (obj_preds)
    resmi nesne katmanından başlar.
    """
    ayar = _boy_ayari(boy)
    bas = YOLOXHead(len(EK_SINIFLAR), ayar["genislik"], in_channels=_GIRIS_KANALLARI, act="silu")
    bn_ayari(bas)
    resmi_durum = resmi.head.state_dict()
    yeni_durum = bas.state_dict()
    for anahtar, deger in yeni_durum.items():
        if anahtar.startswith("cls_preds."):
            continue
        kaynak = resmi_durum.get(anahtar)
        if kaynak is None or kaynak.shape != deger.shape:
            raise ForkliftHatasi(f"resmi model '{boy}' boyuna uymuyor (baş tensörü {anahtar})")
        yeni_durum[anahtar] = kaynak.detach().clone()
    bas.load_state_dict(yeni_durum)
    egilim = -math.log((1 - ONCUL_OLASILIK) / ONCUL_OLASILIK)
    for evrisim in bas.cls_preds:
        nn.init.normal_(evrisim.weight, mean=0.0, std=0.01)
        nn.init.constant_(evrisim.bias, egilim)
    return bas


def ek_bas_yukle(resmi: YOLOX, boy: str, kip: str, yol: str | Path) -> YOLOXHead:
    """egit.py'nin yazdığı ek_bas.pth'yi ({"ek_bas", "boy", "kip", "devir"}) yükler."""
    _kip_dogrula(kip)
    yol = Path(yol)
    kayit = _torch_oku(yol, "ek baş dosyası")
    if not isinstance(kayit, dict) or not isinstance(kayit.get("ek_bas"), dict):
        raise ForkliftHatasi(f"{yol} bir ek baş dosyası değil ('ek_bas' anahtarı yok)")
    if kayit.get("boy") != boy or kayit.get("kip") != kip:
        raise ForkliftHatasi(
            f"{yol} {kayit.get('boy')}-{kayit.get('kip')} için eğitilmiş; istenen {boy}-{kip}"
        )
    bas = ek_bas_olustur(resmi, boy)
    try:
        bas.load_state_dict(kayit["ek_bas"])
    except RuntimeError as hata:
        raise ForkliftHatasi(f"{yol} ek başa uymuyor: {hata}") from hata
    bas.eval()
    return bas


class DonukYOLOX(YOLOX):
    """Eğitim modeli: resmi omurga (donuk) + ek baş; yalnız kipin bölümleri öğrenir.

    Omurga resmi modelle PAYLAŞILIR (kopyalanmaz). Donuk her modül eğitim
    kipinde bile eval'de kalır: BN istatistikleri yalnız okunur, hiç
    güncellenmez; böylece eğitimde görülen öznitelikler dışa aktarılan
    modeldekiyle aynıdır.
    """

    def __init__(self, resmi: YOLOX, boy: str, kip: str) -> None:
        _kip_dogrula(kip)
        super().__init__(resmi.backbone, ek_bas_olustur(resmi, boy))
        self.boy = boy
        self.kip = kip
        for parametre in self.parameters():
            parametre.requires_grad_(False)
        for bolum in EGITILEN_BOLUMLER[kip]:
            for parametre in getattr(self.head, bolum).parameters():
                parametre.requires_grad_(True)
        self.train()

    def egitilen_parametreler(self) -> list[nn.Parameter]:
        """Eğitilen parametreler (optimizasyona yalnız bunlar girer)."""
        return [parametre for parametre in self.parameters() if parametre.requires_grad]

    def egitilen_anahtarlar(self) -> list[str]:
        """Eğitimle değişebilen durum anahtarları: parametreler ve BN istatistikleri."""
        onekler = tuple(f"head.{bolum}." for bolum in EGITILEN_BOLUMLER[self.kip])
        return [anahtar for anahtar in self.state_dict() if anahtar.startswith(onekler)]

    def ek_bas_durumu(self) -> dict[str, torch.Tensor]:
        """Yalnız ek başın durumu (kopya; sonraki eğitim adımları değiştirmez)."""
        durum = self.head.state_dict()
        for anahtar, deger in durum.items():
            durum[anahtar] = deger.detach().clone()
        return durum

    def train(self, mode: bool = True) -> DonukYOLOX:
        super().train(mode)
        if mode:
            # Altında hiç eğitilen parametre olmayan her modül (omurga, stems,
            # reg_convs; v1'de cls_convs da) eval'e döner: donuk BN'ler
            # istatistik biriktirmez.
            for modul in self.modules():
                if not any(parametre.requires_grad for parametre in modul.parameters()):
                    modul.train(False)
        return self

    def forward(self, x: torch.Tensor, targets: torch.Tensor | None = None):
        if not self.training:
            return super().forward(x)
        if targets is None:
            raise ValueError("eğitim kipinde hedef kutular (targets) gerekli")
        # Omurga donuk: gradyan tutmaya gerek yok (bellek ve süre kazancı).
        with torch.no_grad():
            fpn = self.backbone(x)
        kayip, iou, nesne, sinif, l1, on_plan = self.head(fpn, targets, x)
        return {
            "total_loss": kayip,
            "iou_loss": iou,
            "l1_loss": l1,
            "conf_loss": nesne,
            "cls_loss": sinif,
            "num_fg": on_plan,
        }


def _kisi_onceligi_dogrula(kisi_onceligi: int) -> None:
    if isinstance(kisi_onceligi, bool) or not isinstance(kisi_onceligi, int) or kisi_onceligi < 0:
        raise ForkliftHatasi(f"kişi önceliği 0 ya da pozitif tam sayı olmalı: {kisi_onceligi!r}")


class Birlesik(nn.Module):
    """Resmi model + ek baş = tek model; çıktı [B, A, 5 + len(CIKIS_SINIFLARI)].

    Seviye başına (adım 8, 16, 32): resmi stem, sınıf ve kutu dalları; kutu
    resmi reg_preds. Eski puan = sigmoid(resmi nesne) x sigmoid(resmi sınıf);
    yeni puan = sigmoid(ek nesne) x sigmoid(ek sınıf). v1'de ek sınıf katmanı
    resmi sınıf özniteliğini, v2'de ek başın kendi sınıf dalını okur; ek
    nesne katmanı v1 ve v2'de resmi kutu özniteliğini okur. v3'te ek başın
    kendi kutu dalı vardır: ek nesne katmanı onun özniteliğini okur ve
    forklift puanının (kişi önceliğinden sonra) bütün eski puanları KESİN
    geçtiği çapada kutu da ondan gelir; öteki her çapada kutu resmi kutudur.
    Kişi önceliği k ile forklift puanı (1 - resmi insan puanı)^k ile çarpılır
    (k = 0: düz).
    """

    def __init__(
        self,
        resmi: YOLOX,
        ek_bas: YOLOXHead,
        kip: str,
        kisi_onceligi: int = KISI_ONCELIGI_VARSAYILAN,
    ) -> None:
        super().__init__()
        _kip_dogrula(kip)
        _kisi_onceligi_dogrula(kisi_onceligi)
        self.omurga = resmi.backbone
        self.resmi_bas = resmi.head
        self.ek_bas = ek_bas
        self.kip = kip
        self.kisi_onceligi = kisi_onceligi
        self._eski_satirlar = [RESMI_SATIRLAR[ad] for ad in ESKI_SINIFLAR]
        self._cikis_sirasi = list(_CIKIS_SIRASI)
        self._insan = ESKI_SINIFLAR.index("person")
        self._forklift = EK_SINIFLAR.index("forklift")

    def _kisi_onceligi_uygula(self, eski: torch.Tensor, yeni: torch.Tensor) -> torch.Tensor:
        """Forklift puanı x (1 - insan puanı)^k; üs, kesin olsun diye çarpımla alınır."""
        koruma = 1.0 - eski[:, self._insan : self._insan + 1]
        bastirma = koruma
        for _ in range(self.kisi_onceligi - 1):
            bastirma = bastirma * koruma
        parcalar = [yeni[:, i : i + 1] for i in range(yeni.shape[1])]
        parcalar[self._forklift] = parcalar[self._forklift] * bastirma
        return torch.cat(parcalar, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        fpn = self.omurga(x)
        cikislar = []
        for k, girdi in enumerate(fpn):
            h = self.resmi_bas.stems[k](girdi)
            sinif_ozniteligi = self.resmi_bas.cls_convs[k](h)
            kutu_ozniteligi = self.resmi_bas.reg_convs[k](h)
            kutu = self.resmi_bas.reg_preds[k](kutu_ozniteligi)
            nesne = self.resmi_bas.obj_preds[k](kutu_ozniteligi).sigmoid()
            sinif = self.resmi_bas.cls_preds[k](sinif_ozniteligi).sigmoid()
            if self.kip == "v2":
                yeni_sinif = self.ek_bas.cls_preds[k](self.ek_bas.cls_convs[k](h)).sigmoid()
            else:
                yeni_sinif = self.ek_bas.cls_preds[k](sinif_ozniteligi).sigmoid()
            if self.kip in KENDI_KUTUSU:
                ek_kutu_ozniteligi = self.ek_bas.reg_convs[k](h)
                ek_kutu = self.ek_bas.reg_preds[k](ek_kutu_ozniteligi)
                yeni_nesne = self.ek_bas.obj_preds[k](ek_kutu_ozniteligi).sigmoid()
            else:
                yeni_nesne = self.ek_bas.obj_preds[k](kutu_ozniteligi).sigmoid()
            eski = nesne * sinif[:, self._eski_satirlar]
            yeni = yeni_nesne * yeni_sinif
            if self.kisi_onceligi:
                yeni = self._kisi_onceligi_uygula(eski, yeni)
            if self.kip in KENDI_KUTUSU:
                forklift = yeni[:, self._forklift : self._forklift + 1]
                kutu = torch.where(forklift > eski.amax(1, keepdim=True), ek_kutu, kutu)
            puan = torch.cat([eski, yeni], 1)[:, self._cikis_sirasi]
            ust = puan.amax(1, keepdim=True).clamp_min(1e-9)
            cikislar.append(torch.cat([kutu, ust, puan / ust], 1))
        # YOLOXHead gibi: önce adım 8, satır satır
        return torch.cat([c.flatten(start_dim=2) for c in cikislar], 2).permute(0, 2, 1)


def ust_veri(kart: dict) -> dict[str, str]:
    """Birleşik ONNX'in üst verisi (uygulama "dalsan_classes"ı okur)."""
    return {
        "dalsan_classes": json.dumps(DALSAN_SINIFLARI),
        "dalsan_cikis_siniflari": json.dumps(list(CIKIS_SINIFLARI)),
        "dalsan_model_karti": json.dumps(kart, ensure_ascii=False),
    }


def disa_aktar(
    resmi: YOLOX,
    ek_bas: YOLOXHead,
    kip: str,
    boy: str,
    cikti: str | Path,
    kart: dict,
    kisi_onceligi: int = KISI_ONCELIGI_VARSAYILAN,
) -> Path:
    """Resmi model + ek başı tek ONNX'e yazar (opset 11, sabit [1, 3, S, S] girdi).

    Model kartına dışa aktarılan kip ("kip") ve kullanılan kişi önceliği
    ("kisi_onceligi") her zaman yazılır; kartta başka bir kip yazıyorsa dışa
    aktarım durur (denetim kutu karşılaştırmasını karttaki kipe göre yapar).
    Verilen modeller değişmez: dışa aktarım bir kopya üzerinde yapılır (SiLU
    değişimi modülleri yerinde değiştirir).
    """
    girdi = _boy_ayari(boy)["girdi"]
    if kart.get("kip", kip) != kip:
        raise ForkliftHatasi(f"model kartında kip {kart['kip']!r} yazıyor; dışa aktarılan {kip!r}")
    kart = {**kart, "kip": kip, "kisi_onceligi": kisi_onceligi}
    birlesik = copy.deepcopy(Birlesik(resmi, ek_bas, kip, kisi_onceligi))
    birlesik = replace_module(birlesik, nn.SiLU, SiLU)
    birlesik.eval()
    hedef = Path(cikti)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = hedef.with_name(hedef.name + ".part")
    try:
        with torch.no_grad(), warnings.catch_warnings():
            # dynamo=False bilinçli (resmi YOLOX dışa aktarımıyla aynı yol, opset 11);
            # eski dışa aktarıcının "legacy" uyarıları yalnız gürültü.
            warnings.simplefilter("ignore", DeprecationWarning)
            torch.onnx.export(
                birlesik,
                torch.zeros(1, 3, girdi, girdi),
                str(gecici),
                input_names=["images"],
                output_names=["output"],
                opset_version=11,
                dynamo=False,
                do_constant_folding=True,
            )
        model = onnx.load(str(gecici))
        for anahtar, deger in ust_veri(kart).items():
            ozellik = model.metadata_props.add()
            ozellik.key = anahtar
            ozellik.value = deger
        onnx.checker.check_model(model)
        onnx.save(model, str(hedef))
    finally:
        gecici.unlink(missing_ok=True)
    return hedef


def on_isle(kare: np.ndarray, girdi: int) -> np.ndarray:
    """Uygulamanın ön işlemesi (tespit.py Tespitci._on_isle) ile birebir aynı.

    Sol üste yaslı ölçekleme, 114 gri dolgu, BGR, 0-255 float32, [1, 3, S, S].
    """
    dolgulu = np.full((girdi, girdi, 3), 114, dtype=np.uint8)
    oran = min(girdi / kare.shape[0], girdi / kare.shape[1])
    yeni_boyut = (int(kare.shape[1] * oran), int(kare.shape[0] * oran))
    kucultulmus = cv2.resize(kare, yeni_boyut, interpolation=cv2.INTER_LINEAR)
    dolgulu[: yeni_boyut[1], : yeni_boyut[0]] = kucultulmus
    return np.ascontiguousarray(dolgulu.transpose(2, 0, 1).astype(np.float32)[np.newaxis])


def _oturum(yol: Path) -> onnxruntime.InferenceSession:
    if not yol.is_file():
        raise ForkliftHatasi(f"ONNX dosyası bulunamadı: {yol}")
    try:
        return onnxruntime.InferenceSession(str(yol), providers=["CPUExecutionProvider"])
    except Exception as hata:  # onnxruntime kendi hata tipini garanti etmiyor
        raise ForkliftHatasi(f"ONNX dosyası açılamadı: {yol} ({hata!r})") from hata


def _kart_kipi(oturum: onnxruntime.InferenceSession) -> str | None:
    """Model kartındaki kip ("v1", "v2", "v3"); kart yoksa ya da okunamıyorsa None."""
    ust = dict(oturum.get_modelmeta().custom_metadata_map or {})
    try:
        kart = json.loads(ust.get("dalsan_model_karti", "null"))
    except ValueError:
        return None
    kip = kart.get("kip") if isinstance(kart, dict) else None
    return kip if kip in KIPLER else None


def _ust_veri_denetimi(oturum: onnxruntime.InferenceSession) -> list[str]:
    """Birleşik modelin üst verisi ortak.py'deki sabitlerle aynı mı?"""
    ust = dict(oturum.get_modelmeta().custom_metadata_map or {})
    nedenler = []
    beklenen = {
        "dalsan_classes": DALSAN_SINIFLARI,
        "dalsan_cikis_siniflari": list(CIKIS_SINIFLARI),
    }
    for anahtar, deger in beklenen.items():
        try:
            okunan = json.loads(ust.get(anahtar, "null"))
        except ValueError:
            okunan = None
        if okunan != deger:
            nedenler.append(f"üst veri {anahtar} beklenenden farklı: {ust.get(anahtar)!r}")
    return nedenler


def denetle(
    onnx_yolu: str | Path,
    resmi_onnx_yolu: str | Path,
    goruntuler: Iterable[str | Path],
    boy: str,
) -> dict:
    """Birleşik ONNX resmi modelin davranışını koruyor mu? (uygulamanın ön işlemesiyle)

    (a) Her görüntüde, HER çapada eski sınıf puanları (nesne x sınıf; person,
        truck, car, bus) resmi ONNX'in COCO 0/7/2/5 satırlarıyla 1e-5 içinde,
        kutu sütunları 0-3 1e-4 içinde aynı olmalı. Kendi kutusu olan kipte
        (v3, kip model kartından okunur) kutu, forkliftin kazanmadığı her
        çapada karşılaştırılır; kazandığı çapalar "ek_kutulu_capa"da sayılır.
    (b) Çıktı [1, A, 5 + 6], değerler sonlu, nesne ve sınıf sütunları [0, 1].
    (c) Üst veri ortak.py'deki sınıf sabitleriyle aynı.
    """
    girdi = _boy_ayari(boy)["girdi"]
    birlesik = _oturum(Path(onnx_yolu))
    resmi = _oturum(Path(resmi_onnx_yolu))
    sonuc: dict = {
        "en_buyuk_skor_farki": 0.0,
        "en_buyuk_kutu_farki": 0.0,
        "goruntu": 0,
        "gecti": False,
        "yeni_sinif_en_buyuk_puan": {ad: 0.0 for ad in EK_SINIFLAR},
        "ek_kutulu_capa": 0,
        "nedenler": [],
    }
    nedenler: list[str] = sonuc["nedenler"]
    for ad, oturum in (("birleşik", birlesik), ("resmi", resmi)):
        sekil = list(oturum.get_inputs()[0].shape)
        if sekil != [1, 3, girdi, girdi]:
            nedenler.append(f"{ad} modelin girdisi {sekil}, beklenen [1, 3, {girdi}, {girdi}]")
    if nedenler:
        return sonuc
    nedenler.extend(_ust_veri_denetimi(birlesik))
    kendi_kutusu = _kart_kipi(birlesik) in KENDI_KUTUSU
    forklift_sutunu = 5 + CIKIS_SINIFLARI.index("forklift")

    birlesik_girdi = birlesik.get_inputs()[0].name
    resmi_girdi = resmi.get_inputs()[0].name
    eski_sutunlar = [5 + CIKIS_SINIFLARI.index(ad) for ad in ESKI_SINIFLAR]
    resmi_sutunlar = [5 + RESMI_SATIRLAR[ad] for ad in ESKI_SINIFLAR]
    yeni_sutunlar = {ad: 5 + CIKIS_SINIFLARI.index(ad) for ad in EK_SINIFLAR}
    sutun_sayisi = 5 + len(CIKIS_SINIFLARI)
    for yol in goruntuler:
        yol = Path(yol)
        kare = cv2.imread(str(yol))
        if kare is None:
            raise ForkliftHatasi(f"görüntü okunamadı: {yol}")
        x = on_isle(kare, girdi)
        b = birlesik.run(None, {birlesik_girdi: x})[0]
        r = resmi.run(None, {resmi_girdi: x})[0]
        if b.ndim != 3 or b.shape[0] != 1 or b.shape[2] != sutun_sayisi:
            nedenler.append(
                f"birleşik çıktı biçimi {list(b.shape)}, beklenen [1, A, {sutun_sayisi}]"
            )
            break
        if r.ndim != 3 or r.shape[1] != b.shape[1] or r.shape[2] != 85:
            nedenler.append(
                f"resmi çıktı biçimi {list(r.shape)} birleşikle ({list(b.shape)}) uyumsuz"
            )
            break
        b, r = b[0], r[0]  # [A, sütun]
        if not np.isfinite(b).all():
            nedenler.append(f"{yol.name}: çıktıda sonlu olmayan değer var")
        olasilik = b[:, 4:]
        if float(olasilik.min()) < 0.0 or float(olasilik.max()) > 1.0 + _OLASILIK_PAYI:
            nedenler.append(f"{yol.name}: nesne/sınıf sütunları [0, 1] dışında")
        birlesik_puan = b[:, 4:5] * b[:, eski_sutunlar]
        resmi_puan = r[:, 4:5] * r[:, resmi_sutunlar]
        skor_farki = float(np.abs(birlesik_puan - resmi_puan).max())
        kutu_farklari = np.abs(b[:, :4] - r[:, :4]).max(1)
        if kendi_kutusu:
            forklift_puani = b[:, 4] * b[:, forklift_sutunu]
            eski_en_buyuk = birlesik_puan.max(1)
            sonuc["ek_kutulu_capa"] += int((forklift_puani > eski_en_buyuk + _KAZANMA_PAYI).sum())
            kutu_farklari = kutu_farklari[forklift_puani < eski_en_buyuk - _KAZANMA_PAYI]
        kutu_farki = float(kutu_farklari.max()) if kutu_farklari.size else 0.0
        if not (skor_farki <= SKOR_TOLERANSI and kutu_farki <= KUTU_TOLERANSI):
            nedenler.append(
                f"{yol.name}: resmi modelden sapma (puan {skor_farki:.2e}, kutu {kutu_farki:.2e})"
            )
        sonuc["en_buyuk_skor_farki"] = max(sonuc["en_buyuk_skor_farki"], skor_farki)
        sonuc["en_buyuk_kutu_farki"] = max(sonuc["en_buyuk_kutu_farki"], kutu_farki)
        yeni_puanlar = sonuc["yeni_sinif_en_buyuk_puan"]
        for ad, sutun in yeni_sutunlar.items():
            yeni_puanlar[ad] = max(yeni_puanlar[ad], float((b[:, 4] * b[:, sutun]).max()))
        sonuc["goruntu"] += 1
    if sonuc["goruntu"] == 0 and not nedenler:
        nedenler.append("denetlenecek görüntü yok")
    sonuc["gecti"] = not nedenler
    return sonuc


def dosya_ozeti(yol: Path) -> str:
    """Dosyanın sha256 özeti (onaltılık, küçük harf)."""
    ozet = hashlib.sha256()
    with yol.open("rb") as dosya:
        for parca in iter(lambda: dosya.read(1 << 20), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def _kart_oku(yol: Path) -> dict:
    try:
        kart = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as hata:
        raise ForkliftHatasi(f"model kartı okunamadı: {yol} ({hata})") from hata
    if not isinstance(kart, dict):
        raise ForkliftHatasi(f"model kartı bir JSON nesnesi olmalı: {yol}")
    return kart


def _disa_aktar_komutu(args: argparse.Namespace) -> int:
    resmi = resmi_model(args.boy, args.resmi_pth)
    if args.ek_bas is not None:
        ek_bas = ek_bas_yukle(resmi, args.boy, args.kip, args.ek_bas)
    else:
        torch.manual_seed(0)  # eğitilmemiş ek baş: yeniden üretilebilir başlangıç
        ek_bas = ek_bas_olustur(resmi, args.boy).eval()
    if args.kart is not None:
        kart = _kart_oku(args.kart)
    else:
        kart = {
            "boy": args.boy,
            "kip": args.kip,
            "ek_bas": args.ek_bas.name if args.ek_bas is not None else "egitilmemis",
        }
    yol = disa_aktar(
        resmi, ek_bas, args.kip, args.boy, args.cikti, kart, kisi_onceligi=args.kisi_onceligi
    )
    print(
        f"dışa aktarıldı: {yol} ({args.boy}-{args.kip}, kişi önceliği {args.kisi_onceligi}, "
        f"{yol.stat().st_size} bayt, sha256 {dosya_ozeti(yol)})"
    )
    return 0


def _goruntu_listesi(yol: Path, sinir: int | None) -> list[Path]:
    if yol.is_file():
        goruntuler = [yol]
    elif yol.is_dir():
        goruntuler = sorted(
            p for p in yol.iterdir() if p.is_file() and p.suffix.lower() in GORUNTU_UZANTILARI
        )
    else:
        raise ForkliftHatasi(f"görüntü klasörü bulunamadı: {yol}")
    if sinir is not None:
        goruntuler = goruntuler[:sinir]
    if not goruntuler:
        raise ForkliftHatasi(f"klasörde görüntü yok: {yol}")
    return goruntuler


def _denetle_komutu(args: argparse.Namespace) -> int:
    goruntuler = _goruntu_listesi(args.goruntu, args.sinir)
    sonuc = denetle(args.onnx, args.resmi_onnx, goruntuler, args.boy)
    durum = "GEÇTİ" if sonuc["gecti"] else "GEÇMEDİ"
    print(
        f"denetim {durum}: {sonuc['goruntu']} görüntü, en büyük puan farkı "
        f"{sonuc['en_buyuk_skor_farki']:.2e} (sınır {SKOR_TOLERANSI:g}), en büyük kutu farkı "
        f"{sonuc['en_buyuk_kutu_farki']:.2e} (sınır {KUTU_TOLERANSI:g})"
    )
    for neden in sonuc["nedenler"]:
        print(f"  - {neden}")
    print("DENETIM_JSON " + json.dumps(sonuc))
    return 0 if sonuc["gecti"] else 1


def _pozitif_tam(deger: str) -> int:
    sayi = int(deger)
    if sayi <= 0:
        raise argparse.ArgumentTypeError("pozitif bir tam sayı olmalı")
    return sayi


def komut_satiri() -> argparse.ArgumentParser:
    ayristirici = argparse.ArgumentParser(
        description="Forklift ek başı: birleşik ONNX dışa aktarımı ve resmi modele göre denetim."
    )
    alt = ayristirici.add_subparsers(dest="komut", required=True)

    disa = alt.add_parser("disa-aktar", help="resmi model + ek baş -> tek ONNX")
    disa.add_argument("--boy", choices=tuple(BOYLAR), required=True)
    disa.add_argument("--kip", choices=KIPLER, required=True)
    disa.add_argument("--resmi-pth", type=Path, required=True, help="resmi YOLOX .pth")
    disa.add_argument(
        "--ek-bas", type=Path, default=None, help="egit.py'nin ek_bas.pth'si (yoksa eğitilmemiş)"
    )
    disa.add_argument("--cikti", type=Path, required=True, help="yazılacak .onnx")
    disa.add_argument("--kart", type=Path, default=None, help="model kartı (JSON nesnesi)")
    disa.add_argument(
        "--kisi-onceligi",
        type=int,
        choices=KISI_ONCELIGI_SECENEKLERI,
        default=KISI_ONCELIGI_VARSAYILAN,
        help="forklift puanı x (1 - resmi insan puanı)^k; 0 = düz birleştirme",
    )

    den = alt.add_parser("denetle", help="birleşik ONNX'i resmi ONNX ile karşılaştırır")
    den.add_argument("--boy", choices=tuple(BOYLAR), required=True)
    den.add_argument("--onnx", type=Path, required=True, help="birleşik .onnx")
    den.add_argument("--resmi-onnx", type=Path, required=True, help="resmi YOLOX .onnx")
    den.add_argument("--goruntu", type=Path, required=True, help="görüntü klasörü (ya da dosya)")
    den.add_argument("--sinir", type=_pozitif_tam, default=None, help="en çok bu kadar görüntü")
    return ayristirici


def main(argv: Sequence[str] | None = None) -> int:
    args = komut_satiri().parse_args(argv)
    try:
        if args.komut == "disa-aktar":
            return _disa_aktar_komutu(args)
        return _denetle_komutu(args)
    except ForkliftHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

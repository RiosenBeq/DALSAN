"""Forklift ek başının işlemcide (CPU) eğitimi (ortak.py, model.py DonukYOLOX).

Resmi YOLOX COCO modeli donuk kalır; yalnız ek başın kip bölümleri öğrenir.
Veri, veri.py hazirla çıktısıdır (COCO biçimi): VERI/egitim/*.jpg ve
VERI/annotations/egitim.json (kategori 1 forklift, 2 pallet_jack).

GitHub'ın işlemcili makinesinde bir iş en çok 6 saat sürer; eğitim bu yüzden
"bacaklara" bölünür. --sure-sn (DALSAN_IS_BASLANGICI ortam değişkenindeki unix
saniyesinden, yoksa sürecin başından sayılır) dolmadan sıradaki devir
sığmayacaksa devir sınırında durulur; sonraki çalıştırma CALISMA/son.pth'ten
kendiliğinden devam eder (her çalıştırma en az bir devir ilerler; başka boy,
kip, devir ya da parti ile yazılmış bir ara kayıttan devam edilmez).

CALISMA klasörü:
    son.pth           her devirden sonra: model, EMA, optimizer, devir, geçmiş
    SURUYOR           bitmemişse: sıradaki devrin (1'den sayılan) numarası
    BITTI, ek_bas.pth bitince: EMA ek başı {"ek_bas", "boy", "kip", "devir"}
    egitim_ozeti.json son çalıştırmanın özeti ve devir devir kayıtlar
    train_log.txt     YOLOX günlüğü (bacaklar boyunca eklenir)

--resmi-pth yalnız ortak.RESMI_AGIRLIKLAR'daki sha256'yla kabul edilir: donuk
model resmi ONNX'le aynı olmalıdır.

    python egitim/forklift/egit.py --veri VERI --boy tiny --kip v1
        --resmi-pth yolox_tiny.pth --calisma W [--devir 30] [--parti N]
        [--sure-sn 19800] [--is-parcacigi 4] [--veri-isci 2] [--tohum 0] [--onbellek]

Çıkış kodu: 0 (bitti ya da süre bütçesinde durdu; sonunda tek satır
"EGITIM_OZETI {json}"), 2 girdi hatası.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import statistics
import sys
import time
import warnings
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import psutil
import torch
from loguru import logger
from model import DonukYOLOX, ForkliftHatasi, dosya_ozeti, resmi_model
from ortak import BOYLAR, EK_SINIFLAR, KIPLER, RESMI_AGIRLIKLAR
from torch import nn
from yolox.core import Trainer
from yolox.data import (
    COCODataset,
    DataLoader,
    InfiniteSampler,
    MosaicDetection,
    TrainTransform,
    YoloBatchSampler,
    worker_init_reset_seed,
)
from yolox.exp import Exp
from yolox.utils import ModelEMA, configure_module

SON_KAYIT = "son.pth"
EK_BAS_DOSYASI = "ek_bas.pth"
BITTI = "BITTI"
SURUYOR = "SURUYOR"
OZET_DOSYASI = "egitim_ozeti.json"

# Çok ölçekli eğitim aralığı (x 32 piksel): tiny 320-512, s 512-704
COKLU_OLCEK = {"tiny": (10, 16), "s": (16, 22)}
EMA_BOZUNMA = 0.9998
# Sıradaki devrin süre tahmini bu payla büyütülür (mozaik kapanışı, dalgalanma)
SURE_PAYI = 1.15
# Adım günlüğü kaç adımda bir yazılır
KAYIT_ARALIGI = 20

# YOLOX kayıp sözlüğünün anahtarları ve günlükteki adları
KAYIP_ADLARI = {
    "total_loss": "toplam",
    "iou_loss": "kutu",
    "conf_loss": "nesne",
    "cls_loss": "sınıf",
    "l1_loss": "l1",
    "num_fg": "ön plan",
}


class EkBasDeneyi(Exp):
    """Kodla kurulan YOLOX deneyi (deney dosyası yok): 2 sınıflı ek baş, donuk resmi model."""

    def __init__(
        self,
        veri: Path,
        boy: str,
        kip: str,
        resmi_pth: Path,
        devir: int,
        veri_isci: int = 2,
        tohum: int = 0,
        onbellek: bool = False,
    ) -> None:
        super().__init__()
        ayar = BOYLAR[boy]
        self.boy = boy
        self.kip = kip
        self.resmi_pth = Path(resmi_pth)
        self.onbellek = onbellek
        # model
        self.num_classes = len(EK_SINIFLAR)
        self.depth = ayar["derinlik"]
        self.width = ayar["genislik"]
        self.input_size = (ayar["girdi"], ayar["girdi"])
        self.test_size = self.input_size
        self.random_size = COKLU_OLCEK[boy]
        # veri
        self.data_dir = str(veri)
        self.train_ann = "egitim.json"
        self.data_num_workers = veri_isci
        # artırma: mozaik açık, karıştırma (mixup) kapalı
        self.mosaic_prob = 1.0
        self.mosaic_scale = (0.5, 1.5)
        self.enable_mixup = False
        self.mixup_prob = 0.0
        self.degrees = 5.0
        self.translate = 0.1
        self.shear = 1.0
        self.hsv_prob = 1.0
        self.flip_prob = 0.5
        # takvim
        self.max_epoch = devir
        self.no_aug_epochs = max(2, devir // 10)
        self.warmup_epochs = 1
        self.basic_lr_per_img = 0.01 / 64.0
        self.min_lr_ratio = 0.05
        self.scheduler = "yoloxwarmcos"
        self.weight_decay = 5e-4
        self.momentum = 0.9
        self.ema = True
        # Eğitim içinde COCO değerlendirmesi yok: ölçüm degerlendir.py'nin işi
        # (uygulamanın kendi dedektörüyle).
        self.eval_interval = devir + 1
        self.print_interval = KAYIT_ARALIGI
        self.save_history_ckpt = False
        self.seed = tohum
        self.exp_name = f"forklift-{boy}-{kip}"

    def get_model(self) -> DonukYOLOX:
        if getattr(self, "model", None) is None:
            self.model = DonukYOLOX(resmi_model(self.boy, self.resmi_pth), self.boy, self.kip)
        self.model.train()
        return self.model

    def get_dataset(self, cache: bool = False, cache_type: str = "ram") -> COCODataset:
        return COCODataset(
            data_dir=self.data_dir,
            json_file=self.train_ann,
            name="egitim",
            img_size=self.input_size,
            preproc=TrainTransform(max_labels=50, flip_prob=self.flip_prob, hsv_prob=self.hsv_prob),
            cache=cache,
            cache_type=cache_type,
        )

    def get_data_loader(
        self, batch_size: int, is_distributed: bool, no_aug: bool = False, cache_img=None
    ) -> DataLoader:
        """YOLOX'un yükleyicisi; işlemcide sabitlenmiş bellek (pin_memory) yok."""
        if self.dataset is None:
            self.dataset = self.get_dataset(cache=self.onbellek, cache_type="ram")
        if len(self.dataset) == 0:
            raise ForkliftHatasi(f"eğitim verisinde görüntü yok: {self.data_dir}")
        mozaik = MosaicDetection(
            dataset=self.dataset,
            mosaic=not no_aug,
            img_size=self.input_size,
            preproc=TrainTransform(
                max_labels=120, flip_prob=self.flip_prob, hsv_prob=self.hsv_prob
            ),
            degrees=self.degrees,
            translate=self.translate,
            mosaic_scale=self.mosaic_scale,
            mixup_scale=self.mixup_scale,
            shear=self.shear,
            enable_mixup=self.enable_mixup,
            mosaic_prob=self.mosaic_prob,
            mixup_prob=self.mixup_prob,
        )
        ornekleyici = InfiniteSampler(len(mozaik), seed=self.seed if self.seed else 0)
        parti_ornekleyici = YoloBatchSampler(
            sampler=ornekleyici, batch_size=batch_size, drop_last=False, mosaic=not no_aug
        )
        return DataLoader(
            mozaik,
            num_workers=self.data_num_workers,
            pin_memory=False,
            batch_sampler=parti_ornekleyici,
            worker_init_fn=worker_init_reset_seed,
        )

    def random_resize(self, data_loader, epoch, rank, is_distributed) -> tuple[int, int]:
        # YOLOX'unki torch.LongTensor(2).cuda() çağırır; işlemcide aynısı, CUDA'sız
        boyut = random.randint(*self.random_size) * 32
        return (boyut, boyut)

    def get_optimizer(self, batch_size: int) -> torch.optim.Optimizer:
        """YOLOX'un üç parametre grubu (BN ağırlığı, ağırlık, eğilim), YALNIZ eğitilenlerle."""
        if "optimizer" not in self.__dict__:
            egitilen = {id(p) for p in self.model.egitilen_parametreler()}
            bn_agirliklari, agirliklar, egilimler = [], [], []
            for ad, modul in self.model.named_modules():
                egilim = getattr(modul, "bias", None)
                if isinstance(egilim, nn.Parameter) and id(egilim) in egitilen:
                    egilimler.append(egilim)
                agirlik = getattr(modul, "weight", None)
                if not isinstance(agirlik, nn.Parameter) or id(agirlik) not in egitilen:
                    continue
                if isinstance(modul, nn.BatchNorm2d) or "bn" in ad:
                    bn_agirliklari.append(agirlik)
                else:
                    agirliklar.append(agirlik)
            gruplar = [
                {"params": bn_agirliklari},
                {"params": agirliklar, "weight_decay": self.weight_decay},
                {"params": egilimler},
            ]
            gruplar = [grup for grup in gruplar if grup["params"]]
            if sum(len(grup["params"]) for grup in gruplar) != len(egitilen):
                raise ForkliftHatasi("eğitilen parametrelerin bir kısmı hiçbir gruba girmedi")
            lr = self.warmup_lr if self.warmup_epochs > 0 else self.basic_lr_per_img * batch_size
            self.optimizer = torch.optim.SGD(gruplar, lr=lr, momentum=self.momentum, nesterov=True)
        return self.optimizer


class EkBasEMA(ModelEMA):
    """Yalnız eğitilen bölümlerin (ve onların BN istatistiklerinin) hareketli ortalaması.

    YOLOX'un ModelEMA'sı tüm durumu ortalar; donuk bir tensörde bile
    d * v + (1 - d) * v yuvarlama yüzünden birkaç bin adımda son bitlerde
    kayabilir. Donuk tensörlere hiç dokunulmaz: resmi değerleriyle kalırlar.
    """

    def __init__(self, model: DonukYOLOX, bozunma: float, guncelleme: int = 0) -> None:
        super().__init__(model, bozunma, guncelleme)
        self._anahtarlar = model.egitilen_anahtarlar()

    def update(self, model: DonukYOLOX) -> None:
        with torch.no_grad():
            self.updates += 1
            d = self.decay(self.updates)
            canli = model.state_dict()
            ortalama = self.ema.state_dict()
            for anahtar in self._anahtarlar:
                deger = ortalama[anahtar]
                if deger.dtype.is_floating_point:
                    deger *= d
                    deger += (1.0 - d) * canli[anahtar].detach()


def _sayi(deger: torch.Tensor | float) -> float:
    """Kayıp değeri (tensör ya da sayı) -> float; grafiğe dokunmadan."""
    if isinstance(deger, torch.Tensor):
        return float(deger.detach())
    return float(deger)


class _IslemciOnYukleyici:
    """YOLOX DataPrefetcher'ın işlemci karşılığı (CUDA akışı yok)."""

    def __init__(self, yukleyici: DataLoader) -> None:
        self._yineleyici = iter(yukleyici)

    def next(self) -> tuple[torch.Tensor, torch.Tensor]:
        girdi, hedef, _, _ = next(self._yineleyici)
        return girdi, hedef


class IslemciEgitici(Trainer):
    """YOLOX Trainer'ın işlemci sürümü: CUDA yok, süre bütçesi, kendiliğinden devam."""

    def __init__(self, exp: EkBasDeneyi, args: argparse.Namespace, is_baslangici: float) -> None:
        super().__init__(exp, args)
        self.device = "cpu"
        self.calisma = Path(self.file_name)
        self.is_baslangici = is_baslangici
        self.calisma_baslangici = time.time()
        self.sure_sn = float(args.sure_sn)
        self.devir_gecmisi: list[dict] = []
        self.bitti = False
        self.bu_calismada = 0
        self._ema_durumu: dict | None = None
        self._ema_guncelleme: int | None = None
        self._devir_sifirla()

    # ---- kurulum ve devam ----

    def before_train(self) -> None:
        torch.set_num_threads(self.args.is_parcacigi)
        model = self.exp.get_model()
        model.to(self.device)
        self.optimizer = self.exp.get_optimizer(self.args.batch_size)
        model = self.resume_train(model)
        # Devam eden bacak aynı görüntü sırasını baştan tekrarlamasın
        self.exp.seed = self.args.tohum + self.start_epoch
        self.no_aug = self.start_epoch >= self.max_epoch - self.exp.no_aug_epochs
        self.train_loader = self.exp.get_data_loader(
            batch_size=self.args.batch_size, is_distributed=False, no_aug=self.no_aug
        )
        self.prefetcher = _IslemciOnYukleyici(self.train_loader)
        self.max_iter = len(self.train_loader)
        self.lr_scheduler = self.exp.get_lr_scheduler(
            self.exp.basic_lr_per_img * self.args.batch_size, self.max_iter
        )
        if self.use_model_ema:
            self.ema_model = EkBasEMA(model, EMA_BOZUNMA)
            if self._ema_durumu is not None:
                self.ema_model.ema.load_state_dict(self._ema_durumu)
            self.ema_model.updates = (
                self._ema_guncelleme
                if self._ema_guncelleme is not None
                else self.max_iter * self.start_epoch
            )
        self.model = model
        egitilen = sum(p.numel() for p in model.egitilen_parametreler())
        toplam = sum(p.numel() for p in model.parameters())
        gecen = time.time() - self.is_baslangici
        logger.info(
            f"forklift ek başı {self.exp.boy}-{self.exp.kip}: eğitilen parametre {egitilen:,} / "
            f"{toplam:,} (gerisi donuk), {len(self.train_loader.dataset)} görüntü, devir başına "
            f"{self.max_iter} adım, parti {self.args.batch_size}, {torch.get_num_threads()} iş "
            f"parçacığı, {self.exp.data_num_workers} veri işçisi"
        )
        logger.info(
            f"devir {self.start_epoch + 1}/{self.max_epoch} ile başlanıyor; süre bütçesi "
            f"{self.sure_sn:.0f} sn, iş başından beri {gecen:.0f} sn geçti"
        )

    def _yapilandirma(self) -> dict:
        return {
            "boy": self.exp.boy,
            "kip": self.exp.kip,
            "devir": self.max_epoch,
            "parti": self.args.batch_size,
        }

    def resume_train(self, model: DonukYOLOX) -> DonukYOLOX:
        yol = self.calisma / SON_KAYIT
        if not yol.exists():
            self.start_epoch = 0
            return model
        try:
            kayit = torch.load(yol, map_location="cpu", weights_only=False)
        except (RuntimeError, OSError, EOFError, pickle.UnpicklingError) as hata:
            raise ForkliftHatasi(f"ara kayıt okunamadı: {yol} ({hata})") from hata
        if not isinstance(kayit, dict):
            raise ForkliftHatasi(f"ara kayıt bu betiğin kaydı değil: {yol}")
        onceki = kayit.get("yapilandirma")
        if onceki != self._yapilandirma():
            raise ForkliftHatasi(
                f"{yol} başka bir eğitimin ara kaydı ({onceki}); bu çalıştırma "
                f"{self._yapilandirma()}. Yeni eğitim için boş bir --calisma klasörü verin."
            )
        model.load_state_dict(kayit["model"])
        self.optimizer.load_state_dict(kayit["optimizer"])
        self._ema_durumu = kayit.get("ema")
        self._ema_guncelleme = kayit.get("ema_guncelleme")
        self.devir_gecmisi = list(kayit.get("devir_gecmisi", []))
        self.start_epoch = int(kayit["devir"])
        logger.info(f"ara kayıttan devam: {yol} ({self.start_epoch} devir tamamlanmış)")
        return model

    # ---- devir döngüsü ----

    def train_in_epoch(self) -> None:
        self._suruyor_yaz(self.start_epoch)
        for devir in range(self.start_epoch, self.max_epoch):
            self.epoch = devir  # YOLOX'un adım sayacı (progress_in_iter) bunu okur
            baslangic = time.time()
            self.before_epoch()
            self.train_in_iter()
            self._devir_kaydi(time.time() - baslangic)
            self.after_epoch()
            self.bu_calismada += 1
            if self.epoch + 1 >= self.max_epoch:
                break
            self._suruyor_yaz(self.epoch + 1)
            sigar, gecen, tahmin = self._sonraki_devir_sigar_mi()
            if not sigar:
                logger.info(
                    f"süre bütçesi: iş başından beri {gecen:.0f} sn geçti, sıradaki devir "
                    f"~{tahmin:.0f} sn sürer, bütçe {self.sure_sn:.0f} sn; devir "
                    f"{self.epoch + 2}/{self.max_epoch} sonraki çalıştırmaya kaldı"
                )
                return
        self._bitir()

    def before_epoch(self) -> None:
        logger.info(f"devir {self.epoch + 1}/{self.max_epoch} başlıyor")
        # YOLOX'un kendi kuralı: son devirlerde mozaik kapanır, L1 kaybı eklenir.
        # (YOLOX burada eval_interval'ı 1 yapar; burada eğitim içi ölçüm yok.)
        if self.epoch + 1 == self.max_epoch - self.exp.no_aug_epochs or self.no_aug:
            logger.info("mozaik kapandı, L1 kutu kaybı eklendi (son devirler)")
            self.train_loader.close_mosaic()
            self.model.head.use_l1 = True
        self._devir_sifirla()

    def train_one_iter(self) -> None:
        # YOLOX'un adımı; GradScaler/autocast (CUDA) olmadan
        baslangic = time.time()
        girdi, hedef = self.prefetcher.next()
        girdi = girdi.to(self.data_type)
        hedef = hedef.to(self.data_type)
        hedef.requires_grad = False
        girdi, hedef = self.exp.preprocess(girdi, hedef, self.input_size)
        veri_hazir = time.time()

        cikti = self.model(girdi, hedef)
        self.optimizer.zero_grad()
        cikti["total_loss"].backward()
        self.optimizer.step()
        if self.use_model_ema:
            self.ema_model.update(self.model)
        lr = self.lr_scheduler.update_lr(self.progress_in_iter + 1)
        for grup in self.optimizer.param_groups:
            grup["lr"] = lr

        bitis = time.time()
        self.meter.update(
            iter_time=bitis - baslangic, data_time=veri_hazir - baslangic, lr=lr, **cikti
        )
        self._adim_sureleri.append(bitis - baslangic)
        self._veri_sureleri.append(veri_hazir - baslangic)
        for anahtar in KAYIP_ADLARI:
            self._kayip_toplami[anahtar] += _sayi(cikti[anahtar])
        self._goruntu += int(girdi.shape[0])
        self._son_lr = lr

    def after_iter(self) -> None:
        if (self.iter + 1) % self.exp.print_interval == 0:
            kayiplar = ", ".join(
                f"{KAYIP_ADLARI[ad]} {olcer.latest:.3f}"
                for ad, olcer in self.meter.items()
                if ad in KAYIP_ADLARI
            )
            logger.info(
                f"devir {self.epoch + 1}/{self.max_epoch}, adım {self.iter + 1}/{self.max_iter}: "
                f"{self.meter['iter_time'].avg:.2f} sn/adım (veri {self.meter['data_time'].avg:.3f}"
                f" sn), {kayiplar}, lr {self.meter['lr'].latest:.2e}, boyut {self.input_size[0]}"
            )
            self.meter.clear_meters()
        # YOLOX: 10 adımda bir yeni rastgele girdi boyutu (çok ölçekli eğitim)
        if (self.progress_in_iter + 1) % 10 == 0:
            self.input_size = self.exp.random_resize(
                self.train_loader, self.epoch, self.rank, self.is_distributed
            )

    def after_epoch(self) -> None:
        # Her devrin sonunda ara kayıt (YOLOX'un latest_ckpt'si ve ölçümü yerine)
        self._kaydet()

    def after_train(self) -> None:
        if self.bitti:
            logger.info(f"eğitim bitti: {self.calisma / EK_BAS_DOSYASI}")
        else:
            logger.info(f"eğitim sürüyor; sıradaki çalıştırma {self.calisma / SON_KAYIT}'ten devam")

    # ---- yardımcılar ----

    def _devir_sifirla(self) -> None:
        self._adim_sureleri: list[float] = []
        self._veri_sureleri: list[float] = []
        self._kayip_toplami: dict[str, float] = defaultdict(float)
        self._goruntu = 0
        self._son_lr = 0.0

    def _devir_kaydi(self, sure: float) -> None:
        adim = len(self._adim_sureleri)
        kayit = {
            "devir": self.epoch + 1,
            "sn": round(sure, 2),
            "adim": adim,
            "adim_sn": round(statistics.fmean(self._adim_sureleri), 4),
            "adim_sn_medyan": round(statistics.median(self._adim_sureleri), 4),
            "veri_sn": round(statistics.fmean(self._veri_sureleri), 4),
            "goruntu_sn": round(self._goruntu / sure, 2),
            "kayip": {ad: round(self._kayip_toplami[ad] / adim, 4) for ad in KAYIP_ADLARI},
            "lr": self._son_lr,
            "mozaik": bool(self.train_loader.batch_sampler.mosaic),
        }
        self.devir_gecmisi.append(kayit)
        kayiplar = ", ".join(
            f"{KAYIP_ADLARI[ad]} {deger:.3f}" for ad, deger in kayit["kayip"].items()
        )
        logger.info(
            f"devir {kayit['devir']}/{self.max_epoch} bitti: {sure:.1f} sn, {adim} adım "
            f"({kayit['adim_sn']:.2f} sn/adım, medyan {kayit['adim_sn_medyan']:.2f}, veri "
            f"{kayit['veri_sn']:.3f} sn), {kayit['goruntu_sn']:.1f} görüntü/sn, ortalama "
            f"kayıp: {kayiplar}, lr {self._son_lr:.2e}"
        )

    def _sonraki_devir_sigar_mi(self) -> tuple[bool, float, float]:
        gecen = time.time() - self.is_baslangici
        son = [kayit["sn"] for kayit in self.devir_gecmisi[-3:]]
        tahmin = max(statistics.fmean(son), son[-1]) * SURE_PAYI
        return gecen + tahmin <= self.sure_sn, gecen, tahmin

    def _yaz_atomik(self, veri: object, yol: Path) -> None:
        # Yarıda kesilen bir kayıt (iş zaman aşımı) eski dosyayı bozmasın
        gecici = yol.with_name(yol.name + ".part")
        torch.save(veri, gecici)
        os.replace(gecici, yol)

    def _kaydet(self) -> None:
        self._yaz_atomik(
            {
                "devir": self.epoch + 1,
                "yapilandirma": self._yapilandirma(),
                "model": self.model.state_dict(),
                "ema": self.ema_model.ema.state_dict() if self.use_model_ema else None,
                "ema_guncelleme": self.ema_model.updates if self.use_model_ema else None,
                "optimizer": self.optimizer.state_dict(),
                "devir_gecmisi": self.devir_gecmisi,
            },
            self.calisma / SON_KAYIT,
        )

    def _suruyor_yaz(self, tamamlanan: int) -> None:
        # SURUYOR: sıradaki devrin (1'den sayılan) numarası
        (self.calisma / SURUYOR).write_text(f"{tamamlanan + 1}\n", encoding="utf-8")

    def _bitir(self) -> None:
        kaynak = self.ema_model.ema if self.use_model_ema else self.model
        self._yaz_atomik(
            {
                "ek_bas": kaynak.ek_bas_durumu(),
                "boy": self.exp.boy,
                "kip": self.exp.kip,
                "devir": self.max_epoch,
            },
            self.calisma / EK_BAS_DOSYASI,
        )
        (self.calisma / SURUYOR).unlink(missing_ok=True)
        (self.calisma / BITTI).write_text(
            datetime.now(UTC).isoformat(timespec="seconds") + "\n", encoding="utf-8"
        )
        self.bitti = True

    def ozet(self) -> dict:
        tamamlanan = len(self.devir_gecmisi)
        return {
            "boy": self.exp.boy,
            "kip": self.exp.kip,
            "devir": self.max_epoch,
            "parti": self.args.batch_size,
            "goruntu": len(self.train_loader.dataset),
            "adim_devir": self.max_iter,
            "tamamlanan_devir": tamamlanan,
            "bu_calismada": self.bu_calismada,
            "bitti": self.bitti,
            "sonraki_devir": None if self.bitti else tamamlanan + 1,
            "calisma_sn": round(time.time() - self.calisma_baslangici, 1),
            "is_baslangicindan_sn": round(time.time() - self.is_baslangici, 1),
            "sure_sn": self.sure_sn,
            "is_parcacigi": torch.get_num_threads(),
            "veri_isci": self.exp.data_num_workers,
            "onbellek": self.exp.onbellek,
            "son_devir": self.devir_gecmisi[-1] if self.devir_gecmisi else None,
        }


def is_baslangici_oku() -> float:
    """Süre bütçesinin başlangıcı: DALSAN_IS_BASLANGICI (unix saniyesi) ya da süreç başı."""
    ham = os.environ.get("DALSAN_IS_BASLANGICI", "").strip()
    if not ham:
        return psutil.Process().create_time()
    try:
        deger = float(ham)
    except ValueError:
        raise ForkliftHatasi(f"DALSAN_IS_BASLANGICI bir unix saniyesi olmalı: {ham!r}") from None
    if deger > time.time() + 60:
        raise ForkliftHatasi(
            f"DALSAN_IS_BASLANGICI gelecekte: {ham!r} (saniye yerine milisaniye mi yazıldı?)"
        )
    return deger


def _pozitif_tam(deger: str) -> int:
    sayi = int(deger)
    if sayi <= 0:
        raise argparse.ArgumentTypeError("pozitif bir tam sayı olmalı")
    return sayi


def _negatif_olmayan_tam(deger: str) -> int:
    sayi = int(deger)
    if sayi < 0:
        raise argparse.ArgumentTypeError("0 ya da pozitif bir tam sayı olmalı")
    return sayi


def _pozitif_sayi(deger: str) -> float:
    sayi = float(deger)
    if not sayi > 0:
        raise argparse.ArgumentTypeError("pozitif bir sayı olmalı")
    return sayi


def argumanlar(argv: list[str] | None = None) -> argparse.Namespace:
    ayristirici = argparse.ArgumentParser(
        description="Forklift ek başını işlemcide eğitir (resmi YOLOX modeli donuk kalır)."
    )
    ayristirici.add_argument("--veri", type=Path, required=True, help="veri.py hazirla çıktısı")
    ayristirici.add_argument("--boy", choices=tuple(BOYLAR), required=True)
    ayristirici.add_argument("--kip", choices=KIPLER, required=True)
    ayristirici.add_argument("--resmi-pth", type=Path, required=True, help="resmi YOLOX .pth")
    ayristirici.add_argument(
        "--calisma", type=Path, required=True, help="ara kayıt ve çıktı klasörü"
    )
    ayristirici.add_argument("--devir", type=_pozitif_tam, default=30)
    ayristirici.add_argument(
        "--parti", type=_pozitif_tam, default=None, help="varsayılan: ortak.BOYLAR[boy]['parti']"
    )
    ayristirici.add_argument(
        "--sure-sn", type=_pozitif_sayi, default=19800.0, help="süre bütçesi (saniye)"
    )
    ayristirici.add_argument("--is-parcacigi", type=_pozitif_tam, default=4)
    ayristirici.add_argument("--veri-isci", type=_negatif_olmayan_tam, default=2)
    ayristirici.add_argument("--tohum", type=_negatif_olmayan_tam, default=0)
    ayristirici.add_argument(
        "--onbellek", action="store_true", help="görüntüleri RAM'de önbellekle"
    )
    return ayristirici.parse_args(argv)


def egitimi_calistir(args: argparse.Namespace) -> dict:
    """Eğitimi çalıştırır (ya da sürdürür); özet sözlüğünü döndürür."""
    veri = args.veri
    if not (veri / "annotations" / "egitim.json").is_file() or not (veri / "egitim").is_dir():
        raise ForkliftHatasi(
            f"eğitim verisi bulunamadı: {veri} (beklenen annotations/egitim.json ve egitim/)"
        )
    if not args.resmi_pth.is_file():
        raise ForkliftHatasi(f"resmi ağırlık dosyası bulunamadı: {args.resmi_pth}")
    # Donuk model resmi ONNX'le aynı olmalı: yalnız sabitlenmiş resmi yayın kabul edilir
    resmi_ozet = dosya_ozeti(args.resmi_pth)
    beklenen_ozet = RESMI_AGIRLIKLAR[args.boy][1]
    if resmi_ozet != beklenen_ozet:
        raise ForkliftHatasi(
            f"{args.resmi_pth} resmi YOLOX-{args.boy} ağırlığı değil (sha256 {resmi_ozet}, "
            f"beklenen {beklenen_ozet}); ondan kurulan model resmi ONNX'le aynı olmazdı"
        )
    is_baslangici = is_baslangici_oku()
    calisma = args.calisma.resolve()
    calisma.mkdir(parents=True, exist_ok=True)
    if (calisma / BITTI).exists():
        return {"bitti": True, "zaten_bitmisti": True, "calisma": str(calisma)}

    configure_module()  # YOLOX: OpenCV iş parçacıkları kapalı (veri işçileriyle yarışmasın)
    # YOLOX'un kendi kodundaki torch.cuda.amp çağrıları (işlemcide kapalı) her adımda
    # "deprecated" uyarısı basar; günlüğü boğmasın.
    warnings.filterwarnings(
        "ignore", message=r".*torch\.cuda\.amp\..* is deprecated", category=FutureWarning
    )
    torch.set_num_threads(args.is_parcacigi)
    random.seed(args.tohum)
    np.random.seed(args.tohum)
    torch.manual_seed(args.tohum)

    parti = args.parti or BOYLAR[args.boy]["parti"]
    deney = EkBasDeneyi(
        veri=veri,
        boy=args.boy,
        kip=args.kip,
        resmi_pth=args.resmi_pth,
        devir=args.devir,
        veri_isci=args.veri_isci,
        tohum=args.tohum,
        onbellek=args.onbellek,
    )
    deney.output_dir = str(calisma.parent)
    yolox_argumanlari = argparse.Namespace(
        # YOLOX Trainer'ın beklediği alanlar
        fp16=False,
        batch_size=parti,
        experiment_name=calisma.name,
        logger="yok",
        cache=None,
        occupy=False,
        resume=False,
        ckpt=None,
        start_epoch=None,
        # bu betiğin alanları
        sure_sn=args.sure_sn,
        is_parcacigi=args.is_parcacigi,
        tohum=args.tohum,
    )
    egitici = IslemciEgitici(deney, yolox_argumanlari, is_baslangici)
    egitici.train()
    ozet = dict(egitici.ozet(), resmi_pth_sha256=resmi_ozet)
    tam = dict(ozet, devirler=egitici.devir_gecmisi)
    (calisma / OZET_DOSYASI).write_text(
        json.dumps(tam, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return ozet


def main(argv: list[str] | None = None) -> int:
    args = argumanlar(argv)
    try:
        ozet = egitimi_calistir(args)
    except ForkliftHatasi as hata:
        # YOLOX günlüğü sys.stderr'i yönlendirir; hata iletisi gerçek stderr'e gider
        print(f"HATA: {hata}", file=sys.__stderr__)
        return 2
    if ozet.get("zaten_bitmisti"):
        print(f"eğitim zaten bitmiş ({ozet['calisma']}/{BITTI}); yapılacak iş yok")
    logger.complete()
    print("EGITIM_OZETI " + json.dumps(ozet), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

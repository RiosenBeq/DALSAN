"""Forklift adayını ürünün kendi tespit motoruyla ölçer (docs/17 §12.3).

Operatör isteği 23.09.2026. torch GEREKMEZ: ürün ortamında (.venv) çalışır;
aday ve resmi model uygulamanın kendi sınıfıyla (backend/app/analiz/tespit.py
Tespitci) açılır. Ayarlar uygulamanın varsayılanlarıdır ve .env.example'dan
okunur (TESPIT_GUVEN_ESIGI, TESPIT_INSAN_GUVEN_ESIGI, TESPIT_NMS_ESIGI,
TESPIT_EN_KUCUK_KENAR_PX, CIKARIM_IS_PARCACIGI); cihaz her zaman CPU. Ölçülen
şey, sahada kuralların göreceği tespitlerin kendisidir.

    python egitim/forklift/degerlendir.py --model aday.onnx
        --resmi models/yolox_tiny.onnx --veri OUT --cikti olcum.json
        [--video vtest.avi] [--arac-seti KLASOR] [--esikler egitim/forklift/esikler.json]
        [--sinir N] [--etiket tiny-v1]

Veri: `veri.py hazirla` çıktısı, yani OUT/annotations/test.json (COCO:
forklift, pallet_jack) ve OUT/test/. --sinir N en çok N görüntü ölçer (duman
koşusu): forklift içeren, hiçbir şey içermeyen ve yalnız transpalet içeren
görüntülerden sırayla birer tane (sinirli_secim); araç setinden de ad
sırasıyla ilk N görüntü. AP için her model ikinci kez, güven eşiği 0,01 ile
(öteki ayarlar aynı) açılır; bu ikinci örnek yalnız AP'de kullanılır.

Araç seti (--arac-seti): etiketsiz, gerçek tır, otomobil ve otobüs
fotoğrafları (iş akışında egitim/forklift/arac_seti.sha256'daki Open Images
V7 doğrulama görüntüleri). LOCO depo sahnesidir, vtest yayadır: ikisinde de
gerçek araç yoktur. Resmi modelin bulduğu bir aracı aday "forklift" derse
tır park kuralı (VEHICLE_OUT_OF_POSITION, yalnız "truck") onu artık görmez;
LOCO'daki arac_kaybi bunu kayıp saymaz (forklift de araçtır), tr_fk ise
LOCO'da çoğunlukla DOĞRU dönüşümdür (resmi modelin "truck" dediği gerçek
forklift). Bu yüzden ayrı bir sette ölçülür.

Araç koruması (arac_kaybi, tr_fk, arac_kazanci; video ve araç setindeki
karşılıkları) adayın ETİKET görünümüyle ölçülür: adayın ham çıktısında kutu
sütunları resmi modelinkiyle değiştirilip uygulamanın son işlemesinden
geçirilir. v1 ve v2'de kutu zaten resmi kutudur, görünüm adayın kendi
tespitleriyle aynıdır. v3'te forkliftin kazandığı çapada kutu ek baştan gelir:
resmi modelin gevşek sardığı bir aracı doğru yeniden etiketleyen aday, kutu
oynadı diye araç "kaybetmiş" sayılmasın; bir tırı forklifte çeviren aday da
kutusu oynadı diye tr_fk'den kaçmasın. İnsan koruması ve forklift metrikleri
uygulamanın gerçek tespitleriyle ölçülür. AP tespitleri, etiket görünümü ve
tanının ham kutuları aynı iki ham çıktıdan (aday ve resmi, birer çıkarım)
türetilir.

Eşleştirme COCO usulüdür: tespitler puana göre büyükten küçüğe gezilir; her
tespit, henüz alınmamış gerçek kutular arasında IoU'su en az 0,5 olan en
yüksek kutuya bağlanır (bir kutuya bir tespit; en iyi kutusu alınmışsa eşiği
geçen öteki boş kutuya düşer). Değerlendirilen forklift: kısa kenarı model
girdisinde en az 16 piksel olan kutu (min(w, h) x girdi / max(W, H) >= 16).
Daha küçük forklift yok sayılır: onunla eşleşen tespit ne doğru ne yanlış
sayılır (VOC "difficult"). AP50, VOC'nin her nokta enterpolasyonudur ve
yalnız bu enterpolasyon tests/dogruluk_kiyas/olcum.py ile aynıdır. O dosyanın
eşleştirmesi VOC usulüdür (tespit yalnız en yüksek IoU'lu kutuya bakar, o
kutu alınmışsa yanlış sayılır) ve yok sayılan kutu bilmez: iç içe kutularda
iki AP ayrılabilir. Testi ikisini aynı işaretlerle ve birbirinden uzak
kutularda karşılaştırır.

Metrikler (aksi yazılmadıkça uygulamanın çalışma noktasında):
  fk_r, fk_r_tum        "forklift" tespitiyle bulunan değerlendirilen (tum: bütün)
                        forklift kutularının oranı. fk_r'nin paydası girdi
                        boyuna bağlıdır (tiny 416'da s 640'tan az kutu
                        değerlendirilir): boylar arası kıyasta fk_r_tum
                        ve sayilar.fk_gercek de okunmalı
  vg_r, vg_r_tum        aynısı, "forklift" YA DA "truck" tespitiyle (kuralların
                        gördüğü araç); _resmi ekli olanlar resmi model içindir,
                        vg_r_artisi = vg_r - vg_r_resmi. _tum sayımları ayrı bir
                        eşleştirmedir (her kutu eşit, yok sayılan yok)
  fk_ap50, vg_ap50      güven 0,01'de AP50 (vg_ap50_resmi: resmi model)
  pt_fk                 "forklift" tespitiyle eşleşen el transpaleti oranı
  fk_fp_goruntu_basi    forklift ve transpalet içermeyen görüntü başına forklift
                        tespiti; fk_fp_goruntu_orani: en az biri olanların oranı
  fk_kesinlik           forklift kutusuyla eşleşen forklift tespitleri / bütün
                        forklift tespitleri (transpaletle eşleşen yanlış sayılır)
  insan_kaybi           resmi modelin insanlarından adayda IoU >= 0,5 insan
                        karşılığı olmayanların oranı
  arac_kaybi            resmi modelin araçlarından ("truck": COCO car, bus,
                        truck) adayda truck ya da forklift karşılığı olmayanlar
                        (adayın etiket görünümüyle, yukarıya bakın)
  tr_fk                 resmi araçlardan karşılığı forklift olanlar
  insan_kazanci,        adayın resmi karşılığı olmayan tespitleri / resmi sayı
  arac_kazanci
  gecikme_*_ms          Tespitci.tespit_et süresi, 5 ısınma görüntüsünden sonra
                        (medyan, p90); gecikme_orani_p90 = p90(aday) / p90(resmi)
  video_*               --video: her kare (600 kareden uzunsa her ikinci kare);
                        video_fk_kare_orani: en az bir forklift tespiti olan kare
                        oranı (vtest'te forklift yok: hepsi yanlış alarmdır)
  arac_seti_tr_fk       --arac-seti: resmi modelin araçlarından ("truck")
                        adayda karşılığı forklift olanların oranı;
                        arac_seti_arac_kaybi ve arac_seti_insan_kaybi yukarıdaki
                        kayıplarla aynı tanım
  fk_kutu_tavani        TANI, kapı değil: değerlendirilen forklift kutularından
                        adayın ham çıktısında IoU'su en az 0,5 olan bir çapa
                        kutusu bulunanların oranı (v1 ve v2'de kutu resmi
                        modelin donuk kutu dalıdır; tavan düşükse forklift puanı
                        da düşük öğrenilir, model.py "Neden v3")
  fk_kutu_tavani_resmi  TANI: aynı oran resmi modelin ham çıktısında (donuk kutu
                        dalının tavanı; v3'ün kutu dalı bunu geçmeli)
  fk_puan50_medyan      TANI: o çapalardaki en yüksek forklift puanının medyanı
  fk_kazanir50          TANI: o çapalardan birinde forklift puanı çalışma eşiğini
                        ve eşlenen bütün öteki puanları geçen kutuların oranı
Paydası sıfır olan oran ölçülmemiştir: None (JSON null); "ölçülmedi" "%0" değildir.

Kapılar (esikler.json): "<metrik>_en_fazla" (metrik <= eşik) ya da
"<metrik>_en_az" (metrik >= eşik). Ölçülemeyen metrik (--video ya da
--arac-seti verilmediyse onların metrikleri, paydası sıfır olan oran) kendi
kapısını KALDIRIR.

Çıkış kodu: 0 ölçüm yazıldı (kapılar kalsa da: kararı iş akışı verir);
2 girdi hatası (dosya yok ya da bozuk, model açılmıyor, eşik dosyası hatalı).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from ortak import EK_SINIFLAR

KOK = Path(__file__).resolve().parents[2]
ENV_ORNEGI = KOK / ".env.example"
VARSAYILAN_ESIKLER = Path(__file__).resolve().with_name("esikler.json")

# Tespitci'nin döndürdüğü katalog kodları (backend/app/rules/tipler.py)
INSAN = "person"
FORKLIFT = "forklift"
TIR = "truck"
ARAC = frozenset({FORKLIFT, TIR})

# test.json kategori adları (veri.py; ortak.EK_SINIFLAR)
FK_KATEGORISI, PT_KATEGORISI = EK_SINIFLAR

# Ölçüm tanımının sabitleri (SPEC 2.5)
IOU_ESIGI = 0.5
EN_KUCUK_FORKLIFT_PX = 16  # model girdisinde kısa kenar
AP_GUVEN_ESIGI = 0.01
ISINMA_GORUNTUSU = 5
VIDEO_TEK_KARE_SINIRI = 600  # daha uzun videoda her ikinci kare
ARAC_SETI_UZANTILARI = frozenset({".jpg", ".jpeg", ".png"})
_ILERLEME_ARALIGI = 250
_BASAMAK = 6

# Kapıların dayanabileceği bütün metrikler (tablo sırası)
METRIKLER = (
    "insan_kaybi",
    "arac_kaybi",
    "tr_fk",
    "insan_kazanci",
    "arac_kazanci",
    "fk_r",
    "fk_r_tum",
    "vg_r",
    "vg_r_tum",
    "vg_r_resmi",
    "vg_r_tum_resmi",
    "vg_r_artisi",
    "fk_ap50",
    "vg_ap50",
    "vg_ap50_resmi",
    "pt_fk",
    "fk_kesinlik",
    "fk_fp_goruntu_basi",
    "fk_fp_goruntu_orani",
    "gecikme_medyan_ms",
    "gecikme_p90_ms",
    "gecikme_medyan_ms_resmi",
    "gecikme_p90_ms_resmi",
    "gecikme_orani_p90",
    "video_insan_kaybi",
    "video_arac_kaybi",
    "video_fk_kare_orani",
    "arac_seti_tr_fk",
    "arac_seti_arac_kaybi",
    "arac_seti_insan_kaybi",
    "fk_kutu_tavani",
    "fk_kutu_tavani_resmi",
    "fk_puan50_medyan",
    "fk_kazanir50",
)
KAPI_YONLERI = {"_en_fazla": "en_fazla", "_en_az": "en_az"}

Kutu = tuple[float, float, float, float]  # x1, y1, x2, y2 (piksel)


class DegerlendirmeHatasi(Exception):
    """Girdi hatası: ölçüm yapılamaz (çıkış kodu 2)."""


# ---------------------------------------------------------------------------
# Saf ölçüm fonksiyonları (model ve dosya bilmez)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tespit:
    sinif: str
    kutu: Kutu
    puan: float


def iou(a: Kutu, b: Kutu) -> float:
    """İki kutunun kesişim / birleşim oranı."""
    genislik = min(a[2], b[2]) - max(a[0], b[0])
    yukseklik = min(a[3], b[3]) - max(a[1], b[1])
    if genislik <= 0 or yukseklik <= 0:
        return 0.0
    kesisim = genislik * yukseklik
    birlesim = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - kesisim
    return kesisim / birlesim if birlesim > 0 else 0.0


def eslestir(
    tahminler: Sequence[Tespit],
    gercekler: Sequence[Kutu],
    iou_esigi: float = IOU_ESIGI,
    yoksayilan: Sequence[bool] | None = None,
) -> list[int]:
    """Her tahminin bağlandığı gerçek kutunun sırası; bağlanmadıysa -1.

    Tahminler puana göre büyükten küçüğe (eşit puanda verildikleri sırayla)
    gezilir. Her tahmin, henüz alınmamış gerçek kutular arasında IoU'su
    `iou_esigi` ve üstü olan en yüksek kutuyu alır: bir kutuya bir tahmin.
    Yok sayılan kutu yalnız başka aday yoksa seçilir ve birden çok tahmini
    karşılayabilir; onunla eşleşen tahmin ne doğru ne yanlış sayılmalıdır.
    """
    yoksay = [False] * len(gercekler) if yoksayilan is None else list(yoksayilan)
    if len(yoksay) != len(gercekler):
        raise ValueError("yoksayilan, gerçek kutularla aynı uzunlukta olmalı")
    sira = sorted(range(len(tahminler)), key=lambda i: -tahminler[i].puan)
    alinan = [False] * len(gercekler)
    sonuc = [-1] * len(tahminler)
    for i in sira:
        kutu = tahminler[i].kutu
        secilen, secilen_iou = -1, -1.0
        yedek, yedek_iou = -1, -1.0
        for j, gercek in enumerate(gercekler):
            deger = iou(kutu, gercek)
            if deger < iou_esigi:
                continue
            if yoksay[j]:
                if deger > yedek_iou:
                    yedek, yedek_iou = j, deger
            elif not alinan[j] and deger > secilen_iou:
                secilen, secilen_iou = j, deger
        if secilen >= 0:
            alinan[secilen] = True
            sonuc[i] = secilen
        else:
            sonuc[i] = yedek
    return sonuc


def degerlendirilir_mi(kutu: Kutu, genislik: int, yukseklik: int, girdi: int) -> bool:
    """Forklift kutusunun kısa kenarı model girdisinde en az 16 piksel mi?"""
    kisa = min(kutu[2] - kutu[0], kutu[3] - kutu[1])
    return kisa * girdi / max(genislik, yukseklik) >= EN_KUCUK_FORKLIFT_PX


def ap_isaretleri(
    tahminler: Sequence[Tespit], gercekler: Sequence[Kutu], yoksayilan: Sequence[bool]
) -> list[tuple[float, bool]]:
    """AP için (puan, doğru mu) çiftleri; yok sayılan kutuya düşen tahmin atlanır."""
    eslesme = eslestir(tahminler, gercekler, yoksayilan=yoksayilan)
    return [
        (tahmin.puan, j >= 0)
        for tahmin, j in zip(tahminler, eslesme, strict=True)
        if not (j >= 0 and yoksayilan[j])
    ]


def ortalama_hassasiyet(isaretler: Iterable[tuple[float, bool]], n_gercek: int) -> float | None:
    """VOC her nokta enterpolasyonlu AP; gerçek kutu yoksa None (ölçülmedi)."""
    if n_gercek <= 0:
        return None
    sirali = sorted(isaretler, key=lambda cift: -cift[0])
    recall, hassasiyet = [0.0], [0.0]
    dogru = 0
    for adet, (_, dogru_mu) in enumerate(sirali, 1):
        dogru += int(dogru_mu)
        recall.append(dogru / n_gercek)
        hassasiyet.append(dogru / adet)
    # Her recall düzeyinde o düzey ve sonrasının en iyi hassasiyeti
    for i in range(len(hassasiyet) - 2, -1, -1):
        hassasiyet[i] = max(hassasiyet[i], hassasiyet[i + 1])
    return float(
        sum(
            (recall[i] - recall[i - 1]) * hassasiyet[i]
            for i in range(1, len(recall))
            if recall[i] > recall[i - 1]
        )
    )


def oran(pay: float, payda: float) -> float | None:
    """pay / payda; payda sıfırsa None (ölçülmedi)."""
    return pay / payda if payda > 0 else None


@dataclass(frozen=True)
class Koruma:
    """Resmi modelin bir sınıfının adayda korunması (sayılar)."""

    resmi: int = 0  # resmi modelin tespitleri
    kayip: int = 0  # adayda karşılığı olmayanlar
    fazla: int = 0  # adayın resmi karşılığı olmayan tespitleri
    forklift: int = 0  # karşılığı adayda "forklift" olanlar

    def __add__(self, diger: Koruma) -> Koruma:
        return Koruma(
            self.resmi + diger.resmi,
            self.kayip + diger.kayip,
            self.fazla + diger.fazla,
            self.forklift + diger.forklift,
        )


def koruma(
    resmi: Sequence[Tespit],
    aday: Sequence[Tespit],
    resmi_siniflari: Iterable[str],
    aday_siniflari: Iterable[str],
) -> Koruma:
    """Resmi tespitler "gerçek", adayınkiler "tahmin" sayılarak birebir eşleştirilir."""
    resmi_siniflari, aday_siniflari = set(resmi_siniflari), set(aday_siniflari)
    r = [t for t in resmi if t.sinif in resmi_siniflari]
    a = [t for t in aday if t.sinif in aday_siniflari]
    eslesme = eslestir(a, [t.kutu for t in r])
    eslesen = sum(1 for j in eslesme if j >= 0)
    return Koruma(
        resmi=len(r),
        kayip=len(r) - eslesen,
        fazla=len(a) - eslesen,
        forklift=sum(1 for t, j in zip(a, eslesme, strict=True) if j >= 0 and t.sinif == FORKLIFT),
    )


@dataclass(frozen=True)
class Gercek:
    """Bir test görüntüsünün etiketleri (piksel, xyxy)."""

    alt_kume: str
    genislik: int
    yukseklik: int
    forkliftler: tuple[Kutu, ...] = ()
    transpaletler: tuple[Kutu, ...] = ()


@dataclass(frozen=True)
class GoruntuSonucu:
    alt_kume: str
    fk_gercek: int  # değerlendirilen forklift kutuları
    fk_gercek_tum: int
    fk_bulunan: int
    fk_bulunan_tum: int
    vg_bulunan: int
    vg_bulunan_tum: int
    vg_bulunan_resmi: int
    vg_bulunan_tum_resmi: int
    pt_gercek: int
    pt_fk: int
    fk_tespit: int  # adayın bütün forklift tespitleri
    fk_dogru: int  # bir forklift kutusuyla eşleşenler (her boyutta)
    bos: bool  # forklift de transpalet de yok
    insan: Koruma
    arac: Koruma
    ap_fk: tuple[tuple[float, bool], ...]
    ap_vg: tuple[tuple[float, bool], ...]
    ap_vg_resmi: tuple[tuple[float, bool], ...]


def _sinifta(tespitler: Iterable[Tespit], siniflar: Iterable[str]) -> list[Tespit]:
    siniflar = set(siniflar)
    return [t for t in tespitler if t.sinif in siniflar]


def _bulunan(
    tahminler: Sequence[Tespit], gercekler: Sequence[Kutu], yoksayilan: Sequence[bool]
) -> tuple[int, int]:
    """(bulunan değerlendirilen kutu, bulunan kutu) sayıları.

    İkisi AYRI eşleştirmedir. İlkinde küçük kutular yok sayılır (yalnız
    yedek); "bütün kutular" sayımında her kutu eşittir. Tek eşleştirmeden
    sayılsaydı bir tespit büyük kutuya yönelir, küçük kutuyu karşılayacak
    sonraki tespit boşta kalır ve bütün kutuların sayımı eksik çıkardı.
    """
    degerlendirilen = {
        j
        for j in eslestir(tahminler, gercekler, yoksayilan=yoksayilan)
        if j >= 0 and not yoksayilan[j]
    }
    butun = {j for j in eslestir(tahminler, gercekler) if j >= 0}
    return len(degerlendirilen), len(butun)


def goruntuyu_olc(
    gercek: Gercek,
    aday: Sequence[Tespit],
    resmi: Sequence[Tespit],
    aday_ap: Sequence[Tespit],
    resmi_ap: Sequence[Tespit],
    girdi: int,
    aday_arac: Sequence[Tespit] | None = None,
) -> GoruntuSonucu:
    """Bir görüntünün ölçümü: çalışma noktası tespitleri ve AP için güven 0,01 tespitleri.

    aday_arac: araç korumasında kullanılacak aday tespitleri (etiket görünümü,
    modül belgesi); verilmezse aday.
    """
    yoksay = [
        not degerlendirilir_mi(k, gercek.genislik, gercek.yukseklik, girdi)
        for k in gercek.forkliftler
    ]
    fk = _sinifta(aday, {FORKLIFT})
    fk_bulunan, fk_bulunan_tum = _bulunan(fk, gercek.forkliftler, yoksay)
    vg_bulunan, vg_bulunan_tum = _bulunan(_sinifta(aday, ARAC), gercek.forkliftler, yoksay)
    vg_resmi, vg_tum_resmi = _bulunan(_sinifta(resmi, ARAC), gercek.forkliftler, yoksay)
    return GoruntuSonucu(
        alt_kume=gercek.alt_kume,
        fk_gercek=yoksay.count(False),
        fk_gercek_tum=len(gercek.forkliftler),
        fk_bulunan=fk_bulunan,
        fk_bulunan_tum=fk_bulunan_tum,
        vg_bulunan=vg_bulunan,
        vg_bulunan_tum=vg_bulunan_tum,
        vg_bulunan_resmi=vg_resmi,
        vg_bulunan_tum_resmi=vg_tum_resmi,
        pt_gercek=len(gercek.transpaletler),
        pt_fk=len({j for j in eslestir(fk, gercek.transpaletler) if j >= 0}),
        fk_tespit=len(fk),
        fk_dogru=sum(1 for j in eslestir(fk, gercek.forkliftler) if j >= 0),
        bos=not gercek.forkliftler and not gercek.transpaletler,
        insan=koruma(resmi, aday, {INSAN}, {INSAN}),
        arac=koruma(resmi, aday if aday_arac is None else aday_arac, {TIR}, ARAC),
        ap_fk=tuple(ap_isaretleri(_sinifta(aday_ap, {FORKLIFT}), gercek.forkliftler, yoksay)),
        ap_vg=tuple(ap_isaretleri(_sinifta(aday_ap, ARAC), gercek.forkliftler, yoksay)),
        ap_vg_resmi=tuple(ap_isaretleri(_sinifta(resmi_ap, ARAC), gercek.forkliftler, yoksay)),
    )


def _capa_ioulari(kutu: Kutu, kutular: np.ndarray) -> np.ndarray:
    """Bir gerçek kutunun bütün çapa kutularıyla IoU'su (kutular: [A, 4] xyxy)."""
    kesisim = np.clip(
        np.minimum(kutu[2], kutular[:, 2]) - np.maximum(kutu[0], kutular[:, 0]), 0, None
    ) * np.clip(np.minimum(kutu[3], kutular[:, 3]) - np.maximum(kutu[1], kutular[:, 1]), 0, None)
    alan = (kutular[:, 2] - kutular[:, 0]) * (kutular[:, 3] - kutular[:, 1])
    birlesim = (kutu[2] - kutu[0]) * (kutu[3] - kutu[1]) + alan - kesisim
    return kesisim / np.maximum(birlesim, 1e-9)


def kutu_tavanlari(
    kutular: np.ndarray, gercekler: Sequence[Kutu], yoksayilan: Sequence[bool]
) -> list[float]:
    """Değerlendirilen her gerçek kutu için ham çıktıdaki en iyi çapa IoU'su (tanı)."""
    tavanlar = []
    for kutu, yok in zip(gercekler, yoksayilan, strict=True):
        if not yok:
            ioular = _capa_ioulari(kutu, kutular)
            tavanlar.append(float(ioular.max()) if len(ioular) else 0.0)
    return tavanlar


def forklift_tanisi(
    kutular: np.ndarray,
    puanlar: np.ndarray,
    gercekler: Sequence[Kutu],
    yoksayilan: Sequence[bool],
    forklift: int,
    digerleri: Sequence[int],
    esik: float,
) -> list[tuple[float, float, bool]]:
    """Değerlendirilen her forklift kutusu için ham çıktıdan (tanı):
    (en iyi çapa IoU'su, IoU >= 0,5 çapalarda en yüksek forklift puanı,
    o çapalardan birinde forklift eşiği ve eşlenen öteki puanları geçiyor mu).

    kutular: [A, 4] xyxy piksel; puanlar: [A, sütun] nesne x sınıf.
    """
    fk = puanlar[:, forklift]
    diger = puanlar[:, list(digerleri)].max(1) if digerleri else np.zeros(len(puanlar))
    sonuc = []
    for kutu, yok in zip(gercekler, yoksayilan, strict=True):
        if yok:
            continue
        ioular = _capa_ioulari(kutu, kutular)
        yakin = ioular >= IOU_ESIGI
        sonuc.append(
            (
                float(ioular.max()) if len(ioular) else 0.0,
                float(fk[yakin].max()) if yakin.any() else 0.0,
                bool(np.any(yakin & (fk >= esik) & (fk > diger))),
            )
        )
    return sonuc


def tani_ozeti(tani: Sequence[tuple[float, float, bool]], resmi_tavanlari: Sequence[float]) -> dict:
    """forklift_tanisi ve resmi modelin kutu_tavanlari sonuçlarından tanı metrikleri."""
    return {
        "fk_kutu_tavani": _yuvarla(oran(sum(t[0] >= IOU_ESIGI for t in tani), len(tani))),
        "fk_kutu_tavani_resmi": _yuvarla(
            oran(sum(t >= IOU_ESIGI for t in resmi_tavanlari), len(resmi_tavanlari))
        ),
        "fk_puan50_medyan": _yuvarla(float(np.median([t[1] for t in tani]))) if tani else None,
        "fk_kazanir50": _yuvarla(oran(sum(t[2] for t in tani), len(tani))),
    }


def _yuvarla(deger: float | None, basamak: int = _BASAMAK) -> float | None:
    """JSON'a girecek sayı: yuvarlanmış; None ve sonlu olmayan değer None."""
    if deger is None or not math.isfinite(deger):
        return None
    return round(float(deger), basamak)


def _fark(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a - b


def _topla(sonuclar: Iterable[GoruntuSonucu], alan: str) -> int:
    return sum(getattr(s, alan) for s in sonuclar)


# GoruntuSonucu'nun görüntüler üzerinden toplanan sayı alanları
_TOPLANAN_ALANLAR = (
    "fk_gercek",
    "fk_gercek_tum",
    "fk_bulunan",
    "fk_bulunan_tum",
    "vg_bulunan",
    "vg_bulunan_tum",
    "vg_bulunan_resmi",
    "vg_bulunan_tum_resmi",
    "pt_gercek",
    "pt_fk",
    "fk_tespit",
    "fk_dogru",
)


def _fp_sayilari(sonuclar: Sequence[GoruntuSonucu]) -> tuple[int, int, int]:
    """(boş görüntü, onlardaki forklift tespiti, forklift tespiti olan boş görüntü)."""
    bos = [s for s in sonuclar if s.bos]
    return len(bos), sum(s.fk_tespit for s in bos), sum(1 for s in bos if s.fk_tespit)


def ozetle(sonuclar: Sequence[GoruntuSonucu]) -> tuple[dict, dict, dict]:
    """Görüntü sonuçlarından (metrikler, sayılar, alt küme dökümü)."""
    t = {alan: _topla(sonuclar, alan) for alan in _TOPLANAN_ALANLAR}
    insan = sum((s.insan for s in sonuclar), Koruma())
    arac = sum((s.arac for s in sonuclar), Koruma())
    bos, bos_fk, bos_fk_goruntu = _fp_sayilari(sonuclar)
    vg_r = oran(t["vg_bulunan"], t["fk_gercek"])
    vg_r_resmi = oran(t["vg_bulunan_resmi"], t["fk_gercek"])
    ham = {
        "insan_kaybi": oran(insan.kayip, insan.resmi),
        "arac_kaybi": oran(arac.kayip, arac.resmi),
        "tr_fk": oran(arac.forklift, arac.resmi),
        "insan_kazanci": oran(insan.fazla, insan.resmi),
        "arac_kazanci": oran(arac.fazla, arac.resmi),
        "fk_r": oran(t["fk_bulunan"], t["fk_gercek"]),
        "fk_r_tum": oran(t["fk_bulunan_tum"], t["fk_gercek_tum"]),
        "vg_r": vg_r,
        "vg_r_tum": oran(t["vg_bulunan_tum"], t["fk_gercek_tum"]),
        "vg_r_resmi": vg_r_resmi,
        "vg_r_tum_resmi": oran(t["vg_bulunan_tum_resmi"], t["fk_gercek_tum"]),
        "vg_r_artisi": _fark(vg_r, vg_r_resmi),
        "fk_ap50": ortalama_hassasiyet(_birlestir(sonuclar, "ap_fk"), t["fk_gercek"]),
        "vg_ap50": ortalama_hassasiyet(_birlestir(sonuclar, "ap_vg"), t["fk_gercek"]),
        "vg_ap50_resmi": ortalama_hassasiyet(_birlestir(sonuclar, "ap_vg_resmi"), t["fk_gercek"]),
        "pt_fk": oran(t["pt_fk"], t["pt_gercek"]),
        "fk_kesinlik": oran(t["fk_dogru"], t["fk_tespit"]),
        "fk_fp_goruntu_basi": oran(bos_fk, bos),
        "fk_fp_goruntu_orani": oran(bos_fk_goruntu, bos),
    }
    sayilar = {
        "goruntu": len(sonuclar),
        **t,
        "bos_goruntu": bos,
        "bos_fk_tespit": bos_fk,
        "bos_fk_goruntu": bos_fk_goruntu,
        "resmi_insan": insan.resmi,
        "kaybolan_insan": insan.kayip,
        "fazla_insan": insan.fazla,
        "resmi_arac": arac.resmi,
        "kaybolan_arac": arac.kayip,
        "forklifte_donen_arac": arac.forklift,
        "fazla_arac": arac.fazla,
    }
    return (
        {ad: _yuvarla(deger) for ad, deger in ham.items()},
        sayilar,
        _alt_kume_dokumu(sonuclar),
    )


def _birlestir(sonuclar: Iterable[GoruntuSonucu], alan: str) -> list[tuple[float, bool]]:
    return [cift for s in sonuclar for cift in getattr(s, alan)]


def _alt_kume_dokumu(sonuclar: Sequence[GoruntuSonucu]) -> dict:
    gruplar: dict[str, list[GoruntuSonucu]] = defaultdict(list)
    for sonuc in sonuclar:
        gruplar[sonuc.alt_kume].append(sonuc)
    dokum = {}
    for ad, grup in sorted(gruplar.items()):
        fk_gercek = _topla(grup, "fk_gercek")
        bos, bos_fk, bos_fk_goruntu = _fp_sayilari(grup)
        dokum[ad] = {
            "goruntu": len(grup),
            "fk_gercek": fk_gercek,
            "fk_r": _yuvarla(oran(_topla(grup, "fk_bulunan"), fk_gercek)),
            "vg_r": _yuvarla(oran(_topla(grup, "vg_bulunan"), fk_gercek)),
            "vg_r_resmi": _yuvarla(oran(_topla(grup, "vg_bulunan_resmi"), fk_gercek)),
            "bos_goruntu": bos,
            "fk_fp_goruntu_basi": _yuvarla(oran(bos_fk, bos)),
            "fk_fp_goruntu_orani": _yuvarla(oran(bos_fk_goruntu, bos)),
        }
    return dokum


@dataclass(frozen=True)
class KareSonucu:
    insan: Koruma
    arac: Koruma
    forklift_var: bool


def kareyi_olc(
    aday: Sequence[Tespit], resmi: Sequence[Tespit], aday_arac: Sequence[Tespit] | None = None
) -> KareSonucu:
    """Etiketsiz bir kare (video, araç seti): koruma ve forklift yanlış alarmı.

    aday_arac: araç korumasının etiket görünümü (goruntuyu_olc gibi); verilmezse aday.
    """
    return KareSonucu(
        insan=koruma(resmi, aday, {INSAN}, {INSAN}),
        arac=koruma(resmi, aday if aday_arac is None else aday_arac, {TIR}, ARAC),
        forklift_var=any(t.sinif == FORKLIFT for t in aday),
    )


def video_adimi(kare_sayisi: int) -> int:
    """600 kareye kadar her kare, daha uzun videoda her ikinci kare."""
    return 2 if kare_sayisi > VIDEO_TEK_KARE_SINIRI else 1


def video_ozeti(kareler: Sequence[KareSonucu]) -> tuple[dict, dict]:
    insan = sum((k.insan for k in kareler), Koruma())
    arac = sum((k.arac for k in kareler), Koruma())
    fk_kare = sum(1 for k in kareler if k.forklift_var)
    metrikler = {
        "video_insan_kaybi": _yuvarla(oran(insan.kayip, insan.resmi)),
        "video_arac_kaybi": _yuvarla(oran(arac.kayip, arac.resmi)),
        "video_fk_kare_orani": _yuvarla(oran(fk_kare, len(kareler))),
    }
    sayilar = {
        "video_kare": len(kareler),
        "video_resmi_insan": insan.resmi,
        "video_kaybolan_insan": insan.kayip,
        "video_resmi_arac": arac.resmi,
        "video_kaybolan_arac": arac.kayip,
        "video_fk_kare": fk_kare,
    }
    return metrikler, sayilar


def arac_seti_ozeti(kareler: Sequence[KareSonucu]) -> tuple[dict, dict]:
    """Araç seti (etiketsiz gerçek araç fotoğrafları): resmi araçlar adayda ne oldu."""
    insan = sum((k.insan for k in kareler), Koruma())
    arac = sum((k.arac for k in kareler), Koruma())
    metrikler = {
        "arac_seti_tr_fk": _yuvarla(oran(arac.forklift, arac.resmi)),
        "arac_seti_arac_kaybi": _yuvarla(oran(arac.kayip, arac.resmi)),
        "arac_seti_insan_kaybi": _yuvarla(oran(insan.kayip, insan.resmi)),
    }
    sayilar = {
        "arac_seti_goruntu": len(kareler),
        "arac_seti_resmi_arac": arac.resmi,
        "arac_seti_forklifte_donen_arac": arac.forklift,
        "arac_seti_kaybolan_arac": arac.kayip,
        "arac_seti_resmi_insan": insan.resmi,
        "arac_seti_kaybolan_insan": insan.kayip,
    }
    return metrikler, sayilar


def gecikme_ozeti(aday_sn: Sequence[float], resmi_sn: Sequence[float]) -> dict:
    """Tespit süreleri (saniye) -> medyan ve p90 (ms), p90 oranı."""

    def medyan_p90(sureler: Sequence[float]) -> tuple[float | None, float | None]:
        if not sureler:
            return None, None
        ms = np.asarray(sureler, dtype=float) * 1000.0
        return float(np.median(ms)), float(np.percentile(ms, 90))

    aday_medyan, aday_p90 = medyan_p90(aday_sn)
    resmi_medyan, resmi_p90 = medyan_p90(resmi_sn)
    return {
        "gecikme_medyan_ms": _yuvarla(aday_medyan, 3),
        "gecikme_p90_ms": _yuvarla(aday_p90, 3),
        "gecikme_medyan_ms_resmi": _yuvarla(resmi_medyan, 3),
        "gecikme_p90_ms_resmi": _yuvarla(resmi_p90, 3),
        "gecikme_orani_p90": _yuvarla(
            None if aday_p90 is None or resmi_p90 is None else oran(aday_p90, resmi_p90), 4
        ),
    }


def kapi_adini_coz(ad: str) -> tuple[str, str]:
    """Kapı adını ayırır: "fk_r_en_az" -> ("fk_r", "en_az"); tanınmayan biçim ValueError."""
    for ek, yon in KAPI_YONLERI.items():
        if ad.endswith(ek) and len(ad) > len(ek):
            return ad[: -len(ek)], yon
    raise ValueError(f"kapı adı '<metrik>_en_fazla' ya da '<metrik>_en_az' olmalı: {ad!r}")


def kapilari_degerlendir(
    metrikler: dict[str, float | None], esikler: dict[str, float]
) -> tuple[bool, list[str], dict]:
    """(hepsi geçti mi, kalan kapılar, kapı başına ayrıntı).

    Ölçülemeyen (eksik, None ya da sonlu olmayan) metrik kapıyı kaldırır.
    """
    kalan: list[str] = []
    ayrinti: dict[str, dict] = {}
    for ad, esik in esikler.items():
        metrik, yon = kapi_adini_coz(ad)
        deger = metrikler.get(metrik)
        if deger is None or not math.isfinite(deger):
            gecti = False
        elif yon == "en_fazla":
            gecti = deger <= esik
        else:
            gecti = deger >= esik
        ayrinti[ad] = {"metrik": metrik, "yon": yon, "esik": esik, "deger": deger, "gecti": gecti}
        if not gecti:
            kalan.append(ad)
    return not kalan, kalan, ayrinti


# ---------------------------------------------------------------------------
# Girdiler
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TespitAyari:
    guven_esigi: float
    insan_guven_esigi: float
    nms_esigi: float
    en_kucuk_kenar_px: int
    is_parcacigi: int


_AYAR_ANAHTARLARI = {
    "guven_esigi": ("TESPIT_GUVEN_ESIGI", float),
    "insan_guven_esigi": ("TESPIT_INSAN_GUVEN_ESIGI", float),
    "nms_esigi": ("TESPIT_NMS_ESIGI", float),
    "en_kucuk_kenar_px": ("TESPIT_EN_KUCUK_KENAR_PX", int),
}


def uygulama_ayarlari(yol: Path = ENV_ORNEGI) -> TespitAyari:
    """Tespit ayarlarının uygulama varsayılanları (.env.example; uygulamanın ayrıştırıcısıyla)."""
    from dotenv import dotenv_values

    if not yol.is_file():
        raise DegerlendirmeHatasi(f"{yol} yok: tespit ayarları oradan okunur")
    try:
        degerler = dotenv_values(yol)
    except (OSError, UnicodeDecodeError) as hata:
        raise DegerlendirmeHatasi(f"{yol} okunamadı: {hata}") from hata
    ayar: dict[str, float | int] = {}
    for alan, (anahtar, tip) in _AYAR_ANAHTARLARI.items():
        ham = degerler.get(anahtar)
        if ham is None or not ham.strip():
            raise DegerlendirmeHatasi(f"{yol}: {anahtar} yok ya da boş")
        try:
            ayar[alan] = tip(ham.strip())
        except ValueError as hata:
            raise DegerlendirmeHatasi(f"{yol}: {anahtar}={ham!r} sayı değil") from hata
    ham = (degerler.get("CIKARIM_IS_PARCACIGI") or "0").strip()
    try:
        ayar["is_parcacigi"] = int(ham)
    except ValueError as hata:
        raise DegerlendirmeHatasi(f"{yol}: CIKARIM_IS_PARCACIGI={ham!r} sayı değil") from hata
    return TespitAyari(**ayar)


def esikleri_oku(yol: Path) -> dict[str, float]:
    """esikler.json: {"<metrik>_en_fazla" | "<metrik>_en_az": sayı}."""
    try:
        belge = json.loads(yol.read_text(encoding="utf-8"))
    except FileNotFoundError as hata:
        raise DegerlendirmeHatasi(f"eşik dosyası yok: {yol}") from hata
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as hata:
        raise DegerlendirmeHatasi(f"eşik dosyası okunamadı: {yol} ({hata})") from hata
    if not isinstance(belge, dict):
        raise DegerlendirmeHatasi(f"eşik dosyası bir JSON nesnesi olmalı: {yol}")
    esikler: dict[str, float] = {}
    for ad, deger in belge.items():
        try:
            metrik, _ = kapi_adini_coz(ad)
        except ValueError as hata:
            raise DegerlendirmeHatasi(f"{yol}: {hata}") from hata
        if metrik not in METRIKLER:
            raise DegerlendirmeHatasi(f"{yol}: {ad!r} bilinmeyen bir metriğe dayanıyor")
        if (
            isinstance(deger, bool)
            or not isinstance(deger, int | float)
            or not math.isfinite(deger)
        ):
            raise DegerlendirmeHatasi(f"{yol}: {ad!r} sayı olmalı, {deger!r} verilmiş")
        esikler[ad] = float(deger)
    return esikler


@dataclass(frozen=True)
class OlcumGoruntusu:
    yol: Path
    alt_kume: str
    json_boyu: tuple[int, int] | None  # (genişlik, yükseklik), test.json'dan
    forkliftler: tuple[Kutu, ...]
    transpaletler: tuple[Kutu, ...]


def _alt_kume(goruntu: dict) -> str:
    if goruntu.get("alt_kume"):
        return str(goruntu["alt_kume"])
    parcalar = str(goruntu.get("kaynak_yol", "")).split("/")
    return parcalar[2] if len(parcalar) > 3 else "bilinmiyor"


def sinirli_secim(goruntuler: Sequence[OlcumGoruntusu], sinir: int) -> list[OlcumGoruntusu]:
    """--sinir N: en çok N görüntü, üç gruptan SIRAYLA birer tane alınarak:
    forklift içeren, ne forklift ne transpalet içeren (yanlış alarm paydası),
    yalnız transpalet içeren. Her grup kendi içinde JSON sırasıyla gezilir,
    sonuç yine JSON sırasıyla döner; her seferinde aynıdır.

    Neden: LOCO test JSON'u yol sırasıdır ve subset-1'in ilk görüntülerinde
    forklift yoktur. "İlk N" alınsaydı duman ölçümünde fk_r, fk_ap50 ve
    fk_kesinlik hiç ölçülmez (null), forklift yolu hiç sınanmazdı.
    """
    gruplar: tuple[list[int], ...] = ([], [], [])
    for sira, goruntu in enumerate(goruntuler):
        if goruntu.forkliftler:
            gruplar[0].append(sira)
        elif not goruntu.transpaletler:
            gruplar[1].append(sira)
        else:
            gruplar[2].append(sira)
    secilen: list[int] = []
    tur = 0
    while len(secilen) < sinir and any(tur < len(grup) for grup in gruplar):
        for grup in gruplar:
            if tur < len(grup) and len(secilen) < sinir:
                secilen.append(grup[tur])
        tur += 1
    return [goruntuler[sira] for sira in sorted(secilen)]


def olcum_setini_oku(veri: Path, sinir: int | None = None) -> list[OlcumGoruntusu]:
    """OUT/annotations/test.json -> görüntüler (JSON sırasıyla; --sinir: sinirli_secim)."""
    json_yolu = veri / "annotations" / "test.json"
    try:
        belge = json.loads(json_yolu.read_text(encoding="utf-8"))
    except FileNotFoundError as hata:
        raise DegerlendirmeHatasi(
            f"{json_yolu} yok. Önce: python egitim/forklift/veri.py hazirla --kaynak ... "
            f"--hedef {veri}"
        ) from hata
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as hata:
        raise DegerlendirmeHatasi(f"{json_yolu} okunamadı: {hata}") from hata
    try:
        kategoriler = {k["name"]: k["id"] for k in belge["categories"]}
        if FK_KATEGORISI not in kategoriler:
            raise DegerlendirmeHatasi(f"{json_yolu}: '{FK_KATEGORISI}' kategorisi yok")
        fk_id, pt_id = kategoriler[FK_KATEGORISI], kategoriler.get(PT_KATEGORISI)
        kutular: dict[object, dict[str, list[Kutu]]] = defaultdict(lambda: {"fk": [], "pt": []})
        for etiket in belge["annotations"]:
            x, y, w, h = (float(d) for d in etiket["bbox"])
            if etiket["category_id"] == fk_id:
                kutular[etiket["image_id"]]["fk"].append((x, y, x + w, y + h))
            elif etiket["category_id"] == pt_id:
                kutular[etiket["image_id"]]["pt"].append((x, y, x + w, y + h))
        goruntuler = []
        for goruntu in belge["images"]:
            if "asil_id" in goruntu:
                continue  # tekrar girdisi (eğitim JSON'unda olur): aynı dosya bir kez
            boy = (
                (int(goruntu["width"]), int(goruntu["height"]))
                if goruntu.get("width") and goruntu.get("height")
                else None
            )
            etiketler = kutular.get(goruntu["id"], {"fk": [], "pt": []})
            goruntuler.append(
                OlcumGoruntusu(
                    yol=veri / "test" / str(goruntu["file_name"]),
                    alt_kume=_alt_kume(goruntu),
                    json_boyu=boy,
                    forkliftler=tuple(etiketler["fk"]),
                    transpaletler=tuple(etiketler["pt"]),
                )
            )
    except (KeyError, TypeError, ValueError) as hata:
        raise DegerlendirmeHatasi(f"{json_yolu}: COCO biçimi beklenmedik ({hata!r})") from hata
    if sinir is not None:
        goruntuler = sinirli_secim(goruntuler, sinir)
    if not goruntuler:
        raise DegerlendirmeHatasi(f"{json_yolu}: ölçülecek görüntü yok")
    eksik = [g.yol for g in goruntuler if not g.yol.is_file()]
    if eksik:
        raise DegerlendirmeHatasi(
            f"{len(eksik)} görüntü dosyası yok (ilki: {eksik[0]}); veri seti eksik"
        )
    return goruntuler


def arac_setini_oku(klasor: Path, sinir: int | None = None) -> list[Path]:
    """--arac-seti: klasördeki görüntüler, ad sırasıyla (--sinir N: ilk N)."""
    if not klasor.is_dir():
        raise DegerlendirmeHatasi(f"araç seti klasörü yok: {klasor}")
    yollar = sorted(
        yol
        for yol in klasor.iterdir()
        if yol.is_file() and yol.suffix.lower() in ARAC_SETI_UZANTILARI
    )
    if sinir is not None:
        yollar = yollar[:sinir]
    if not yollar:
        raise DegerlendirmeHatasi(f"araç setinde görüntü yok: {klasor}")
    return yollar


def dosya_ozeti(yol: Path) -> str:
    ozet = hashlib.sha256()
    with yol.open("rb") as dosya:
        for parca in iter(lambda: dosya.read(1 << 20), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def _kare_oku(goruntu: OlcumGoruntusu) -> np.ndarray:
    kare = cv2.imread(str(goruntu.yol), cv2.IMREAD_COLOR)
    if kare is None:
        raise DegerlendirmeHatasi(f"görüntü okunamadı: {goruntu.yol}")
    boy = (kare.shape[1], kare.shape[0])
    if goruntu.json_boyu is not None and goruntu.json_boyu != boy:
        raise DegerlendirmeHatasi(
            f"{goruntu.yol}: test.json {goruntu.json_boyu[0]}x{goruntu.json_boyu[1]} diyor, "
            f"dosya {boy[0]}x{boy[1]}; kutular bu görüntüye uymaz"
        )
    return kare


# ---------------------------------------------------------------------------
# Ürünün tespit motoru
# ---------------------------------------------------------------------------


def _uygulama_siniflari() -> tuple[type, type[Exception]]:
    """(Tespitci, ModelHatasi): backend/ gerekirse import yoluna eklenir."""
    backend = str(KOK / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.analiz.tespit import ModelHatasi, Tespitci

    return Tespitci, ModelHatasi


def tespitci_ac(yol: Path, ayar: TespitAyari, guven_esigi: float):
    """Uygulamanın Tespitci'si; ayarlar uygulama varsayılanı, cihaz CPU."""
    tespitci_sinifi, model_hatasi = _uygulama_siniflari()
    try:
        return tespitci_sinifi(
            yol,
            "cpu",
            guven_esigi=guven_esigi,
            insan_guven_esigi=ayar.insan_guven_esigi,
            nms_esigi=ayar.nms_esigi,
            en_kucuk_kenar_px=ayar.en_kucuk_kenar_px,
            is_parcacigi=ayar.is_parcacigi,
        )
    except model_hatasi as hata:
        raise DegerlendirmeHatasi(
            f"{yol} açılamadı: {hata.kullanici_mesaji} ({hata.teknik_ayrinti})"
        ) from hata


def girdi_boyu(tespitci) -> int:
    """Modelin girdi kenarı: Tespitci onu ONNX girdi biçiminden okur."""
    return int(tespitci._girdi_boyu)


def _model_karti(tespitci) -> dict | str | None:
    """Birleşik ONNX'in üst verisindeki model kartı (resmi modelde yok)."""
    try:
        ust = dict(tespitci._oturum.get_modelmeta().custom_metadata_map or {})
    except AttributeError:
        return None
    ham = ust.get("dalsan_model_karti")
    if not ham:
        return None
    try:
        return json.loads(ham)
    except json.JSONDecodeError:
        return ham


def tespitleri_cevir(sonuc: tuple[np.ndarray, np.ndarray, np.ndarray]) -> list[Tespit]:
    """Tespitci.tespit_et çıktısı -> Tespit listesi."""
    kutular, guvenler, adlar = sonuc
    return [
        Tespit(str(ad), (float(k[0]), float(k[1]), float(k[2]), float(k[3])), float(g))
        for k, g, ad in zip(kutular, guvenler, adlar, strict=True)
    ]


def etiket_gorunumu(aday_ham: np.ndarray, resmi_ham: np.ndarray) -> np.ndarray:
    """Adayın ham çıktısı, kutu sütunları (0-3) resmi modelinkiyle (modül belgesi)."""
    gorunum = np.array(aday_ham, copy=True)
    gorunum[:, :4] = resmi_ham[:, :4]
    return gorunum


def ham_kutular(
    cikti: np.ndarray, oran_: float, genislik: int, yukseklik: int, girdi: int
) -> np.ndarray:
    """Ham çıktının bütün çapa kutuları: xyxy, özgün piksel, kareye kırpılmış.

    Izgara çözümü ve kırpma uygulamanın Tespitci._son_isle'siyle aynıdır (üs
    taşmasın diye log boyut 20'de kesilir; kırpma sonucu aynı kalır).
    """
    izgaralar, adimlar = [], []
    for adim in (8, 16, 32):
        kenar = girdi // adim
        xv, yv = np.meshgrid(np.arange(kenar), np.arange(kenar))
        izgaralar.append(np.stack((xv, yv), 2).reshape(-1, 2))
        adimlar.append(np.full((kenar * kenar, 1), adim))
    izgara, adim_dizisi = np.concatenate(izgaralar), np.concatenate(adimlar)
    cikti = np.asarray(cikti, dtype=np.float64)
    merkez = (cikti[:, :2] + izgara) * adim_dizisi / oran_
    boyut = np.exp(np.minimum(cikti[:, 2:4], 20.0)) * adim_dizisi / oran_
    kutular = np.concatenate([merkez - boyut / 2, merkez + boyut / 2], 1)
    kutular[:, [0, 2]] = kutular[:, [0, 2]].clip(0, genislik)
    kutular[:, [1, 3]] = kutular[:, [1, 3]].clip(0, yukseklik)
    return kutular


@dataclass(frozen=True)
class HamSonuc:
    """Bir görüntünün iki ham çıktısından türetilenler (Olcer.ham_ciktilar)."""

    aday_ap: list[Tespit]
    resmi_ap: list[Tespit]
    aday_arac: list[Tespit]  # etiket görünümü: adayın sınıfları, resmi kutular
    aday_kutular: np.ndarray  # [A, 4] xyxy özgün piksel, kırpılmış
    aday_puanlar: np.ndarray  # [A, sütun] nesne x sınıf
    resmi_kutular: np.ndarray


class Olcer:
    """Aday ve resmi model; her biri çalışma noktasında ve AP için güven 0,01'de."""

    def __init__(self, model: Path, resmi: Path, ayar: TespitAyari) -> None:
        self.aday = tespitci_ac(model, ayar, ayar.guven_esigi)
        self.resmi = tespitci_ac(resmi, ayar, ayar.guven_esigi)
        self.girdi = girdi_boyu(self.aday)
        if girdi_boyu(self.resmi) != self.girdi:
            raise DegerlendirmeHatasi(
                f"aday girdisi {self.girdi}px, resmi modelinki {girdi_boyu(self.resmi)}px: "
                "aynı boydaki resmi modelle karşılaştırın (tiny 416, s 640)"
            )
        self.aday_ap = tespitci_ac(model, ayar, AP_GUVEN_ESIGI)
        self.resmi_ap = tespitci_ac(resmi, ayar, AP_GUVEN_ESIGI)
        self.aday_sureleri: list[float] = []
        self.resmi_sureleri: list[float] = []
        # Tanı için adayın sütunları (sınıf eşlemesi: model sütunu -> katalog kodu)
        esleme = dict(self.aday._sinif_esleme)
        forkliftler = [sutun for sutun, kod in esleme.items() if kod == FORKLIFT]
        self.forklift_sutunu = forkliftler[0] if forkliftler else None
        self.diger_sutunlar = sorted(sutun for sutun, kod in esleme.items() if kod != FORKLIFT)

    def isit(self, kareler: Iterable[np.ndarray]) -> None:
        for kare in kareler:
            self.aday.tespit_et(kare)
            self.resmi.tespit_et(kare)

    def calisma_noktasi(self, kare: np.ndarray, sira: int) -> tuple[list[Tespit], list[Tespit]]:
        """(aday, resmi) tespitleri; süreler ölçülür, sıra her görüntüde değişir."""
        sonuclar = {}
        cift = (
            (("aday", self.aday), ("resmi", self.resmi))
            if sira % 2 == 0
            else (("resmi", self.resmi), ("aday", self.aday))
        )
        for ad, tespitci in cift:
            baslangic = time.perf_counter()
            sonuclar[ad] = tespitci.tespit_et(kare)
            sure = time.perf_counter() - baslangic
            (self.aday_sureleri if ad == "aday" else self.resmi_sureleri).append(sure)
        return tespitleri_cevir(sonuclar["aday"]), tespitleri_cevir(sonuclar["resmi"])

    @staticmethod
    def _ham_calistir(tespitci, kare: np.ndarray) -> tuple[np.ndarray, float]:
        """Uygulamanın ön işlemesi ve oturumuyla ham çıktı [A, 5 + sınıf] ve letterbox oranı.

        İki modelin girdi boyu aynıdır (kurucu denetler): oran ikisinde de aynıdır.
        """
        girdi, oran_ = tespitci._on_isle(kare)
        with tespitci._kilit:
            cikti = tespitci._oturum.run(None, {tespitci._girdi_adi: girdi})[0]
        return cikti[0], oran_

    def ham_ciktilar(self, kare: np.ndarray) -> HamSonuc:
        """Aday ve resmi model birer kez çalışır; AP tespitleri (güven 0,01 örneklerinin
        son işlemesiyle), araç korumasının etiket görünümü ve tanının ham kutuları bu iki
        çıktıdan türetilir."""
        aday_ham, oran_ = self._ham_calistir(self.aday, kare)
        resmi_ham, _ = self._ham_calistir(self.resmi, kare)
        genislik, yukseklik = kare.shape[1], kare.shape[0]
        gorunum = etiket_gorunumu(aday_ham, resmi_ham)
        return HamSonuc(
            aday_ap=tespitleri_cevir(self.aday_ap._son_isle(aday_ham, oran_, genislik, yukseklik)),
            resmi_ap=tespitleri_cevir(
                self.resmi_ap._son_isle(resmi_ham, oran_, genislik, yukseklik)
            ),
            aday_arac=tespitleri_cevir(self.aday._son_isle(gorunum, oran_, genislik, yukseklik)),
            aday_kutular=ham_kutular(aday_ham, oran_, genislik, yukseklik, self.girdi),
            aday_puanlar=np.asarray(aday_ham[:, 4:5], np.float64) * aday_ham[:, 5:],
            resmi_kutular=ham_kutular(resmi_ham, oran_, genislik, yukseklik, self.girdi),
        )

    def kare(self, kare: np.ndarray) -> KareSonucu:
        """Video ya da araç seti karesi (süre ölçülmez): modeller birer kez çalışır."""
        aday_ham, oran_ = self._ham_calistir(self.aday, kare)
        resmi_ham, _ = self._ham_calistir(self.resmi, kare)
        genislik, yukseklik = kare.shape[1], kare.shape[0]
        return kareyi_olc(
            tespitleri_cevir(self.aday._son_isle(aday_ham, oran_, genislik, yukseklik)),
            tespitleri_cevir(self.resmi._son_isle(resmi_ham, oran_, genislik, yukseklik)),
            tespitleri_cevir(
                self.aday._son_isle(
                    etiket_gorunumu(aday_ham, resmi_ham), oran_, genislik, yukseklik
                )
            ),
        )


def _ilerleme(ne: str, sira: int, toplam: int, baslangic: float) -> None:
    if sira % _ILERLEME_ARALIGI == 0 or sira == toplam:
        print(f"  {ne}: {sira}/{toplam} ({time.monotonic() - baslangic:.0f} sn)", flush=True)


def videoyu_olc(yol: Path, olcer: Olcer) -> tuple[dict, dict, dict]:
    """(metrikler, sayılar, video bilgisi)."""
    kamera = cv2.VideoCapture(str(yol))
    try:
        if not kamera.isOpened():
            raise DegerlendirmeHatasi(f"video açılamadı: {yol}")
        toplam = int(kamera.get(cv2.CAP_PROP_FRAME_COUNT))
        if toplam <= 0:  # kapsayıcı söylemiyorsa sayılır
            while kamera.grab():
                toplam += 1
            kamera.release()
            kamera = cv2.VideoCapture(str(yol))
        adim = video_adimi(toplam)
        kareler: list[KareSonucu] = []
        baslangic = time.monotonic()
        no = 0
        while True:
            if no % adim == 0:
                okundu, kare = kamera.read()
                if not okundu:
                    break
                kareler.append(olcer.kare(kare))
                _ilerleme("video", len(kareler), math.ceil(toplam / adim), baslangic)
            elif not kamera.grab():
                break
            no += 1
    finally:
        kamera.release()
    if not kareler:
        raise DegerlendirmeHatasi(f"videodan kare okunamadı: {yol}")
    metrikler, sayilar = video_ozeti(kareler)
    bilgi = {"dosya": yol.name, "sha256": dosya_ozeti(yol), "kare_sayisi": toplam, "adim": adim}
    return metrikler, sayilar, bilgi


def arac_setini_olc(yollar: Sequence[Path], olcer: Olcer) -> tuple[dict, dict, dict]:
    """(metrikler, sayılar, araç seti bilgisi). Süre ölçülmez."""
    kareler: list[KareSonucu] = []
    ozet = hashlib.sha256()
    baslangic = time.monotonic()
    for sira, yol in enumerate(yollar, 1):
        kare = cv2.imread(str(yol), cv2.IMREAD_COLOR)
        if kare is None:
            raise DegerlendirmeHatasi(f"araç seti görüntüsü okunamadı: {yol}")
        ozet.update(f"{yol.name} {dosya_ozeti(yol)}\n".encode())
        kareler.append(olcer.kare(kare))
        _ilerleme("arac seti", sira, len(yollar), baslangic)
    metrikler, sayilar = arac_seti_ozeti(kareler)
    # Hangi görüntülerle ölçüldü: "ad özet" satırlarının özeti (sıra: ad)
    bilgi = {"klasor": yollar[0].parent.name, "goruntu": len(yollar), "sha256": ozet.hexdigest()}
    return metrikler, sayilar, bilgi


# ---------------------------------------------------------------------------
# Ölçüm, rapor, komut satırı
# ---------------------------------------------------------------------------


def olc(secenekler: argparse.Namespace) -> dict:
    """Bütün ölçüm: olcum.json içeriği."""
    baslangic = time.monotonic()
    ayar = uygulama_ayarlari()
    esikler = esikleri_oku(secenekler.esikler)
    goruntuler = olcum_setini_oku(secenekler.veri, secenekler.sinir)
    for ne, yol in (("model", secenekler.model), ("resmi model", secenekler.resmi)):
        if not yol.is_file():
            raise DegerlendirmeHatasi(f"{ne} dosyası yok: {yol}")
    if secenekler.video is not None and not secenekler.video.is_file():
        raise DegerlendirmeHatasi(f"video dosyası yok: {secenekler.video}")
    arac_yollari = (
        None
        if secenekler.arac_seti is None
        else arac_setini_oku(secenekler.arac_seti, secenekler.sinir)
    )

    olcer = Olcer(secenekler.model, secenekler.resmi, ayar)
    print(
        f"Olcum: {secenekler.model.name} / {secenekler.resmi.name}, {len(goruntuler)} goruntu, "
        f"girdi {olcer.girdi}px",
        flush=True,
    )
    olcer.isit(_kare_oku(g) for g in goruntuler[:ISINMA_GORUNTUSU])
    sonuclar = []
    tani: list[tuple[float, float, bool]] = []
    resmi_tavanlari: list[float] = []
    for sira, goruntu in enumerate(goruntuler):
        kare = _kare_oku(goruntu)
        aday, resmi = olcer.calisma_noktasi(kare, sira)
        ham = olcer.ham_ciktilar(kare)
        gercek = Gercek(
            goruntu.alt_kume,
            kare.shape[1],
            kare.shape[0],
            goruntu.forkliftler,
            goruntu.transpaletler,
        )
        sonuclar.append(
            goruntuyu_olc(
                gercek, aday, resmi, ham.aday_ap, ham.resmi_ap, olcer.girdi, ham.aday_arac
            )
        )
        if goruntu.forkliftler and olcer.forklift_sutunu is not None:
            yoksay = [
                not degerlendirilir_mi(k, gercek.genislik, gercek.yukseklik, olcer.girdi)
                for k in goruntu.forkliftler
            ]
            tani.extend(
                forklift_tanisi(
                    ham.aday_kutular,
                    ham.aday_puanlar,
                    goruntu.forkliftler,
                    yoksay,
                    olcer.forklift_sutunu,
                    olcer.diger_sutunlar,
                    ayar.guven_esigi,
                )
            )
            resmi_tavanlari.extend(kutu_tavanlari(ham.resmi_kutular, goruntu.forkliftler, yoksay))
        _ilerleme("goruntu", sira + 1, len(goruntuler), baslangic)

    metrikler, sayilar, alt_kumeler = ozetle(sonuclar)
    metrikler.update(tani_ozeti(tani, resmi_tavanlari))
    metrikler.update(gecikme_ozeti(olcer.aday_sureleri, olcer.resmi_sureleri))
    video = None
    if secenekler.video is not None:
        video_metrikleri, video_sayilari, video = videoyu_olc(secenekler.video, olcer)
        metrikler.update(video_metrikleri)
        sayilar.update(video_sayilari)
    arac_seti = None
    if arac_yollari is not None:
        arac_metrikleri, arac_sayilari, arac_seti = arac_setini_olc(arac_yollari, olcer)
        metrikler.update(arac_metrikleri)
        sayilar.update(arac_sayilari)
    gecti, kalan, kapilar = kapilari_degerlendir(metrikler, esikler)
    return {
        "etiket": secenekler.etiket or secenekler.model.stem,
        "tarih": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": secenekler.model.name,
        "model_sha256": dosya_ozeti(secenekler.model),
        "resmi": secenekler.resmi.name,
        "resmi_sha256": dosya_ozeti(secenekler.resmi),
        "model_forklift_taniyor": bool(olcer.aday.forklift_taniyor),
        "model_karti": _model_karti(olcer.aday),
        "girdi": olcer.girdi,
        "ayarlar": {
            "guven_esigi": ayar.guven_esigi,
            "insan_guven_esigi": ayar.insan_guven_esigi,
            "nms_esigi": ayar.nms_esigi,
            "en_kucuk_kenar_px": ayar.en_kucuk_kenar_px,
            "is_parcacigi": ayar.is_parcacigi,
            "ap_guven_esigi": AP_GUVEN_ESIGI,
            "iou_esigi": IOU_ESIGI,
            "en_kucuk_forklift_px": EN_KUCUK_FORKLIFT_PX,
            "isinma_goruntusu": min(ISINMA_GORUNTUSU, len(goruntuler)),
        },
        "goruntu_sayisi": len(goruntuler),
        "metrikler": metrikler,
        "sayilar": sayilar,
        "alt_kumeler": alt_kumeler,
        "video": video,
        "arac_seti": arac_seti,
        "esikler": esikler,
        "kapilar": kapilar,
        "gecti": gecti,
        "kalan": kalan,
        "sure_sn": round(time.monotonic() - baslangic, 1),
    }


def _bicimle(ad: str, deger: float | None) -> str:
    if deger is None:
        return "yok"
    return f"{deger:.1f}" if "_ms" in ad else f"{deger:.4f}"


def tablo(olcum: dict) -> str:
    """Günlük için kısa ASCII tablo."""
    video = olcum.get("video")
    arac_seti = olcum.get("arac_seti")
    satirlar = [
        f"Forklift olcumu: {olcum['etiket']} | girdi {olcum['girdi']} | "
        f"{olcum['goruntu_sayisi']} goruntu"
        + (f" | video {olcum['sayilar'].get('video_kare', 0)} kare" if video else "")
        + (f" | arac seti {arac_seti['goruntu']} goruntu" if arac_seti else ""),
        f"  {'metrik':<26}{'deger':>10}   {'kapi':<14}sonuc",
    ]
    kapilar: dict[str, list[dict]] = defaultdict(list)
    for kapi in olcum["kapilar"].values():
        kapilar[kapi["metrik"]].append(kapi)
    for ad in METRIKLER:
        if ad not in olcum["metrikler"] and ad not in kapilar:
            continue
        satir = f"  {ad:<26}{_bicimle(ad, olcum['metrikler'].get(ad)):>10}"
        for kapi in kapilar.get(ad, []):
            isaret = "<=" if kapi["yon"] == "en_fazla" else ">="
            satir += f"   {isaret} {kapi['esik']:<11.4g}{'gecti' if kapi['gecti'] else 'KALDI'}"
        satirlar.append(satir)
    if olcum["alt_kumeler"]:
        satirlar.append(
            f"  {'alt kume':<12}{'goruntu':>8}{'fk_gercek':>10}{'fk_r':>8}{'vg_r':>8}"
            f"{'vg_r_resmi':>11}{'fk_fp/g':>9}"
        )
        for ad, alt in olcum["alt_kumeler"].items():
            satirlar.append(
                f"  {ad:<12}{alt['goruntu']:>8}{alt['fk_gercek']:>10}"
                f"{_bicimle('', alt['fk_r']):>8}{_bicimle('', alt['vg_r']):>8}"
                f"{_bicimle('', alt['vg_r_resmi']):>11}"
                f"{_bicimle('', alt['fk_fp_goruntu_basi']):>9}"
            )
    satirlar.append(
        "SONUC: GECTI"
        if olcum["gecti"]
        else "SONUC: KALDI (kalan: " + ", ".join(olcum["kalan"]) + ")"
    )
    return "\n".join(satirlar)


def _pozitif_tamsayi(metin: str) -> int:
    try:
        deger = int(metin)
    except ValueError as hata:
        raise argparse.ArgumentTypeError(f"tamsayı bekleniyordu: {metin!r}") from hata
    if deger < 1:
        raise argparse.ArgumentTypeError(f"en az 1 olmalı: {deger}")
    return deger


def _ayristirici() -> argparse.ArgumentParser:
    ayristirici = argparse.ArgumentParser(
        prog="degerlendir.py",
        description="Forklift adayını ürünün tespit motoruyla resmi modele karşı ölçer.",
    )
    ayristirici.add_argument("--model", type=Path, required=True, help="aday ONNX")
    ayristirici.add_argument("--resmi", type=Path, required=True, help="resmi YOLOX ONNX")
    ayristirici.add_argument("--veri", type=Path, required=True, help="veri.py hazirla çıktısı")
    ayristirici.add_argument("--video", type=Path, default=None, help="etiketsiz deneme videosu")
    ayristirici.add_argument(
        "--arac-seti",
        type=Path,
        default=None,
        help="etiketsiz gerçek araç fotoğrafları klasörü (arac_seti_tr_fk)",
    )
    ayristirici.add_argument("--esikler", type=Path, default=VARSAYILAN_ESIKLER)
    ayristirici.add_argument("--cikti", type=Path, required=True, help="olcum.json")
    ayristirici.add_argument(
        "--sinir",
        type=_pozitif_tamsayi,
        default=None,
        help="en çok N test görüntüsü (forklift, boş, transpalet: sırayla) ve araç seti görüntüsü",
    )
    ayristirici.add_argument("--etiket", default=None, help="ör. tiny-v1 (varsayılan: model adı)")
    return ayristirici


def main(argv: Sequence[str] | None = None) -> int:
    secenekler = _ayristirici().parse_args(argv)
    try:
        olcum = olc(secenekler)
        print(tablo(olcum), flush=True)
        print(
            "OLCUM_JSON " + json.dumps(olcum, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )
        try:
            secenekler.cikti.parent.mkdir(parents=True, exist_ok=True)
            secenekler.cikti.write_text(
                json.dumps(olcum, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as hata:
            raise DegerlendirmeHatasi(f"{secenekler.cikti} yazılamadı: {hata}") from hata
    except DegerlendirmeHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

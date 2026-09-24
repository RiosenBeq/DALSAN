"""Yerelde eğitilen forklift modelini programa kurar (Forklift sayfası, "Modeli kur").

Operatör, 24.09.2026: "sadece yüklesem yeter mi ekstra kod vs. bir şey yapmam
lazım mı?" Kapalı bilgisayardaki eğitim (egitim/forklift/yerel.py) sonunda
KURULACAK/ klasörüne iki dosya bırakır: model (.onnx) ve ölçümü (.olcum.json,
egitim/forklift/degerlendir.py). Program ikisini alır ve kurmadan önce denetler:

1. Ölçüm bu modele ait: ölçümdeki model_sha256, yüklenen dosyanın SHA-256'sı.
2. Tabanı hazır model: ölçümdeki resmi model BILINEN_MODELLER'den biri ve özeti
   tutuyor. Forklift modeli insanı ve aracı onunla AYNI tanır; açılamazsa
   süpervizör ona döner (model_indir.forklift_yedegi, MODEL_FALLBACK).
3. Kapılar: ölçümdeki metrikler, ürünün taşıdığı eşiklerle (KAPILAR,
   egitim/forklift/esikler.json'un kopyası; test ikisini karşılaştırır) YENİDEN
   değerlendirilir. Ölçülmemiş metrik kapıyı kaldırır; biri kalırsa kurulmaz
   (docs/17 §12.3-8: aday ancak kapıların hepsini geçerse seçilebilir olur).
4. Kısa deneme (duman, ön deneme) modeli kurulmaz (model kartı).
5. Model ürünün kendi tespit motoruyla (Tespitci) açılır ve forklifti ayrı
   sınıf olarak tanıdığı görülür.

Geçen model models/nextgen_forklift_<boy>_yerel_<sha8>.onnx adıyla, ölçümü
yanına .olcum.json olarak konur. Seçim DEĞİŞMEZ: model Ayarlar'daki "Tanıma
modeli" listesinde seçilebilir olur; hangi modelin çalışacağı operatörün
seçimidir (§12.3-8).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app import zaman
from app.analiz.model_adi import gorunen_model_adi
from app.analiz.model_indir import BILINEN_MODELLER, yerel_forklift_modelleri
from app.hatalar import DogrulamaHatasi

# egitim/forklift/esikler.json'un kopyası: paketlenmiş programda eğitim klasörü
# yoktur (ürün dışıdır). İkisi test ile aynı tutulur (tests/test_forklift_kurulum.py).
KAPILAR: dict[str, float] = {
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
# Kapıların ekrandaki adları: egitim/forklift/yerel.py METRIK_ADLARI ile aynı (test)
METRIK_ADLARI = {
    "insan_kaybi": "Kaybolan insan (resmi modelin bulduğu)",
    "arac_kaybi": "Kaybolan araç (resmi modelin bulduğu)",
    "vg_r_artisi": "Forkliftlerin araç olarak bulunmasındaki artış",
    "fk_r": "Forklift bulma oranı",
    "fk_fp_goruntu_basi": "Forkliftsiz karede yanlış forklift (kare başına)",
    "pt_fk": "Transpaletin forklift sanılması",
    "fk_kesinlik": "Forklift kesinliği (doğru tespit oranı)",
    "arac_seti_tr_fk": "Tırın forklift sanılması (araç seti)",
    "video_insan_kaybi": "Videoda kaybolan insan",
    "video_fk_kare_orani": "Videoda yanlış forklift (kare oranı)",
    "gecikme_orani_p90": "Yavaşlama (resmi modele göre, p90)",
}
# Tabanı olabilecek hazır modeller ve boyları (ad = nextgen_forklift_<boy>_yerel_...)
TABAN_BOYLARI = {"yolox_tiny.onnx": "tiny", "yolox_s.onnx": "s"}
KISA_DENEME_KIPLERI = frozenset({"duman", "on_deneme"})
OLCUM_UZANTISI = ".olcum.json"
# Tiny ~22 MB, s ~40 MB; sınır bozuk ya da yanlış dosyayı belleğe almamak için.
EN_BUYUK_MODEL_BAYT = 300 * 1024 * 1024
EN_BUYUK_OLCUM_BAYT = 5 * 1024 * 1024


class KurulumHatasi(DogrulamaHatasi):
    """Model kurulmadı; sebebi ve yapılacak iş kullanıcı mesajındadır."""


def dosya_ozeti(yol: Path) -> str:
    ozet = hashlib.sha256()
    with yol.open("rb") as dosya:
        for parca in iter(lambda: dosya.read(1 << 20), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def _olculdu_mu(deger: object) -> bool:
    return isinstance(deger, int | float) and not isinstance(deger, bool) and math.isfinite(deger)


def kalan_kapilar(metrikler: dict) -> list[str]:
    """KAPILAR'dan geçmeyenler (egitim/forklift/degerlendir.py kapilari_degerlendir
    ile aynı kural: ölçülmemiş metrik kapıyı kaldırır)."""
    kalan = []
    for ad, esik in KAPILAR.items():
        metrik, _, yon = ad.rpartition("_en_")
        deger = metrikler.get(metrik)
        if not _olculdu_mu(deger):
            kalan.append(ad)
        elif (yon == "fazla" and deger > esik) or (yon == "az" and deger < esik):
            kalan.append(ad)
    return kalan


def kapi_adi(ad: str) -> str:
    metrik = ad.rpartition("_en_")[0]
    return METRIK_ADLARI.get(metrik, metrik)


@dataclass(frozen=True)
class Aday:
    """Denetimden geçen ölçüm: modelin özeti, tabanı ve ölçümün kendisi."""

    sha256: str
    taban: str
    olcum: dict

    @property
    def dosya_adi(self) -> str:
        return f"nextgen_forklift_{TABAN_BOYLARI[self.taban]}_yerel_{self.sha256[:8]}.onnx"


def olcumu_denetle(olcum_baytlari: bytes, model_sha256: str) -> Aday:
    """1-4. denetimler (dosya açılmadan); geçmezse KurulumHatasi."""
    try:
        olcum = json.loads(olcum_baytlari)
    except ValueError as hata:
        raise KurulumHatasi(
            "Ölçüm dosyası okunamadı. Eğitim klasöründeki KURULACAK'ta duran "
            ".olcum.json dosyasını seçin.",
            f"Ölçüm JSON değil: {hata}",
        ) from hata
    if not isinstance(olcum, dict) or not isinstance(olcum.get("metrikler"), dict):
        raise KurulumHatasi(
            "Seçilen dosya bir forklift ölçümü değil. Eğitim klasöründeki KURULACAK'ta "
            "duran .olcum.json dosyasını seçin."
        )
    if olcum.get("model_sha256") != model_sha256:
        raise KurulumHatasi(
            "Ölçüm dosyası bu modele ait değil (başka bir adayın ölçümü). KURULACAK "
            "klasöründe yan yana duran iki dosyayı birlikte seçin.",
            f"Ölçümdeki model {olcum.get('model_sha256')!r}, yüklenen {model_sha256}",
        )
    taban = olcum.get("resmi")
    if taban not in TABAN_BOYLARI or olcum.get("resmi_sha256") != BILINEN_MODELLER.get(taban):
        raise KurulumHatasi(
            "Model, programın hazır modellerinden biri üzerine eğitilmemiş; kurulmaz.",
            f"Ölçümdeki resmi model {taban!r} / {olcum.get('resmi_sha256')!r}",
        )
    kart = olcum.get("model_karti")
    if isinstance(kart, dict) and kart.get("calistirma_kipi") in KISA_DENEME_KIPLERI:
        raise KurulumHatasi(
            "Bu model yalnız kurulumu sınayan kısa denemenin (duman) modeli; kurulmaz. "
            "Eğitimi --duman olmadan çalıştırın."
        )
    if not olcum.get("model_forklift_taniyor"):
        raise KurulumHatasi("Model forklifti ayrı sınıf olarak tanımıyor; kurulmaz.")
    kalan = kalan_kapilar(olcum["metrikler"])
    if kalan:
        raise KurulumHatasi(
            "Model ölçüm kapılarından geçmedi; program onu kurmaz. "
            f"Kalan: {'; '.join(kapi_adi(ad) for ad in kalan)}. Eğitim sonucundaki "
            "(SONUC.txt) önerilere bakın.",
            f"Kalan kapılar: {kalan}",
        )
    return Aday(sha256=model_sha256, taban=taban, olcum=olcum)


def kur(
    gecici_model: Path,
    olcum_baytlari: bytes,
    modeller_klasoru: Path,
    modeli_ac: Callable[[Path], object],
) -> tuple[str, bool]:
    """Yüklenen modeli (modeller klasöründeki geçici dosya) denetleyip kurar.

    `modeli_ac` ürünün tespit motorudur (Tespitci; açılamazsa ModelHatasi).
    Döner: (kurulan dosya adı, yeni mi). Aynı model zaten kuruluysa dokunulmaz.
    Başarıda geçici dosya yerine taşınır; hata ve "zaten kurulu" durumunda
    silinmesi çağıranın işidir.
    """
    sha = dosya_ozeti(gecici_model)
    aday = olcumu_denetle(olcum_baytlari, sha)
    hedef = modeller_klasoru / aday.dosya_adi
    if hedef.is_file():
        if dosya_ozeti(hedef) == sha:
            return aday.dosya_adi, False
        raise KurulumHatasi(
            "Aynı adlı başka bir model kurulu; bu model kurulmadı. Destek ekibine iletin.",
            f"Ad çakışması: {hedef}",
        )
    tespitci = modeli_ac(gecici_model)
    if not getattr(tespitci, "forklift_taniyor", False):
        raise KurulumHatasi("Model açıldı ama forklifti ayrı sınıf olarak tanımıyor; kurulmaz.")
    hedef.with_suffix(OLCUM_UZANTISI).write_bytes(olcum_baytlari)
    os.replace(gecici_model, hedef)
    return aday.dosya_adi, True


def kurulu_modeller(modeller_klasoru: Path, secili_model: Path) -> list[dict]:
    """Forklift sayfasının listesi: kurulu yerel modeller, ölçümlerinin özeti.

    Kişisel veri yok: ölçüm dosyası yalnız sayılar tutar.
    """
    satirlar = []
    for ad, taban in yerel_forklift_modelleri(modeller_klasoru).items():
        yol = modeller_klasoru / ad
        try:
            olcum = json.loads(yol.with_suffix(OLCUM_UZANTISI).read_text(encoding="utf-8"))
            metrikler = olcum.get("metrikler") or {}
        except (OSError, ValueError, AttributeError):
            olcum, metrikler = {}, {}
        try:
            kurulma = datetime.fromtimestamp(yol.stat().st_mtime, UTC).isoformat()
        except OSError:
            continue
        satirlar.append(
            {
                "ad": ad,
                "gorunen": gorunen_model_adi(ad),
                "taban": gorunen_model_adi(taban),
                "kurulma": zaman.ekranda_goster(kurulma),
                "secili": secili_model.name == ad,
                "goruntu": olcum.get("goruntu_sayisi"),
                "fk_r": metrikler.get("fk_r"),
                "fk_kesinlik": metrikler.get("fk_kesinlik"),
                "fk_fp": metrikler.get("fk_fp_goruntu_basi"),
                "fk_ap50": metrikler.get("fk_ap50"),
            }
        )
    return list(reversed(satirlar))  # en yenisi üstte

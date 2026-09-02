"""Tespit modelini ilk açılışta otomatik indirir (models/indir.sh ile aynı kaynak).

Model ağırlıkları depoya girmez (CLAUDE.md §7). Kullanıcı terminal komutu
çalıştırmasın diye (CLAUDE.md §8) eksik model, sistem açılırken BİR KEZ
indirilir. Yalnızca YOLOX'un resmi yayın dosyaları bilinir; başka bir ad
verilmişse indirilmez, kullanıcıya dosyayı kendisinin koyması söylenir.
"""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from app.analiz.model_adi import MARKA, gorunen_model_adi
from app.hatalar import DalsanHata

# ADR-002: Apache-2.0 lisanslı YOLOX resmi yayınları (models/indir.sh ile aynı)
_YAYIN_ADRESI = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/"
BILINEN_MODELLER = ("yolox_tiny.onnx", "yolox_s.onnx")


class ModelIndirmeHatasi(DalsanHata):
    """İnternet yok / adres erişilemez — sistem tespitsiz devam eder.

    Kullanıcı mesajında indirme adresi YOKTUR (bkz. `_indirme_hata_metinleri`);
    tam adres `teknik_ayrinti` üzerinden sistem.log'a gider.
    """


def indirilebilir_mi(model_dosyasi: Path) -> bool:
    return model_dosyasi.name in BILINEN_MODELLER


def ozel_model_hatasi(model_dosyasi: Path) -> ModelIndirmeHatasi:
    """Hazır listede olmayan model için ORTAK açıklama (tek metin kaynağı).

    İki yerden çağrılır: indirme denendiğinde ve süpervizör indirmeyi
    atladığında. Böylece kendi modelini koyan kullanıcı hangi yoldan gelirse
    gelsin aynı, markalı açıklamayı görür — ham dosya yolunu değil.
    """
    # Ekranda dosya adı GEÇMEZ (kullanıcı yazılımcı değil); tam ad günlüğe gider.
    hazir_adlar = " veya ".join(gorunen_model_adi(ad) for ad in BILINEN_MODELLER)
    return ModelIndirmeHatasi(
        f"{gorunen_model_adi(model_dosyasi.name)} kendiliğinden inemez: seçili model, "
        f"hazır modellerden ({hazir_adlar}) biri değil. Kendi eğittiğiniz bir modeli "
        "kullanıyorsanız, model dosyanızı .env ayar dosyasındaki MODEL_DOSYASI "
        "satırında yazan yere koyun. Hazır modele dönmek için: program klasöründeki "
        ".env dosyasını bir metin düzenleyiciyle açın, MODEL_DOSYASI ile başlayan "
        "satırı yanındaki .env.example dosyasında yazdığı gibi düzeltip kaydedin, "
        "sonra Kontrol Paneli'nde Durdur'a ve Sistemi Başlat'a basın.",
        f"Otomatik indirme atlandı: {model_dosyasi} bilinen yayın dosyalarından "
        f"({', '.join(BILINEN_MODELLER)}) biri değil.",
    )


def modeli_indir(model_dosyasi: Path, ilerleme: Callable[[int, int], None] | None = None) -> None:
    """Modeli `.part` dosyasına indirip bitince adını değiştirir — yarım
    kalan indirme asla 'geçerli model' sanılmaz."""
    if not indirilebilir_mi(model_dosyasi):
        raise ozel_model_hatasi(model_dosyasi)
    adres = _YAYIN_ADRESI + model_dosyasi.name
    gecici = model_dosyasi.with_suffix(model_dosyasi.suffix + ".part")
    try:
        model_dosyasi.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(adres, timeout=30) as yanit, gecici.open("wb") as hedef:
            toplam = int(yanit.headers.get("Content-Length") or 0)
            inen = 0
            while True:
                parca = yanit.read(1024 * 256)
                if not parca:
                    break
                hedef.write(parca)
                inen += len(parca)
                if ilerleme is not None:
                    ilerleme(inen, toplam)
        if gecici.stat().st_size < 1024 * 1024:
            raise ModelIndirmeHatasi(
                f"{MARKA} eksik indi. İnternet bağlantısını kontrol edip Kontrol Paneli'nde "
                "Durdur'a, sonra Sistemi Başlat'a basın.",
                f"İndirilen model dosyası beklenmedik biçimde küçük "
                f"({gecici.stat().st_size} bayt): {adres} → {gecici}",
            )
        gecici.replace(model_dosyasi)
    except (urllib.error.URLError, TimeoutError, OSError) as hata:
        gecici.unlink(missing_ok=True)
        kullanici_mesaji, teknik_ayrinti = _indirme_hata_metinleri(adres, model_dosyasi, hata)
        raise ModelIndirmeHatasi(kullanici_mesaji, teknik_ayrinti) from hata


def _indirme_hata_metinleri(adres: str, model_dosyasi: Path, hata: Exception) -> tuple[str, str]:
    """(ekrana çıkan sade mesaj, günlüğe yazılan tam ayrıntı) döndürür.

    İndirme adresi EKRANA ÇIKMAZ: kullanıcı yazılımcı değil, uzun bir GitHub
    adresi ana sayfada ne yapacağını söylemez, yalnızca korkutur. Tam adres,
    hedef dosya ve özgün hata metni veri/loglar/sistem.log'a yazılır — destek
    akışı oradan kopyalandığı için hiçbir bilgi kaybolmaz.

    Sebebe göre DOĞRU çözümü söyler — "internetinizi kontrol edin" her zaman
    doğru teşhis değildir.
    """
    sebep = getattr(hata, "reason", hata)
    if isinstance(sebep, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(hata):
        kullanici_mesaji = (
            f"{MARKA} indirilemedi: güvenlik sertifikaları doğrulanamadı. "
            "Mac'te python.org'dan kurulan Python'da bu sık görülür. Çözüm: Uygulamalar → "
            "Python 3.x klasöründeki 'Install Certificates.command' dosyasına çift tıklayın, "
            "sonra Kontrol Panelinden yeniden başlatın."
        )
    else:
        kullanici_mesaji = (
            f"{MARKA} indirilemedi. İnternet bağlantısını kontrol edip "
            "Kontrol Panelinden yeniden başlatın."
        )
    teknik_ayrinti = (
        f"{kullanici_mesaji} | indirme adresi: {adres} | hedef dosya: {model_dosyasi} "
        f"| özgün hata: {hata!r}"
    )
    return kullanici_mesaji, teknik_ayrinti

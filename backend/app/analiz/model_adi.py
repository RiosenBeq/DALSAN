"""Tespit modelinin KULLANICIYA GÖRÜNEN adı - tek kaynak.

Ekranda teknik dosya adı değil, ürün adı yazar. Dosya adları, indirme
adresleri ve `.env` içindeki `MODEL_DOSYASI` anahtarı AYNEN kalır: sistem
modeli onlarla bulur, indirme adresi de yerel dosya adından kurulur. Burada
değişen yalnızca ekrana basılan metindir.

Modül SAF tutulur (yalnızca stdlib): hem web katmanı hem analiz katmanı aynı
adı üretsin, iki yerde iki farklı isim çıkmasın diye.

Alttaki açık kaynak bileşenlerin lisans atfı depo kökündeki
LICENSE-THIRD-PARTY dosyasındadır.
"""

from __future__ import annotations

import re

from app import kaynaklar

MARKA = "NextGen AI"

# Dosya adı (küçük harfle) → ekranda görünen ad.
# Anahtarlar model_indir.BILINEN_MODELLER ile aynı dosyaları gösterir;
# tests/test_gorunen_model_adi.py bu iki listenin ayrışmasını engeller.
GORUNEN_ADLAR: dict[str, str] = {
    "yolox_tiny.onnx": f"{MARKA} Hızlı",
    "yolox_s.onnx": f"{MARKA} İsabetli",
}

# Tanınmayan dosya: kullanıcı kendi eğittiği modeli koymuş olabilir.
OZEL_MODEL_ADI = f"{MARKA} (özel model)"

# Fabrikanın kendi verisiyle yerelde eğitilip Forklift sayfasından kurulan model
# (egitim/forklift/yerel.py, web/forklift_web.py). Ad, tabanı (insanı ve aracı
# aynı tanıyan hazır model: yolox_<boy>.onnx) ve SHA-256'nın ilk 8 hanesini
# taşır: tabanı adından bulunur, dosya silinse ya da bozulsa da yedek bellidir.
YEREL_FORKLIFT_ADI = re.compile(r"nextgen_forklift_(tiny|s)_yerel_([0-9a-f]{8})\.onnx")
# Tabanın dosya adı kalıbı (teknik sabit, ekrana çıkmaz): boy -> hazır model dosyası
YEREL_FORKLIFT_TABANI = "yolox_{boy}.onnx"


def yerel_forklift_tabani(dosya_adi: str) -> str | None:
    """Yerel forklift modelinin tabanının dosya adı; yerel model değilse None."""
    eslesme = YEREL_FORKLIFT_ADI.fullmatch(dosya_adi.strip().lower())
    return YEREL_FORKLIFT_TABANI.format(boy=eslesme.group(1)) if eslesme else None


# Model hatalarının ortak çözüm cümlesi. Model Ayarlar'dan seçilir (.env'i
# elle düzenletmek yok: paketlenmiş programda o dosya program klasöründe
# bile değildir); web arayüzü model çalışmasa da açılır.
def hazir_modele_donus() -> str:
    """Hazır modele dönüş tarifi; yeniden başlatma kuruluma göre (app/kaynaklar.py)."""
    return (
        "Hazır modele dönmek için Ayarlar'daki “Tanıma modeli” listesinden bir hazır "
        f"model seçip kaydedin ve {kaynaklar.baslatma_tarifi(cumle_basi=False)}."
    )


def gorunen_model_adi(dosya_adi: str) -> str:
    """Model dosyasının adından, kullanıcıya gösterilecek adı üretir.

    Windows dosya adlarında büyük/küçük harf ayrımı olmadığı için karşılaştırma
    küçük harf üzerinden yapılır; ekranda yine de ürün adı görünür.
    """
    ad = dosya_adi.strip().lower()
    if ad in GORUNEN_ADLAR:
        return GORUNEN_ADLAR[ad]
    taban = yerel_forklift_tabani(ad)
    if taban is not None:
        surum = YEREL_FORKLIFT_ADI.fullmatch(ad).group(2)
        return f"{GORUNEN_ADLAR.get(taban, MARKA)} + Forklift (fabrika eğitimi {surum})"
    return OZEL_MODEL_ADI

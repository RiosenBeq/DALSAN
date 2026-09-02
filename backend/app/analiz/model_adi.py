"""Tespit modelinin KULLANICIYA GÖRÜNEN adı — tek kaynak.

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


def gorunen_model_adi(dosya_adi: str) -> str:
    """Model dosyasının adından, kullanıcıya gösterilecek adı üretir.

    Windows dosya adlarında büyük/küçük harf ayrımı olmadığı için karşılaştırma
    küçük harf üzerinden yapılır; ekranda yine de ürün adı görünür.
    """
    return GORUNEN_ADLAR.get(dosya_adi.strip().lower(), OZEL_MODEL_ADI)

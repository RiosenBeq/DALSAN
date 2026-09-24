"""Forklift modeli eğitiminin ortak sabitleri (operatör isteği 23.09.2026).

Tasarım (docs/17 §12.3): resmi YOLOX COCO modeli DONDURULUR ve hiç
değişmez; yanına yalnız iki yeni sınıfı (forklift, el transpaleti) öğrenen
küçük bir "ek baş" eğitilir. Dışa aktarımda ikisi tek ONNX'te birleşir:
kutular ve insan/araç puanları resmi modelinkiyle aynıdır, forklift puanı
ek baştan gelir. Böylece insan ve araç tanıma yapı gereği korunur.

Veri: LOCO (TU München, CC0 1.0). Bu dosya yalnız standart kütüphaneyle
çalışır; veri hazırlama, eğitim, dışa aktarım ve ölçüm betiklerinin hepsi
buradaki sabitleri kullanır.
"""

from __future__ import annotations

# Ek başın öğrendiği sınıflar. Eğitim JSON'unda COCO kategori kimlikleri 1 ve 2
# (YOLOX COCODataset: sınıf indeksi = sıralı kategori kimliklerindeki sırası).
EK_SINIFLAR = ("forklift", "pallet_jack")

# Birleşik ONNX'in sınıf sütunları (çıktı sütunu 5 + i).
CIKIS_SINIFLARI = ("person", "forklift", "truck", "pallet_jack", "car", "bus")

# ONNX üst verisi "dalsan_classes" (backend/app/analiz/tespit.py::sinif_eslemesi).
# Sözlük biçimi: pallet_jack eşlenmez, uygulama onu sessizce yok sayar (katalogda
# yok, S12). car ve bus bugünkü COCO eşlemesindeki gibi "truck" sayılır: mesafe
# kuralının araç grubu bütün kalır (docs/17 §12.3-5).
DALSAN_SINIFLARI = {"0": "person", "1": "forklift", "2": "truck", "4": "truck", "5": "truck"}

# Resmi COCO modelinin ilgili sınıf satırları
RESMI_SATIRLAR = {"person": 0, "car": 2, "bus": 5, "truck": 7}

# Model boyları: resmi YOLOX-tiny (416) ve YOLOX-s (640)
BOYLAR = {
    "tiny": {"derinlik": 0.33, "genislik": 0.375, "girdi": 416, "parti": 16},
    "s": {"derinlik": 0.33, "genislik": 0.50, "girdi": 640, "parti": 8},
}

# v1: ek baş resmi başın kendi özniteliklerinin üstünde yalnız 1x1 katman
#     (neredeyse sıfır ek işlemci yükü).
# v2: ek başın kendi sınıf dalı (iki 3x3 evrişim) + 1x1 katman.
# v3: ek başın kendi kutu dalı (iki 3x3 evrişim + kutu ve nesne katmanı) +
#     resmi sınıf özniteliği üstünde 1x1 sınıf katmanı. Forkliftin kazandığı
#     çapada kutu da ek baştan gelir (model.py, "Neden v3").
KIPLER = ("v1", "v2", "v3")

# ---- Sabitlenmiş kaynaklar (sha256) ----

YOLOX_COMMIT = "6ddff4824372906469a7fae2dc3206c7aa4bbaee"
_YOLOX_YAYIN = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/"
RESMI_AGIRLIKLAR = {
    "tiny": (
        _YOLOX_YAYIN + "yolox_tiny.pth",
        "9de513de589ac98bb92d3bca53b5af7b9acfa9b0bacb831f7999d0f7afaee8f0",
    ),
    "s": (
        _YOLOX_YAYIN + "yolox_s.pth",
        "f55ded7181e1b0c13285c56e7790b8f0e8f8db590fe4edb37f0b7f345c913a30",
    ),
}
# Resmi ONNX dosyaları uygulamanın models/ klasöründekilerle aynıdır
# (models/SHA256SUMS); karşılaştırma için models/indir.sh ile indirilir.
RESMI_ONNX = {"tiny": "yolox_tiny.onnx", "s": "yolox_s.onnx"}

LOCO_COMMIT = "b460ab8c37f09162f0613c7546948c496e1b1628"
_LOCO_HAM = f"https://raw.githubusercontent.com/tum-fml/loco/{LOCO_COMMIT}/"
LOCO_ETIKET = (
    _LOCO_HAM + "rgb/loco-all-v1.json",
    "5a794d2e61f308150039e3e1953bc57e8fad208bb3e2b9117245230ec1c22054",
)
LOCO_LISANS = (
    _LOCO_HAM + "LICENSE",
    "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499",
)
# Kısa bağlantı TUM'un dosya sunucusuna yönlenir; ikincisi onun doğrudan adresi.
# 23.09.2026 yoklaması: 769.055.500 bayt, application/zip, kısmi indirme var.
LOCO_ARSIV_ADRESLERI = (
    "https://go.mytum.de/239870",
    "https://webdisk.ads.mwn.de/Handlers/AnonymousDownload.ashx"
    "?folder=73e976ba&path=LOCO%5Cv1%5Cdataset.zip",
)
LOCO_ARSIV_BOYUTU = 769_055_500
# İlk gerçek indirmede (GitHub Actions, 23.09.2026, 5689 üye) ölçüldü ve
# sabitlendi: arşiv değişirse veri.py indirmeyi reddeder. None iken özet yalnız
# günlüğe yazılırdı.
LOCO_ARSIV_SHA256: str | None = "f3629d989071b824edc63e000f45ccc5826cfbb201a338f16ed87ab3e10bcdcf"

# Yazarların kendi bölmesi, ortam ayrık: 2-3-5 eğitim, 1-4 test.
EGITIM_ALT_KUMELERI = ("subset-2", "subset-3", "subset-5")
TEST_ALT_KUMELERI = ("subset-1", "subset-4")

# LOCO sınıfı -> ek baş sınıfı; palet, küçük yük taşıyıcı ve kafes atılır.
LOCO_ESLEME = {"forklift": "forklift", "pallet_truck": "pallet_jack"}

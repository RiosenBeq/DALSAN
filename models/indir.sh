#!/bin/bash
# DALSAN İSG — tespit modellerini indirir (model ağırlıkları repoya girmez).
# Kullanım: bash models/indir.sh
# YOLOX (Apache-2.0) resmi yayın dosyaları — ADR-002 karar gerekçesi docs/05'te.
set -e
cd "$(dirname "$0")"

indir() {
  ad="$1"; url="$2"
  if [ -s "$ad" ]; then
    echo "✓ $ad zaten var, atlandı"
  else
    echo "▶ $ad indiriliyor..."
    curl -L --fail --progress-bar -o "$ad.part" "$url"
    mv "$ad.part" "$ad"
    echo "✓ $ad indirildi"
  fi
}

indir yolox_tiny.onnx "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx"
indir yolox_s.onnx    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx"

echo ""
echo "Tamam. Geliştirmede yolox_tiny (hızlı), fabrikada yolox_s (isabetli) kullanılır."
echo "Seçim .env dosyasındaki MODEL_DOSYASI ayarıyla yapılır."

#!/bin/bash
# DALSAN İSG - tespit modellerini indirir ve DOĞRULAR (model ağırlıkları repoya girmez).
# Kullanım: bash models/indir.sh
# YOLOX (Apache-2.0) resmi yayın dosyaları - ADR-002 karar gerekçesi docs/05'te.
#
# Her dosya models/SHA256SUMS'taki özetle karşılaştırılır (docs/17 §10.5 R17);
# tutmayan dosya kullanılmaz. Aynı özetler backend/app/analiz/model_indir.py
# içinde de durur - tests/test_model_butunlugu.py ikisinin aynı kaldığını denetler.
set -e
cd "$(dirname "$0")"

YAYIN="https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0"
# Forklift tanıyan modeller bu deponun kendi yayınındadır (egitim/forklift,
# docs/17 §12.3); backend/app/analiz/model_indir.py DALSAN_MODELLERI ile aynı.
DALSAN_YAYINI="https://github.com/RiosenBeq/DALSAN/releases/download"

# Dosya, SHA256SUMS'taki kendi satırıyla tutuyor mu? (Linux: sha256sum,
# Mac: shasum - ikisi de işletim sistemiyle gelir.) Denetlenen dosya adı
# ikinci argümandır: indirme .part dosyasına yapılır, satır asıl adı taşır.
ozet_tutuyor_mu() {
  ad="$1"; dosya="$2"
  satir="$(grep "  $ad\$" SHA256SUMS | sed "s|  $ad\$|  $dosya|")"
  [ -n "$satir" ] || return 1
  if command -v sha256sum >/dev/null 2>&1; then
    echo "$satir" | sha256sum -c >/dev/null 2>&1
  else
    echo "$satir" | shasum -a 256 -c >/dev/null 2>&1
  fi
}

# İnmeyen ya da doğrulanamayan dosya: hazır YOLOX modeli ZORUNLUDUR (sistem
# onsuz tespit yapmaz), betik durur. Forklift modeli (DALSAN yayını) yalnız
# Ayarlar'da seçilirse gerekir: uyarı yazılır, betik öteki modellerle biter.
basarisiz() {
  ad="$1"; zorunlu="$2"
  rm -f "$ad.part"
  if [ -n "$zorunlu" ]; then
    exit 1
  fi
  echo "  $ad isteğe bağlıdır (Ayarlar'da seçilmedikçe gerekmez); öteki modellerle devam ediliyor." >&2
}

# indir <dosya> [<DALSAN yayın etiketi>/<yayın dosyası>]: ikinci argüman yoksa
# dosya YOLOX'un resmi yayınından, aynı adla iner.
indir() {
  ad="$1"
  if [ -n "${2:-}" ]; then
    adres="$DALSAN_YAYINI/$2"; zorunlu=""
  else
    adres="$YAYIN/$ad"; zorunlu=1
  fi
  if [ -s "$ad" ]; then
    if ozet_tutuyor_mu "$ad" "$ad"; then
      echo "✓ $ad zaten var ve doğrulandı, atlandı"
      return
    fi
    # Silinmez, kenara alınır: aynı adla kendi modelini koyan birinin dosyası kaybolmasın.
    mv "$ad" "$ad.eski"
    echo "✗ $ad doğrulanamadı (bozuk ya da farklı bir sürüm): $ad.eski olarak kenara alındı."
  fi
  echo "▶ $ad indiriliyor..."
  if ! curl -L --fail --progress-bar -o "$ad.part" "$adres"; then
    echo "✗ $ad indirilemedi. İnternet bağlantısını ve güvenlik duvarında github.com ile" >&2
    echo "  release-assets.githubusercontent.com'un açık olduğunu kontrol edip yeniden deneyin." >&2
    basarisiz "$ad" "$zorunlu"
    return 0
  fi
  if ! ozet_tutuyor_mu "$ad" "$ad.part"; then
    echo "✗ $ad indirildi ama doğrulanamadı: dosya eksik, bozuk ya da yolda değiştirilmiş." >&2
    echo "  İnternet bağlantısını kontrol edip yeniden deneyin. Sürerse bilgi işlem birimine" >&2
    echo "  haber verin: ağdaki bir güvenlik cihazı indirilen dosyayı değiştiriyor olabilir." >&2
    basarisiz "$ad" "$zorunlu"
    return 0
  fi
  mv "$ad.part" "$ad"
  echo "✓ $ad indirildi ve doğrulandı"
}

indir yolox_tiny.onnx
indir yolox_s.onnx

echo ""
echo "Tamam. Geliştirmede NextGen AI Hızlı, fabrikada NextGen AI İsabetli kullanılır."
echo "Seçim Ayarlar sayfasındaki “Tanıma modeli” listesinden yapılır."

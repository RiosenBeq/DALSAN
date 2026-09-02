#!/bin/bash
# ============================================================================
#  NextGen Detector — Mac uygulamasi (.app) uretir.
#  Bu dosyaya CIFT TIKLAYIN. Baska hicbir sey yapmaniza gerek yoktur.
#
#  Sonuc: dist/NextGen Detector.app   (islem sonunda Finder'da acilir)
#  Sure : ilk seferde 2-5 dakika.
# ============================================================================

# Calistirma izni kaybolmus olabilir (ZIP ile geldiyse). Kendi iznimizi tazele.
chmod +x "$0" 2>/dev/null

cd "$(dirname "$0")/.." || exit 1
DEPO="$(pwd)"
PY="$DEPO/.venv/bin/python"

echo ""
echo "=============================================================="
echo "  NextGen Detector — Mac uygulamasi uretiliyor"
echo "=============================================================="
echo ""

if [ ! -x "$PY" ]; then
  echo "  [HATA] Yalitilmis Python ortami bulunamadi."
  echo ""
  echo "  Cozum: once Baslat-Mac.command dosyasina cift tiklayip"
  echo "         'Ilk Kurulumu Yap' dugmesine basin, sonra buraya donun."
  echo ""
  read -r -p "  Kapatmak icin Enter..."
  exit 1
fi

echo "-> Paketleme araci kuruluyor (zaten kuruluysa atlanir)…"
"$PY" -m pip install --no-cache-dir -r paketleme/requirements-paketleme.txt || {
  echo ""
  echo "  [HATA] Paketleme araci kurulamadi. Internet baglantisini kontrol edin."
  read -r -p "  Kapatmak icin Enter..."
  exit 1
}

echo ""
echo "-> Onceki cikti temizleniyor…"
rm -rf "$DEPO/build" "$DEPO/dist"

echo ""
echo "-> Uygulama uretiliyor (ekran arada sessiz kalabilir, bekleyin)…"
"$PY" -m PyInstaller --noconfirm --clean paketleme/NextGenDetector-mac.spec || {
  echo ""
  echo "  [HATA] Uretim tamamlanamadi. Yukaridaki son satirlari kopyalayin."
  read -r -p "  Kapatmak icin Enter..."
  exit 1
}

# build/ klasoru yuzlerce MB'dir ve ise yaramaz: uretim bitince silinir.
# dist/NextGen Detector (klasor) ise .app'in ayni icerikteki ikizidir —
# PyInstaller once onu kurar, sonra .app'in icine kopyalar. Kullaniciya
# iki ayni sey gostermek kafa karistirir, ustelik bir o kadar yer kaplar.
echo ""
echo "-> Gecici klasorler siliniyor…"
rm -rf "$DEPO/build" "$DEPO/dist/NextGen Detector"

BOYUT="$(du -sh "$DEPO/dist/NextGen Detector.app" 2>/dev/null | cut -f1)"
echo ""
echo "=============================================================="
echo "  TAMAM — 'NextGen Detector.app' hazir  (boyut: ${BOYUT:-bilinmiyor})"
echo "=============================================================="
echo ""
echo "  Simdi acilan Finder penceresindeki uygulamayi Uygulamalar"
echo "  klasorune surukleyip cift tiklayabilirsiniz."
echo ""

open "$DEPO/dist"
read -r -p "  Kapatmak icin Enter..."

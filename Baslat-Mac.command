#!/bin/bash
# DALSAN ISG - Mac baslatici. Bu dosyaya cift tiklayin.
cd "$(dirname "$0")"

# Calistirma izni kaybolmus olabilir (ZIP ile geldiyse ya da Windows/exFAT
# uzerinden kopyalandiysa). Finder o zaman dosyayi hic acmaz; kendi iznimizi
# tazelemek en ucuz cozumdur.
chmod +x "$0" 2>/dev/null

# DIKKAT: /usr/bin/python3 her Mac'te VARDIR ama Command Line Tools kurulu
# degilse yalnizca bir yer tutucudur; calistirilinca "gelistirici araclari
# gerekiyor" penceresi acar. Bu yuzden once gercek Python kurulumlari denenir
# ve /usr/bin/python3 EN SONA birakilir.
#
# Desteklenen surum YALNIZ Python 3.12 (docs/17 R10): daha yeni bir surum
# (3.13, 3.14) de kuruluysa once 3.12 aranir; sinama her adayda yapilir.
adaylar=(
  /opt/homebrew/bin/python3.12
  /usr/local/bin/python3.12
)
# python.org kurulumu
framework=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
[ -x "$framework" ] && adaylar+=("$framework")
adaylar+=(python3.12)
adaylar+=(python3)

for aday in "${adaylar[@]}"; do
  if command -v "$aday" >/dev/null 2>&1 && \
     "$aday" -c 'import sys, tkinter; sys.exit(0 if (3, 12) <= sys.version_info[:2] < (3, 13) else 1)' >/dev/null 2>&1; then
    exec "$aday" masaustu/dalsan_launcher.py
  fi
done

echo ""
echo "  Calisan bir Python 3.12 bulunamadi (tkinter ile birlikte)."
echo "  Daha yeni surumler (3.13, 3.14) henuz desteklenmiyor; 3.12 onlarla"
echo "  yan yana kurulabilir."
echo ""
echo "  Cozum: https://www.python.org/downloads/ adresinden Python 3.12 kurun."
echo "  Homebrew kullaniyorsaniz: brew install python@3.12 python-tk@3.12"
echo ""
echo "  Kurduktan sonra bu dosyaya tekrar cift tiklayin."
echo ""
read -p "  Kapatmak icin Enter..."

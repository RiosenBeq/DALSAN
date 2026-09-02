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
adaylar=(
  /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11
  /usr/local/bin/python3.12 /usr/local/bin/python3.11
)
# python.org kurulumlari
for framework in /Library/Frameworks/Python.framework/Versions/3.1[123]/bin/python3; do
  [ -x "$framework" ] && adaylar+=("$framework")
done
adaylar+=(python3)

for aday in "${adaylar[@]}"; do
  if command -v "$aday" >/dev/null 2>&1 && \
     "$aday" -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
    exec "$aday" masaustu/dalsan_launcher.py
  fi
done

echo ""
echo "  Calisan bir Python 3.11+ bulunamadi (tkinter ile birlikte)."
echo ""
echo "  Cozum: https://www.python.org/downloads/ adresinden Python 3.12 kurun."
echo "  Homebrew kullaniyorsaniz: brew install python@3.12 python-tk@3.12"
echo ""
echo "  Kurduktan sonra bu dosyaya tekrar cift tiklayin."
echo ""
read -p "  Kapatmak icin Enter..."

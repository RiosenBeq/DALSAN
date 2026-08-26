#!/bin/bash
# DALSAN ISG - Mac baslatici. Bu dosyaya cift tiklayin.
cd "$(dirname "$0")"

# Kontrol Paneli icin en uygun Python'u sec: 3.10+ ve tkinter iceren ilk aday.
for aday in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3; do
  if command -v "$aday" >/dev/null 2>&1 && \
     "$aday" -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
    exec "$aday" masaustu/dalsan_launcher.py
  fi
done

# Uygun surum yoksa eldeki python3 ile ac (panel durumu kendisi aciklar)
if command -v python3 >/dev/null 2>&1; then
  exec python3 masaustu/dalsan_launcher.py
fi

echo ""
echo "  Python bulunamadi."
echo "  https://www.python.org/downloads/ adresinden Python 3.12 kurun,"
echo "  sonra bu dosyaya tekrar cift tiklayin."
echo ""
read -p "  Kapatmak icin Enter..."

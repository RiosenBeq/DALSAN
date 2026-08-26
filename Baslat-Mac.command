#!/bin/bash
# DALSAN ISG - Mac baslatici. Bu dosyaya cift tiklayin.
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  python3 masaustu/dalsan_launcher.py
else
  echo ""
  echo "  Python bulunamadi."
  echo "  https://www.python.org/downloads/ adresinden Python 3.12 kurun,"
  echo "  sonra bu dosyaya tekrar cift tiklayin."
  echo ""
  read -p "  Kapatmak icin Enter..."
fi

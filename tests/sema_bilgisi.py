"""Şema betiklerinin TEK kaynağı (testler için).

Yeni bir göç eklendiğinde sürüm numarası testlerin içine dağılmış olsaydı,
her göçte birkaç dosyada "001_ilk.sql" aranıp değiştirilirdi ve biri
unutulurdu. Burası backend/sema/ klasörünü okuyup gerçeği söyler.
"""

from __future__ import annotations

from pathlib import Path

SEMA_DIZINI = Path(__file__).resolve().parents[1] / "backend" / "sema"

SEMA_BETIKLERI = sorted(yol.name for yol in SEMA_DIZINI.glob("*.sql"))
SEMA_BETIK_SAYISI = len(SEMA_BETIKLERI)
# veritabani.mevcut_surum() MAX(surum) döndürür — betikler isim sırasıyla
# uygulandığı için bu, sondaki betiğin adıdır.
SON_SEMA_SURUMU = SEMA_BETIKLERI[-1]

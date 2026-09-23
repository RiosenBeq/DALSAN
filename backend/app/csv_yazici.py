"""Dışa aktarılan her CSV'nin tek yazıcısı (docs/17 §10.5 R31).

Web ekranlarının CSV'leri (olaylar, rapor) ve bakımın masaüstüne yazdığı
uyarı kaydı arşivi aynı yazıcıyı kullanır: kaçış tek yerde olmasaydı yeni bir
sütun ya da yeni bir dosya onu unuturdu. Web katmanına bağlı değildir; bakım
(analiz katmanı) da içe aktarabilsin diye burada durur.
"""

from __future__ import annotations

import csv

# CSV formül enjeksiyonu (docs/17 §10.5 R31). Excel ve LibreOffice = + - @ ile
# (ya da sekme / satır başı ile) başlayan hücreyi FORMÜL olarak okur. Kamera
# adı, bölüm, bölge adı ve inceleme notu kullanıcıdan gelir: adı
# `=HYPERLINK(...)` olan bir kamera, raporu açan kişinin bilgisayarında
# tıklanabilir bir bağlantıya ya da dış veri isteğine dönüşürdü. Böyle başlayan
# METİN hücresinin başına tek tırnak eklenir; sayı hücreleri (negatif sayı
# dahil) değişmez.
_FORMUL_BASLARI = ("=", "+", "-", "@", "\t", "\r")
# Tek başına "-" boş değer işaretidir (ekranda ve raporda "değer yok"). Ardında
# formül olmadığı için çalışacak bir şey taşımaz; kaçışlansaydı raporda "'-"
# görünürdü.
BOS_DEGER = "-"


def csv_hucresi(deger):
    if isinstance(deger, str) and deger != BOS_DEGER and deger.startswith(_FORMUL_BASLARI):
        return "'" + deger
    return deger


class CsvYazici:
    """Noktalı virgüllü CSV (Türkçe Excel bunu bekler); her hücre
    `csv_hucresi`'nden geçer. Dışa aktarılan her CSV bunu kullanır: kaçış tek
    yerde olmasaydı yeni bir sütun ya da yeni bir dosya onu unuturdu."""

    def __init__(self, tampon) -> None:
        self._yazici = csv.writer(tampon, delimiter=";")

    def writerow(self, satir) -> None:
        self._yazici.writerow([csv_hucresi(hucre) for hucre in satir])

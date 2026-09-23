"""CSV formül enjeksiyonu (docs/17 §10.5 R31; Faz 5d).

Excel ve LibreOffice = + - @ ile (ya da sekme / satır başı ile) başlayan
hücreyi FORMÜL olarak çalıştırır. Kamera adı, bölüm, bölge adı ve inceleme
notu kullanıcıdan gelir; dışa aktarılan dosyayı açan kişinin bilgisayarında
formüle dönüşmemeli. Sayı hücreleri (negatif sayı dahil) değişmez.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import veritabani, zaman
from app.csv_yazici import csv_hucresi

UYGULAMA = Path(__file__).resolve().parents[1] / "backend" / "app"


@pytest.mark.parametrize(
    ("deger", "beklenen"),
    [
        ('=HYPERLINK("http://x")', '\'=HYPERLINK("http://x")'),
        ("+90 555", "'+90 555"),
        ("-2+3", "'-2+3"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\t=1", "'\t=1"),
        ("\r=1", "'\r=1"),
        ("Rampa", "Rampa"),
        ("-", "-"),  # tek başına tire boş değer işaretidir, formül taşımaz
        ("--1", "'--1"),
        ("- 1", "'- 1"),
        ("%50", "%50"),
        ("", ""),
        (-3, -3),  # sayı hücresi dokunulmaz
        (0, 0),
        (None, None),
    ],
)
def test_hucre_kacisi(deger, beklenen):
    assert csv_hucresi(deger) == beklenen


def test_uygulamada_kacissiz_csv_yazici_yok():
    """Kaçış tek yerde (csv_yazici.CsvYazici): yeni bir dışa aktarma onu
    atlamasın. Web ekranları da bakımın uyarı kaydı arşivi de oradan yazar."""
    # KKD veri setinin etiket dosyası (egitim/veri_seti.py) eğitim betiğinin
    # okuduğu virgüllü CSV'dir ve zip içinde sha256 ile kilitlidir; hücrelerinin
    # hepsi sistemin ürettiği değerlerdir (kimlik, tarih, sabit etiket, sayı),
    # kullanıcı metni taşımaz. Biçimi Excel'e göre değiştirilemez.
    istisnalar = {"csv_yazici.py", "veri_seti.py"}
    for dosya in UYGULAMA.rglob("*.py"):
        if dosya.name in istisnalar:
            continue
        assert "csv.writer(" not in dosya.read_text(encoding="utf-8"), dosya.name


def test_web_katmani_ayni_kacisi_kullanir():
    from app.web import ortak

    assert ortak.csv_hucresi is csv_hucresi


def _kamera(baglanti, ad: str, alan: str = "Sevkiyat") -> int:
    an = "2026-07-01T00:00:00+00:00"
    imlec = baglanti.execute(
        "INSERT INTO cameras (name, area, source_type, source_url, created_at, updated_at) "
        "VALUES (?, ?, 'file', 'v.mp4', ?, ?)",
        (ad, alan, an, an),
    )
    baglanti.commit()
    return int(imlec.lastrowid)


def _olay(baglanti, kamera_id: int, an: str, not_metni: str = "") -> None:
    baglanti.execute(
        "INSERT INTO events (occurred_at, event_type, camera_id, rule_snapshot, details, "
        "status, note) VALUES (?, 'violation', ?, ?, '{}', 'false_alarm', ?)",
        (an, kamera_id, json.dumps({"rule_type": "zone_intrusion"}), not_metni),
    )
    baglanti.commit()


def _hucreler(metin: str) -> list[str]:
    return [h for satir in metin.lstrip("﻿").splitlines() for h in satir.split(";")]


def test_olay_listesi_csvsinde_kullanici_metni_kacisli(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera = _kamera(baglanti, "=HYPERLINK(1)", alan="@bolum")
        _olay(baglanti, kamera, zaman.simdi_utc(), not_metni="+çağır")
    finally:
        baglanti.close()

    hucreler = _hucreler(istemci.get("/olaylar/disa-aktar.csv").text)
    assert "'=HYPERLINK(1)" in hucreler
    assert "'@bolum" in hucreler
    assert "'+çağır" in hucreler
    assert not any(h.startswith(("=", "+", "@")) for h in hucreler)


def test_rapor_csvsinde_kamera_adi_kacisli(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera = _kamera(baglanti, "-1+1")
        _olay(baglanti, kamera, "2026-08-10T09:00:00+00:00")
        baglanti.execute(
            "INSERT INTO analysis_hours (camera_id, hour_utc, analyzed_s) VALUES (?, ?, 3600)",
            (kamera, "2026-08-10T09"),
        )
        baglanti.commit()
    finally:
        baglanti.close()

    metin = istemci.get("/komuta/rapor/ozet.csv?baslangic=2026-08-01&bitis=2026-08-31").text
    hucreler = _hucreler(metin)
    # Kamera kırılımında ve analiz saatleri tablosunda
    assert hucreler.count("'-1+1") == 2
    assert "-1+1" not in hucreler

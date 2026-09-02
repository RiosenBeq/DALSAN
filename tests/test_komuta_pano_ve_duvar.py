"""Komuta panosu (/komuta) ve canlı duvar (/komuta/duvar).

İki soruyu birden korur:
  1. VERİ VARKEN ekran gerçek veritabanı sayılarını gösteriyor mu?
  2. VERİ YOKKEN sıfır dolu bir pano yerine öğretici bir boş durum çıkıyor mu?

Tasarımın örnek sayıları (24 kamera, 6 bölüm, 34 ihlal, 192.168.1.41) ekrana
sızarsa buradaki nöbetçi test bunu yakalar.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from app import veritabani, zaman
from app.web.komuta import duvar_sutun_sayisi

# ------------------------------------------------------------------ yardımcılar


def _kamera_ekle(istemci, ad: str, alan: str = "") -> int:
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": ad,
            "area": alan,
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.5:554/1",
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    return int(yanit.headers["location"].rsplit("/", 1)[1])


def _bugun_saat(saat: int) -> str:
    """Bugünün Türkiye saatiyle `saat`:30'unun UTC karşılığı (ISO metni)."""
    gun_basi = datetime.fromisoformat(zaman.gun_basi_utc(0))
    return (gun_basi + timedelta(hours=saat, minutes=30)).isoformat(timespec="seconds")


def _olay_ekle(
    test_ayarlari,
    kamera_id: int,
    occurred_at: str,
    *,
    tip: str = "violation",
    durum: str = "new",
    kural_tipi: str = "safe_distance",
    detaylar: dict | None = None,
) -> int:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        imlec = baglanti.execute(
            "INSERT INTO events (occurred_at, event_type, camera_id, rule_snapshot, "
            "details, status) VALUES (?, ?, ?, ?, ?, ?)",
            (
                occurred_at,
                tip,
                kamera_id,
                json.dumps({"rule_type": kural_tipi}),
                json.dumps(detaylar or {}),
                durum,
            ),
        )
        baglanti.commit()
        return int(imlec.lastrowid)
    finally:
        baglanti.close()


def _kural_ekle(test_ayarlari, kamera_id: int, *, acik: bool = True) -> None:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        baglanti.execute(
            "INSERT INTO rules (camera_id, rule_type, target_classes, params, enabled, "
            "updated_at) VALUES (?, 'safe_distance', '[\"person\"]', '{}', ?, ?)",
            (kamera_id, 1 if acik else 0, zaman.simdi_utc()),
        )
        baglanti.commit()
    finally:
        baglanti.close()


def _dolu_kurulum(istemci, test_ayarlari) -> dict:
    """İki bölümde üç kamera, bugün ve dün olaylar, bir açık kural."""
    sevkiyat = _kamera_ekle(istemci, "Sevkiyat Rampası", "Sevkiyat")
    depo = _kamera_ekle(istemci, "Depo Koridoru", "Depo")
    pasif = _kamera_ekle(istemci, "Boyahane 3", "Boyahane")

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        baglanti.execute("UPDATE cameras SET enabled = 0 WHERE id = ?", (pasif,))
        baglanti.execute("UPDATE cameras SET status = 'online' WHERE id = ?", (sevkiyat,))
        baglanti.commit()
    finally:
        baglanti.close()

    # Sevkiyat: bugün 3 ihlal (ikisi 09:30, biri 14:30) — en yoğun alan
    _olay_ekle(test_ayarlari, sevkiyat, _bugun_saat(9))
    _olay_ekle(test_ayarlari, sevkiyat, _bugun_saat(9))
    _olay_ekle(
        test_ayarlari,
        sevkiyat,
        _bugun_saat(14),
        durum="reviewed",
        kural_tipi="ppe_violation",
        detaylar={"eksik_kkd": ["helmet"]},
    )
    # Depo: bugün 1 ihlal
    _olay_ekle(test_ayarlari, depo, _bugun_saat(11), kural_tipi="zone_intrusion")
    # Dün 1 ihlal — "düne göre" karşılaştırması gerçek veriden çıksın
    dun = datetime.fromisoformat(zaman.gun_basi_utc(1)) + timedelta(hours=10)
    _olay_ekle(test_ayarlari, depo, dun.isoformat(timespec="seconds"))

    _kural_ekle(test_ayarlari, sevkiyat)
    return {"sevkiyat": sevkiyat, "depo": depo, "pasif": pasif}


# --------------------------------------------------------------- boş durumlar


def test_kamerasiz_panoda_ogretici_bos_durum(istemci):
    metin = istemci.get("/komuta").text
    assert "Henüz kamera eklenmedi" in metin
    assert 'href="/kameralar/yeni"' in metin
    # Sıfır dolu sayı kartları gösterilmez
    assert 'class="sayi-karti"' not in metin


def test_kamerasiz_duvarda_ogretici_bos_durum(istemci):
    metin = istemci.get("/komuta/duvar").text
    assert "Duvara koyacak kamera yok" in metin
    assert 'href="/kameralar/yeni"' in metin
    assert 'class="duvar-izgara"' not in metin


def test_olaysiz_panoda_her_bolum_ne_yapilacagini_soyluyor(istemci):
    _kamera_ekle(istemci, "Sevkiyat Rampası", "Sevkiyat")
    metin = istemci.get("/komuta").text
    # Kamera var: sayı kartları çıkar ama grafikler uydurma veriyle dolmaz
    assert 'class="sayi-karti"' in metin
    assert "günde ihlal kaydedilmedi" in metin
    assert "Henüz olay yok" in metin
    assert "Bugün ihlal kaydedilmedi" in metin
    assert 'class="komuta-histogram"' not in metin


# ---------------------------------------------------------------- sayı kartları


_KART = re.compile(r'sayi-etiketi">([^<]+)</span>\s*<span class="sayi-degeri ([^"]*)">(\d+)</span>')


def _kartlar(metin: str) -> dict[str, tuple[str, int]]:
    """Ekrandaki dört özet kutusu: etiket → (renk sınıfı, sayı)."""
    return {ad: (renk.strip(), int(deger)) for ad, renk, deger in _KART.findall(metin)}


def test_sayi_kartlari_gercek_veritabanindan(istemci, test_ayarlari):
    _dolu_kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta").text
    kartlar = _kartlar(metin)
    # bugün 4 ihlal, 4 'new' olay, 3 kameranın 1'i canlı, 1 açık kural
    assert kartlar["Bugünkü ihlal"] == ("", 4)
    assert kartlar["İncelenmeyi bekleyen"] == ("dikkat", 4)
    assert kartlar["Canlı kamera"] == ("dikkat", 1)
    assert kartlar["Aktif kural"] == ("", 1)
    assert "toplam 3 kamera" in metin
    assert "düne göre +3" in metin
    assert 'href="/olaylar?durum=new"' in metin


def test_dun_veri_yoksa_iyilesme_izlenimi_verilmez(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "K1", "Depo")
    _olay_ekle(test_ayarlari, kamera, _bugun_saat(9))
    metin = istemci.get("/komuta").text
    assert "dün ihlal yoktu" in metin
    assert "düne göre" not in metin


# ------------------------------------------------------- alan yoğunluğu (bar)


def test_alan_cubuklari_en_yuksege_oranli(istemci, test_ayarlari):
    _dolu_kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta").text
    assert "Alanlara göre ihlal yoğunluğu" in metin
    # Sevkiyat 3, Depo 2 (biri dün) → en yüksek %100 ve 'yogun'
    assert 'class="yogun" style="width: 100%"' in metin
    assert metin.index("Sevkiyat") < metin.index("Depo Koridoru")


def test_bolumsuz_kamera_bos_etiketle_gosterilmez(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "K1")  # area boş
    _olay_ekle(test_ayarlari, kamera, _bugun_saat(9))
    metin = istemci.get("/komuta").text
    assert "Bölüm girilmemiş" in metin


# ----------------------------------------------------------------- canlı akış


def test_canli_akis_olay_detayina_baglaniyor(istemci, test_ayarlari):
    kimlikler = _dolu_kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta").text
    assert "Canlı akış" in metin
    # Özet metni olay listesindekiyle AYNI kaynaktan gelir
    assert "KKD (baret/yelek) — baret yok" in metin
    assert "Sevkiyat Rampası · Sevkiyat" in metin
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        olay_id = baglanti.execute(
            "SELECT id FROM events WHERE camera_id = ? ORDER BY id DESC LIMIT 1",
            (kimlikler["depo"],),
        ).fetchone()["id"]
    finally:
        baglanti.close()
    assert f'href="/olaylar/{olay_id}"' in metin


def test_akis_satir_rengi_olay_durumundan(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "K1", "Depo")
    _olay_ekle(test_ayarlari, kamera, _bugun_saat(9), durum="new")
    _olay_ekle(test_ayarlari, kamera, _bugun_saat(8), durum="reviewed")
    _olay_ekle(
        test_ayarlari, kamera, _bugun_saat(7), tip="system", detaylar={"mesaj": "Kamera koptu"}
    )
    metin = istemci.get("/komuta").text
    assert 'class="akis-satiri kirmizi"' in metin
    assert 'class="akis-satiri sari"' in metin
    assert 'class="akis-satiri notr"' in metin
    assert "Kamera koptu" in metin


# ------------------------------------------------------------------ histogram


def test_histogram_yerel_saate_gore_kovaliyor(istemci, test_ayarlari):
    _dolu_kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta").text
    assert "İhlallerin saate göre dağılımı" in metin
    assert 'class="komuta-histogram"' in metin
    # 09'da 2, 11'de 1, 14'te 1 → en yoğun 09:00-10:00
    assert "En yoğun 09:00 – 10:00 · 2 ihlal" in metin
    assert 'class="histogram-cubuk yogun" style="height: 100%"' in metin
    # 24 sütun: gece saatleri de boş sütun olarak görünür
    assert metin.count('class="histogram-sutun"') == 24


# ------------------------------------------------------- öne çıkan kameralar


def test_one_cikan_kameralar_olay_sayisina_gore(istemci, test_ayarlari):
    kimlikler = _dolu_kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta").text
    assert "Öne çıkan kameralar" in metin
    assert "3 ihlal" in metin
    assert f'data-kamera="{kimlikler["sevkiyat"]}"' in metin
    # Duvarı boğmayan tazeleme aralığı canlı kareye geçmiş olmalı
    assert 'data-aralik="2000"' in metin
    assert metin.index("Sevkiyat Rampası") < metin.index("Depo Koridoru")


# ----------------------------------------------------------------- canlı duvar


def test_duvar_sutun_sayisi_kamera_sayisina_uyar():
    """Tasarımdaki 6 sütun 24 kamera içindi; 3-4 kamerada kutular pul olurdu."""
    assert duvar_sutun_sayisi(0) == 1
    assert duvar_sutun_sayisi(1) == 1
    assert duvar_sutun_sayisi(4) == 2
    assert duvar_sutun_sayisi(9) == 3
    assert duvar_sutun_sayisi(24) == 5
    assert duvar_sutun_sayisi(100) == 6  # üst sınır


def test_duvarda_her_kamera_bir_kez_ve_bos_kutu_yok(istemci, test_ayarlari):
    _dolu_kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta/duvar").text
    assert metin.count('class="duvar-kutu') == 3
    assert "--duvar-sutun: 2" in metin
    assert "Canlı duvar · 3 kamera" in metin
    for ad in ("Sevkiyat Rampası", "Depo Koridoru", "Boyahane 3"):
        assert ad in metin


def test_duvarda_acik_ihlal_kirmizi_cerceve(istemci, test_ayarlari):
    kimlikler = _dolu_kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta/duvar").text
    assert "ihlalli" in metin
    assert "açık ihlal" in metin
    # Kutuya tıklayınca kameranın sayfası açılır
    assert f'href="/kameralar/{kimlikler["sevkiyat"]}"' in metin


def test_duvarda_pasif_kameradan_kare_istenmez(istemci, test_ayarlari):
    kimlikler = _dolu_kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta/duvar").text
    assert "pasif" in metin
    assert f'data-kamera="{kimlikler["pasif"]}"' not in metin
    # Bağlı kameradan istenir
    assert f'data-kamera="{kimlikler["sevkiyat"]}"' in metin


def test_duvarda_durum_metinleri_turkce(istemci, test_ayarlari):
    _dolu_kurulum(istemci, test_ayarlari)
    metin = istemci.get("/komuta/duvar").text
    assert "canlı kare" in metin  # online kamera
    assert "bağlantı yok" in metin  # offline kamera


# ------------------------------------------------- tasarımdan sahte veri sızmadı


def test_tasarimin_ornek_verileri_ekranda_yok(istemci, test_ayarlari):
    _dolu_kurulum(istemci, test_ayarlari)
    for yol in ("/komuta", "/komuta/duvar"):
        metin = istemci.get(yol).text
        for sahte in (
            "24 kamera",
            "6 bölüm",
            "34 ihlal",
            "192.168.1.4",
            "%94",
            "1 842",
            "Vardiya 1",
            "Kaynak Hattı",
        ):
            assert sahte not in metin, f"{yol} → tasarımdan sahte veri: {sahte}"

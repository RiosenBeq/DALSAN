"""Olay inceleme (/komuta/inceleme) ve kamera sağlığı (/komuta/saglik).

Üç soruyu birden korur:
  1. VERİ VARKEN ekranlar gerçek veritabanı kayıtlarını mı gösteriyor?
  2. VERİ YOKKEN uydurma sayı yerine öğretici bir boş durum mu çıkıyor?
  3. İnceleme düğmeleri GERÇEKTEN veritabanına yazıyor mu?

Tasarımın örnek satırları (Olay #418, 192.168.1.41, "Sevkiyat Rampası ·
5,8 fps") ekrana sızarsa buradaki nöbetçi testler yakalar.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

from app import veritabani, zaman

# ------------------------------------------------------------------ yardımcılar


def _kamera_ekle(istemci, ad: str, alan: str = "", fps: float = 6) -> int:
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": ad,
            "area": alan,
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.5:554/1",
            "sample_fps": str(fps),
        },
        follow_redirects=False,
    )
    return int(yanit.headers["location"].rsplit("/", 1)[1])


def _sql(test_ayarlari, betik: str, degerler: tuple = ()):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        imlec = baglanti.execute(betik, degerler)
        baglanti.commit()
        return imlec.lastrowid
    finally:
        baglanti.close()


def _satir(test_ayarlari, betik: str, degerler: tuple = ()):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return baglanti.execute(betik, degerler).fetchone()
    finally:
        baglanti.close()


_KART = re.compile(r'sayi-etiketi">([^<]+)</span>\s*<span class="sayi-degeri[^"]*">(\d+)</span>')


def _kartlar(metin: str) -> dict[str, int]:
    """Ekrandaki üç özet kutusu: etiket → sayı."""
    return {ad: int(deger) for ad, deger in _KART.findall(metin)}


def _once(saniye: float) -> str:
    """`saniye` saniye önceki an, ISO-8601 UTC metni."""
    return (datetime.now(UTC) - timedelta(seconds=saniye)).isoformat(timespec="seconds")


def _ihlal_ekle(
    test_ayarlari,
    kamera_id: int,
    *,
    dakika_once: float = 1,
    durum: str = "new",
    kural_tipi: str = "safe_distance",
    params: dict | None = None,
    detaylar: dict | None = None,
    foto: str | None = None,
) -> int:
    return _sql(
        test_ayarlari,
        "INSERT INTO events (occurred_at, event_type, camera_id, rule_snapshot, "
        "details, snapshot_path, status) VALUES (?, 'violation', ?, ?, ?, ?, ?)",
        (
            _once(dakika_once * 60),
            kamera_id,
            json.dumps({"rule_type": kural_tipi, "params": params or {}}),
            json.dumps(detaylar or {}),
            foto,
            durum,
        ),
    )


def _kalibre_et(test_ayarlari, kamera_id: int, tarih: str) -> None:
    _sql(
        test_ayarlari,
        "INSERT INTO camera_calibrations (camera_id, image_points, world_points, "
        "homography, calibrated_at) VALUES (?, '[]', '[]', '[]', ?)",
        (kamera_id, tarih),
    )


def _kamera_durumu(test_ayarlari, kamera_id: int, **alanlar) -> None:
    atama = ", ".join(f"{ad} = ?" for ad in alanlar)
    _sql(
        test_ayarlari,
        f"UPDATE cameras SET {atama} WHERE id = ?",
        (*alanlar.values(), kamera_id),
    )


# =====================================================================
# OLAY İNCELEME
# =====================================================================


def test_olaysiz_kuyrukta_ogretici_bos_durum(istemci):
    metin = istemci.get("/komuta/inceleme").text
    assert "Kuyrukta olay yok" in metin
    assert 'href="/kameralar"' in metin
    assert 'class="akis-satiri' not in metin


def test_sistem_olayi_inceleme_kuyruguna_dusmez(istemci, test_ayarlari):
    """Kuyruk 'ihlalleri işaretleme' kuyruğudur; kamera koptu bilgisi
    işaretlenecek bir şey değildir."""
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    _sql(
        test_ayarlari,
        "INSERT INTO events (occurred_at, event_type, camera_id, details, status) "
        "VALUES (?, 'system', ?, ?, 'new')",
        (zaman.simdi_utc(), kamera, json.dumps({"mesaj": "Kamera çevrimdışı: Rampa A"})),
    )
    metin = istemci.get("/komuta/inceleme").text
    assert "Kuyrukta olay yok" in metin
    assert "Kamera çevrimdışı" not in metin


def test_kuyruk_gercek_veriden_ve_rozetler(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    _ihlal_ekle(test_ayarlari, kamera, dakika_once=5, detaylar={"mesafe_m": 1.4})
    _ihlal_ekle(test_ayarlari, kamera, dakika_once=9, durum="reviewed")
    _ihlal_ekle(test_ayarlari, kamera, dakika_once=12, durum="false_alarm")

    metin = istemci.get("/komuta/inceleme").text
    assert "1 bekleyen" in metin
    for rozet in ("yeni", "incelendi", "yanlış alarm"):
        assert rozet in metin
    assert "Rampa A · Sevkiyat" in metin
    # Özet cümlesi olay listesindekiyle aynı kaynaktan gelir
    assert "Güvenli mesafe — 1,4 m" in metin


def test_bekleyen_olaylar_kuyrugun_basinda(istemci, test_ayarlari):
    """İşaretlenmemiş olay, daha yeni bir 'incelendi' olayının altında
    kalmamalı: kuyruk penceresi dolduğunda gözden kaçardı."""
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    _ihlal_ekle(test_ayarlari, kamera, dakika_once=60, kural_tipi="ppe_violation")
    _ihlal_ekle(test_ayarlari, kamera, dakika_once=1, durum="reviewed")

    metin = istemci.get("/komuta/inceleme").text
    assert metin.index("KKD (baret/yelek)") < metin.index("Güvenli mesafe")


def test_secili_olay_baglantiyla_degisir(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    yeni = _ihlal_ekle(test_ayarlari, kamera, dakika_once=1)
    eski = _ihlal_ekle(test_ayarlari, kamera, dakika_once=30, kural_tipi="zone_intrusion")

    varsayilan = istemci.get("/komuta/inceleme").text
    assert f"Olay #{yeni}" in varsayilan  # kuyruğun başı

    secilmis = istemci.get(f"/komuta/inceleme?olay={eski}").text
    assert f"Olay #{eski}" in secilmis
    assert 'aria-current="true"' in secilmis


def test_kanit_fotografi_ve_eksikligi(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    (test_ayarlari.goruntu_klasoru / "2026").mkdir(parents=True, exist_ok=True)
    (test_ayarlari.goruntu_klasoru / "2026" / "kanit.jpg").write_bytes(b"jpeg")
    fotolu = _ihlal_ekle(test_ayarlari, kamera, dakika_once=1, foto="2026/kanit.jpg")
    fotosuz = _ihlal_ekle(test_ayarlari, kamera, dakika_once=2)

    metin = istemci.get(f"/komuta/inceleme?olay={fotolu}").text
    assert 'src="/goruntuler/2026/kanit.jpg"' in metin
    assert istemci.get("/goruntuler/2026/kanit.jpg").status_code == 200

    metin = istemci.get(f"/komuta/inceleme?olay={fotosuz}").text
    assert "kanıt fotoğrafı kaydedilememiş" in metin


def test_mesafe_olayinda_olculen_deger_ve_kural_esigi(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    olay = _ihlal_ekle(
        test_ayarlari,
        kamera,
        params={"distance_m": 3.0},
        detaylar={"mesafe_m": 1.85, "arac_sinifi": "forklift", "arac_hiz_mps": 1.4},
    )
    metin = istemci.get(f"/komuta/inceleme?olay={olay}").text
    assert "Ölçülen mesafe" in metin and "1,85 m" in metin
    assert "Kural eşiği" in metin and "3 m" in metin
    assert "Forklift" in metin
    assert "1,4 m/s" in metin


def test_kkd_olayinda_uc_durumlu_karar_gosterilir(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Pres 1", "Presleme")
    olay = _ihlal_ekle(
        test_ayarlari,
        kamera,
        kural_tipi="ppe_violation",
        params={"window_size": 15, "min_valid_observations": 8},
        detaylar={
            "eksik_kkd": ["helmet"],
            "ppe": {
                "required": ["helmet", "vest"],
                "helmet": {"decision": "no"},
                "vest": {"decision": "unknown"},
                "dwell_s": 4.2,
            },
        },
    )
    metin = istemci.get(f"/komuta/inceleme?olay={olay}").text
    assert "baret yok · yelek belirsiz" in metin
    assert "8 / 15 gözlem" in metin
    assert "4,2 sn" in metin


def test_kaynagi_olmayan_kutu_hic_cizilmez(istemci, test_ayarlari):
    """Ölçüm kaydı yoksa '—' yazan boş kutu gösterilmez: ölçüm yapılmış ama
    sonuç çıkmamış izlenimi vermemeli."""
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    olay = _ihlal_ekle(test_ayarlari, kamera, params={}, detaylar={"mesafe_m": 2.0})
    metin = istemci.get(f"/komuta/inceleme?olay={olay}").text
    assert "Ölçülen mesafe" in metin
    assert "Kural eşiği" not in metin
    assert "Araç hızı" not in metin


# ---------------------------------------------- düğmeler gerçekten yazıyor mu


@pytest.mark.parametrize("durum", ["reviewed", "false_alarm"])
def test_isaretleme_veritabanina_yazar_ve_ekranda_kalir(istemci, test_ayarlari, durum):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    olay = _ihlal_ekle(test_ayarlari, kamera)

    yanit = istemci.post(
        f"/olaylar/{olay}/durum",
        data={"durum": durum, "not_metni": "  kontrol edildi  ", "donus": "inceleme"},
        follow_redirects=False,
    )
    assert yanit.headers["location"] == f"/komuta/inceleme?olay={olay}"

    satir = _satir(test_ayarlari, "SELECT * FROM events WHERE id = ?", (olay,))
    assert satir["status"] == durum
    assert satir["note"] == "kontrol edildi"
    assert satir["reviewed_at"] is not None

    metin = istemci.get(f"/komuta/inceleme?olay={olay}").text
    assert ("İhlal · İncelendi" if durum == "reviewed" else "İhlal · Yanlış alarm") in metin
    assert "kontrol edildi" in metin


def test_not_kaydetmek_durumu_degistirmez(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    olay = _ihlal_ekle(test_ayarlari, kamera)
    istemci.post(
        f"/olaylar/{olay}/durum",
        data={"durum": "new", "not_metni": "vardiya şefine soruldu", "donus": "inceleme"},
        follow_redirects=False,
    )
    satir = _satir(test_ayarlari, "SELECT * FROM events WHERE id = ?", (olay,))
    assert satir["status"] == "new"
    assert satir["note"] == "vardiya şefine soruldu"
    assert satir["reviewed_at"] is None


def test_olay_detay_sayfasi_hala_kendi_sayfasina_doner(istemci, test_ayarlari):
    """İnceleme ekranı için eklenen dönüş alanı eski akışı bozmamalı."""
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    olay = _ihlal_ekle(test_ayarlari, kamera)
    yanit = istemci.post(
        f"/olaylar/{olay}/durum", data={"durum": "reviewed"}, follow_redirects=False
    )
    assert yanit.headers["location"] == f"/olaylar/{olay}"


def test_bilinmeyen_donus_ekrani_reddedilir(istemci, test_ayarlari):
    """Dışarıdan verilen adrese yönlendirme (açık yönlendirme) mümkün olmasın."""
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    olay = _ihlal_ekle(test_ayarlari, kamera)
    yanit = istemci.post(
        f"/olaylar/{olay}/durum",
        data={"durum": "reviewed", "donus": "https://baska-site.example/"},
        follow_redirects=False,
    )
    assert yanit.status_code >= 400


# ------------------------------------------------------- yönlendirme ve ipuçları


def test_yanlis_alarmin_neden_onemli_oldugu_ekranda(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    _ihlal_ekle(test_ayarlari, kamera)
    metin = istemci.get("/komuta/inceleme").text
    assert "Yanlış alarm" in metin
    assert "kaçırılan ihlalden daha ağır bir kusurdur" in metin


def test_klavye_kisayolu_ekranda_gorunur_ve_hedefi_var(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    birinci = _ihlal_ekle(test_ayarlari, kamera, dakika_once=1)
    ikinci = _ihlal_ekle(test_ayarlari, kamera, dakika_once=5)

    metin = istemci.get(f"/komuta/inceleme?olay={birinci}").text
    assert "önceki olay" in metin and "sonraki olay" in metin
    assert f'data-sonraki="{ikinci}"' in metin
    assert 'data-onceki=""' in metin
    assert "/static/inceleme.js" in metin

    metin = istemci.get(f"/komuta/inceleme?olay={ikinci}").text
    assert f'data-onceki="{birinci}"' in metin


def test_incelemede_tasarimin_ornek_verisi_yok(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    _ihlal_ekle(test_ayarlari, kamera, detaylar={"mesafe_m": 1.4})
    metin = istemci.get("/komuta/inceleme").text
    for sahte in ("Olay #418", "Presleme Hattı 2", "2,1 m", "7 / 5"):
        assert sahte not in metin


# =====================================================================
# KAMERA SAĞLIĞI
# =====================================================================


def test_kamerasiz_saglikta_ogretici_bos_durum(istemci):
    metin = istemci.get("/komuta/saglik").text
    assert "Henüz kamera eklenmedi" in metin
    assert 'href="/kameralar/yeni"' in metin
    assert 'class="komuta-tablo saglik-tablo"' not in metin


def test_uc_ozet_kutusu_gercek_sayilar(istemci, test_ayarlari):
    bagli = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    kopuk = _kamera_ekle(istemci, "Hat B", "Presleme")
    kapali = _kamera_ekle(istemci, "Boya C", "Boyahane")
    _kamera_durumu(test_ayarlari, bagli, status="online")
    _kamera_durumu(test_ayarlari, kopuk, status="offline")
    _kamera_durumu(test_ayarlari, kapali, enabled=0)

    metin = istemci.get("/komuta/saglik").text
    assert _kartlar(metin) == {"Bağlı": 1, "Sorunlu": 1, "Pasif": 1}


def test_rozet_onceligi_kapali_baglanti_kalibrasyon(istemci, test_ayarlari):
    kapali = _kamera_ekle(istemci, "Boya C")
    kopuk = _kamera_ekle(istemci, "Hat B")
    baglaniyor = _kamera_ekle(istemci, "Rampa A")
    kalibrasyonsuz = _kamera_ekle(istemci, "Depo D")
    tam = _kamera_ekle(istemci, "Montaj E")

    _kamera_durumu(test_ayarlari, kapali, enabled=0, status="online")
    _kamera_durumu(test_ayarlari, kopuk, status="offline")
    _kamera_durumu(test_ayarlari, baglaniyor, status="connecting")
    _kamera_durumu(test_ayarlari, kalibrasyonsuz, status="online")
    _kamera_durumu(test_ayarlari, tam, status="online")
    # Kapalı kameranın kalibrasyonu var ama rozeti yine 'pasif' olmalı
    _kalibre_et(test_ayarlari, kapali, zaman.simdi_utc())
    _kalibre_et(test_ayarlari, tam, "2026-08-28T09:00:00+00:00")

    metin = istemci.get("/komuta/saglik").text
    for rozet in (
        "pasif",
        "bağlantı yok",
        "yeniden bağlanıyor",
        "kalibrasyon bekliyor",
        "bağlı",
    ):
        assert f'class="rozet {"gri" if rozet == "pasif" else ""}' in metin or rozet in metin
        assert rozet in metin
    assert "28.08.2026" in metin


def test_son_kare_insan_diliyle(istemci, test_ayarlari):
    yeni = _kamera_ekle(istemci, "Rampa A")
    eski = _kamera_ekle(istemci, "Hat B")
    hic = _kamera_ekle(istemci, "Boya C")
    _kamera_durumu(test_ayarlari, yeni, status="online", last_frame_at=_once(3))
    _kamera_durumu(test_ayarlari, eski, status="offline", last_frame_at=_once(200))
    _kamera_durumu(test_ayarlari, hic, status="offline")

    metin = istemci.get("/komuta/saglik").text
    # Saniye satırında TAM sayı aranmaz: sayfa isteği bir saniye sürerse "3 sn"
    # "4 sn" olur ve test sebepsiz kırılırdı. Burada korunan şey BİÇİM — tam
    # sayının doğruluğunu aşağıdaki birim testi sabit saatle çiviliyor.
    assert re.search(r"\b[1-9]\d? sn önce\b", metin), "Saniye biçimi görünmüyor"
    # 200 saniye -> "3 dk önce"; bu eşik 40 saniye pay bırakır, kararlıdır.
    assert "3 dk önce" in metin
    # Hiç kare gelmemiş kameraya uydurma bir süre yazılmaz
    assert metin.count("—") >= 1


def test_kalibrasyonsuz_kameraya_kalibre_et_baglantisi(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A")
    _kamera_durumu(test_ayarlari, kamera, status="online")
    metin = istemci.get("/komuta/saglik").text
    assert f'href="/kameralar/{kamera}#kalibrasyon-formu"' in metin
    assert "güvenli mesafe kuralı bilerek" in metin


def test_dusuk_fps_gorsel_uyari_ve_aciklama(istemci, test_ayarlari):
    yavas = _kamera_ekle(istemci, "Rampa A", fps=6)
    normal = _kamera_ekle(istemci, "Hat B", fps=6)
    # .env eşiği %60: 6 fps'e ayarlı kamerada 2,0 düşük, 5,4 normaldir
    _kamera_durumu(test_ayarlari, yavas, status="online", measured_fps=2.0)
    _kamera_durumu(test_ayarlari, normal, status="online", measured_fps=5.4)

    metin = istemci.get("/komuta/saglik").text
    assert metin.count("fps-dusuk") == 1
    assert "2,0" in metin and "5,4" in metin
    assert "%60 sınırının altına" in metin
    assert "kamera ya da ağ" in metin


def test_dusuk_fps_esigi_ayardan_gelir(istemci, test_ayarlari, monkeypatch):
    """Eşik koda gömülü olsaydı bu test onu yakalardı: ayar değişince ekran
    da değişmeli."""
    from dataclasses import replace

    kamera = _kamera_ekle(istemci, "Rampa A", fps=6)
    _kamera_durumu(test_ayarlari, kamera, status="online", measured_fps=4.0)
    assert "fps-dusuk" not in istemci.get("/komuta/saglik").text

    istemci.app.state.ayarlar = replace(test_ayarlari, fps_uyari_orani=0.9)
    metin = istemci.get("/komuta/saglik").text
    assert "fps-dusuk" in metin
    assert "%90 sınırının altına" in metin


def test_olculemeyen_fps_uydurulmaz(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A")
    _kamera_durumu(test_ayarlari, kamera, status="offline", measured_fps=None)
    metin = istemci.get("/komuta/saglik").text
    assert "fps-dusuk" not in metin


def test_saglikta_tasarimin_ornek_verisi_yok(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa A", "Sevkiyat")
    _kamera_durumu(test_ayarlari, kamera, status="online", measured_fps=5.9)
    metin = istemci.get("/komuta/saglik").text
    for sahte in ("192.168.1.4", "5,7", "Boyahane Girişi", "Kaynak Hattı 1", "48 sn"):
        assert sahte not in metin


# =====================================================================
# "ne kadar önce" biçimi (zaman.py)
# =====================================================================


@pytest.mark.parametrize(
    ("saniye", "beklenen"),
    [
        (0, "1 sn önce"),
        (1, "1 sn önce"),
        (48, "48 sn önce"),
        (185, "3 dk önce"),
        (3 * 3600 + 60, "3 saat önce"),
        (2 * 86400, "2 gün önce"),
    ],
)
def test_ne_kadar_once_biçimi(saniye, beklenen):
    # Sabit bir "şimdi" veriliyor: gerçek saatle ölçülseydi makine bir saniye
    # yavaşladığında "48 sn önce" beklentisi "49 sn önce" görüp kırılırdı.
    simdi = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)
    damga = (simdi - timedelta(seconds=saniye)).isoformat(timespec="seconds")
    assert zaman.ne_kadar_once(damga, simdi=simdi) == beklenen


def test_ileri_tarihli_damga_negatif_sure_yazmaz():
    ileri = (datetime.now(UTC) + timedelta(minutes=5)).isoformat(timespec="seconds")
    assert zaman.ne_kadar_once(ileri) == "az önce"

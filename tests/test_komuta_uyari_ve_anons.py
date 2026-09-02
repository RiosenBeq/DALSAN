"""Uyarı zinciri (/komuta/uyari) ve Anons sistemi (/komuta/anons).

Dört soruyu birden korur:
  1. Şema göçü (002) MEVCUT VERİYİ koruyor mu?
  2. Ekranlardaki her satır gerçek veritabanından mı geliyor?
  3. Gölge mod GERÇEKTEN anonsu susturuyor ama olayı yazıyor mu?
  4. Hoparlör bölgeleri ekle/düzenle/sil/dene akışı çalışıyor mu?

Tasarımın örnek satırları ("Ani hareket · forklift hızı", "12 kamera · 3 m",
"192.168.1.41", "6 / 7 çalışıyor") ekrana sızarsa nöbetçi testler yakalar.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta

import pytest

from app import veritabani, zaman
from tests.sema_bilgisi import SEMA_DIZINI

# ------------------------------------------------------------------ yardımcılar


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


def _kural_ekle(
    test_ayarlari,
    kamera_id: int,
    *,
    tip: str = "safe_distance",
    params: dict | None = None,
    anons_id: int | None = None,
    golge: int = 0,
    aktif: int = 1,
    zone_id: int | None = None,
) -> int:
    return _sql(
        test_ayarlari,
        "INSERT INTO rules (camera_id, rule_type, zone_id, target_classes, params, "
        "cooldown_s, announcement_id, enabled, shadow_mode, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            kamera_id,
            tip,
            zone_id,
            json.dumps(["person"]),
            json.dumps(params if params is not None else {"distance_m": 3.0}),
            90,
            anons_id,
            aktif,
            golge,
            zaman.simdi_utc(),
        ),
    )


def _anons_id(test_ayarlari, anahtar: str = "safe_distance") -> int:
    return _satir(test_ayarlari, "SELECT id FROM announcement_messages WHERE key = ?", (anahtar,))[
        "id"
    ]


def _ihlal_ekle(test_ayarlari, kamera_id: int, kural_kaydi: dict, *, saat_once: float = 1) -> int:
    an = (datetime.now(UTC) - timedelta(hours=saat_once)).isoformat(timespec="seconds")
    return _sql(
        test_ayarlari,
        "INSERT INTO events (occurred_at, event_type, camera_id, rule_snapshot, details, status) "
        "VALUES (?, 'violation', ?, ?, '{}', 'new')",
        (an, kamera_id, json.dumps(kural_kaydi)),
    )


def _hoparlor_ekle(
    istemci, ad: str, adres: str = "http://10.0.0.9:8080/anons", alan: str = "", aktif: str = "1"
):
    return istemci.post(
        "/hoparlorler/kaydet",
        data={"name": ad, "area": alan, "address": adres, "enabled": aktif, "description": ""},
        follow_redirects=False,
    )


# =====================================================================
# ŞEMA GÖÇÜ — 002 mevcut veriyi KORUMALI
# =====================================================================


def test_goc_mevcut_kural_bolge_ve_olaylari_koruyor(tmp_path):
    """En kritik test: 002 uygulanınca kullanıcının kurulumu KAYBOLMAMALI.

    `zones`/`rules` tablosunu "yeniden kur + kopyala" yöntemiyle değiştiren bir
    betik, foreign_keys PRAGMA'sı işlem içinde etkisiz olduğu için bağlı
    kayıtları SESSİZCE silerdi. Bu test tam olarak onu yakalar: önce yalnız
    001 uygulanır, gerçek veri yazılır, sonra 002 gelir.
    """
    sema = tmp_path / "sema"
    sema.mkdir()
    shutil.copy(SEMA_DIZINI / "001_ilk.sql", sema / "001_ilk.sql")

    baglanti = veritabani.baglanti_ac(tmp_path / "goc.db")
    try:
        veritabani.semayi_uygula(baglanti, sema)
        simdi = zaman.simdi_utc()
        baglanti.execute(
            "INSERT INTO cameras (id, name, area, source_type, source_url, created_at, updated_at) "
            "VALUES (1, 'Sevkiyat Rampası', 'Sevkiyat', 'rtsp', 'rtsp://a/1', ?, ?)",
            (simdi, simdi),
        )
        baglanti.execute(
            "INSERT INTO zones (id, camera_id, name, zone_type, polygon, updated_at) "
            "VALUES (7, 1, 'Rampa önü', 'vehicle_area', '[[0,0],[1,0],[1,1]]', ?)",
            (simdi,),
        )
        baglanti.execute(
            "INSERT INTO rules (id, camera_id, rule_type, zone_id, target_classes, params, "
            "cooldown_s, enabled, updated_at) "
            "VALUES (5, 1, 'safe_distance', 7, '[\"person\"]', '{\"distance_m\": 2.5}', 90, 1, ?)",
            (simdi,),
        )
        baglanti.execute(
            "INSERT INTO events (occurred_at, event_type, camera_id, rule_id, status) "
            "VALUES (?, 'violation', 1, 5, 'new')",
            (simdi,),
        )
        baglanti.commit()

        # --- göç ---
        shutil.copy(
            SEMA_DIZINI / "002_hoparlor_bolgeleri_ve_golge_mod.sql",
            sema / "002_hoparlor_bolgeleri_ve_golge_mod.sql",
        )
        veritabani.semayi_uygula(baglanti, sema)

        # --- her şey AYNEN duruyor mu? ---
        assert baglanti.execute("SELECT COUNT(*) FROM cameras").fetchone()[0] == 1
        assert baglanti.execute("SELECT COUNT(*) FROM zones").fetchone()[0] == 1
        assert baglanti.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        kural = baglanti.execute("SELECT * FROM rules WHERE id = 5").fetchone()
        assert kural is not None, "GÖÇ KURALLARI SİLDİ"
        assert kural["zone_id"] == 7
        assert json.loads(kural["params"])["distance_m"] == 2.5
        # Yeni kolon eskiden kurulmuş kuralın davranışını DEĞİŞTİRMEZ
        assert kural["shadow_mode"] == 0
        # Yeni tablo geldi ve boş
        assert baglanti.execute("SELECT COUNT(*) FROM speaker_zones").fetchone()[0] == 0
    finally:
        baglanti.close()


def test_hoparlor_tablosu_ve_golge_kolonu_kuruldu(test_ayarlari, istemci):
    kolonlar = {
        satir["name"] for satir in _satir_listesi(test_ayarlari, "PRAGMA table_info(speaker_zones)")
    }
    assert {"name", "area", "address", "description", "enabled", "last_announced_at"} <= kolonlar
    kural_kolonlari = {
        satir["name"] for satir in _satir_listesi(test_ayarlari, "PRAGMA table_info(rules)")
    }
    assert "shadow_mode" in kural_kolonlari


def _satir_listesi(test_ayarlari, betik: str):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return baglanti.execute(betik).fetchall()
    finally:
        baglanti.close()


def test_ana_sayfada_sema_surumu_gorunuyor(istemci):
    """Kullanıcı hangi sürümde olduğunu tek bakışta görebilmeli."""
    from tests.sema_bilgisi import SON_SEMA_SURUMU

    assert SON_SEMA_SURUMU in istemci.get("/").text


# =====================================================================
# UYARI ZİNCİRİ
# =====================================================================


def test_kural_yokken_ogretici_bos_durum(istemci):
    metin = istemci.get("/komuta/uyari").text
    assert "Henüz kural kurulmadı" in metin
    assert 'href="/kurallar"' in metin


def test_zincir_satiri_gercek_kuraldan_geliyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kural_ekle(test_ayarlari, kamera, params={"distance_m": 4.5})

    metin = istemci.get("/komuta/uyari").text
    assert "Güvenli mesafe" in metin
    # Eşik kuralın kendi params'ından; tasarımdaki "3 m" DEĞİL
    assert "4,5 m" in metin
    assert "1 kamera" in metin
    assert "Rampa 1" in metin


def test_ayni_esikli_kurallar_tek_satirda_gruplaniyor(istemci, test_ayarlari):
    for ad in ("Rampa 1", "Rampa 2", "Rampa 3", "Rampa 4"):
        kamera = _kamera_ekle(istemci, ad, "Sevkiyat")
        _kural_ekle(test_ayarlari, kamera, params={"distance_m": 3.0})

    metin = istemci.get("/komuta/uyari").text
    assert "4 kamera · 3 m" in metin
    # 4 kamera 3'ten fazla: adlar kapsam satırına yazılmaz (satır okunmaz olurdu)
    assert "Rampa 1, Rampa 2" not in metin
    # Tek satır: dört ayrı "Güvenli mesafe" başlığı olmamalı
    assert metin.count(">Güvenli mesafe<") == 1


def test_farkli_esik_ayri_satir(istemci, test_ayarlari):
    k1 = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    k2 = _kamera_ekle(istemci, "Depo 1", "Depo")
    _kural_ekle(test_ayarlari, k1, params={"distance_m": 3.0})
    _kural_ekle(test_ayarlari, k2, params={"distance_m": 5.0})

    metin = istemci.get("/komuta/uyari").text
    assert "3 m" in metin and "5 m" in metin
    assert metin.count(">Güvenli mesafe<") == 2


def test_bolge_ihlali_esigi_insan_diliyle(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Depo Koridoru", "Depo")
    bolge = _sql(
        test_ayarlari,
        "INSERT INTO zones (camera_id, name, zone_type, polygon, updated_at) "
        "VALUES (?, 'Yaya yolu', 'pedestrian_path', '[[0,0],[1,0],[1,1]]', ?)",
        (kamera, zaman.simdi_utc()),
    )
    _kural_ekle(
        test_ayarlari,
        kamera,
        tip="zone_intrusion",
        zone_id=bolge,
        params={"mode": "outside", "min_dwell_s": 5.0},
    )
    metin = istemci.get("/komuta/uyari").text
    assert "Bölge ihlali · Yaya yolu" in metin
    assert "bölge dışında · 5 sn kalış" in metin


def test_anons_mesaji_ve_yolu_gercek(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kural_ekle(test_ayarlari, kamera, anons_id=_anons_id(test_ayarlari))

    metin = istemci.get("/komuta/uyari").text
    assert "Lütfen iş makinelerinden güvenli mesafede durunuz." in metin
    # test ayarlarında ANONS=null
    assert "anons sistemi kapalı" in metin


def test_anonssuz_kural_sessizce_gecistirilmiyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kural_ekle(test_ayarlari, kamera, anons_id=None)
    metin = istemci.get("/komuta/uyari").text
    assert "anons yok" in metin
    assert "anons mesajı seçilmemiş" in metin


def test_kalibrasyonsuz_mesafe_kurali_ekranda_uyariyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kural_ekle(test_ayarlari, kamera, tip="safe_distance")
    metin = istemci.get("/komuta/uyari").text
    assert "kalibrasyon yok" in metin


def test_bildirim_kanallari_durustce_kurulmadi_diyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kural_ekle(test_ayarlari, kamera)
    metin = istemci.get("/komuta/uyari").text
    assert "kurulmadı" in metin
    assert "07-YOL-HARITASI" in metin
    # Tasarımın sahte tırmandırma adımları AYNEN taşınmadı
    assert "3 dk sonra vardiya şefi" not in metin


# ---- gölge mod ----


def test_golge_moddaki_kural_rozetle_gorunuyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kural_ekle(test_ayarlari, kamera, golge=1)
    metin = istemci.get("/komuta/uyari").text
    assert "gölge mod" in metin
    assert "Anonsu aç" in metin


def test_golge_moda_alma_veritabanina_yaziyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    kural = _kural_ekle(test_ayarlari, kamera)

    yanit = istemci.post(
        "/komuta/uyari/golge",
        data={"golge": "1", "kural_idler": [str(kural)]},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert _satir(test_ayarlari, "SELECT shadow_mode FROM rules WHERE id = ?", (kural,))[0] == 1

    istemci.post(
        "/komuta/uyari/golge",
        data={"golge": "0", "kural_idler": [str(kural)]},
        follow_redirects=False,
    )
    assert _satir(test_ayarlari, "SELECT shadow_mode FROM rules WHERE id = ?", (kural,))[0] == 0


def test_grup_halindeki_kurallar_birlikte_degisiyor(istemci, test_ayarlari):
    kurallar = []
    for ad in ("Rampa 1", "Rampa 2"):
        kamera = _kamera_ekle(istemci, ad, "Sevkiyat")
        kurallar.append(_kural_ekle(test_ayarlari, kamera, params={"distance_m": 3.0}))

    istemci.post(
        "/komuta/uyari/golge",
        data={"golge": "1", "kural_idler": [str(k) for k in kurallar]},
        follow_redirects=False,
    )
    for kural in kurallar:
        assert _satir(test_ayarlari, "SELECT shadow_mode FROM rules WHERE id = ?", (kural,))[0] == 1


def test_gecersiz_golge_degeri_reddediliyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1")
    kural = _kural_ekle(test_ayarlari, kamera)
    yanit = istemci.post(
        "/komuta/uyari/golge", data={"golge": "belki", "kural_idler": [str(kural)]}
    )
    assert yanit.status_code == 400


def test_kural_formunda_golge_mod_kutusu_var(istemci):
    _kamera_ekle(istemci, "Rampa 1")
    metin = istemci.get("/kurallar/yeni").text
    assert 'name="shadow_mode"' in metin
    assert "anons çalmasın" in metin


def test_kural_formundan_golge_mod_kaydediliyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1")
    istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": str(kamera),
            "rule_type": "safe_distance",
            "distance_m": "3",
            "cooldown_s": "90",
            "enabled": "1",
            "shadow_mode": "1",
        },
        follow_redirects=False,
    )
    assert _satir(test_ayarlari, "SELECT shadow_mode FROM rules")[0] == 1


# ---- gölge modun GERÇEK etkisi: olay yazılır, anons çalmaz ----


def test_golge_modda_olay_yazilir_ama_anons_calmaz(test_ayarlari, tmp_path):
    """Gölge modun tanımı budur; ekrandaki rozet değil davranış korunur."""
    from app.analiz.supervizor import AnalizSupervizoru
    from app.rules.tipler import Ihlal

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        simdi = zaman.simdi_utc()
        baglanti.execute(
            "INSERT INTO cameras (id, name, area, source_type, source_url, created_at, updated_at) "
            "VALUES (1, 'Rampa 1', 'Sevkiyat', 'rtsp', 'rtsp://a/1', ?, ?)",
            (simdi, simdi),
        )
        anons = baglanti.execute(
            "SELECT id FROM announcement_messages WHERE key = 'safe_distance'"
        ).fetchone()["id"]
        baglanti.execute(
            "INSERT INTO rules (id, camera_id, rule_type, target_classes, params, cooldown_s, "
            "announcement_id, enabled, shadow_mode, updated_at) "
            "VALUES (1, 1, 'safe_distance', '[\"person\"]', '{}', 90, ?, 1, 1, ?)",
            (anons, simdi),
        )
        baglanti.commit()

        supervizor = AnalizSupervizoru(test_ayarlari)
        cagrilar: list[tuple] = []
        supervizor._anons = _AnonsCasusu(cagrilar)
        supervizor._anons_mesajlari = {anons: {"id": anons, "key": "safe_distance", "enabled": 1}}
        supervizor._kamera_konfig = {1: {"id": 1, "area": "Sevkiyat"}}

        ihlal = Ihlal(kural_id=1, kamera_id=1, takip_idler=[3], bolge_id=None, olculen=2.1)
        supervizor._ihlali_kaydet(baglanti, _HatCasusu(), ihlal, 100.0)

        assert baglanti.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1, "olay yazılmalı"
        assert cagrilar == [], "gölge modda anons ÇALMAMALI"

        # Gölge mod kapatılınca anons çalar — ve kameranın BÖLÜMÜ iletilir
        baglanti.execute("UPDATE rules SET shadow_mode = 0 WHERE id = 1")
        baglanti.commit()
        supervizor._ihlali_kaydet(baglanti, _HatCasusu(), ihlal, 200.0)
        assert len(cagrilar) == 1
        assert cagrilar[0][0] == 1  # kamera id
        assert cagrilar[0][1] == "Sevkiyat"  # anons hangi bölümün hoparlörüne gidecek
    finally:
        baglanti.close()


class _AnonsCasusu:
    """duyur() çağrılarını kaydeder; hiçbir ses çalmaz."""

    def duyur(self, kamera_id, kamera_alani, zaman_s, mesaj):
        self._kayit.append((kamera_id, kamera_alani, mesaj))

    def __init__(self, kayit):
        self._kayit = kayit


class _HatCasusu:
    def son_islenmis_jpeg(self, bolgeler_dahil: bool = True):
        return None


def test_golge_moddaki_olay_ekran_bandini_tetiklemiyor(istemci, test_ayarlari):
    """Canlı akış (SSE) olayı 'gölge' diye işaretler; bandı static/uyari.js
    o işarete bakarak gizler."""
    from app.web.ortak import olay_hazirla

    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _ihlal_ekle(test_ayarlari, kamera, {"rule_type": "safe_distance", "shadow_mode": 1})
    satir = _satir(test_ayarlari, "SELECT e.*, '' AS kamera_adi, '' AS kamera_alani FROM events e")
    assert olay_hazirla(satir)["golge_mod"] is True

    _ihlal_ekle(test_ayarlari, kamera, {"rule_type": "safe_distance", "shadow_mode": 0})
    satirlar = _satir_listesi(
        test_ayarlari,
        "SELECT e.*, '' AS kamera_adi, '' AS kamera_alani FROM events e ORDER BY e.id",
    )
    assert olay_hazirla(satirlar[1])["golge_mod"] is False


# =====================================================================
# ANONS SİSTEMİ
# =====================================================================


def test_anons_kartlari_env_ve_veritabanindan(istemci):
    metin = istemci.get("/komuta/anons").text
    # test ayarlarında ANONS=null, ANONS_BEKLEME_SN=30
    assert "Anons yolu" in metin and "kapalı" in metin
    assert "30 sn" in metin
    assert "Tanımlanmadı" in metin  # hoparlör bölgesi yok
    # Tasarımın örnek değerleri sızmamalı
    assert "6 / 7 çalışıyor" not in metin
    assert "20 sn" not in metin


def test_bes_hazir_mesaj_listeleniyor(istemci):
    metin = istemci.get("/komuta/anons").text
    assert "Lütfen baretinizi takınız." in metin
    assert "Lütfen yaya yolunu kullanınız." in metin
    assert "hiçbir kurala bağlı değil" in metin


def test_mesaja_bagli_kural_ve_bolum_gercek(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kural_ekle(test_ayarlari, kamera, anons_id=_anons_id(test_ayarlari))
    metin = istemci.get("/komuta/anons").text
    assert "Güvenli mesafe · 1 kural" in metin
    assert "Sevkiyat" in metin


def test_bugunku_sayi_gercek_olaylardan_golge_haric(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    anons = _anons_id(test_ayarlari)
    for _ in range(3):
        _ihlal_ekle(test_ayarlari, kamera, {"announcement_id": anons, "shadow_mode": 0})
    # Gölge moddaki kuralın olayı SAYILMAZ: hoparlör hiç çalmadı
    _ihlal_ekle(test_ayarlari, kamera, {"announcement_id": anons, "shadow_mode": 1})
    # Anonsu olmayan kuralın olayı da sayılmaz
    _ihlal_ekle(test_ayarlari, kamera, {"announcement_id": None})

    metin = istemci.get("/komuta/anons").text
    assert "Bugün anons tetikleyen ihlal" in metin
    assert ">3</span>" in metin
    # Sayının ne OLMADIĞI da yazıyor
    assert "hoparlörün kaç kez bağırdığını değil" in metin


def test_anons_histogrami_gercek_saatlerden(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    anons = _anons_id(test_ayarlari)
    _ihlal_ekle(test_ayarlari, kamera, {"announcement_id": anons}, saat_once=0.1)
    metin = istemci.get("/komuta/anons").text
    assert "Anonsun saatlere dağılımı" in metin
    assert "En yoğun" in metin
    saat = f"{zaman.yerel_saat(zaman.simdi_utc()):02d}:00"
    assert saat in metin


def test_anons_olmayinca_ogretici_bos_durum(istemci):
    metin = istemci.get("/komuta/anons").text
    assert "Bugün anons tetikleyen ihlal yok" in metin
    # Tasarımın örnek anons sayısı (41) sayı kutusuna sızmamalı.
    # Çıplak "41" aranamaz: başlıktaki sunucu saati günde bir kez "…:41"
    # gösterir ve test o dakikada sebepsiz kırılırdı. Sayı kutusunun kendisi
    # aranır — sızıntı zaten oraya düşerdi.
    assert ">41<" not in metin


# ---- hoparlör bölgeleri ----


def test_hoparlor_yokken_ogretici_bos_durum(istemci):
    metin = istemci.get("/komuta/anons").text
    assert "Hoparlör bölgesi tanımlanmadı" in metin
    assert "192.168.1.4" not in metin  # tasarımın örnek adresleri


def test_hoparlor_ekleniyor_ve_listeleniyor(istemci, test_ayarlari):
    _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    yanit = _hoparlor_ekle(istemci, "Sevkiyat rampaları", alan="Sevkiyat")
    assert yanit.status_code == 303

    kayit = _satir(test_ayarlari, "SELECT * FROM speaker_zones")
    assert kayit["name"] == "Sevkiyat rampaları"
    assert kayit["area"] == "Sevkiyat"
    assert kayit["enabled"] == 1

    metin = istemci.get("/komuta/anons").text
    assert "Sevkiyat rampaları" in metin
    assert "http://10.0.0.9:8080/anons" in metin
    assert "1 / 1 açık" in metin


def test_hoparlor_adresindeki_sifre_listede_maskeleniyor(istemci, test_ayarlari):
    """Liste satırında kullanıcı adı/şifre GÖRÜNMEZ (docs/01 §3.6).

    Kameranın RTSP adresiyle aynı desen: listede maskeli, düzenleme formunun
    girdi alanında ham — kullanıcı yanlış yazdığı şifreyi düzeltebilmeli ve
    o form varsayılan olarak kapalı duruyor.
    """
    _hoparlor_ekle(istemci, "Depo", adres="http://admin:gizli123@10.0.0.9/anons")
    metin = istemci.get("/komuta/anons").text
    liste_satiri = metin.split('class="hoparlor-satiri"')[1].split("<details")[0]
    assert "gizli123" not in liste_satiri
    assert "••••@10.0.0.9" in liste_satiri
    # Veritabanında ham adres durur; maskeleme yalnızca gösterimdedir
    assert _satir(test_ayarlari, "SELECT address FROM speaker_zones")[0].endswith("@10.0.0.9/anons")


def test_semasiz_adres_reddediliyor(istemci):
    yanit = istemci.post(
        "/hoparlorler/kaydet",
        data={"name": "Depo", "area": "", "address": "10.0.0.9/anons", "enabled": "1"},
    )
    assert yanit.status_code == 400
    assert "http://" in yanit.json()["hata"]


def test_adsiz_hoparlor_reddediliyor(istemci):
    yanit = istemci.post(
        "/hoparlorler/kaydet",
        data={"name": "  ", "area": "", "address": "http://10.0.0.9/anons", "enabled": "1"},
    )
    assert yanit.status_code == 400


def test_hoparlor_duzenleniyor(istemci, test_ayarlari):
    _hoparlor_ekle(istemci, "Depo")
    kayit_id = _satir(test_ayarlari, "SELECT id FROM speaker_zones")[0]
    istemci.post(
        "/hoparlorler/kaydet",
        data={
            "hoparlor_id": str(kayit_id),
            "name": "Depo koridoru",
            "area": "",
            "address": "http://10.0.0.10/anons",
            "description": "iki hoparlör",
            "enabled": "0",
        },
        follow_redirects=False,
    )
    kayit = _satir(test_ayarlari, "SELECT * FROM speaker_zones")
    assert kayit["name"] == "Depo koridoru"
    assert kayit["address"] == "http://10.0.0.10/anons"
    assert kayit["enabled"] == 0
    assert "kapalı" in istemci.get("/komuta/anons").text


def test_hoparlor_siliniyor_kurallar_etkilenmiyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    kural = _kural_ekle(test_ayarlari, kamera)
    _hoparlor_ekle(istemci, "Sevkiyat rampaları", alan="Sevkiyat")
    kayit_id = _satir(test_ayarlari, "SELECT id FROM speaker_zones")[0]

    istemci.post(f"/hoparlorler/{kayit_id}/sil", follow_redirects=False)
    assert _satir(test_ayarlari, "SELECT COUNT(*) FROM speaker_zones")[0] == 0
    assert _satir(test_ayarlari, "SELECT COUNT(*) FROM rules WHERE id = ?", (kural,))[0] == 1


def test_ulasilamayan_hoparlor_turkce_hata_veriyor(istemci):
    # 127.0.0.1:9 (discard portu) — kimse dinlemiyor, bağlantı hemen reddedilir
    _hoparlor_ekle(istemci, "Deneme", adres="http://kullanici:parola@127.0.0.1:9/anons")
    yanit = istemci.post("/hoparlorler/1/dene")
    assert yanit.status_code == 400
    hata = yanit.json()["hata"]
    assert "Deneme" in hata
    assert "ulaşılamadı" in hata
    # Hata ekranı da bir ekrandır: şifre oraya da basılmaz
    assert "parola" not in hata
    assert "••••@127.0.0.1:9" in hata


def test_olmayan_hoparlor_denenemez(istemci):
    assert istemci.post("/hoparlorler/999/dene").status_code == 400


def test_anons_kapali_uyarisi_ekranda(istemci):
    """Bölge tanımlı ama .env'de ANONS=null: 'açık' demek yalan olurdu."""
    _hoparlor_ekle(istemci, "Sevkiyat")
    metin = istemci.get("/komuta/anons").text
    assert "beklemede" in metin
    assert "yalnızca <b>IP hoparlör</b> yolunda" in metin


# ---- bölge seçim kuralı (anons katmanıyla AYNI fonksiyon) ----


def test_bolge_secimi_once_bolume_sonra_tum_fabrikaya_bakiyor():
    from app.olaylar.anons import bolge_sec

    bolgeler = [
        {"id": 1, "name": "Genel", "area": "", "enabled": 1},
        {"id": 2, "name": "Sevkiyat", "area": "Sevkiyat", "enabled": 1},
        {"id": 3, "name": "Depo", "area": "Depo", "enabled": 0},
    ]
    assert bolge_sec(bolgeler, "Sevkiyat")["id"] == 2
    # Kapalı bölge seçilmez, "tüm fabrika" bölgesine düşülür
    assert bolge_sec(bolgeler, "Depo")["id"] == 1
    assert bolge_sec(bolgeler, "")["id"] == 1
    assert bolge_sec([], "Sevkiyat") is None


def test_zincirde_dogru_hoparlor_yaziyor(istemci, test_ayarlari):
    """Ekranda yazan hoparlör, anonsun gerçekten gideceği hoparlör olmalı."""
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kural_ekle(test_ayarlari, kamera, anons_id=_anons_id(test_ayarlari))
    _hoparlor_ekle(istemci, "Sevkiyat rampaları", alan="Sevkiyat")
    _hoparlor_ekle(istemci, "Genel anons", alan="")

    # ANONS=http olduğunda bölge adı görünür
    istemci.app.state.ayarlar = _http_ayarlari(istemci.app.state.ayarlar)
    metin = istemci.get("/komuta/uyari").text
    assert "IP hoparlör · Sevkiyat rampaları" in metin
    assert "Genel anons" not in metin


def _http_ayarlari(ayarlar):
    """Aynı ayarların ANONS=http sürümü (dataclass donmuş olduğu için kopya)."""
    import dataclasses

    return dataclasses.replace(
        ayarlar, anons="http", anons_http_adresi="http://10.0.0.9:8080/anons"
    )


# =====================================================================
# TASARIMDAN SAHTE VERİ SIZMADI
# =====================================================================


@pytest.mark.parametrize("yol", ["/komuta/uyari", "/komuta/anons"])
def test_tasarimin_ornek_verileri_ekranda_yok(istemci, test_ayarlari, yol):
    kamera = _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kural_ekle(test_ayarlari, kamera, anons_id=_anons_id(test_ayarlari))
    metin = istemci.get(yol).text
    for sahte in (
        "Ani hareket",
        "12 kamera · 3 m",
        "192.168.1.4",
        "18 kez bugün",
        "6 / 7 çalışıyor",
        "Boyahane",
        "Dikkat, forklifte yaklaşmayın",
        "Gece vardiyasında",
    ):
        assert sahte not in metin, f"{yol} → tasarımdan sahte veri: {sahte}"

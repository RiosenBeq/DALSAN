"""Olay yaşam döngüsü süpervizörde ve canlı akışta (docs/17 §6.3; Faz 2c-3).

Kural katmanının geçişleri (tests/rules/test_olay_durumu.py) burada
veritabanına ve anonsa taşınır: açılışta satır + anons, hatırlatmada yeni satır
YOK ama anons var (S17), kapanışta bitiş ve sebep. Kamera, model ve iş
parçacığı yoktur; zaman, monotonik saate göre geriye verilir.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app import veritabani, zaman
from app.analiz.boru_hatti import KameraHatti
from app.analiz.kamera import DURUM_OFFLINE, DURUM_ONLINE
from app.analiz.supervizor import AnalizSupervizoru
from app.olaylar.yazici import ihlal_yaz
from app.rules.olay_durumu import ACILDI, HATIRLATMA, KAPANDI, OlayGecisi
from app.rules.tipler import Bolge, Ihlal, Kural, Tespit
from app.web.olaylar_web import kapanan_olaylar

ANAHTAR = (1, 1, 5)
ORTA = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]


@pytest.fixture
def baglanti(test_ayarlari):
    bag = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(bag)
    simdi = zaman.simdi_utc()
    bag.execute(
        "INSERT INTO cameras (id, name, area, source_type, source_url, created_at, updated_at) "
        "VALUES (1, 'Dolum', 'Üretim', 'rtsp', 'rtsp://x', ?, ?)",
        (simdi, simdi),
    )
    bag.execute(
        "INSERT INTO zones (id, camera_id, name, zone_type, polygon, updated_at) "
        "VALUES (1, 1, 'Makine', 'restricted', ?, ?)",
        (json.dumps(ORTA), simdi),
    )
    anons = bag.execute(
        "SELECT id FROM announcement_messages WHERE key = 'restricted_entry'"
    ).fetchone()["id"]
    bag.execute(
        "INSERT INTO rules (id, camera_id, zone_id, rule_type, target_classes, params, "
        "cooldown_s, announcement_id, enabled, updated_at) "
        "VALUES (1, 1, 1, 'zone_intrusion', '[\"person\"]', '{}', 60, ?, 1, ?)",
        (anons, simdi),
    )
    bag.commit()
    yield bag
    bag.close()


class _AnonsCasusu:
    def __init__(self):
        self.cagrilar = []

    def duyur(self, kamera_id, kamera_alani, zaman_s, mesaj, *, olay=None):
        self.cagrilar.append((kamera_id, kamera_alani, (mesaj or {}).get("key")))
        self.olaylar = [*getattr(self, "olaylar", []), olay]

    def golge_kaydet(self, *a, **kw):
        pass

    def ekran_kaydet(self, olay):
        pass


class _Hat:
    """Geçişleri senaryodan veren sahte hat (KameraHatti arayüzü)."""

    def __init__(self):
        self.gecisler: list[OlayGecisi] = []
        self.acik: dict[tuple, float] = {}

    def gecisleri_al(self):
        gecisler, self.gecisler = self.gecisler, []
        return gecisler

    def olaylari_birak(self, sebep):
        gecisler = [OlayGecisi(KAPANDI, a, None, sebep, t) for a, t in self.acik.items()]
        self.acik = {}
        return gecisler

    def son_islenmis_jpeg(self, bolgeler_dahil: bool = True):
        return None


@pytest.fixture
def supervizor(test_ayarlari, baglanti):
    sup = AnalizSupervizoru(test_ayarlari)
    sup._anons = _AnonsCasusu()
    sup._anons_mesajlari = {
        s["id"]: dict(s) for s in baglanti.execute("SELECT * FROM announcement_messages")
    }
    sup._kamera_konfig = {1: {"id": 1, "name": "Dolum", "area": "Üretim"}}
    return sup


def _ihlal():
    return Ihlal(
        kural_id=1,
        kamera_id=1,
        takip_idler=[5],
        bolge_id=1,
        olculen=2.0,
        detaylar={"sinif": "person", "mode": "inside"},
        kod="RESTRICTED_ENTRY",
        onem="high",
    )


def _olaylar(baglanti) -> list[dict]:
    satirlar = baglanti.execute(
        "SELECT id, event_type, event_code, occurred_at, resolved_at, details "
        "FROM events ORDER BY id"
    ).fetchall()
    return [{**dict(s), "detaylar": json.loads(s["details"])} for s in satirlar]


# ------------------------------------------------------------------ süpervizör


def test_acilis_hatirlatma_kapanis(supervizor, baglanti):
    hat = _Hat()
    hat.gecisler = [OlayGecisi(ACILDI, ANAHTAR, _ihlal())]
    supervizor._gecisleri_isle(baglanti, hat, 100.0)
    (olay,) = _olaylar(baglanti)
    assert olay["event_code"] == "RESTRICTED_ENTRY" and olay["resolved_at"] is None
    assert supervizor._anons.cagrilar == [(1, "Üretim", "restricted_entry")]

    # Bekleme süresi doldu, kişi hâlâ içeride: yeni satır YOK, anons tekrarlanır
    hat.gecisler = [OlayGecisi(HATIRLATMA, ANAHTAR, _ihlal())]
    supervizor._gecisleri_isle(baglanti, hat, 160.0)
    assert len(_olaylar(baglanti)) == 1
    assert len(supervizor._anons.cagrilar) == 2

    # Olay bir dakika önce açılmış olsun; koşul 7 sn önce son görüldü
    baglanti.execute(
        "UPDATE events SET occurred_at = ? WHERE id = ?", (zaman.saniye_once_utc(60), olay["id"])
    )
    hat.gecisler = [OlayGecisi(KAPANDI, ANAHTAR, None, "kosul_bitti", time.monotonic() - 7.0)]
    supervizor._gecisleri_isle(baglanti, hat, 170.0)
    (olay,) = _olaylar(baglanti)
    assert olay["detaylar"]["kapanis_sebebi"] == "kosul_bitti"
    gecen = zaman.sure_saniye(olay["resolved_at"])
    assert 6 <= gecen <= 9  # bitiş, kapanışın fark edildiği an değil
    assert supervizor._acik_olaylar == {}


def test_golge_modda_hatirlatma_da_susar(supervizor, baglanti):
    baglanti.execute("UPDATE rules SET shadow_mode = 1 WHERE id = 1")
    baglanti.commit()
    hat = _Hat()
    hat.gecisler = [
        OlayGecisi(ACILDI, ANAHTAR, _ihlal()),
        OlayGecisi(HATIRLATMA, ANAHTAR, _ihlal()),
    ]
    supervizor._gecisleri_isle(baglanti, hat, 100.0)
    assert len(_olaylar(baglanti)) == 1
    assert supervizor._anons.cagrilar == []


def test_acilisi_yazilamamis_olayin_hatirlatmasi_satiri_yazar(supervizor, baglanti):
    """Açılışta veritabanı kilitliydi: olay kaybolmaz, ilk hatırlatmada yazılır."""
    hat = _Hat()
    hat.gecisler = [OlayGecisi(HATIRLATMA, ANAHTAR, _ihlal())]
    supervizor._gecisleri_isle(baglanti, hat, 100.0)
    (olay,) = _olaylar(baglanti)
    assert olay["resolved_at"] is None
    assert supervizor._acik_olaylar == {ANAHTAR: olay["id"]}


class _SahteKaynak:
    son_hata = ""
    olculen_fps = 6.0

    def __init__(self, hal):
        self.hal = hal

    def durum(self):
        return self.hal

    def kesintisiz_akis_sn(self):
        return 0.0


def test_kamera_kopunca_acik_ihlal_olayi_kamera_koptu_ile_biter(supervizor, baglanti):
    hat = _Hat()
    hat.gecisler = [OlayGecisi(ACILDI, ANAHTAR, _ihlal())]
    supervizor._gecisleri_isle(baglanti, hat, 100.0)
    hat.acik = {ANAHTAR: time.monotonic() - 2.0}
    supervizor._hatlar = {1: hat}
    supervizor._kaynaklar = {1: _SahteKaynak(DURUM_OFFLINE)}
    supervizor._son_durumlar = {1: DURUM_ONLINE}

    supervizor._durumlari_yaz(baglanti)

    ihlal, kopukluk = _olaylar(baglanti)
    assert kopukluk["event_code"] == "CAMERA_DOWN"
    assert ihlal["resolved_at"] is not None
    assert ihlal["detaylar"]["kapanis_sebebi"] == "kamera_koptu"


def test_gercek_hatta_kural_kaldirilinca_olay_kural_degisti_ile_biter(supervizor, baglanti):
    """Gerçek KameraHatti + kural motoru: kişi yasak alanda → olay açılır;
    kural silinince (yapılandırma yenilemesi) olay hemen biter."""
    kural = Kural(
        id=1,
        kamera_id=1,
        tip="zone_intrusion",
        bolge_id=1,
        hedef_siniflar=["person"],
        params={"min_dwell_s": 0.0},
        cooldown_s=60.0,
    )
    bolge = Bolge(id=1, tip="restricted", poligon=ORTA)
    hat = KameraHatti(1, 6)
    hat.yapilandir([bolge], [kural], None)
    kisi = Tespit(sinif="person", kutu=(460.0, 300.0, 540.0, 500.0), takip_id=5)
    simdi = time.monotonic()
    hat._motor.degerlendir(simdi, (1000.0, 1000.0), [kisi], [bolge], None)
    supervizor._gecisleri_isle(baglanti, hat, simdi)
    (olay,) = _olaylar(baglanti)
    assert olay["event_code"] == "RESTRICTED_ENTRY" and olay["resolved_at"] is None

    hat.yapilandir([bolge], [], None)  # kural silindi
    supervizor._gecisleri_isle(baglanti, hat, time.monotonic())
    (olay,) = _olaylar(baglanti)
    assert olay["detaylar"]["kapanis_sebebi"] == "kural_degisti"
    assert olay["resolved_at"] is not None


def test_hat_atilinca_acik_olay_kamera_degisti_ile_biter(supervizor, baglanti):
    hat = _Hat()
    hat.gecisler = [OlayGecisi(ACILDI, ANAHTAR, _ihlal())]
    supervizor._gecisleri_isle(baglanti, hat, 100.0)
    hat.acik = {ANAHTAR: time.monotonic()}
    supervizor._hatlar = {1: hat}
    supervizor._hatti_birak(baglanti, 1, "kamera_degisti")
    (olay,) = _olaylar(baglanti)
    assert olay["detaylar"]["kapanis_sebebi"] == "kamera_degisti"
    assert 1 not in supervizor._hatlar


# ------------------------------------------------------------------ yazıcı ve canlı akış


def test_suren_ihlal_bitissiz_yazilir(baglanti, test_ayarlari):
    olay_id = ihlal_yaz(baglanti, test_ayarlari, _ihlal(), {"id": 1}, None, suruyor=True)
    satir = baglanti.execute("SELECT resolved_at FROM events WHERE id = ?", (olay_id,)).fetchone()
    assert satir["resolved_at"] is None


def test_canli_akis_kapanan_olaylari_bildirir(baglanti, test_ayarlari):
    suren = ihlal_yaz(baglanti, test_ayarlari, _ihlal(), {"id": 1}, None, suruyor=True)
    biten = ihlal_yaz(baglanti, test_ayarlari, _ihlal(), {"id": 1}, None, suruyor=True)
    baglanti.execute(
        "UPDATE events SET occurred_at = ?, resolved_at = ? WHERE id = ?",
        (zaman.saniye_once_utc(30), zaman.saniye_once_utc(18), biten),
    )
    baglanti.commit()
    assert kapanan_olaylar(baglanti, set()) == []
    (guncelleme,) = kapanan_olaylar(baglanti, {suren, biten})
    assert guncelleme == {
        "guncelleme": "bitti",
        "id": biten,
        "tip": "violation",
        "sure_metni": "12 sn",
    }


def test_arayuz_bitti_guncellemesini_isler():
    """Kritik bant kendiliğinden kaybolmaz; olay bitince ya da tıklanınca kapanır."""
    statik = Path(__file__).resolve().parents[1] / "backend" / "app" / "web" / "static"
    uyari = (statik / "uyari.js").read_text(encoding="utf-8")
    assert 'if (veri.onem !== "critical") k._zamanlayici = setTimeout(gizle, 8000);' in uyari
    assert 'kutu.addEventListener("click", gizle);' in uyari
    assert "bitti: function (id)" in uyari
    canli = (statik / "canli.js").read_text(encoding="utf-8")
    assert 'if (veri.guncelleme === "bitti")' in canli
    assert "window.Uyari.bitti(veri.id)" in canli

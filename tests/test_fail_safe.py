"""Fail-safe sırası: kayıt yapılamasa da uyarı duyurulur (docs/17 §3.5; Faz 2d-1).

Eskiden `_ihlali_kaydet` önce kural satırını okuyup olayı yazıyor, anonsu en
son çalıyordu. İkisinden biri istisna fırlatırsa (kilitli veritabanı, dolu
disk) anons hiç çalmıyor, hata döngüde yutuluyordu: ihlal ne kayda geçiyor ne
duyuruluyordu. Şimdi:

- olay satırı yazılamazsa CRITICAL günlük + /saglik "olay_yazilamadi", anons YİNE çalar;
- kural satırı okunamazsa gölge/anons kararı bellekteki haritadan verilir —
  gölgedeki kural bellekten tanınıp susar.
"""

from __future__ import annotations

import sqlite3

import pytest

from app import veritabani, zaman
from app.analiz import supervizor as supervizor_modulu
from app.analiz.supervizor import AnalizSupervizoru
from app.rules.olay_durumu import ACILDI, HATIRLATMA, OlayGecisi
from app.rules.tipler import Ihlal


class _AnonsCasusu:
    """duyur() çağrılarını kaydeder; hiçbir ses çalmaz."""

    def __init__(self) -> None:
        self.cagrilar: list[tuple] = []

    def duyur(self, kamera_id, kamera_alani, zaman_s, mesaj):
        self.cagrilar.append((kamera_id, kamera_alani, mesaj))

    def bolgeleri_yukle(self, satirlar) -> None:
        list(satirlar)


class _HatCasusu:
    def son_islenmis_jpeg(self, bolgeler_dahil: bool = True):
        return None


@pytest.fixture
def ortam(test_ayarlari):
    """Tek kamera, anonslu tek kural (gölgesiz) ve casus anonslu süpervizör."""
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    simdi = zaman.simdi_utc()
    # Kamera kapalı: yapılandırma yüklenince okuma iş parçacığı açılmasın
    baglanti.execute(
        "INSERT INTO cameras (id, name, area, source_type, source_url, enabled, created_at, "
        "updated_at) VALUES (1, 'Rampa 1', 'Sevkiyat', 'rtsp', 'rtsp://a/1', 0, ?, ?)",
        (simdi, simdi),
    )
    anons = baglanti.execute(
        "SELECT id FROM announcement_messages WHERE key = 'safe_distance'"
    ).fetchone()["id"]
    for kural_id, golge in ((1, 0), (2, 1)):
        baglanti.execute(
            "INSERT INTO rules (id, camera_id, rule_type, target_classes, params, cooldown_s, "
            "announcement_id, enabled, shadow_mode, updated_at) "
            "VALUES (?, 1, 'safe_distance', '[\"person\"]', '{}', 90, ?, 1, ?, ?)",
            (kural_id, anons, golge, simdi),
        )
    baglanti.commit()

    supervizor = AnalizSupervizoru(test_ayarlari)
    supervizor._anons = _AnonsCasusu()
    supervizor._kamera_konfig = {1: {"id": 1, "area": "Sevkiyat"}}
    supervizor._konfigurasyonu_yenile(baglanti)  # anons mesajları + kural haritası
    try:
        yield supervizor, baglanti
    finally:
        baglanti.close()


def _ihlal(kural_id: int = 1) -> Ihlal:
    return Ihlal(kural_id=kural_id, kamera_id=1, takip_idler=[3], bolge_id=None, olculen=2.1)


def _olay_sayisi(baglanti) -> int:
    return baglanti.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def _kilitli(*args, **kwargs):
    raise sqlite3.OperationalError("database is locked")


def test_kural_haritasi_yapilandirmayla_yuklenir(ortam):
    supervizor, _ = ortam
    assert supervizor._kural_haritasi[1]["shadow_mode"] == 0
    assert supervizor._kural_haritasi[2]["shadow_mode"] == 1
    assert supervizor._kural_haritasi[1]["announcement_id"] is not None


def test_olay_yazilamazsa_uyari_yine_duyurulur(ortam, monkeypatch):
    supervizor, baglanti = ortam
    monkeypatch.setattr(supervizor_modulu, "ihlal_yaz", _kilitli)

    olay_id = supervizor._ihlali_kaydet(baglanti, _HatCasusu(), _ihlal(), 100.0)

    assert olay_id is None
    assert len(supervizor._anons.cagrilar) == 1, "kayıt başarısız ama anons çalmalı"
    assert supervizor._anons.cagrilar[0][:2] == (1, "Sevkiyat")
    assert supervizor.sorunlar() == ["olay_yazilamadi"]
    assert _olay_sayisi(baglanti) == 0


def test_basarili_kayit_olay_yazilamadi_isaretini_temizler(ortam, monkeypatch):
    supervizor, baglanti = ortam
    monkeypatch.setattr(supervizor_modulu, "ihlal_yaz", _kilitli)
    supervizor._ihlali_kaydet(baglanti, _HatCasusu(), _ihlal(), 100.0)
    monkeypatch.undo()

    assert supervizor._ihlali_kaydet(baglanti, _HatCasusu(), _ihlal(), 200.0) is not None
    assert supervizor.sorunlar() == []
    assert _olay_sayisi(baglanti) == 1


def test_kural_satiri_okunamazsa_anons_bellekten_calar(ortam, monkeypatch):
    supervizor, baglanti = ortam
    monkeypatch.setattr(supervizor, "_kural_kaydi", _kilitli)

    supervizor._ihlali_kaydet(baglanti, _HatCasusu(), _ihlal(1), 100.0)

    assert len(supervizor._anons.cagrilar) == 1
    # Olay yine yazılır; kural anlık görüntüsü bellekteki kadarıyla eksik kalır
    assert _olay_sayisi(baglanti) == 1


def test_kural_satiri_okunamazken_golgedeki_kural_bellekten_taninip_susar(ortam, monkeypatch):
    supervizor, baglanti = ortam
    monkeypatch.setattr(supervizor, "_kural_kaydi", _kilitli)

    supervizor._ihlali_kaydet(baglanti, _HatCasusu(), _ihlal(2), 100.0)

    assert supervizor._anons.cagrilar == [], "gölgedeki kural susmalı"
    assert _olay_sayisi(baglanti) == 1


def test_ikisi_birden_bozukken_de_duyurulur(ortam, monkeypatch):
    """Veritabanı tamamen kilitli: ne kural okunur ne olay yazılır — anons çalar."""
    supervizor, baglanti = ortam
    monkeypatch.setattr(supervizor, "_kural_kaydi", _kilitli)
    monkeypatch.setattr(supervizor_modulu, "ihlal_yaz", _kilitli)

    supervizor._ihlali_kaydet(baglanti, _HatCasusu(), _ihlal(1), 100.0)

    assert len(supervizor._anons.cagrilar) == 1
    assert supervizor.sorunlar() == ["olay_yazilamadi"]


def test_yazilamayan_acilis_hatirlatmada_yazilir(ortam, monkeypatch):
    """Açılış yazılamazsa olay "açık" sayılmaz; hatırlatma geldiğinde yazılır."""
    supervizor, baglanti = ortam
    anahtar = (1, 1, 3)
    monkeypatch.setattr(supervizor_modulu, "ihlal_yaz", _kilitli)
    supervizor._gecisi_isle(baglanti, _HatCasusu(), OlayGecisi(ACILDI, anahtar, _ihlal()), 100.0)
    assert anahtar not in supervizor._acik_olaylar
    monkeypatch.undo()

    supervizor._gecisi_isle(
        baglanti, _HatCasusu(), OlayGecisi(HATIRLATMA, anahtar, _ihlal()), 190.0
    )
    assert anahtar in supervizor._acik_olaylar
    assert _olay_sayisi(baglanti) == 1
    assert len(supervizor._anons.cagrilar) == 2  # açılış ve hatırlatma ikisi de duyuruldu


def test_saglik_olay_yazilamadi_der(istemci, test_ayarlari):
    supervizor = AnalizSupervizoru(test_ayarlari)
    supervizor.olay_yazma_hatasi = "OperationalError: database is locked"
    istemci.app.state.supervizor = supervizor
    try:
        yanit = istemci.get("/saglik")
    finally:
        istemci.app.state.supervizor = None
    assert yanit.status_code == 200
    assert yanit.json()["durum"] == "calisiyor"
    assert "olay_yazilamadi" in yanit.json()["sorunlar"]

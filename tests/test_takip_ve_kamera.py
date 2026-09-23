"""Faz 2b - takip ve kamera (docs/17 §13, K7, K8, R29).

Gerçek kamera, ağ ya da model kullanılmaz: zaman elle verilir, cv2 ve kaynak
sahtedir. Sınanan şey kararlardır: takip hafızası kaç kare, kopukluk kaç
saniyede fark edilir, "tekrar çevrimiçi" ne zaman yazılır, kurala hangi zaman
gider.
"""

from __future__ import annotations

import dataclasses

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import veritabani, zaman
from app.analiz import kamera as kamera_modulu
from app.analiz.boru_hatti import KameraHatti
from app.analiz.kamera import DURUM_OFFLINE, DURUM_ONLINE, KameraKaynagi
from app.analiz.supervizor import AnalizSupervizoru, _KameraOlcumu, _yuzdelik
from app.analiz.takip import Takipci, kayip_iz_tamponu
from app.rules.tipler import Kural
from app.uygulama import uygulama_olustur

# ------------------------------------------------------------- takip hafızası


def test_takip_hafizasi_kare_hizina_gore_olceklenir():
    """supervision tamponu 30 fps'teki kare sayar ve kendi kare hızına ölçekler:
    6 fps × 2 sn hafıza = 12 kare (docs/17 §13 2b)."""
    assert kayip_iz_tamponu(2.0) == 60
    assert Takipci(6, 2.0)._izleyici.max_time_lost == 12
    # Eski davranış (tampon 30): fps ne olursa olsun 1 sn
    assert Takipci(6)._izleyici.max_time_lost == 6


def _bolge_kurali() -> Kural:
    return Kural(
        id=1,
        kamera_id=1,
        tip="zone_intrusion",
        bolge_id=1,
        hedef_siniflar=["person"],
        params={},
        cooldown_s=60.0,
    )


def test_kural_ve_sayac_izi_takip_hafizasi_kadar_bekler():
    """Takipçi izi 2 sn aynı kimlikle beklerken kural 5 değerlendirmede
    (6 fps'te 0,83 sn) bırakırsa kalış sayacı yine sıfırlanırdı (§6.3)."""
    hat = KameraHatti(1, 6, takip_hafiza_sn=2.0)
    assert hat.kayip_toleransi == 12
    hat.yapilandir([], [_bolge_kurali()], None)
    assert hat._motor._degerlendiriciler[0]._kayip_toleransi == 12
    assert hat._sayac._kayip_toleransi == 12


def test_hafiza_verilmezse_eski_tolerans_kalir():
    hat = KameraHatti(1, 6)
    hat.yapilandir([], [_bolge_kurali()], None)
    assert hat._motor._degerlendiriciler[0]._kayip_toleransi == 5


def test_ornekleme_hizi_degisince_hat_korunur_tolerans_guncellenir():
    """R34: örnekleme hızı değişince hat yeniden KURULMAZ (izler, kalış
    sayaçları, cooldown ve açık olaylar giderdi); yalnız saniyeden kareye
    çevrilen iki sayı yeni hıza göre değişir: 2 sn hafıza 10 fps'te 20 kare."""
    hat = KameraHatti(1, 6, takip_hafiza_sn=2.0)
    hat.yapilandir([], [_bolge_kurali()], None)
    degerlendirici, takipci, sayac = hat._motor._degerlendiriciler[0], hat._takipci, hat._sayac
    hat.fps_guncelle(10)
    assert (hat.fps, hat.kayip_toleransi) == (10, 20)
    assert hat._takipci is takipci and takipci._izleyici.max_time_lost == 20
    assert hat._motor._degerlendiriciler[0] is degerlendirici
    assert degerlendirici._kayip_toleransi == 20
    assert hat._sayac is sayac and sayac._kayip_toleransi == 20
    # Sonradan yeniden kurulan değerlendirici de yeni toleransı alır
    hat.yapilandir([], [dataclasses.replace(_bolge_kurali(), cooldown_s=30.0)], None)
    assert hat._motor._degerlendiriciler[0]._kayip_toleransi == 20


def test_hiz_degisince_takip_kimligi_korunur():
    """Takipçi yeniden kurulsaydı aynı kişi yeni bir kimlikle görünür, kalış
    sayacı sıfırlanır ve uyarı tekrarlardı."""
    takipci = Takipci(6, 2.0)
    kutu, guven, sinif = (
        np.array([[100.0, 100.0, 150.0, 260.0]]),
        np.array([0.9]),
        np.array(["person"]),
    )
    kimlikler = {t.takip_id for _ in range(3) for t in takipci.guncelle(kutu, guven, sinif)}
    takipci.kare_hizi_guncelle(10)
    sonra = {t.takip_id for _ in range(2) for t in takipci.guncelle(kutu, guven, sinif)}
    assert len(kimlikler) == 1 and sonra == kimlikler


def test_supervizor_hiz_degisince_hatti_atmaz(test_ayarlari, monkeypatch):
    """Süpervizör yapılandırma yenilemesinde aynı hat nesnesini korur ve
    açık olayları "kamera değişti" diye kapatmaz."""
    supervizor = AnalizSupervizoru(test_ayarlari)
    hat = KameraHatti(1, 6, takip_hafiza_sn=2.0)
    supervizor._hatlar[1] = hat
    birakilanlar = []
    monkeypatch.setattr(supervizor, "_hatti_birak", lambda *a: birakilanlar.append(a))
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        baglanti.execute(
            "INSERT INTO cameras (id, name, source_type, source_url, enabled, sample_fps, "
            "created_at, updated_at) VALUES (1, 'Rampa', 'rtsp', 'rtsp://10.0.0.5/1', 1, 10, "
            "?, ?)",
            (zaman.simdi_utc(), zaman.simdi_utc()),
        )
        baglanti.commit()
        monkeypatch.setattr(
            supervizor,
            "_atanmis_kameralar",
            lambda b: [dict(r) for r in b.execute("SELECT * FROM cameras")],
        )
        monkeypatch.setattr(kamera_modulu.KameraKaynagi, "baslat", lambda self: None)
        supervizor._konfigurasyonu_yenile(baglanti)
    finally:
        baglanti.close()
        supervizor._anons.kapat(1.0)
    assert supervizor._hatlar[1] is hat and hat.fps == 10 and hat.kayip_toleransi == 20
    assert birakilanlar == []


# ------------------------------------------------------------- RTSP zaman aşımı


def test_rtsp_acilisina_zaman_asimlari_gecer(monkeypatch):
    """Zaman aşımı olmadan FFmpeg yanıtsız bir kamerada dakikalarca bekler ve
    iş parçacığı takılır (AUDIT R4)."""
    cagrilar = []

    class _SahteYakalayici:
        def __init__(self, *argumanlar):
            cagrilar.append(argumanlar)

        def isOpened(self):  # noqa: N802 - OpenCV adı
            return True

    monkeypatch.setattr(kamera_modulu.cv2, "VideoCapture", _SahteYakalayici)
    monkeypatch.setattr(KameraKaynagi, "_on_kontrol", lambda self: "")
    kaynak = KameraKaynagi(
        1,
        "K1",
        "rtsp",
        "rtsp://10.0.0.5/ana",
        acilis_zaman_asimi_ms=4000,
        okuma_zaman_asimi_ms=9000,
    )
    assert kaynak._ac() is not None
    url, arka_uc, parametreler = cagrilar[0]
    assert (url, arka_uc) == ("rtsp://10.0.0.5/ana", cv2.CAP_FFMPEG)
    assert parametreler == [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
        4000,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
        9000,
    ]


# ------------------------------------------------------------- kesintisiz akış


def test_kesintisiz_akis_kopukluktan_sonra_yeniden_baslar():
    kaynak = KameraKaynagi(1, "K1", "rtsp", "rtsp://x")
    kaynak._akis_baslangici, kaynak._son_kare_zamani = 100.0, 104.0
    assert kaynak.kesintisiz_akis_sn(simdi=104.5) == pytest.approx(4.5)
    # Son kareden bu yana kopukluk eşiği geçti: akış yok
    assert kaynak.kesintisiz_akis_sn(simdi=104.0 + 11) == 0.0


# ------------------------------------------------------------- UP kararlılığı


class _SahteKaynak:
    def __init__(self):
        self.hal = DURUM_OFFLINE
        self.akis_sn = 0.0
        self.son_hata = ""
        self.olculen_fps = 6.0

    def durum(self):
        return self.hal

    def kesintisiz_akis_sn(self):
        return self.akis_sn


@pytest.fixture
def supervizor(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO cameras (id, name, source_type, source_url, sample_fps, created_at, "
        "updated_at) VALUES (1, 'Rampa', 'rtsp', 'rtsp://x', 6, ?, ?)",
        (simdi, simdi),
    )
    baglanti.commit()
    sup = AnalizSupervizoru(dataclasses.replace(test_ayarlari, kamera_up_kararlilik_sn=5.0))
    kaynak = _SahteKaynak()
    sup._kaynaklar = {1: kaynak}
    sup._kamera_konfig = {1: {"name": "Rampa", "sample_fps": 6}}
    sup._son_durumlar = {1: DURUM_OFFLINE}
    yield sup, kaynak, baglanti
    baglanti.close()


def _mesajlar(baglanti) -> list[str]:
    return [
        __import__("json").loads(satir[0])["mesaj"]
        for satir in baglanti.execute(
            "SELECT details FROM events WHERE event_type = 'system' ORDER BY id"
        )
    ]


def test_tekrar_cevrimici_kararli_akistan_once_yazilmaz(supervizor):
    sup, kaynak, baglanti = supervizor
    kaynak.hal, kaynak.akis_sn = DURUM_ONLINE, 2.0
    sup._durumlari_yaz(baglanti)
    assert not any("tekrar çevrimiçi" in m for m in _mesajlar(baglanti))
    # Ekrandaki durum anlıktır: kamera satırı yine de çevrimiçi görünür
    assert baglanti.execute("SELECT status FROM cameras").fetchone()[0] == DURUM_ONLINE

    kaynak.akis_sn = 6.0
    sup._durumlari_yaz(baglanti)
    assert [m for m in _mesajlar(baglanti) if "tekrar çevrimiçi" in m] == [
        "Kamera tekrar çevrimiçi: Rampa"
    ]


def test_gidip_gelen_baglanti_olay_seli_uretmez(supervizor):
    """Her iki saniyede bir kopan kablo: kararlı akış hiç oluşmaz, olay yok."""
    sup, kaynak, baglanti = supervizor
    for _ in range(5):
        kaynak.hal, kaynak.akis_sn = DURUM_ONLINE, 2.0
        sup._durumlari_yaz(baglanti)
        kaynak.hal, kaynak.akis_sn = DURUM_OFFLINE, 0.0
        sup._durumlari_yaz(baglanti)
    assert _mesajlar(baglanti) == []


# ------------------------------------------------------------- R29 ve ölçümler


def test_kurala_karenin_zamani_gider_ve_islem_olculur(supervizor):
    """AUDIT R29: kurala işlendiği an gidiyordu; kare kuyrukta beklediyse hız
    hesabındaki dt ve kalış süresi kayardı."""
    sup, _, baglanti = supervizor

    class _Kaynak:
        def son_kare(self):
            return np.zeros((4, 4, 3), np.uint8), 1234.5

    class _Hat:
        def __init__(self):
            self.zamanlar = []

        def isle(self, kare, zaman_s, tespitci, kkd):
            self.zamanlar.append(zaman_s)
            return [], []

        def gecisleri_al(self):  # olay yaşam döngüsü (KameraHatti arayüzü)
            return []

    hat = _Hat()
    sup._kaynaklar = {1: _Kaynak()}
    sup._hatlar = {1: hat}
    sup._kkd_ornekle = lambda *a, **k: None
    sup._kameralari_isle(baglanti, simdi=2000.0)
    assert hat.zamanlar == [1234.5]
    assert len(sup._olcumler[1].isle_ms) == 1


def test_olcum_ozeti():
    olcum = _KameraOlcumu()
    for i in range(13):  # 6 fps, 2 sn
        olcum.islenen.append(100.0 + i / 6)
    assert olcum.islenen_fps(simdi=102.0) == pytest.approx(6.0)
    assert _yuzdelik(list(range(1, 11)), 90) == 9
    assert _yuzdelik([], 90) is None  # ölçülmedi, 0 değil


# ------------------------------------------------------------- varsayılan örnekleme


def test_yeni_kameranin_varsayilan_hizi_ayardan_gelir(test_ayarlari):
    """kameralar.py sabit 6 yazıyordu; .env KARE_ORNEKLEME_FPS okunmuyordu."""
    ayarlar = dataclasses.replace(test_ayarlari, kare_ornekleme_fps=4)
    with TestClient(uygulama_olustur(ayarlar, analiz=False)) as istemci:
        assert 'value="4"' in istemci.get("/kameralar/yeni").text
        istemci.post(
            "/kameralar/yeni",
            data={"name": "Rampa", "source_type": "rtsp", "source_url": "rtsp://10.0.0.5/1"},
        )
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
    try:
        assert baglanti.execute("SELECT sample_fps FROM cameras").fetchone()[0] == 4
    finally:
        baglanti.close()

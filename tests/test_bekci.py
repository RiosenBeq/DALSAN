"""Bekçi, analiz yavaşlığı ve analiz saatleri (docs/17 §3.6, §8.2; Faz 2d-2).

- Bekçi: sahte saatle takılmayı yakalar; görüntü yokken ya da model
  hazırlanırken saymaz; aynı sorunu bir kez bildirir; masaüstü paketinde
  süreçten çıkmaz, sunucu kipinde `os._exit` çağrılır (sahte çıkış).
- ANALYSIS_DEGRADED: üst üste işleme hatası hattı yeniden kurar; işlenen hız
  hedefin altında kalırsa bir kez yazılır.
- analysis_hours: analiz edilen süre, işlenen ve başarısız kare sayısı.
"""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from app import veritabani, zaman
from app.analiz import bekci as bekci_modulu
from app.analiz.bekci import ANALIZ_OLU, ANALIZ_TAKILDI, YENIDEN_BASLATMA_KODU, Bekci
from app.analiz.kamera import DURUM_OFFLINE, DURUM_ONLINE
from app.analiz.supervizor import AnalizSupervizoru, _KameraOlcumu

# ------------------------------------------------------------------ bekçi


class _SahteAnaliz:
    def __init__(self) -> None:
        self.canli = True
        self.nabiz: float | None = 0.0
        self.model_durumu = "hazir"
        self.kare_var = True

    def analiz_canli_mi(self) -> bool:
        return self.canli

    def kare_ureten_kamera_var(self, simdi: float) -> bool:
        return self.kare_var


class _Saat:
    def __init__(self) -> None:
        self.an = 0.0

    def __call__(self) -> float:
        return self.an


@pytest.fixture
def bekci_ortami(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    baglanti.close()
    analiz, saat, cikislar = _SahteAnaliz(), _Saat(), []

    def kur(**ek):
        ayarlar = dataclasses.replace(test_ayarlari, **ek)
        return Bekci(analiz, ayarlar, saat=saat, cikis=cikislar.append)

    return analiz, saat, cikislar, kur


def _stalled_olaylari(test_ayarlari) -> list[str]:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return [
            json.loads(s["details"])["mesaj"]
            for s in baglanti.execute(
                "SELECT details FROM events WHERE event_code = 'ANALYSIS_STALLED' ORDER BY id"
            )
        ]
    finally:
        baglanti.close()


def test_taze_nabizda_sorun_yok(bekci_ortami, test_ayarlari):
    analiz, saat, _, kur = bekci_ortami
    bekci = kur()
    saat.an, analiz.nabiz = 1000.0, 999.0
    bekci.tur()
    assert bekci.sorun is None
    assert _stalled_olaylari(test_ayarlari) == []


def test_sahte_saatle_takilma_yakalanir_ve_bir_kez_bildirilir(bekci_ortami, test_ayarlari):
    analiz, saat, cikislar, kur = bekci_ortami
    bekci = kur()  # BEKCI_ESIGI_SN varsayılanı 90
    analiz.nabiz = 1000.0
    saat.an = 1089.0
    bekci.tur()
    assert bekci.sorun is None, "eşiğin altında takılma yok"

    saat.an = 1095.0
    bekci.tur()
    saat.an = 1105.0
    bekci.tur()  # aynı sorun: ikinci olay yok
    assert bekci.sorun == ANALIZ_TAKILDI
    (mesaj,) = _stalled_olaylari(test_ayarlari)
    assert mesaj.startswith("Analiz takıldı: görüntü geliyor ama analiz 95 sn'dir ilerlemiyor")
    assert cikislar == [], "varsayılan tepki yalnız uyarmaktır"

    analiz.nabiz = 1104.0  # döngü yeniden ilerledi
    bekci.tur()
    assert bekci.sorun is None


def test_goruntu_yokken_ya_da_model_hazirlanirken_takilma_sayilmaz(bekci_ortami):
    analiz, saat, _, kur = bekci_ortami
    bekci = kur()
    analiz.nabiz, saat.an = 0.0, 500.0
    analiz.kare_var = False
    bekci.tur()
    assert bekci.sorun is None

    analiz.kare_var = True
    for evre in ("yukleniyor", "indiriliyor"):
        analiz.model_durumu = evre
        bekci.tur()
        assert bekci.sorun is None

    analiz.model_durumu, analiz.nabiz = "hazir", None  # döngü hiç başlamadı
    bekci.tur()
    assert bekci.sorun is None


def test_olu_is_parcacigi_bildirilir(bekci_ortami, test_ayarlari):
    analiz, _, _, kur = bekci_ortami
    bekci = kur()
    analiz.canli = False
    bekci.tur()
    assert bekci.sorun == ANALIZ_OLU
    (mesaj,) = _stalled_olaylari(test_ayarlari)
    assert mesaj.startswith("Analiz durdu:")


def test_sunucu_kipinde_yeniden_baslatma_os_exit_cagirir(bekci_ortami, test_ayarlari, monkeypatch):
    analiz, saat, cikislar, kur = bekci_ortami
    monkeypatch.setattr(bekci_modulu, "paketlenmis_mi", lambda: False)
    bekci = kur(bekci_tepkisi="yeniden_baslat")
    analiz.nabiz, saat.an = 0.0, 200.0
    bekci.tur()
    assert cikislar == [YENIDEN_BASLATMA_KODU]
    # Çıkmadan önce iz bırakılır: olay yazılmış olmalı
    assert _stalled_olaylari(test_ayarlari)[0].endswith("Program yeniden başlatılıyor.")


def test_masaustu_paketinde_hicbir_zaman_surecten_cikmaz(bekci_ortami, monkeypatch):
    analiz, saat, cikislar, kur = bekci_ortami
    monkeypatch.setattr(bekci_modulu, "paketlenmis_mi", lambda: True)
    bekci = kur(bekci_tepkisi="yeniden_baslat")
    analiz.nabiz, saat.an = 0.0, 200.0
    bekci.tur()
    assert bekci.sorun == ANALIZ_TAKILDI
    assert cikislar == [], "Kontrol Paneli de kapanırdı"


def test_bekci_sorunu_supervizorun_sorunlarinda(test_ayarlari):
    supervizor = AnalizSupervizoru(test_ayarlari)
    assert supervizor.sorunlar() == []
    supervizor.bekci.sorun = ANALIZ_TAKILDI
    assert supervizor.sorunlar() == [ANALIZ_TAKILDI]


def test_baslamamis_supervizorde_bekci_calismaz_ve_durdurulabilir(test_ayarlari):
    supervizor = AnalizSupervizoru(test_ayarlari)
    supervizor.bekci.durdur()  # başlatılmadan durdurmak hata vermemeli
    assert supervizor.analiz_canli_mi() is False


# ------------------------------------------------------------------ analiz sağlığı


class _Kaynak:
    def __init__(self, durum: str = DURUM_ONLINE, fps: float = 6.0) -> None:
        self._durum, self.olculen_fps = durum, fps
        self.kare_zamani = 0.0

    def durum(self, simdi=None) -> str:
        return self._durum

    def son_kare(self):
        self.kare_zamani += 1.0
        return np.zeros((48, 64, 3), dtype=np.uint8), self.kare_zamani


class _Hat:
    """Kare işlemede istenen kez hata veren hat."""

    def __init__(self, hata_sayisi: int = 0) -> None:
        self.hata_sayisi = hata_sayisi

    def isle(self, kare, zaman_s, tespitci, kkd):
        if self.hata_sayisi:
            self.hata_sayisi -= 1
            raise RuntimeError("çıkarım hatası")
        return [], []

    def gecisleri_al(self):
        return []

    def olaylari_birak(self, sebep):
        return []


@pytest.fixture
def analiz_ortami(test_ayarlari, monkeypatch):
    # Saat dilimi sabit: test saat başına denk gelirse iki satır oluşmasın
    monkeypatch.setattr(zaman, "simdi_utc", lambda: "2026-09-23T10:15:00+00:00")
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO cameras (id, name, area, source_type, source_url, enabled, sample_fps, "
        "created_at, updated_at) VALUES (1, 'Rampa', 'Sevkiyat', 'rtsp', 'rtsp://a/1', 0, 6, ?, ?)",
        (simdi, simdi),
    )
    baglanti.commit()

    def kur(**ek):
        supervizor = AnalizSupervizoru(dataclasses.replace(test_ayarlari, **ek))
        supervizor.tespitci = object()  # "model yüklü"
        supervizor._kamera_konfig = {1: {"id": 1, "name": "Rampa", "sample_fps": 6}}
        supervizor._kaynaklar = {1: _Kaynak()}
        supervizor._hatlar = {1: _Hat()}
        return supervizor

    try:
        yield kur, baglanti
    finally:
        baglanti.close()


def _olaylar(baglanti, kod: str) -> list[dict]:
    """Olay satırları; sistem olayının mesajı `mesaj` anahtarında."""
    return [
        {**dict(satir), "mesaj": json.loads(satir["details"])["mesaj"]}
        for satir in baglanti.execute(
            "SELECT * FROM events WHERE event_code = ? ORDER BY id", (kod,)
        )
    ]


def _isle(supervizor, baglanti, adim: int, baslangic: float = 0.0, aralik: float = 1.0):
    for i in range(adim):
        supervizor._siradaki_ornek[1] = 0.0
        supervizor._kameralari_isle(baglanti, baslangic + i * aralik)


def test_ust_uste_isleme_hatasi_hatti_yeniden_kurar(analiz_ortami):
    kur, baglanti = analiz_ortami
    supervizor = kur(analiz_hata_esigi=3)
    eski_hat = _Hat(hata_sayisi=5)
    supervizor._hatlar[1] = eski_hat

    _isle(supervizor, baglanti, 2)
    assert supervizor._hatlar[1] is eski_hat and _olaylar(baglanti, "ANALYSIS_DEGRADED") == []
    _isle(supervizor, baglanti, 1, baslangic=2.0)

    assert supervizor._hatlar[1] is not eski_hat, "hat yeniden kurulmalı"
    (olay,) = _olaylar(baglanti, "ANALYSIS_DEGRADED")
    assert "3 görüntü üst üste işlenemedi" in olay["mesaj"]
    assert olay["camera_id"] == 1


def test_basarili_kare_hata_sayacini_sifirlar(analiz_ortami):
    kur, baglanti = analiz_ortami
    supervizor = kur(analiz_hata_esigi=3)
    supervizor._hatlar[1] = hat = _Hat(hata_sayisi=2)
    _isle(supervizor, baglanti, 3)  # 2 hata + 1 başarı
    hat.hata_sayisi = 2
    _isle(supervizor, baglanti, 2, baslangic=3.0)
    assert _olaylar(baglanti, "ANALYSIS_DEGRADED") == [], "sayaç başarıyla sıfırlanmalıydı"


def test_yavas_analiz_bir_kez_bildirilir_ve_duzelince_yeniden_kurulur(analiz_ortami):
    kur, baglanti = analiz_ortami
    supervizor = kur(analiz_yavas_sure_sn=60.0)
    olcum = supervizor._olcumler[1] = _KameraOlcumu()

    def saniyede_bir(simdi):
        olcum.islenen.clear()
        olcum.islenen.extend(simdi - k for k in range(9, -1, -1))  # 1 fps

    for simdi in (100.0, 130.0, 159.0):
        saniyede_bir(simdi)
        supervizor._analiz_hizini_denetle(baglanti, simdi)
    assert _olaylar(baglanti, "ANALYSIS_DEGRADED") == [], "60 sn dolmadı"
    for simdi in (160.0, 200.0):
        saniyede_bir(simdi)
        supervizor._analiz_hizini_denetle(baglanti, simdi)
    (olay,) = _olaylar(baglanti, "ANALYSIS_DEGRADED")
    assert "saniyede 1,0 görüntü işleniyor, hedef 6,0" in olay["mesaj"]

    # Hız düzelir, sonra yeniden düşer: 60 sn sonra ikinci olay
    olcum.islenen.clear()
    olcum.islenen.extend(210.0 - k / 6 for k in range(59, -1, -1))  # 6 fps
    supervizor._analiz_hizini_denetle(baglanti, 210.0)
    for simdi in (220.0, 281.0):
        saniyede_bir(simdi)
        supervizor._analiz_hizini_denetle(baglanti, simdi)
    assert len(_olaylar(baglanti, "ANALYSIS_DEGRADED")) == 2


def test_yavas_kamera_analiz_yavasligi_sayilmaz(analiz_ortami):
    """Saniyede 3 kare veren kameradan 6 kare işlenemez: hedef 3'tür."""
    kur, baglanti = analiz_ortami
    supervizor = kur()
    supervizor._kaynaklar[1] = _Kaynak(fps=3.0)
    olcum = supervizor._olcumler[1] = _KameraOlcumu()
    for simdi in (100.0, 200.0):
        olcum.islenen.clear()
        olcum.islenen.extend(simdi - k / 2.9 for k in range(28, -1, -1))  # ~2.9 fps
        supervizor._analiz_hizini_denetle(baglanti, simdi)
    assert _olaylar(baglanti, "ANALYSIS_DEGRADED") == []


def test_cevrimdisi_kamerada_ve_modelsiz_hiz_olculmez(analiz_ortami):
    kur, baglanti = analiz_ortami
    supervizor = kur()
    supervizor._kaynaklar[1] = _Kaynak(durum=DURUM_OFFLINE)
    for simdi in (100.0, 200.0):
        supervizor._analiz_hizini_denetle(baglanti, simdi)
    supervizor._kaynaklar[1] = _Kaynak()
    supervizor.tespitci = None
    for simdi in (300.0, 400.0):
        supervizor._analiz_hizini_denetle(baglanti, simdi)
    assert _olaylar(baglanti, "ANALYSIS_DEGRADED") == []


# ------------------------------------------------------------------ analysis_hours


def _saat_satirlari(baglanti) -> list[dict]:
    return [dict(s) for s in baglanti.execute("SELECT * FROM analysis_hours ORDER BY hour_utc")]


def test_analiz_saati_islenen_kareler_arasi_sureyi_toplar(analiz_ortami):
    kur, baglanti = analiz_ortami
    supervizor = kur()
    _isle(supervizor, baglanti, 4, aralik=0.5)  # 3 aralık × 0,5 sn
    supervizor._analiz_saatlerini_yaz(baglanti)
    (satir,) = _saat_satirlari(baglanti)
    assert (satir["camera_id"], satir["hour_utc"]) == (1, "2026-09-23T10")
    assert (satir["analyzed_s"], satir["frames_processed"], satir["frames_failed"]) == (1.5, 4, 0)

    # Uzun boşluk (kopukluk) analiz sayılmaz; yazımlar birikir (upsert)
    _isle(supervizor, baglanti, 1, baslangic=60.0)
    supervizor._hatlar[1] = _Hat(hata_sayisi=1)
    _isle(supervizor, baglanti, 1, baslangic=60.5)
    supervizor._analiz_saatlerini_yaz(baglanti)
    (satir,) = _saat_satirlari(baglanti)
    assert (satir["analyzed_s"], satir["frames_processed"], satir["frames_failed"]) == (1.5, 5, 1)


def test_model_yokken_islenen_kare_analiz_sayilmaz(analiz_ortami):
    kur, baglanti = analiz_ortami
    supervizor = kur()
    supervizor.tespitci = None
    _isle(supervizor, baglanti, 4)
    supervizor._analiz_saatlerini_yaz(baglanti)
    (satir,) = _saat_satirlari(baglanti)
    assert (satir["analyzed_s"], satir["frames_processed"]) == (0.0, 0)


def test_yazilamayan_analiz_saati_kaybolmaz(analiz_ortami, test_ayarlari):
    kur, baglanti = analiz_ortami
    supervizor = kur()
    _isle(supervizor, baglanti, 3)
    kapali = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    kapali.close()
    supervizor._analiz_saatlerini_yaz(kapali)  # hata: birikim geri konur
    supervizor._analiz_saatlerini_yaz(baglanti)
    (satir,) = _saat_satirlari(baglanti)
    assert (satir["analyzed_s"], satir["frames_processed"]) == (2.0, 3)

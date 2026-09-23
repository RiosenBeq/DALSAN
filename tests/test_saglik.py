"""/saglik genişler (docs/17 §9.1; Faz 2d-3).

- Her durumda 200 ve `durum: "calisiyor"` (Kontrol Paneli'nin sözleşmesi);
  yalnız `?hazirlik=1` hazır olmayan sistemde 503.
- Kimliksiz gövde dar: kamera ölçümleri, disk ve tur yaşı yalnız `?ayrinti=1`
  ve geçerli oturumla.
- `hazir`'ı yalnız hizmet arızaları bozar; yapılandırma eksiği (kalibrasyon
  bekleyen kural) listede görünür ama Docker'ı "unhealthy" yapmaz.
- Komuta → Sağlık okunan ve işlenen hızı ayrı gösterir (R12).
"""

from __future__ import annotations

import dataclasses
import time

import pytest
from fastapi.testclient import TestClient

from app import veritabani, zaman
from app.analiz.kamera import DURUM_ONLINE
from app.analiz.supervizor import AnalizSupervizoru, _KameraOlcumu
from app.uygulama import uygulama_olustur

DAR_ALANLAR = {"durum", "analiz", "model", "hazir", "sorunlar"}
AYRINTI_ALANLARI = {"kameralar", "bos_disk_gb", "analiz_tur_yasi_sn"}


class _HazirAnaliz:
    """/saglik'in süpervizörden okuduklarının sahtesi."""

    def __init__(self, model: str = "hazir", sorunlar: tuple[str, ...] = ()) -> None:
        self.model_durumu = model
        self._sorunlar = list(sorunlar)

    def sorunlar(self) -> list[str]:
        return list(self._sorunlar)

    def analiz_tur_yasi(self) -> float:
        return 0.1

    def kamera_saglik_ozeti(self) -> list[dict]:
        return [
            {
                "id": 1,
                "durum": "online",
                "okunan_fps": 6.0,
                "islenen_fps": 5.9,
                "hedef_fps": 6.0,
                "yavas": False,
                "isle_p50_ms": 80.0,
                "isle_p90_ms": 130.0,
                "son_kare_yasi_sn": 0.2,
            }
        ]


@pytest.fixture
def supervizorlu(istemci):
    def kur(analiz):
        istemci.app.state.supervizor = analiz
        return istemci

    yield kur
    istemci.app.state.supervizor = None


def test_analizsiz_sistem_calisiyor_ama_hazir_degil(istemci):
    yanit = istemci.get("/saglik")
    assert yanit.status_code == 200
    govde = yanit.json()
    assert set(govde) == DAR_ALANLAR
    assert (govde["durum"], govde["analiz"], govde["hazir"]) == ("calisiyor", False, False)


def test_hazirlik_sorgusu_hazir_degilse_503(istemci):
    yanit = istemci.get("/saglik?hazirlik=1")
    assert yanit.status_code == 503
    assert yanit.json()["durum"] == "calisiyor", "gövde yine aynı sözleşmeyle döner"


def test_hazir_sistem(supervizorlu):
    istemci = supervizorlu(_HazirAnaliz())
    govde = istemci.get("/saglik").json()
    assert (govde["hazir"], govde["sorunlar"]) == (True, [])
    assert istemci.get("/saglik?hazirlik=1").status_code == 200


@pytest.mark.parametrize(
    "sorun", ["analiz_takildi", "analiz_olu", "model_yuklenemedi", "olay_yazilamadi"]
)
def test_hizmet_arizasi_hazirligi_bozar(supervizorlu, sorun):
    istemci = supervizorlu(_HazirAnaliz(sorunlar=(sorun,)))
    yanit = istemci.get("/saglik")
    assert yanit.status_code == 200 and yanit.json()["hazir"] is False
    assert istemci.get("/saglik?hazirlik=1").status_code == 503


def test_yapilandirma_eksigi_hazirligi_bozmaz(supervizorlu):
    istemci = supervizorlu(_HazirAnaliz(sorunlar=("ort_paket_cakismasi",)))
    govde = istemci.get("/saglik").json()
    assert govde["hazir"] is True and govde["sorunlar"] == ["ort_paket_cakismasi"]


def test_model_hazir_degilken_hazir_degil(supervizorlu):
    istemci = supervizorlu(_HazirAnaliz(model="yukleniyor"))
    assert istemci.get("/saglik").json()["hazir"] is False


def test_sifresiz_sistemde_ayrinti_oturumsuz_gelir(supervizorlu):
    istemci = supervizorlu(_HazirAnaliz())
    govde = istemci.get("/saglik?ayrinti=1").json()
    assert set(govde) == DAR_ALANLAR | AYRINTI_ALANLARI
    (kamera,) = govde["kameralar"]
    assert (kamera["islenen_fps"], kamera["isle_p90_ms"]) == (5.9, 130.0)
    assert "ad" not in kamera and "name" not in kamera, "kamera adı verilmez"
    assert isinstance(govde["bos_disk_gb"], float)


def test_sifreli_sistemde_ayrinti_oturum_ister(test_ayarlari):
    sifre = "dalsan2026"
    uygulama = uygulama_olustur(
        dataclasses.replace(test_ayarlari, yonetici_sifresi=sifre), analiz=False
    )
    with TestClient(uygulama) as istemci:
        uygulama.state.supervizor = _HazirAnaliz()
        yanit = istemci.get("/saglik?ayrinti=1")
        assert yanit.status_code == 200, "sağlık ucu kimliksiz de cevap verir"
        assert set(yanit.json()) == DAR_ALANLAR, "oturumsuz ayrıntı yok"

        istemci.post("/giris", data={"sifre": sifre, "sonra": "/"}, follow_redirects=False)
        assert AYRINTI_ALANLARI <= set(istemci.get("/saglik?ayrinti=1").json())
        uygulama.state.supervizor = None


def test_veritabani_okunamazsa_hazir_degil(supervizorlu, test_ayarlari):
    istemci = supervizorlu(_HazirAnaliz())
    istemci.app.state.ayarlar = dataclasses.replace(
        test_ayarlari, veritabani_yolu=test_ayarlari.kok_dizin / "yok" / "yok" / "dalsan.db"
    )
    try:
        govde = istemci.get("/saglik").json()
    finally:
        istemci.app.state.ayarlar = test_ayarlari
    assert govde["durum"] == "calisiyor"
    assert "veritabani_acilamadi" in govde["sorunlar"] and govde["hazir"] is False


def test_ayrinti_toplanamazsa_saglik_yine_200(supervizorlu):
    class _Bozuk(_HazirAnaliz):
        def kamera_saglik_ozeti(self):
            raise RuntimeError("beklenmeyen")

    istemci = supervizorlu(_Bozuk())
    yanit = istemci.get("/saglik?ayrinti=1")
    assert yanit.status_code == 200 and yanit.json()["kameralar"] == []


# ------------------------------------------------------------------ gerçek süpervizör


class _Kaynak:
    olculen_fps = 6.0

    def durum(self, simdi=None) -> str:
        return DURUM_ONLINE

    def son_kare(self):
        return None, 1.0  # kare zamanı: yaş = monotonic − 1


def test_supervizor_sorunlari_ve_kamera_ozeti(test_ayarlari):
    supervizor = AnalizSupervizoru(test_ayarlari)
    supervizor.model_durumu = "hata"
    assert supervizor.sorunlar() == ["model_yuklenemedi"]
    supervizor.model_durumu = "hazir"

    class _Tespitci:
        ort_paket_cakismasi = True

    supervizor.tespitci = _Tespitci()
    assert supervizor.sorunlar() == ["ort_paket_cakismasi"]

    supervizor._kaynaklar = {1: _Kaynak()}
    supervizor._kamera_konfig = {1: {"id": 1, "sample_fps": 6}}
    olcum = supervizor._olcumler[1] = _KameraOlcumu()
    simdi = time.monotonic()
    olcum.islenen.extend(simdi - k for k in range(9, -1, -1))  # 1 fps
    olcum.isle_ms.extend([50.0, 80.0, 90.0, 100.0, 200.0])
    (kamera,) = supervizor.kamera_saglik_ozeti()
    assert kamera["id"] == 1 and kamera["okunan_fps"] == 6.0
    assert kamera["islenen_fps"] == pytest.approx(1.0, abs=0.1)
    assert (kamera["isle_p50_ms"], kamera["isle_p90_ms"]) == (90.0, 200.0)
    assert kamera["hedef_fps"] == 6.0 and kamera["yavas"] is True
    assert kamera["son_kare_yasi_sn"] > 0
    assert supervizor.analiz_tur_yasi() is None  # döngü hiç başlamadı


# ------------------------------------------------------------------ Komuta → Sağlık


def _kamera(istemci, test_ayarlari) -> int:
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "Rampa", "source_type": "file", "source_url": str(video), "sample_fps": "6"},
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        baglanti.execute(
            "UPDATE cameras SET status = 'online', measured_fps = 6.0, last_frame_at = ? "
            "WHERE id = ?",
            (zaman.simdi_utc(), kamera_id),
        )
        baglanti.commit()
    finally:
        baglanti.close()
    return kamera_id


def test_saglik_ekrani_okunan_ve_islenen_hizi_ayri_gosterir(supervizorlu, test_ayarlari):
    istemci = supervizorlu(None)
    _kamera(istemci, test_ayarlari)
    metin = istemci.get("/komuta/saglik").text
    assert "Okunan fps" in metin and "İşlenen fps" in metin
    assert 'title="analiz çalışmıyor"' in metin, "analiz yokken işlenen hız uydurulmaz"

    class _Yavas(_HazirAnaliz):
        def kamera_saglik_ozeti(self):
            ozet = super().kamera_saglik_ozeti()
            ozet[0].update(islenen_fps=1.2, yavas=True)
            return ozet

    istemci.app.state.supervizor = _Yavas()
    metin = istemci.get("/komuta/saglik").text
    assert "islenen-dusuk" in metin and "1,2" in metin
    assert "bir kareyi işleme (p90): 130 ms" in metin
    assert "analiz yetişemiyor" in metin

"""KKD anons kapısı ve gölge karnesi (docs/17 §5.7, §13 3e; S33).

Kapı, kalem ve model sürümü başına dört şartın dördü de sağlanınca açılır:
precision ≥ KKD_KAPI_PRECISION, ilk olaydan bu yana ≥ KKD_KAPI_GUN gün,
≥ KKD_KAPI_EN_AZ_OLAY incelenmiş olay, incelenmemiş olay yok. Tasarımın
kabul ölçütleri: precision 0,89'da kapı kapalı; 1 doğru olay (%100) ama N az →
kapalı; incelenmemiş olay varken kapalı; model sürümü değişince sayaç sıfırlanır.
Kapı sunucuda denetlenir; açık onayla aşılırsa PPE_GATE_OVERRIDDEN yazılır.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app import veritabani, zaman
from app.web import kkd_karnesi
from app.web.kkd_karnesi import KalemSayaci, KapiEsikleri, kapi_eksikleri, karne_hesapla, sartlar

ESIK = KapiEsikleri(precision=0.90, gun=3, en_az_olay=30)
ILK = "2026-09-01T08:00:00+00:00"
DORT_GUN_SONRA = "2026-09-05T08:00:00+00:00"


def _eksikler(sayac: KalemSayaci, esik: KapiEsikleri = ESIK, simdi: str = DORT_GUN_SONRA):
    return [s.eksik for s in sartlar(sayac, esik, simdi) if not s.tamam]


# ------------------------------------------------------------------ şartlar


def test_dort_sart_saglaninca_kapi_acik():
    # 27/30 tam 0,90: kayan noktada eşiğin altına düşmemeli (kesirle karşılaştırılır)
    assert _eksikler(KalemSayaci(olay=30, dogru=27, yanlis=3, ilk_olay_utc=ILK)) == []


def test_precision_089_kapi_kapali():
    eksikler = _eksikler(KalemSayaci(olay=100, dogru=89, yanlis=11, ilk_olay_utc=ILK))
    assert eksikler == ["precision 0,89 (en az 0,90)"]


def test_tek_dogru_olay_yuzde_yuz_ama_az_kapi_kapali():
    """S33: tek incelenmiş olayla precision %100 çıkar ve kapı açılırdı."""
    sayac = KalemSayaci(olay=1, dogru=1, yanlis=0, ilk_olay_utc=ILK)
    assert kkd_karnesi.precision_metni(sayac) == "1,00"
    assert _eksikler(sayac) == ["1 incelenmiş olay (en az 30)"]


def test_incelenmemis_olay_varken_kapi_kapali():
    """Seçilerek incelenen olaylardan hesaplanan oran şişebilir (docs/04 §8.2)."""
    eksikler = _eksikler(KalemSayaci(olay=41, dogru=40, yanlis=0, ilk_olay_utc=ILK))
    assert eksikler == ["1 olay incelenmedi"]


@pytest.mark.parametrize(
    ("simdi", "acik"),
    [("2026-09-04T07:00:00+00:00", False), ("2026-09-04T08:00:00+00:00", True)],
)
def test_gun_sarti_ilk_olaydan_sayilir(simdi, acik):
    eksikler = _eksikler(KalemSayaci(olay=30, dogru=30, yanlis=0, ilk_olay_utc=ILK), simdi=simdi)
    assert (eksikler == []) is acik
    if not acik:
        assert eksikler == ["ilk olaydan bu yana 2 gün 23 sa (en az 3 gün)"]


def test_esikler_ayarlardan_gelir():
    sayac = KalemSayaci(olay=1, dogru=1, yanlis=0, ilk_olay_utc=ILK)
    assert _eksikler(sayac, KapiEsikleri(precision=0.95, gun=1, en_az_olay=1)) == []


@pytest.mark.parametrize(
    ("dogru", "incelenen", "beklenen"),
    [(26, 29, "0,89"), (899, 1000, "0,89"), (9, 10, "0,90"), (0, 5, "0,00")],
)
def test_precision_asagi_yuvarlanir(dogru, incelenen, beklenen):
    """0,899 "0,90" görünüp kapalı kapıyı açık sandırmamalı."""
    sayac = KalemSayaci(olay=incelenen, dogru=dogru, yanlis=incelenen - dogru)
    assert kkd_karnesi.precision_metni(sayac) == beklenen


def test_olculmeyen_sayi_yazilmaz():
    """docs/17 §5.9: ölçülmeyen metrik ekrana yazılmaz, "ölçülecek" yazar."""
    sayac = KalemSayaci(olay=5)
    assert kkd_karnesi.precision_metni(sayac) == "ölçülecek"
    assert kkd_karnesi.kapsama_metni(sayac) == "%0"
    assert kkd_karnesi.kapsama_metni(KalemSayaci()) == "-"
    assert kkd_karnesi.kapsama_metni(KalemSayaci(olay=300, dogru=299)) == "%99"


# ------------------------------------------------------------------ olaylardan sayaç


def _baglanti(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    return baglanti


def _kkd_olaylari(
    baglanti,
    kod: str,
    adet: int,
    durum: str = "reviewed",
    surum: str | None = "kkd-test",
    an: str | None = None,
) -> None:
    ppe = {"required": ["helmet", "vest"], "dwell_s": 4.0}
    if surum is not None:
        ppe["model_version"] = surum
    kalem = kkd_karnesi.KOD_KALEMLERI.get(kod, "helmet")
    for _ in range(adet):
        baglanti.execute(
            "INSERT INTO events (occurred_at, event_type, details, status, event_code, severity) "
            "VALUES (?, 'violation', ?, ?, ?, 'high')",
            (
                an or zaman.gun_once_utc(4),
                json.dumps({"ppe": ppe, "eksik_kkd": [kalem]}),
                durum,
                kod,
            ),
        )
    baglanti.commit()


def test_model_surumu_degisince_sayac_sifirlanir(test_ayarlari):
    baglanti = _baglanti(test_ayarlari)
    try:
        for kod in ("PPE_NO_HELMET", "PPE_NO_VEST"):
            _kkd_olaylari(baglanti, kod, 30, surum="kkd-eski")
        eski = karne_hesapla(baglanti, test_ayarlari, "kkd-eski")
        assert kapi_eksikleri(eski, ["helmet", "vest"]) == []

        yeni = karne_hesapla(baglanti, test_ayarlari, "kkd-yeni")
        assert yeni["baska_surum_olay"] == 60
        assert yeni["kalemler"]["helmet"]["sayac"] == KalemSayaci()
        assert kapi_eksikleri(yeni, ["helmet"]) == [f"Baret: {kkd_karnesi.HENUZ_OLAY_YOK}"]
        baret = yeni["kalemler"]["helmet"]
        assert (baret["precision"], baret["aciklama"]) == (
            "ölçülecek",
            "bu model sürümüyle henüz olay yok",
        )
    finally:
        baglanti.close()


def test_kalemler_ayri_sayilir(test_ayarlari):
    baglanti = _baglanti(test_ayarlari)
    try:
        _kkd_olaylari(baglanti, "PPE_NO_HELMET", 30)
        _kkd_olaylari(baglanti, "PPE_NO_VEST", 25)
        _kkd_olaylari(baglanti, "PPE_NO_VEST", 5, durum="false_alarm")
        _kkd_olaylari(baglanti, "PPE_NO_VEST", 2, durum="new")
        karne = karne_hesapla(baglanti, test_ayarlari, "kkd-test")
        assert kapi_eksikleri(karne, ["helmet"]) == []
        assert kapi_eksikleri(karne, ["helmet", "vest"]) == [
            "Yelek: precision 0,83 (en az 0,90)",
            "Yelek: 2 olay incelenmedi",
        ]
        # Ekrandaki cümle kalem başına toplu; ayırıcı ondalık virgülüyle karışmaz
        assert kkd_karnesi.kapi_ozeti(karne, ["helmet", "vest"]) == (
            "Yelek: precision 0,83 (en az 0,90) · 2 olay incelenmedi"
        )
        yelek = karne["kalemler"]["vest"]
        assert yelek["sayac"] == KalemSayaci(
            olay=32, dogru=25, yanlis=5, ilk_olay_utc=yelek["sayac"].ilk_olay_utc
        )
        assert (yelek["precision"], yelek["aciklama"], yelek["model"]) == (
            "0,83",
            "30 incelenmiş olay, kapsama %93",
            "kkd-test",
        )
    finally:
        baglanti.close()


def test_baska_olaylar_sayilmaz(test_ayarlari):
    baglanti = _baglanti(test_ayarlari)
    try:
        _kkd_olaylari(baglanti, "RESTRICTED_ENTRY", 3)  # KKD olayı değil
        _kkd_olaylari(baglanti, "PPE_NO_HELMET", 2, surum=None)  # sürümsüz: başka sürüm
        baglanti.execute(
            "INSERT INTO events (occurred_at, event_type, details, status, event_code, severity) "
            "VALUES (?, 'system', '{}', 'new', 'PPE_MODEL_CHANGED', 'system')",
            (zaman.simdi_utc(),),
        )
        baglanti.commit()
        karne = karne_hesapla(baglanti, test_ayarlari, "kkd-test")
        assert all(k["sayac"].olay == 0 for k in karne["kalemler"].values())
        assert karne["baska_surum_olay"] == 2
    finally:
        baglanti.close()


def test_model_yokken_kapi_kapali(test_ayarlari):
    baglanti = _baglanti(test_ayarlari)
    try:
        karne = karne_hesapla(baglanti, test_ayarlari, "")
        assert karne["kalemler"] == {}
        assert kapi_eksikleri(karne, ["helmet"]) == [kkd_karnesi.MODEL_YOK]
    finally:
        baglanti.close()


# ------------------------------------------------------------------ web: kapı sunucuda


@pytest.fixture
def yuklu_model(istemci):
    istemci.app.state.supervizor = SimpleNamespace(
        kkd=SimpleNamespace(model_var=True, model_surumu="kkd-test", kart={}), kkd_hatasi=None
    )
    try:
        yield
    finally:
        istemci.app.state.supervizor = None


def _duz(html: str) -> str:
    """Ekranda okunan metin: etiketler atılır, boşluklar teke iner."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


def _satirlar(test_ayarlari, sorgu: str, parametreler: tuple = ()) -> list[dict]:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return [dict(s) for s in baglanti.execute(sorgu, parametreler)]
    finally:
        baglanti.close()


def _kkd_kurali(istemci, test_ayarlari) -> int:
    """KKD bölgesi + hazır KKD kuralı (gölgede doğar); kural id'si."""
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "Saha", "source_type": "file", "source_url": str(video), "sample_fps": "6"},
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": "KKD alanı",
            "zone_type": "ppe_required",
            "polygon": "[[0.25,0.25],[0.75,0.25],[0.75,0.75],[0.25,0.75]]",
        },
        follow_redirects=False,
    )
    bolge_id = _satirlar(test_ayarlari, "SELECT MAX(id) AS m FROM zones")[0]["m"]
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    return _satirlar(test_ayarlari, "SELECT MAX(id) AS m FROM rules")[0]["m"]


def _kapiyi_gecir(test_ayarlari) -> None:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        for kod in ("PPE_NO_HELMET", "PPE_NO_VEST"):
            _kkd_olaylari(baglanti, kod, 30)
    finally:
        baglanti.close()


def _anonsu_ac(istemci, kural_id: int, **ek):
    return istemci.post(
        "/komuta/uyari/golge",
        data={"golge": "0", "kural_idler": [str(kural_id)], **ek},
        follow_redirects=False,
    )


def _kural(test_ayarlari, kural_id: int) -> dict:
    return _satirlar(
        test_ayarlari,
        "SELECT shadow_mode, approved_model_version FROM rules WHERE id = ?",
        (kural_id,),
    )[0]


def _asilma_olaylari(test_ayarlari) -> list[dict]:
    return [
        json.loads(s["details"])
        for s in _satirlar(
            test_ayarlari, "SELECT details FROM events WHERE event_code = 'PPE_GATE_OVERRIDDEN'"
        )
    ]


def test_kapi_kapaliyken_anons_onaysiz_acilmaz(istemci, test_ayarlari, yuklu_model):
    kural_id = _kkd_kurali(istemci, test_ayarlari)
    yanit = _anonsu_ac(istemci, kural_id)
    assert yanit.status_code == 400
    assert "kapının şartları sağlanmadı" in yanit.json()["hata"]
    assert "Baret: bu model sürümüyle henüz olay yok" in yanit.json()["hata"]
    assert _kural(test_ayarlari, kural_id) == {"shadow_mode": 1, "approved_model_version": None}
    assert _asilma_olaylari(test_ayarlari) == []


def test_olculmeden_acmak_sistem_olayi_yazar(istemci, test_ayarlari, yuklu_model):
    kural_id = _kkd_kurali(istemci, test_ayarlari)
    assert _anonsu_ac(istemci, kural_id, olcmeden="1").status_code == 303
    assert _kural(test_ayarlari, kural_id) == {
        "shadow_mode": 0,
        "approved_model_version": "kkd-test",
    }
    (olay,) = _asilma_olaylari(test_ayarlari)
    assert olay["kural_idler"] == [kural_id]
    assert olay["model_version"] == "kkd-test"
    assert olay["eksik_sartlar"] == [
        "Baret: bu model sürümüyle henüz olay yok",
        "Yelek: bu model sürümüyle henüz olay yok",
    ]
    assert olay["mesaj"].startswith("KKD anonsu ölçülmeden açıldı")


def test_kapi_acikken_onay_gerekmez_ve_olay_yazilmaz(istemci, test_ayarlari, yuklu_model):
    kural_id = _kkd_kurali(istemci, test_ayarlari)
    _kapiyi_gecir(test_ayarlari)
    assert _anonsu_ac(istemci, kural_id).status_code == 303
    assert _kural(test_ayarlari, kural_id) == {
        "shadow_mode": 0,
        "approved_model_version": "kkd-test",
    }
    assert _asilma_olaylari(test_ayarlari) == []


def test_golgeye_almak_kapiya_takilmaz(istemci, test_ayarlari, yuklu_model):
    kural_id = _kkd_kurali(istemci, test_ayarlari)
    _anonsu_ac(istemci, kural_id, olcmeden="1")
    yanit = istemci.post(
        "/komuta/uyari/golge",
        data={"golge": "1", "kural_idler": [str(kural_id)]},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert _kural(test_ayarlari, kural_id)["shadow_mode"] == 1


# ------------------------------------------------------------------ web: ekranlar


def test_uyari_zinciri_kapali_kapiyi_ve_eksik_sartlari_gosterir(
    istemci, test_ayarlari, yuklu_model
):
    _kkd_kurali(istemci, test_ayarlari)
    metin = istemci.get("/komuta/uyari").text
    duz = _duz(metin)
    assert "Precision: ölçülecek (bu model sürümüyle henüz olay yok, model kkd-test)" in duz
    assert (
        "Anons kapısı kapalı. Baret: bu model sürümüyle henüz olay yok; "
        "Yelek: bu model sürümüyle henüz olay yok." in duz
    )
    assert 'name="olcmeden"' in metin and "Ölçülmeden açıyorum" in metin
    assert "kapi-kapali" in metin
    # Gölge mod panelindeki kapı cümlesi eşikleri ayarlardan yazar
    assert "precision en az 0,90, en az 3 gün, en az 30 incelenmiş olay" in duz


def test_uyari_zinciri_acik_kapida_onay_istemez(istemci, test_ayarlari, yuklu_model):
    _kkd_kurali(istemci, test_ayarlari)
    _kapiyi_gecir(test_ayarlari)
    metin = istemci.get("/komuta/uyari").text
    assert "Precision: 1,00 (30 incelenmiş olay, kapsama %100, model kkd-test)" in _duz(metin)
    assert "Anons kapısı açık" in metin
    assert 'name="olcmeden"' not in metin and "kapi-kapali" not in metin


def test_model_yokken_zincir_olculecek_yazar(istemci, test_ayarlari):
    _kkd_kurali(istemci, test_ayarlari)
    metin = istemci.get("/komuta/uyari").text
    assert "KKD modeli yüklü değil: precision ölçülecek." in metin
    assert kkd_karnesi.MODEL_YOK in metin


def test_kkd_sayfasinda_karne(istemci, test_ayarlari, yuklu_model):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        _kkd_olaylari(baglanti, "PPE_NO_HELMET", 28)
        _kkd_olaylari(baglanti, "PPE_NO_HELMET", 2, durum="false_alarm")
        _kkd_olaylari(baglanti, "PPE_NO_VEST", 4, surum="kkd-eski")
    finally:
        baglanti.close()
    metin = istemci.get("/kkd").text
    assert 'id="golge-karnesi"' in metin
    assert "Precision: 0,93 (30 incelenmiş olay, kapsama %100, model kkd-test)" in _duz(metin)
    assert "kapı açık" in metin  # baret: 28/30, 4 gün, 30 olay, bekleyen yok
    assert "kapı kapalı" in metin  # yelek: bu sürümle olay yok
    assert "Başka model sürümlerinin 4 KKD olayı" in metin


def test_kkd_sayfasi_model_yokken_karne_bos(istemci):
    metin = istemci.get("/kkd").text
    assert "Model yüklü değil: karne" in metin

"""KKD kuralının gölgesi ve onaylı model sürümü (docs/17 §5.7; Faz 3d).

- KKD kuralı gölgede doğar: hazır kural da formdan kurulan da. Form anonsu
  AÇAMAZ; anonsu Komuta → Uyarı zinciri açar ve yüklü model sürümünü onaylı
  olarak yazar.
- Onaylı sürüm yüklü modelden farklıysa (ya da hiç yoksa) süpervizör kuralı
  gölgeye alır ve PPE_MODEL_CHANGED yazar; kural parametreleri değişmez, bu
  yüzden pencere ve bekleme süreleri sıfırlanmaz.
- Formdaki "boş = kapalı" eşikler boş bırakılınca None olur, önceki değer
  taşınmaz.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import veritabani, zaman
from app.analiz.supervizor import AnalizSupervizoru


def _satirlar(test_ayarlari, sorgu: str, parametreler: tuple = ()) -> list[dict]:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return [dict(s) for s in baglanti.execute(sorgu, parametreler)]
    finally:
        baglanti.close()


def _kamera_ve_kkd_bolgesi(istemci, test_ayarlari) -> tuple[int, int]:
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
    return kamera_id, _satirlar(test_ayarlari, "SELECT MAX(id) AS m FROM zones")[0]["m"]


def _kkd_formu(kamera_id: int, bolge_id: int, kural_id: int | None = None, **ek) -> dict:
    veri = {
        "camera_id": str(kamera_id),
        "rule_type": "ppe_violation",
        "zone_id": str(bolge_id),
        "required_ppe": ["helmet", "vest"],
        "cooldown_s": "180",
        "enabled": "1",
        "require_full_bbox": "1",
        "surucu_muaf": "1",
        "max_kisi_ortusmesi": "",
        "min_netlik": "",
        **ek,
    }
    if kural_id:
        veri["kural_id"] = str(kural_id)
    return veri


def _kural(test_ayarlari, kural_id: int) -> dict:
    satir = _satirlar(test_ayarlari, "SELECT * FROM rules WHERE id = ?", (kural_id,))[0]
    satir["params"] = json.loads(satir["params"])
    return satir


# ------------------------------------------------------------------ doğuş


def test_kkd_hazir_kurali_golgede_dogar(istemci, test_ayarlari):
    _, bolge_id = _kamera_ve_kkd_bolgesi(istemci, test_ayarlari)
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    kurallar = _satirlar(test_ayarlari, "SELECT rule_type, shadow_mode FROM rules")
    assert kurallar == [{"rule_type": "ppe_violation", "shadow_mode": 1}]


def test_formdan_kurulan_kkd_kurali_golgede_dogar_ve_form_anonsu_acamaz(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_kkd_bolgesi(istemci, test_ayarlari)
    yanit = istemci.post(
        "/kurallar/kaydet", data=_kkd_formu(kamera_id, bolge_id), follow_redirects=False
    )
    assert yanit.status_code == 303
    kural_id = _satirlar(test_ayarlari, "SELECT MAX(id) AS m FROM rules")[0]["m"]
    assert _kural(test_ayarlari, kural_id)["shadow_mode"] == 1, "gölge kutusu işaretsizdi"
    # Düzenlemede de gölge kutusu işaretsiz gönderilse anons açılmaz
    istemci.post(
        "/kurallar/kaydet", data=_kkd_formu(kamera_id, bolge_id, kural_id), follow_redirects=False
    )
    assert _kural(test_ayarlari, kural_id)["shadow_mode"] == 1


def test_uyari_zincirinden_acilan_kkd_anonsu_formla_kapanmaz(istemci, test_ayarlari):
    """Zincirden açılmış (onaylı) bir KKD kuralını formla düzenlemek, anonsu
    kendiliğinden gölgeye almamalı."""
    kamera_id, bolge_id = _kamera_ve_kkd_bolgesi(istemci, test_ayarlari)
    istemci.post("/kurallar/kaydet", data=_kkd_formu(kamera_id, bolge_id), follow_redirects=False)
    kural_id = _satirlar(test_ayarlari, "SELECT MAX(id) AS m FROM rules")[0]["m"]
    istemci.post(
        "/komuta/uyari/golge",
        data={"golge": "0", "kural_idler": [str(kural_id)]},
        follow_redirects=False,
    )
    istemci.post(
        "/kurallar/kaydet", data=_kkd_formu(kamera_id, bolge_id, kural_id), follow_redirects=False
    )
    assert _kural(test_ayarlari, kural_id)["shadow_mode"] == 0


# ------------------------------------------------------------------ onaylı sürüm


@pytest.mark.parametrize(
    ("supervizor", "beklenen"),
    [
        (SimpleNamespace(kkd=SimpleNamespace(model_var=True, model_surumu="kkd-abc")), "kkd-abc"),
        (SimpleNamespace(kkd=SimpleNamespace(model_var=False, model_surumu="")), None),
        (None, None),
    ],
)
def test_anonsu_acmak_yuklu_surumu_onaylar(istemci, test_ayarlari, supervizor, beklenen):
    kamera_id, bolge_id = _kamera_ve_kkd_bolgesi(istemci, test_ayarlari)
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    kkd_id = _satirlar(test_ayarlari, "SELECT MAX(id) AS m FROM rules")[0]["m"]
    istemci.app.state.supervizor = supervizor
    try:
        istemci.post(
            "/komuta/uyari/golge",
            data={"golge": "0", "kural_idler": [str(kkd_id)]},
            follow_redirects=False,
        )
    finally:
        istemci.app.state.supervizor = None
    kural = _kural(test_ayarlari, kkd_id)
    assert kural["shadow_mode"] == 0
    assert kural["approved_model_version"] == beklenen


# ------------------------------------------------------------------ süpervizör


@pytest.fixture
def supervizor_ve_kurallar(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO cameras (id, name, source_type, source_url, created_at, updated_at) "
        "VALUES (1, 'K1', 'file', 'v.mp4', ?, ?)",
        (simdi, simdi),
    )
    # (id, tip, gölge, onaylı sürüm)
    for kural_id, tip, golge, onayli in (
        (1, "ppe_violation", 0, "kkd-eski"),  # model değişti → gölgeye
        (2, "ppe_violation", 0, "kkd-yeni"),  # onaylı sürüm yüklü → dokunulmaz
        (3, "ppe_violation", 1, None),  # zaten gölgede → dokunulmaz
        (4, "zone_intrusion", 0, None),  # KKD değil → dokunulmaz
        (5, "ppe_violation", 0, None),  # hiç onaylanmamış → gölgeye
    ):
        baglanti.execute(
            "INSERT INTO rules (id, camera_id, rule_type, zone_id, target_classes, params, "
            "cooldown_s, enabled, shadow_mode, approved_model_version, updated_at) "
            "VALUES (?, 1, ?, NULL, '[\"person\"]', '{\"min_dwell_s\": 3.0}', 180, 1, ?, ?, ?)",
            (kural_id, tip, golge, onayli, simdi),
        )
    baglanti.commit()
    supervizor = AnalizSupervizoru(test_ayarlari)
    supervizor._kural_haritasi = {i: {"shadow_mode": 0} for i in range(1, 6)}
    try:
        yield supervizor, baglanti
    finally:
        baglanti.close()


def _kurallar(baglanti) -> dict[int, tuple]:
    return {
        s["id"]: (s["shadow_mode"], s["params"])
        for s in baglanti.execute("SELECT id, shadow_mode, params FROM rules")
    }


def test_onaysiz_surumle_calisan_kkd_kurali_golgeye_alinir(supervizor_ve_kurallar):
    supervizor, baglanti = supervizor_ve_kurallar
    supervizor.kkd = SimpleNamespace(model_var=True, model_surumu="kkd-yeni")
    once = _kurallar(baglanti)
    supervizor._kkd_surumunu_denetle(baglanti)
    sonra = _kurallar(baglanti)

    assert {k: v[0] for k, v in sonra.items()} == {1: 1, 2: 0, 3: 1, 4: 0, 5: 1}
    # Parametreler aynı: kural imzası değişmez, pencere ve bekleme sürer
    assert {k: v[1] for k, v in sonra.items()} == {k: v[1] for k, v in once.items()}
    # Bellek haritası da hemen güncel: bir sonraki ihlal beklemeden susar
    assert supervizor._kural_haritasi[1]["shadow_mode"] == 1
    assert supervizor._kural_haritasi[2]["shadow_mode"] == 0

    olaylar = [
        json.loads(s["details"])
        for s in baglanti.execute(
            "SELECT details FROM events WHERE event_code = 'PPE_MODEL_CHANGED' ORDER BY id"
        )
    ]
    assert [o["kural_id"] for o in olaylar] == [1, 5]
    assert "onaylı sürüm kkd-eski" in olaylar[0]["mesaj"]
    assert "hiçbir sürüm onaylanmamış" in olaylar[1]["mesaj"]

    # İkinci denetim yeni olay yazmaz (kurallar zaten gölgede)
    supervizor._kkd_surumunu_denetle(baglanti)
    assert (
        baglanti.execute(
            "SELECT COUNT(*) FROM events WHERE event_code = 'PPE_MODEL_CHANGED'"
        ).fetchone()[0]
        == 2
    )


def test_model_yokken_kurallara_dokunulmaz(supervizor_ve_kurallar):
    supervizor, baglanti = supervizor_ve_kurallar
    once = _kurallar(baglanti)
    supervizor._kkd_surumunu_denetle(baglanti)  # KkdSiniflandirici(None)
    assert _kurallar(baglanti) == once
    assert baglanti.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


# ------------------------------------------------------------------ form eşikleri


def test_bos_kapali_esikler(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_kkd_bolgesi(istemci, test_ayarlari)
    istemci.post(
        "/kurallar/kaydet",
        data=_kkd_formu(kamera_id, bolge_id, min_netlik="25", max_kisi_ortusmesi="0,4"),
        follow_redirects=False,
    )
    kural_id = _satirlar(test_ayarlari, "SELECT MAX(id) AS m FROM rules")[0]["m"]
    params = _kural(test_ayarlari, kural_id)["params"]
    assert params["min_netlik"] == 25 and params["max_kisi_ortusmesi"] == 0.4
    assert params["surucu_muaf"] is True
    # Boş bırakmak KAPATIR: önceki değer taşınmaz
    istemci.post(
        "/kurallar/kaydet",
        data=_kkd_formu(kamera_id, bolge_id, kural_id, surucu_muaf=""),
        follow_redirects=False,
    )
    params = _kural(test_ayarlari, kural_id)["params"]
    assert params["min_netlik"] is None and params["max_kisi_ortusmesi"] is None
    assert params["surucu_muaf"] is False

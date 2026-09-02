"""Yaya yolu kuralı, görüntü kalitesi teşhisi ve renk anahtarı.

Fabrikada çizili yürüyüş yolu vardır ve insanların oradan yürümesi beklenir;
bu kural onun karşılığıdır. Görüntü kalitesi ise sahada tespit isabetini en çok
etkileyen ama en az fark edilen etkendir.
"""

from __future__ import annotations

import json

import cv2
import numpy as np

from app import veritabani
from app.analiz import goruntu


def _kamera_ve_bolge(istemci, test_ayarlari, tip: str, ad: str) -> tuple[int, int]:
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "K1",
            "source_type": "file",
            "source_url": str(video),
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": ad,
            "zone_type": tip,
            "polygon": "[[0.1,0.6],[0.9,0.6],[0.9,0.95],[0.1,0.95]]",
        },
        follow_redirects=False,
    )
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        bolge_id = baglanti.execute("SELECT MAX(id) AS m FROM zones").fetchone()["m"]
    finally:
        baglanti.close()
    return kamera_id, bolge_id


# ---- yaya yolu ----


def test_yaya_yolu_kurali_tek_tikla_kurulur(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(
        istemci, test_ayarlari, "pedestrian_path", "Yürüyüş yolu"
    )
    yanit = istemci.post(
        "/kurallar/yaya-yolu", data={"zone_id": str(bolge_id)}, follow_redirects=False
    )
    assert yanit.status_code == 303
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kural = baglanti.execute("SELECT * FROM rules").fetchone()
    finally:
        baglanti.close()
    assert kural["rule_type"] == "zone_intrusion"
    assert kural["zone_id"] == bolge_id
    assert json.loads(kural["target_classes"]) == ["person"]
    params = json.loads(kural["params"])
    # DIŞARIDA olmak ihlal: yolu kullanmayan kişi uyarı üretir
    assert params["mode"] == "outside"
    assert params["min_dwell_s"] >= 3, "kenara bir adım atan kişi uyarı üretmemeli"
    assert kural["announcement_id"] is not None, "yaya yolu anonsuna bağlanmalı"


def test_yaya_yolu_kurali_yanlis_bolge_tipinde_reddedilir(istemci, test_ayarlari):
    _, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, "loading_area", "Rampa")
    yanit = istemci.post(
        "/kurallar/yaya-yolu", data={"zone_id": str(bolge_id)}, follow_redirects=False
    )
    assert yanit.status_code == 400
    assert "Yaya yolu" in yanit.json()["hata"]


def test_ayni_bolgeye_ikinci_kural_engellenir(istemci, test_ayarlari):
    _, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, "pedestrian_path", "Yol")
    istemci.post("/kurallar/yaya-yolu", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    yanit = istemci.post(
        "/kurallar/yaya-yolu", data={"zone_id": str(bolge_id)}, follow_redirects=False
    )
    assert yanit.status_code == 400
    assert "zaten bir kural var" in yanit.json()["hata"]


def test_yaya_yolu_dugmesi_kamera_sayfasinda_gorunur(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(
        istemci, test_ayarlari, "pedestrian_path", "Yürüyüş yolu"
    )
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "yaya yolu kuralı ekle" in detay
    # Kural kurulunca düğme kaybolmalı
    istemci.post("/kurallar/yaya-yolu", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "yaya yolu kuralı ekle" not in detay


def test_yaya_yolu_disindaki_kisi_ihlal_uretir():
    """Kural motoru tarafı: yolun dışında kalan kişi süre dolunca uyarı üretmeli,
    yolun üstünde yürüyen kişi ASLA uyarı üretmemeli."""
    import sys

    sys.path.insert(0, "tests/rules")
    from yardimci import KARE, kural, tespit

    from app.rules.motor import KuralMotoru
    from app.rules.tipler import Bolge

    # Karenin alt yarısı yaya yolu
    yol = Bolge(
        id=1, tip="pedestrian_path", poligon=[(0.0, 0.6), (1.0, 0.6), (1.0, 1.0), (0.0, 1.0)]
    )
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle([kural("zone_intrusion", params={"mode": "outside", "min_dwell_s": 5.0})])

    def calistir(zaman_s, tespitler):
        return motor.degerlendir(zaman_s, KARE, tespitler, [yol], None)

    # Yolun ÜSTÜNDE yürüyen kişi (ayak y=0.8) → hiç uyarı yok
    icerde = [tespit(ayak=(0.5, 0.8), takip_id=1)]
    assert calistir(0.0, icerde) == []
    assert calistir(10.0, icerde) == []

    # Yolun DIŞINDA duran kişi (ayak y=0.4) → süre dolunca uyarı
    disarda = [tespit(ayak=(0.5, 0.4), takip_id=2)]
    assert calistir(20.0, disarda) == []
    ihlaller = calistir(26.0, disarda)
    assert len(ihlaller) == 1
    assert ihlaller[0].detaylar["mode"] == "outside"
    assert ihlaller[0].takip_idler == [2]


# ---- görüntü kalitesi ----


def test_karanlik_kare_teshis_edilir():
    kare = np.full((240, 320, 3), 20, dtype=np.uint8)
    sonuc = goruntu.kalite_olc(kare)
    assert sonuc["sorun"] == "karanlik"
    assert "karanlık" in sonuc["mesaj"]


def test_bulanik_kare_teshis_edilir():
    kare = np.random.default_rng(7).integers(60, 200, (240, 320, 3), dtype=np.uint8)
    kare = cv2.GaussianBlur(kare, (31, 31), 0)
    sonuc = goruntu.kalite_olc(kare)
    assert sonuc["sorun"] in ("bulanik", "dusuk_kontrast"), sonuc


def test_iyi_kare_uyari_uretmez():
    rng = np.random.default_rng(3)
    kare = rng.integers(30, 225, (240, 320, 3), dtype=np.uint8)
    sonuc = goruntu.kalite_olc(kare)
    assert sonuc["sorun"] == "yok", sonuc
    assert sonuc["mesaj"] == ""


def test_iyilestirme_dusuk_kontrasti_acar():
    """Sisli/düşük kontrastlı doku — CLAHE sonrası yerel kontrast artmalı.

    Gerçek sahne dokusu kullanılır (düz bir rampa DEĞİL): CLAHE yerel çalışır,
    tek yönlü düz geçişte küresel std'yi düşürebilir ve test yanıltıcı olurdu.
    """
    rng = np.random.default_rng(11)
    doku = rng.integers(0, 255, (240, 320), dtype=np.uint8)
    doku = cv2.GaussianBlur(doku, (9, 9), 0)
    # Dar bir aralığa sıkıştır: "sisli kamera" görüntüsü
    sisli = (doku.astype(np.float32) * 0.18 + 105).astype(np.uint8)
    kare = cv2.cvtColor(sisli, cv2.COLOR_GRAY2BGR)

    iyilesmis = goruntu.iyilestir(kare)
    assert iyilesmis.shape == kare.shape
    assert iyilesmis.dtype == kare.dtype
    onceki = cv2.cvtColor(kare, cv2.COLOR_BGR2GRAY).std()
    sonraki = cv2.cvtColor(iyilesmis, cv2.COLOR_BGR2GRAY).std()
    assert sonraki > onceki * 1.5, f"kontrast belirgin artmalı: {onceki:.1f} -> {sonraki:.1f}"


def test_iyilestirme_renkleri_bozmaz():
    """Reflektörlü yeleğin SARISI korunmalı: iyileştirme yalnız parlaklık
    kanalında yapılır, renk kanallarına dokunulmaz."""
    kare = np.zeros((120, 160, 3), dtype=np.uint8)
    kare[:, :] = (40, 200, 230)  # BGR: sarı-turuncu yelek rengi
    iyilesmis = goruntu.iyilestir(kare)
    b, g, r = iyilesmis[60, 80].astype(int)
    assert r > b and g > b, f"sarı ton korunmalı, çıkan: B={b} G={g} R={r}"


def test_bos_kare_cokmez():
    assert goruntu.kalite_olc(np.zeros((0, 0, 3), dtype=np.uint8))["sorun"] == "yok"


# ---- renk anahtarı ----


def test_renk_anahtari_kamera_sayfasinda(istemci, test_ayarlari):
    kamera_id, _ = _kamera_ve_bolge(istemci, test_ayarlari, "pedestrian_path", "Yol")
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    for etiket in ("İnsan", "Forklift", "Tır / Araç", "Baret", "Reflektörlü yelek", "Kural ihlali"):
        assert etiket in detay, etiket


def test_renk_anahtari_overlay_renkleriyle_ayni():
    """Ekrandaki anahtar, çizilen kutu renkleriyle BİREBİR aynı olmalı; yoksa
    kullanıcıyı yanıltır."""
    from pathlib import Path

    from app.analiz.boru_hatti import _BOLGE_RENGI, _IHLAL_RENGI, _RENKLER, _YELEK_RENGI

    sablon = Path("backend/app/web/templates/renk_anahtari.html").read_text(encoding="utf-8")

    def hex_kod(bgr):  # BGR -> #RRGGBB
        return f"#{bgr[2]:02X}{bgr[1]:02X}{bgr[0]:02X}"

    assert hex_kod(_RENKLER["person"]) in sablon
    assert hex_kod(_RENKLER["forklift"]) in sablon
    assert hex_kod(_RENKLER["truck"]) in sablon
    assert hex_kod(_IHLAL_RENGI) in sablon
    assert hex_kod(_YELEK_RENGI) in sablon
    assert hex_kod(_BOLGE_RENGI) in sablon


def test_bolge_rengi_arac_renginden_ayirt_edilir():
    """Bölge çerçevesi ile araç kutusu ekranda karışmamalı: kanıt fotoğrafına
    bakan kişi hangisinin çizdiği bölge, hangisinin araç olduğunu anlamalı."""
    from app.analiz.boru_hatti import _BOLGE_RENGI, _RENKLER

    fark = sum(abs(a - b) for a, b in zip(_BOLGE_RENGI, _RENKLER["truck"], strict=True))
    assert fark > 150, f"bölge ve araç rengi çok yakın (fark {fark})"

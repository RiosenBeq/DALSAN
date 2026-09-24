"""Forklift sayfası (web/forklift_web.py): kapı, etiketleme, eğitim verisi.

- Kapı sayfanın en üstünde, varsayılan KAPALI; açmak onay ister; her
  değişiklik FORKLIFT_COLLECTION_CHANGED ve erişim izi yazar.
- Etiketleme ekranı sıradaki kareyi açar, kutuları kaydeder, "Atla" ve
  "Kareyi sil" sonraki kareye geçer; geçersiz etiket Türkçe hatayla reddedilir.
- Kare görüntüsü ve dışa aktarım erişim izine yazılır; zip LOCO düzenindedir.
- Menüde Forklift bağlantısı var.
"""

from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import pytest

from app import veritabani
from app.egitim import forklift_verisi as fv


def _baglanti(test_ayarlari):
    return veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)


def _sorgu(test_ayarlari, sql: str, *parametre) -> list[dict]:
    baglanti = _baglanti(test_ayarlari)
    try:
        return [dict(s) for s in baglanti.execute(sql, parametre)]
    finally:
        baglanti.close()


@pytest.fixture
def kareler(istemci, test_ayarlari):
    """Üç etiketsiz kare (istemci şemayı kurduktan sonra)."""
    baglanti = _baglanti(test_ayarlari)
    try:
        kare = np.zeros((480, 640, 3), dtype=np.uint8)
        for _ in range(3):
            fv.kareyi_kaydet(
                baglanti,
                test_ayarlari.goruntu_klasoru,
                None,
                kare,
                [{"kutu": [10.0, 20.0, 300.0, 400.0], "sinif": "truck", "puan": 0.6}],
            )
        return [s["id"] for s in baglanti.execute("SELECT id FROM forklift_samples ORDER BY id")]
    finally:
        baglanti.close()


def test_menude_forklift_ve_kapi_varsayilan_kapali(istemci, test_ayarlari):
    metin = istemci.get("/forklift").text
    assert 'href="/forklift"' in metin
    assert "1. Kare toplama: KAPALI" in metin
    assert metin.index("Kare toplama:") < metin.index("2. Etiketleme")
    assert _sorgu(test_ayarlari, "SELECT enabled FROM forklift_collection_gate")[0]["enabled"] == 0


def test_onaysiz_acilmaz_ac_kapat_olay_ve_iz_yazar(istemci, test_ayarlari):
    yanit = istemci.post("/forklift/toplama", data={"ac": "1"}, follow_redirects=False)
    assert yanit.status_code == 400 and "aydınlatma" in yanit.json()["hata"]
    istemci.post("/forklift/toplama", data={"ac": "1", "onay": "1"}, follow_redirects=False)
    assert "1. Kare toplama: AÇIK" in istemci.get("/forklift").text
    istemci.post("/forklift/toplama", data={"ac": "0"}, follow_redirects=False)
    istemci.post("/forklift/toplama", data={"ac": "0"}, follow_redirects=False)  # zaten kapalı
    olaylar = _sorgu(
        test_ayarlari,
        "SELECT details FROM events WHERE event_code = 'FORKLIFT_COLLECTION_CHANGED' ORDER BY id",
    )
    mesajlar = [json.loads(o["details"])["mesaj"] for o in olaylar]
    assert len(mesajlar) == 2, "aynı duruma geçiş olay yazmaz"
    assert "açıldı" in mesajlar[0] and "kapatıldı" in mesajlar[1]
    izler = _sorgu(
        test_ayarlari,
        "SELECT target FROM access_log WHERE action = 'forklift_collection_gate' ORDER BY id",
    )
    assert [i["target"] for i in izler] == ["acik", "kapali"]


def test_etiketleme_sirayla_kaydeder_atlar_siler(istemci, test_ayarlari, kareler):
    ilk, ikinci, ucuncu = kareler
    sayfa = istemci.get("/forklift/etiket").text
    assert f"kare #{ilk}" in sayfa and f"/forklift/kare/{ilk}.jpg" in sayfa
    assert '"sinif": "truck"' in sayfa, "öneri kutuları sayfada"

    yanit = istemci.post(
        f"/forklift/{ilk}/etiket",
        json={"kutular": [{"kutu": [10, 20, 300, 400], "sinif": "forklift"}]},
    )
    assert yanit.status_code == 200 and yanit.json() == {"sonraki": ikinci}
    satir = _sorgu(test_ayarlari, "SELECT labels FROM forklift_samples WHERE id = ?", ilk)[0]
    assert json.loads(satir["labels"]) == [
        {"kutu": [10.0, 20.0, 300.0, 400.0], "sinif": "forklift"}
    ]

    assert f"kare #{ucuncu}" in istemci.get(f"/forklift/etiket?sonra={ikinci}").text, "Atla"
    assert f"kare #{ikinci}" in istemci.get(f"/forklift/etiket?sonra={ucuncu}").text, "baştan"

    hatali = istemci.post(
        f"/forklift/{ikinci}/etiket", json={"kutular": [{"kutu": [0, 0, 9, 9], "sinif": "tır"}]}
    )
    assert hatali.status_code == 400 and "forklift ya da transpalet" in hatali.json()["hata"]

    assert istemci.post(f"/forklift/{ikinci}/sil").json() == {"sonraki": ucuncu}
    assert istemci.post(f"/forklift/{ucuncu}/etiket", json={"kutular": []}).json() == {
        "sonraki": None
    }
    assert "Etiketlenecek kare kalmadı" in istemci.get("/forklift/etiket").text


def test_kare_goruntusu_erisim_izine_yazilir(istemci, test_ayarlari, kareler):
    yanit = istemci.get(f"/forklift/kare/{kareler[0]}.jpg")
    assert yanit.status_code == 200 and yanit.content[:2] == b"\xff\xd8"
    assert istemci.get("/forklift/kare/99999.jpg").status_code == 404
    izler = _sorgu(
        test_ayarlari, "SELECT target FROM access_log WHERE action = 'view_forklift_frame'"
    )
    assert izler == [{"target": f"frame:{kareler[0]}"}]


def test_egitim_verisi_zip_iner_ve_iz_yazar(istemci, test_ayarlari, kareler):
    yanit = istemci.get("/forklift/veri-seti.zip")
    assert yanit.status_code == 400 and "etiketli kare yok" in yanit.json()["hata"]
    istemci.post(
        f"/forklift/{kareler[0]}/etiket",
        json={"kutular": [{"kutu": [10, 20, 300, 400], "sinif": "forklift"}]},
    )
    yanit = istemci.get("/forklift/veri-seti.zip")
    assert yanit.status_code == 200
    assert "dalsan-forklift-veri-seti-" in yanit.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(yanit.content)) as arsiv:
        adlar = set(arsiv.namelist())
    assert {"annotations/egitim.json", "annotations/test.json", "manifest.json"} <= adlar
    assert f"egitim/saha-{kareler[0]:06d}.jpg" in adlar
    izler = _sorgu(test_ayarlari, "SELECT target FROM access_log WHERE action = 'export_dataset'")
    assert izler == [{"target": "forklift (1 kare)"}]


def test_hepsini_sil_onay_ister(istemci, test_ayarlari, kareler):
    yanit = istemci.post("/forklift/hepsini-sil", data={}, follow_redirects=False)
    assert yanit.status_code == 400
    assert len(_sorgu(test_ayarlari, "SELECT id FROM forklift_samples")) == 3
    yanit = istemci.post("/forklift/hepsini-sil", data={"onay": "1"}, follow_redirects=False)
    assert yanit.status_code == 303
    assert _sorgu(test_ayarlari, "SELECT id FROM forklift_samples") == []
    assert not list((test_ayarlari.goruntu_klasoru / fv.KLASOR).rglob("*.jpg"))


def test_sayfa_sayilari_ve_etiket_dugmesi(istemci, kareler):
    metin = istemci.get("/forklift").text
    assert "Etiketlemeye başla (3 kare)" in metin
    assert "Hepsini sil" in metin

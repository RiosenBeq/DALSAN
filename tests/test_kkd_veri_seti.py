"""KKD veri seti: güne göre bölme, zor örnek ve dışa aktarım (docs/17 §5.8; Faz 3b).

Rastgele bölme yasak (docs/04 §5.4): aynı kamera ve gün iki kümede olamaz, günler
kronolojik ayrılır. Dışa aktarılan zip'in manifest'i her dosyanın sha256'sını
taşır ve dosyalarla tutarlıdır.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

from app import veritabani
from app.analiz.kkd_siniflandirici import netlik_olc
from app.egitim import veri_seti
from app.egitim.veri_seti import ZOR_ORNEKLER, disa_aktar, etiketli_ornekler, gun_bolmesi

# ------------------------------------------------------------------ bölme


def _gunler(adet: int) -> list[str]:
    return [f"2026-09-{gun:02d}" for gun in range(1, adet + 1)]


def _sayilar(bolme: dict[str, str]) -> tuple[int, int, int]:
    degerler = list(bolme.values())
    return degerler.count("train"), degerler.count("val"), degerler.count("test")


def test_docs04_ornegi_sekiz_gun():
    """docs/04 §5.4: 1.–5. gün eğitim, 6. doğrulama, 7.–8. test."""
    bolme = gun_bolmesi(_gunler(8))
    assert _sayilar(bolme) == (5, 1, 2)
    assert bolme["2026-09-06"] == "val"
    assert bolme["2026-09-07"] == bolme["2026-09-08"] == "test"


@pytest.mark.parametrize(
    ("adet", "beklenen"), [(0, (0, 0, 0)), (1, (1, 0, 0)), (2, (1, 0, 1)), (3, (1, 1, 1))]
)
def test_az_gunde_bolme(adet, beklenen):
    assert _sayilar(gun_bolmesi(_gunler(adet))) == beklenen


@pytest.mark.parametrize("adet", range(3, 61))
def test_bolme_kronolojik_ve_kumeler_dolu(adet):
    gunler = [f"2026-{9 + i // 28:02d}-{1 + i % 28:02d}" for i in range(adet)]
    bolme = gun_bolmesi(reversed(gunler))  # sıra girdiye bağlı değil
    egitim, val, test = _sayilar(bolme)
    assert egitim >= 1 and val >= 1 and test >= 1
    sirali = sorted(bolme)
    kumeler = [bolme[g] for g in sirali]
    assert kumeler == sorted(kumeler, key=veri_seti.KUMELER.index), "günler kronolojik ayrılmalı"


def test_uc_gunden_azsa_uyari_var():
    assert veri_seti.uyarilar(gun_bolmesi(_gunler(3))) == []
    uyari = veri_seti.uyarilar(gun_bolmesi(_gunler(2)))
    assert uyari and "val kümesi boş" in uyari[0] and "en az üç" in uyari[0]


# ------------------------------------------------------------------ dışa aktarım


@pytest.fixture
def baglanti(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    for kid in (1, 2):
        baglanti.execute(
            "INSERT INTO cameras (id, name, source_type, source_url, created_at, updated_at) "
            "VALUES (?, ?, 'file', 'v.mp4', '2026-09-01T00:00:00+00:00', "
            "'2026-09-01T00:00:00+00:00')",
            (kid, f"K{kid}"),
        )
    baglanti.commit()
    try:
        yield baglanti
    finally:
        baglanti.close()


def _ornek(
    baglanti,
    goruntu_klasoru: Path,
    kamera_id: int,
    an: str,
    baret: str | None = "yes",
    yelek: str | None = "no",
    dosya_var: bool = True,
    zor: str | None = None,
    yol: str | None = None,
) -> int:
    goreli = yol or f"kkd-ornekler/{an[:10]}-{kamera_id}-{an[11:13]}{an[14:16]}.jpg"
    if dosya_var:
        tam = goruntu_klasoru / goreli
        tam.parent.mkdir(parents=True, exist_ok=True)
        tam.write_bytes(f"jpeg:{goreli}".encode())
    etiketli = baret is not None and yelek is not None
    imlec = baglanti.execute(
        "INSERT INTO ppe_samples (camera_id, captured_at, crop_path, helmet_label, vest_label, "
        "source, labeled_at, person_height_px, sharpness, hard_case) "
        "VALUES (?, ?, ?, ?, ?, 'auto', ?, 180, 42.5, ?)",
        (kamera_id, an, goreli, baret, yelek, an if etiketli else None, zor),
    )
    baglanti.commit()
    return int(imlec.lastrowid)


def _veri_seti_kur(baglanti, klasor: Path) -> None:
    # Dört gün × iki kamera; gün sınırı Türkiye saatiyle (21:30 UTC = ertesi gün 00:30)
    for gun in ("01", "02", "03", "04"):
        for kamera in (1, 2):
            _ornek(baglanti, klasor, kamera, f"2026-09-{gun}T09:00:00+00:00")
    _ornek(baglanti, klasor, 1, "2026-09-04T21:30:00+00:00", zor="white_cap")  # 5 Eylül
    _ornek(baglanti, klasor, 2, "2026-09-02T10:00:00+00:00", baret=None)  # etiketsiz
    _ornek(baglanti, klasor, 2, "2026-09-03T10:00:00+00:00", dosya_var=False)  # dosyası yok
    _ornek(baglanti, klasor, 1, "2026-09-03T11:00:00+00:00", yol="../../disari.jpg")


def test_disa_aktarim_bolme_ve_manifest_tutarli(baglanti, test_ayarlari):
    klasor = test_ayarlari.goruntu_klasoru
    _veri_seti_kur(baglanti, klasor)
    (klasor.parent.parent / "disari.jpg").write_bytes(b"klasor disi")  # varsa bile alinmaz

    tampon = io.BytesIO()
    manifest = disa_aktar(etiketli_ornekler(baglanti), klasor, tampon)
    arsiv = zipfile.ZipFile(tampon)

    # Etiketsiz örnek dışarıda; dosyası olmayan ve klasör dışını gösteren atlandı
    assert manifest["ornek_sayisi"] == 9
    assert manifest["eksik_dosya"] == 2
    assert any("2 örneğin görüntü dosyası" in u for u in manifest["uyarilar"])

    # sha256 manifest'i zip'teki her dosyayla tutarlı; listede olmayan dosya yok
    assert set(arsiv.namelist()) == set(manifest["dosyalar"]) | {"manifest.json"}
    for ad, ozet in manifest["dosyalar"].items():
        assert hashlib.sha256(arsiv.read(ad)).hexdigest() == ozet, ad
    assert json.loads(arsiv.read("manifest.json"))["dosyalar"] == manifest["dosyalar"]

    satirlar = list(csv.DictReader(io.StringIO(arsiv.read("etiketler.csv").decode("utf-8"))))
    assert len(satirlar) == 9
    kume_gruplari: dict[tuple, set] = defaultdict(set)
    gun_kumeleri: dict[str, set] = defaultdict(set)
    for satir in satirlar:
        assert satir["dosya"].startswith(f"goruntuler/{satir['kume']}/")
        kume_gruplari[(satir["kamera_id"], satir["gun"])].add(satir["kume"])
        gun_kumeleri[satir["gun"]].add(satir["kume"])
    # ASIL KURAL: aynı kamera ve gün iki kümede olamaz (bir gün de)
    assert all(len(k) == 1 for k in kume_gruplari.values())
    assert all(len(k) == 1 for k in gun_kumeleri.values())
    # Türkiye günü: 4 Eylül 21:30 UTC örneği 5 Eylül'e düştü → beş gün, son gün test
    assert {s["gun"] for s in satirlar if s["zor_ornek"] == "white_cap"} == {"2026-09-05"}
    assert gun_kumeleri["2026-09-05"] == {"test"}
    assert gun_kumeleri["2026-09-01"] == {"train"}
    # Boy, netlik ve kaynak eğitim betiğine gider; kamera ADI gitmez
    assert satirlar[0]["kisi_boyu_px"] == "180" and satirlar[0]["netlik"] == "42.5"
    assert "K1" not in arsiv.read("etiketler.csv").decode("utf-8")

    bolme = json.loads(arsiv.read("bolme.json"))
    tum_gunler = [g for kume in veri_seti.KUMELER for g in bolme["gunler"][kume]]
    assert sorted(tum_gunler) == sorted(set(tum_gunler)) == sorted(gun_kumeleri)


# ------------------------------------------------------------------ web


def test_zor_ornek_isareti(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        ornek = _ornek(
            baglanti, test_ayarlari.goruntu_klasoru, None, "2026-09-01T09:00:00+00:00", baret=None
        )
    finally:
        baglanti.close()

    metin = istemci.get("/kkd").text
    for ad in ZOR_ORNEKLER.values():
        assert ad in metin
    assert istemci.post(f"/kkd/{ornek}/zor", data={"kod": "backpack"}).status_code == 204

    def _kayit():
        b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
        try:
            return b.execute("SELECT hard_case FROM ppe_samples WHERE id = ?", (ornek,)).fetchone()[
                0
            ]
        finally:
            b.close()

    assert _kayit() == "backpack"
    assert istemci.post(f"/kkd/{ornek}/zor", data={"kod": ""}).status_code == 204
    assert _kayit() is None
    assert istemci.post(f"/kkd/{ornek}/zor", data={"kod": "uydurma"}).status_code == 400


def test_etiketli_ornek_yokken_disa_aktarim_anlasilir_hata(istemci):
    yanit = istemci.get("/kkd/veri-seti.zip")
    assert yanit.status_code == 400
    assert "etiketli örnek yok" in yanit.json()["hata"]
    assert "Henüz etiketli örnek yok" in istemci.get("/kkd").text


def test_veri_seti_indirilir_ve_gecici_dosya_silinir(istemci, test_ayarlari, monkeypatch):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        for gun in ("01", "02"):
            _ornek(baglanti, test_ayarlari.goruntu_klasoru, None, f"2026-09-{gun}T09:00:00+00:00")
    finally:
        baglanti.close()

    import tempfile

    uretilen = []
    gercek = tempfile.mkstemp

    def _kaydet(*a, **k):
        sonuc = gercek(*a, **k)
        uretilen.append(sonuc[1])
        return sonuc

    monkeypatch.setattr(tempfile, "mkstemp", _kaydet)
    sayfa = istemci.get("/kkd").text
    assert "val kümesi boş" in sayfa  # iki gün: uyarı sayfada

    yanit = istemci.get("/kkd/veri-seti.zip")
    assert yanit.status_code == 200
    assert yanit.headers["content-type"] == "application/zip"
    assert "dalsan-kkd-veri-seti-" in yanit.headers["content-disposition"]
    assert (
        json.loads(zipfile.ZipFile(io.BytesIO(yanit.content)).read("manifest.json"))["ornek_sayisi"]
        == 2
    )
    assert uretilen and not Path(uretilen[0]).exists(), "geçici zip gönderildikten sonra silinmeli"


# ------------------------------------------------------------------ netlik


def test_netlik_keskin_goruntude_yuksek_bulanikta_dusuk():
    import cv2

    dama = (np.indices((256, 128)).sum(axis=0) // 8 % 2 * 255).astype(np.uint8)
    keskin = cv2.merge([dama, dama, dama])
    bulanik = cv2.GaussianBlur(keskin, (15, 15), 5)
    assert netlik_olc(keskin) > 10 * netlik_olc(bulanik)
    assert netlik_olc(np.full((256, 128, 3), 128, dtype=np.uint8)) == 0.0

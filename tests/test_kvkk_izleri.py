"""KVKK izleri (docs/17 §10, şema 010; Faz 5c).

- Dondurulan olay (hukuki süreç) saklama süresi dolsa da silinmez; kanıt
  fotoğrafı ve uyarı teslim kaydı da kalır.
- Her bakım koşusu `purge_log`'a bir satır yazar (kişisel veri yok).
- Dondurma ve çözme erişim izine düşer; sebep zorunludur.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from app import veritabani, zaman
from app.analiz.supervizor import AnalizSupervizoru
from app.loglama import log_al
from app.olaylar.yazici import ihlal_yaz
from app.rules.tipler import Ihlal
from app.web import erisim_izi


@pytest.fixture
def baglanti(test_ayarlari):
    b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(b)
    simdi = zaman.simdi_utc()
    b.execute(
        "INSERT INTO cameras (name, source_type, source_url, created_at, updated_at) "
        "VALUES ('K1', 'file', 'v.mp4', ?, ?)",
        (simdi, simdi),
    )
    b.commit()
    erisim_izi.tekrar_bellegini_temizle()
    try:
        yield b
    finally:
        b.close()


def _eski_olay(baglanti, ayarlar, gun: int, dondur: bool = False) -> int:
    """Saklama süresinin dışına taşınmış, kanıt fotoğraflı bir ihlal olayı."""
    olay_id = ihlal_yaz(
        baglanti,
        ayarlar,
        Ihlal(kural_id=1, kamera_id=1, takip_idler=[1], bolge_id=None, olculen=1.0),
        {"rule_type": "zone_intrusion"},
        b"kanit",
    )
    baglanti.execute(
        "UPDATE events SET occurred_at = ?, hold = ?, hold_reason = ? WHERE id = ?",
        (zaman.gun_once_utc(gun), int(dondur), "dava 2026/12" if dondur else None, olay_id),
    )
    baglanti.commit()
    yol = baglanti.execute("SELECT snapshot_path FROM events WHERE id = ?", (olay_id,)).fetchone()
    eski_zaman = time.time() - gun * 86400
    os.utime(ayarlar.goruntu_klasoru / yol[0], (eski_zaman, eski_zaman))
    return olay_id


def _bakim(ayarlar, baglanti) -> None:
    supervizor = AnalizSupervizoru.__new__(AnalizSupervizoru)
    supervizor.ayarlar = ayarlar
    supervizor._log = log_al("test")
    supervizor._bakim_yap(baglanti)


def test_dondurulan_olay_ve_kaniti_sure_dolsa_da_silinmez(baglanti, test_ayarlari):
    gun = test_ayarlari.olay_saklama_gun + 10
    donmus = _eski_olay(baglanti, test_ayarlari, gun, dondur=True)
    siradan = _eski_olay(baglanti, test_ayarlari, gun)
    donmus_foto = baglanti.execute(
        "SELECT snapshot_path FROM events WHERE id = ?", (donmus,)
    ).fetchone()[0]
    for olay_id in (donmus, siradan):
        baglanti.execute(
            "INSERT INTO alert_deliveries (event_id, event_code, channel, stage, result, "
            "queued_at) VALUES (?, 'RESTRICTED_ENTRY', 'http', 'acildi', 'ok', ?)",
            (olay_id, zaman.gun_once_utc(gun)),
        )
    baglanti.commit()

    _bakim(test_ayarlari, baglanti)

    satir = baglanti.execute("SELECT * FROM events WHERE id = ?", (donmus,)).fetchone()
    assert satir is not None and satir["snapshot_path"] == donmus_foto
    assert (test_ayarlari.goruntu_klasoru / donmus_foto).is_file(), "kanıt fotoğrafı kalır"
    assert baglanti.execute("SELECT 1 FROM events WHERE id = ?", (siradan,)).fetchone() is None
    teslimler = [
        s[0] for s in baglanti.execute("SELECT event_id FROM alert_deliveries ORDER BY id")
    ]
    assert teslimler == [donmus], "dondurulan olayın teslim kaydı kanıtın parçasıdır"


def test_her_bakim_kosusu_imha_kaydi_yazar(baglanti, test_ayarlari):
    _eski_olay(baglanti, test_ayarlari, test_ayarlari.olay_saklama_gun + 10, dondur=True)
    _eski_olay(baglanti, test_ayarlari, test_ayarlari.olay_saklama_gun + 10)
    _bakim(test_ayarlari, baglanti)
    _bakim(test_ayarlari, baglanti)  # silinecek bir şey kalmasa da satır yazılır
    ilk, ikinci = (dict(s) for s in baglanti.execute("SELECT * FROM purge_log ORDER BY id"))
    assert (ilk["events_deleted"], ilk["held_skipped"]) == (1, 1)
    assert ilk["photos_deleted"] == 1, "yalnız dondurulmayan olayın fotoğrafı silinir"
    assert (ikinci["events_deleted"], ikinci["photos_deleted"]) == (0, 0)
    politika = json.loads(ilk["policy"])
    assert politika["olay_gun"] == test_ayarlari.olay_saklama_gun
    assert set(politika) == {
        "olay_gun",
        "sistem_olay_gun",
        "goruntu_gun",
        "kkd_ham_veri_gun",
        "uyari_kaydi_gun",  # 011: uyarı kaydı arşivi (23.09.2026)
    }
    # Arşivlenecek uyarı kaydı yoktu: sayı 0, dosya yok
    assert (ilk["alerts_archived"], ilk["alert_archive_file"]) == (0, None)


def _olay_ekle(test_ayarlari) -> int:
    b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        olay_id = ihlal_yaz(
            b,
            test_ayarlari,
            Ihlal(kural_id=1, kamera_id=1, takip_idler=[1], bolge_id=None, olculen=1.0),
            {"rule_type": "zone_intrusion"},
            None,
        )
    finally:
        b.close()
    return olay_id


def _erisimler(test_ayarlari) -> list[dict]:
    b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return [dict(s) for s in b.execute("SELECT * FROM access_log ORDER BY id")]
    finally:
        b.close()


def test_dondur_ve_coz_erisim_izine_duser(istemci, baglanti, test_ayarlari):
    olay_id = _olay_ekle(test_ayarlari)
    yanit = istemci.post(
        f"/olaylar/{olay_id}/dondur",
        data={"sebep": "  iş kazası   soruşturması "},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    satir = baglanti.execute(
        "SELECT hold, hold_reason FROM events WHERE id = ?", (olay_id,)
    ).fetchone()
    assert tuple(satir) == (1, "iş kazası soruşturması")
    metin = istemci.get(f"/olaylar/{olay_id}").text
    assert "dondurulmuş" in metin and "Dondurmayı kaldır" in metin
    assert "dondurulmuş" in istemci.get("/olaylar").text

    istemci.post(f"/olaylar/{olay_id}/coz", follow_redirects=False)
    satir = baglanti.execute(
        "SELECT hold, hold_reason FROM events WHERE id = ?", (olay_id,)
    ).fetchone()
    assert tuple(satir) == (0, None)
    izler = _erisimler(test_ayarlari)
    assert [(i["action"], i["target"]) for i in izler] == [
        ("hold_change", f"event:{olay_id} hold=1"),
        ("hold_change", f"event:{olay_id} hold=0"),
    ]
    assert all(i["client"] == "testclient" for i in izler)


def test_sebepsiz_dondurma_reddedilir(istemci, baglanti, test_ayarlari):
    olay_id = _olay_ekle(test_ayarlari)
    yanit = istemci.post(f"/olaylar/{olay_id}/dondur", data={"sebep": "   "})
    assert yanit.status_code == 400
    assert baglanti.execute("SELECT hold FROM events WHERE id = ?", (olay_id,)).fetchone()[0] == 0
    assert _erisimler(test_ayarlari) == []


# ------------------------------------------------------------ erişim izi (5c-2)


def _kanitli_olay(test_ayarlari) -> tuple[int, str]:
    b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        olay_id = ihlal_yaz(
            b,
            test_ayarlari,
            Ihlal(kural_id=1, kamera_id=1, takip_idler=[1], bolge_id=None, olculen=1.0),
            {"rule_type": "zone_intrusion"},
            b"kanit",
        )
        yol = b.execute("SELECT snapshot_path FROM events WHERE id = ?", (olay_id,)).fetchone()[0]
    finally:
        b.close()
    return olay_id, yol


def test_kanit_goruntuleme_iz_birakir_sifre_ve_cerez_yazilmaz(baglanti, test_ayarlari):
    """docs/17 §13 5c: kanıt görüntüleme access_log'a düşer ve şifre/çerez içermez.
    Aynı kaydın dakika içindeki tekrarı (küçük resim, yenileme) bir kez yazılır."""
    import dataclasses

    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    sifre = "kvkk-sifre-2026"
    olay_id, yol = _kanitli_olay(test_ayarlari)
    uygulama = uygulama_olustur(
        dataclasses.replace(test_ayarlari, yonetici_sifresi=sifre), analiz=False
    )
    with TestClient(uygulama) as istemci:
        istemci.post("/giris", data={"sifre": sifre, "sonra": "/"}, follow_redirects=False)
        cerezler = [c.value for c in istemci.cookies.jar]
        assert cerezler, "oturum çerezi alınmış olmalı"
        for _ in range(3):
            assert istemci.get(f"/goruntuler/{yol}").status_code == 200
    izler = _erisimler(test_ayarlari)
    assert [(i["action"], i["target"]) for i in izler] == [("view_snapshot", f"event:{olay_id}")]
    ham = json.dumps(izler, ensure_ascii=False)
    assert sifre not in ham and not any(c in ham for c in cerezler)

    erisim_izi.tekrar_bellegini_temizle()  # tekrar aralığı geçti
    with TestClient(uygulama) as istemci:
        istemci.post("/giris", data={"sifre": sifre, "sonra": "/"}, follow_redirects=False)
        istemci.get(f"/goruntuler/{yol}")
    assert len(_erisimler(test_ayarlari)) == 2


def test_kkd_kirpigi_goruntuleme_iz_birakir(istemci, baglanti, test_ayarlari):
    kirpik = test_ayarlari.goruntu_klasoru / "kkd-ornekler" / "ornek.jpg"
    kirpik.parent.mkdir(parents=True, exist_ok=True)
    kirpik.write_bytes(b"jpg")
    ornek_id = baglanti.execute(
        "INSERT INTO ppe_samples (captured_at, crop_path, source) "
        "VALUES (?, 'kkd-ornekler/ornek.jpg', 'auto')",
        (zaman.simdi_utc(),),
    ).lastrowid
    baglanti.commit()
    assert istemci.get(f"/kkd/ornek/{ornek_id}.jpg").status_code == 200
    erisim_izi.tekrar_bellegini_temizle()
    assert istemci.get("/goruntuler/kkd-ornekler/ornek.jpg").status_code == 200
    assert [(i["action"], i["target"]) for i in _erisimler(test_ayarlari)] == [
        ("view_ppe_crop", f"sample:{ornek_id}"),
        ("view_ppe_crop", f"sample:{ornek_id}"),
    ]


def test_disa_aktarim_ve_degisiklikler_iz_birakir(istemci, baglanti, test_ayarlari):
    _olay_ekle(test_ayarlari)
    istemci.get("/olaylar/disa-aktar.csv")
    istemci.get("/komuta/rapor/ozet.csv")
    istemci.post("/kkd/toplama", data={"ac": "1", "onay": "1"}, follow_redirects=False)
    istemci.post("/kkd/toplama", data={"ac": "0"}, follow_redirects=False)
    kural_id = baglanti.execute(
        "INSERT INTO rules (camera_id, rule_type, target_classes, params, updated_at) "
        "VALUES (1, 'zone_intrusion', '[\"person\"]', '{}', ?)",
        (zaman.simdi_utc(),),
    ).lastrowid
    baglanti.commit()
    istemci.post(
        "/komuta/uyari/golge",
        data={"golge": "1", "kural_idler": [str(kural_id)]},
        follow_redirects=False,
    )
    istemci.post(f"/kurallar/{kural_id}/sil", follow_redirects=False)
    izler = [(i["action"], i["target"]) for i in _erisimler(test_ayarlari)]
    assert izler[0] == ("export_csv", "olaylar (1 satır)")
    assert izler[1][0] == "export_csv" and izler[1][1].startswith("rapor (")
    assert izler[2:] == [
        ("ppe_collection_gate", "acik"),
        ("ppe_collection_gate", "kapali"),
        ("rule_change", f"rule:{kural_id} golge=1"),
        ("rule_change", f"rule:{kural_id} silindi"),
    ]


def test_ayar_degisikligi_yalniz_anahtar_adini_yazar(test_ayarlari):
    """Değer (şifre, adres, gün sayısı) izde görünmez; değişmeyen ayar yazılmaz."""
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur
    from tests.test_ayarlar_sayfasi import ORNEK_ENV, TAM_FORM

    test_ayarlari.env_yolu.write_text(ORNEK_ENV, encoding="utf-8")
    b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(b)
    b.close()
    with TestClient(uygulama_olustur(test_ayarlari, analiz=False)) as istemci:
        istemci.post("/ayarlar/kaydet", data={**TAM_FORM, "OLAY_SAKLAMA_GUN": "200"})
        istemci.post("/ayarlar/kaydet", data={**TAM_FORM, "OLAY_SAKLAMA_GUN": "200"})
    izler = [(i["action"], i["target"]) for i in _erisimler(test_ayarlari)]
    assert len(izler) == 1, "aynı değerlerle ikinci kayıt iz bırakmaz"
    eylem, hedef = izler[0]
    assert eylem == "settings_change" and "OLAY_SAKLAMA_GUN" in hedef.split(", ")
    assert "200" not in hedef, "değer yazılmaz"


# ------------------------------------------------------------ Ayarlar → KVKK (5c-3)


def test_ayarlar_kvkk_bolumu_erisim_ve_imha_kayitlarini_gosterir(istemci, baglanti, test_ayarlari):
    """docs/17 §13 5c: Ayarlar → KVKK'da "adres, saat, olay #123" satırları ve
    imha günlüğü."""
    metin = istemci.get("/ayarlar").text
    assert "KVKK: erişim ve imha kayıtları" in metin
    assert "Henüz erişim kaydı yok." in metin and "Bakım henüz çalışmadı" in metin

    olay_id = _olay_ekle(test_ayarlari)
    istemci.post(f"/olaylar/{olay_id}/dondur", data={"sebep": "dava"}, follow_redirects=False)
    _bakim(test_ayarlari, baglanti)
    metin = istemci.get("/ayarlar").text
    assert f'<a href="/olaylar/{olay_id}">olay #{olay_id} dondu</a>' in metin
    assert "<code>testclient</code>" in metin and "olay dondurma değişti" in metin
    assert f"olay {test_ayarlari.olay_saklama_gun} gün" in metin
    assert "Hukuki süreç için dondurulmuş olay: <b>1</b>" in metin


def test_hedef_metinleri():
    assert erisim_izi.hedef_metni("event:12 hold=0") == ("olay #12 çözüldü", "/olaylar/12")
    assert erisim_izi.hedef_metni("rule:3,4 golge=0") == ("kural #3, #4 anonsu açıldı", None)
    assert erisim_izi.hedef_metni("camera:2 mahremiyet kontrolü") == (
        "kamera #2 mahremiyet kontrolü",
        "/kameralar/2",
    )
    assert erisim_izi.hedef_metni("OLAY_SAKLAMA_GUN") == ("OLAY_SAKLAMA_GUN", None)
    assert erisim_izi.hedef_metni(None) == ("-", None)

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
    assert set(politika) == {"olay_gun", "sistem_olay_gun", "goruntu_gun", "kkd_ham_veri_gun"}


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

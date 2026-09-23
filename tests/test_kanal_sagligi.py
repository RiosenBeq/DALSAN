"""Uyarı kanallarının sağlığı ve uyarı garantisi (docs/17 §7.3-1, §7.4; Faz 4b).

- Durum makinesi: kesintisiz "bağlı değil" ANONS_KOPUK_ESIGI_SN'yi (30) doldurunca
  bir kez AUDIO_CHANNEL_DOWN; iki ardışık "bağlı" ile AUDIO_CHANNEL_UP. 29 sn
  olay üretmez. "Öğrenemedik" (None) olay üretmez ve garantiyi null yapar.
- Yoklama: boş çıkış adı None (R37); listede olmayan bluez sink False; aynı
  adresli sink (profil soneki değişmiş) True; çalıcı yok False; TCP reddi False.
- Yönlendirme: bölüm kanalı koptuysa uyarı "Tüm fabrika"ya düşer.
- Garanti: açılışı hiçbir sesli/uzak kanala ulaşmayan olay ALERT_UNDELIVERED
  (kamera başına hız sınırlı) ve /saglik "uyari_ulasmiyor"; ekran sayılmaz.
Gerçek ses ÇALINMAZ, gerçek ağa çıkılmaz (yalnız 127.0.0.1).
"""

from __future__ import annotations

import json
import socket

import pytest

from app import veritabani
from app.olaylar import anons, ekran
from app.olaylar.anons import AnonsHatasi, AnonsYoneticisi, OlayBilgisi
from app.olaylar.dagitici import ASAMA_HATIRLATMA
from app.olaylar.kanal_sagligi import (
    HAL_KOPTU,
    KOD_GELDI,
    KOD_KOPTU,
    KanalHali,
    ilerle,
    kanal_yokla,
)
from app.olaylar.kanallar import kanal_sagligi_ozeti
from app.olaylar.ses_cihazlari import SesCihazi

BT = "bluez_output.AA_BB_CC_DD_EE_FF.1"
BT_YENI_SONEK = "bluez_output.AA_BB_CC_DD_EE_FF.a2dp-sink"
DAHILI = "alsa_output.pci-0000_00_1f.3.analog-stereo"


# ------------------------------------------------------------ durum makinesi


def test_29_sn_olay_uretmez_30_sn_bir_kez_koptu():
    hali = KanalHali()
    assert ilerle(hali, True, 0.0, 30) is None and hali.saglik == "ok"
    assert ilerle(hali, False, 10.0, 30) is None
    assert ilerle(hali, False, 39.0, 30) is None, "29 sn: kısa aksaklık olay üretmez"
    assert hali.saglik == "ok", "şüpheli bir karar değildir; son karar korunur"
    assert ilerle(hali, False, 40.0, 30) == KOD_KOPTU
    assert hali.saglik == "down"
    assert ilerle(hali, False, 50.0, 30) is None, "koptu olayı bir kez yazılır"


def test_iki_ardisik_bagli_geldi_uretir():
    hali = KanalHali(hal=HAL_KOPTU, saglik="down")
    assert ilerle(hali, True, 0.0, 30) is None, "tek 'bağlı' yetmez (histerezis)"
    assert ilerle(hali, False, 10.0, 30) is None, "araya giren kopukluk sayacı sıfırlar"
    assert ilerle(hali, True, 20.0, 30) is None
    assert ilerle(hali, True, 30.0, 30) == KOD_GELDI
    assert hali.saglik == "ok"


def test_kisa_aksaklik_sayaci_sifirlanir():
    hali = KanalHali()
    ilerle(hali, False, 0.0, 30)
    ilerle(hali, True, 20.0, 30)
    assert ilerle(hali, False, 25.0, 30) is None
    assert ilerle(hali, False, 54.0, 30) is None, "süre yeni aksaklıktan sayılır"
    assert ilerle(hali, False, 55.0, 30) == KOD_KOPTU


def test_bilinmiyor_olay_uretmez_ve_koptuyu_degistirmez():
    hali = KanalHali()
    assert ilerle(hali, True, 0.0, 30) is None
    assert ilerle(hali, None, 10.0, 30) is None
    assert hali.saglik == "unknown"
    koptu = KanalHali(hal=HAL_KOPTU, saglik="down")
    assert ilerle(koptu, None, 0.0, 30) is None
    assert (koptu.hal, koptu.saglik) == (HAL_KOPTU, "down"), "öğrenemedik ≠ düzeldi"


# ------------------------------------------------------------ yoklama


def _ses(device: str) -> dict:
    return {"kind": "ses_karti", "device": device}


def _cihazlar(*kimlikler: str) -> list[SesCihazi]:
    return [SesCihazi(kimlik=k, ad=k) for k in kimlikler]


def _yokla(kanal, cihazlar=(), secim=True, calici=True, platform="linux", **ek):
    return kanal_yokla(
        kanal, list(cihazlar), secim=secim, calici_var=calici, platform=platform, **ek
    )


def test_bos_cikis_adi_bilinmiyor_r37():
    """Varsayılan çıkış denetlenemez: "bağlı" demek yalan olurdu."""
    sonuc, neden = _yokla(_ses(""), _cihazlar(DAHILI))
    assert sonuc is None and "çıkış seçilmemiş" in neden


def test_bluetooth_sink_listede_yoksa_koptu_soneki_degistiyse_bagli():
    assert _yokla(_ses(BT), _cihazlar(DAHILI))[0] is False
    assert _yokla(_ses(BT), _cihazlar(DAHILI, BT))[0] is True
    # Yeniden bağlanan hoparlörün profil soneki değişebilir: aynı adres = aynı hoparlör
    assert _yokla(_ses(BT), _cihazlar(DAHILI, BT_YENI_SONEK))[0] is True


def test_calici_yoksa_koptu_liste_okunamazsa_bilinmiyor():
    assert _yokla(_ses(BT), _cihazlar(BT), calici=False)[0] is False
    assert _yokla(_ses(BT), ())[0] is None


def test_windows_her_zaman_bilinmiyor_macos_varsayilana_bakar():
    assert _yokla(_ses("Hoparlör"), platform="win32")[0] is None
    varsayilan = [SesCihazi(kimlik="JBL Flip", ad="JBL Flip", varsayilan=True)]
    assert _yokla(_ses("JBL Flip"), varsayilan, secim=False, platform="darwin")[0] is True
    assert _yokla(_ses("Dahili"), varsayilan, secim=False, platform="darwin")[0] is False
    assert _yokla(_ses("JBL Flip"), (), secim=False, platform="darwin")[0] is None


def test_ip_hoparlor_tcp_reddi_koptu_dinleyen_varsa_bagli():
    with socket.socket() as dinleyen:
        dinleyen.bind(("127.0.0.1", 0))
        dinleyen.listen(1)
        port = dinleyen.getsockname()[1]
        kanal = {"kind": "http", "address": f"http://127.0.0.1:{port}/anons"}
        assert _yokla(kanal)[0] is True
    # Soket kapandı: aynı port artık bağlantıyı reddeder
    sonuc, neden = _yokla(kanal)
    assert sonuc is False and "bağlantı kurulamadı" in neden


def test_ip_hoparlor_r30_reddi_koptu_sayilir():
    """Bu bilgisayarı gösteren adres yoklanmaz bile (SSRF, R30)."""
    kanal = {"kind": "http", "address": "http://127.0.0.1/anons"}
    sonuc, neden = _yokla(kanal, adres_dogrula=anons.hoparlor_adresini_dogrula)
    assert sonuc is False and neden


# ------------------------------------------------------------ yönetici


@pytest.fixture
def db(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    try:
        yield baglanti
    finally:
        baglanti.close()


def _kanal_ekle(db, kid: int, alan: str = "", tur: str = "http", **ek) -> dict:
    satir = {
        "id": kid,
        "name": ek.get("name", f"K{kid}"),
        "area": alan,
        "kind": tur,
        "address": ek.get("address", f"http://10.0.0.{kid}/anons" if tur == "http" else ""),
        "device": ek.get("device", ""),
        "enabled": ek.get("enabled", 1),
        "health": ek.get("health"),
    }
    db.execute(
        "INSERT INTO speaker_zones (id, name, area, address, kind, device, enabled, health, "
        "created_at, updated_at) VALUES (:id, :name, :area, :address, :kind, :device, "
        ":enabled, :health, '2026-09-23', '2026-09-23')",
        satir,
    )
    db.commit()
    return satir


@pytest.fixture
def yonetici(test_ayarlari, db):
    y = AnonsYoneticisi(test_ayarlari)
    yield y
    y.kapat(2.0)


@pytest.fixture
def yoklama(monkeypatch):
    """Kanal id → sıradaki yoklama sonucu; verilmeyen kanal "bağlı"."""
    sonuclar: dict[int, bool | None] = {}

    def _kanal_yokla(kanal, cihazlar, **_):
        sonuc = sonuclar.get(kanal["id"], True)
        return sonuc, "" if sonuc else "sahte sebep"

    monkeypatch.setattr(anons, "kanal_yokla", _kanal_yokla)
    return sonuclar


def _olaylar(db, kod: str) -> list[dict]:
    satirlar = db.execute(
        "SELECT * FROM events WHERE event_code = ? ORDER BY id", (kod,)
    ).fetchall()
    return [dict(s) for s in satirlar]


def _saglik(db, kid: int):
    return db.execute("SELECT health FROM speaker_zones WHERE id = ?", (kid,)).fetchone()[0]


def test_saglik_turu_koptu_ve_geldi_olaylari(yonetici, yoklama, db):
    _kanal_ekle(db, 1, name="Rampa hoparlörü")
    yonetici.saglik_turu(db, simdi=0.0)
    assert _saglik(db, 1) == "ok"
    yoklama[1] = False
    for t in (10.0, 20.0, 39.0):
        yonetici.saglik_turu(db, simdi=t)
    assert _olaylar(db, KOD_KOPTU) == [] and _saglik(db, 1) == "ok"
    yonetici.saglik_turu(db, simdi=40.0)
    (koptu,) = _olaylar(db, KOD_KOPTU)
    assert koptu["resolved_at"] is None, "koptu olayı SÜREN bir olaydır"
    assert "Rampa hoparlörü" in json.loads(koptu["details"])["mesaj"]
    assert _saglik(db, 1) == "down"
    yonetici.saglik_turu(db, simdi=50.0)
    assert len(_olaylar(db, KOD_KOPTU)) == 1
    yoklama[1] = True
    yonetici.saglik_turu(db, simdi=60.0)
    assert _olaylar(db, KOD_GELDI) == []
    yonetici.saglik_turu(db, simdi=70.0)
    assert len(_olaylar(db, KOD_GELDI)) == 1 and _saglik(db, 1) == "ok"
    (koptu,) = _olaylar(db, KOD_KOPTU)
    assert koptu["resolved_at"] is not None
    assert json.loads(koptu["details"])["kapanis_sebebi"] == "kosul_bitti"


def test_bilinmiyor_olay_yok_garanti_null(yonetici, yoklama, db):
    _kanal_ekle(db, 1)
    yoklama[1] = None
    for t in (0.0, 100.0):
        yonetici.saglik_turu(db, simdi=t)
    assert _olaylar(db, KOD_KOPTU) == [] and _saglik(db, 1) == "unknown"
    assert kanal_sagligi_ozeti(db, canli=True)["uyari_garantisi"] is None


def test_kapatilan_kanalin_acik_koptu_olayi_kapanir(yonetici, yoklama, db):
    _kanal_ekle(db, 1)
    yoklama[1] = False
    yonetici.saglik_turu(db, simdi=0.0)
    yonetici.saglik_turu(db, simdi=30.0)
    db.execute("UPDATE speaker_zones SET enabled = 0 WHERE id = 1")
    db.commit()
    yonetici.saglik_turu(db, simdi=40.0)
    (koptu,) = _olaylar(db, KOD_KOPTU)
    assert json.loads(koptu["details"])["kapanis_sebebi"] == "kanal_degisti"
    assert _saglik(db, 1) is None, "yeniden açılınca eski karar bayat görünmesin"


def test_cikisi_degisen_kanalin_eski_durumu_gecersiz(yonetici, yoklama, db):
    _kanal_ekle(db, 1)
    yoklama[1] = False
    yonetici.saglik_turu(db, simdi=0.0)
    yonetici.saglik_turu(db, simdi=30.0)
    db.execute("UPDATE speaker_zones SET address = 'http://10.0.0.99/a' WHERE id = 1")
    db.commit()
    yoklama[1] = True
    yonetici.saglik_turu(db, simdi=31.0)
    (koptu,) = _olaylar(db, KOD_KOPTU)
    assert json.loads(koptu["details"])["kapanis_sebebi"] == "kanal_degisti"
    assert _saglik(db, 1) == "ok", "yeni adres ilk yoklamada bağlı sayılır"


def test_acilis_onceki_kararla_baslar(yonetici, yoklama, db):
    """Açılışta sütundaki son karar korunur: ekran ve /saglik boşa düşmez."""
    _kanal_ekle(db, 1, health="ok")
    yoklama[1] = False
    yonetici.saglik_turu(db, simdi=0.0)
    assert _saglik(db, 1) == "ok"
    assert yonetici.kanal_halleri()[1] == ("ok", "sahte sebep")


# ------------------------------------------------------------ yönlendirme


@pytest.fixture
def http_calanlar(monkeypatch):
    """HTTP kanalına gidenleri (adres, metin) olarak kaydeder; `hatalar`daki adres düşer."""
    kayit: list[tuple[str, str]] = []
    hatalar: set[str] = set()

    def _cal(self, anahtar, metin, ses, kes=None):
        kayit.append((self._adres, metin))
        if self._adres in hatalar:
            raise AnonsHatasi("Anons adresine ulaşılamadı.")

    monkeypatch.setattr(anons.HttpAnonscu, "cal", _cal)
    kayit_ve_hatalar = (kayit, hatalar)
    return kayit_ve_hatalar


def _mesaj(mid: int = 1) -> dict:
    return {"id": mid, "key": "helmet", "text": f"Mesaj {mid}", "enabled": 1, "audio_file": None}


def _teslimler(db) -> list[tuple[int, str]]:
    satirlar = db.execute("SELECT speaker_zone_id, result FROM alert_deliveries ORDER BY id")
    return [(s["speaker_zone_id"], s["result"]) for s in satirlar]


def _yukle(yonetici, db) -> None:
    yonetici.bolgeleri_yukle(db.execute("SELECT * FROM speaker_zones ORDER BY id"))


def test_bolum_kanali_koptuysa_tum_fabrikaya_duser(yonetici, http_calanlar, db):
    kayit, _ = http_calanlar
    _kanal_ekle(db, 1, alan="Sevkiyat")
    _kanal_ekle(db, 2)  # Tüm fabrika
    _yukle(yonetici, db)
    yonetici._haller[1] = KanalHali(hal=HAL_KOPTU, saglik="down")
    yonetici.duyur(7, "Sevkiyat", 0.0, _mesaj(), olay=OlayBilgisi(olay_id=None, kod="HELMET"))
    assert yonetici.bosalt(5.0)
    assert [adres for adres, _ in kayit] == ["http://10.0.0.2/anons"]
    assert sorted(_teslimler(db)) == [(1, "fallback"), (2, "ok")]
    assert yonetici.ulasmiyor is False


def test_her_sey_koptuysa_yine_denenir(yonetici, http_calanlar, db):
    """Belki şimdi bağlanmıştır; denemenin sonucu kayda düşer."""
    kayit, _ = http_calanlar
    _kanal_ekle(db, 1, alan="Sevkiyat")
    _kanal_ekle(db, 2)
    _yukle(yonetici, db)
    for kid in (1, 2):
        yonetici._haller[kid] = KanalHali(hal=HAL_KOPTU, saglik="down")
    yonetici.duyur(7, "Sevkiyat", 0.0, _mesaj())
    assert yonetici.bosalt(5.0)
    assert [adres for adres, _ in kayit] == ["http://10.0.0.1/anons"]


# ------------------------------------------------------------ garanti


def test_kanal_yoksa_ulasmadi_kamera_basina_hiz_sinirli(yonetici, db):
    for _ in range(3):
        yonetici.duyur(7, "Sevkiyat", 0.0, _mesaj(), olay=OlayBilgisi(olay_id=None))
    assert yonetici.bosalt(5.0)
    assert yonetici.ulasmiyor is True
    (olay,) = _olaylar(db, "ALERT_UNDELIVERED")
    assert olay["camera_id"] is None or olay["camera_id"] == 7
    assert "sesli kanal tanımlı değil" in json.loads(olay["details"])["mesaj"]
    # Aralık dolunca aradaki iki uyarı sayılarak bir kayıt daha düşer
    yonetici._ulasmayan_son[7] -= yonetici._ulasmayan_araligi + 1
    yonetici.duyur(7, "Sevkiyat", 0.0, _mesaj())
    assert yonetici.bosalt(5.0)
    ilk, ikinci = _olaylar(db, "ALERT_UNDELIVERED")
    ayrinti = json.loads(ikinci["details"])
    assert ayrinti["arada_ulasmayan"] == 2 and "2 uyarı daha" in ayrinti["mesaj"]


def test_butun_kanallar_calamazsa_ulasmadi_sonra_duzelir(yonetici, http_calanlar, db):
    _, hatalar = http_calanlar
    _kanal_ekle(db, 1)
    _yukle(yonetici, db)
    hatalar.add("http://10.0.0.1/anons")
    yonetici.duyur(7, "", 0.0, _mesaj(1))
    assert yonetici.bosalt(5.0)
    assert yonetici.ulasmiyor is True
    assert len(_olaylar(db, "ALERT_UNDELIVERED")) == 1
    hatalar.clear()
    yonetici.duyur(7, "", 0.0, _mesaj(2))
    assert yonetici.bosalt(5.0)
    assert yonetici.ulasmiyor is False, "ulaşan uyarı bayrağı siler"


def test_bastirilan_uyari_ulasmis_sayilir(yonetici, http_calanlar, db):
    """Aynı anons o kanaldan az önce çaldı: garanti sağlanmıştır."""
    _kanal_ekle(db, 1)
    _yukle(yonetici, db)
    yonetici.duyur(7, "", 0.0, _mesaj())
    assert yonetici.bosalt(5.0)
    yonetici.duyur(7, "", 1.0, _mesaj())
    assert yonetici.bosalt(5.0)
    assert [r for _, r in _teslimler(db)] == ["ok", "suppressed_cooldown"]
    assert yonetici.ulasmiyor is False and _olaylar(db, "ALERT_UNDELIVERED") == []


def test_hatirlatma_ve_golge_garantiye_girmez(yonetici, http_calanlar, db):
    _, hatalar = http_calanlar
    _kanal_ekle(db, 1)
    _yukle(yonetici, db)
    hatalar.add("http://10.0.0.1/anons")
    yonetici.duyur(7, "", 0.0, _mesaj(), olay=OlayBilgisi(asama=ASAMA_HATIRLATMA))
    yonetici.golge_kaydet(7, "", _mesaj(2))
    assert yonetici.bosalt(5.0)
    assert yonetici.ulasmiyor is False and _olaylar(db, "ALERT_UNDELIVERED") == []


def test_basarili_kanal_denemesi_bayragi_siler(yonetici, http_calanlar, db):
    kanal = _kanal_ekle(db, 1)
    yonetici.ulasmiyor = True
    sonuc, _, _ = yonetici.kanali_dene(kanal, "deneme", "Deneme", None, zaman_asimi=5.0)
    assert sonuc == "ok" and yonetici.ulasmiyor is False


def test_supervizor_ulasmiyor_sorununu_bildirir(test_ayarlari):
    from app.analiz.supervizor import AnalizSupervizoru
    from app.web.rotalar import HAZIRLIGI_BOZAN_SORUNLAR

    supervizor = AnalizSupervizoru(test_ayarlari)
    try:
        assert "uyari_ulasmiyor" not in supervizor.sorunlar()
        supervizor._anons.ulasmiyor = True
        assert "uyari_ulasmiyor" in supervizor.sorunlar()
        assert "uyari_ulasmiyor" in HAZIRLIGI_BOZAN_SORUNLAR
    finally:
        supervizor._anons.kapat(1.0)


# ------------------------------------------------------------ özet ve /saglik


def test_kanal_yoksa_sesli_kanal_yok_ve_garanti_false(db):
    ozet = kanal_sagligi_ozeti(db, canli=True)
    assert (ozet["uyari_garantisi"], ozet["sorunlar"]) == (False, ["sesli_kanal_yok"])
    assert kanal_sagligi_ozeti(db, canli=False)["uyari_garantisi"] is False


def test_ekran_bagliyken_de_kanallar_olduyse_garanti_false(db):
    """Ekran garantiye sayılmaz (K21): izleme penceresi açık diye "sağlandı" denmez."""
    _kanal_ekle(db, 1, health="down")
    _kanal_ekle(db, 2, health="down")
    ekran.baglandi()
    try:
        assert kanal_sagligi_ozeti(db, canli=True)["uyari_garantisi"] is False
    finally:
        ekran.ayrildi()


def test_analiz_kapaliyken_garanti_dogrulanamaz(db):
    _kanal_ekle(db, 1, health="ok")
    assert kanal_sagligi_ozeti(db, canli=True)["uyari_garantisi"] is True
    ozet = kanal_sagligi_ozeti(db, canli=False)
    assert ozet["uyari_garantisi"] is None, "sütun önceki çalışmadan kalmadır"
    assert ozet["kanallar"] == [{"ad": "K1", "tur": "http", "saglik": None}]


def test_tek_bluetooth_kanali_kirmizi(db):
    _kanal_ekle(db, 1, tur="ses_karti", device=BT, health="ok")
    assert "tek_kanal_bluetooth" in kanal_sagligi_ozeti(db, canli=True)["sorunlar"]
    _kanal_ekle(db, 2, health="down")
    assert "tek_kanal_bluetooth" in kanal_sagligi_ozeti(db, canli=True)["sorunlar"], (
        "kopuk IP hoparlör yedek sayılmaz"
    )
    assert "tek_kanal_bluetooth" not in kanal_sagligi_ozeti(db, canli=False)["sorunlar"], (
        "analiz kapalıyken yalnız yapılandırmaya bakılır"
    )
    db.execute("UPDATE speaker_zones SET health = 'ok' WHERE id = 2")
    db.commit()
    assert "tek_kanal_bluetooth" not in kanal_sagligi_ozeti(db, canli=True)["sorunlar"]


def test_bolum_kanali_var_yedek_yoksa_sorun(db):
    _kanal_ekle(db, 1, alan="Sevkiyat", health="ok")
    assert kanal_sagligi_ozeti(db, canli=True)["sorunlar"] == ["yedek_ses_kanali_yok"]
    _kanal_ekle(db, 2, health="ok")
    assert kanal_sagligi_ozeti(db, canli=True)["sorunlar"] == []


class _HazirAnaliz:
    model_durumu = "hazir"

    def sorunlar(self) -> list[str]:
        return []

    def analiz_tur_yasi(self) -> float:
        return 0.1

    def kamera_saglik_ozeti(self) -> list[dict]:
        return []


@pytest.fixture
def analizli(istemci):
    istemci.app.state.supervizor = _HazirAnaliz()
    yield istemci
    istemci.app.state.supervizor = None


def test_saglik_dar_govdede_garanti_ve_kanal_sorunlari(analizli, db):
    govde = analizli.get("/saglik").json()
    assert govde["uyari_garantisi"] is False and "sesli_kanal_yok" in govde["sorunlar"]
    assert govde["hazir"] is True, "yapılandırma eksiği hazırlığı bozmaz; kırmızı görünür"
    _kanal_ekle(db, 1, tur="ses_karti", device=BT, health="ok")
    govde = analizli.get("/saglik").json()
    assert govde["uyari_garantisi"] is True
    assert govde["sorunlar"] == ["tek_kanal_bluetooth"]
    assert "kanallar" not in govde, "kanal adları yalnız oturumlu ayrıntıda"


def test_saglik_ayrintisinda_kanallar(analizli, db):
    _kanal_ekle(db, 1, name="Rampa hoparlörü", alan="Sevkiyat", health="down")
    _kanal_ekle(db, 2, name="Tüm fabrika", health="unknown")
    govde = analizli.get("/saglik?ayrinti=1").json()
    assert govde["kanallar"] == [
        {"ad": "Rampa hoparlörü", "tur": "http", "saglik": "down"},
        {"ad": "Tüm fabrika", "tur": "http", "saglik": "unknown"},
    ]
    assert govde["uyari_garantisi"] is None, "biri bilinmiyorsa doğrulanamaz"


def test_analiz_kapaliyken_saglik_garantisi(istemci, db):
    assert istemci.get("/saglik").json()["uyari_garantisi"] is False  # kanal yok
    _kanal_ekle(db, 1, health="ok")
    assert istemci.get("/saglik").json()["uyari_garantisi"] is None

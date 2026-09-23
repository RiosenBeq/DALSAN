"""Uyarı dağıtıcısı (docs/17 §7.3; Faz 4a-3).

Her çıkışın tek işçisi ve öncelikli kuyruğu vardır; kritik uyarı çalan düşük
öncelikli sesi keser; bayat öğe çalınmaz; bastırma yalnız başarılı çalmada
tükenir; kritik bir açılış bastırılmaz; her deneme `alert_deliveries`'e yazılır.
Gerçek ses ÇALINMAZ: çalıcı ve HTTP sahte fonksiyonlarla değiştirilir.
"""

from __future__ import annotations

import subprocess
import threading
import time

import pytest

from app import veritabani
from app.olaylar import anons, ekran, ton
from app.olaylar.anons import AnonsHatasi, AnonsYoneticisi, OlayBilgisi
from app.olaylar.dagitici import CikisIscisi, UyariOgesi
from app.olaylar.teslim import teslim_ozeti


def _kanal(kid: int, alan: str = "", tur: str = "http", acik: int = 1, **ek) -> dict:
    return {
        "id": kid,
        "name": f"K{kid}",
        "area": alan,
        "kind": tur,
        "address": ek.get("address", f"http://10.0.0.{kid}/anons"),
        "device": ek.get("device", ""),
        "enabled": acik,
    }


def _mesaj(mid: int = 1, anahtar: str = "helmet", ses: str | None = None) -> dict:
    return {"id": mid, "key": anahtar, "text": f"Mesaj {mid}", "enabled": 1, "audio_file": ses}


@pytest.fixture
def db(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    for kid in range(1, 6):
        baglanti.execute(
            "INSERT INTO speaker_zones (id, name, area, address, enabled, created_at, "
            "updated_at) VALUES (?, ?, '', 'http://10.0.0.1/a', 1, '2026-09-23', '2026-09-23')",
            (kid, f"K{kid}"),
        )
    baglanti.commit()
    try:
        yield baglanti
    finally:
        baglanti.close()


def _teslimler(db) -> list[dict]:
    return [dict(s) for s in db.execute("SELECT * FROM alert_deliveries ORDER BY id")]


@pytest.fixture
def yonetici(test_ayarlari, db):
    y = AnonsYoneticisi(test_ayarlari)
    yield y
    y.kapat(2.0)


@pytest.fixture
def http_calanlar(monkeypatch):
    """HTTP kanalına gidenleri sırayla kaydeder; `hata` kümesindekiler başarısız."""
    kayit: list[str] = []
    hatalar: set[str] = set()

    def _cal(self, anahtar, metin, ses, kes=None):
        kayit.append(metin)
        if metin in hatalar:
            hatalar.discard(metin)
            raise AnonsHatasi("Anons adresine ulaşılamadı.")

    monkeypatch.setattr(anons.HttpAnonscu, "cal", _cal)
    return kayit, hatalar


# ------------------------------------------------------------ kuyruk


def test_oncelik_once_onem_sonra_giris_sirasi():
    sira: list[str] = []
    basladi, birak = threading.Event(), threading.Event()

    def isle(oge, kes):
        if oge.anahtar == "ilk":
            basladi.set()
            birak.wait(5)
        sira.append(oge.anahtar)
        oge.sonuc = "ok"

    isci = CikisIscisi("t", isle, lambda oge: None, bekleme_sn=60)
    isci.ekle(UyariOgesi(kanal={}, anahtar="ilk", metin="", onem="critical"))
    assert basladi.wait(5)
    for ad, onem in (
        ("dusuk", "low"),
        ("orta1", "medium"),
        ("yuksek", "high"),
        ("orta2", "medium"),
        ("kritik", "critical"),
    ):
        isci.ekle(UyariOgesi(kanal={}, anahtar=ad, metin="", onem=onem))
    birak.set()
    assert isci.bosalt(5)
    assert sira == ["ilk", "kritik", "yuksek", "orta1", "orta2", "dusuk"]
    isci.durdur(1)


def test_deneme_gercek_uyarinin_onune_gecmez():
    sira: list[str] = []
    basladi, birak = threading.Event(), threading.Event()

    def isle(oge, kes):
        if oge.anahtar == "ilk":
            basladi.set()
            birak.wait(5)
        sira.append(oge.anahtar)

    isci = CikisIscisi("t", isle, lambda oge: None, bekleme_sn=60)
    isci.ekle(UyariOgesi(kanal={}, anahtar="ilk", metin="", onem="critical"))
    assert basladi.wait(5)
    isci.ekle(UyariOgesi(kanal={}, anahtar="deneme", metin="", onem="critical", asama="test"))
    isci.ekle(UyariOgesi(kanal={}, anahtar="dusuk", metin="", onem="low"))
    birak.set()
    assert isci.bosalt(5)
    assert sira == ["ilk", "dusuk", "deneme"]
    isci.durdur(1)


def test_bayat_oge_calinmaz_kritik_calinir():
    calinan: list[str] = []
    birak = threading.Event()

    def isle(oge, kes):
        if oge.anahtar == "ilk":
            birak.wait(5)
        calinan.append(oge.anahtar)
        oge.sonuc = "ok"

    bitenler: list[UyariOgesi] = []
    isci = CikisIscisi("t", isle, bitenler.append, bekleme_sn=0.2)
    isci.ekle(UyariOgesi(kanal={}, anahtar="ilk", metin="", onem="critical"))
    isci.ekle(UyariOgesi(kanal={}, anahtar="orta", metin="", onem="medium"))
    isci.ekle(UyariOgesi(kanal={}, anahtar="kritik", metin="", onem="critical"))
    time.sleep(0.4)
    birak.set()
    assert isci.bosalt(5)
    assert calinan == ["ilk", "kritik"]
    sonuclar = {o.anahtar: o.sonuc for o in bitenler}
    assert sonuclar == {"ilk": "ok", "kritik": "ok", "orta": "stale"}
    isci.durdur(1)


def test_ayni_cikista_tek_ses_farkli_cikislar_beklemez(yonetici, monkeypatch):
    """İki bölümün satırı aynı ses çıkışını gösteriyor: sesleri sıraya girer.
    IP hoparlör ayrı çıkıştır, onları beklemez."""
    kilit = threading.Lock()
    aktif = {"toplam": 0, "d1": 0}
    en_cok = {"toplam": 0, "d1": 0}

    def _cal(cikis):
        def cal(self, anahtar, metin, ses, kes=None):
            with kilit:
                for k in ("toplam", cikis):
                    if k in aktif:
                        aktif[k] += 1
                        en_cok[k] = max(en_cok[k], aktif[k])
            time.sleep(0.2)
            with kilit:
                for k in ("toplam", cikis):
                    if k in aktif:
                        aktif[k] -= 1

        return cal

    monkeypatch.setattr(anons.SesKartiAnonscu, "cal", _cal("d1"))
    monkeypatch.setattr(anons.HttpAnonscu, "cal", _cal("http"))
    yonetici.bolgeleri_yukle(
        [
            _kanal(1, "A", "ses_karti", device="d1"),
            _kanal(2, "B", "ses_karti", device="d1"),
            _kanal(3, "C"),
        ]
    )
    yonetici.duyur(1, "A", 0.0, _mesaj(1))
    yonetici.duyur(2, "B", 0.0, _mesaj(1))
    yonetici.duyur(3, "C", 0.0, _mesaj(1))
    assert yonetici.bosalt()
    assert en_cok["d1"] == 1, "aynı çıkışta iki ses üst üste bindi"
    assert en_cok["toplam"] >= 2, "farklı çıkışlar birbirini bekledi"


def test_ayni_cikisa_giden_iki_satir_tek_ses(yonetici, http_calanlar, db):
    calinanlar, _ = http_calanlar
    yonetici.bolgeleri_yukle(
        [_kanal(1, address="http://10.0.0.9/a"), _kanal(2, address="http://10.0.0.9/a")]
    )
    yonetici.duyur(7, "", 0.0, _mesaj(1))
    assert yonetici.bosalt()
    assert calinanlar == ["Mesaj 1"]


# ------------------------------------------------------------ kesme


class _SahtePopen:
    """Dosya adına göre çalma süresi olan sahte çalıcı süreci."""

    SURELER = {"orta.wav": 10.0, "kritik.wav": 0.05}
    ornekler: list[_SahtePopen] = []

    def __init__(self, komut, **_):
        self.komut = komut
        self.returncode: int | None = None
        self.sonlandirildi = threading.Event()
        self._bitis = time.monotonic() + self.SURELER.get(komut[-1].rsplit("/", 1)[-1], 0.05)
        _SahtePopen.ornekler.append(self)

    def communicate(self, timeout=None):
        kalan = max(0.0, self._bitis - time.monotonic())
        if self.sonlandirildi.wait(min(timeout if timeout is not None else kalan, kalan)):
            self.returncode = -15
            return b"", b""
        if time.monotonic() >= self._bitis:
            self.returncode = 0
            return b"", b""
        raise subprocess.TimeoutExpired(self.komut, timeout)

    def terminate(self):
        self.sonlandirildi.set()

    kill = terminate


def test_kritik_uyari_calan_orta_sesi_keser(test_ayarlari, db, monkeypatch):
    _SahtePopen.ornekler = []
    # Dosyalar diskte olmalı: olmayan dosyanın yerine uyarı tonu çalar
    for ad in _SahtePopen.SURELER:
        (test_ayarlari.kok_dizin / ad).write_bytes(b"RIFF")
    monkeypatch.setattr(anons, "_ses_komutu", lambda ses, cihaz="": ["paplay", ses])
    monkeypatch.setattr(anons.subprocess, "Popen", _SahtePopen)
    yonetici = AnonsYoneticisi(test_ayarlari)
    try:
        yonetici.bolgeleri_yukle([_kanal(1, "", "ses_karti", device="d1")])
        yonetici.duyur(1, "", 0.0, _mesaj(1, ses="orta.wav"), olay=OlayBilgisi(onem="medium"))
        son = time.monotonic() + 5
        while not _SahtePopen.ornekler and time.monotonic() < son:
            time.sleep(0.01)
        yonetici.duyur(2, "", 0.0, _mesaj(2, ses="kritik.wav"), olay=OlayBilgisi(onem="critical"))
        assert yonetici.bosalt()
    finally:
        yonetici.kapat(1)
    orta, kritik = _SahtePopen.ornekler
    assert orta.sonlandirildi.is_set()
    assert not kritik.sonlandirildi.is_set()
    sonuclar = [(t["event_code"], t["result"]) for t in _teslimler(db)]
    assert [s for _, s in sonuclar] == ["preempted", "ok"]
    assert "KESİLDİ" in yonetici.son_sonuc or "ÇALINDI" in yonetici.son_sonuc


# ------------------------------------------------------------ bastırma


def test_basarisiz_calmada_bastirma_tukenmez(yonetici, http_calanlar, db):
    """R20: çalamayan hoparlör bir sonraki ihlalde yeniden denenir."""
    calinanlar, hatalar = http_calanlar
    yonetici.bolgeleri_yukle([_kanal(1)])
    hatalar.add("Mesaj 1")
    yonetici.duyur(7, "", 0.0, _mesaj(1))
    assert yonetici.bosalt()
    yonetici.duyur(7, "", 1.0, _mesaj(1))  # bekleme süresi (30 sn) içinde
    assert yonetici.bosalt()
    yonetici.duyur(7, "", 2.0, _mesaj(1))  # ikincisi çaldı: bu bastırılır
    assert yonetici.bosalt()
    assert calinanlar == ["Mesaj 1", "Mesaj 1"]
    assert [t["result"] for t in _teslimler(db)] == ["failed", "ok", "suppressed_cooldown"]


def test_ikinci_ayri_kritik_acilis_bastirilmaz(yonetici, http_calanlar, db):
    calinanlar, _ = http_calanlar
    yonetici.bolgeleri_yukle([_kanal(1)])
    kritik = OlayBilgisi(onem="critical", asama="acildi", kod="VEHICLE_PERSON_PROXIMITY")
    for zaman_s in (0.0, 1.0):
        yonetici.duyur(7, "", zaman_s, _mesaj(1), olay=kritik)
        assert yonetici.bosalt()
    # Aynı anahtarın kritik olmayan uyarısı az önce çalanın ardından susar
    yonetici.duyur(7, "", 2.0, _mesaj(1), olay=OlayBilgisi(onem="medium"))
    # Kritik HATIRLATMA muaf değildir
    yonetici.duyur(7, "", 3.0, _mesaj(1), olay=OlayBilgisi(onem="critical", asama="hatirlatma"))
    assert yonetici.bosalt()
    assert calinanlar == ["Mesaj 1", "Mesaj 1"]
    assert [t["result"] for t in _teslimler(db)] == [
        "ok",
        "ok",
        "suppressed_cooldown",
        "suppressed_cooldown",
    ]


def test_bastirma_kanal_basinadir(yonetici, http_calanlar, db):
    """Bir kanaldaki bastırma öbür kanalı susturmaz."""
    calinanlar, _ = http_calanlar
    yonetici.bolgeleri_yukle([_kanal(1, "A")])
    yonetici.duyur(7, "A", 0.0, _mesaj(1))
    assert yonetici.bosalt()
    yonetici.bolgeleri_yukle([_kanal(1, "A"), _kanal(2, "A")])
    yonetici.duyur(7, "A", 1.0, _mesaj(1))
    assert yonetici.bosalt()
    assert len(calinanlar) == 2
    assert sorted((t["speaker_zone_id"], t["result"]) for t in _teslimler(db)) == [
        (1, "ok"),
        (1, "suppressed_cooldown"),
        (2, "ok"),
    ]


# ------------------------------------------------------------ teslim kaydı


def test_olay_yazilamadiginda_teslim_event_id_bos(yonetici, http_calanlar, db):
    """Fail-safe (docs/17 §3.5): olay satırı yazılamasa da uyarı çalar ve iz kalır."""
    yonetici.bolgeleri_yukle([_kanal(1)])
    yonetici.duyur(
        7, "", 0.0, _mesaj(1), olay=OlayBilgisi(olay_id=None, kod="RESTRICTED_ENTRY", onem="high")
    )
    assert yonetici.bosalt()
    [satir] = _teslimler(db)
    assert satir["event_id"] is None
    assert (satir["event_code"], satir["channel"], satir["stage"], satir["result"]) == (
        "RESTRICTED_ENTRY",
        "http",
        "acildi",
        "ok",
    )
    assert satir["started_at"] and satir["finished_at"]


def test_kare_zamanindan_baslamaya_gecikme_yazilir(yonetici, http_calanlar, db):
    yonetici.bolgeleri_yukle([_kanal(1)])
    kare = time.monotonic() - 0.25
    yonetici.duyur(7, "", 0.0, _mesaj(1), olay=OlayBilgisi(kare_zamani=kare))
    assert yonetici.bosalt()
    [satir] = _teslimler(db)
    assert 250 <= satir["frame_to_start_ms"] < 5000


def test_golge_kural_calmaz_calsaydi_diye_yazilir(yonetici, http_calanlar, db):
    calinanlar, _ = http_calanlar
    yonetici.bolgeleri_yukle([_kanal(1), _kanal(2, address="http://10.0.0.8/b")])
    yonetici.golge_kaydet(7, "", _mesaj(1), olay=OlayBilgisi(kod="PPE_NO_HELMET"))
    assert yonetici.bosalt()
    assert calinanlar == []
    assert [(t["speaker_zone_id"], t["result"]) for t in _teslimler(db)] == [
        (1, "shadow"),
        (2, "shadow"),
    ]


def test_ekran_kanali_dinleyeni_yazar(yonetici, db):
    yonetici.ekran_kaydet(OlayBilgisi(kod="RESTRICTED_ENTRY"))
    ekran.baglandi()
    try:
        yonetici.ekran_kaydet(OlayBilgisi(kod="RESTRICTED_ENTRY"))
    finally:
        ekran.ayrildi()
    assert yonetici.bosalt()
    assert [(t["channel"], t["result"]) for t in _teslimler(db)] == [
        ("ekran", "no_listener"),
        ("ekran", "ok"),
    ]


def test_ses_dosyasi_proje_disindaysa_o_dosya_calinmaz_uyari_tonu_calar(yonetici, monkeypatch, db):
    """Proje dışındaki yol ÇALINMAZ (güvenlik); ama hoparlör de susmaz: sözlü
    anons yerine uyarı tonu çalar (operatör isteği 23.09.2026)."""
    http: list[str] = []
    calinan: list[str] = []
    monkeypatch.setattr(anons.HttpAnonscu, "cal", lambda self, a, m, s, kes=None: http.append(m))
    monkeypatch.setattr(
        anons.SesKartiAnonscu, "cal", lambda self, a, m, ses, kes=None: calinan.append(ses)
    )
    yonetici.bolgeleri_yukle([_kanal(1, "A", "ses_karti", device="d1"), _kanal(2, "A")])
    yonetici.duyur(7, "A", 0.0, _mesaj(1, ses="../../disari.wav"))
    assert yonetici.bosalt()
    assert http == ["Mesaj 1"]
    assert calinan == [str(ton.uyari_tonu_yolu())]
    sonuclar = {t["speaker_zone_id"]: (t["result"], t["detail"]) for t in _teslimler(db)}
    assert sonuclar[2] == ("ok", None)
    assert sonuclar[1][0] == "ok"
    assert "proje klasörünün dışında" in sonuclar[1][1] and "uyarı tonu" in sonuclar[1][1]


@pytest.mark.parametrize("ses", [None, "veri/sesler/olmayan.wav"])
def test_ses_dosyasi_yoksa_hoparlor_susmaz_uyari_tonu_calar(yonetici, monkeypatch, db, ses):
    """Operatör isteği (23.09.2026): risk anında hoparlör uyarı versin. Mesaja
    WAV bağlanmamışsa ya da dosya diskte yoksa eskiden ses çıkışı kanalı susar
    ve uyarı "ulaşmadı" sayılırdı; şimdi üretilmiş uyarı tonu çalar."""
    calinan: list[str] = []
    monkeypatch.setattr(
        anons.SesKartiAnonscu, "cal", lambda self, a, m, s, kes=None: calinan.append(s)
    )
    yonetici.bolgeleri_yukle([_kanal(1, "", "ses_karti", device="d1")])
    yonetici.duyur(7, "", 0.0, _mesaj(1, ses=ses), olay=OlayBilgisi(onem="critical"))
    assert yonetici.bosalt()
    assert calinan == [str(ton.uyari_tonu_yolu())]
    (teslim,) = _teslimler(db)
    assert teslim["result"] == "ok"
    assert "uyarı tonu çalındı" in teslim["detail"]
    assert not yonetici.ulasmiyor
    assert "uyarı tonu" in yonetici.son_sonuc


def test_ton_da_uretilemezse_kanal_basarisiz_ve_sebep_yazilir(yonetici, monkeypatch, db):
    def uretilemez():
        raise OSError("disk dolu")

    monkeypatch.setattr(anons, "uyari_tonu_yolu", uretilemez)
    monkeypatch.setattr(anons.SesKartiAnonscu, "cal", lambda *a, **k: pytest.fail("çalınmamalı"))
    yonetici.bolgeleri_yukle([_kanal(1, "", "ses_karti", device="d1")])
    yonetici.duyur(7, "", 0.0, _mesaj(1))
    assert yonetici.bosalt()
    (teslim,) = _teslimler(db)
    assert teslim["result"] == "failed"
    assert "bağlanmamış" in teslim["detail"] and "disk dolu" in teslim["detail"]


def test_kapanista_sira_bosaltilir_sonra_calmaz(test_ayarlari, db, monkeypatch):
    calinan: list[str] = []

    def yavas(self, anahtar, metin, ses, kes=None):
        time.sleep(0.05)
        calinan.append(metin)

    monkeypatch.setattr(anons.HttpAnonscu, "cal", yavas)
    yonetici = AnonsYoneticisi(test_ayarlari)
    yonetici.bolgeleri_yukle([_kanal(1)])
    for mid in (1, 2, 3):
        yonetici.duyur(mid, "", 0.0, _mesaj(mid))
    yonetici.kapat(3.0)
    assert sorted(calinan) == ["Mesaj 1", "Mesaj 2", "Mesaj 3"]
    yonetici.duyur(9, "", 0.0, _mesaj(9))
    assert "Mesaj 9" not in calinan


def test_teslim_ozeti_orani_ve_gecikmeyi_verir(db):
    from app import zaman

    simdi = zaman.simdi_utc()
    satirlar = [
        ("http", "acildi", "ok", 100),
        ("http", "acildi", "ok", 300),
        ("ses_karti", "hatirlatma", "failed", None),
        ("http", "acildi", "suppressed_cooldown", None),
        ("http", "test", "ok", None),
        ("ekran", "acildi", "no_listener", None),
    ]
    for kanal, asama, sonuc, ms in satirlar:
        db.execute(
            "INSERT INTO alert_deliveries (channel, stage, result, queued_at, "
            "frame_to_start_ms) VALUES (?, ?, ?, ?, ?)",
            (kanal, asama, sonuc, simdi, ms),
        )
    db.commit()
    ozet = teslim_ozeti(db)
    assert (ozet["deneme"], ozet["caldi"]) == (3, 2)  # bastırılan ve test sayılmaz
    assert ozet["oran"] == pytest.approx(2 / 3)
    assert (ozet["p50_ms"], ozet["p90_ms"]) == (200, 280)
    assert (ozet["ekran_olay"], ozet["ekran_dinleyen_yok"]) == (1, 1)


def test_teslim_yoksa_oran_olculemedi(db):
    ozet = teslim_ozeti(db)
    assert ozet["oran"] is None and ozet["p50_ms"] is None

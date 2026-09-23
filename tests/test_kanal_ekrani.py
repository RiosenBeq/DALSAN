"""Komuta → Anons: uyarı kanalı ekranı ve formu (docs/17 §7.2, §7.5, §7.8; K22).

Kanal yapılandırmasının tek yeri bu ekrandır: her satır ya bu bilgisayarın
bir ses çıkışı (kablolu amfi ya da Bluetooth hoparlör) ya da bir IP
hoparlördür. Gerçek ses ÇALINMAZ: ses çıkışlarının listesi ve test sesi
sahte fonksiyonlarla değiştirilir.
"""

from __future__ import annotations

import re

import pytest

from app import veritabani
from app.olaylar import ses_cihazlari, test_sesi

DAHILI = "alsa_output.pci-0000_00_1f.3.analog-stereo"
BLUETOOTH = "bluez_output.AA_BB_CC_DD_EE_FF.1"
BAGLI = [
    ses_cihazlari.SesCihazi(kimlik=DAHILI, ad="Dahili ses", varsayilan=True),
    ses_cihazlari.SesCihazi(kimlik=BLUETOOTH, ad="JBL Charge", bluetooth=True),
]


@pytest.fixture
def linux(monkeypatch):
    """Çıkışın programdan seçilebildiği platform (fabrika sunucusu)."""
    monkeypatch.setattr(ses_cihazlari, "secim_destekleniyor_mu", lambda: True)
    monkeypatch.setattr(ses_cihazlari, "cihazlari_listele", lambda: list(BAGLI))


def _kanal_ekle(istemci, **alanlar):
    veri = {"name": "Genel", "area": "", "kind": "ses_karti", "enabled": "1", **alanlar}
    return istemci.post("/hoparlorler/kaydet", data=veri, follow_redirects=False)


def _satirlar(test_ayarlari) -> list[dict]:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        return [dict(s) for s in baglanti.execute("SELECT * FROM speaker_zones ORDER BY id")]
    finally:
        baglanti.close()


def _liste_satiri(metin: str, sira: int = 1) -> str:
    """Kanal listesinin `sira`'ncı satırı (düzenleme formu hariç)."""
    return metin.split('class="hoparlor-satiri"')[sira].split("<details")[0]


# ------------------------------------------------------------------ kayıt


def test_ses_cikisi_kanali_kaydedilir(istemci, test_ayarlari, linux):
    # Formda iki alan da gönderilir (tür seçimi yalnız görünürlüğü değiştirir);
    # türe uymayan adres yok sayılır.
    yanit = _kanal_ekle(istemci, device=BLUETOOTH, address="http://10.0.0.9/anons")
    assert yanit.status_code == 303
    [satir] = _satirlar(test_ayarlari)
    assert (satir["kind"], satir["device"], satir["address"]) == ("ses_karti", BLUETOOTH, "")

    liste = _liste_satiri(istemci.get("/komuta/anons").text)
    assert f"Tüm fabrika · ses çıkışı · {BLUETOOTH}" in liste
    assert '<span class="rozet yesil">açık</span>' in liste


def test_linuxta_cikis_bos_birakilamaz(istemci, test_ayarlari, linux):
    """'Varsayılan çıkış' denetlenemez: Bluetooth koparsa ses sessizce
    bilgisayarın kendi hoparlörüne gider (docs/17 §7.2, R37)."""
    yanit = _kanal_ekle(istemci, device="  ")
    assert yanit.status_code == 400
    assert "Ses çıkışını seçin" in yanit.json()["hata"]
    assert _satirlar(test_ayarlari) == []


def test_mac_ve_windowsta_cikis_bos_kalabilir(istemci, test_ayarlari, monkeypatch):
    """Orada çıkış işletim sisteminden seçilir; alan zorunlu değildir ve
    ekran çıkış adına bakıp bir şey iddia etmez (docs/17 §7.7)."""
    monkeypatch.setattr(ses_cihazlari, "secim_destekleniyor_mu", lambda: False)
    monkeypatch.setattr(ses_cihazlari, "cihazlari_listele", lambda: list(BAGLI))
    assert _kanal_ekle(istemci, device="").status_code == 303
    metin = istemci.get("/komuta/anons").text
    liste = _liste_satiri(metin)
    assert "işletim sisteminin varsayılan çıkışı" in liste
    assert '<span class="rozet yesil">açık</span>' in liste
    assert "işletim sisteminin ses ayarlarından seçilir" in metin


def test_cikis_adi_tek_satir_olmali(istemci, test_ayarlari, linux):
    yanit = _kanal_ekle(istemci, device="bluez_output.AA\nYONETICI_SIFRESI=")
    assert yanit.status_code == 400
    assert _satirlar(test_ayarlari) == []


def test_ip_hoparlore_gecince_cikis_adi_silinir(istemci, test_ayarlari, linux):
    _kanal_ekle(istemci, device=BLUETOOTH)
    [satir] = _satirlar(test_ayarlari)
    yanit = _kanal_ekle(
        istemci, hoparlor_id=str(satir["id"]), kind="http", address="http://10.0.0.9/anons"
    )
    assert yanit.status_code == 303
    [satir] = _satirlar(test_ayarlari)
    assert (satir["kind"], satir["device"], satir["address"]) == (
        "http",
        "",
        "http://10.0.0.9/anons",
    )


def test_ip_hoparlor_adresi_yine_dogrulanir(istemci, test_ayarlari, linux):
    yanit = _kanal_ekle(istemci, kind="http", address="")
    assert yanit.status_code == 400
    assert "adresi boş olamaz" in yanit.json()["hata"]


def test_bilinmeyen_tur_reddedilir(istemci, test_ayarlari, linux):
    assert _kanal_ekle(istemci, kind="webhook", device=DAHILI).status_code == 400
    assert _satirlar(test_ayarlari) == []


# ------------------------------------------------------------------- form


def test_formda_bagli_cikislar_ve_varsayilan_onceden_secili(istemci, linux):
    """Bağlı çıkışlar öneri olarak listelenir, o anki varsayılan önceden
    yazılı gelir (docs/17 §7.5-1); ad yine elle yazılabilir."""
    metin = istemci.get("/komuta/anons").text
    assert f'name="device" value="{DAHILI}"' in metin
    assert f'<option value="{BLUETOOTH}">JBL Charge · Bluetooth</option>' in metin
    assert f'<option value="{DAHILI}">Dahili ses · varsayılan</option>' in metin
    # Çıkış bulunan bilgisayarda yeni kanalın türü önce ses çıkışıdır
    assert re.search(r'value="ses_karti"\s+checked', metin)


def test_cikis_listesi_yoksa_ip_hoparlor_onde_ve_not_var(istemci, monkeypatch):
    monkeypatch.setattr(ses_cihazlari, "secim_destekleniyor_mu", lambda: True)
    monkeypatch.setattr(ses_cihazlari, "cihazlari_listele", list)
    metin = istemci.get("/komuta/anons").text
    assert re.search(r'value="http"\s+checked', metin)
    assert "Çıkış listesi okunamadı" in metin


# ------------------------------------------------------------ anlık durum


def test_gorunmeyen_cikis_kirmizi_ve_uyarili(istemci, test_ayarlari, linux):
    """Bluetooth hoparlör kapandığında anons o kanaldan duyulmaz; ekran bunu
    kanalın kendi satırında ve panelin başında söyler."""
    _kanal_ekle(istemci, device="bluez_output.11_22_33_44_55_66.1")
    metin = istemci.get("/komuta/anons").text
    assert "Bir uyarı kanalı çalışmıyor" in metin
    liste = _liste_satiri(metin)
    assert '<span class="rozet kirmizi">görünmüyor</span>' in liste
    assert "bu kanaldan anons duyulmaz" in liste


def test_liste_okunamazsa_gorunmuyor_denmez(istemci, test_ayarlari, monkeypatch):
    """'Kontrol edemedik' ile 'koptu' aynı şey değildir."""
    monkeypatch.setattr(ses_cihazlari, "secim_destekleniyor_mu", lambda: True)
    monkeypatch.setattr(ses_cihazlari, "cihazlari_listele", list)
    _kanal_ekle(istemci, device=BLUETOOTH)
    metin = istemci.get("/komuta/anons").text
    assert "görünmüyor" not in metin
    # R38: bilinmeyen durum yeşil "açık" rozetiyle bağlı gibi de görünmez
    assert '<span class="rozet gri">bilinmiyor</span>' in _liste_satiri(metin)


def test_eski_bos_cikisli_satir_uyarir(istemci, test_ayarlari, linux):
    """.env'den aktarılmış, çıkış adı boş satır (ANONS_SES_CIHAZI boştu)."""
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        baglanti.execute(
            "INSERT INTO speaker_zones (name, area, address, kind, device, enabled, "
            "created_at, updated_at) VALUES ('Tüm fabrika', '', '', 'ses_karti', '', 1, "
            "'2026-09-23T08:00:00+00:00', '2026-09-23T08:00:00+00:00')"
        )
        baglanti.commit()
    finally:
        baglanti.close()
    liste = _liste_satiri(istemci.get("/komuta/anons").text)
    assert '<span class="rozet sari">çıkış seçilmedi</span>' in liste
    assert "eski kayıt" in liste


def test_kapali_kanal_gri(istemci, test_ayarlari, linux):
    _kanal_ekle(istemci, device=BLUETOOTH, enabled="0")
    metin = istemci.get("/komuta/anons").text
    assert '<span class="rozet gri">kapalı</span>' in _liste_satiri(metin)
    assert "Hepsi kapalı" in metin  # özet kutusu: satır var ama hiçbiri açık değil


def test_bolum_kanali_var_tum_fabrika_yoksa_ozet_uyarir(istemci, test_ayarlari, linux):
    _kanal_ekle(istemci, name="Rampa", area="Sevkiyat", device=BLUETOOTH)
    metin = istemci.get("/komuta/anons").text
    assert "1 açık" in metin
    assert "bölümünde kanal olmayan olay sesli duyurulmaz" in metin


# ------------------------------------------------------------------- dene


def test_dene_ses_cikisinda_satirin_cikisina_calar(istemci, test_ayarlari, linux, monkeypatch):
    """R39: test sesi bellekteki eski ayara değil, kaydedilmiş satırın
    çıkışına çalar."""
    calinan: list[str] = []
    monkeypatch.setattr(test_sesi, "cal", lambda cihaz="": calinan.append(cihaz) or "")
    _kanal_ekle(istemci, device=BLUETOOTH)
    [satir] = _satirlar(test_ayarlari)
    yanit = istemci.post(f"/hoparlorler/{satir['id']}/dene", follow_redirects=False)
    assert yanit.status_code == 303
    assert calinan == [BLUETOOTH]
    assert _satirlar(test_ayarlari)[0]["last_announced_at"]


def test_dene_hatasi_kanal_adiyla_turkce(istemci, test_ayarlari, linux, monkeypatch):
    monkeypatch.setattr(test_sesi, "cal", lambda cihaz="": "Ses çalıcı bulunamadı.")
    _kanal_ekle(istemci, name="Rampa hoparlörü", device=BLUETOOTH)
    [satir] = _satirlar(test_ayarlari)
    yanit = istemci.post(f"/hoparlorler/{satir['id']}/dene")
    assert yanit.status_code == 400
    hata = yanit.json()["hata"]
    assert "Rampa hoparlörü" in hata and "Ses çalıcı bulunamadı." in hata
    assert _satirlar(test_ayarlari)[0]["last_announced_at"] is None


# ------------------------------------------------------------ teslim kaydı


def test_deneme_teslim_kaydina_test_diye_yazilir(istemci, test_ayarlari, monkeypatch):
    """Analiz kapalıyken deneme doğrudan çalar ve kaydı web isteği yazar."""
    import urllib.request

    class _Yanit:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Yanit())
    _kanal_ekle(istemci, kind="http", address="http://10.0.0.9/anons")
    [satir] = _satirlar(test_ayarlari)
    yanit = istemci.post(f"/hoparlorler/{satir['id']}/dene", follow_redirects=False)
    assert yanit.status_code == 303
    assert "gecikme=0" in yanit.headers["location"]
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kayit = baglanti.execute(
            "SELECT channel, stage, result, speaker_zone_id, event_id FROM alert_deliveries"
        ).fetchone()
    finally:
        baglanti.close()
    assert tuple(kayit) == ("http", "test", "ok", satir["id"], None)
    sayfa = istemci.get(yanit.headers["location"]).text
    assert "Yazılım gecikmesi: 0 ms" in sayfa


def test_teslim_paneli_veri_yokken_olculemedi_der(istemci):
    metin = istemci.get("/komuta/anons").text
    assert "Teslim kaydı" in metin
    panel = metin.split('id="teslim"')[1].split("</section>")[0]
    assert "ölçülemedi" in panel
    assert "%100" not in panel

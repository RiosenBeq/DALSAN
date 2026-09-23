"""Hoparlör bağlama: ses çıkışı seçimi, Bluetooth kopması ve test sesi.

Çözülen sorun şuydu ve ikisi de SESSİZDİ:

1. Kullanıcı fabrikaya Bluetooth bir hoparlör koyuyor, ama ses dizüstünün
   kendi hoparlöründen çıkıyor. Hiçbir hata yok; kimse fark etmiyor.
2. Bluetooth hoparlör kapanıyor. Anons artık hiçbir yere gitmiyor ve ekranda
   bunu söyleyen tek satır yok.

Gerçek ses ÇALINMAZ: test makinesinde hoparlör yok ve olsaydı da test
çalıştırması odayı bip sesine boğardı. Ölçülen şey kararlar: hangi komut
kuruluyor, kopma nasıl anlaşılıyor, ekran ne yazıyor.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

from app.olaylar import anons, ses_cihazlari, test_sesi

# --------------------------------------------------- çalma komutu ve cihaz


def test_cihaz_verilmezse_komut_eskisi_gibi(monkeypatch):
    """Cihaz seçilmemişken davranış DEĞİŞMEMELİ: kurulu sistemler etkilenmesin."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        anons.shutil, "which", lambda ad: f"/usr/bin/{ad}" if ad == "aplay" else None
    )
    assert anons._ses_komutu("/ses/a.wav") == ["/usr/bin/aplay", "/ses/a.wav"]


def test_paplay_cihazi_bayrakla_alir(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        anons.shutil, "which", lambda ad: f"/usr/bin/{ad}" if ad == "paplay" else None
    )
    komut = anons._ses_komutu("/ses/a.wav", "bluez_output.AC_12")
    assert komut == ["/usr/bin/paplay", "--device=bluez_output.AC_12", "/ses/a.wav"]


def test_aplay_cihazi_D_bayragiyla_alir(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        anons.shutil, "which", lambda ad: f"/usr/bin/{ad}" if ad == "aplay" else None
    )
    assert anons._ses_komutu("/ses/a.wav", "hw:1,0") == [
        "/usr/bin/aplay",
        "-D",
        "hw:1,0",
        "/ses/a.wav",
    ]


def test_paplay_aplaydan_once_denenir(monkeypatch):
    """SIRA ÖNEMLİ: aplay ham ALSA'dır ve Bluetooth hoparlörü HİÇ GÖRMEZ.

    İkisi de kuruluyken aplay seçilseydi kullanıcı listeden Bluetooth
    hoparlörünü seçer, ses sessizce hiçbir yere gitmezdi.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(anons.shutil, "which", lambda ad: f"/usr/bin/{ad}")
    # afplay bu sahte ortamda da "bulunuyor"; Linux'ta olmaz. paplay'in
    # aplay'den önce geldiğini görmek için afplay'i yok sayalım.
    monkeypatch.setattr(
        anons.shutil, "which", lambda ad: None if ad == "afplay" else f"/usr/bin/{ad}"
    )
    assert anons._ses_komutu("/ses/a.wav", "x")[0].endswith("paplay")


def test_afplay_cihaz_bayragi_almaz(monkeypatch):
    """macOS'ta afplay'in cihaz seçeneği YOKTUR.

    Tanımadığı bir bayrak verilseydi ses HİÇ çalmazdı — yani cihaz seçmek,
    anonsu tamamen susturmak anlamına gelirdi.
    """
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        anons.shutil, "which", lambda ad: f"/usr/bin/{ad}" if ad == "afplay" else None
    )
    assert anons._ses_komutu("/ses/a.wav", "Hoparlörüm") == ["/usr/bin/afplay", "/ses/a.wav"]


class _SahteWinsound:
    """Windows'un stdlib `winsound` modülünün yerine: çağrıları kaydeder."""

    SND_FILENAME = 0x20000
    SND_NODEFAULT = 0x2

    def __init__(self, hata: Exception | None = None) -> None:
        self.cagrilar: list[tuple[str, int]] = []
        self._hata = hata

    def PlaySound(self, ses, bayraklar):  # noqa: N802 — stdlib adı
        self.cagrilar.append((ses, bayraklar))
        if self._hata is not None:
            raise self._hata


def _windows(monkeypatch, sahte: _SahteWinsound) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winsound", sahte)
    # Windows'ta süreç AÇILMAZ; açılırsa test kırılsın.
    monkeypatch.setattr(anons.subprocess, "run", lambda *a, **k: pytest.fail("süreç açıldı"))


def test_windows_cihaz_bayragi_almaz(monkeypatch):
    """winsound da varsayılan çıkışa çalar; cihaz adı hiçbir yere geçmez."""
    sahte = _SahteWinsound()
    _windows(monkeypatch, sahte)
    assert anons._ses_komutu("C:/ses/a.wav", "Hoparlörüm") is None
    anons.SesKartiAnonscu("Hoparlörüm").cal("helmet", "Baret takınız", "C:/ses/a.wav")
    assert sahte.cagrilar == [("C:/ses/a.wav", sahte.SND_FILENAME | sahte.SND_NODEFAULT)]


def test_windows_bozuk_dosyada_bip_calip_basarili_demez(monkeypatch):
    """SND_NODEFAULT olmadan Windows eksik/bozuk dosyada varsayılan bip sesini
    çalar ve BAŞARILI döner; bayrakla PlaySound RuntimeError verir ve bu,
    Türkçe AnonsHatasi olarak Anons sayfasına çıkar."""
    _windows(monkeypatch, _SahteWinsound(RuntimeError("Failed to play sound")))
    with pytest.raises(anons.AnonsHatasi, match="WAV biçiminde değil"):
        anons.SesKartiAnonscu().cal("helmet", "Baret takınız", "C:/ses/yok.wav")


def test_ayar_anonscuya_geciyor():
    """Ayar okunup adaptöre verilmezse seçim hiçbir işe yaramaz."""
    anonscu = anons.SesKartiAnonscu("bluez_output.AC_12")
    assert anonscu.cihaz == "bluez_output.AC_12"


# ------------------------------------------------- cihaz seçimi destekleniyor mu


@pytest.mark.parametrize(
    ("platform", "beklenen"),
    [("linux", True), ("darwin", False), ("win32", False)],
)
def test_secim_destegi_platforma_gore(monkeypatch, platform, beklenen):
    """Mac/Windows'ta seçim "çalışıyormuş gibi" gösterilmemeli.

    Gösterilseydi kullanıcı listeden hoparlörü seçer, ses başka yerden çıkar
    ve sebebini hiçbir zaman öğrenemezdi.
    """
    monkeypatch.setattr(sys, "platform", platform)
    assert ses_cihazlari.secim_destekleniyor_mu() is beklenen


# ------------------------------------------------------------ cihaz listesi


def test_liste_alinamazsa_bos_doner_hata_firlatmaz(monkeypatch):
    """Burada istisna fırlatmak, ANONS SAYFASININ hiç açılmaması demekti."""

    def patlat(*_a, **_k):
        raise OSError("komut yok")

    monkeypatch.setattr(ses_cihazlari.subprocess, "run", patlat)
    assert ses_cihazlari.cihazlari_listele() == []


def test_pactl_ciktisi_cozumleniyor(monkeypatch):
    cikti = (
        "0\talsa_output.pci-0000_00_1f.3.analog-stereo\tmodule-alsa-card.c"
        "\ts16le 2ch 48000Hz\tRUNNING\n"
        "1\tbluez_output.AC_12_34_56_78_9A.1\tmodule-bluez5-device.c\ts16le 2ch 44100Hz\tIDLE\n"
    )
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ses_cihazlari.shutil, "which", lambda ad: f"/usr/bin/{ad}")
    monkeypatch.setattr(
        ses_cihazlari,
        "_calistir",
        lambda komut: "bluez_output.AC_12_34_56_78_9A.1" if "get-default-sink" in komut else cikti,
    )
    cihazlar = ses_cihazlari.cihazlari_listele()
    assert len(cihazlar) == 2
    bluetooth = [c for c in cihazlar if c.bluetooth]
    assert len(bluetooth) == 1
    assert bluetooth[0].varsayilan is True
    assert "Bluetooth" in bluetooth[0].ad  # ham sink adı ekranda okunmaz


def test_bagli_mi_uc_durumu_ayirir(monkeypatch):
    """ "Hoparlörünüz koptu" ile "kontrol edemedik" AYNI ŞEY DEĞİLDİR.

    Birincisini yanlışlıkla söylemek, kullanıcıyı olmayan bir arızanın
    peşine düşürür.
    """
    monkeypatch.setattr(ses_cihazlari, "cihazlari_listele", list)
    assert ses_cihazlari.cihaz_bagli_mi("") is True  # varsayılan çıkış
    assert ses_cihazlari.cihaz_bagli_mi("x") is None  # liste okunamadı

    monkeypatch.setattr(
        ses_cihazlari,
        "cihazlari_listele",
        lambda: [ses_cihazlari.SesCihazi(kimlik="x", ad="X")],
    )
    assert ses_cihazlari.cihaz_bagli_mi("x") is True
    assert ses_cihazlari.cihaz_bagli_mi("kapali-hoparlor") is False


# -------------------------------------------------------------- test sesi


def test_uretilen_wav_gercekten_calinabilir_bir_dosya(tmp_path):
    hedef = test_sesi.wav_uret(tmp_path / "test.wav")
    with wave.open(str(hedef), "rb") as dosya:
        assert dosya.getnchannels() == 1
        assert dosya.getsampwidth() == 2
        assert dosya.getframerate() == test_sesi.ORNEKLEME_HIZI
        # Üç bip + aralar: bir saniyeyi geçer, üç saniyeyi geçmez.
        saniye = dosya.getnframes() / dosya.getframerate()
        assert 0.5 < saniye < 3.0


def test_ses_tam_seviyede_degil():
    """Kulağa yakın bir hoparlörde deneme yapan kullanıcıyı irkiltmemeli."""
    assert 0 < test_sesi.SES_SEVIYESI < 0.6


def test_test_sesi_gercek_anons_yolunu_kullanir():
    """Ayrı bir çalma kodu yazılsaydı test çalar, gerçek anons sessizce
    çalmayabilirdi — düğme tam da güvenilmesi gereken yerde yalan söylerdi."""
    kaynak = Path(test_sesi.__file__).read_text(encoding="utf-8")
    assert "SesKartiAnonscu" in kaynak


def test_cal_istisna_firlatmaz_turkce_hata_dondurur(monkeypatch):
    def patlat(self, *_a, **_k):
        raise anons.AnonsHatasi("Hoparlör bulunamadı.")

    monkeypatch.setattr(anons.SesKartiAnonscu, "cal", patlat)
    assert test_sesi.cal("x") == "Hoparlör bulunamadı."


def test_test_sesi_diske_kalici_dosya_birakmaz(monkeypatch, tmp_path):
    """Kullanıcının veri klasöründe, yedeklemeye giren, kimsenin ne olduğunu
    bilmediği bir .wav bırakmanın anlamı yok."""
    monkeypatch.setattr(test_sesi.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(anons.SesKartiAnonscu, "cal", lambda self, *a: None)
    assert test_sesi.cal() == ""
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------------ ekran


def _ses_kartina_al(istemci, test_ayarlari):
    """Ayarları "ses kartı" yoluna çevirir (kart yalnızca o yolda görünür)."""
    object.__setattr__(test_ayarlari, "anons", "ses_karti")
    return istemci


def test_ses_karti_yolunda_cikis_karti_gorunur(istemci, test_ayarlari):
    _ses_kartina_al(istemci, test_ayarlari)
    sayfa = istemci.get("/anons").text
    assert "Ses çıkışı" in sayfa
    assert "Test sesi çal" in sayfa


def test_ip_hoparlor_yolunda_cikis_karti_gizli(istemci, test_ayarlari):
    """IP hoparlörde ses bilgisayardan HİÇ çıkmaz; çıkış cihazı diye bir
    kavram yoktur ve kart gösterilse kullanıcıyı yanıltırdı."""
    object.__setattr__(test_ayarlari, "anons", "http")
    assert "Ses çıkışı" not in istemci.get("/anons").text


def test_kopmus_hoparlor_ekranda_kirmizi_yaziyor(istemci, test_ayarlari, monkeypatch):
    """Sessiz kalması, anonsun hiçbir yere gitmediğini kimsenin bilmemesi demekti."""
    object.__setattr__(test_ayarlari, "anons", "ses_karti")
    object.__setattr__(test_ayarlari, "anons_ses_cihazi", "kapali-hoparlor")
    monkeypatch.setattr(
        ses_cihazlari,
        "cihazlari_listele",
        lambda: [ses_cihazlari.SesCihazi(kimlik="baska", ad="Başka")],
    )
    sayfa = istemci.get("/anons").text
    assert "seçili cihaz bağlı değil" in sayfa
    assert "anonslar duyulmaz" in sayfa
    # Kapalı cihaz seçenek olarak KALMALI: kalmazsa form kaydedilince ayar
    # sessizce silinir ve kullanıcı hoparlörü açtığında seçimi kaybolmuş olur.
    assert "kapali-hoparlor" in sayfa


def test_secim_desteklenmeyen_platformda_ne_yapilacagi_yaziyor(istemci, test_ayarlari, monkeypatch):
    object.__setattr__(test_ayarlari, "anons", "ses_karti")
    monkeypatch.setattr(ses_cihazlari, "secim_destekleniyor_mu", lambda: False)
    sayfa = istemci.get("/anons").text
    assert "sistem ayarlarından" in sayfa
    assert "Bluetooth" in sayfa
    assert 'name="ses_cihazi"' not in sayfa, "çalışmayan bir seçim kutusu gösterilmemeli"


def test_cikis_kaydedilince_yeniden_baslatma_soyleniyor(istemci, test_ayarlari):
    """Ayarlar açılışta bir kez okunur; söylenmezse "kaydettim ama değişmedi"."""
    object.__setattr__(test_ayarlari, "anons", "ses_karti")
    yanit = istemci.post(
        "/anons/ses-cikisi", data={"ses_cihazi": "hoparlor-1"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert "ANONS_SES_CIHAZI=hoparlor-1" in test_ayarlari.env_yolu.read_text(encoding="utf-8")
    assert "yeniden başlat" in istemci.get("/anons?sonuc=ses_cikisi").text


def test_test_sesi_yanlis_yolda_reddedilir(istemci, test_ayarlari):
    object.__setattr__(test_ayarlari, "anons", "http")
    yanit = istemci.post("/anons/test-sesi", follow_redirects=False)
    assert yanit.status_code == 400
    assert "Anonsu Dene" in yanit.text


# Komuta kabuğundaki anons ekranı artık ses çıkışını kanal satırında gösterir;
# kopuk çıkış uyarısı ve form tests/test_kanal_ekrani.py'de.

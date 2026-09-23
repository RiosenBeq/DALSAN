"""Uyarı kaydı arşivi (operatör isteği 23.09.2026; olaylar/uyari_arsivi.py).

"15 günde bir temizlensin ama öncesinde temizlenmeden olan loglar masaüstüne
kaydedilsin": en eski uyarı kaydı süreyi doldurunca o ana kadarki kayıtlar
masaüstündeki klasöre CSV olarak yazılır, geri okunup doğrulanır, SONRA
silinir. Yazılamazsa hiçbir kayıt silinmez. Dondurulan olayın kaydı ne
arşivlenir ne silinir. Testler gerçek masaüstüne yazmaz (conftest klasörü
geçici klasöre çevirir).
"""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path

import pytest

from app import veritabani, zaman
from app.ayarlar import AyarHatasi, ayarlari_coz
from app.olaylar import uyari_arsivi


@pytest.fixture
def baglanti(test_ayarlari):
    b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(b)
    simdi = zaman.simdi_utc()
    b.execute(
        "INSERT INTO cameras (id, name, area, source_type, source_url, created_at, updated_at) "
        "VALUES (1, 'Rampa 1', 'Sevkiyat', 'file', 'v.mp4', ?, ?)",
        (simdi, simdi),
    )
    b.execute(
        "INSERT INTO speaker_zones (id, name, area, address, kind, device, enabled, "
        "created_at, updated_at) VALUES (1, 'Tüm fabrika', '', '', 'ses_karti', "
        "'bluez_output.AA_BB.1', 1, ?, ?)",
        (simdi, simdi),
    )
    b.commit()
    try:
        yield b
    finally:
        b.close()


def _olay(b, gun_once: int, hold: int = 0) -> int:
    imlec = b.execute(
        "INSERT INTO events (occurred_at, event_type, camera_id, rule_snapshot, details, "
        "status, event_code, severity, hold) VALUES (?, 'violation', 1, '{}', '{}', 'new', "
        "'VEHICLE_PERSON_PROXIMITY', 'critical', ?)",
        (zaman.gun_once_utc(gun_once), hold),
    )
    b.commit()
    return int(imlec.lastrowid)


def _teslim(
    b, gun_once: int, olay_id: int | None, sonuc: str = "ok", kanal: str = "ses_karti"
) -> int:
    asama = "acildi" if olay_id is not None else "test"
    imlec = b.execute(
        "INSERT INTO alert_deliveries (event_id, event_code, speaker_zone_id, channel, stage, "
        "result, detail, queued_at, frame_to_start_ms) VALUES (?, ?, 1, ?, ?, ?, NULL, ?, 180)",
        (
            olay_id,
            "VEHICLE_PERSON_PROXIMITY" if olay_id is not None else None,
            kanal,
            asama,
            sonuc,
            zaman.gun_once_utc(gun_once),
        ),
    )
    b.commit()
    return int(imlec.lastrowid)


def _arsivle(ayarlar, b):
    return uyari_arsivi.arsivle_ve_temizle(b, ayarlar)


def _teslim_sayisi(b) -> int:
    return b.execute("SELECT COUNT(*) FROM alert_deliveries").fetchone()[0]


def _csv_satirlari(dosya: Path) -> list[list[str]]:
    with open(dosya, encoding="utf-8-sig", newline="") as akim:
        return list(csv.reader(akim, delimiter=";"))


def _klasor(ayarlar) -> Path:
    return uyari_arsivi.arsiv_klasoru(ayarlar)


# ------------------------------------------------------------ döngü


def test_sure_dolmadan_arsivlenmez_silinmez(baglanti, test_ayarlari):
    _teslim(baglanti, 3, _olay(baglanti, 3))
    assert _arsivle(test_ayarlari, baglanti) is None
    assert _teslim_sayisi(baglanti) == 1
    assert not _klasor(test_ayarlari).exists()


def test_sure_dolunca_once_masaustune_yazilir_sonra_silinir(baglanti, test_ayarlari):
    olay = _olay(baglanti, 16)
    _teslim(baglanti, 16, olay, sonuc="no_listener", kanal="ekran")
    _teslim(baglanti, 16, olay)
    _teslim(baglanti, 2, None)  # yeni bir deneme sesi: döngü o ana kadarkinin hepsini alır

    sonuc = _arsivle(test_ayarlari, baglanti)

    (dosya,) = _klasor(test_ayarlari).iterdir()
    assert sonuc == uyari_arsivi.ArsivSonucu(satir=3, dosya=dosya)
    ilk = zaman.yerel_tarih_iso(zaman.gun_once_utc(16))
    son = zaman.yerel_tarih_iso(zaman.gun_once_utc(2))
    assert dosya.name == f"uyari-kayitlari_{ilk}_{son}.csv"
    assert dosya.read_bytes().startswith(b"\xef\xbb\xbf"), "Excel Türkçe harfler için BOM"
    baslik, *satirlar = _csv_satirlari(dosya)
    assert tuple(baslik) == uyari_arsivi.BASLIKLAR
    assert len(satirlar) == 3
    ekran, hoparlor, deneme = satirlar
    assert ekran[3:6] == ["Araç-yaya yakınlığı", "Kritik", str(olay)]
    assert (ekran[8], ekran[9]) == ("ekran", "açık izleme ekranı yok")
    assert hoparlor[1:3] == ["Rampa 1", "Sevkiyat"]
    assert hoparlor[6:11] == ["açıldı", "Tüm fabrika", "ses çıkışı", "çaldı", "180"]
    assert (deneme[3], deneme[6]) == ("Deneme sesi", "deneme")

    # Dosya doğrulandıktan SONRA sistemden silindi; olayın kendisi durur
    assert _teslim_sayisi(baglanti) == 0
    assert baglanti.execute("SELECT COUNT(*) FROM events WHERE id = ?", (olay,)).fetchone()[0]
    # Yarım yazılmış geçici dosya kalmaz
    assert not list(_klasor(test_ayarlari).glob("*.yaziliyor"))


def test_dondurulan_olayin_kaydi_ne_arsivlenir_ne_silinir(baglanti, test_ayarlari):
    donmus = _olay(baglanti, 20, hold=1)
    siradan = _olay(baglanti, 20)
    donmus_teslim = _teslim(baglanti, 20, donmus)
    _teslim(baglanti, 20, siradan)

    _arsivle(test_ayarlari, baglanti)

    (dosya,) = _klasor(test_ayarlari).iterdir()
    _, *satirlar = _csv_satirlari(dosya)
    assert [s[5] for s in satirlar] == [str(siradan)]
    kalan = [s[0] for s in baglanti.execute("SELECT id FROM alert_deliveries")]
    assert kalan == [donmus_teslim]
    # Yalnız dondurulmuş kayıt kaldı: döngü onu beklemez, her gün yeniden tetiklenmez
    assert _arsivle(test_ayarlari, baglanti) is None
    assert len(list(_klasor(test_ayarlari).iterdir())) == 1


def test_yazilamazsa_hicbir_kayit_silinmez(baglanti, test_ayarlari, tmp_path):
    engel = tmp_path / "dosya-bu"
    engel.write_text("klasör değil", encoding="utf-8")
    ayarlar = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_klasoru=str(engel / "alt"))
    _teslim(baglanti, 16, _olay(baglanti, 16))

    with pytest.raises(uyari_arsivi.ArsivHatasi):
        _arsivle(ayarlar, baglanti)

    assert _teslim_sayisi(baglanti) == 1


def test_kapaliyken_arsiv_calismaz(baglanti, test_ayarlari):
    ayarlar = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_gun=0)
    _teslim(baglanti, 16, _olay(baglanti, 16))
    assert _arsivle(ayarlar, baglanti) is None
    assert _teslim_sayisi(baglanti) == 1
    assert not _klasor(ayarlar).exists()


def test_formul_kacisi_ve_ayni_adli_dosyanin_uzerine_yazilmaz(baglanti, test_ayarlari):
    baglanti.execute("UPDATE cameras SET name = '=HYPERLINK(\"http://x\")' WHERE id = 1")
    baglanti.commit()
    _teslim(baglanti, 16, _olay(baglanti, 16))
    klasor = _klasor(test_ayarlari)
    klasor.mkdir(parents=True)
    gun = zaman.yerel_tarih_iso(zaman.gun_once_utc(16))
    eski = klasor / f"uyari-kayitlari_{gun}_{gun}.csv"
    eski.write_text("önceki arşiv", encoding="utf-8")

    _arsivle(test_ayarlari, baglanti)

    assert eski.read_text(encoding="utf-8") == "önceki arşiv"
    yeni = klasor / f"uyari-kayitlari_{gun}_{gun}-2.csv"
    _, satir = _csv_satirlari(yeni)
    assert satir[1].startswith("'="), "kamera adı formül olarak çalışmamalı (R31)"


# ------------------------------------------------------------ klasör


def test_ayar_verilmisse_o_klasor_goreliyse_program_kokune_gore(test_ayarlari):
    ayarlar = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_klasoru="arsiv/uyari")
    assert uyari_arsivi.arsiv_klasoru(ayarlar) == test_ayarlari.kok_dizin / "arsiv" / "uyari"


def test_masaustunde_uygulama_adli_klasor(test_ayarlari, tmp_path, monkeypatch):
    monkeypatch.delenv("DALSAN_KAPSAYICI", raising=False)
    monkeypatch.setattr(uyari_arsivi, "masaustu_klasoru", lambda: tmp_path / "Desktop")
    ayarlar = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_klasoru="")
    assert uyari_arsivi.arsiv_klasoru(ayarlar) == (
        tmp_path / "Desktop" / "NextGen Detector uyarı kayıtları"
    )


def test_ekrandaki_yer_metni(test_ayarlari, tmp_path, monkeypatch):
    monkeypatch.delenv("DALSAN_KAPSAYICI", raising=False)
    ayarlar = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_klasoru="")
    monkeypatch.setattr(uyari_arsivi, "masaustu_klasoru", lambda: tmp_path / "Desktop")
    assert uyari_arsivi.klasor_metni(ayarlar) == "Masaüstü › NextGen Detector uyarı kayıtları"
    monkeypatch.setattr(uyari_arsivi, "masaustu_klasoru", lambda: None)
    assert uyari_arsivi.klasor_metni(ayarlar) == "veri/arsiv/uyari-kayitlari"
    ag = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_klasoru="/mnt/isg/uyarilar")
    assert uyari_arsivi.klasor_metni(ag) == str(Path("/mnt/isg/uyarilar"))


def test_masaustu_yoksa_ya_da_kapsayicidaysa_veri_klasoru(test_ayarlari, monkeypatch):
    ayarlar = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_klasoru="")
    beklenen = test_ayarlari.veri_dizini / "arsiv" / "uyari-kayitlari"
    monkeypatch.delenv("DALSAN_KAPSAYICI", raising=False)
    monkeypatch.setattr(uyari_arsivi, "masaustu_klasoru", lambda: None)
    assert uyari_arsivi.arsiv_klasoru(ayarlar) == beklenen

    def aranmamali():
        raise AssertionError("Docker'da masaüstü aranmaz")

    monkeypatch.setenv("DALSAN_KAPSAYICI", "1")
    monkeypatch.setattr(uyari_arsivi, "masaustu_klasoru", aranmamali)
    assert uyari_arsivi.arsiv_klasoru(ayarlar) == beklenen


def test_linux_turkce_masaustu_xdg_den_bulunur(tmp_path):
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text(
        '# yorum\nXDG_DESKTOP_DIR="$HOME/Masaüstü"\nXDG_DOWNLOAD_DIR="$HOME/İndirilenler"\n',
        encoding="utf-8",
    )
    (tmp_path / "Masaüstü").mkdir()
    (tmp_path / "Desktop").mkdir()  # XDG'nin gösterdiği önce gelir
    bulunan = uyari_arsivi.masaustu_klasoru("linux", tmp_path, {})
    assert bulunan == tmp_path / "Masaüstü"


def test_linux_masaustu_kapaliysa_ev_kokune_yazilmaz(tmp_path):
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text(
        'XDG_DESKTOP_DIR="$HOME/"\n', encoding="utf-8"
    )
    assert uyari_arsivi.masaustu_klasoru("linux", tmp_path, {}) is None


def test_windows_bilinen_klasor_once_yoksa_profil(tmp_path, monkeypatch):
    onedrive = tmp_path / "OneDrive" / "Masaüstü"
    onedrive.mkdir(parents=True)
    (tmp_path / "Desktop").mkdir()
    ortam = {"USERPROFILE": str(tmp_path)}
    monkeypatch.setattr(uyari_arsivi, "_windows_masaustu", lambda: onedrive)
    assert uyari_arsivi.masaustu_klasoru("win32", tmp_path, ortam) == onedrive
    monkeypatch.setattr(uyari_arsivi, "_windows_masaustu", lambda: None)
    assert uyari_arsivi.masaustu_klasoru("win32", tmp_path, ortam) == tmp_path / "Desktop"


def test_macos_masaustu(tmp_path):
    assert uyari_arsivi.masaustu_klasoru("darwin", tmp_path, {}) is None
    (tmp_path / "Desktop").mkdir()
    assert uyari_arsivi.masaustu_klasoru("darwin", tmp_path, {}) == tmp_path / "Desktop"


# ------------------------------------------------------------ ayar


def test_ayar_varsayilani_15_gun_ve_sinirlar(tmp_path, monkeypatch):
    monkeypatch.delenv("DALSAN_KAPSAYICI", raising=False)
    assert ayarlari_coz(tmp_path, {}).uyari_kaydi_arsiv_gun == 15
    assert ayarlari_coz(tmp_path, {"UYARI_KAYDI_ARSIV_GUN": "0"}).uyari_kaydi_arsiv_gun == 0
    with pytest.raises(AyarHatasi):
        ayarlari_coz(tmp_path, {"UYARI_KAYDI_ARSIV_GUN": "400"})


# ------------------------------------------------------------ bakım


def _bakim(ayarlar, b) -> None:
    from app.analiz.supervizor import AnalizSupervizoru
    from app.loglama import log_al

    supervizor = AnalizSupervizoru.__new__(AnalizSupervizoru)
    supervizor.ayarlar = ayarlar
    supervizor._log = log_al("test")
    supervizor._bakim_yap(b)


def test_bakim_arsivler_ve_imha_kaydina_yazar(baglanti, test_ayarlari):
    _teslim(baglanti, 16, _olay(baglanti, 16))
    _bakim(test_ayarlari, baglanti)
    (dosya,) = _klasor(test_ayarlari).iterdir()
    kayit = baglanti.execute("SELECT * FROM purge_log ORDER BY id DESC").fetchone()
    assert (kayit["alerts_archived"], kayit["alert_archive_file"]) == (1, str(dosya))
    assert _teslim_sayisi(baglanti) == 0


def test_bakim_olaydan_once_arsivler(baglanti, test_ayarlari):
    """Saklama süresi dolan olay silinince teslim kaydı da gider (CASCADE);
    arşiv önce çalışmasaydı o kayıt masaüstüne hiç yazılmazdı."""
    gun = test_ayarlari.olay_saklama_gun + 5
    olay = _olay(baglanti, gun)
    _teslim(baglanti, gun, olay)
    _bakim(test_ayarlari, baglanti)
    assert not baglanti.execute("SELECT 1 FROM events WHERE id = ?", (olay,)).fetchone()
    (dosya,) = _klasor(test_ayarlari).iterdir()
    _, satir = _csv_satirlari(dosya)
    assert satir[5] == str(olay)


def test_bakimda_yazilamazsa_silinmez_ve_sistem_olayi_duser(baglanti, test_ayarlari, tmp_path):
    engel = tmp_path / "dosya-bu"
    engel.write_text("klasör değil", encoding="utf-8")
    ayarlar = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_klasoru=str(engel / "alt"))
    _teslim(baglanti, 16, _olay(baglanti, 16))

    _bakim(ayarlar, baglanti)

    assert _teslim_sayisi(baglanti) == 1
    olay = baglanti.execute(
        "SELECT details FROM events WHERE event_code = 'ALERT_ARCHIVE_FAILED'"
    ).fetchone()
    assert olay is not None and "hiçbir kayıt" in olay["details"]
    kayit = baglanti.execute("SELECT * FROM purge_log ORDER BY id DESC").fetchone()
    assert (kayit["alerts_archived"], kayit["alert_archive_file"]) == (0, None)


def test_arsiv_aciksa_eski_teslim_kaydi_arsivsiz_silinmez(baglanti, test_ayarlari, tmp_path):
    """Arşiv yazılamazken ihlal saklama süresi de dolmuşsa: olay satırı olmayan
    kayıt (deneme sesi) eskiden 180 günde silinirdi; arşiv açıkken yalnız
    arşivden sonra silinir."""
    engel = tmp_path / "dosya-bu"
    engel.write_text("klasör değil", encoding="utf-8")
    ayarlar = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_klasoru=str(engel / "alt"))
    _teslim(baglanti, test_ayarlari.olay_saklama_gun + 5, None)
    _bakim(ayarlar, baglanti)
    assert _teslim_sayisi(baglanti) == 1


# ------------------------------------------------------------ Ayarlar ekranı


def test_ayarlar_ekrani_arsivi_ve_imha_satirini_gosterir(istemci, baglanti, test_ayarlari):
    metin = istemci.get("/ayarlar").text
    assert 'name="UYARI_KAYDI_ARSIV_GUN"' in metin and 'value="15"' in metin
    assert 'name="UYARI_KAYDI_ARSIV_KLASORU"' in metin
    assert "<code>veri/masaustu</code>" in metin  # göreli: mutlak yol ekrana çıkmaz
    assert str(test_ayarlari.kok_dizin) not in metin
    assert "saklama süresine" in metin  # masaüstü kopyasının KVKK notu

    _teslim(baglanti, 16, _olay(baglanti, 16))
    _bakim(test_ayarlari, baglanti)
    (dosya,) = _klasor(test_ayarlari).iterdir()
    metin = istemci.get("/ayarlar").text
    assert "Arşivlenen uyarı kaydı" in metin
    assert f"1 <code>{dosya.name}</code>" in metin
    assert "uyarı kaydı arşivi 15 gün" in metin


def test_arsiv_kapaliyken_ekran_soyler(test_ayarlari, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    ayarlar = dataclasses.replace(test_ayarlari, uyari_kaydi_arsiv_gun=0)
    with TestClient(uygulama_olustur(ayarlar, analiz=False)) as istemci:
        metin = istemci.get("/ayarlar").text
    assert "Uyarı kaydı arşivi kapalı" in metin

"""Mac / Windows uyumu — platformdan bağımsız olarak sınanabilen kısımlar.

Bu testlerin tamamı Linux'ta da anlamlıdır: kod yolunu, dosya içeriğini ve
kodlama davranışını sınarlar. Amaç, "Mac'te çalışıyordu" diye Windows'ta
sessizce bozulan sınıfı hataları geri gelmeden yakalamak.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from conftest import git_gerekli

KOK = Path(__file__).resolve().parents[1]


# ---- başlatıcılar ----


def test_windows_baslaticisi_magaza_takma_adina_dusmez():
    """`where python` Windows 10/11'de Python KURULU OLMASA BİLE başarılıdır
    (Microsoft Store takma adı PATH'tedir): eski betik Mağaza'yı açıp pencereyi
    kapatıyor ve yardım mesajı hiç görünmüyordu."""
    metin = (KOK / "Baslat-Windows.bat").read_text(encoding="utf-8")
    # Açıklama satırları (REM) hariç: tuzağın kendisi anlatılıyor olabilir
    komutlar = "\n".join(
        s for s in metin.splitlines() if not s.strip().upper().startswith(("REM", "ECHO"))
    )
    assert "where python" not in komutlar, "Store takma adı tuzağına düşen kontrol"
    assert "py -3" in komutlar, "py launcher denenmeli (Add to PATH işaretlenmese de kurulur)"
    assert 'python -c "import sys"' in komutlar, "aday gerçekten Python mu, doğrulanmalı"


def test_windows_baslaticisi_hatada_pencereyi_kapatmaz():
    """Çökme anında pencere kapanırsa kullanıcının kopyalayacak satırı kalmaz —
    destek akışının tamamı buna dayanır (CLAUDE.md §8)."""
    metin = (KOK / "Baslat-Windows.bat").read_text(encoding="utf-8")
    assert metin.count("pause") >= 2, "hem hata dalında hem Python yokken beklemeli"


def test_bat_dosyasi_crlf_command_dosyasi_lf():
    """Satır sonları karışırsa: CRLF'li .command Mac'te 'cd: $\\r' hatası verir."""
    assert b"\r\n" in (KOK / "Baslat-Windows.bat").read_bytes()
    assert b"\r\n" not in (KOK / "Baslat-Mac.command").read_bytes()


def test_gitattributes_satir_sonlarini_sabitler():
    metin = (KOK / ".gitattributes").read_text(encoding="utf-8")
    kurallar = dict(
        (parca[0], " ".join(parca[1:]))
        for parca in (s.split() for s in metin.splitlines() if s and not s.startswith("#"))
    )
    assert kurallar["*.command"].endswith("eol=lf")
    assert kurallar["*.sh"].endswith("eol=lf")
    assert kurallar["*.bat"].endswith("eol=crlf")


def test_mac_baslaticisi_stub_pythonu_en_sona_birakir():
    """/usr/bin/python3 her Mac'te vardır ama Command Line Tools yoksa yalnızca
    bir yer tutucudur ve çalıştırılınca modal pencere açar. Gerçek kurulumlar
    önce denenmeli."""
    metin = (KOK / "Baslat-Mac.command").read_text(encoding="utf-8")
    homebrew = metin.index("/opt/homebrew/bin/python3.12")
    son_aday = metin.index("adaylar+=(python3)")
    assert homebrew < son_aday, "gerçek kurulumlar bare python3'ten ÖNCE denenmeli"
    assert "chmod +x" in metin, "ZIP'ten gelen dosyanın çalıştırma izni tazelenmeli"


@git_gerekli
def test_mac_baslaticisi_calistirilabilir():
    """Git'te çalıştırma izni yoksa Finder dosyayı hiç açmaz."""
    cikti = subprocess.run(
        ["git", "ls-files", "-s", "Baslat-Mac.command"],
        cwd=KOK,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert cikti.startswith("100755"), f"çalıştırma izni yok: {cikti.strip()}"


# ---- Kontrol Paneli ----


def test_panel_alt_surec_ciktisini_utf8_okur():
    """Windows'ta varsayılan çözücü cp1254'tür ve büyük Ş/Ğ harfleri (0x9E)
    orada TANIMSIZDIR: "SİSTEM BAŞLATILIYOR" satırı UnicodeDecodeError verip
    günlük penceresini sessizce dondururdu."""
    metin = (KOK / "masaustu" / "dalsan_launcher.py").read_text(encoding="utf-8")
    popenler = re.findall(r"subprocess\.Popen\((.*?)\n        \)", metin, re.S)
    assert len(popenler) >= 2, "iki Popen çağrısı bekleniyordu"
    for gövde in popenler:
        assert 'encoding="utf-8"' in gövde, f"encoding verilmemiş: {gövde[:80]}"


def test_turkce_buyuk_harfler_cp1254te_cozulemez():
    """Yukarıdaki testin dayandığı olgu — kodlama davranışı gerçekten böyle."""
    ham = "SİSTEM BAŞLATILIYOR".encode()
    try:
        ham.decode("cp1254")
    except UnicodeDecodeError:
        return  # beklenen
    raise AssertionError("cp1254 bu baytları çözebiliyorsa test varsayımı yanlış")


def test_panel_sahipsiz_sunucuyu_sahiplenir():
    """Panel çökerse sunucu ayakta kalır; 'Durdur' onu bulamayınca kullanıcı
    panelden çıkamayacağı bir duruma sıkışıyordu."""
    metin = (KOK / "masaustu" / "dalsan_launcher.py").read_text(encoding="utf-8")
    assert "_sahipsiz_sureci_durdur" in metin
    assert "sunucu.pid" in metin


def test_panel_python_surumu_bagimlilikla_uyumlu():
    """onnxruntime 3.11+ ister; 3.10'a izin vermek pip'i çok eski bir sürüme
    düşürüyor ve tespit sessizce bozuluyordu."""
    metin = (KOK / "masaustu" / "dalsan_launcher.py").read_text(encoding="utf-8")
    assert "sys.version_info >= (3, 11)" in metin


# ---- bağımlılıklar ----


def test_bagimliliklar_sabit_surumlu():
    """En yeni sürümler her platform için hazır paket yayınlamıyor: Intel Mac'te
    pip kaynaktan derlemeye kalkıp kurulumu dakikalarca sürükleyip kırıyordu."""
    metin = (KOK / "backend" / "requirements.txt").read_text(encoding="utf-8")
    for paket in ("opencv-python", "onnxruntime", "supervision"):
        satir = next(s for s in metin.splitlines() if s.startswith(paket))
        assert "==" in satir, f"{paket} sürümü sabitlenmeli: {satir}"


# ---- görüntü üzerine yazı ----


def test_overlay_etiketleri_ascii():
    """cv2.putText yalnızca ASCII çizer: "tır" ekranda "t?r" görünürdü."""
    from app.analiz.tespit import SINIF_OVERLAY, SINIF_TR

    for ad in SINIF_OVERLAY.values():
        assert ad.isascii(), f"overlay etiketi ASCII olmalı: {ad}"
    # Arayüzdeki adlar TÜRKÇE kalmalı — sadeleştirme oraya sıçramasın
    assert not SINIF_TR["truck"].isascii()


# ---- yollar ----


def test_anons_ses_yolu_posix_biciminde_saklanir(istemci, test_ayarlari):
    """Windows'ta kaydedilen 'veri\\sesler\\a.wav' Linux fabrika sunucusunda tek
    bir dosya adı sanılır ve bulunamazdı."""
    ses = test_ayarlari.kok_dizin / "veri" / "sesler" / "baret.wav"
    ses.parent.mkdir(parents=True, exist_ok=True)
    ses.write_bytes(b"RIFF....WAVE")
    yanit = istemci.post(
        "/anons/1/kaydet",
        data={"text": "Baret takınız", "audio_file": "veri/sesler/baret.wav", "enabled": "1"},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    from app import veritabani

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kayit = baglanti.execute(
            "SELECT audio_file FROM announcement_messages WHERE id = 1"
        ).fetchone()["audio_file"]
    finally:
        baglanti.close()
    assert "\\" not in kayit, f"yol POSIX biçiminde saklanmalı: {kayit}"


def test_wav_disi_ses_dosyasi_reddedilir(istemci, test_ayarlari):
    """Windows'un ses çalıcısı yalnız WAV çalar; MP3 Mac'te çalışıp fabrikada
    sessizce çalışmazdı."""
    ses = test_ayarlari.kok_dizin / "veri" / "sesler" / "baret.mp3"
    ses.parent.mkdir(parents=True, exist_ok=True)
    ses.write_bytes(b"ID3")
    yanit = istemci.post(
        "/anons/1/kaydet",
        data={"text": "Baret", "audio_file": "veri/sesler/baret.mp3", "enabled": "1"},
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    assert "wav" in yanit.json()["hata"].lower()


def test_kapali_anons_denemesi_dogru_soyler(test_ayarlari):
    """ANONS=null iken 'Anonsu Dene' başarılı demez — hoparlörden ses çıkmaz."""
    from app.olaylar.anons import AnonsYoneticisi

    yonetici = AnonsYoneticisi(test_ayarlari)  # test ayarlarında anons="null"
    yonetici._cal_ve_kaydet("helmet", "Baret takınız", None)
    assert "ÇALINAMADI" in yonetici.son_sonuc
    assert "ANONS=null" in yonetici.son_sonuc


def test_powershell_kesme_isareti_kacirilir():
    """Yolda kesme işareti varsa ("Ali'nin Sesleri") PowerShell metni erken
    kapanır: hem bozulur hem komut enjeksiyonu yüzeyi olur."""
    import sys
    from unittest import mock

    from app.olaylar import anons

    with mock.patch.object(sys, "platform", "win32"):
        komut = anons._ses_komutu("C:/Ali'nin Sesleri/baret.wav")
    assert komut is not None
    assert "''" in komut[-1], "tek tırnak ikilenmeli"


def test_bakim_kilitli_dosyada_durmaz(test_ayarlari, monkeypatch):
    """Windows'ta başka bir işlemin açık tuttuğu dosya PermissionError verir;
    yalnızca FileNotFoundError yakalamak o günkü bakımın TAMAMINI iptal
    ediyordu."""
    import os
    import time as time_mod

    from app.analiz.supervizor import AnalizSupervizoru

    supervizor = AnalizSupervizoru.__new__(AnalizSupervizoru)
    eski = time_mod.time() - 200 * 86400
    for ad in ("kilitli.jpg", "normal.jpg"):
        dosya = test_ayarlari.goruntu_klasoru / "2026-01" / ad
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_bytes(b"jpeg")
        os.utime(dosya, (eski, eski))

    gercek_unlink = Path.unlink

    def sahte_unlink(self, *a, **k):
        if self.name == "kilitli.jpg":
            raise PermissionError(32, "dosya başka bir işlem tarafından kullanılıyor")
        return gercek_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", sahte_unlink)
    silinen = supervizor._eski_dosyalari_sil(
        test_ayarlari.goruntu_klasoru, 90, test_ayarlari.nesne_klasoru
    )
    assert silinen == 1, "kilitli dosya atlanmalı, diğeri silinmeli"

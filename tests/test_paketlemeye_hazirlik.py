"""Paketlenmiş (tek dosyalık) çalışmaya hazırlık: yol ve veri klasörü çözümü.

NEDEN BU TESTLER VAR — paketleme sırasında iki şey birden değişir:

* Kaynak dosyalar (şablon, stil, şema betiği) artık depoda değil, programın
  açtığı geçici klasördedir; `__file__` oraya işaret ETMEZ.
* Uygulama paketi SALT OKUNURDUR; veritabanı, günlük ve indirilen model
  oraya yazılamaz.

Bu iki soru `app/kaynaklar.py` içinde, tek yerde çözülür. Buradaki testler
her iki modu da (normal ve sahte-paketlenmiş) sınar ve en önemlisini korur:
**bugünkü kurulumun veri yolu DEĞİŞMEZ.**

Sahte-paketlenmiş mod, PyInstaller'ın yaptığının aynısıdır: `sys._MEIPASS`
değişkenini kurmak. Gerçek bir paket üretmeye gerek yoktur; program da zaten
kararı yalnızca bu değişkene bakarak verir.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app import kaynaklar

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture
def sahte_paket(tmp_path, monkeypatch):
    """PyInstaller altında çalışıyormuş gibi yapar; kaynak klasörünü döndürür."""
    kaynak_klasoru = tmp_path / "paket_icerigi"
    kaynak_klasoru.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(kaynak_klasoru), raising=False)
    return kaynak_klasoru


# ---------------------------------------------------------------- kaynak yolu


def test_normal_calismada_kaynak_yolu_depo_kokune_cozulur():
    assert kaynaklar.paketlenmis_mi() is False
    assert kaynaklar.kaynak_yolu() == KOK
    assert kaynaklar.kaynak_yolu("backend", "sema") == KOK / "backend" / "sema"
    assert kaynaklar.kaynak_yolu("backend", "sema").is_dir()


def test_paketlenmis_calismada_kaynak_yolu_gecici_klasore_cozulur(sahte_paket):
    assert kaynaklar.paketlenmis_mi() is True
    assert kaynaklar.kaynak_yolu() == sahte_paket
    assert kaynaklar.kaynak_yolu("backend", "sema") == sahte_paket / "backend" / "sema"


def test_kaynak_yollarini_cozen_tek_yer_kaynaklar_modulu():
    """`__file__` ile yol çözümü YALNIZCA kaynaklar.py'de kalmalı.

    Bir dosya kendi yolunu yeniden `__file__` üzerinden hesaplarsa paketlenmiş
    programda o yol geçersiz olur ve sayfa/şema sessizce bulunamaz. Bu test,
    düzeltmenin ilerideki bir değişiklikle geri alınmasını engeller.
    """
    suclular = []
    for dosya in sorted((KOK / "backend").rglob("*.py")):
        if dosya.name == "kaynaklar.py" or "__pycache__" in dosya.parts:
            continue
        for sira, satir in enumerate(dosya.read_text(encoding="utf-8").splitlines(), 1):
            if "__file__" in satir:
                suclular.append(f"{dosya.relative_to(KOK)}:{sira}")
    assert not suclular, (
        "Yol çözümü kaynaklar.py dışına kaçmış (paketlenmiş programda kırılır): "
        + ", ".join(suclular)
    )


def test_sablon_statik_ve_sema_yollari_kaynaklar_uzerinden_geliyor():
    """Üç kaynak klasörünün de tek fonksiyondan geldiğini doğrular."""
    from app import uygulama, veritabani
    from app.web import rotalar

    assert veritabani.SEMA_DIZINI == kaynaklar.kaynak_yolu("backend", "sema")
    assert uygulama.STATIK_DIZINI == kaynaklar.kaynak_yolu("backend", "app", "web", "static")
    assert rotalar.SABLON_DIZINI == kaynaklar.kaynak_yolu("backend", "app", "web", "templates")
    # Üçü de gerçekten var: yanlış bir alt yol sessizce boş klasöre çözülmesin.
    for klasor in (veritabani.SEMA_DIZINI, uygulama.STATIK_DIZINI, rotalar.SABLON_DIZINI):
        assert klasor.is_dir(), f"Kaynak klasörü bulunamadı: {klasor.name}"


# ------------------------------------------------------- yazılabilir veri kökü


def test_gelistirmede_veri_koku_bugunku_gibi_depo_koku():
    """EN ÖNEMLİ TEST: mevcut kurulumun veri yolu değişmemeli."""
    konum = kaynaklar.veri_konumu()
    assert konum.kok == KOK
    assert konum.gunluk_notu == ""


def test_paketlenmis_calismada_veri_koku_kullanici_profilinde(sahte_paket, tmp_path):
    program = tmp_path / "Uygulamalar"
    program.mkdir()
    profil = tmp_path / "profil" / "NextGen Detector"

    konum = kaynaklar.veri_konumu(program_dizini_=program, kullanici_dizini=profil)

    assert konum.kok == profil.resolve()
    assert konum.gunluk_notu == ""


def test_eski_konumdaki_veri_TASINMAZ_oradan_okunmaya_devam_eder(sahte_paket, tmp_path):
    """Sessiz veri taşıması yapılmaz; eski klasör kullanılmaya devam eder.

    Kullanıcı yedeğini eski klasörde arar. Kopyalama yarıda kalırsa ya da
    kullanıcı dosyayı bulamazsa, kayıtları kaybolmuş sayılır.
    """
    program = tmp_path / "program"
    (program / "veri").mkdir(parents=True)
    kayit = program / "veri" / "dalsan.db"
    kayit.write_bytes(b"eski kayitlar")
    profil = tmp_path / "profil" / "NextGen Detector"

    konum = kaynaklar.veri_konumu(program_dizini_=program, kullanici_dizini=profil)

    assert konum.kok == program.resolve()
    assert konum.gunluk_notu, "Olağandışı konum sessiz kalmamalı — günlüğe not düşmeli"
    assert "taşınmadı" in konum.gunluk_notu.lower()
    # Hiçbir şey taşınmadı / kopyalanmadı:
    assert kayit.read_bytes() == b"eski kayitlar"
    assert not profil.exists()


def test_iki_konumda_da_veri_varsa_yeni_konum_kullanilir(sahte_paket, tmp_path):
    program = tmp_path / "program"
    (program / "veri").mkdir(parents=True)
    (program / "veri" / "dalsan.db").write_bytes(b"eski")
    profil = tmp_path / "profil"
    (profil / "veri").mkdir(parents=True)
    (profil / "veri" / "dalsan.db").write_bytes(b"yeni")

    konum = kaynaklar.veri_konumu(program_dizini_=program, kullanici_dizini=profil)

    assert konum.kok == profil.resolve()
    assert konum.gunluk_notu == ""


def test_gunluk_notunun_ayrintisi_ekrana_degil_dosyaya_gider(sahte_paket, tmp_path):
    """Tam yollar `gunluk_ayrintisi` alanında durur; ekran metninde YOK.

    loglama.py ekran akışına yalnızca `mesaj`ı, dosyaya `ayrinti`yı yazar.
    """
    program = tmp_path / "program"
    (program / "veri").mkdir(parents=True)
    (program / "veri" / "dalsan.db").write_bytes(b"x")

    konum = kaynaklar.veri_konumu(program_dizini_=program, kullanici_dizini=tmp_path / "profil")

    assert str(program) not in konum.gunluk_notu
    assert str(program) in konum.gunluk_ayrintisi


# ----------------------------------------------- işletim sistemine göre klasör


def test_mac_kullanici_klasoru(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda _sinif: tmp_path))
    assert (
        kaynaklar.kullanici_veri_koku()
        == tmp_path / "Library" / "Application Support" / "NextGen Detector"
    )


def test_windows_kullanici_klasoru(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    assert kaynaklar.kullanici_veri_koku() == tmp_path / "AppData" / "Local" / "NextGen Detector"


def test_mac_uygulama_paketinin_yanindaki_klasor(monkeypatch, tmp_path):
    """macOS'ta çalışan dosya Ad.app/Contents/MacOS/ içindedir.

    Kullanıcının gördüğü klasör .app'in DURDUĞU klasördür; eski kayıtlar
    orada aranmalıdır.
    """
    icerik = tmp_path / "Uygulamalar" / "NextGen Detector.app" / "Contents" / "MacOS"
    icerik.mkdir(parents=True)
    calisan = icerik / "NextGen Detector"
    calisan.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(calisan))

    assert kaynaklar.program_dizini() == tmp_path / "Uygulamalar"


# ------------------------------------------------------------------ .env dosyası


ORNEK_ENV = "OLAY_SAKLAMA_GUN=30\nANONS=null\n"


def test_paketlenmis_calismada_env_ornekten_bir_kez_olusturulur(sahte_paket, tmp_path):
    """Paketlenmiş programda kullanıcı .env.example'ı kopyalayamaz.

    Dosya paketin içindedir ve kullanıcı yazılım bilmiyor; ayar dosyası bu
    yüzden ilk açılışta kendiliğinden üretilir.
    """
    from app.ayarlar import ayarlari_yukle

    (sahte_paket / ".env.example").write_text(ORNEK_ENV, encoding="utf-8")
    veri_koku = tmp_path / "profil"
    veri_koku.mkdir()

    ayarlar = ayarlari_yukle(veri_koku)

    assert (veri_koku / ".env").is_file()
    assert ayarlar.olay_saklama_gun == 30
    assert ayarlar.env_yolu == veri_koku / ".env"

    # İKİNCİ açılış dosyanın üzerine YAZMAZ: kullanıcının değişiklikleri kalır.
    (veri_koku / ".env").write_text("OLAY_SAKLAMA_GUN=7\n", encoding="utf-8")
    assert ayarlari_yukle(veri_koku).olay_saklama_gun == 7


def test_gelistirmede_env_kendiliginden_olusturulmaz(tmp_path):
    """Bugünkü davranış aynen korunur: .env yoksa anlaşılır hatayla durulur."""
    from app.ayarlar import ayarlari_yukle
    from app.hatalar import AyarHatasi

    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert ".env.example" in hata.value.kullanici_mesaji
    assert not (tmp_path / ".env").exists()


# ==================================================================
# UÇTAN UCA: TARİFİN DEDİĞİ PAKET GERÇEKTEN AÇILIYOR MU?
# ==================================================================
#
# Yukarıdaki testler `kaynak_yolu` fonksiyonunu tek tek sınıyor; üretim
# tarifi (paketleme/) de "şu klasörler pakete konacak" diyor. Ama ikisi
# birbirini TUTUYOR MU sorusu hiçbir yerde sorulmuyordu — ve tutmadığında
# ortaya çıkan hata tam olarak şudur: uygulama açılır açılmaz "şablon
# bulunamadı" ile çöker, çıktı hiçbir ekrana düşmez, kullanıcı yalnızca
# "açılmıyor" der.
#
# Burada paket GERÇEKTEN kuruluyor: tarifin `veri_dosyalari()` listesi ne
# diyorsa o kopyalanıyor, `sys._MEIPASS` o klasöre kuruluyor ve sistem AYRI
# BİR SÜREÇTE açılıyor. Ayrı süreç şart: şablon/şema yolları modül seviyesinde
# bir kez çözülür, aynı süreçte yeniden çözdürülemez.


def _sahte_paketi_kur(hedef: Path) -> None:
    """Üretim tarifinin `datas` listesini gerçekten uygular.

    PyInstaller kuralı: kaynak bir KLASÖRSE içeriği hedef klasöre, DOSYAYSA
    dosyanın kendisi hedef klasöre kopyalanır.
    """
    import shutil

    sys.path.insert(0, str(KOK / "paketleme"))
    try:
        import paketleme_ortak as ortak
    finally:
        sys.path.pop(0)

    for kaynak_metni, hedef_metni in ortak.veri_dosyalari(KOK):
        kaynak = Path(kaynak_metni)
        varis = hedef / hedef_metni
        if kaynak.is_dir():
            shutil.copytree(kaynak, varis, dirs_exist_ok=True)
        else:
            varis.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(kaynak, varis / kaynak.name)


_PAKET_ACILIS_BETIGI = """
import sys
from pathlib import Path

sys._MEIPASS = {paket!r}          # PyInstaller'ın yaptığı: kaynaklar burada
sys.frozen = True
sys.path.insert(0, {backend!r})

from fastapi.testclient import TestClient

from app.ayarlar import ayarlari_yukle
from app.uygulama import uygulama_olustur

# .env YOK: paketlenmiş programda örnekten BİR KEZ üretilmesi gerekir.
ayarlar = ayarlari_yukle(Path({veri_koku!r}))
with TestClient(uygulama_olustur(ayarlar, analiz=False)) as istemci:
    for yol in ("/saglik", "/kurallar", "/komuta", "/komuta/rapor", "/kameralar"):
        yanit = istemci.get(yol)
        assert yanit.status_code == 200, (yol, yanit.status_code)
    # Statik dosya paketten servis ediliyor mu
    assert istemci.get("/static/komuta.css").status_code == 200
print("ACILDI")
"""


def _paketlenmis_sistemi_baslat(tmp_path: Path):
    import subprocess

    paket = tmp_path / "paket"
    paket.mkdir()
    _sahte_paketi_kur(paket)
    veri_koku = tmp_path / "kullanici"
    veri_koku.mkdir()

    betik = _PAKET_ACILIS_BETIGI.format(
        paket=str(paket), backend=str(KOK / "backend"), veri_koku=str(veri_koku)
    )
    sonuc = subprocess.run(
        [sys.executable, "-c", betik], capture_output=True, text=True, timeout=180
    )
    return sonuc, paket, veri_koku


def test_tarifin_kopyaladigi_paketle_sistem_gercekten_aciliyor(tmp_path):
    """Şablon, stil ve şema betikleri pakette bulunuyor mu — uçtan uca."""
    sonuc, _, _ = _paketlenmis_sistemi_baslat(tmp_path)
    assert sonuc.returncode == 0, (
        "Paketlenmiş sistem açılamadı. Üretim tarifindeki `veri_dosyalari()` "
        "listesi ile app/kaynaklar.py'nin aradığı yollar uyuşmuyor olabilir.\n"
        f"--- stdout ---\n{sonuc.stdout}\n--- stderr ---\n{sonuc.stderr}"
    )
    assert "ACILDI" in sonuc.stdout


def test_paketten_acilinca_veritabani_ve_env_kullanici_klasorune_yaziliyor(tmp_path):
    """Uygulama paketi SALT OKUNURDUR (imzalı .app / Program Files): kayıtlar
    pakete değil kullanıcı klasörüne gitmelidir."""
    sonuc, paket, veri_koku = _paketlenmis_sistemi_baslat(tmp_path)
    assert sonuc.returncode == 0, sonuc.stderr

    assert (veri_koku / ".env").is_file(), ".env örnekten üretilmemiş"
    assert (veri_koku / "veri" / "dalsan.db").is_file(), "veritabanı kullanıcı klasöründe yok"
    assert not (paket / "veri").exists(), "pakete yazılmış — paket salt okunur olmalı"
    assert not (paket / ".env").exists(), "ayar dosyası pakete yazılmış"

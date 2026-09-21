"""İzleme ekranı TARAYICI SEKMESİ yerine uygulama penceresinde açılıyor mu?

Kullanıcının şikâyeti şuydu: "Windows ve Mac'te uygulama olarak gözüksün,
tarayıcıda açılıyordu." Buradaki testler o davranışın geri gelmemesini korur.

GERÇEK BİR PENCERE AÇILMAZ. Açılabilseydi de bu makinede Chrome/Edge yok ve
test çalıştırması ekranda bir pencere bırakırdı. Ölçülen şey, kararın kendisi:
hangi tarayıcı seçiliyor, komut satırı uygulama kipini istiyor mu, tarayıcı
bulunamayınca ne oluyor.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MASAUSTU = KOK / "masaustu"
PENCERE = MASAUSTU / "uygulama_penceresi.py"
LAUNCHER = MASAUSTU / "dalsan_launcher.py"


@pytest.fixture
def pencere():
    """Modülü tek başına yükler (masaustu/ bir paket değildir)."""
    tanim = importlib.util.spec_from_file_location("uygulama_penceresi_test", PENCERE)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


# ------------------------------------------------------- komut satırı kararı


def test_komut_uygulama_kipini_ister(pencere):
    """`--app=` olmazsa açılan şey sekmeli, adres çubuklu bir tarayıcıdır."""
    satir = pencere.komut("/yol/chrome", "http://127.0.0.1:8080")
    assert satir[0] == "/yol/chrome"
    assert "--app=http://127.0.0.1:8080" in satir
    # Adresin AYRI bir argüman olarak da geçirilmemesi gerekir: geçseydi
    # tarayıcı biri uygulama penceresi, biri sekme olmak üzere İKİ pencere açardı.
    assert "http://127.0.0.1:8080" not in satir


def test_ayri_profil_verilir(pencere, tmp_path):
    """Profilsiz pencere kullanıcının açık tarayıcı oturumunun içine düşer:
    tarayıcı kapanınca sistem ekranı da kapanır ve görev çubuğunda tarayıcıyla
    aynı simgenin altında gruplanır."""
    satir = pencere.komut("/yol/chrome", "http://127.0.0.1:8080", tmp_path / "profil")
    assert any(a.startswith("--user-data-dir=") for a in satir)


def test_profil_verilmezse_bayrak_hic_konmaz(pencere):
    satir = pencere.komut("/yol/chrome", "http://127.0.0.1:8080")
    assert not any(a.startswith("--user-data-dir=") for a in satir)


def test_pencere_boyutu_verilir(pencere):
    satir = pencere.komut("/yol/chrome", "http://x")
    assert f"--window-size={pencere.PENCERE_GENISLIGI}," in " ".join(satir)


# --------------------------------------------------------- tarayıcı seçimi


def test_windowsta_edge_ilk_sirada(pencere):
    """Windows'ta Edge HER kurulumda vardır ve kaldırılamaz.

    İlk sırada olması, hiçbir şey kurmamış bir kullanıcıda da uygulama
    penceresinin açılması demektir — Chrome önde olsaydı Chrome'suz bir
    bilgisayarda liste boşa dönebilirdi.
    """
    assert pencere._WINDOWS_ADAYLARI[0][-1] == "msedge.exe"


def test_safari_ve_firefox_aday_degil(pencere):
    """İkisinin de uygulama kipi yoktur; listeye konsalardı sıradan bir
    sekme açılır, üstelik "uygulama gibi açıldı" sanılırdı."""
    hepsi = " ".join(
        ["/".join(aday) for aday in pencere._WINDOWS_ADAYLARI]
        + list(pencere._MAC_ADAYLARI)
        + list(pencere._LINUX_ADAYLARI)
    ).lower()
    assert "safari" not in hepsi
    assert "firefox" not in hepsi


def test_windowsta_kullaniciya_ozel_kurulum_da_aranir(pencere, monkeypatch, tmp_path):
    """Chrome, yönetici hakkı olmayan bilgisayarlarda LOCALAPPDATA altına kurulur.

    Yalnız "Program Files"a bakan bir arama onu hiç bulamaz ve kullanıcı
    Chrome'u olduğu halde tarayıcı sekmesi görür.
    """
    yerel = tmp_path / "Local"
    hedef = yerel / "Google" / "Chrome" / "Application" / "chrome.exe"
    hedef.parent.mkdir(parents=True)
    hedef.write_text("")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(yerel))
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    assert pencere.tarayici_bul() == str(hedef)


def test_tarayici_yoksa_none(pencere, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    assert pencere.tarayici_bul() is None


# ------------------------------------------------------------ geri çekilme


def test_tarayici_bulunamazsa_olagan_tarayici_acilir(pencere, monkeypatch):
    """Uygulama penceresi açılamıyor diye EKRAN HİÇ AÇILMAMASI daha kötüdür."""
    acilanlar, gunluk = [], []
    monkeypatch.setattr(pencere, "tarayici_bul", lambda: None)
    monkeypatch.setattr(pencere.webbrowser, "open", acilanlar.append)

    assert pencere.ac("http://127.0.0.1:8080", log=gunluk.append) is False
    assert acilanlar == ["http://127.0.0.1:8080"]
    # Kullanıcı NEDEN uygulama penceresi görmediğini öğrenmeli.
    assert gunluk and "Chrome" in gunluk[0]


def test_tarayici_calistirilamazsa_da_ekran_acilir(pencere, monkeypatch):
    """Dosya duruyor ama çalıştırılamıyor (izin, bozuk kurulum, virüs koruması)."""
    acilanlar, gunluk = [], []
    monkeypatch.setattr(pencere, "tarayici_bul", lambda: "/yol/chrome")
    monkeypatch.setattr(pencere.webbrowser, "open", acilanlar.append)

    def patlat(*_a, **_k):
        raise OSError("izin yok")

    monkeypatch.setattr(pencere.subprocess, "Popen", patlat)
    assert pencere.ac("http://x", log=gunluk.append) is False
    assert acilanlar == ["http://x"]
    assert gunluk and "izin yok" in gunluk[0]


def test_basarili_acilista_tarayici_sekmesi_acilmaz(pencere, monkeypatch, tmp_path):
    """İkisi birden çalışsaydı kullanıcı her seferinde İKİ pencere görürdü."""
    acilanlar, cagrilar = [], []
    monkeypatch.setattr(pencere, "tarayici_bul", lambda: "/yol/chrome")
    monkeypatch.setattr(pencere.webbrowser, "open", acilanlar.append)
    monkeypatch.setattr(pencere.subprocess, "Popen", lambda *a, **k: cagrilar.append(a))

    assert pencere.ac("http://x", tmp_path / "profil") is True
    assert acilanlar == []
    assert len(cagrilar) == 1
    assert (tmp_path / "profil").is_dir()


def test_profil_klasoru_acilamazsa_pencere_yine_acilir(pencere, monkeypatch, tmp_path):
    """Bozuk bir --user-data-dir veren tarayıcı HİÇ açılmaz; bayrağı hiç verme."""
    cagrilar = []
    engel = tmp_path / "dosya"
    engel.write_text("")  # klasör olarak oluşturulamaz
    monkeypatch.setattr(pencere, "tarayici_bul", lambda: "/yol/chrome")
    monkeypatch.setattr(pencere.subprocess, "Popen", lambda *a, **k: cagrilar.append(a[0]))

    assert pencere.ac("http://x", engel / "profil") is True
    assert not any(a.startswith("--user-data-dir=") for a in cagrilar[0])


# ------------------------------------------- Kontrol Paneli gerçekten kullanıyor mu


def _launcher_kaynagi() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def test_panel_ekrani_tarayici_sekmesinde_acmiyor():
    """Asıl korunan şey bu: `webbrowser.open(URL)` düğmeye geri bağlanmasın.

    Modül metin olarak okunuyor çünkü dalsan_launcher import edildiğinde
    ayar dosyalarını okuyup klasör yolları çözüyor; testin yan etkisi olmamalı.
    """
    kaynak = _launcher_kaynagi()
    agac = ast.parse(kaynak)
    geri_cekilme = 0
    for dugum in ast.walk(agac):
        if (
            isinstance(dugum, ast.Call)
            and isinstance(dugum.func, ast.Attribute)
            and dugum.func.attr == "open"
            and isinstance(dugum.func.value, ast.Name)
            and dugum.func.value.id == "webbrowser"
        ):
            geri_cekilme += 1
    # Tek bir çağrı kalmalı: `uygulama_penceresi` hiç yüklenemediğinde
    # kullanılan son çare (izleme_ekranini_ac içinde).
    assert geri_cekilme == 1, (
        "İzleme ekranı tarayıcı sekmesinde açılıyor. Uygulama penceresi için "
        "izleme_ekranini_ac() kullanılmalı."
    )
    assert "izleme_ekranini_ac(log)" in kaynak, "düğme uygulama penceresini çağırmalı"


def test_panel_profil_klasorunu_veri_disina_koyar():
    """veri/ yedekleniyor ("veri/ klasörünü kopyala"); tarayıcı önbelleği
    oraya konsaydı her yedek yüzlerce megabayt şişerdi."""
    kaynak = _launcher_kaynagi()
    assert 'TARAYICI_PROFILI = ROOT / "tarayici-profili"' in kaynak
    assert "tarayici-profili/" in (KOK / ".gitignore").read_text(encoding="utf-8")


def test_windows_gorev_cubugu_kimligi_kuruluyor():
    """Bu satır olmadan pencere, görev çubuğunda PYTHON'un simgesiyle çıkar
    ve başka bir Python programıyla aynı yığına girer."""
    kaynak = _launcher_kaynagi()
    assert "SetCurrentProcessExplicitAppUserModelID" in kaynak
    # Pencere oluşmadan ÖNCE çağrılmalı: Windows simgeyi ilk çizimde okur.
    assert kaynak.index("windows_uygulama_kimligini_kur()\n\n    kok = tk.Tk()") > 0


def test_pencere_simgesi_pakete_konuyor():
    """Tk penceresi simgeyi çalışma anında AYRI bir dosyadan okur; .exe'ye
    gömülü simge onun için yeterli değildir."""
    ortak = (KOK / "paketleme" / "paketleme_ortak.py").read_text(encoding="utf-8")
    assert "NextGenDetector.ico" in ortak
    assert '"uygulama_penceresi"' in ortak, "modül pakete alınmalı"
    assert (KOK / "paketleme" / "NextGenDetector.ico").is_file()

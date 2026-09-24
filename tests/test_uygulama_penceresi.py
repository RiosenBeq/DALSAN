"""İzleme ekranı TARAYICI AÇMADAN, programın kendi penceresinde açılıyor mu?

Kullanıcının iki şikâyeti var: önce "Windows ve Mac'te uygulama olarak
gözüksün, tarayıcıda açılıyordu", sonra (23.09.2026) "tarayıcı da açılmaması
lazım ... fabrikada olacağı için". Buradaki testler o davranışın geri
gelmemesini korur.

GERÇEK BİR PENCERE AÇILMAZ. Pencere süreci gerçekten başlatılır ama
`pywebview` yerine SAHTESİNİ bulur: sahte kütüphane pencere çizmez, olayları
gerçeğinin sırasıyla tetikler ve her çağrıyı bir dosyaya yazar. Böylece
Kontrol Paneli ile pencere süreci arasındaki dil (HAZIR, GOSTER, kanalın
kapanması) gerçek borular üzerinden sınanır. Sahte kütüphanenin taklit
ettiği davranış pywebview 6.2.1'in kaynağından okundu (docs/16).
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MASAUSTU = KOK / "masaustu"
PENCERE = MASAUSTU / "uygulama_penceresi.py"
LAUNCHER = MASAUSTU / "dalsan_launcher.py"
WEB = KOK / "backend" / "app" / "web"

ADRES = "http://127.0.0.1:9"

SAHTE_WEBVIEW = '''\
"""Sahte pywebview: pencere AÇMAZ; olayları gerçeğinin sırasıyla tetikler.

Ortam: SAHTE_MOTOR (web motorunun adı), SAHTE_YUKLE ("0" ise sayfa hiç
yüklenmez), SAHTE_KAYIT (her çağrının yazıldığı JSON satırları dosyası),
SAHTE_KAPAT (bu dosya belirince kullanıcı pencereyi kapatmış sayılır).
"""
import inspect
import json
import os
import threading
import time

settings = {"ALLOW_DOWNLOADS": False, "OPEN_EXTERNAL_LINKS_IN_BROWSER": True}
windows = []


def _kaydet(*kayit):
    yol = os.environ.get("SAHTE_KAYIT")
    if yol:
        with open(yol, "a", encoding="utf-8") as dosya:
            dosya.write(json.dumps(kayit) + "\\n")


class _Olay:
    def __init__(self):
        self._isler = []
        self._olay = threading.Event()

    def __iadd__(self, is_):
        self._isler.append(is_)
        return self

    def set(self, *bilgi):
        donenler = [
            is_(*bilgi) if inspect.signature(is_).parameters else is_()
            for is_ in self._isler
        ]
        self._olay.set()
        return any(donen is False for donen in donenler)

    def wait(self, sure=None):
        return self._olay.wait(sure)


class _Pencere:
    def __init__(self):
        self.events = type("Olaylar", (), {})()
        for ad in ("initialized", "shown", "loaded", "minimized", "maximized", "restored"):
            setattr(self.events, ad, _Olay())
        self.kapandi = threading.Event()

    def show(self):
        _kaydet("show")

    def restore(self):
        _kaydet("restore")

    def maximize(self):
        _kaydet("maximize")

    def destroy(self):
        _kaydet("destroy")
        self.kapandi.set()


def create_window(baslik, adres, **secenek):
    _kaydet("create_window", baslik, adres, secenek)
    pencere = _Pencere()
    windows.append(pencere)
    return pencere


def _kullanici_kapatirsa(pencere):
    yol = os.environ.get("SAHTE_KAPAT")
    while yol and not pencere.kapandi.is_set():
        if os.path.exists(yol):
            _kaydet("kullanici_kapatti")
            pencere.kapandi.set()
        time.sleep(0.05)


def start(func=None, args=None, **secenek):
    _kaydet("start", secenek, dict(settings))
    pencere = windows[0]
    # Gerçeği gibi: `initialized` işleyicisi False dönerse pencere hiç açılmaz.
    if pencere.events.initialized.set(os.environ.get("SAHTE_MOTOR", "edgechromium")):
        return
    pencere.events.shown.set()
    if os.environ.get("SAHTE_YUKLE", "1") == "1":
        pencere.events.loaded.set()
    threading.Thread(target=_kullanici_kapatirsa, args=(pencere,), daemon=True).start()
    pencere.kapandi.wait()
'''


@pytest.fixture
def pencere():
    """Modülü tek başına yükler (masaustu/ bir paket değildir)."""
    tanim = importlib.util.spec_from_file_location("uygulama_penceresi_test", PENCERE)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    yield modul
    modul.pencereyi_kapat()  # test yarıda kalsa da pencere süreci ortada kalmasın


@pytest.fixture
def sahte_webview(tmp_path, monkeypatch):
    """Pencere süreci `import webview` deyince sahtesini bulur; kayıt dosyasını döner."""
    paket = tmp_path / "sahte" / "webview"
    paket.mkdir(parents=True)
    (paket / "__init__.py").write_text(SAHTE_WEBVIEW, encoding="utf-8")
    kayit = tmp_path / "kayit.jsonl"
    monkeypatch.setenv("PYTHONPATH", str(paket.parent))
    monkeypatch.setenv("SAHTE_KAYIT", str(kayit))
    monkeypatch.delenv("SAHTE_MOTOR", raising=False)
    monkeypatch.delenv("SAHTE_YUKLE", raising=False)
    return kayit


def _kayitlar(dosya: Path) -> list[list]:
    if not dosya.exists():
        return []
    return [json.loads(satir) for satir in dosya.read_text(encoding="utf-8").splitlines()]


def _sahte_modul(sahte_kayit: Path, monkeypatch):
    """Sahte kütüphaneyi BU süreçte `webview` olarak yükler."""
    tanim = importlib.util.spec_from_file_location(
        "webview", sahte_kayit.parent / "sahte" / "webview" / "__init__.py"
    )
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    monkeypatch.setitem(sys.modules, "webview", modul)
    return modul


# ------------------------------------------------------- pencere süreci (gerçek)


def test_pencere_acilir_one_gelir_ve_panelle_birlikte_kapanir(pencere, sahte_webview, tmp_path):
    """Asıl akış: pencere süreci açılır, ikinci tıklama yeni pencere açmaz,
    panel kapanınca pencere de kapanır. Hepsi gerçek borularla."""
    gunluk = []
    assert pencere.ac(ADRES, tmp_path / "profil", log=gunluk.append) is True
    surec = pencere._yerel_surec
    assert surec is not None and surec.poll() is None, "pencere açık olmalı"

    # İkinci tıklama: aynı süreç, "öne gel" satırı gider.
    assert pencere.ac(ADRES, tmp_path / "profil", log=gunluk.append) is True
    assert pencere._yerel_surec is surec

    pencere.pencereyi_kapat()
    assert surec.wait(timeout=10) == 0
    adlar = [kayit[0] for kayit in _kayitlar(sahte_webview)]
    assert adlar.count("create_window") == 1, "ikinci pencere açılmamalı"
    assert adlar.index("show") < adlar.index("destroy"), "önce öne geldi, sonra kapandı"
    assert gunluk == [], gunluk


def test_kullanici_pencereyi_kapatinca_surec_biter(pencere, sahte_webview, monkeypatch, tmp_path):
    """Kullanıcı pencereyi kapattığında panelin kanalı AÇIKTIR ve pencere
    süreci onu dinlemektedir. Süreç yine de hemen bitmeli: bitmeseydi panel
    onu açık sanar, düğmeye basılınca penceresi olmayan bir sürece "öne gel"
    der ve kullanıcı hiçbir şey görmezdi."""
    kapat = tmp_path / "kapat"
    monkeypatch.setenv("SAHTE_KAPAT", str(kapat))
    assert pencere.ac(ADRES, tmp_path / "profil") is True
    surec = pencere._yerel_surec

    kapat.write_text("")
    assert surec.wait(timeout=10) == 0

    kapat.unlink()
    assert pencere.ac(ADRES, tmp_path / "profil") is True
    assert pencere._yerel_surec is not None and pencere._yerel_surec is not surec


def test_ie_motoruna_dusulurse_pencere_acilmaz_yedege_gecilir(
    pencere, sahte_webview, monkeypatch, tmp_path
):
    """WebView2 yoksa pywebview Windows'ta Internet Explorer motoruna düşer;
    izleme ekranı orada çalışmaz. Pencere hiç açılmamalı, yedek devreye girmeli."""
    monkeypatch.setenv("SAHTE_MOTOR", "mshtml")
    yedek, gunluk = [], []
    monkeypatch.setattr(
        pencere, "_uygulama_kipinde_ac", lambda adres, profil, yaz: yedek.append(adres) or True
    )
    assert pencere.ac(ADRES, tmp_path / "profil", log=gunluk.append) is True
    assert yedek == [ADRES]
    adlar = [kayit[0] for kayit in _kayitlar(sahte_webview)]
    assert "start" in adlar and "show" not in adlar
    assert any("WebView2" in satir for satir in gunluk), gunluk


def test_pywebview_yoksa_yedek_pencere_acilir(pencere, sahte_webview, monkeypatch, tmp_path):
    (sahte_webview.parent / "sahte" / "webview" / "__init__.py").write_text(
        'raise ImportError("sahte: pywebview kurulu değil")\n', encoding="utf-8"
    )
    yedek, gunluk = [], []
    monkeypatch.setattr(
        pencere, "_uygulama_kipinde_ac", lambda adres, profil, yaz: yedek.append(adres) or True
    )
    assert pencere.ac(ADRES, tmp_path / "profil", log=gunluk.append) is True
    assert yedek == [ADRES]
    assert any("pywebview" in satir for satir in gunluk), gunluk


def test_program_izleme_penceresi_olarak_acilir(sahte_webview):
    """Paketlenmiş uygulamada pencere süreci programın KENDİSİDİR: Kontrol
    Paneli'nin giriş betiği bağımsız değişkeni görünce Tk kurmadan pencereyi
    açmalı. Kurmasaydı her pencere için ikinci bir panel açılırdı."""
    sonuc = subprocess.run(
        [sys.executable, str(LAUNCHER), "--izleme-penceresi", ADRES],
        stdin=subprocess.DEVNULL,  # kanal hemen kapanır: pencere açılıp kapanmalı
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert "HAZIR" in sonuc.stdout
    adlar = [kayit[0] for kayit in _kayitlar(sahte_webview)]
    assert adlar[0] == "create_window" and adlar[-1] == "destroy"


def test_paket_sinamasi_pencere_acmadan_biter(sahte_webview):
    """`--pencere-denetimi`: üretim hattı paketin pencere bileşenini sınar."""
    sonuc = subprocess.run(
        [sys.executable, str(LAUNCHER), "--pencere-denetimi"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert "pywebview yüklü" in sonuc.stdout
    assert _kayitlar(sahte_webview) == [], "denetim pencere açmamalı"


# ------------------------------------------------------ pencere süreci (içeride)


def test_pencere_ayarlari(pencere, sahte_webview, monkeypatch, tmp_path, capsys):
    """Tarayıcı açan bağlantı yok, indirmeler kaydetme penceresiyle çalışır,
    oturum ve ses tercihi kalıcı, sayfa olağan bir sayfa gibi davranır."""
    _sahte_modul(sahte_webview, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO("GOSTER\n"))
    assert pencere.yerel_pencereyi_calistir(ADRES, tmp_path / "profil") == 0

    kayitlar = _kayitlar(sahte_webview)
    pencere_kaydi = next(k for k in kayitlar if k[0] == "create_window")
    _, baslik, adres, secenek = pencere_kaydi
    assert "NextGen Detector" in baslik and adres == ADRES
    assert secenek["min_size"] == list(pencere.EN_KUCUK_PENCERE)
    assert secenek["text_select"] is True and secenek["zoomable"] is True

    _, baslatma, ayarlar = next(k for k in kayitlar if k[0] == "start")
    assert baslatma["private_mode"] is False
    assert baslatma["storage_path"] == str(tmp_path / "profil")
    assert baslatma["localization"] == pencere.PYWEBVIEW_METINLERI, "menü ve düğmeler Türkçe"
    assert ayarlar["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is False, "tarayıcı açılmamalı"
    assert ayarlar["ALLOW_DOWNLOADS"] is True, "CSV ve veri seti indirilebilmeli"

    assert [k[0] for k in kayitlar][-2:] == ["show", "destroy"]
    assert "HAZIR" in capsys.readouterr().out


# pywebview 6.2.1 webview/localization.py: kendi metinlerinin tamamı
PYWEBVIEW_ANAHTARLARI = {
    "global.quitConfirmation",
    "global.ok",
    "global.quit",
    "global.cancel",
    "global.saveFile",
    "cocoa.menu.about",
    "cocoa.menu.services",
    "cocoa.menu.view",
    "cocoa.menu.edit",
    "cocoa.menu.hide",
    "cocoa.menu.hideOthers",
    "cocoa.menu.showAll",
    "cocoa.menu.quit",
    "cocoa.menu.fullscreen",
    "cocoa.menu.cut",
    "cocoa.menu.copy",
    "cocoa.menu.paste",
    "cocoa.menu.selectAll",
    "windows.fileFilter.allFiles",
    "windows.fileFilter.otherFiles",
    "linux.openFile",
    "linux.openFiles",
    "linux.openFolder",
}


def test_pywebview_metinleri_turkce(pencere):
    """Mac menüsü, onay kutusu düğmeleri ve kaydetme penceresi pywebview'ün
    kendi metinleridir; verilmeyen anahtar İngilizce kalır (arayüz Türkçe)."""
    assert set(pencere.PYWEBVIEW_METINLERI) == PYWEBVIEW_ANAHTARLARI
    ingilizce = {"OK", "Cancel", "Quit", "About", "Hide", "Edit", "View", "Copy"}
    assert not ingilizce & set(pencere.PYWEBVIEW_METINLERI.values())
    assert pencere.PYWEBVIEW_METINLERI["global.ok"] == "Tamam"


def test_pywebview_metinleri_kurulu_surumle_ayni(pencere):
    """Paketleme ortamında pywebview kuruluysa anahtarlar onunkiyle aynı olmalı:
    yeni sürüm yeni bir metin eklerse o metin İngilizce kalmasın."""
    yerel = pytest.importorskip("webview.localization")
    assert set(pencere.PYWEBVIEW_METINLERI) == set(yerel.original_localization)


def test_sayfa_hic_yuklenmezse_pencere_kapanir_ve_hata_doner(
    pencere, sahte_webview, monkeypatch, tmp_path, capsys
):
    """WebView2 kuruldu ama çalışmıyor: boş beyaz bir pencere açık kalmamalı,
    panel yedek pencereye geçebilsin diye süreç hata koduyla bitmeli."""
    monkeypatch.setenv("SAHTE_YUKLE", "0")
    _sahte_modul(sahte_webview, monkeypatch)
    monkeypatch.setattr(pencere, "YUKLEME_BEKLEMESI_SN", 0.2)
    assert pencere.yerel_pencereyi_calistir(ADRES) == pencere.KOD_WEB_GORUNUMU_KURULAMADI
    assert [k[0] for k in _kayitlar(sahte_webview)][-1] == "destroy"
    assert "HATA sayfa" in capsys.readouterr().out


def test_panel_ile_yukleme_bekleme_sureleri_uyumlu(pencere):
    """Panel, yüklenemeyen pencerenin kendini kapatmasını beklemeli; yoksa
    yedek pencere hiç açılmaz ve kullanıcı boş bir pencereyle kalır."""
    assert pencere.YEREL_ACILIS_BEKLEMESI_SN > pencere.YUKLEME_BEKLEMESI_SN + 10


@pytest.mark.parametrize(
    ("kucuk", "buyuk", "beklenen"),
    [
        (False, False, ["show"]),
        (True, False, ["restore", "show"]),
        (True, True, ["maximize", "show"]),  # tam ekrandıysa yine tam ekran
    ],
)
def test_one_getirirken_eski_boyutuna_doner(pencere, kucuk, buyuk, beklenen):
    cagrilar = []

    class Kayitci:
        def __getattr__(self, ad):
            return lambda: cagrilar.append(ad)

    pencere._one_getir(Kayitci(), {"kucuk": kucuk, "buyuk": buyuk})
    assert cagrilar == beklenen


def test_pencere_sureci_programin_kendisidir(pencere, monkeypatch, tmp_path):
    """Paketlenmiş uygulamada ayrı bir Python yoktur: pencere, programın
    kendisinin bir bağımsız değişkenle açılmış kopyasıdır."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Uygulama/NextGen Detector")
    assert pencere.yerel_pencere_komutu(ADRES, tmp_path) == [
        "/Uygulama/NextGen Detector",
        "--izleme-penceresi",
        ADRES,
        str(tmp_path),
    ]


def test_gelistirmede_pencere_sureci_bu_dosyadir(pencere, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    satir = pencere.yerel_pencere_komutu(ADRES)
    assert satir[1] == str(PENCERE.resolve())
    assert satir[2:] == ["--izleme-penceresi", ADRES]


# ------------------------------------------------------------ tarayıcısız yedek


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


def test_windowsta_edge_ilk_sirada(pencere):
    """Windows'ta Edge HER kurulumda vardır ve kaldırılamaz.

    İlk sırada olması, hiçbir şey kurmamış bir kullanıcıda da yedek
    pencerenin açılması demektir - Chrome önde olsaydı Chrome'suz bir
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

    Yalnız "Program Files"a bakan bir arama onu hiç bulamaz.
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


def test_yedek_pencere_profilini_olusturur(pencere, monkeypatch, tmp_path):
    cagrilar, gunluk = [], []
    monkeypatch.setattr(pencere, "_yerel_pencere_dene", lambda *a: False)
    monkeypatch.setattr(pencere, "tarayici_bul", lambda: "/yol/chrome")
    monkeypatch.setattr(pencere.subprocess, "Popen", lambda *a, **k: cagrilar.append(a[0]))

    assert pencere.ac("http://x", tmp_path / "profil", log=gunluk.append) is True
    assert len(cagrilar) == 1 and "--app=http://x" in cagrilar[0]
    assert (tmp_path / "profil").is_dir()
    assert any("yedek pencere" in satir for satir in gunluk)


def test_profil_klasoru_acilamazsa_yedek_pencere_yine_acilir(pencere, monkeypatch, tmp_path):
    """Bozuk bir --user-data-dir veren tarayıcı HİÇ açılmaz; bayrağı hiç verme."""
    cagrilar = []
    engel = tmp_path / "dosya"
    engel.write_text("")  # klasör olarak oluşturulamaz
    monkeypatch.setattr(pencere, "_yerel_pencere_dene", lambda *a: False)
    monkeypatch.setattr(pencere, "tarayici_bul", lambda: "/yol/chrome")
    monkeypatch.setattr(pencere.subprocess, "Popen", lambda *a, **k: cagrilar.append(a[0]))

    assert pencere.ac("http://x", engel / "profil") is True
    assert not any(a.startswith("--user-data-dir=") for a in cagrilar[0])


def test_hicbir_pencere_acilamazsa_tarayici_sekmesi_de_acilmaz(pencere, monkeypatch):
    """Operatör kararı: tarayıcı AÇILMAZ. Kullanıcı ne yapacağını günlükten öğrenir."""
    gunluk = []
    monkeypatch.setattr(pencere, "_yerel_pencere_dene", lambda *a: False)
    monkeypatch.setattr(pencere, "tarayici_bul", lambda: None)

    assert pencere.ac(ADRES, log=gunluk.append) is False
    assert len(gunluk) == 1
    assert "WebView2" in gunluk[0] and ADRES in gunluk[0]


def test_yedek_pencere_calistirilamazsa_sebep_yazilir(pencere, monkeypatch):
    """Dosya duruyor ama çalıştırılamıyor (izin, bozuk kurulum, virüs koruması)."""
    gunluk = []
    monkeypatch.setattr(pencere, "_yerel_pencere_dene", lambda *a: False)
    monkeypatch.setattr(pencere, "tarayici_bul", lambda: "/yol/chrome")

    def patlat(*_a, **_k):
        raise OSError("izin yok")

    monkeypatch.setattr(pencere.subprocess, "Popen", patlat)
    assert pencere.ac("http://x", log=gunluk.append) is False
    assert "izin yok" in gunluk[0]


# ------------------------------------------- tarayıcı hiçbir yoldan açılmıyor mu


def _tarayici_kullanimi(dosya: Path) -> list[str]:
    """`webbrowser` modülünün import edildiği ya da kullanıldığı satırlar."""
    bulunan = []
    for dugum in ast.walk(ast.parse(dosya.read_text(encoding="utf-8"))):
        if isinstance(dugum, ast.Import | ast.ImportFrom):
            adlar = [a.name for a in dugum.names] + [getattr(dugum, "module", None) or ""]
            if "webbrowser" in adlar:
                bulunan.append(f"{dosya.name}:{dugum.lineno}")
        elif isinstance(dugum, ast.Name) and dugum.id == "webbrowser":
            bulunan.append(f"{dosya.name}:{dugum.lineno}")
    return bulunan


def test_panel_ve_pencere_tarayici_acmaz():
    """Asıl korunan şey bu: `webbrowser.open(...)` hiçbir yoldan geri gelmesin.

    Dosyalar metin olarak okunuyor çünkü dalsan_launcher import edildiğinde
    ayar dosyalarını okuyup klasör yolları çözüyor; testin yan etkisi olmamalı.
    """
    assert _tarayici_kullanimi(LAUNCHER) == []
    assert _tarayici_kullanimi(PENCERE) == []


def test_arayuzde_yeni_pencere_acan_baglanti_yok():
    """Uygulama penceresinin sekmesi ve geri düğmesi yoktur. `target=_blank`
    ya da `window.open` o pencerede ya tarayıcıyı açar ya da ekranın yerine
    geçip kullanıcıyı geri dönemeyeceği bir sayfada bırakır."""
    bulunan = []
    for dosya in [*WEB.glob("templates/**/*.html"), *WEB.glob("static/*.js")]:
        metin = dosya.read_text(encoding="utf-8")
        if re.search(r"""target\s*=\s*["']?_blank|window\.open\s*\(""", metin):
            bulunan.append(dosya.name)
    assert bulunan == []


def test_disa_aktarma_baglantilari_indirme_olarak_isaretli():
    """`download` işareti olmayan bir CSV bağlantısı macOS'un web görünümünde
    dosyayı İNDİRMEZ, pencerede düz metin olarak açar - geri düğmesi olmayan
    bir pencerede kullanıcı orada kalır. İşaretliyse kaydetme penceresi açılır."""
    eksik = []
    for dosya in WEB.glob("templates/**/*.html"):
        for etiket in re.findall(r"<a\b[^>]*>", dosya.read_text(encoding="utf-8")):
            if re.search(r'href="[^"]*\.(csv|zip)\b', etiket) and not re.search(
                r"\sdownload\b", etiket
            ):
                eksik.append(f"{dosya.name}: {etiket[:80]}")
    assert eksik == []


# ------------------------------------------- Kontrol Paneli gerçekten kullanıyor mu


def _launcher_kaynagi() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def _fonksiyon(ad: str) -> ast.FunctionDef:
    for dugum in ast.walk(ast.parse(_launcher_kaynagi())):
        if isinstance(dugum, ast.FunctionDef) and dugum.name == ad:
            return dugum
    raise AssertionError(f"{ad} bulunamadı")


def test_dugme_ve_otomatik_acilis_ayni_pencereyi_acar():
    kaynak = _launcher_kaynagi()
    assert kaynak.count("izleme_ekranini_ac(log)") >= 2, "düğme ve otomatik açılış"


def test_pencere_arka_planda_acilir():
    """Pencerenin açıldığı saniyeler içinde anlaşılır; bu sırada Kontrol
    Paneli donmamalı (düğmeler, günlük, Durdur çalışmalı)."""
    govde = ast.unparse(_fonksiyon("izleme_ekranini_ac"))
    assert "threading.Thread(" in govde and "uygulama_penceresi.ac" in govde


def test_panel_kapaninca_izleme_penceresi_de_kapanir():
    govde = ast.unparse(_fonksiyon("arayuzu_baslat"))
    kapanis = govde[govde.index("def kapanirken") :]
    assert kapanis.index("izleme_penceresini_kapat()") < kapanis.index("sistemi_durdur()")


def test_pencere_sureci_tk_kurulmadan_ayrilir():
    """Ayrılmasaydı her izleme penceresi için ikinci bir Kontrol Paneli açılır,
    o da sistemi bir daha başlatmaya kalkardı."""
    kaynak = _launcher_kaynagi()
    ana = kaynak[kaynak.index('if __name__ == "__main__":') :]
    assert ana.index("pencere_sureci_mi(sys.argv[1:])") < ana.index("arayuzu_baslat()")


def test_panel_profil_klasorunu_veri_disina_koyar():
    """veri/ yedekleniyor ("veri/ klasörünü kopyala"); pencere önbelleği
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
    # İzleme penceresi de panelle aynı uygulama olarak görünür.
    assert "windows_uygulama_kimligini_kur()" in ast.unparse(
        _fonksiyon("pencere_surecini_calistir")
    )


def test_pencere_simgesi_pakete_konuyor():
    """Tk penceresi simgeyi çalışma anında AYRI bir dosyadan okur; .exe'ye
    gömülü simge onun için yeterli değildir."""
    ortak = (KOK / "paketleme" / "paketleme_ortak.py").read_text(encoding="utf-8")
    assert "NextGenDetector.ico" in ortak
    assert '"uygulama_penceresi"' in ortak, "modül pakete alınmalı"
    assert (KOK / "paketleme" / "NextGenDetector.ico").is_file()


# ------------------------------------------ üretim hattının pencere sınaması


def _sinama_modulu():
    tanim = importlib.util.spec_from_file_location(
        "pencere_sinamasi_test", KOK / "paketleme" / "pencere_sinamasi.py"
    )
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


def _program_sarici(tmp_path: Path) -> str:
    """Paketlenmiş programın yerine geçen betik: Kontrol Paneli'nin giriş
    betiğini aynı bağımsız değişkenlerle çalıştırır."""
    sarici = tmp_path / "NextGen Detector"
    sarici.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{LAUNCHER}" "$@"\n')
    sarici.chmod(0o755)
    return str(sarici)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="sarıcı bir kabuk betiği")
def test_uretim_hattinin_pencere_sinamasi_gecer(sahte_webview, tmp_path, monkeypatch):
    """GitHub Actions paketi yayımlamadan önce bunu çalıştırır; burada sahte
    kütüphaneyle, gerçek süreçler ve borularla uçtan uca koşar."""
    sinama = _sinama_modulu()
    monkeypatch.setattr(sinama, "MOTOR_BEKLEMESI_SN", 0.2)  # sahte sayfa çizmez
    sinama.pencere_sina(_program_sarici(tmp_path), None)
    assert [k[0] for k in _kayitlar(sahte_webview)][-2:] == ["show", "destroy"]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="sarıcı bir kabuk betiği")
def test_uretim_hattinin_pencere_sinamasi_ie_motorunu_yakalar(sahte_webview, tmp_path, monkeypatch):
    """WebView2'siz bir makinede sınama KIRMIZI olmalı: paket o haliyle
    yayımlansaydı ekran yedek pencerede açılırdı ve kimse fark etmezdi."""
    monkeypatch.setenv("SAHTE_MOTOR", "mshtml")
    sinama = _sinama_modulu()
    with pytest.raises(sinama.SinamaHatasi, match="HAZIR demeden 4"):
        sinama.pencere_sina(_program_sarici(tmp_path), None)


class _SaglikSunucusu:
    """/saglik yanıtlarını sırayla veren yerel sunucu (tam sınamanın model beklemesi)."""

    def __init__(self, yanitlar: list[dict]) -> None:
        import http.server
        import threading

        kalan = list(yanitlar)

        class _Isleyici(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server arayüzü
                govde = json.dumps(kalan.pop(0) if len(kalan) > 1 else kalan[0]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(govde)

            def log_message(self, *_):
                pass

        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Isleyici)
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()
        self.adres = f"http://127.0.0.1:{self.sunucu.server_address[1]}/saglik"

    def kapat(self) -> None:
        self.sunucu.shutdown()
        self.sunucu.server_close()


class _CalisanSurec:
    returncode = None

    def poll(self):
        return None


@pytest.mark.parametrize(
    ("yanitlar", "beklenen"),
    [
        ([{"model": "indiriliyor"}, {"model": "yukleniyor"}, {"model": "hazir"}], "hazir"),
        ([{"model": "indiriliyor"}, {"model": "hata", "sorunlar": ["model_yuklenemedi"]}], None),
    ],
)
def test_tam_sinama_modelin_yuklenmesini_bekler(monkeypatch, yanitlar, beklenen):
    """Model inmez ya da yüklenemezse paket tespitsiz çalışırdı; /saglik yanıt
    veriyor diye sınama geçmemeli. Forklift modeli ilk açılışta DALSAN'ın
    kendi yayınından iner: yayın dosyası eksikse burada yakalanır."""
    sinama = _sinama_modulu()
    sunucu = _SaglikSunucusu(yanitlar)
    monkeypatch.setattr(sinama, "SAGLIK_ADRESI", sunucu.adres)
    monkeypatch.setattr(sinama.time, "sleep", lambda _sn: None)
    try:
        if beklenen:
            assert sinama._model_bekle(_CalisanSurec())["model"] == beklenen
        else:
            with pytest.raises(sinama.SinamaHatasi, match="model_yuklenemedi"):
                sinama._model_bekle(_CalisanSurec())
    finally:
        sunucu.kapat()

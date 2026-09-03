"""Mac uygulaması (.app) üretimi — üretim tarifini ve paketlenmiş modu korur.

NEDEN BU TESTLER VAR — paketlenmiş programın hataları, geliştirme kurulumunda
GÖRÜNMEZ. Uygulama açılıp hemen çöktüğünde ekranda tek satır bile olmayabilir
(bir .app'in çıktısı hiçbir yere gitmez). Bu yüzden üretim tarifinin unutulmaya
en açık dört parçası ve paneldeki paketlenmiş mod davranışı burada kilitlenir.

Testler .app üretmez (üretim dakikalar sürer ve yüzlerce MB yer kaplar); tarif
dosyasını, başlatıcı kodunu ve depo ayarlarını sınarlar.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
from pathlib import Path

import pytest
from conftest import git_gerekli

KOK = Path(__file__).resolve().parents[1]
SPEC = KOK / "paketleme" / "NextGenDetector-mac.spec"
# Mac ve Windows tariflerinin ortak bölümü burada durur (bkz. test_paketleme.py).
ORTAK = KOK / "paketleme" / "paketleme_ortak.py"
BASLATICI = KOK / "masaustu" / "dalsan_launcher.py"
URETICI = KOK / "paketleme" / "Mac-Uygulama-Uret.command"


@pytest.fixture(scope="module")
def spec_metni() -> str:
    """Mac üretim tarifinin TAMAMI: ortak bölüm + macOS'a özel bölüm.

    Tarif iki dosyaya bölündü (kopyala-yapıştır iki tarifi zamanla ayrıştırır),
    ama buradaki soruların cevabı değişmedi: "pakete şu konuyor mu?" Bu yüzden
    testler ikisini birlikte okur.
    """
    return ORTAK.read_text(encoding="utf-8") + "\n" + SPEC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def baslatici_metni() -> str:
    return BASLATICI.read_text(encoding="utf-8")


# --------------------------------------------------------------- üretim tarifi


def test_sablon_stil_ve_sema_pakete_konuyor(spec_metni):
    """Bunlar kod değil VERİ dosyalarıdır: PyInstaller kendiliğinden toplamaz.

    Unutulursa uygulama açılır açılmaz "şablon bulunamadı" ile çöker — üstelik
    hata hiçbir ekrana düşmez.
    """
    for klasor in (
        "backend/app/web/templates",
        "backend/app/web/static",
        "backend/sema",
    ):
        assert klasor in spec_metni, f"veri klasörü pakete konmuyor: {klasor}"


def test_ornek_ayar_dosyasi_pakete_konuyor(spec_metni):
    """Paketlenmiş programda .env bu örnekten üretilir (app/ayarlar.py)."""
    assert ".env.example" in spec_metni


def test_uvicorunun_metinle_yukledigi_moduller_listeleniyor(spec_metni):
    """`http="auto"` gibi ayarlar modül adını METİN olarak taşır; PyInstaller
    tarayarak bulamaz ve pakete koymaz — sunucu o zaman hiç açılmaz."""
    for modul in (
        "uvicorn.lifespan.on",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
    ):
        assert modul in spec_metni, f"gizli modül eksik: {modul}"


def test_kamera_izni_metni_turkce_ve_yerinde(spec_metni):
    """Bu anahtar yoksa macOS kamera erişimini SORMADAN reddeder."""
    assert "NSCameraUsageDescription" in spec_metni
    assert "Fabrikadaki kameralardan görüntü almak için kullanılır." in spec_metni


def test_supervisionun_zorunlu_bagimliliklari_disarida_birakilmiyor(spec_metni):
    """matplotlib ve scipy "gereksiz" görünür ama supervision onları ÇALIŞMA
    ANINDA yükler (ByteTrack → scipy, supervision.draw.color → matplotlib).
    Boyut küçültmek için çıkarılırlarsa tespit ilk karede çöker."""
    agac = ast.parse(spec_metni)
    disarida = next(
        d.value
        for d in agac.body
        if isinstance(d, ast.Assign) and getattr(d.targets[0], "id", "") == "disarida"
    )
    adlar = {e.value for e in disarida.elts}
    for zorunlu in ("matplotlib", "scipy", "numpy", "cv2", "onnxruntime", "supervision"):
        assert zorunlu not in adlar, f"{zorunlu} çıkarılamaz — çalışma anında gerekiyor"


def test_openssl_cakismasi_sessizce_gecilemiyor(spec_metni):
    """opencv'nin eski OpenSSL'i Python'un `_ssl` modülünü kırıyordu; düzeltme
    uygulanamazsa ÜRETİM DURMALI, yoksa hata ancak uygulama açılmayınca
    fark edilir."""
    assert "_openssl_cakismasini_gider" in spec_metni
    assert "raise SystemExit" in spec_metni


def test_ikon_dosyasi_var_ve_gecerli():
    ikon = KOK / "paketleme" / "NextGenDetector.icns"
    assert ikon.is_file(), "uygulama simgesi yok"
    assert ikon.read_bytes()[:4] == b"icns", "bu bir .icns dosyası değil"


# ------------------------------------------------------------ üretim komutu


@git_gerekli
def test_uretim_komutu_calistirilabilir_ve_lf():
    """Çalıştırma izni yoksa Finder dosyayı hiç açmaz; CRLF ise Mac 'cd: $\\r'
    hatası verir."""
    import subprocess

    cikti = subprocess.run(
        ["git", "ls-files", "-s", "paketleme/Mac-Uygulama-Uret.command"],
        cwd=KOK,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert cikti.startswith("100755"), f"çalıştırma izni yok: {cikti.strip()}"
    assert b"\r\n" not in URETICI.read_bytes()


def test_uretim_komutu_gecici_klasorleri_temizliyor():
    """build/ yüzlerce MB'dir ve işe yaramaz; dist/'teki ikiz klasör de öyle."""
    metin = URETICI.read_text(encoding="utf-8")
    assert 'rm -rf "$DEPO/build"' in metin


def test_paketleme_araci_calisma_bagimliligina_karismiyor():
    """PyInstaller bir DERLEME aracıdır. backend/requirements.txt'e girerse
    fabrika sunucusundaki her kurulum onu da indirir."""
    calisma = (KOK / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "pyinstaller" not in calisma.lower()
    uretim = (KOK / "paketleme" / "requirements-paketleme.txt").read_text(encoding="utf-8")
    assert "pyinstaller" in uretim.lower()


@git_gerekli
def test_uretilen_uygulama_depoya_girmiyor_tarif_giriyor():
    import subprocess

    def yoksayiliyor(yol: str) -> bool:
        return (
            subprocess.run(
                ["git", "check-ignore", "-q", yol], cwd=KOK, capture_output=True
            ).returncode
            == 0
        )

    assert yoksayiliyor("dist/NextGen Detector.app"), "üretilen uygulama depoya girmemeli"
    assert yoksayiliyor("build/x.o"), "geçici derleme klasörü depoya girmemeli"
    assert not yoksayiliyor("paketleme/NextGenDetector-mac.spec"), (
        "üretim tarifi KAYNAK dosyadır, depoda durmalı"
    )


# ------------------------------------------------------- paketlenmiş modda panel


def _baslatici_yukle(monkeypatch, meipass: Path):
    """Başlatıcıyı PAKETLENMİŞ programmış gibi yükler.

    PyInstaller'ın yaptığının aynısı: `sys.frozen` ve `sys._MEIPASS` kurulur.
    Gerçek .app üretmeye gerek yok — panel kararını tam olarak bu ikisine
    bakarak veriyor.
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    tanim = importlib.util.spec_from_file_location("paket_baslatici", BASLATICI)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


def test_paketlenmis_panelde_kurulum_adimi_yok(monkeypatch, tmp_path):
    """Python ortamı ve paketler uygulamanın içinde gelir: "İlk Kurulumu Yap"
    diye bir iş kalmaz, kullanıcı olmayan bir adımı aramamalı."""
    modul = _baslatici_yukle(monkeypatch, tmp_path)
    assert modul.PAKETLENMIS is True
    assert modul.paketler_hazir() is True
    assert modul.kod_hazir() is True


def test_paketlenmis_panel_yazilabilir_klasoru_backendle_ayni_yerden_alir(monkeypatch, tmp_path):
    """Panel ile sunucu ayrı klasörlere bakarsa kullanıcı kayıtlarını bulamaz.
    Karar tek yerde, app/kaynaklar.py'de verilir."""
    from app import kaynaklar

    modul = _baslatici_yukle(monkeypatch, tmp_path)
    assert modul.ROOT == kaynaklar.veri_konumu().kok
    assert modul.ROOT != KOK, "paketlenmiş programda depo kökü kullanılmamalı"


def test_gelistirme_kurulumunun_veri_yolu_degismedi():
    """Paketleme çalışması BUGÜNKÜ kurulumu bozmamalı."""
    sys.modules.pop("normal_baslatici", None)
    tanim = importlib.util.spec_from_file_location("normal_baslatici", BASLATICI)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    assert modul.PAKETLENMIS is False
    assert modul.ROOT == KOK


def test_paketlenmis_modda_sunucu_ALT_SUREC_olarak_baslatilmiyor(baslatici_metni):
    """EN TEHLİKELİ TUZAK. Paketlenmiş programda `sys.executable` artık python
    değil, UYGULAMANIN KENDİSİDİR; onu alt süreç olarak çalıştırmak ikinci bir
    Kontrol Paneli açar ve sonsuz döngü olur.

    Bu yüzden paketlenmiş dalda süreç başlatan yol HİÇ çağrılmamalı.
    """
    agac = ast.parse(baslatici_metni)
    baslat = next(
        d for d in ast.walk(agac) if isinstance(d, ast.FunctionDef) and d.name == "sistemi_baslat"
    )
    dallar = [
        d
        for d in ast.walk(baslat)
        if isinstance(d, ast.If) and getattr(d.test, "id", "") == "PAKETLENMIS"
    ]
    assert len(dallar) == 1, "paketlenmiş/geliştirme ayrımı tek yerde olmalı"
    dal = dallar[0]

    def cagrilan_adlar(govde) -> set[str]:
        return {
            d.func.id
            for g in govde
            for d in ast.walk(g)
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
        }

    paketli = cagrilan_adlar(dal.body)
    gelistirme = cagrilan_adlar(dal.orelse)
    assert "_ic_surecte_baslat" in paketli, "paketlenmiş modda sunucu aynı süreçte kalkmalı"
    assert "alt_surecte_baslat" not in paketli, "paketlenmiş modda alt süreç açılamaz"
    assert "alt_surecte_baslat" in gelistirme, "geliştirme kurulumu alt süreci kullanır"


def test_alt_surec_yolu_venvin_pythonunu_kullanir(baslatici_metni):
    """Yukarıdaki testin dayanağı: alt süreç yolu `sys.executable`'ı DEĞİL,
    .venv içindeki python'u çalıştırır — paketlenmiş programda o dosya yoktur."""
    agac = ast.parse(baslatici_metni)
    alt = next(
        d
        for d in ast.walk(agac)
        if isinstance(d, ast.FunctionDef) and d.name == "alt_surecte_baslat"
    )
    govde = ast.unparse(alt)
    assert "venv_python()" in govde
    assert "sys.executable" not in govde


def test_panel_gunlugu_ekran_biciminden_ayrinti_sizdirmiyor(test_ayarlari):
    """Paketlenmiş programda sunucunun satırları panele DOĞRUDAN log
    sisteminden akar. O yolda ekran biçimlendiricisi kullanılmazsa dosya
    yolları ve yığın izleri kullanıcının penceresine düşerdi (CLAUDE.md §8).
    """
    from app import loglama

    sys.modules.pop("normal_baslatici", None)
    tanim = importlib.util.spec_from_file_location("normal_baslatici", BASLATICI)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)

    loglama.kur(test_ayarlari)
    kok = logging.getLogger("dalsan")
    onceki = list(kok.handlers)
    toplanan: list[str] = []
    try:
        modul._gunlugu_panele_bagla(toplanan.append)
        loglama.log_al("tespit").info("Model yüklendi", extra={"ayrinti": "/gizli/yol/model.onnx"})
    finally:
        kok.handlers = onceki

    assert toplanan, "panel akışı hiç satır almadı"
    satir = toplanan[-1]
    assert "Model yüklendi" in satir
    assert "/gizli/yol/model.onnx" not in satir, "teknik ayrıntı ekrana sızdı"

    # Aynı ayrıntı DOSYADA durmalı — destek akışı ona dayanıyor.
    assert "/gizli/yol/model.onnx" in test_ayarlari.log_dosyasi.read_text(encoding="utf-8")


def test_panel_akisi_iki_kez_eklenmiyor(test_ayarlari):
    """Durdur/Başlat döngüsünde her seferinde bir akış daha eklenirse satırlar
    ikilenir, üçlenir; kullanıcı aynı mesajı defalarca görür."""
    from app import loglama

    sys.modules.pop("normal_baslatici", None)
    tanim = importlib.util.spec_from_file_location("normal_baslatici", BASLATICI)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)

    loglama.kur(test_ayarlari)
    kok = logging.getLogger("dalsan")
    onceki = list(kok.handlers)
    toplanan: list[str] = []
    try:
        modul._gunlugu_panele_bagla(toplanan.append)
        modul._gunlugu_panele_bagla(toplanan.append)
        loglama.log_al("sistem").info("Tek satır")
    finally:
        kok.handlers = onceki

    assert len(toplanan) == 1, f"satır ikilendi: {toplanan}"


def test_paketlenmis_baslatma_ayarlari_HER_SEFERINDE_yeniden_okur(baslatici_metni):
    """Paketlenmiş programda Durdur → Sistemi Başlat aynı süreçte olur.

    Hazır `app.main.app` nesnesi kullanılırsa ayar dosyası bir daha okunmaz:
    Ayarlar sayfasında eşiği değiştirip yeniden başlatan kullanıcı, hiçbir şey
    değişmediğini görür ve sebebini anlayamaz. Bu yüzden uygulama her
    başlatmada fabrikadan yeniden kurulmalı.
    """
    agac = ast.parse(baslatici_metni)
    baslat = next(
        d
        for d in ast.walk(agac)
        if isinstance(d, ast.FunctionDef) and d.name == "_ic_surecte_baslat"
    )
    govde = ast.unparse(baslat)
    assert "uygulamayi_kur()" in govde, "uygulama her başlatmada yeniden kurulmalı"
    assert "import app as" not in govde, "hazır uygulama nesnesi kullanılamaz"


def test_uygulama_fabrikasi_main_icinde_ve_tek_kaynak():
    """Fabrika main.py'de kalmalı: ayar okuma + log kurulumu + uygulama kurulumu
    sırası TEK yerde tarif edilsin (CLAUDE.md §4 — main.py tek giriş noktası)."""
    metin = (KOK / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    agac = ast.parse(metin)
    fabrikalar = [
        d for d in agac.body if isinstance(d, ast.FunctionDef) and d.name == "uygulamayi_kur"
    ]
    assert fabrikalar, "app.main.uygulamayi_kur bulunamadı"
    atamalar = [
        ast.unparse(d)
        for d in agac.body
        if isinstance(d, ast.Assign) and getattr(d.targets[0], "id", "") == "app"
    ]
    assert atamalar == ["app = uygulamayi_kur()"], (
        f"uvicorn'un beklediği modül düzeyi `app` nesnesi fabrikadan gelmeli: {atamalar}"
    )

"""Windows uygulaması (.exe) üretimi ve iki tarifin ORTAK bölümü.

NEDEN BU TESTLER VAR — .exe bu bilgisayarda üretilemez. PyInstaller çapraz
derleme yapmaz: Windows uygulaması ancak bir Windows bilgisayarda üretilir.
Yani üretim tarifi, kullanıcının bilgisayarına gidene kadar HİÇ denenmemiş
olacak; oradaki ilk deneme de yazılım bilmeyen bir kişi tarafından, bir kez
yapılacak. Tarifte bir yazım hatası varsa bunu orada keşfetmek pahalıdır.

Bu yüzden burada üretimin denenebilen HER parçası deneniyor:

* `.spec` dosyaları sahte bir PyInstaller ile GERÇEKTEN çalıştırılıyor —
  yazım hatası, eksik değişken, yanlış yol anında görülüyor.
* Açılış hatası kancasının davranışı (kayıp çıkış akışı, hata dosyası, uyarı
  penceresi metni) doğrudan çağrılarak sınanıyor.
* Üretim betiğinin Windows'a özgü tuzakları (Mağaza takma adı, satır sonu,
  konsol kodlaması, pencerenin kapanmaması) metninde aranıyor.

Hiçbiri .exe üretmez; üretim dakikalar sürer ve yüzlerce MB yer kaplar.
"""

from __future__ import annotations

import ast
import importlib.util
import struct
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

KOK = Path(__file__).resolve().parents[1]
PAKETLEME = KOK / "paketleme"
ORTAK = PAKETLEME / "paketleme_ortak.py"
MAC_SPEC = PAKETLEME / "NextGenDetector-mac.spec"
WIN_SPEC = PAKETLEME / "NextGenDetector-windows.spec"
KANCA = PAKETLEME / "windows_acilis_kancasi.py"
BAT = PAKETLEME / "Windows-Uygulama-Uret.bat"
IKON = PAKETLEME / "NextGenDetector.ico"
BELGE = KOK / "docs" / "13-UYGULAMA-PAKETLEME.md"


# ---------------------------------------------------------------- yardımcılar


class _SahtePyInstaller:
    """`.spec` dosyasını PyInstaller olmadan çalıştırmak için sahte fabrika.

    PyInstaller bir `.spec` dosyasını Python olarak ÇALIŞTIRIR ve içine
    `Analysis`, `EXE`, `COLLECT`… adlarını enjekte eder. Burada aynısı
    yapılıyor: tarif gerçekten çalışıyor, ama tek satır kod paketlenmiyor.
    """

    def __init__(self) -> None:
        self.cagrilar: dict[str, list[tuple[tuple, dict]]] = {}

    def fabrika(self, ad: str):
        def _cagir(*konum, **anahtar):
            self.cagrilar.setdefault(ad, []).append((konum, anahtar))
            nesne = ModuleType("sahte_analiz")
            nesne.pure, nesne.scripts, nesne.binaries = [], [], []
            nesne.datas = []
            return nesne

        return _cagir

    def kwargs(self, ad: str) -> dict:
        return self.cagrilar[ad][0][1]

    def args(self, ad: str) -> tuple:
        return self.cagrilar[ad][0][0]


def _tarifi_calistir(spec: Path) -> _SahtePyInstaller:
    sahte = _SahtePyInstaller()
    ortam = {
        "__file__": str(spec),
        "SPECPATH": str(spec.parent),
        "DISTPATH": str(KOK / "dist"),
        "Analysis": sahte.fabrika("Analysis"),
        "PYZ": sahte.fabrika("PYZ"),
        "EXE": sahte.fabrika("EXE"),
        "COLLECT": sahte.fabrika("COLLECT"),
        "BUNDLE": sahte.fabrika("BUNDLE"),
    }
    exec(compile(spec.read_text(encoding="utf-8"), str(spec), "exec"), ortam)
    return sahte


@pytest.fixture(scope="module")
def windows_tarifi() -> _SahtePyInstaller:
    return _tarifi_calistir(WIN_SPEC)


@pytest.fixture(scope="module")
def kanca() -> ModuleType:
    """Açılış kancasını modül olarak yükler.

    Yükleme YAN ETKİSİZ olmalı: kanca yalnızca paketlenmiş programda kurulur
    (dosyanın sonundaki `sys.frozen` kontrolü). Aksi hâlde bu satır pytest'in
    kendi hata yakalayıcısını değiştirirdi.
    """
    tanim = importlib.util.spec_from_file_location("windows_acilis_kancasi", KANCA)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def bat_metni() -> str:
    # ASCII dışı bayt varsa okuma ÇÖKMESİN: onun kendi testi var
    # (test_betik_sadece_ascii) ve tek bir yerden bildirilsin.
    return BAT.read_bytes().decode("ascii", errors="replace")


def _git(*komut: str) -> subprocess.CompletedProcess:
    return subprocess.run(komut, cwd=KOK, capture_output=True, text=True)


# ------------------------------------------------- tarifler gerçekten çalışıyor


def test_windows_tarifi_calistirilabiliyor(windows_tarifi):
    """En temel kontrol: tarif hatasız çalışıyor mu?

    Yazım hatası, tanımsız değişken ya da yanlış yol burada görülür — üretim
    komutunu Windows'ta ilk kez çalıştıran kişide değil.
    """
    assert "Analysis" in windows_tarifi.cagrilar
    assert "EXE" in windows_tarifi.cagrilar
    assert "COLLECT" in windows_tarifi.cagrilar


def test_windows_tarifi_ayni_kontrol_panelini_paketliyor(windows_tarifi):
    """İki platform da AYNI programı paketler; ayrı bir Windows sürümü yok."""
    giris = windows_tarifi.args("Analysis")[0]
    assert [Path(y).name for y in giris] == ["dalsan_launcher.py"]


def test_windows_paketinde_sablon_stil_sema_ve_ornek_ayar_var(windows_tarifi):
    """Bunlar kod değil VERİ dosyalarıdır; unutulursa uygulama açılır açılmaz
    "şablon bulunamadı" ile çöker ve hata hiçbir ekrana düşmez."""
    hedefler = [hedef for _, hedef in windows_tarifi.kwargs("Analysis")["datas"]]
    for beklenen in ("backend/app/web/templates", "backend/app/web/static", "backend/sema"):
        assert beklenen in hedefler
    kaynaklar = [Path(k).name for k, _ in windows_tarifi.kwargs("Analysis")["datas"]]
    assert ".env.example" in kaynaklar


def test_windows_paketinde_uvicorunun_gizli_modulleri_var(windows_tarifi):
    """`http="auto"` gibi ayarlar modül adını METİN olarak taşır; PyInstaller
    tarayarak bulamaz ve pakete koymaz — sunucu o zaman hiç açılmaz."""
    gizli = windows_tarifi.kwargs("Analysis")["hiddenimports"]
    for modul in (
        "uvicorn.lifespan.on",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
    ):
        assert modul in gizli, f"gizli modül eksik: {modul}"
    assert any(m.startswith("app.") for m in gizli), "sistemin kendi modülleri toplanmamış"


def test_windows_paketinden_goruntu_isleme_cikarilmiyor(windows_tarifi):
    """matplotlib ve scipy "gereksiz" görünür ama supervision onları ÇALIŞMA
    ANINDA yükler; çıkarılırlarsa tespit ilk karede çöker."""
    disarida = windows_tarifi.kwargs("Analysis")["excludes"]
    for zorunlu in ("matplotlib", "scipy", "numpy", "cv2", "onnxruntime", "supervision"):
        assert zorunlu not in disarida, f"{zorunlu} çıkarılamaz — çalışma anında gerekiyor"


# ------------------------------------------------------- ortak bölüm tek yerde


def test_iki_tarif_de_ortak_bolumu_kullaniyor():
    """Kopyala-yapıştır iki tarifi zamanla ayrıştırır: birine yeni bir şablon
    klasörü eklenir, diğerine unutulur ve hata YALNIZCA o platformda çıkar."""
    for spec in (MAC_SPEC, WIN_SPEC):
        assert "import paketleme_ortak" in spec.read_text(encoding="utf-8"), (
            f"{spec.name} ortak bölümü kullanmıyor"
        )


def test_pakete_ne_konacagi_iki_tarifte_TEKRARLANMIYOR():
    """Ortak listelerin tek bir kopyası olmalı — ikinci kopya sessizce eskir."""
    ortak_metin = ORTAK.read_text(encoding="utf-8")
    tarifler = {s.name: s.read_text(encoding="utf-8") for s in (MAC_SPEC, WIN_SPEC)}
    for parca in (
        "backend/app/web/templates",
        "uvicorn.protocols.http.auto",
        "tkinter.scrolledtext",
        "PySide6",
        "dalsan_launcher.py",
    ):
        assert parca in ortak_metin, f"ortak bölümde olması gereken parça yok: {parca}"
        for ad, metin in tarifler.items():
            assert parca not in metin, f"{ad} içinde ortak bölümün kopyası var: {parca}"


def test_ortak_bolum_ve_kanca_python_olarak_ayristirilabiliyor():
    for dosya in (ORTAK, KANCA):
        ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))


def test_iki_tarif_ayni_uygulama_adini_kullaniyor(windows_tarifi):
    """Ad değişirse kullanıcının kayıt klasörü de değişir (app/kaynaklar.py):
    eski kayıtlar "kayboldu" görünür. Ad tek yerden gelmeli."""
    from app.kaynaklar import UYGULAMA_ADI

    assert windows_tarifi.kwargs("COLLECT")["name"] == UYGULAMA_ADI
    assert windows_tarifi.kwargs("EXE")["name"] == UYGULAMA_ADI


# --------------------------------------------------------- Windows'a özgü olan


def _kod_govdesi(dosya: Path) -> str:
    """Dosyanın YAPTIĞI iş — açıklama satırları ve başlık metni dışarıda.

    Tarifler, birbirlerinden neden ayrıldıklarını uzun uzun anlatır; o
    açıklamalarda "`.icns` Windows'ta okunmaz" gibi cümleler geçer. Aranan
    şey metin değil, çalıştırılan koddur.
    """
    agac = ast.parse(dosya.read_text(encoding="utf-8"), filename=str(dosya))
    govde = agac.body
    if govde and isinstance(govde[0], ast.Expr) and isinstance(govde[0].value, ast.Constant):
        govde = govde[1:]  # modül başlığındaki açıklama metni
    return "\n".join(ast.unparse(dugum) for dugum in govde)


def test_windows_tarifinde_macos_ozel_parcalar_yok():
    """BUNDLE, .icns ve `otool` macOS'a özeldir. Kopyalanırlarsa üretim,
    Windows'ta olmayan bir aracı çağırıp anlaşılmaz bir hatayla durur."""
    kod = _kod_govdesi(WIN_SPEC)
    for parca in ("BUNDLE", ".icns", "otool", "NSCameraUsageDescription"):
        assert parca not in kod, f"Windows tarifinde macOS'a özel parça: {parca}"


def test_windows_tarifi_app_kabugu_uretmiyor(windows_tarifi):
    assert "BUNDLE" not in windows_tarifi.cagrilar


def test_windows_simgesi_ico_ve_tarif_onu_kullaniyor(windows_tarifi):
    """Windows `.icns` okumaz; simge `.ico` olmak zorundadır."""
    assert Path(windows_tarifi.kwargs("EXE")["icon"]) == IKON
    assert IKON.is_file(), "Windows uygulama simgesi yok"


def test_ico_dosyasi_gercekten_gecerli():
    """Bozuk bir .ico üretimi en sonda, dakikalar harcandıktan sonra durdurur."""
    ham = IKON.read_bytes()
    rezerv, tur, adet = struct.unpack("<HHH", ham[:6])
    assert (rezerv, tur) == (0, 1), "bu bir .ico dosyası değil"
    assert adet >= 4, "simgede yeterli boyut yok"
    boyutlar = set()
    for sira in range(adet):
        alan = struct.unpack("<BBBBHHII", ham[6 + sira * 16 : 22 + sira * 16])
        genislik, _, _, _, _, _, veri_uzunlugu, ofset = alan
        boyutlar.add(genislik or 256)
        assert ofset + veri_uzunlugu <= len(ham), "simge verisi dosyanın dışını gösteriyor"
    assert {16, 32, 256} <= boyutlar, f"küçük/büyük boyutlar eksik: {sorted(boyutlar)}"


def test_konsol_gizli_ama_hata_gorunur_kaliyor(windows_tarifi):
    """İkisi BİRLİKTE doğru: siyah komut penceresi açılmaz, ama program
    açılırken çökerse kullanıcı sebebini görebilir.

    Konsol gizlenip kanca takılmazsa uygulama "hiç açılmıyor" olur ve ekranda
    tek satır bile bulunmaz — bu, teşhis edilemeyen tek durumdur.
    """
    exe = windows_tarifi.kwargs("EXE")
    assert exe["console"] is False, "siyah komut penceresi açılmamalı"
    assert exe["disable_windowed_traceback"] is False, "son çare uyarı yolu kapatılmamalı"
    kancalar = [Path(y).name for y in windows_tarifi.kwargs("Analysis")["runtime_hooks"]]
    assert KANCA.name in kancalar, "açılış hatası kancası takılmamış"


def test_upx_sikistirmasi_kapali(windows_tarifi):
    """UPX ile sıkıştırılmış dosyaları virüs koruma yazılımları çok daha sık
    "şüpheli" işaretler; kazanılan yer, karantinaya değmez."""
    assert windows_tarifi.kwargs("EXE")["upx"] is False
    assert windows_tarifi.kwargs("COLLECT")["upx"] is False


# ------------------------------------------------- açılış hatası kancası (davranış)


def test_kanca_normal_calistirmada_KURULMUYOR(kanca):
    """Kanca yalnızca paketlenmiş programa aittir. Geliştirme kurulumunda
    kurulursa pytest'in ve Kontrol Paneli'nin kendi hata yolunu ezerdi."""
    assert sys.excepthook is not kanca.hata_yakalayici
    assert 'if getattr(sys, "frozen", False):' in KANCA.read_text(encoding="utf-8")


def test_kayip_cikti_akislari_dosyaya_baglaniyor(kanca, tmp_path, monkeypatch):
    """Pencereli Windows uygulamasında `sys.stdout` ve `sys.stderr` YOKTUR.
    Bağlanmazsa program ekrana yazdığı her satırı sessizce kaybeder."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    yol = kanca.ciktilari_dosyaya_yonlendir(tmp_path)
    akis = sys.stdout
    try:
        assert sys.stdout is not None and sys.stderr is not None
        akis.write("acilis satiri\n")
        akis.flush()
    finally:
        akis.close()

    assert yol is not None
    assert "acilis satiri" in yol.read_text(encoding="utf-8")


def test_akislar_yerindeyse_dokunulmuyor(kanca, tmp_path):
    """Geliştirme kurulumunda çıktı terminale gitmeye devam etmeli."""
    onceki = sys.stdout
    assert kanca.ciktilari_dosyaya_yonlendir(tmp_path) is None
    assert sys.stdout is onceki


def test_ekran_dosyasi_sinirsiz_buyumuyor(kanca, tmp_path):
    """Sunucunun günlük satırları da buraya akar. Sınır olmasaydı 7/24 çalışan
    bir sistemde bu dosya diski doldururdu."""
    hedef = tmp_path / "ekran.log"
    with open(hedef, "w", encoding="utf-8") as dosya:
        akis = kanca.SinirliDosya(dosya, sinir=100)
        assert akis.write("a" * 60) == 60
        assert akis.write("b" * 60) == 60
        assert akis.write("c" * 500) == 500  # sınır aşıldı: yazılmamalı

    metin = hedef.read_text(encoding="utf-8")
    assert "a" * 60 in metin
    assert "ccc" not in metin, "sınırdan sonra da yazmaya devam etmiş"
    assert "sınırına ulaşıldı" in metin, "kullanıcı satırların kesildiğini bilmeli"


def test_hata_ayrintisi_dosyaya_yaziliyor(kanca, tmp_path):
    yol = kanca.hatayi_yaz("Traceback...\nValueError: sahte hata", tmp_path)
    assert yol is not None
    assert yol.name == kanca.HATA_DOSYASI_ADI
    assert "ValueError: sahte hata" in yol.read_text(encoding="utf-8")
    # Kayıtlar veritabanının ve kanıt fotoğraflarının yanında dursun.
    assert yol.parent == tmp_path / "veri" / "loglar"


def test_hata_dosyasi_yazilamiyorsa_program_yine_de_devam_ediyor(kanca, tmp_path):
    """Salt okunur klasör yüzünden çökmek, asıl hatanın üstünü örter."""
    engel = tmp_path / "veri"
    engel.write_text("bu bir dosya, klasör değil", encoding="utf-8")
    assert kanca.hatayi_yaz("herhangi bir hata", tmp_path) is None


def test_hata_penceresi_turkce_ve_dosyanin_yerini_soyluyor(kanca, capsys):
    """Kullanıcı yazılım bilmiyor: ne olduğunu ve neyi göndereceğini anlamalı.

    (Windows dışında ileti penceresi açılamaz; metin ekrana düşer ve test
    onu okur. Windows'ta aynı metin uyarı penceresinde görünür.)
    """
    kanca.pencerede_goster(Path("C:/Users/ali/veri/loglar/acilis-hatasi.log"))
    metin = capsys.readouterr().err
    assert "hata oluştu" in metin
    assert "acilis-hatasi.log" in metin, "kullanıcı dosyayı bulamaz"
    assert "Traceback" not in metin and "Exception" not in metin


def test_hata_penceresi_dosya_yokken_de_bir_sey_soyluyor(kanca, capsys):
    kanca.pencerede_goster(None)
    metin = capsys.readouterr().err
    assert "hata oluştu" in metin
    assert "kaydedilemedi" in metin


def test_kanca_kurulunca_hata_yakalayici_devreye_giriyor(kanca, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    kanca.kur()
    assert sys.excepthook is kanca.hata_yakalayici


def test_coklu_surec_tuzagi_kapatiliyor(kanca):
    """TUZAK: paketlenmiş programda `sys.executable` UYGULAMANIN KENDİSİDİR.
    Bir kütüphane arka planda ikinci bir işlem başlatırsa ekranda ikinci bir
    Kontrol Paneli açılır, o da bir üçüncüsünü açar."""
    govde = ast.unparse(
        next(
            d
            for d in ast.walk(ast.parse(KANCA.read_text(encoding="utf-8")))
            if isinstance(d, ast.FunctionDef) and d.name == "kur"
        )
    )
    assert "_coklu_surec_tuzagini_kapat()" in govde
    kanca._coklu_surec_tuzagini_kapat()  # çağrılabilir olduğu da doğrulansın


# ------------------------------------------------------------- üretim betiği


def test_betik_windows_satir_sonlariyla_yazilmis():
    """LF satır sonlu bir .bat dosyasını Windows komut yorumlayıcısı yanlış
    okur: satırların sonuna görünmez bir karakter takılır ve komutlar
    "bulunamadı" der."""
    ham = BAT.read_bytes()
    assert b"\r\n" in ham
    assert ham.replace(b"\r\n", b"").count(b"\n") == 0, "bazı satırlar LF kalmış"


def test_gitattributes_bat_dosyalarini_crlf_tutuyor():
    """Depodan klonlayan kişi de CRLF almalı — yoksa yukarıdaki hata geri gelir."""
    cikti = _git("git", "check-attr", "eol", "--", "paketleme/Windows-Uygulama-Uret.bat").stdout
    assert cikti.strip().endswith("eol: crlf"), cikti


def test_betik_sadece_ascii():
    """Windows konsolunun kod sayfası (cp857/cp1254) her Türkçe harfi taşımaz.
    Ayrıca betiğin içinde ASCII dışı bayt varsa `chcp 65001` satırı komut
    yorumlayıcısının okumasını bozar."""
    ham = BAT.read_bytes()
    disi = [(sira, bayt) for sira, bayt in enumerate(ham) if bayt > 127]
    assert not disi, f"ASCII dışı bayt var: {disi[:5]}"


def test_betik_magaza_takma_adina_kanmiyor(bat_metni):
    """Windows 10/11'de Python kurulu OLMASA BİLE PATH'te sıfır baytlık bir
    `python.exe` durur; çalıştırılınca Mağaza penceresi açılır ve hiçbir şey
    üretilmez. Aday, gerçekten Python olduğu doğrulanmadan kullanılamaz."""
    assert 'py -3 -c "import sys"' in bat_metni, "önce py.exe launcher denenmeli"
    assert 'python -c "import sys"' in bat_metni, "aday doğrulanmadan kullanılmış"
    assert "Store" in bat_metni or "Magaza" in bat_metni, "kullanıcı uyarılmamış"


def test_betik_python_surumunu_dogruluyor(bat_metni):
    """onnxruntime 3.11+ ister; eski sürümde üretim, sebebi hiç anlaşılmayan
    bir pip hatasıyla kırılır."""
    assert "sys.version_info >= (3, 11)" in bat_metni


def test_betik_derin_klasoru_uyariyor(bat_metni):
    """Windows'ta yol 260 karakteri geçemez; derin bir klasörde üretim
    "dosya bulunamadı" gibi anlaşılmaz bir hatayla kırılır."""
    assert "260" in bat_metni, "sınır belgelenmemiş"
    assert "UZUNLUK" in bat_metni, "yol uzunluğu hiç ölçülmüyor"
    assert "if %UZUNLUK% GTR 80" in bat_metni, "ölçüm sonucuna göre uyarı yok"


def test_betik_defender_karantinasini_fark_ediyor(bat_metni):
    """Üretim "başarılı" bitip .exe ortada olmadığında sebep neredeyse her
    zaman budur. Kullanıcı bunu bilmezse aynı işi tekrar tekrar dener."""
    assert "urun_yok" in bat_metni
    assert "karantina" in bat_metni.lower()
    assert "Koruma" in bat_metni and "gecmisi" in bat_metni, "izlenecek adım yazılmamış"


def test_betik_smartscreen_uyarisini_anlatiyor(bat_metni):
    """Uygulama imzasız: ilk açılışta Windows "bilinmeyen yayinci" der ve
    kullanıcı, uygulamanın bozuk olduğunu sanır."""
    assert "Daha fazla bilgi" in bat_metni
    assert "Yine de calistir" in bat_metni


def test_betik_konsol_kodlamasini_ayarliyor(bat_metni):
    """Üretim çıktısındaki Türkçe harfler bozulmasın diye konsol ve Python
    aynı kodlamaya getirilir."""
    assert "chcp 65001" in bat_metni
    assert "PYTHONIOENCODING=utf-8" in bat_metni


def test_betik_hata_cikislarinda_pencereyi_kapatmiyor(bat_metni):
    """Pencere kapanırsa kullanıcı hatayı okuyamaz ve bize aktaramaz.
    Her hata çıkışı `:son_hata`ya gitmeli; orada `pause` var."""
    satirlar = [s.strip() for s in bat_metni.splitlines()]
    etiketler = [s for s in satirlar if s.startswith(":") and not s.startswith("::")]
    # Akış etiketleri (döngü, başarı yolu) dışındaki HER etiket bir hata
    # çıkışıdır. Liste böyle kurulu ki sonradan eklenen bir çıkış da denetlensin.
    akis = {":yol_say", ":yol_sayildi", ":python_bulundu", ":son", ":son_hata"}
    hata_etiketleri = [e for e in etiketler if e not in akis]
    assert len(hata_etiketleri) >= 6, f"hata çıkışları eksik: {etiketler}"

    for etiket in hata_etiketleri:
        basla = satirlar.index(etiket)
        blok = []
        for satir in satirlar[basla + 1 :]:
            if satir.startswith(":") and not satir.startswith("::"):
                break
            blok.append(satir)
        assert "goto :son_hata" in blok, f"{etiket} bloğu hata çıkışına gitmiyor"

    son_hata = satirlar[satirlar.index(":son_hata") :]
    assert "pause" in son_hata, "hata çıkışında pencere kapanıyor"
    assert "pause" in satirlar[satirlar.index(":son") :], "başarı çıkışında da beklenmeli"


def test_betik_bozuk_python_ortamini_fark_ediyor(bat_metni):
    """Bilgisayardaki Python güncellenince .venv içindeki python çalışmaz hale
    gelir ama DOSYA yerinde durur. Bakılmazsa pip adımı "internet yok" gibi,
    sebebi hiç ilgisiz bir hatayla kırılır ve kullanıcı boşuna uğraşır."""
    assert '"%VPY%" -c "pass"' in bat_metni, "ortam çalışıyor mu diye bakılmıyor"
    assert ":ortam_bozuk" in bat_metni
    assert '".venv" klasorunu SILIN' in bat_metni, "kullanıcıya çözüm söylenmemiş"


def test_betik_dogru_tarifi_calistiriyor_ve_gecici_klasoru_siliyor(bat_metni):
    """build/ yüzlerce MB'dir ve işe yaramaz."""
    assert "NextGenDetector-windows.spec" in bat_metni
    assert "NextGenDetector-mac.spec" not in bat_metni
    assert "rmdir /s /q" in bat_metni


def test_betik_paketleme_aracini_kuruyor(bat_metni):
    assert "requirements-paketleme.txt" in bat_metni
    assert "backend\\requirements.txt" in bat_metni


# --------------------------------------------------------------- depo ayarları


def test_uretilen_uygulama_depoya_girmiyor_tarif_ve_simge_giriyor():
    def yoksayiliyor(yol: str) -> bool:
        return _git("git", "check-ignore", "-q", yol).returncode == 0

    assert yoksayiliyor("dist/NextGen Detector/NextGen Detector.exe")
    assert yoksayiliyor("build/x.o")
    for kaynak in (
        "paketleme/NextGenDetector-windows.spec",
        "paketleme/paketleme_ortak.py",
        "paketleme/windows_acilis_kancasi.py",
        "paketleme/Windows-Uygulama-Uret.bat",
        "paketleme/NextGenDetector.ico",
    ):
        assert not yoksayiliyor(kaynak), f"{kaynak} KAYNAK dosyadır, depoda durmalı"


def test_gitattributes_simgeleri_ikili_sayiyor():
    """Simge dosyasına satır sonu dönüşümü uygulanırsa içi bozulur ve üretim,
    "geçersiz simge" diye durur."""
    for uzanti in ("paketleme/NextGenDetector.ico", "paketleme/NextGenDetector.icns"):
        cikti = _git("git", "check-attr", "text", "--", uzanti).stdout
        assert cikti.strip().endswith("text: unset"), cikti


def test_paketleme_araci_calisma_bagimliligina_karismiyor():
    """PyInstaller bir DERLEME aracıdır; backend/requirements.txt'e girerse
    fabrika sunucusundaki her kurulum onu da indirir."""
    assert (
        "pyinstaller"
        not in (KOK / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()
    )


# -------------------------------------------------------------------- belge


def test_belge_yazildi_ve_dokuman_haritasinda():
    assert BELGE.is_file(), "docs/13-UYGULAMA-PAKETLEME.md yok"
    harita = (KOK / "CLAUDE.md").read_text(encoding="utf-8")
    assert "13-UYGULAMA-PAKETLEME.md" in harita, "CLAUDE.md §10 haritasına eklenmemiş"


def test_belge_kullanicinin_soracagi_her_seyi_kapsiyor():
    """Kullanıcı yazılım bilmiyor: belge, tek başına yeterli olmalı."""
    metin = BELGE.read_text(encoding="utf-8")
    for konu in (
        "Mac-Uygulama-Uret.command",
        "Windows-Uygulama-Uret.bat",
        "Application Support",
        "LOCALAPPDATA",
        "SmartScreen",
        "Defender",
        "acilis-hatasi.log",
        "Güncelleme",
    ):
        assert konu in metin, f"belgede eksik konu: {konu}"

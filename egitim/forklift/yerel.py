"""Forklift modelini fabrikanın kendi verisiyle KAPALI bir bilgisayarda eğitir: tek komut.

Operatör, 24.09.2026: "gidip fabrikadan daha çok görüntü çekip mi yükleyeyim ve
sadece yüklesem yeter mi ekstra kod vs. bir şey yapmam lazım mı?" Kod yazmak
gerekmez. Programın Forklift sayfasından inen veri paketi bu betiğe verilir,
gerisini betik yapar (Windows'ta Egit-Windows.bat onu çağırır):

1. Ortam: Python sürümü, boş disk, bellek; Windows'ta çalışma klasörünün yolu
   ASCII olmalı (OpenCV, Türkçe karakterli yolu Windows'ta açamaz).
2. Fabrika paketi denetlenip açılır (veri.py saha_paketini_ac). Test günü yoksa
   burada durur: kabul ölçümü etiketli saha test günüdür (docs/17 §14).
3. Küçük kaynaklar, bir kez ve SHA-256 ya da içerik özetiyle denetlenerek:
   YOLOX kaynak kodu, resmi ağırlık (.pth) ve ONNX, deneme videosu, araç seti.
4. Ön deneme: fabrikanın 64 karesiyle 4 devir, dışa aktarım, denetim ve 10
   görüntüde ölçüm. Ortam sorunu bir gün sonra değil, birkaç dakikada görünür.
5. LOCO (~770 MB, bir kez) indirilip hazırlanır ve fabrika verisiyle birleşir
   (veri.py hazirla, birlestir).
6. Eğitim (egit.py). Kesilirse (bilgisayar kapandı, pencere kapandı) aynı komut
   kaldığı devirden sürdürür.
7. Üç aday, kişi önceliği k = 0, 1, 2 (model.py disa-aktar ve denetle).
8. Ölçüm (degerlendir.py): fabrikanın test günleri, deneme videosu, araç seti.
   Kapılar egitim/forklift/esikler.json'dur ve burada DEĞİŞMEZ (docs/17 §12.3-8:
   aday ancak hepsini geçerse seçilebilir olur).
9. Sonuç: CALISMA/SONUC.txt (kısa, Türkçe). Geçen aday CALISMA/KURULACAK/'a
   konur ve programın Forklift sayfasında "Modeli kur" ile yüklenir.

Fabrika kareleri kişisel veridir (KVKK): yalnız bu bilgisayarda işlenir, hiçbir
yere yüklenmez; betik yalnız yukarıdaki kaynakları İNDİRİR. Kareler GitHub'daki
eğitim hattına hiç girmez (CLAUDE.md, forklift eğitimi istisnası).

    python egitim/forklift/yerel.py --saha dalsan-forklift-veri-seti-2026-10-10.zip
        --calisma C:/NextGen-Forklift [--boy tiny] [--kip v3] [--devir N]
        [--saha-tekrar 3] [--is-parcacigi N] [--oncelik dusuk|normal]
        [--loco-veri HAZIR_LOCO] [--duman]

--devir verilmezse istek.json'daki (GitHub'daki son tam eğitimin) devir sayısı.
--loco-veri: daha önce `veri.py hazirla` ile hazırlanmış LOCO (indirme atlanır).
--duman: her adım en küçük boyda koşar (LOCO'da alt küme başına 20 görüntü,
64 eğitim görüntüsü, 4 devir, ölçümde 10 görüntü, araç setinden 10 görüntü);
yalnız kurulumu sınar, aday kurulmaz (KURULACAK boş kalır).

Çıkış kodları: 0 bitti (aday geçti ya da kaldı; SONUC.txt söyler); 1 ağ hatası
ya da bir adım yarıda kaldı (yeniden çalıştırın, kaldığı yerden sürer); 2 girdi
ya da ortam hatası (iletideki adımı yapın).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import ortak
import veri

BURASI = Path(__file__).resolve().parent
KOK = BURASI.parents[1]
ESIKLER = BURASI / "esikler.json"
ISTEK = BURASI / "istek.json"
ARAC_SETI_LISTESI = BURASI / "arac_seti.sha256"
MODEL_OZETLERI = KOK / "models" / "SHA256SUMS"

KISI_ONCELIKLERI = (0, 1, 2)
# Önerilen aday: geçenler arasında bu sırayla ilki. k = 1, resmi modelin 0,5 ve
# üstü güvenle bulduğu hiçbir kişiyi kaybettirmez (docs/17 §12.3-2); k = 2 daha
# geniş korur; k = 0'da bu güvence yoktur.
ONERI_SIRASI = (1, 2, 0)
# Ön deneme ve duman: 64 görüntü, 4 devir. Neden 4: egit.py'de mozaiksiz son
# devir sayısı en az 2'dir; YOLOX mozaiği ancak 3. devrin başında kapatır, daha
# az devirde kapanış yolu hiç sınanmaz (forklift-egit.yml'deki duman gibi).
KUCUK_GORUNTU = 64
KUCUK_DEVIR = 4
KUCUK_OLCUM = 10
KUCUK_DENETIM = 5
DUMAN_LOCO_SINIRI = 20
DUMAN_ARAC_SETI = 10
DENETIM_GORUNTUSU = 20
# Süre bütçesi yok: eğitim bitene dek sürer (egit.py'nin bütçesi bacaklar içindi).
EGITIM_SURESI_SN = 60 * 24 * 3600.0
# Boş disk: LOCO arşivi (0,77 GB) ve hazırlığı, ağırlıklar, ara kayıtlar, adaylar.
GEREKEN_DISK_GB = 6.0
GEREKEN_DISK_GB_LOCO_HAZIR = 2.0
ONERILEN_BELLEK_GB = 8.0
ESZAMANLI_INDIRME = 8
KILIT = "KILIT"
TAMAM = "TAMAM"
SONUC = "SONUC.txt"
KURULACAK = "KURULACAK"
GUNLUK = "gunluk.txt"
# Eğitim ortamında bulunması gereken modüller (gereksinimler-yerel.txt). dotenv:
# ölçüm betiği ürünün tespit motorunu (backend/app) açar, o da ayar okur.
GEREKEN_MODULLER = (
    "torch",
    "torchvision",
    "cv2",
    "numpy",
    "pycocotools",
    "onnx",
    "onnxruntime",
    "thop",
    "loguru",
    "psutil",
    "tabulate",
    "tqdm",
    "tensorboard",
    "dotenv",
)
YOLOX_MODULLERI = ("yolox.core", "yolox.data", "yolox.exp", "yolox.utils", "yolox.models")

# SONUC.txt'de kapıların adları (esikler.json'un metrikleri; test denetler)
METRIK_ADLARI = {
    "insan_kaybi": "Kaybolan insan (resmi modelin bulduğu)",
    "arac_kaybi": "Kaybolan araç (resmi modelin bulduğu)",
    "vg_r_artisi": "Forkliftlerin araç olarak bulunmasındaki artış",
    "fk_r": "Forklift bulma oranı",
    "fk_fp_goruntu_basi": "Forkliftsiz karede yanlış forklift (kare başına)",
    "pt_fk": "Transpaletin forklift sanılması",
    "fk_kesinlik": "Forklift kesinliği (doğru tespit oranı)",
    "arac_seti_tr_fk": "Tırın forklift sanılması (araç seti)",
    "video_insan_kaybi": "Videoda kaybolan insan",
    "video_fk_kare_orani": "Videoda yanlış forklift (kare oranı)",
    "gecikme_orani_p90": "Yavaşlama (resmi modele göre, p90)",
}
# docs/17 §14 hedefi: forklift AP50 >= 0,90. Kapı değil; varsayılan modelin
# değişmesi için sahada ölçülüp operatörün onaylaması gereken sayı (§12.3-8).
AP50_HEDEFI = 0.90


class YerelHata(Exception):
    """Girdi ya da ortam hatası: iletideki adımı yapın (çıkış kodu 2)."""

    cikis_kodu = 2


class AdimHatasi(YerelHata):
    """Ağ hatası ya da bir adım yarıda kaldı: yeniden çalıştırmak kaldığı yerden sürer."""

    cikis_kodu = 1


def _yaz(ileti: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {ileti}", flush=True)


def _baslik(ileti: str) -> None:
    print(f"\n==== {ileti} ====", flush=True)


def dosya_ozeti(yol: Path) -> str:
    return veri.dosya_ozeti(yol)


# ---------------------------------------------------------------------------
# Klasörler
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Klasorler:
    """Çalışma klasörünün düzeni. `kimlik`: paketin özeti; `varyant`: eğitim ayarları."""

    calisma: Path
    kimlik: str
    varyant: str
    duman: bool

    @property
    def kaynaklar(self) -> Path:
        return self.calisma / "kaynaklar"

    @property
    def yolox(self) -> Path:
        return self.kaynaklar / "yolox-kaynak"

    def pth(self, boy: str) -> Path:
        return self.kaynaklar / ortak.RESMI_AGIRLIKLAR[boy][0].rsplit("/", 1)[-1]

    def onnx(self, boy: str) -> Path:
        return self.kaynaklar / ortak.RESMI_ONNX[boy]

    @property
    def video(self) -> Path:
        return self.kaynaklar / "vtest.avi"

    @property
    def arac_seti(self) -> Path:
        return self.kaynaklar / "arac-seti"

    @property
    def loco_ham(self) -> Path:
        return self.calisma / "loco-ham"

    @property
    def loco_veri(self) -> Path:
        return self.calisma / ("loco-veri-duman" if self.duman else "loco-veri")

    @property
    def saha(self) -> Path:
        return self.calisma / f"saha-{self.kimlik}"

    @property
    def on_deneme(self) -> Path:
        return self.calisma / f"on-deneme-{self.varyant}"

    @property
    def birlesik(self) -> Path:
        return self.calisma / f"birlesik-{self.varyant}"

    @property
    def egitim(self) -> Path:
        return self.calisma / f"egitim-{self.varyant}"

    @property
    def adaylar(self) -> Path:
        return self.calisma / f"aday-{self.varyant}"

    @property
    def kurulacak(self) -> Path:
        return self.calisma / KURULACAK

    @property
    def sonuc(self) -> Path:
        return self.calisma / SONUC


def varyant_adi(
    boy: str,
    kip: str,
    devir: int,
    saha_tekrar: int,
    kimlik: str,
    duman: bool,
    loco_kimligi: str | None = None,
) -> str:
    """Eğitimi belirleyen her şey adda: başka ayarla ya da başka veriyle yazılmış ara
    kayıt sürdürülmez. Betiğin indirdiği LOCO sabittir (ortak.py); --loco-veri ile
    verilen hazır LOCO'nun kimliği (eğitim JSON'unun özeti) ada eklenir."""
    ad = f"{boy}-{kip}-d{devir}-t{saha_tekrar}-{kimlik}"
    if loco_kimligi:
        ad += f"-l{loco_kimligi}"
    return ad + ("-duman" if duman else "")


def hazir_loco_kimligi(loco: Path) -> str:
    """--loco-veri klasörünün kimliği; klasör hazırlanmamışsa LocoBozukHatasi."""
    json_yolu = loco / "annotations" / "egitim.json"
    if not json_yolu.is_file():
        raise veri.LocoBozukHatasi(
            f"{json_yolu} yok: --loco-veri, `veri.py hazirla` çıktısı olmalı"
        )
    return dosya_ozeti(json_yolu)[:8]


# ---------------------------------------------------------------------------
# Günlük: ekrana ve CALISMA/gunluk.txt'ye birlikte
# ---------------------------------------------------------------------------


class _Ikiz(io.TextIOBase):
    """Yazılanı iki akışa birden yazar (ekran ve günlük dosyası)."""

    def __init__(self, ekran, dosya) -> None:
        super().__init__()
        self._ekran = ekran
        self._dosya = dosya

    def write(self, metin: str) -> int:
        self._ekran.write(metin)
        self._dosya.write(metin)
        return len(metin)

    def flush(self) -> None:
        self._ekran.flush()
        self._dosya.flush()


@contextlib.contextmanager
def gunluge_de_yaz(yol: Path):
    yol.parent.mkdir(parents=True, exist_ok=True)
    with yol.open("a", encoding="utf-8", errors="replace") as dosya:
        dosya.write(f"\n---- {datetime.now().isoformat(timespec='seconds')} ----\n")
        eski_cikis, eski_hata = sys.stdout, sys.stderr
        ikiz = _Ikiz(eski_cikis, dosya)
        sys.stdout = sys.stderr = ikiz
        try:
            yield
        except (YerelHata, veri.VeriHatasi) as hata:
            # Ekrana main() yazar; günlükte de dursun (destek ekibi dosyaya bakar)
            dosya.write(f"\nDURDU: {hata}\n")
            raise
        except KeyboardInterrupt:
            dosya.write("\nDURDURULDU (kullanıcı)\n")
            raise
        finally:
            sys.stdout, sys.stderr = eski_cikis, eski_hata


# ---------------------------------------------------------------------------
# Alt süreçler
# ---------------------------------------------------------------------------

Calistirici = Callable[[str, Sequence[str]], int]


def alt_surec_ortami(yolox_klasoru: Path) -> dict[str, str]:
    """Alt süreçlerin ortamı: YOLOX kaynağı import yolunda, çıktı UTF-8."""
    ortam = dict(os.environ)
    yollar = [str(yolox_klasoru)]
    if ortam.get("PYTHONPATH"):
        yollar.append(ortam["PYTHONPATH"])
    ortam["PYTHONPATH"] = os.pathsep.join(yollar)
    ortam["PYTHONUTF8"] = "1"
    ortam["PYTHONIOENCODING"] = "utf-8"
    # egit.py süre bütçesini bu değişkenden sayar (GitHub bacakları); burada yok
    ortam.pop("DALSAN_IS_BASLANGICI", None)
    return ortam


def surec_calistirici(ortam: dict[str, str]) -> Calistirici:
    """Alt süreci çalıştırıp çıktısını satır satır ekrana ve günlüğe aktarır."""

    def calistir(adim: str, komut: Sequence[str]) -> int:
        _yaz(f"{adim}: {' '.join(str(p) for p in komut[1:])}")
        with subprocess.Popen(
            [str(p) for p in komut],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=ortam,
            text=True,
            encoding="utf-8",
            errors="replace",
        ) as surec:
            assert surec.stdout is not None
            for satir in surec.stdout:
                sys.stdout.write(satir)
            kod = surec.wait()
        sys.stdout.flush()
        return kod

    return calistir


def _betik(ad: str) -> str:
    return str(BURASI / ad)


def _zorunlu(calistir: Calistirici, adim: str, komut: Sequence[str]) -> None:
    kod = calistir(adim, komut)
    if kod == 2:
        raise YerelHata(f"{adim}: girdi hatası (çıkış kodu 2); ayrıntı yukarıda ve {GUNLUK}'ta.")
    if kod != 0:
        raise AdimHatasi(
            f"{adim} başarısız (çıkış kodu {kod}); ayrıntı yukarıda ve {GUNLUK}'ta. "
            "Aynı komutla yeniden çalıştırın: biten adımlar atlanır."
        )


# ---------------------------------------------------------------------------
# Ortam
# ---------------------------------------------------------------------------


def calisma_yolunu_denetle(calisma: Path, windows: bool | None = None) -> None:
    """Windows'ta OpenCV (cv2.imread, VideoCapture) ASCII olmayan yolu açamaz."""
    if windows is None:
        windows = os.name == "nt"
    if windows and not str(calisma.resolve()).isascii():
        raise YerelHata(
            f"Çalışma klasörünün yolunda Türkçe ya da özel karakter var: {calisma}. "
            "Görüntü kitaplığı (OpenCV) bu yolları Windows'ta açamaz; C:\\NextGen-Forklift "
            "gibi yalnız İngilizce harfli bir klasör seçin."
        )


def diski_denetle(calisma: Path, gereken_gb: float) -> None:
    bos = shutil.disk_usage(calisma).free / 1e9
    if bos < gereken_gb:
        raise YerelHata(
            f"Diskte {bos:.1f} GB boş yer var; eğitim için en az {gereken_gb:.0f} GB gerekir "
            f"({calisma}). Yer açın ya da --calisma ile başka bir disk seçin."
        )


def bellek_uyarisi() -> str | None:
    try:
        import psutil
    except ImportError:
        return None
    toplam = psutil.virtual_memory().total / 1e9
    if toplam < ONERILEN_BELLEK_GB:
        return (
            f"Bu bilgisayarda {toplam:.1f} GB bellek var ({ONERILEN_BELLEK_GB:.0f} GB "
            "önerilir): eğitim yavaş olabilir ya da bellek yetmeyebilir."
        )
    return None


def modulleri_denetle(calistir: Calistirici, moduller: Iterable[str], neden: str) -> None:
    ad_listesi = ", ".join(moduller)
    kod = calistir(
        f"paket denetimi ({neden})",
        [sys.executable, "-c", f"import {ad_listesi}; print('paketler tamam')"],
    )
    if kod != 0:
        raise YerelHata(
            f"Eğitim paketleri eksik ({neden}). Windows'ta Egit-Windows.bat bunları kendisi "
            "kurar; elle: python -m pip install torch==2.14.0 torchvision==0.29.0 ve "
            "python -m pip install -r egitim/forklift/gereksinimler-yerel.txt"
        )


def onceligi_dusur() -> None:
    """Eğitim, aynı bilgisayardaki canlı analizi aç bırakmasın (alt süreçler de devralır)."""
    try:
        import psutil

        surec = psutil.Process()
        if os.name == "nt":
            surec.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            surec.nice(10)
    except (ImportError, OSError) as hata:
        _yaz(f"UYARI: süreç önceliği düşürülemedi ({hata!r}); normal öncelikle sürüyor")


@contextlib.contextmanager
def uyku_engeli():
    """Windows eğitim sürerken uykuya geçmesin (uyursa eğitim de durur)."""
    if os.name != "nt":
        yield
        return
    import ctypes

    es_continuous, es_system_required = 0x80000000, 0x00000001
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.SetThreadExecutionState(es_continuous | es_system_required)
    try:
        yield
    finally:
        kernel32.SetThreadExecutionState(es_continuous)


@contextlib.contextmanager
def kilit(calisma: Path):
    """Aynı çalışma klasöründe iki eğitim aynı anda koşmasın."""
    yol = calisma / KILIT
    if yol.is_file():
        try:
            eski = int(yol.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            eski = None
        if eski is not None and eski != os.getpid() and _surec_yasiyor_mu(eski):
            raise YerelHata(
                f"Bu klasörde bir eğitim zaten sürüyor (süreç {eski}): {calisma}. Öteki "
                "pencereyi kapatın ya da bitmesini bekleyin."
            )
    yol.write_text(f"{os.getpid()}\n", encoding="utf-8")
    try:
        yield
    finally:
        yol.unlink(missing_ok=True)


def _surec_yasiyor_mu(pid: int) -> bool:
    try:
        import psutil
    except ImportError:
        # Bilinemiyor. Kilit alınır: psutil'siz ortamı modül denetimi zaten durdurur.
        return False
    return psutil.pid_exists(pid)


# ---------------------------------------------------------------------------
# Kaynaklar
# ---------------------------------------------------------------------------

Indirici = Callable[[str, Path, "str | None"], str]


def kaynak_ozeti(dosyalar: Iterable[tuple[str, bytes]]) -> str:
    """YOLOX paketinin içerik özeti (ortak.YOLOX_KAYNAK_OZETI'nin tanımı)."""
    satirlar = sorted(f"{yol}\0{hashlib.sha256(veri_).hexdigest()}\n" for yol, veri_ in dosyalar)
    return hashlib.sha256("".join(satirlar).encode("utf-8")).hexdigest()


def _klasordeki_paket(kok: Path) -> Iterable[tuple[str, bytes]]:
    """kok/yolox altındaki dosyalar; Python'un yazdığı __pycache__ sayılmaz."""
    for yol in sorted((kok / "yolox").rglob("*")):
        if yol.is_file() and "__pycache__" not in yol.parts and yol.suffix != ".pyc":
            yield yol.relative_to(kok).as_posix(), yol.read_bytes()


def arsivdeki_paket(arsiv: Path) -> list[tuple[str, bytes]]:
    """GitHub arşivinden ("YOLOX-<commit>/yolox/...") yalnız yolox/ paketi."""
    dosyalar = []
    try:
        with zipfile.ZipFile(arsiv) as zip_:
            for bilgi in zip_.infolist():
                parcalar = bilgi.filename.split("/")
                if bilgi.is_dir() or len(parcalar) < 3 or parcalar[1] != "yolox":
                    continue
                if any(p in ("", ".", "..") or "\\" in p for p in parcalar[1:]):
                    raise YerelHata(f"YOLOX arşivinde beklenmedik yol: {bilgi.filename!r}")
                dosyalar.append(("/".join(parcalar[1:]), zip_.read(bilgi)))
    except (zipfile.BadZipFile, OSError) as hata:
        raise AdimHatasi(f"YOLOX arşivi okunamadı: {hata!r}; yeniden çalıştırın") from hata
    return dosyalar


def yolox_kaynagini_hazirla(hedef: Path, indir: Indirici) -> None:
    """YOLOX kaynak kodu, sabit commit (ortak.YOLOX_COMMIT), içerik özeti denetlenerek."""
    if (hedef / "yolox").is_dir() and kaynak_ozeti(_klasordeki_paket(hedef)) == (
        ortak.YOLOX_KAYNAK_OZETI
    ):
        _yaz("YOLOX kaynak kodu: zaten var, içerik özeti tuttu")
        return
    arsiv = hedef.parent / "yolox.zip"
    indir(ortak.YOLOX_ARSIVI, arsiv, None)
    dosyalar = arsivdeki_paket(arsiv)
    ozet = kaynak_ozeti(dosyalar)
    if ozet != ortak.YOLOX_KAYNAK_OZETI:
        arsiv.unlink(missing_ok=True)
        raise YerelHata(
            f"YOLOX kaynak kodu sabitlenen içerikle tutmuyor ({len(dosyalar)} dosya, özet "
            f"{ozet}; beklenen {ortak.YOLOX_KAYNAK_OZETI}). Dosya yolda değiştirilmiş "
            "olabilir; kullanılmadı."
        )
    gecici = Path(tempfile.mkdtemp(prefix=".yolox-", dir=hedef.parent))
    try:
        for yol, icerik in dosyalar:
            (gecici / yol).parent.mkdir(parents=True, exist_ok=True)
            (gecici / yol).write_bytes(icerik)
        if hedef.exists():
            shutil.rmtree(hedef)
        gecici.rename(hedef)
    finally:
        shutil.rmtree(gecici, ignore_errors=True)
    arsiv.unlink(missing_ok=True)
    _yaz(f"YOLOX kaynak kodu hazır: {len(dosyalar)} dosya, içerik özeti tuttu")


def resmi_onnx_ozeti(boy: str) -> str:
    ad = ortak.RESMI_ONNX[boy]
    for satir in MODEL_OZETLERI.read_text(encoding="utf-8").splitlines():
        parcalar = satir.split()
        if len(parcalar) == 2 and parcalar[1] == ad:
            return parcalar[0]
    raise YerelHata(f"{MODEL_OZETLERI} içinde {ad} yok")


def arac_seti_listesi(sinir: int | None = None) -> list[tuple[str, str]]:
    """(sha256, dosya adı) çiftleri, arac_seti.sha256'daki sırayla."""
    satirlar = [
        (parcalar[0], parcalar[1])
        for parcalar in (s.split() for s in ARAC_SETI_LISTESI.read_text("utf-8").splitlines())
        if len(parcalar) == 2
    ]
    return satirlar[:sinir] if sinir is not None else satirlar


def arac_setini_hazirla(hedef: Path, indir: Indirici, sinir: int | None) -> None:
    """Araç seti (Open Images), dosya başına SHA-256 denetimli, 8 indirme birden.

    Her dosyanın ayrıntılı indirme satırı günlüğü boğmasın diye yutulur; yalnız
    özet ve ilk hata yazılır. Eksik küme kapıyı KALDIRDIĞI için (ölçülemeyen
    metrik) eksik kalırsa betik durur.
    """
    liste = arac_seti_listesi(sinir)
    hedef.mkdir(parents=True, exist_ok=True)

    def bir(ozet_ad: tuple[str, str]) -> str | None:
        ozet, ad = ozet_ad
        try:
            indir(f"{ortak.ARAC_SETI_ADRESI}/{ad}", hedef / ad, ozet)
        except veri.VeriHatasi as hata:
            return f"{ad}: {hata}"
        return None

    _yaz(f"Araç seti: {len(liste)} görüntü denetleniyor ya da iniyor ...")
    with contextlib.redirect_stdout(io.StringIO()):
        with ThreadPoolExecutor(ESZAMANLI_INDIRME) as havuz:
            hatalar = [h for h in havuz.map(bir, liste) if h is not None]
    if hatalar:
        raise AdimHatasi(
            f"Araç setinin {len(hatalar)}/{len(liste)} görüntüsü inmedi (ilki: {hatalar[0]}). "
            "İnternet bağlantısını denetleyip yeniden çalıştırın; inenler yeniden inmez."
        )
    _yaz(f"Araç seti hazır: {len(liste)} görüntü, SHA-256'lar tuttu")


def kaynaklari_hazirla(klasorler: Klasorler, boy: str, indir: Indirici) -> None:
    _baslik("Kaynaklar (bir kez iner, sonra denetlenip atlanır)")
    klasorler.kaynaklar.mkdir(parents=True, exist_ok=True)
    yolox_kaynagini_hazirla(klasorler.yolox, indir)
    adres, ozet = ortak.RESMI_AGIRLIKLAR[boy]
    indir(adres, klasorler.pth(boy), ozet)
    indir(
        ortak.RESMI_ONNX_ADRESI + ortak.RESMI_ONNX[boy], klasorler.onnx(boy), resmi_onnx_ozeti(boy)
    )
    indir(ortak.VIDEO[0], klasorler.video, ortak.VIDEO[1])
    arac_setini_hazirla(klasorler.arac_seti, indir, DUMAN_ARAC_SETI if klasorler.duman else None)


def locoyu_hazirla(klasorler: Klasorler, hazir: Path | None) -> Path:
    """LOCO: hazır verilmişse o; yoksa indirilir (bir kez) ve hazırlanır."""
    if hazir is not None:
        _yaz(f"LOCO: hazır klasör kullanılıyor ({hazir})")
        return hazir
    hedef = klasorler.loco_veri
    if (hedef / veri.HAZIRLIK_KAYDI).is_file():
        _yaz(f"LOCO: zaten hazırlanmış ({hedef})")
        return hedef
    _baslik("LOCO (bir kez: ~770 MB iner, hazırlığı birkaç dakika sürer)")
    veri.etiketleri_indir(klasorler.loco_ham)
    veri.arsivi_indir(
        ortak.LOCO_ARSIV_ADRESLERI,
        klasorler.loco_ham,
        beklenen_sha256=ortak.LOCO_ARSIV_SHA256,
        beklenen_boyut=ortak.LOCO_ARSIV_BOYUTU,
    )
    veri.hazirla(
        klasorler.loco_ham,
        hedef,
        sinir=DUMAN_LOCO_SINIRI if klasorler.duman else None,
    )
    return hedef


def birlestirmeyi_hazirla(klasorler: Klasorler, ayar: Ayar, loco_hazir: Path | None) -> None:
    """LOCO + fabrika (bir kez). Betiğin kendi hazırladığı LOCO bozulmuşsa (yarım kopya,
    disk hatası, virüs tarayıcısı) klasör silinip bir kez yeniden hazırlanır; kullanıcının
    verdiği hazır klasöre dokunulmaz, hata ona söylenir."""
    if (klasorler.birlesik / veri.BIRLESTIRME_KAYDI).is_file():
        return
    loco = locoyu_hazirla(klasorler, loco_hazir)
    _baslik("Birleştirme (LOCO + fabrika)")
    for deneme in (1, 2):
        if klasorler.birlesik.exists():
            shutil.rmtree(klasorler.birlesik)
        try:
            veri.birlestir(loco, klasorler.saha, klasorler.birlesik, saha_tekrar=ayar.saha_tekrar)
            return
        except veri.LocoBozukHatasi as hata:
            if loco_hazir is not None or deneme == 2:
                raise
            _yaz(f"UYARI: {hata} LOCO silinip yeniden hazırlanıyor.")
            shutil.rmtree(loco, ignore_errors=True)
            loco = locoyu_hazirla(klasorler, None)


# ---------------------------------------------------------------------------
# Veri
# ---------------------------------------------------------------------------


def saha_paketini_hazirla(paket: Path, klasorler: Klasorler) -> dict:
    """Fabrika paketini denetleyip açar (bir kez); manifest'i döndürür."""
    if not (klasorler.saha / TAMAM).is_file():
        if klasorler.saha.exists():
            shutil.rmtree(klasorler.saha)
        _yaz(f"Fabrika paketi denetlenip açılıyor: {paket}")
        veri.saha_paketini_ac(paket, klasorler.saha)
        (klasorler.saha / TAMAM).write_text(f"{paket.name}\n", encoding="utf-8")
    manifest = json.loads((klasorler.saha / veri.SAHA_MANIFESTI).read_text(encoding="utf-8"))
    test = json.loads((klasorler.saha / "annotations" / "test.json").read_text(encoding="utf-8"))
    egitim = json.loads(
        (klasorler.saha / "annotations" / "egitim.json").read_text(encoding="utf-8")
    )
    if not test["images"]:
        raise YerelHata(
            "Fabrika paketinde test günü yok: etiketli kareler tek günden. Kabul ölçümü "
            "eğitimde görülmemiş günlerde yapılır (docs/17 §14). En az iki ayrı günün "
            "karesini etiketleyip paketi Forklift sayfasından yeniden indirin."
        )
    if not egitim["images"]:
        raise YerelHata("Fabrika paketinde eğitim günü yok; paketi yeniden indirin.")
    return manifest


def kucuk_egitim_seti(kaynak: Path, hedef: Path, sinir: int) -> int:
    """kaynak'ın eğitim kümesinden en çok `sinir` görüntü (kutulular önce, tekrarsız).

    Ön deneme ve duman içindir; görüntüler bağlanır, JSON salt ASCII yazılır.
    """
    belge = json.loads((kaynak / "annotations" / "egitim.json").read_text(encoding="utf-8"))
    kutulu = {e["image_id"] for e in belge["annotations"]}
    asillar = [g for g in belge["images"] if "asil_id" not in g]
    secilen = sorted(asillar, key=lambda g: g["id"] not in kutulu)[:sinir]
    kimlikler = {g["id"] for g in secilen}
    if hedef.exists():
        shutil.rmtree(hedef)
    (hedef / "egitim").mkdir(parents=True)
    (hedef / "annotations").mkdir()
    for giris in secilen:
        ad = giris["file_name"]
        veri.bagla_ya_da_kopyala(kaynak / "egitim" / ad, hedef / "egitim" / ad)
    veri._json_yaz(
        hedef / "annotations" / "egitim.json",
        {
            "images": secilen,
            "annotations": [e for e in belge["annotations"] if e["image_id"] in kimlikler],
            "categories": belge["categories"],
        },
    )
    return len(secilen)


# ---------------------------------------------------------------------------
# Eğitim, dışa aktarım, ölçüm
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ayar:
    boy: str
    kip: str
    devir: int
    saha_tekrar: int
    is_parcacigi: int
    veri_isci: int


def egit(
    calistir: Calistirici, ayar: Ayar, veri_klasoru: Path, calisma: Path, pth: Path, devir: int
) -> None:
    """egit.py; biterse calisma/BITTI. Veri işçileriyle düşerse bir kez işçisiz yeniden
    dener (Windows'ta çok süreçli veri yüklemesi sorun çıkarabilir; ara kayıttan sürer)."""
    komut = [
        sys.executable,
        _betik("egit.py"),
        "--veri",
        str(veri_klasoru),
        "--boy",
        ayar.boy,
        "--kip",
        ayar.kip,
        "--resmi-pth",
        str(pth),
        "--calisma",
        str(calisma),
        "--devir",
        str(devir),
        "--sure-sn",
        str(EGITIM_SURESI_SN),
        "--is-parcacigi",
        str(ayar.is_parcacigi),
    ]
    kod = calistir("eğitim", [*komut, "--veri-isci", str(ayar.veri_isci)])
    if kod not in (0, 2) and ayar.veri_isci > 0:
        _yaz("UYARI: eğitim düştü; veri işçisiz (tek süreç) yeniden deneniyor, ara kayıttan sürer")
        kod = calistir("eğitim (işçisiz)", [*komut, "--veri-isci", "0"])
    if kod == 2:
        raise YerelHata(f"eğitim: girdi hatası; ayrıntı yukarıda ve {GUNLUK}'ta.")
    if kod != 0 or not (calisma / "BITTI").is_file():
        raise AdimHatasi(
            f"eğitim bitmedi (çıkış kodu {kod}); aynı komutla yeniden çalıştırın, kaldığı "
            "devirden sürer."
        )


def model_karti(ayar: Ayar, klasorler: Klasorler, veri_klasoru: Path, pth: Path) -> dict:
    """ONNX'e yazılan kart (dalsan_model_karti): nereden, hangi veriyle. Kişisel veri yok."""
    birlestirme = veri_klasoru / veri.BIRLESTIRME_KAYDI
    egitim_json = veri_klasoru / "annotations" / "egitim.json"
    kart = {
        "ad": "NextGen AI Forklift adayı (fabrikanın kendi verisiyle, yerel eğitim)",
        "tarih": datetime.now().astimezone().isoformat(timespec="seconds"),
        "boy": ayar.boy,
        "kip": ayar.kip,
        "devir": ayar.devir,
        "calistirma_kipi": "duman" if klasorler.duman else "yerel",
        "saha_tekrar": ayar.saha_tekrar,
        "loco_commit": ortak.LOCO_COMMIT,
        "yolox_commit": ortak.YOLOX_COMMIT,
        "resmi_pth_sha256": dosya_ozeti(pth),
        "saha_paketi": klasorler.kimlik,
        "egitim_json_sha256": dosya_ozeti(egitim_json),
        "egitim_goruntu_kaydi": len(json.loads(egitim_json.read_bytes())["images"]),
    }
    if birlestirme.is_file():
        kart["birlestirme_sha256"] = dosya_ozeti(birlestirme)
    return kart


def aday_adi(klasorler: Klasorler, boy: str, kip: str, k: int) -> str:
    return f"forklift-{boy}-{kip}-{klasorler.kimlik}-k{k}"


def adaylari_uret(
    calistir: Calistirici,
    ayar: Ayar,
    klasorler: Klasorler,
    calisma: Path,
    cikti: Path,
    kart: dict,
    denetim_klasoru: Path,
    kisi_oncelikleri: Sequence[int] = KISI_ONCELIKLERI,
    denetim_sinir: int = DENETIM_GORUNTUSU,
) -> list[int]:
    """Her k için birleşik ONNX + denetim (eski sınıflar resmi modelle aynı mı)."""
    cikti.mkdir(parents=True, exist_ok=True)
    kart_yolu = cikti / "kart.json"
    if not kart_yolu.is_file():
        kart_yolu.write_text(json.dumps(kart, ensure_ascii=False, indent=2) + "\n", "utf-8")
    for k in kisi_oncelikleri:
        ad = aday_adi(klasorler, ayar.boy, ayar.kip, k)
        if (cikti / f"{ad}.{TAMAM}").is_file():
            continue
        onnx = cikti / f"{ad}.onnx"
        _zorunlu(
            calistir,
            f"dışa aktarım k={k}",
            [
                sys.executable,
                _betik("model.py"),
                "disa-aktar",
                "--boy",
                ayar.boy,
                "--kip",
                ayar.kip,
                "--resmi-pth",
                str(klasorler.pth(ayar.boy)),
                "--ek-bas",
                str(calisma / "ek_bas.pth"),
                "--cikti",
                str(onnx),
                "--kart",
                str(kart_yolu),
                "--kisi-onceligi",
                str(k),
            ],
        )
        _zorunlu(
            calistir,
            f"denetim k={k} (eski sınıflar resmi modelle aynı mı)",
            [
                sys.executable,
                _betik("model.py"),
                "denetle",
                "--boy",
                ayar.boy,
                "--onnx",
                str(onnx),
                "--resmi-onnx",
                str(klasorler.onnx(ayar.boy)),
                "--goruntu",
                str(denetim_klasoru),
                "--sinir",
                str(denetim_sinir),
            ],
        )
        (cikti / f"{ad}.{TAMAM}").write_text(dosya_ozeti(onnx) + "\n", encoding="utf-8")
    return list(kisi_oncelikleri)


def olc(
    calistir: Calistirici,
    klasorler: Klasorler,
    boy: str,
    model: Path,
    veri_klasoru: Path,
    cikti: Path,
    sinir: int | None,
) -> dict:
    """degerlendir.py; aynı modelin aynı kapılarla ölçümü varsa yeniden ölçülmez."""
    esikler = json.loads(ESIKLER.read_text(encoding="utf-8"))
    if cikti.is_file():
        try:
            eski = json.loads(cikti.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            eski = {}
        if eski.get("model_sha256") == dosya_ozeti(model) and eski.get("esikler") == esikler:
            return eski
    komut = [
        sys.executable,
        _betik("degerlendir.py"),
        "--model",
        str(model),
        "--resmi",
        str(klasorler.onnx(boy)),
        "--veri",
        str(veri_klasoru),
        "--video",
        str(klasorler.video),
        "--arac-seti",
        str(klasorler.arac_seti),
        "--esikler",
        str(ESIKLER),
        "--cikti",
        str(cikti),
        "--etiket",
        model.stem,
    ]
    if sinir is not None:
        komut += ["--sinir", str(sinir)]
    _zorunlu(calistir, f"ölçüm {model.stem}", komut)
    return json.loads(cikti.read_text(encoding="utf-8"))


def on_deneme(calistir: Calistirici, ayar: Ayar, klasorler: Klasorler) -> None:
    """Fabrikanın 64 karesiyle 4 devir, tek aday, 10 görüntüde ölçüm: zincirin hepsi."""
    kok = klasorler.on_deneme
    if (kok / TAMAM).is_file():
        _yaz("Ön deneme: daha önce geçti, atlanıyor")
        return
    _baslik("Ön deneme (birkaç dakika: ortam ve zincir sınanır)")
    if kok.exists():
        shutil.rmtree(kok)
    sayi = kucuk_egitim_seti(klasorler.saha, kok / "veri", KUCUK_GORUNTU)
    _yaz(f"Ön deneme verisi: {sayi} fabrika karesi")
    egit(calistir, ayar, kok / "veri", kok / "calisma", klasorler.pth(ayar.boy), KUCUK_DEVIR)
    kart = model_karti(ayar, klasorler, kok / "veri", klasorler.pth(ayar.boy))
    kart["calistirma_kipi"] = "on_deneme"
    adaylari_uret(
        calistir,
        ayar,
        klasorler,
        kok / "calisma",
        kok / "aday",
        kart,
        klasorler.saha / "test",
        kisi_oncelikleri=(1,),
        denetim_sinir=KUCUK_DENETIM,
    )
    model = kok / "aday" / f"{aday_adi(klasorler, ayar.boy, ayar.kip, 1)}.onnx"
    olc(calistir, klasorler, ayar.boy, model, klasorler.saha, kok / "olcum.json", KUCUK_OLCUM)
    (kok / TAMAM).write_text("geçti\n", encoding="utf-8")
    _yaz("Ön deneme geçti: ortam ve zincir çalışıyor")


# ---------------------------------------------------------------------------
# Sonuç
# ---------------------------------------------------------------------------


def _sayi(deger: float | None) -> str:
    """Üç anlamlı basamak: 0,005 gibi eşikler yuvarlanıp başka sayı görünmesin."""
    return "ölçülmedi" if deger is None else f"{deger:.3g}".replace(".", ",")


def _kapi_satiri(ad: str, kapi: dict) -> str:
    metrik = kapi["metrik"]
    yon = "en fazla" if kapi["yon"] == "en_fazla" else "en az"
    isim = METRIK_ADLARI.get(metrik, metrik)
    durum = "geçti" if kapi["gecti"] else "KALDI"
    return f"  {isim:<50} {_sayi(kapi['deger']):>9}  ({yon} {_sayi(kapi['esik'])})  {durum}"


def oneri_sec(olcumler: dict[int, dict]) -> int | None:
    """Geçen adaylar arasında ONERI_SIRASI'ndaki ilki; geçen yoksa None."""
    for k in ONERI_SIRASI:
        if k in olcumler and olcumler[k].get("gecti"):
            return k
    return None


def en_yakin(olcumler: dict[int, dict]) -> int:
    """Hiçbiri geçmediyse en az kapıda kalan (eşitlikte öneri sırası)."""
    return min(
        (k for k in ONERI_SIRASI if k in olcumler),
        key=lambda k: (len(olcumler[k].get("kalan") or []), ONERI_SIRASI.index(k)),
    )


def _neler_yapilabilir(kalan: Iterable[str]) -> list[str]:
    kalan = set(kalan)
    oneriler = []
    if kalan & {"fk_r_en_az", "vg_r_artisi_en_az"}:
        oneriler.append(
            "Daha çok forkliftli kare etiketleyin: farklı saatler, ışık, kameralar ve "
            "forkliftin farklı yönleri (yandan, önden, yüklü, boş)."
        )
    if kalan & {"fk_fp_goruntu_basi_en_fazla", "fk_kesinlik_en_az", "pt_fk_en_fazla"}:
        oneriler.append(
            "Forkliftsiz kareleri de etiketleyin (“Forklift yok”), özellikle yanlış "
            "forklift gösterilen kamerada; transpaleti “Transpalet” diye işaretleyin."
        )
    if kalan & {
        "insan_kaybi_en_fazla",
        "arac_kaybi_en_fazla",
        "video_insan_kaybi_en_fazla",
        "video_fk_kare_orani_en_fazla",
        "arac_seti_tr_fk_en_fazla",
        "gecikme_orani_p90_en_fazla",
    }:
        oneriler.append(
            "İnsan, araç ya da hız kapısı kaldı: bu, etiket eklemekle değil yöntemle ilgili "
            "olabilir; sonucu (bu dosya ve gunluk.txt) destek ekibine iletin."
        )
    oneriler.append(
        "Sonra Forklift sayfasından yeni paketi indirip bu adımı yeniden çalıştırın: "
        "yeni paket yeni bir eğitim başlatır."
    )
    return oneriler


def sonuc_metni(
    olcumler: dict[int, dict], oneri: int | None, klasorler: Klasorler, adlar: dict[int, str]
) -> str:
    zaman = datetime.now().strftime("%d.%m.%Y %H:%M")
    satirlar = [f"NextGen Detector - forklift eğitimi sonucu ({zaman})", ""]
    secilen = oneri if oneri is not None else en_yakin(olcumler)
    olcum = olcumler[secilen]
    if klasorler.duman:
        satirlar += [
            "DUMAN SINAMASI: kurulum çalışıyor. Bu kısa denemenin modeli KURULMAZ.",
            "Gerçek eğitim için aynı komutu --duman olmadan çalıştırın.",
            "",
        ]
    elif oneri is not None:
        satirlar += [
            "SONUÇ: GEÇTİ. Kurulacak model hazır.",
            f"  Klasör: {klasorler.kurulacak}",
            f"    {adlar[oneri]}.onnx           model",
            f"    {adlar[oneri]}.olcum.json     ölçüm (program kurarken ister)",
            "  Kurmak için: programda Forklift sayfası > Modeli kur > iki dosyayı seçin.",
            "",
        ]
    else:
        satirlar += [
            "SONUÇ: KALDI. Hiçbir aday bütün kapılardan geçemedi; program bu modeli kurmaz.",
            f"En yakın aday: k={secilen} ({len(olcum.get('kalan') or [])} kapı kaldı).",
            "",
        ]
    sayilar = olcum.get("sayilar") or {}
    satirlar.append(
        f"Fabrikanın test günlerinde ölçüm (k={secilen}; {olcum.get('goruntu_sayisi')} kare, "
        f"{sayilar.get('fk_gercek', 0)} forklift kutusu):"
    )
    for ad, kapi in (olcum.get("kapilar") or {}).items():
        satirlar.append(_kapi_satiri(ad, kapi))
    ap50 = (olcum.get("metrikler") or {}).get("fk_ap50")
    satirlar += [
        "",
        f"Forklift AP50: {_sayi(ap50)} (hedef {_sayi(AP50_HEDEFI)}). Bu bir kapı değildir: "
        "modelin programın varsayılanı olması için ayrıca aranan sayıdır.",
        "",
        "Adaylar (k: insanı koruma ayarı; önerilen k=1):",
    ]
    for k in sorted(olcumler):
        o = olcumler[k]
        durum = "GEÇTİ" if o.get("gecti") else f"KALDI ({', '.join(o.get('kalan') or [])})"
        satirlar.append(f"  k={k}: {durum}")
    if oneri is None and not klasorler.duman:
        satirlar += ["", "Ne yapılabilir:"]
        satirlar += [f"  - {s}" for s in _neler_yapilabilir(olcum.get("kalan") or [])]
    satirlar += [
        "",
        f"Ayrıntı: {klasorler.adaylar} (her adayın ölçüm dosyası) ve {GUNLUK}.",
        "Fabrika kareleri bu bilgisayarda kalır; bu klasörü paylaşmayın (KVKK).",
    ]
    return "\n".join(satirlar) + "\n"


def sonucu_yaz(
    olcumler: dict[int, dict], klasorler: Klasorler, adlar: dict[int, str]
) -> int | None:
    oneri = None if klasorler.duman else oneri_sec(olcumler)
    if klasorler.kurulacak.exists():
        shutil.rmtree(klasorler.kurulacak)
    if oneri is not None:
        klasorler.kurulacak.mkdir()
        for uzanti in ("onnx", "olcum.json"):
            shutil.copyfile(
                klasorler.adaylar / f"{adlar[oneri]}.{uzanti}",
                klasorler.kurulacak / f"{adlar[oneri]}.{uzanti}",
            )
    metin = sonuc_metni(olcumler, oneri, klasorler, adlar)
    klasorler.sonuc.write_text(metin, encoding="utf-8")
    print(metin, flush=True)
    return oneri


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------


def varsayilan_devir(boy: str) -> int:
    """istek.json'daki devir: GitHub'daki son tam eğitimle aynı."""
    try:
        return int(json.loads(ISTEK.read_text(encoding="utf-8"))["devir"][boy])
    except (OSError, ValueError, KeyError, TypeError) as hata:
        raise YerelHata(f"{ISTEK} okunamadı ({hata!r}); --devir verin") from hata


def akisi_calistir(
    secenekler: argparse.Namespace,
    *,
    calistirici: Calistirici | None = None,
    indir: Indirici | None = None,
) -> int:
    """Bütün akış; SONUC.txt'yi yazar. Çıkış kodunu döndürür."""
    calisma = secenekler.calisma.resolve()
    calisma_yolunu_denetle(calisma)
    calisma.mkdir(parents=True, exist_ok=True)
    indir = indir or veri.dosya_indir
    with gunluge_de_yaz(calisma / GUNLUK), kilit(calisma), uyku_engeli():
        _baslik("Ortam")
        _yaz(f"Python {sys.version.split()[0]} ({sys.executable})")
        if secenekler.oncelik == "dusuk":
            onceligi_dusur()
        uyari = bellek_uyarisi()
        if uyari:
            _yaz(f"UYARI: {uyari}")
        diski_denetle(
            calisma,
            GEREKEN_DISK_GB_LOCO_HAZIR
            if secenekler.loco_veri or (calisma / "loco-veri" / veri.HAZIRLIK_KAYDI).is_file()
            else GEREKEN_DISK_GB,
        )
        paket = secenekler.saha.resolve()
        kimlik = veri.saha_paketinin_ozeti(paket)[:12]
        devir = (
            KUCUK_DEVIR
            if secenekler.duman
            else (secenekler.devir or varsayilan_devir(secenekler.boy))
        )
        ayar = Ayar(
            boy=secenekler.boy,
            kip=secenekler.kip,
            devir=devir,
            saha_tekrar=secenekler.saha_tekrar,
            is_parcacigi=secenekler.is_parcacigi,
            veri_isci=secenekler.veri_isci,
        )
        klasorler = Klasorler(
            calisma=calisma,
            kimlik=kimlik,
            varyant=varyant_adi(
                ayar.boy,
                ayar.kip,
                ayar.devir,
                ayar.saha_tekrar,
                kimlik,
                secenekler.duman,
                hazir_loco_kimligi(secenekler.loco_veri) if secenekler.loco_veri else None,
            ),
            duman=secenekler.duman,
        )
        _yaz(
            f"Eğitim: {ayar.boy}-{ayar.kip}, {ayar.devir} devir, fabrika kareleri x"
            f"{ayar.saha_tekrar}, {ayar.is_parcacigi} iş parçacığı; paket {kimlik}"
        )
        calistirici = calistirici or surec_calistirici(alt_surec_ortami(klasorler.yolox))
        modulleri_denetle(calistirici, GEREKEN_MODULLER, "eğitim ortamı")

        _baslik("Fabrika paketi")
        manifest = saha_paketini_hazirla(paket, klasorler)
        for uyari in manifest.get("uyarilar") or []:
            _yaz(f"UYARI (paket): {uyari}")

        kaynaklari_hazirla(klasorler, ayar.boy, indir)
        modulleri_denetle(calistirici, YOLOX_MODULLERI, "YOLOX kaynağı")

        if not secenekler.duman:
            on_deneme(calistirici, ayar, klasorler)

        birlestirmeyi_hazirla(
            klasorler,
            ayar,
            secenekler.loco_veri.resolve() if secenekler.loco_veri else None,
        )

        _baslik(f"Eğitim ({ayar.devir} devir; kesilirse aynı komut kaldığı yerden sürdürür)")
        egitim_verisi = klasorler.birlesik
        if secenekler.duman:
            egitim_verisi = klasorler.calisma / f"duman-veri-{klasorler.varyant}"
            kucuk_egitim_seti(klasorler.birlesik, egitim_verisi, KUCUK_GORUNTU)
        if (klasorler.egitim / "BITTI").is_file():
            _yaz("Eğitim daha önce bitmiş, atlanıyor")
        else:
            egit(
                calistirici,
                ayar,
                egitim_verisi,
                klasorler.egitim,
                klasorler.pth(ayar.boy),
                ayar.devir,
            )

        _baslik("Adaylar (kişi önceliği k = 0, 1, 2)")
        kart = model_karti(ayar, klasorler, klasorler.birlesik, klasorler.pth(ayar.boy))
        adaylari_uret(
            calistirici,
            ayar,
            klasorler,
            klasorler.egitim,
            klasorler.adaylar,
            kart,
            klasorler.birlesik / "test",
            denetim_sinir=KUCUK_DENETIM if secenekler.duman else DENETIM_GORUNTUSU,
        )

        _baslik("Ölçüm (fabrikanın test günleri, video, araç seti)")
        adlar = {k: aday_adi(klasorler, ayar.boy, ayar.kip, k) for k in KISI_ONCELIKLERI}
        olcumler = {
            k: olc(
                calistirici,
                klasorler,
                ayar.boy,
                klasorler.adaylar / f"{adlar[k]}.onnx",
                klasorler.birlesik,
                klasorler.adaylar / f"{adlar[k]}.olcum.json",
                KUCUK_OLCUM if secenekler.duman else None,
            )
            for k in KISI_ONCELIKLERI
        }
        _baslik("Sonuç")
        sonucu_yaz(olcumler, klasorler, adlar)
    return 0


def _pozitif(metin: str) -> int:
    try:
        sayi = int(metin)
    except ValueError as hata:
        raise argparse.ArgumentTypeError(f"tam sayı bekleniyordu: {metin!r}") from hata
    if sayi < 1:
        raise argparse.ArgumentTypeError(f"en az 1 olmalı: {sayi}")
    return sayi


def _negatif_olmayan(metin: str) -> int:
    try:
        sayi = int(metin)
    except ValueError as hata:
        raise argparse.ArgumentTypeError(f"tam sayı bekleniyordu: {metin!r}") from hata
    if sayi < 0:
        raise argparse.ArgumentTypeError(f"0 ya da pozitif olmalı: {sayi}")
    return sayi


def ayristirici() -> argparse.ArgumentParser:
    a = argparse.ArgumentParser(
        prog="yerel.py",
        description="Forklift modelini fabrikanın kendi verisiyle kapalı bilgisayarda eğitir.",
    )
    a.add_argument(
        "--saha",
        type=Path,
        required=True,
        help="Forklift sayfasının veri paketi (zip ya da klasör)",
    )
    a.add_argument("--calisma", type=Path, required=True, help="çalışma klasörü (ASCII yol)")
    a.add_argument("--boy", choices=tuple(ortak.BOYLAR), default="tiny")
    a.add_argument("--kip", choices=ortak.KIPLER, default="v3")
    a.add_argument("--devir", type=_pozitif, default=None, help="varsayılan: istek.json")
    a.add_argument("--saha-tekrar", type=_pozitif, default=3)
    a.add_argument(
        "--is-parcacigi",
        type=_pozitif,
        default=max(1, (os.cpu_count() or 2) // 2),
        help="varsayılan: çekirdeklerin yarısı (canlı analize yer kalsın)",
    )
    a.add_argument("--veri-isci", type=_negatif_olmayan, default=2)
    a.add_argument("--oncelik", choices=("dusuk", "normal"), default="dusuk")
    a.add_argument("--loco-veri", type=Path, default=None, help="hazırlanmış LOCO klasörü")
    a.add_argument("--duman", action="store_true", help="yalnız kurulumu sınayan kısa koşu")
    return a


def main(argv: Sequence[str] | None = None) -> int:
    secenekler = ayristirici().parse_args(argv)
    try:
        return akisi_calistir(secenekler)
    except (YerelHata, veri.VeriHatasi) as hata:
        print(f"\nDURDU: {hata}", file=sys.stderr, flush=True)
        return hata.cikis_kodu
    except KeyboardInterrupt:
        print(
            "\nDURDURULDU. Aynı komutla yeniden çalıştırın: biten adımlar atlanır.",
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

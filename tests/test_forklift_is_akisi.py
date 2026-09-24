"""Forklift eğitim iş akışının yapısı ve betikleri (docs/17 §12.3).

.github/workflows/forklift-egit.yml ve forklift-egit-bacak.yml GitHub'da
saatlerce çalışır ve yalnız gönderimle başlar: bir yapı hatası ancak bir
sonraki gönderimde, çoğu zaman saatler sonra görülür. Bu dosya bilinen
hataları gönderimden ÖNCE yakalar:

* tetikleyiciler; sıra yok (çalıştırmalar birbirini ne iptal eder ne bekletir),
* yetkiler: yalnız "yayinla" yazar ve o iş depo kodu çalıştırmaz,
* yalnız GitHub'ın kendi eylemleri, güncel ana sürümleriyle,
* bacak zinciri: eğitim asla sessizce sıfırdan başlamaz, bir varyantın
  düşmesi ötekileri durdurmaz, eğitimle yükleme arasında ağ işi yoktur,
* kip kararı yalnız gönderimin net git farkından verilir,
* egitim/forklift/istek.json ve gereksinimler.txt biçimi.

İş akışındaki önemli kabuk betikleri GERÇEKTEN çalıştırılır (bash 4+, git, jq
ve sha256sum gerekir; yoksa o testler atlanır, GitHub'ın Linux makinesinde
hepsi vardır): kip kararı geçici bir git deposunda, bacağın "iş var mı"
kararı sahte yapıtlarla, yayın adımları sahte bir gh ile. Ürün ortamında
(.venv) çalışır; torch gerekmez.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
IS_AKISLARI = KOK / ".github" / "workflows"
ANA_YOL = IS_AKISLARI / "forklift-egit.yml"
BACAK_YOL = IS_AKISLARI / "forklift-egit-bacak.yml"
FORKLIFT = KOK / "egitim" / "forklift"
if str(FORKLIFT) not in sys.path:
    sys.path.insert(0, str(FORKLIFT))

import ortak  # noqa: E402

GECERLI_VARYANTLAR = {f"{boy}-{kip}" for boy in ortak.BOYLAR for kip in ortak.KIPLER}
DUMAN_VARYANTLARI = ["tiny-v1", "tiny-v2", "tiny-v3"]

# Yalnız GitHub'ın kendi eylemleri, 23.09.2026'daki güncel ana sürümleriyle.
IZINLI_EYLEMLER = {
    "actions/checkout": "v7",
    "actions/setup-python": "v7",
    "actions/upload-artifact": "v7",
    "actions/download-artifact": "v8",
    "actions/cache": "v6",
    "actions/cache/restore": "v6",
    "actions/cache/save": "v6",
}
BACAK_IS_AKISI = "./.github/workflows/forklift-egit-bacak.yml"

# Eğitim ortamı (torch ayrıca, CPU dizininden kurulur)
GEREKSINIMLER = {
    "numpy": "2.4.6",
    "opencv-python-headless": "4.10.0.84",
    "loguru": "0.7.3",
    "tqdm": "4.70.1",
    "tabulate": "0.10.0",
    "psutil": "7.2.2",
    "pycocotools": "2.0.11",
    "onnx": "1.23.0",
    "onnxruntime": "1.30.0",
    "thop": "0.1.1.post2209072238",
    "tensorboard": "2.21.0",
    "packaging": "26.3",
}


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _yukle(yol: Path) -> dict:
    yaml = pytest.importorskip("yaml", reason="PyYAML yok (uvicorn[standard] ile gelir)")
    belge = yaml.safe_load(yol.read_text(encoding="utf-8"))
    # YAML 1.1'de "on" bir mantıksal değerdir: PyYAML onu True anahtarıyla okur
    if True in belge:
        belge["on"] = belge.pop(True)
    return belge


@pytest.fixture(scope="module")
def ana() -> dict:
    return _yukle(ANA_YOL)


@pytest.fixture(scope="module")
def bacak() -> dict:
    return _yukle(BACAK_YOL)


def _adimlar(is_akisi: dict) -> list[tuple[str, dict]]:
    """(iş adı, adım) çiftleri. Yeniden kullanılan iş akışını çağıran işin adımı yoktur."""
    return [(ad, adim) for ad, is_ in is_akisi["jobs"].items() for adim in is_.get("steps", [])]


def _adim(is_akisi: dict, is_adi: str, ad: str) -> dict:
    """Adımı kimliğinden (id) ya da adından bulur."""
    for adim in is_akisi["jobs"][is_adi]["steps"]:
        if ad in (adim.get("id"), adim.get("name")):
            return adim
    raise AssertionError(f"{is_adi} işinde '{ad}' adımı yok")


def _ifade(metin: object) -> str:
    """'${{ ... }}' sarmalını ve boşluk farklarını atar (karşılaştırma için)."""
    metin = str(metin).strip()
    if metin.startswith("${{") and metin.endswith("}}"):
        metin = metin[3:-2]
    return " ".join(metin.split())


def _bash_surumu() -> int:
    if os.name == "nt" or not shutil.which("bash"):
        return 0
    try:
        sonuc = subprocess.run(
            ["bash", "-c", "echo ${BASH_VERSINFO[0]}"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    return int(sonuc.stdout.strip() or 0)


arac_gerekli = pytest.mark.skipif(
    _bash_surumu() < 4 or not all(shutil.which(a) for a in ("git", "jq", "sha256sum")),
    reason="iş akışı betikleri bash 4+, git, jq ve sha256sum ister (GitHub'ın Linux makinesi)",
)


def _ortam(tmp_path: Path, **ek: str) -> dict[str, str]:
    """Adımın göreceği ortam: python ve python3 bu testi çalıştıran Python'dur."""
    klasor = tmp_path / "bin"
    klasor.mkdir(exist_ok=True)
    for ad in ("python", "python3"):
        sarmal = klasor / ad
        sarmal.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        sarmal.chmod(0o755)
    ortam = {
        "PATH": f"{klasor}{os.pathsep}{os.environ.get('PATH', '')}",
        "HOME": str(tmp_path),
        "LC_ALL": "C.UTF-8",
        "PYTHONUTF8": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GITHUB_OUTPUT": str(tmp_path / "github_output.txt"),
        "GITHUB_ENV": str(tmp_path / "github_env.txt"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "github_step_summary.md"),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "ornek/dalsan",
        "GITHUB_RUN_ID": "123456",
        "GITHUB_RUN_NUMBER": "7",
        "GITHUB_SHA": "0123456789abcdef0123456789abcdef01234567",
    }
    ortam.update(ek)
    return ortam


def _calistir(betik: str, cwd: Path, ortam: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Adımı GitHub'ın Linux makinesindeki gibi çalıştırır (shell: bash -> -eo pipefail)."""
    klasor = Path(ortam["HOME"]) / "betikler"
    klasor.mkdir(exist_ok=True)
    dosya = klasor / f"adim-{len(list(klasor.iterdir()))}.sh"
    dosya.write_text(betik, encoding="utf-8")
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(dosya)],
        cwd=cwd,
        env=ortam,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def _ciktilar(ortam: dict[str, str]) -> dict[str, str]:
    yol = Path(ortam["GITHUB_OUTPUT"])
    if not yol.exists():
        return {}
    return dict(s.split("=", 1) for s in yol.read_text(encoding="utf-8").splitlines() if s)


def _ozet(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Tetikleyiciler, sıra, yetkiler, eylemler
# ---------------------------------------------------------------------------


def test_tetikleyiciler(ana):
    on = ana["on"]
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"]["branches"] == ["main"]
    assert set(on["push"]["paths"]) == {
        "egitim/forklift/**",
        ".github/workflows/forklift-egit.yml",
        ".github/workflows/forklift-egit-bacak.yml",
        "tests/test_forklift_*.py",
        # ölçümün dayandığı ürün dosyaları: değişince duman koşar
        "backend/app/analiz/tespit.py",
        "backend/requirements.txt",
        ".env.example",
        "models/indir.sh",
        "models/SHA256SUMS",
    }
    kip = on["workflow_dispatch"]["inputs"]["kip"]
    assert kip["type"] == "choice"
    assert kip["options"] == ["duman", "tam"]
    assert kip["default"] == "duman"


def test_bacak_yalniz_cagrilarak_calisir(bacak):
    on = bacak["on"]
    assert set(on) == {"workflow_call"}
    girdiler = on["workflow_call"]["inputs"]
    assert {ad: g["type"] for ad, g in girdiler.items()} == {
        "varyant": "string",
        "mod": "string",
        "bacak": "number",
        "devir": "number",
    }
    assert all(g["required"] is True for g in girdiler.values())


def test_calistirmalar_birbirini_ne_iptal_eder_ne_bekletir(ana, bacak):
    """Sıra (concurrency) yok. GitHub bir sırada yalnız en son bekleyen çalıştırmayı
    tutar: sıra olsaydı bekleyen bir tam isteğin yerini arkadan gelen bir gönderim
    alırdı. Kipe göre ayrı sıra da kurulamaz: Actions'taki push olayının commit
    listesinde değişen dosyalar yoktur (23.09.2026, çalıştırma 4: istek değiştiği
    halde commits.*.modified ifadesi "duman" verdi, tam istek dumana düştü)."""
    for belge in (ana, bacak):
        assert "concurrency" not in belge
        for is_ in belge["jobs"].values():
            assert "concurrency" not in is_
    kod = [
        satir
        for satir in ANA_YOL.read_text(encoding="utf-8").splitlines()
        if not satir.lstrip().startswith("#")
    ]
    assert not [satir for satir in kod if "github.event.commits" in satir]


def test_betikler_bash_pipefail_ile_calisir(ana, bacak):
    for belge in (ana, bacak):
        assert belge["defaults"]["run"]["shell"] == "bash"


def test_yalniz_yayinla_yazar(ana, bacak):
    for belge in (ana, bacak):
        assert belge["permissions"] == {"contents": "read"}
    for ad, is_ in ana["jobs"].items():
        beklenen = {"contents": "write"} if ad == "yayinla" else None
        assert is_.get("permissions") == beklenen, ad
    for ad, is_ in bacak["jobs"].items():
        assert "permissions" not in is_, ad


def test_yayinla_depo_kodu_calistirmaz(ana):
    is_ = ana["jobs"]["yayinla"]
    for adim in is_["steps"]:
        eylem = adim.get("uses", "")
        assert not eylem or eylem.startswith("actions/download-artifact@"), eylem
        betik = adim.get("run", "")
        for yasak in ("pip", "python", "egitim/", "models/", "bash ", "source ", "./"):
            assert yasak not in betik, f"yayinla / {adim.get('name')}: {yasak!r}"
    assert is_["env"]["GH_TOKEN"] == "${{ github.token }}"
    olustur = _adim(ana, "yayinla", "Ön sürümü yayınla")
    assert _ifade(olustur["if"]) == "env.MOD == 'tam'"
    for parca in ("gh release create", "--prerelease", "--target", "--notes-file", "--title"):
        assert parca in olustur["run"], parca
    # Sürüm oluşturan başka adım yok: duman kipinde hiçbir şey yayımlanmaz
    olusturanlar = [a for a in is_["steps"] if "gh release create" in a.get("run", "")]
    assert olusturanlar == [olustur]


def test_aday_yapitlari_tek_klasore_iner(ana):
    """download-artifact desene uyan TEK yapıtı alt klasör açmadan indirir, birden
    çoğunu alt klasörlere: merge-multiple olmadan tek varyantlı bir istekte
    betikler dosyaları yanlış yerde arardı."""
    for is_adi in ("yayinla", "ozet"):
        indirme = ana["jobs"][is_adi]["steps"][0]
        assert indirme["uses"] == "actions/download-artifact@v8"
        assert indirme["with"] == {"pattern": "aday-*", "path": "adaylar", "merge-multiple": True}


def test_yalniz_github_eylemleri_guncel_surumle(ana, bacak):
    for belge in (ana, bacak):
        for ad, adim in _adimlar(belge):
            if "uses" in adim:
                eylem, _, surum = adim["uses"].partition("@")
                assert IZINLI_EYLEMLER.get(eylem) == surum, f"{ad}: {adim['uses']}"
    cagrilar = {is_["uses"] for is_ in ana["jobs"].values() if "uses" in is_}
    assert cagrilar == {BACAK_IS_AKISI}
    assert all("uses" not in is_ for is_ in bacak["jobs"].values())


def test_kabuk_betiklerine_ifade_gomulmez(ana, bacak):
    """Girdiler ve çıktılar betiğe env ile girer; ${{ }} betik metnine gömülmez
    (betik enjeksiyonu)."""
    for belge in (ana, bacak):
        for ad, adim in _adimlar(belge):
            assert "${{" not in adim.get("run", ""), f"{ad} / {adim.get('name')}"


def test_her_isin_zaman_siniri_var(ana, bacak):
    for belge in (ana, bacak):
        for ad, is_ in belge["jobs"].items():
            if "uses" in is_:
                continue  # yeniden kullanılan iş akışı: sınır kendi işinde
            assert isinstance(is_.get("timeout-minutes"), int), ad
    # GitHub'ın makinesinde bir iş en çok 360 dk sürer
    assert bacak["jobs"]["egit"]["timeout-minutes"] == 350


def test_checkout_kimlik_birakmaz(ana, bacak):
    for belge in (ana, bacak):
        for ad, adim in _adimlar(belge):
            if adim.get("uses", "").startswith("actions/checkout@"):
                assert adim["with"]["persist-credentials"] is False, ad
    # Kip kararı gönderimden önceki commit'le karşılaştırır: bütün geçmiş gerekir
    assert ana["jobs"]["plan"]["steps"][0]["with"]["fetch-depth"] == 0


# ---------------------------------------------------------------------------
# İşler: veri, bacak zinciri, ölçüm, özet
# ---------------------------------------------------------------------------


def test_veri_isi(ana):
    onbellek = _adim(ana, "veri", "onbellek")
    assert onbellek["uses"] == "actions/cache/restore@v6"
    assert onbellek["with"]["path"] == "veri-seti"
    assert onbellek["with"]["key"] == (
        "forklift-veri-v1-${{ hashFiles('egitim/forklift/veri.py', 'egitim/forklift/ortak.py') }}"
    )
    adimlar = ana["jobs"]["veri"]["steps"]
    kaydet = [a for a in adimlar if a.get("uses") == "actions/cache/save@v6"]
    assert len(kaydet) == 1 and kaydet[0]["with"]["path"] == "veri-seti"
    # bozuk veri seti önbelleğe girmez: denetim kaydetmeden önce
    assert adimlar.index(_adim(ana, "veri", "Veri setini denetle")) < adimlar.index(kaydet[0])
    betikler = "\n".join(a.get("run", "") for a in adimlar)
    assert "veri.py indir --hedef ham" in betikler
    assert "veri.py hazirla --kaynak ham --hedef veri-seti" in betikler
    assert "rm -f ham/loco.zip" in betikler
    yukle = [a for a in adimlar if a.get("uses", "").startswith("actions/upload-artifact@")]
    assert len(yukle) == 1
    assert yukle[0]["with"]["name"] == "veri-seti"
    assert yukle[0]["with"]["retention-days"] == 3
    assert yukle[0]["with"]["compression-level"] == 0


def test_bacak_zinciri(ana):
    isler = ana["jobs"]
    assert "bacak4" not in isler
    for no in (1, 2, 3):
        is_ = isler[f"bacak{no}"]
        assert is_["uses"] == BACAK_IS_AKISI
        assert is_["strategy"]["fail-fast"] is False
        matris = is_["strategy"]["matrix"]["varyant"]
        assert _ifade(matris) == "fromJSON(needs.plan.outputs.varyantlar)"
        girdi = is_["with"]
        assert girdi["bacak"] == no
        assert _ifade(girdi["varyant"]) == "matrix.varyant"
        assert _ifade(girdi["mod"]) == "needs.plan.outputs.mod"
        assert _ifade(girdi["devir"]) == "fromJSON(needs.plan.outputs.devirler)[matrix.varyant]"
        if no == 1:
            assert set(is_["needs"]) == {"plan", "veri"}
            assert "if" not in is_
        else:
            assert set(is_["needs"]) == {"plan", f"bacak{no - 1}"}
            # Matris sonucu bütün varyantlarındır: bir varyantın düşmesi ötekilerin
            # sonraki bacaklarını durdurmaz (düşenin bacağı kendi kendine durur)
            onceki = f"needs.bacak{no - 1}.result"
            assert _ifade(is_["if"]) == (
                f"!cancelled() && ({onceki} == 'success' || {onceki} == 'failure')"
            )


def test_bacak_sifirdan_baslamaz(bacak):
    adimlar = bacak["jobs"]["egit"]["steps"]
    # İlk adım saati yazar: egit.py süre bütçesini bundan sayar (kurulum dahil)
    assert adimlar[0]["run"].strip() == 'echo "DALSAN_IS_BASLANGICI=$(date +%s)" >> "$GITHUB_ENV"'
    indir = _adim(bacak, "egit", "Önceki bacağın çalışma klasörü (yoksa DURUR)")
    assert _ifade(indir["if"]) == "inputs.bacak > 1"
    assert indir["with"]["name"] == "calisma-${{ inputs.varyant }}"
    # Hiçbir adım hatayı yutmaz: yapıt yoksa iş düşer
    assert not [a.get("name") for a in adimlar if "continue-on-error" in a]
    yukle = _adim(bacak, "egit", "Çalışma klasörünü yükle")
    assert yukle["with"]["name"] == "calisma-${{ inputs.varyant }}"
    assert yukle["with"]["overwrite"] is True
    assert yukle["with"]["retention-days"] == 7
    # Eğitim önceki bacakta bittiyse hiçbir şey yapılmaz, yapıt yeniden yüklenmez
    sonrakiler = adimlar[adimlar.index(_adim(bacak, "egit", "durum")) + 1 :]
    for adim in sonrakiler:
        kosul = adim.get("if", "")
        assert (
            "steps.durum.outputs.egit == 'true'" in kosul
            or "steps.egitim.outputs.bitti == 'true'" in kosul
        ), adim.get("name")
    egit = _adim(bacak, "egit", "egitim")["run"]
    assert "egitim/forklift/egit.py" in egit and '--sure-sn "$SURE_SN"' in egit
    # Tam: 330 dk. Duman: ilk iki bacak birer devirde durur (sürdürme sınanır)
    assert _ifade(bacak["jobs"]["egit"]["env"]["SURE_SN"]) == (
        "(inputs.mod == 'duman' && inputs.bacak < 3) && '1' || '19800'"
    )


def test_bacak_disa_aktarim_duserse_egitilmis_basi_ayri_adla_saklar(bacak):
    """Eğitim bitti, bir aday dışa aktarımda ya da sözleşme denetiminde düştü:
    zincirin kaydı ezilmez (olağan yükleme yapılmaz) ama eğitilmiş baş ayrı adla
    kalır; saatlerce süren eğitim kaybolmaz."""
    adimlar = bacak["jobs"]["egit"]["steps"]
    yukle = _adim(bacak, "egit", "Çalışma klasörünü yükle")
    sakla = _adim(bacak, "egit", "Eğitilmiş başı sakla (dışa aktarım ya da denetim düştüyse)")
    assert _ifade(sakla["if"]) == "failure() && steps.egitim.outputs.bitti == 'true'"
    assert sakla["with"]["name"] == "egitilmis-${{ inputs.varyant }}"
    assert sakla["with"]["name"] != yukle["with"]["name"]
    assert sakla["with"]["path"] == yukle["with"]["path"]
    assert adimlar.index(yukle) < adimlar.index(sakla)


def test_bacak_torch_cpu_dizininden_once_kurar(bacak):
    betik = _adim(bacak, "egit", "Eğitim paketleri (CPU torch)")["run"]
    assert "torch==2.14.0 torchvision==0.29.0" in betik
    cpu = betik.index("--index-url https://download.pytorch.org/whl/cpu")
    # thop sürümsüz torch ister: gereksinimler önce kurulsaydı pip CUDA'lı torch çekerdi
    assert cpu < betik.index("-r egitim/forklift/gereksinimler.txt")


def test_bacak_uc_aday_uretip_denetler(bacak):
    disa = _adim(bacak, "egit", "Birleşik ONNX'leri dışa aktar (k = 0, 1, 2)")["run"]
    assert "for k in 0 1 2" in disa and '--kisi-onceligi "$k"' in disa
    assert '--cikti "$W/$VARYANT-k$k.onnx"' in disa and '--kart "$W/kart.json"' in disa
    denetim = _adim(bacak, "egit", "Eski sınıflar resmi modelle aynı mı (20 test görüntüsü)")
    assert "model.py denetle" in denetim["run"] and "--sinir 20" in denetim["run"]
    assert '--resmi-onnx "models/yolox_$BOY.onnx"' in denetim["run"]
    test = _adim(bacak, "egit", "Duman - model testleri")
    assert "inputs.mod == 'duman'" in test["if"]
    assert "pytest -q tests/test_forklift_modeli.py" in test["run"]
    # Testler yüklemeden SONRA: düşseler de adaylar ölçülür (duman daha çok şey söyler)
    adimlar = bacak["jobs"]["egit"]["steps"]
    yukle = _adim(bacak, "egit", "Çalışma klasörünü yükle")
    assert adimlar.index(denetim) < adimlar.index(yukle) < adimlar.index(test)


def test_bacakta_egitimle_yukleme_arasinda_ag_isi_yok(bacak):
    """Eğitimden sonra ağdan bir şey inerse geçici bir hata saatlerce süren
    eğitimi yüklenmeden kaybettirir: resmi ONNX'ler eğitimden ÖNCE, yeniden
    denemeyle iner."""
    adimlar = bacak["jobs"]["egit"]["steps"]
    egitim = adimlar.index(_adim(bacak, "egit", "egitim"))
    yukle = adimlar.index(_adim(bacak, "egit", "Çalışma klasörünü yükle"))
    for adim in adimlar[egitim + 1 : yukle]:
        assert "uses" not in adim, adim.get("name")
        betik = adim.get("run", "")
        for ag in ("curl", "wget", "indir", "pip install", "git fetch", "http"):
            assert ag not in betik, f"{adim.get('name')}: {ag!r}"
    onnx = _adim(bacak, "egit", "Resmi ONNX modelleri (models/indir.sh, SHA-256 denetimli)")
    assert adimlar.index(onnx) < egitim
    assert "bash models/indir.sh" in onnx["run"] and "for deneme in 1 2 3" in onnx["run"]
    yolox = _adim(bacak, "egit", "YOLOX kaynağı (sabit commit)")["run"]
    assert "for deneme in 1 2 3" in yolox and "git -C" in yolox


@arac_gerekli
@pytest.mark.parametrize(("dusen", "beklenen_kod"), [(0, 0), (2, 0), (3, 1)])
def test_resmi_onnx_yeniden_denenir(bacak, tmp_path, dusen, beklenen_kod):
    """indir.sh ilk `dusen` denemede düşer; üçüncüsünde de düşerse adım düşer."""
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "indir.sh").write_text(
        'n=$(cat sayac 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > sayac\n'
        f'[ "$n" -gt {dusen} ]\n',
        encoding="utf-8",
    )
    ortam = _ortam(tmp_path)
    uyku = Path(ortam["PATH"].split(os.pathsep)[0]) / "sleep"
    uyku.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")  # 30 sn beklenmez
    uyku.chmod(0o755)
    adim = _adim(bacak, "egit", "Resmi ONNX modelleri (models/indir.sh, SHA-256 denetimli)")
    sonuc = _calistir(adim["run"], tmp_path, ortam)
    assert sonuc.returncode == beklenen_kod, sonuc.stdout + sonuc.stderr
    assert (tmp_path / "sayac").read_text(encoding="utf-8").strip() == str(min(dusen + 1, 3))
    if beklenen_kod:
        assert "::error title=Resmi modeller inmedi::" in sonuc.stdout


def test_yalniz_olcum_isi_forklift_modelini_zorunlu_indirir(ana, bacak):
    """Ölçüm işi ürünün model indirmesini sınar: kayıtlı forklift modeli de inmeli
    (INDIR_SIKI). Eğitim bacağı ise yalnız resmi modellere muhtaçtır; kayıtlı bir
    modelin yayını bozulsa bile eğitim durmamalı."""
    olcum = _adim(ana, "olc", "Resmi modeller (models/indir.sh, SHA-256 denetimli)")
    assert olcum.get("env", {}).get("INDIR_SIKI") == "1"
    egitim = _adim(bacak, "egit", "Resmi ONNX modelleri (models/indir.sh, SHA-256 denetimli)")
    assert "INDIR_SIKI" not in (egitim.get("env") or {})


def test_olc_her_varyanti_ayri_olcer(ana):
    olc = ana["jobs"]["olc"]
    assert "bacak3" in olc["needs"]
    assert "!cancelled()" in olc["if"]
    assert olc["strategy"]["fail-fast"] is False
    matris = olc["strategy"]["matrix"]["varyant"]
    assert _ifade(matris) == "fromJSON(needs.plan.outputs.varyantlar)"
    betik = _adim(ana, "olc", "Ürünün tespit motoruyla ölç")["run"]
    for parca in (
        "egitim/forklift/degerlendir.py",
        "--video vtest.avi",
        "--sinir 50",
        "--esikler egitim/forklift/esikler.json",
    ):
        assert parca in betik, parca
    assert olc["env"]["VIDEO_SHA256"] == (
        "45cddc9490be69345cbdab64ca583be65987e864ca408038e648db99e10516cf"
    )
    betikler = "\n".join(a.get("run", "") for a in olc["steps"])
    assert "pip install -r backend/requirements.txt" in betikler
    assert "bash models/indir.sh" in betikler
    # Gerçek araçlar: araç seti inerse ölçüme girer
    assert '"${sinir[@]}" "${arac[@]}"' in betik and "arac=(--arac-seti arac-seti)" in betik
    assert olc["env"]["ARAC_SETI_ADRESI"] == (
        "https://open-images-dataset.s3.amazonaws.com/validation"
    )


def test_ozet_her_durumda_sonuclari_yazar(ana):
    ozet = ana["jobs"]["ozet"]
    assert _ifade(ozet["if"]) == "always()"
    assert set(ozet["needs"]) == set(ana["jobs"]) - {"ozet"}
    betik = _adim(ana, "ozet", "Sonuç")["run"]
    for parca in (
        "===== FORKLIFT-SONUC-BASLA =====",
        "===== FORKLIFT-SONUC-BITTI =====",
        "::notice title=Forklift olcumu::",
        "OLCUM_JSON",
        "$GITHUB_STEP_SUMMARY",
    ):
        assert parca in betik, parca


# ---------------------------------------------------------------------------
# istek.json ve gereksinimler.txt
# ---------------------------------------------------------------------------


def test_istek_json_bicimi():
    istek = json.loads((FORKLIFT / "istek.json").read_text(encoding="utf-8"))
    assert set(istek) == {"varyantlar", "devir", "not"}
    varyantlar = istek["varyantlar"]
    assert varyantlar and len(set(varyantlar)) == len(varyantlar)
    assert set(varyantlar) <= GECERLI_VARYANTLAR
    assert set(istek["devir"]) <= set(ortak.BOYLAR)
    for boy in {v.split("-")[0] for v in varyantlar}:
        devir = istek["devir"][boy]
        assert type(devir) is int and 1 <= devir <= 300, (boy, devir)
    assert isinstance(istek["not"], str) and istek["not"].strip()


def test_arac_seti_listesi_bicimi():
    """egitim/forklift/arac_seti.sha256: sha256sum -c biçimi, yalnız Open Images
    görüntü kimlikleri (adlar URL'ye ve dosya yoluna girer)."""
    satirlar = (FORKLIFT / "arac_seti.sha256").read_text(encoding="utf-8").splitlines()
    assert len(satirlar) == 523
    adlar = []
    for satir in satirlar:
        assert re.fullmatch(r"[0-9a-f]{64}  [0-9a-f]{16}\.jpg", satir), satir
        adlar.append(satir.split("  ")[1])
    assert len(set(adlar)) == len(adlar) and adlar == sorted(adlar)


def test_gereksinimler_sabit_ve_torchsuz():
    metin = (FORKLIFT / "gereksinimler.txt").read_text(encoding="utf-8")
    satirlar = [s.split("#", 1)[0].strip() for s in metin.splitlines()]
    paketler = dict(s.split("==", 1) for s in satirlar if s)
    assert paketler == GEREKSINIMLER


# ---------------------------------------------------------------------------
# Plan: kip kararı (betik gerçekten çalıştırılır)
# ---------------------------------------------------------------------------


def _git(depo: Path, ortam: dict[str, str], *arg: str) -> str:
    sonuc = subprocess.run(
        ["git", *arg], cwd=depo, env=ortam, capture_output=True, text=True, check=True
    )
    return sonuc.stdout.strip()


def _commit(depo: Path, ortam: dict[str, str], dosyalar: dict[str, str], ileti: str) -> str:
    for yol, icerik in dosyalar.items():
        hedef = depo / yol
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, encoding="utf-8")
    _git(depo, ortam, "add", "-A")
    _git(depo, ortam, "-c", "user.name=Deneme", "-c", "user.email=d@ornek", "commit", "-qm", ileti)
    return _git(depo, ortam, "rev-parse", "HEAD")


def _istek_metni(degisen: dict | None = None) -> str:
    """Depodaki istek.json, istenen anahtarları değiştirilmiş olarak."""
    istek = json.loads((FORKLIFT / "istek.json").read_text(encoding="utf-8"))
    istek.update(degisen or {})
    return json.dumps(istek, ensure_ascii=False, indent=2) + "\n"


def _plan_deposu(tmp_path: Path, ortam: dict[str, str], istek_ile: bool = True) -> tuple[Path, str]:
    """İlk commit'te ortak.py (ve istenirse istek.json) olan bir depo."""
    depo = tmp_path / "depo"
    depo.mkdir()
    _git(depo, ortam, "init", "-q", "-b", "main")
    dosyalar = {"egitim/forklift/ortak.py": (FORKLIFT / "ortak.py").read_text(encoding="utf-8")}
    if istek_ile:
        dosyalar["egitim/forklift/istek.json"] = _istek_metni()
    return depo, _commit(depo, ortam, dosyalar, "ilk")


def _plani_calistir(ana: dict, depo: Path, ortam: dict[str, str], **olay):
    adim = _adim(ana, "plan", "plan")
    assert set(adim["env"]) == {"OLAY", "ELLE_KIP", "ONCEKI", "DAL"}
    ortam = dict(ortam, OLAY="push", ELLE_KIP="", ONCEKI="", DAL="refs/heads/main")
    ortam.update(olay)
    Path(ortam["GITHUB_OUTPUT"]).unlink(missing_ok=True)
    sonuc = _calistir(adim["run"], depo, ortam)
    return sonuc, _ciktilar(ortam)


@arac_gerekli
def test_plan_istek_degisince_tam(ana, tmp_path):
    ortam = _ortam(tmp_path)
    depo, ilk = _plan_deposu(tmp_path, ortam)
    yeni = _istek_metni({"not": "Yeni istek"})
    son = _commit(depo, ortam, {"egitim/forklift/istek.json": yeni}, "istek")
    sonuc, cikti = _plani_calistir(ana, depo, dict(ortam, GITHUB_SHA=son), ONCEKI=ilk)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    istek = json.loads(yeni)
    assert cikti["mod"] == "tam"
    assert json.loads(cikti["varyantlar"]) == istek["varyantlar"]
    assert json.loads(cikti["devirler"]) == {
        v: istek["devir"][v.split("-")[0]] for v in istek["varyantlar"]
    }
    assert cikti["etiket"] == "forklift-r7"
    assert json.loads(cikti["istek"]) == istek
    assert "::notice title=Forklift kipi::tam" in sonuc.stdout


@arac_gerekli
def test_plan_baska_dosya_degisince_duman(ana, tmp_path):
    ortam = _ortam(tmp_path)
    depo, ilk = _plan_deposu(tmp_path, ortam)
    son = _commit(depo, ortam, {"egitim/forklift/veri.py": "# degisti\n"}, "kod")
    sonuc, cikti = _plani_calistir(ana, depo, dict(ortam, GITHUB_SHA=son), ONCEKI=ilk)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert cikti["mod"] == "duman"
    assert json.loads(cikti["varyantlar"]) == DUMAN_VARYANTLARI
    # 4 devir (ilki mozaikli): bacak iş akışı dumanda ilk iki bacağı birer
    # devirde durdurur, üçüncüsü bitirir
    assert json.loads(cikti["devirler"]) == dict.fromkeys(DUMAN_VARYANTLARI, 4)
    assert "::warning" not in sonuc.stdout


@arac_gerekli
def test_plan_istegin_ilk_eklenmesi_duman(ana, tmp_path):
    """istek.json'u ilk kez ekleyen gönderim tam eğitim BAŞLATMAZ: boru hattı önce
    duman kipinde sınanır."""
    ortam = _ortam(tmp_path)
    depo, ilk = _plan_deposu(tmp_path, ortam, istek_ile=False)
    son = _commit(depo, ortam, {"egitim/forklift/istek.json": _istek_metni()}, "istek eklendi")
    sonuc, cikti = _plani_calistir(ana, depo, dict(ortam, GITHUB_SHA=son), ONCEKI=ilk)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert cikti["mod"] == "duman"


@arac_gerekli
def test_plan_cok_commitli_gonderimde_istek_arada_degisse_de_tam(ana, tmp_path):
    ortam = _ortam(tmp_path)
    depo, ilk = _plan_deposu(tmp_path, ortam)
    _commit(depo, ortam, {"egitim/forklift/istek.json": _istek_metni({"not": "y"})}, "istek")
    son = _commit(depo, ortam, {"tests/test_forklift_veri.py": "# test\n"}, "test")
    sonuc, cikti = _plani_calistir(ana, depo, dict(ortam, GITHUB_SHA=son), ONCEKI=ilk)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert cikti["mod"] == "tam"


@arac_gerekli
@pytest.mark.parametrize("onceki", ["0" * 40, "f" * 40])
def test_plan_onceki_commit_yoksa_son_commite_bakar(ana, tmp_path, onceki):
    """Yeni dal (000...) ya da yeniden yazılmış geçmiş: yalnız son commit okunur."""
    ortam = _ortam(tmp_path)
    depo, _ = _plan_deposu(tmp_path, ortam)
    son = _commit(depo, ortam, {"egitim/forklift/istek.json": _istek_metni({"not": "z"})}, "istek")
    sonuc, cikti = _plani_calistir(ana, depo, dict(ortam, GITHUB_SHA=son), ONCEKI=onceki)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert cikti["mod"] == "tam"
    assert "::warning title=Önceki commit yok::" in sonuc.stdout


@arac_gerekli
def test_plan_elle_tam(ana, tmp_path):
    ortam = _ortam(tmp_path)
    depo, ilk = _plan_deposu(tmp_path, ortam)
    sonuc, cikti = _plani_calistir(
        ana, depo, dict(ortam, GITHUB_SHA=ilk), OLAY="workflow_dispatch", ELLE_KIP="tam"
    )
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert cikti["mod"] == "tam"


@arac_gerekli
@pytest.mark.parametrize(("kip", "basarili"), [("tam", False), ("duman", True)])
def test_plan_elle_tam_yalniz_mainden(ana, tmp_path, kip, basarili):
    """Tam kip ön sürüm yayımlar: başka daldan elle istenirse birleşmemiş bir commit'e
    bağlanırdı. Duman her dalda koşabilir."""
    ortam = _ortam(tmp_path)
    depo, ilk = _plan_deposu(tmp_path, ortam)
    sonuc, cikti = _plani_calistir(
        ana,
        depo,
        dict(ortam, GITHUB_SHA=ilk),
        OLAY="workflow_dispatch",
        ELLE_KIP=kip,
        DAL="refs/heads/deneme-dali",
    )
    if basarili:
        assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
        assert cikti["mod"] == "duman"
    else:
        assert sonuc.returncode != 0
        assert "::error title=Tam eğitim yalnız main'den::refs/heads/deneme-dali" in sonuc.stdout
        assert "mod" not in cikti


@arac_gerekli
def test_plan_istek_degistirilip_geri_alininca_duman(ana, tmp_path):
    """Kip net farktan verilir: aynı gönderimde değiştirilip geri alınan istek,
    istek değildir."""
    ortam = _ortam(tmp_path)
    depo, ilk = _plan_deposu(tmp_path, ortam)
    _commit(depo, ortam, {"egitim/forklift/istek.json": _istek_metni({"not": "g"})}, "istek")
    son = _commit(depo, ortam, {"egitim/forklift/istek.json": _istek_metni()}, "geri al")
    sonuc, cikti = _plani_calistir(ana, depo, dict(ortam, GITHUB_SHA=son), ONCEKI=ilk)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert cikti["mod"] == "duman"
    assert "::warning" not in sonuc.stdout


@arac_gerekli
def test_plan_istek_silinip_yeniden_eklenince_tam(ana, tmp_path):
    """Aynı gönderimde silinip başka içerikle yeniden eklenen istek, net farkta
    DEĞİŞMİŞ görünür: yeni bir istektir."""
    ortam = _ortam(tmp_path)
    depo, ilk = _plan_deposu(tmp_path, ortam)
    (depo / "egitim" / "forklift" / "istek.json").unlink()
    _git(depo, ortam, "add", "-A")
    _git(depo, ortam, "-c", "user.name=D", "-c", "user.email=d@ornek", "commit", "-qm", "sil")
    yeni = {"egitim/forklift/istek.json": _istek_metni({"not": "yeniden"})}
    son = _commit(depo, ortam, yeni, "yeniden ekle")
    sonuc, cikti = _plani_calistir(ana, depo, dict(ortam, GITHUB_SHA=son), ONCEKI=ilk)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert cikti["mod"] == "tam"
    assert "::warning" not in sonuc.stdout


@arac_gerekli
@pytest.mark.parametrize(("deneme", "etiket"), [("1", "forklift-r7"), ("2", "forklift-r7-d2")])
def test_plan_yeniden_calistirmada_yeni_etiket(ana, tmp_path, deneme, etiket):
    """Çalıştırma numarası yeniden çalıştırmada aynı kalır: bütün işleri yeniden
    çalıştırılan bir tam koşu saatler sonra "etiket zaten var" diye düşmesin."""
    ortam = _ortam(tmp_path, GITHUB_RUN_ATTEMPT=deneme)
    depo, ilk = _plan_deposu(tmp_path, ortam)
    son = _commit(depo, ortam, {"egitim/forklift/istek.json": _istek_metni({"not": "d"})}, "i")
    sonuc, cikti = _plani_calistir(ana, depo, dict(ortam, GITHUB_SHA=son), ONCEKI=ilk)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    assert cikti["etiket"] == etiket


@arac_gerekli
@pytest.mark.parametrize(
    "bozuk",
    [
        {"varyantlar": ["tiny-v9"]},
        {"varyantlar": []},
        {"varyantlar": ["tiny-v1", "tiny-v1"]},
        {"devir": {"tiny": 0, "s": 20}},
        {"devir": {"tiny": 30}},
        {"devir": {"tiny": True, "s": 20}},
        {"not": ""},
        {"fazla": 1},
    ],
)
def test_plan_bozuk_istegi_her_kipte_durdurur(ana, tmp_path, bozuk):
    ortam = _ortam(tmp_path)
    depo, ilk = _plan_deposu(tmp_path, ortam)
    son = _commit(depo, ortam, {"egitim/forklift/istek.json": _istek_metni(bozuk)}, "bozuk")
    # tam: istek değişti; duman: elle başlatıldı (istek yine denetlenir)
    for olay in ({"ONCEKI": ilk}, {"OLAY": "workflow_dispatch", "ELLE_KIP": "duman"}):
        sonuc, cikti = _plani_calistir(ana, depo, dict(ortam, GITHUB_SHA=son), **olay)
        assert sonuc.returncode != 0, (bozuk, olay, sonuc.stdout)
        assert "::error title=istek.json geçersiz::" in sonuc.stdout
        assert "varyantlar" not in cikti


# ---------------------------------------------------------------------------
# Bacak: iş var mı, duman sınırı, model kartı
# ---------------------------------------------------------------------------


@arac_gerekli
@pytest.mark.parametrize(
    ("no", "dosyalar", "beklenen"),
    [
        (1, None, "true"),
        (2, {"SURUYOR": "5", "son.pth": "x", "BACAK": "1"}, "true"),
        (3, {"SURUYOR": "9", "son.pth": "x", "BACAK": "2"}, "true"),
        (2, {"BITTI": "", "ek_bas.pth": "x", "BACAK": "1"}, "false"),
        (3, {"BITTI": "", "ek_bas.pth": "x", "BACAK": "1"}, "false"),
        (2, {}, None),  # boş yapıt: sıfırdan başlanmaz
        (2, {"SURUYOR": "5", "BACAK": "1"}, None),  # son.pth yok
        (2, {"son.pth": "x", "BACAK": "1"}, None),  # SURUYOR yok
        (3, {"SURUYOR": "5", "son.pth": "x", "BACAK": "1"}, None),  # eski bacağın kaydı
        (2, {"SURUYOR": "5", "son.pth": "x"}, None),  # hangi bacağın olduğu belli değil
    ],
)
def test_bacak_is_var_mi(bacak, tmp_path, no, dosyalar, beklenen):
    calisma = tmp_path / "calisma" / "tiny-v1"
    if dosyalar is not None:
        calisma.mkdir(parents=True)
        for ad, icerik in dosyalar.items():
            (calisma / ad).write_text(icerik, encoding="utf-8")
    ortam = _ortam(tmp_path, BACAK=str(no), W=str(calisma), VARYANT="tiny-v1")
    sonuc = _calistir(_adim(bacak, "egit", "durum")["run"], tmp_path, ortam)
    if beklenen is None:
        assert sonuc.returncode != 0, sonuc.stdout
        assert "::error title=Ara kayıt" in sonuc.stdout
        assert "egit" not in _ciktilar(ortam)
    else:
        assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
        assert _ciktilar(ortam) == {"egit": beklenen}


@arac_gerekli
@pytest.mark.parametrize("varyant", sorted(GECERLI_VARYANTLAR))
def test_bacak_plandaki_her_varyanti_kabul_eder(bacak, tmp_path, varyant):
    # Plan varyant adlarını ortak.py'den denetler; bacağın biçim denetimi
    # plandan geçen hiçbir adı geri çevirmemeli (v1 ve v2'ye sabit eski denetim v3'ü
    # çevirirdi).
    ortam = _ortam(tmp_path, VARYANT=varyant, MOD="tam", BACAK="1", DEVIR="30")
    sonuc = _calistir(_adim(bacak, "egit", "Girdileri denetle")["run"], tmp_path, ortam)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    boy, kip = varyant.split("-")
    satirlar = Path(ortam["GITHUB_ENV"]).read_text(encoding="utf-8").splitlines()
    assert satirlar == [f"BOY={boy}", f"KIP={kip}"]


@arac_gerekli
@pytest.mark.parametrize("varyant", ["tiny", "m-v1", "tiny-v1 ", "tiny-v1;x", "tiny-v10", "s-w1"])
def test_bacak_bozuk_varyanti_geri_cevirir(bacak, tmp_path, varyant):
    ortam = _ortam(tmp_path, VARYANT=varyant, MOD="tam", BACAK="1", DEVIR="30")
    sonuc = _calistir(_adim(bacak, "egit", "Girdileri denetle")["run"], tmp_path, ortam)
    assert sonuc.returncode != 0
    assert "::error title=Geçersiz varyant::" in sonuc.stdout
    assert not Path(ortam["GITHUB_ENV"]).exists()


def _coco(goruntu: int) -> dict:
    return {
        "images": [
            {"id": i, "file_name": f"{i:06d}.jpg", "width": 64, "height": 48}
            for i in range(1, goruntu + 1)
        ],
        "annotations": [
            {
                "id": i,
                "image_id": i,
                "category_id": 1 + i % 2,
                "bbox": [1.0, 2.0, 10.0, 12.0],
                "area": 120.0,
                "iscrowd": 0,
            }
            for i in range(1, goruntu + 1)
        ],
        "categories": [{"id": 1, "name": "forklift"}, {"id": 2, "name": "pallet_jack"}],
    }


@arac_gerekli
def test_bacak_duman_egitimi_64_goruntuyle_sinirlar(bacak, tmp_path):
    json_yolu = tmp_path / "veri-seti" / "annotations" / "egitim.json"
    json_yolu.parent.mkdir(parents=True)
    json_yolu.write_text(json.dumps(_coco(100)), encoding="utf-8")
    betik = _adim(bacak, "egit", "Duman - eğitimi 64 görüntüyle sınırla")["run"]
    sonuc = _calistir(betik, tmp_path, _ortam(tmp_path))
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    belge = json.loads(json_yolu.read_text(encoding="utf-8"))
    assert [g["id"] for g in belge["images"]] == list(range(1, 65))
    assert {e["image_id"] for e in belge["annotations"]} == set(range(1, 65))
    assert belge["categories"] == _coco(1)["categories"]


@arac_gerekli
def test_bacak_model_karti(bacak, tmp_path):
    (tmp_path / "egitim" / "forklift").mkdir(parents=True)
    shutil.copy(FORKLIFT / "ortak.py", tmp_path / "egitim" / "forklift" / "ortak.py")
    veri = tmp_path / "veri-seti"
    (veri / "annotations").mkdir(parents=True)
    (veri / "annotations" / "egitim.json").write_text(json.dumps(_coco(3)), encoding="utf-8")
    (veri / "hazirlik.json").write_text(json.dumps({"loco_arsiv_sha256": "ab" * 32}), "utf-8")
    pth = tmp_path / "yolox_tiny.pth"
    pth.write_bytes(b"agirlik")
    calisma = tmp_path / "calisma" / "tiny-v2"
    calisma.mkdir(parents=True)
    ortam = _ortam(
        tmp_path, BOY="tiny", KIP="v2", DEVIR="30", MOD="tam", RESMI_PTH=str(pth), W=str(calisma)
    )
    sonuc = _calistir(_adim(bacak, "egit", "Model kartı")["run"], tmp_path, ortam)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    kart = json.loads((calisma / "kart.json").read_text(encoding="utf-8"))
    assert kart["boy"] == "tiny" and kart["kip"] == "v2" and kart["devir"] == 30
    assert kart["calistirma_kipi"] == "tam"
    assert kart["loco_commit"] == ortak.LOCO_COMMIT
    assert kart["yolox_commit"] == ortak.YOLOX_COMMIT
    assert kart["loco_arsiv_sha256"] == "ab" * 32
    assert kart["resmi_pth_sha256"] == _ozet(pth)
    assert kart["veri_hazirlik_sha256"] == _ozet(veri / "hazirlik.json")
    assert kart["egitim_json_sha256"] == _ozet(veri / "annotations" / "egitim.json")
    assert kart["egitim_goruntu_kaydi"] == 3
    assert kart["calistirma"] == "https://github.com/ornek/dalsan/actions/runs/123456"
    assert kart["calistirma_no"] == 7
    assert kart["git_sha"] == ortam["GITHUB_SHA"]


# ---------------------------------------------------------------------------
# Veri denetimi, ölçüm tablosu, yayın ve özet (sahte gh ile)
# ---------------------------------------------------------------------------


def _veri_seti(kok: Path) -> Path:
    """veri.py hazirla çıktısı biçiminde; görüntü özeti veri.py'nin formülüyle
    ("<ad> <sha256>" satırları, ad sırasıyla)."""
    veri = kok / "veri-seti"
    ozetler, goruntu_ozetleri = {}, {}
    for bolum, sayi in (("egitim", 3), ("test", 2)):
        (veri / bolum).mkdir(parents=True)
        (veri / "annotations").mkdir(exist_ok=True)
        belge = _coco(sayi)
        satirlar = ""
        for goruntu in belge["images"]:
            icerik = f"jpeg {bolum} {goruntu['id']}".encode()
            (veri / bolum / goruntu["file_name"]).write_bytes(icerik)
            satirlar += f"{goruntu['file_name']} {hashlib.sha256(icerik).hexdigest()}\n"
        goruntu_ozetleri[bolum] = hashlib.sha256(satirlar.encode()).hexdigest()
        yol = veri / "annotations" / f"{bolum}.json"
        yol.write_text(json.dumps(belge), encoding="utf-8")
        ozetler[f"{bolum}.json"] = _ozet(yol)
    kayit = {
        "json_sha256": ozetler,
        "goruntu_sha256": goruntu_ozetleri,
        "bolumler": {},
        "loco_arsiv_sha256": "cd" * 32,
    }
    (veri / "hazirlik.json").write_text(json.dumps(kayit), encoding="utf-8")
    return veri


@arac_gerekli
@pytest.mark.parametrize("bozulma", [None, "json", "goruntu", "bayt", "fazla"])
def test_veri_seti_denetimi(ana, tmp_path, bozulma):
    veri = _veri_seti(tmp_path)
    if bozulma == "json":
        (veri / "annotations" / "test.json").write_text("{}", encoding="utf-8")
    elif bozulma == "goruntu":
        (veri / "egitim" / "000002.jpg").unlink()
    elif bozulma == "bayt":  # önbellekte bozulmuş görüntü: JSON'lar tutar, dosya var
        (veri / "egitim" / "000001.jpg").write_bytes(b"11 bayt ...")
    elif bozulma == "fazla":  # hazırlıkta olmayan bir dosya
        (veri / "test" / "000009.jpg").write_bytes(b"jpeg")
    betik = _adim(ana, "veri", "Veri setini denetle")["run"]
    sonuc = _calistir(betik, tmp_path, _ortam(tmp_path))
    if bozulma is None:
        assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
        assert f"::notice title=LOCO arşivi::sha256 {'cd' * 32}" in sonuc.stdout
    else:
        assert sonuc.returncode != 0
        assert "::error title=Veri seti" in sonuc.stdout


def _olcum(etiket: str, gecti: bool) -> dict:
    return {
        "etiket": etiket,
        "gecti": gecti,
        "kalan": [] if gecti else ["fk_r_en_az"],
        "goruntu_sayisi": 50,
        "metrikler": {
            "fk_r": 0.61234,
            "fk_r_tum": 0.5,
            "pt_fk": 0.25,
            "arac_seti_tr_fk": 0.0,
            "insan_kaybi": 0.0,
            "vg_r_artisi": None,
        },
        "sayilar": {"fk_gercek": 94},
    }


def _aday_klasoru(kok: Path, varyant: str) -> None:
    """olc işinin bir varyant için yüklediği dosyalar (ONNX'ler sahte)."""
    kok.mkdir(parents=True, exist_ok=True)
    for k in range(3):
        ad = f"{varyant}-k{k}"
        (kok / f"{ad}.onnx").write_bytes(f"onnx {ad}".encode())
        olcum = json.dumps(_olcum(ad, gecti=k == 1))
        (kok / f"{ad}.olcum.json").write_text(olcum, encoding="utf-8")
    dosyalar = sorted(p.name for p in kok.iterdir() if p.name.startswith(f"{varyant}-k"))
    satirlar = [f"{_ozet(kok / ad)}  {ad}\n" for ad in dosyalar]
    (kok / f"SHA256SUMS-{varyant}").write_text("".join(satirlar), encoding="utf-8")


@arac_gerekli
@pytest.mark.parametrize(
    ("durum", "bacak", "neden"),
    [
        ("BITTI", "2", None),
        ("SURUYOR", "3", "Üç bacak yetmedi"),
        ("SURUYOR", "1", "Bacak zinciri durdu: son ara kayıt 1. bacağın"),
        ("SURUYOR", None, "Bacak zinciri durdu: son ara kayıt bilinmiyor. bacağın"),
    ],
)
def test_olc_egitim_bitmediyse_durur(ana, tmp_path, durum, bacak, neden):
    """Üç bacak yetmediyse devir sayısı, zincir erken durduysa o bacağın günlüğü söylenir."""
    calisma = tmp_path / "calisma"
    _aday_klasoru(calisma, "s-v1")
    (calisma / durum).write_text("12\n", encoding="utf-8")
    if bacak is not None:
        (calisma / "BACAK").write_text(f"{bacak}\n", encoding="utf-8")
    betik = _adim(ana, "olc", "Eğitim bitti mi, adaylar var mı")["run"]
    sonuc = _calistir(betik, tmp_path, _ortam(tmp_path, W="calisma", VARYANT="s-v1"))
    if neden is None:
        assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    else:
        assert sonuc.returncode != 0
        assert "::error title=s-v1 eğitimi bitmedi::" + neden in sonuc.stdout
        assert "sıradaki devir: 12" in sonuc.stdout


@arac_gerekli
@pytest.mark.skipif(not shutil.which("curl"), reason="curl yok")
@pytest.mark.parametrize("bozuk", [False, True])
def test_olc_arac_seti_iner_ya_da_uyariyla_atlanir(ana, tmp_path, bozuk):
    """Araç seti file:// adresinden iner ve özetleri denetlenir. Bir özet tutmazsa
    ölçüm yine yapılır: klasör silinir (degerlendir'e --arac-seti verilmez), kapısı
    ölçülmedi diye kalır; adım düşmez, uyarı bırakır."""
    kaynak = tmp_path / "kaynak"
    kaynak.mkdir()
    adlar = ("0123456789abcdef.jpg", "fedcba9876543210.jpg")
    satirlar = ""
    for ad in adlar:
        (kaynak / ad).write_bytes(ad.encode())
        satirlar += f"{hashlib.sha256(ad.encode()).hexdigest()}  {ad}\n"
    liste = tmp_path / "egitim" / "forklift" / "arac_seti.sha256"
    liste.parent.mkdir(parents=True)
    liste.write_text(satirlar, encoding="utf-8")
    if bozuk:
        (kaynak / adlar[1]).write_bytes(b"yolda degisti")
    ortam = _ortam(tmp_path, ARAC_SETI_ADRESI=kaynak.as_uri())
    adim = _adim(ana, "olc", "Araç seti (Open Images, SHA-256 denetimli)")
    sonuc = _calistir(adim["run"], tmp_path, ortam)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    if bozuk:
        assert "::warning title=Araç seti inmedi::" in sonuc.stdout
        assert not (tmp_path / "arac-seti").exists()
    else:
        assert "Araç seti: 2 görüntü" in sonuc.stdout
        assert sorted(p.name for p in (tmp_path / "arac-seti").iterdir()) == list(adlar)


@arac_gerekli
def test_olc_tablosu(ana, tmp_path):
    aday = tmp_path / "aday"
    _aday_klasoru(aday, "tiny-v1")
    betik = _adim(ana, "olc", "Ölçüm tablosu")["run"]
    sonuc = _calistir(betik, tmp_path, _ortam(tmp_path, VARYANT="tiny-v1"))
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    satirlar = (aday / "ozet-tiny-v1.md").read_text(encoding="utf-8").splitlines()
    assert satirlar[0] == "### tiny-v1"
    tablo = [s for s in satirlar if s.startswith("| tiny-v1-k")]
    assert len(tablo) == 3
    # görüntü, fk kutusu (fk_r'nin paydası), fk_r, fk_r bütün
    assert tablo[1].startswith("| tiny-v1-k1 | GEÇTİ | 50 | 94 | 0.612 | 0.500 |")
    baslik = next(s for s in satirlar if s.startswith("| Aday |")).split(" | ")
    assert {"fk kutusu", "fk_r bütün", "transpalet fk", "araç setinde fk"} <= set(baslik)
    assert len(baslik) == len(tablo[1].split(" | "))
    assert tablo[0].startswith("| tiny-v1-k0 | KALDI |") and tablo[0].endswith("| fk_r_en_az |")
    # ölçülmeyen metrik "-" yazılır, "0" değil
    assert "| - |" in tablo[0]


# Sahte gh: yalnız iş akışının kullandığı çağrılar. --jq süzgeci gerçek jq ile.
SAHTE_GH = r"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

kayit = Path(os.environ["SAHTE_GH"])
arg = sys.argv[1:]
with open(kayit / "cagrilar.jsonl", "a", encoding="utf-8") as dosya:
    dosya.write(json.dumps(arg) + "\n")


def yaz(belge):
    if "--jq" in arg:
        suzgec = arg[arg.index("--jq") + 1]
        sonuc = subprocess.run(
            ["jq", "-r", suzgec], input=json.dumps(belge), text=True, capture_output=True
        )
        sys.stdout.write(sonuc.stdout)
        sys.exit(sonuc.returncode)
    sys.stdout.write(json.dumps(belge))
    sys.exit(0)


if arg[0] == "api" and "/git/ref/tags/" in arg[1]:
    if (kayit / "etiket_var").exists():
        yaz({"ref": "refs/tags/x"})
    sys.stdout.write('{"message": "Not Found", "status": "404"}')
    sys.stderr.write("gh: Not Found (HTTP 404)\n")
    sys.exit(1)
if arg[0] == "api" and "/releases/tags/" in arg[1]:
    yaz({"assets": json.loads((kayit / "yayin.json").read_text(encoding="utf-8"))})
if arg[:2] == ["release", "view"]:
    sys.stderr.write("release not found\n")
    sys.exit(1)
if arg[:2] == ["release", "create"]:
    dosyalar = []
    for parca in arg[3:]:
        if parca.startswith("--"):
            break
        dosyalar.append(Path(parca))
    varliklar = []
    for yol in dosyalar:
        ozet = "sha256:" + hashlib.sha256(yol.read_bytes()).hexdigest()
        if (kayit / "bozuk").exists() and yol.suffix == ".onnx":
            ozet = "sha256:" + "0" * 64
        if (kayit / "ozetsiz").exists():
            ozet = None
        varliklar.append({"name": yol.name, "digest": ozet})
    (kayit / "yayin.json").write_text(json.dumps(varliklar), encoding="utf-8")
    sys.exit(0)
sys.stderr.write(f"sahte gh bu çağrıyı bilmiyor: {arg}\n")
sys.exit(3)
"""


def _yayin_ortami(tmp_path: Path, mod: str, varyantlar: list[str]) -> dict[str, str]:
    ortam = _ortam(
        tmp_path,
        SAHTE_GH=str(tmp_path / "gh-kayit"),
        GH_TOKEN="sahte",
        GH_REPO="ornek/dalsan",
        MOD=mod,
        ETIKET="forklift-r7",
        VARYANTLAR=json.dumps(varyantlar),
        ISTEK=json.dumps({"not": "Deneme isteği"}),
    )
    (tmp_path / "gh-kayit").mkdir()
    betik = tmp_path / "sahte_gh.py"
    betik.write_text(SAHTE_GH, encoding="utf-8")
    gh = tmp_path / "bin" / "gh"
    gh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{betik}" "$@"\n', encoding="utf-8")
    gh.chmod(0o755)
    return ortam


def _yayinla_adimlari(ana: dict, tmp_path: Path, ortam: dict[str, str], *adlar: str) -> list:
    sonuclar = []
    for ad in adlar:
        sonuc = _calistir(_adim(ana, "yayinla", ad)["run"], tmp_path, ortam)
        sonuclar.append(sonuc)
        if sonuc.returncode != 0:
            break
    return sonuclar


def _gh_cagrilari(ortam: dict[str, str]) -> list[list[str]]:
    yol = Path(ortam["SAHTE_GH"]) / "cagrilar.jsonl"
    return [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines()]


YAYIN_ADIMLARI = (
    "Adayları denetle ve topla",
    "Sürüm notları",
    "Etiket boş mu",
    "Ön sürümü yayınla",
)


@arac_gerekli
def test_yayinla_tam_kipte_tek_on_surum(ana, tmp_path):
    """Bir varyant ölçülemedi (tiny-v2): ötekiler yayımlanır, notlarda "Eksik" yazar."""
    _aday_klasoru(tmp_path / "adaylar", "tiny-v1")
    _aday_klasoru(tmp_path / "adaylar", "s-v1")
    (tmp_path / "adaylar" / "ozet-tiny-v1.md").write_text("### tiny-v1\n", encoding="utf-8")
    ortam = _yayin_ortami(tmp_path, "tam", ["tiny-v1", "tiny-v2", "s-v1"])
    sonuclar = _yayinla_adimlari(ana, tmp_path, ortam, *YAYIN_ADIMLARI)
    assert [s.returncode for s in sonuclar] == [0, 0, 0, 0], sonuclar[-1].stdout
    assert "::warning title=Eksik aday::tiny-v2" in sonuclar[0].stdout
    beklenen = ["SHA256SUMS"]
    for varyant in ("tiny-v1", "s-v1"):
        for k in range(3):
            beklenen += [f"{varyant}-k{k}.onnx", f"{varyant}-k{k}.olcum.json"]
    assert sorted(p.name for p in (tmp_path / "yayin").iterdir()) == sorted(beklenen)
    notlar = (tmp_path / "notlar.md").read_text(encoding="utf-8")
    assert notlar.startswith("# NextGen AI Forklift adayları (r7)")
    assert "- İstek notu: Deneme isteği" in notlar
    assert "### tiny-v1" in notlar
    assert "**Eksik:** tiny-v2" in notlar
    olusturma = [c for c in _gh_cagrilari(ortam) if c[:2] == ["release", "create"]]
    assert len(olusturma) == 1
    cagri = olusturma[0]
    assert cagri[2] == "forklift-r7"
    assert "--prerelease" in cagri
    assert cagri[cagri.index("--target") + 1] == ortam["GITHUB_SHA"]
    assert cagri[cagri.index("--title") + 1] == "NextGen AI Forklift adayları r7"
    assert "::notice title=Ön sürüm yayınlandı::" in sonuclar[-1].stdout


@arac_gerekli
def test_yeniden_calistirilan_kosunun_basligi_etiketle_ayni(ana, tmp_path):
    """Yeniden çalıştırılan tam koşunun etiketi -dN alır; başlık ve notlar da onu
    yazar (eskiden yalnız çalıştırma numarası: yayın etiketiyle ayrışıyordu)."""
    _aday_klasoru(tmp_path / "adaylar", "tiny-v1")
    ortam = _yayin_ortami(tmp_path, "tam", ["tiny-v1"])
    ortam["ETIKET"] = "forklift-r7-d2"
    sonuclar = _yayinla_adimlari(ana, tmp_path, ortam, *YAYIN_ADIMLARI)
    assert [s.returncode for s in sonuclar] == [0, 0, 0, 0], sonuclar[-1].stdout
    notlar = (tmp_path / "notlar.md").read_text(encoding="utf-8")
    assert notlar.startswith("# NextGen AI Forklift adayları (r7-d2)")
    assert "varsayılan model yapılmaz" in notlar
    cagri = next(c for c in _gh_cagrilari(ortam) if c[:2] == ["release", "create"])
    assert cagri[2] == "forklift-r7-d2"
    assert cagri[cagri.index("--title") + 1] == "NextGen AI Forklift adayları r7-d2"


@arac_gerekli
def test_yayinla_duman_kipinde_yayimlamaz(ana, tmp_path):
    _aday_klasoru(tmp_path / "adaylar", "tiny-v1")
    _aday_klasoru(tmp_path / "adaylar", "tiny-v2")
    ortam = _yayin_ortami(tmp_path, "duman", DUMAN_VARYANTLARI)
    adimlar = ana["jobs"]["yayinla"]["steps"]
    # İş akışının kendi koşullarıyla: duman kipinde "Ön sürümü yayınla" atlanır
    for adim in adimlar:
        if "run" not in adim:
            continue
        if adim.get("if") == "env.MOD == 'tam'":
            continue
        sonuc = _calistir(adim["run"], tmp_path, ortam)
        assert sonuc.returncode == 0, (adim["name"], sonuc.stdout + sonuc.stderr)
    assert not [c for c in _gh_cagrilari(ortam) if c[:2] == ["release", "create"]]
    assert "::notice title=Duman kipi::" in sonuc.stdout


@arac_gerekli
def test_yayinla_var_olan_etiketin_ustune_yazmaz(ana, tmp_path):
    _aday_klasoru(tmp_path / "adaylar", "tiny-v1")
    ortam = _yayin_ortami(tmp_path, "tam", ["tiny-v1"])
    (Path(ortam["SAHTE_GH"]) / "etiket_var").touch()
    sonuclar = _yayinla_adimlari(ana, tmp_path, ortam, *YAYIN_ADIMLARI)
    assert [s.returncode for s in sonuclar[:2]] == [0, 0]
    assert sonuclar[2].returncode != 0
    assert "::error title=Etiket zaten var::forklift-r7" in sonuclar[2].stdout
    assert len(sonuclar) == 3
    assert not [c for c in _gh_cagrilari(ortam) if c[:2] == ["release", "create"]]


@arac_gerekli
def test_yayinla_hic_aday_yoksa_durur(ana, tmp_path):
    (tmp_path / "adaylar").mkdir()
    ortam = _yayin_ortami(tmp_path, "tam", ["tiny-v1"])
    sonuclar = _yayinla_adimlari(ana, tmp_path, ortam, *YAYIN_ADIMLARI)
    assert len(sonuclar) == 1 and sonuclar[0].returncode != 0
    assert "::error title=Yayımlanacak aday yok::" in sonuclar[0].stdout


@arac_gerekli
@pytest.mark.parametrize("sizan", ["../gizli.onnx", "tiny-v1-k3.onnx", "notlar.md"])
def test_yayinla_beklenmeyen_dosyayi_yayimlamaz(ana, tmp_path, sizan):
    """Özet listesi üçüncü parti kod çalıştıran bir işten gelir: listede yalnız
    varyantın üç adayı ve üç ölçümü olabilir."""
    adaylar = tmp_path / "adaylar"
    _aday_klasoru(adaylar, "tiny-v1")
    hedef = (adaylar / sizan).resolve()
    hedef.write_bytes(b"sizan dosya")
    liste = adaylar / "SHA256SUMS-tiny-v1"
    satirlar = liste.read_text(encoding="utf-8").splitlines()
    satirlar[0] = f"{_ozet(hedef)}  {sizan}"
    liste.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    ortam = _yayin_ortami(tmp_path, "tam", ["tiny-v1"])
    sonuclar = _yayinla_adimlari(ana, tmp_path, ortam, *YAYIN_ADIMLARI)
    assert len(sonuclar) == 1 and sonuclar[0].returncode != 0
    assert f"::error title=Beklenmeyen dosya::SHA256SUMS-tiny-v1 içinde: {sizan}" in (
        sonuclar[0].stdout
    )
    assert not (tmp_path / "yayin" / Path(sizan).name).exists()


@arac_gerekli
def test_yayinla_bozuk_aday_yayimlanmaz(ana, tmp_path):
    _aday_klasoru(tmp_path / "adaylar", "tiny-v1")
    (tmp_path / "adaylar" / "tiny-v1-k2.onnx").write_bytes(b"yolda bozuldu")
    ortam = _yayin_ortami(tmp_path, "tam", ["tiny-v1"])
    sonuclar = _yayinla_adimlari(ana, tmp_path, ortam, *YAYIN_ADIMLARI)
    assert len(sonuclar) == 1 and sonuclar[0].returncode != 0
    assert not (Path(ortam["SAHTE_GH"]) / "cagrilar.jsonl").exists()


@arac_gerekli
@pytest.mark.parametrize(("durum", "basarili"), [("bozuk", False), ("ozetsiz", True)])
def test_yayinla_yayindaki_dosyalari_dogrular(ana, tmp_path, durum, basarili):
    _aday_klasoru(tmp_path / "adaylar", "tiny-v1")
    ortam = _yayin_ortami(tmp_path, "tam", ["tiny-v1"])
    (Path(ortam["SAHTE_GH"]) / durum).touch()
    sonuclar = _yayinla_adimlari(ana, tmp_path, ortam, *YAYIN_ADIMLARI)
    assert len(sonuclar) == 4
    if basarili:
        assert sonuclar[-1].returncode == 0, sonuclar[-1].stdout + sonuclar[-1].stderr
        assert "::warning title=Özet yok::" in sonuclar[-1].stdout
    else:
        assert sonuclar[-1].returncode != 0
        assert "::error title=Yayındaki dosya farklı::" in sonuclar[-1].stdout


def _isler(yayinla: str = "success") -> str:
    sonuclar = {ad: "success" for ad in ("plan", "veri", "bacak1", "bacak2", "bacak3")}
    sonuclar.update(olc="failure", yayinla=yayinla)
    return json.dumps({ad: {"result": s, "outputs": {}} for ad, s in sonuclar.items()})


@arac_gerekli
def test_ozet_sonuclari_gunlugun_sonuna_yazar(ana, tmp_path):
    _aday_klasoru(tmp_path / "adaylar", "tiny-v1")
    (tmp_path / "adaylar" / "ozet-tiny-v1.md").write_text("### tiny-v1\n", encoding="utf-8")
    ortam = _ortam(tmp_path, ISLER=_isler(), MOD="tam", ETIKET="forklift-r7")
    sonuc = _calistir(_adim(ana, "ozet", "Sonuç")["run"], tmp_path, ortam)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    satirlar = sonuc.stdout.splitlines()
    basla = satirlar.index("===== FORKLIFT-SONUC-BASLA =====")
    assert satirlar[-1] == "===== FORKLIFT-SONUC-BITTI ====="
    blok = satirlar[basla + 1 : -1]
    calistirma = json.loads(blok[0].removeprefix("FORKLIFT_CALISTIRMA "))
    assert calistirma["mod"] == "tam" and calistirma["isler"]["olc"] == "failure"
    assert calistirma["yayin"] == "https://github.com/ornek/dalsan/releases/tag/forklift-r7"
    olcumler = [json.loads(s.removeprefix("OLCUM_JSON ")) for s in blok[1:]]
    assert [o["etiket"] for o in olcumler] == ["tiny-v1-k0", "tiny-v1-k1", "tiny-v1-k2"]
    notlar = [s for s in satirlar if s.startswith("::notice title=Forklift olcumu::")]
    assert len(notlar) == 1
    kisa = json.loads(notlar[0].split("::", 2)[2].replace("%25", "%"))
    assert kisa["adaylar"]["tiny-v1-k1"]["gecti"] is True
    assert kisa["adaylar"]["tiny-v1-k0"]["fk_r"] == 0.61234
    aday = kisa["adaylar"]["tiny-v1-k0"]
    assert (aday["fk_gercek"], aday["fk_r_tum"], aday["pt_fk"]) == (94, 0.5, 0.25)
    assert aday["arac_seti_tr_fk"] == 0.0
    ozet = Path(ortam["GITHUB_STEP_SUMMARY"]).read_text(encoding="utf-8")
    assert "| olc | failure |" in ozet and "### tiny-v1" in ozet


@arac_gerekli
def test_ozet_olcum_yoksa_da_bloku_yazar(ana, tmp_path):
    """Plan düştüyse bile (kip ve etiket boş) blok yazılır; okuyan boşuna beklemez."""
    ortam = _ortam(tmp_path, ISLER=_isler("skipped"), MOD="", ETIKET="")
    sonuc = _calistir(_adim(ana, "ozet", "Sonuç")["run"], tmp_path, ortam)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr
    satirlar = sonuc.stdout.splitlines()
    basla = satirlar.index("===== FORKLIFT-SONUC-BASLA =====")
    assert satirlar[basla + 2].startswith("OLCUM_JSON_YOK")
    assert satirlar[-1] == "===== FORKLIFT-SONUC-BITTI ====="

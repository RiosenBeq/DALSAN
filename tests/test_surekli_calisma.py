"""Program siz kapatana kadar açık kalır (masaustu/surekli_calisma.py).

Operatör, 24.09.2026: "uygulamayı bir kere açınca ben kapatana kadar otomatik
açılmayı ve bu tarz senaryoları düşünüp buna göre kodla". Senaryolar:

- Kullanıcı paneli kapatır (0): gözetmen de kapanır, Windows açılış kaydı silinir.
- Bekçi takılan analizi kapatır (70), sunucu beklenmedik şekilde durur (71) ya
  da panel çöker: gözetmen paneli yeniden açar; saatte en çok 3 kez, sonra son
  bir kez bekçi yalnız uyaracak şekilde.
- Windows kapanırken panel kapanır: yeniden açılmaz.
- Bilgisayar yeniden açılır: program oturum açılınca kendiliğinden başlar
  (HKCU Run); Görev Yöneticisi'nde kapatıldıysa panel söyler.
- Program zaten açıkken yeniden açılır: ikinci kopya açılmaz, açık olan öne gelir.
- Sistem çalışırken Windows uyumaz.

Windows çağrıları sahte nesnelerle sınanır; gerçeğini paketin üretim işi
(uygulama-uret.yml, "Uygulamayı baştan sona çalıştır") çalıştırır.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
MODUL = KOK / "masaustu" / "surekli_calisma.py"
BASLATICI = KOK / "masaustu" / "dalsan_launcher.py"
KANCA = KOK / "paketleme" / "acilis_kancasi.py"


def _yukle(ad: str, yol: Path):
    sys.modules.pop(ad, None)
    tanim = importlib.util.spec_from_file_location(ad, yol)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


@pytest.fixture
def sc():
    return _yukle("surekli_calisma_test", MODUL)


# --------------------------------------------------------------- sahteler


class _SahteSurec:
    def __init__(self, kod: int) -> None:
        self._kod = kod

    def wait(self) -> int:
        return self._kod


class _Baslatici:
    """Sırayla verilen çıkış kodlarıyla biten paneller açar; çağrıları kaydeder."""

    def __init__(self, kodlar: list[int]) -> None:
        self._kodlar = list(kodlar)
        self.cagrilar: list[tuple[list[str], dict]] = []

    def __call__(self, komut, env):
        self.cagrilar.append((komut, env))
        return _SahteSurec(self._kodlar.pop(0))


class _SahteAnahtar:
    def __init__(self, depo: dict, yol: str) -> None:
        self.depo, self.yol = depo, yol

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _SahteKayit:
    """winreg'in kullanılan parçası: HKCU altında anahtar -> {değer: veri}."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.depo: dict[str, dict] = {}

    def CreateKeyEx(self, kok, yol, _ayrilmis, _erisim):  # noqa: N802 - winreg adı
        self.depo.setdefault(yol, {})
        return _SahteAnahtar(self.depo, yol)

    def OpenKey(self, kok, yol, _ayrilmis=0, _erisim=0):  # noqa: N802
        if yol not in self.depo:
            raise FileNotFoundError(yol)
        return _SahteAnahtar(self.depo, yol)

    def SetValueEx(self, anahtar, ad, _ayrilmis, _tur, veri):  # noqa: N802
        anahtar.depo[anahtar.yol][ad] = veri

    def DeleteValue(self, anahtar, ad):  # noqa: N802
        if ad not in anahtar.depo[anahtar.yol]:
            raise FileNotFoundError(ad)
        del anahtar.depo[anahtar.yol][ad]

    def QueryValueEx(self, anahtar, ad):  # noqa: N802
        if ad not in anahtar.depo[anahtar.yol]:
            raise FileNotFoundError(ad)
        return anahtar.depo[anahtar.yol][ad], 1


class _SahteApi:
    def __init__(self, *, muteks_var=False, pencere=0, one_gelir=True, durum_sonucu=1) -> None:
        self.muteks_var = muteks_var
        self.pencere = pencere
        self.one_gelir = one_gelir
        self.durum_sonucu = durum_sonucu
        self.kapatilan: list[int] = []
        self.bayraklar: list[int] = []
        self.kutular: list[str] = []
        self.one_getirilen: list[int] = []

    def muteks_olustur(self, ad):
        return 42, (183 if self.muteks_var else 0)

    def tutamac_kapat(self, tutamac):
        self.kapatilan.append(tutamac)

    def pencere_bul(self, baslik):
        return self.pencere

    def one_getir(self, pencere):
        self.one_getirilen.append(pencere)
        return self.one_gelir

    def calisma_durumu(self, bayrak):
        self.bayraklar.append(bayrak)
        return self.durum_sonucu

    def oturum_kapaniyor(self):
        return False

    def bilgi_kutusu(self, metin, baslik):
        self.kutular.append(metin)


def _calistir(sc, kodlar, *, argumanlar=(), oturum_kapaniyor=lambda: False, saat=None):
    baslat = _Baslatici(kodlar)
    beklemeler: list[float] = []
    satirlar: list[str] = []
    kayit = _SahteKayit()
    donus = sc.gozetmeni_calistir(
        r"C:\Program Files\NextGen Detector\NextGen Detector.exe",
        list(argumanlar),
        baslat=baslat,
        saat=saat or (lambda: 100.0),
        uyu=beklemeler.append,
        oturum_kapaniyor=oturum_kapaniyor,
        yaz=satirlar.append,
        kayit=kayit,
    )
    return donus, baslat.cagrilar, beklemeler, satirlar, kayit


# --------------------------------------------------------------- gözetmen


def test_gozetmen_yalniz_paketlenmis_windows_programinda(sc, monkeypatch):
    monkeypatch.setattr(sc, "IS_WINDOWS", True)
    assert sc.gozetmen_gerekli_mi([], paketlenmis=True)
    assert sc.gozetmen_gerekli_mi(["--kendiliginden"], paketlenmis=True)
    assert not sc.gozetmen_gerekli_mi(["--panel"], paketlenmis=True), "panel kopyası"
    assert not sc.gozetmen_gerekli_mi([], paketlenmis=False), "Başlat betiği"
    monkeypatch.setattr(sc, "IS_WINDOWS", False)
    assert not sc.gozetmen_gerekli_mi([], paketlenmis=True), "Mac uygulaması"


def test_yeniden_acma_karari(sc):
    gecmis: list[float] = []
    assert sc.yeniden_acma_karari(0, gecmis, 0.0) == "bitir"
    assert [sc.yeniden_acma_karari(k, gecmis, t) for k, t in ((70, 0), (1, 10), (71, 20))] == [
        "ac",
        "ac",
        "ac",
    ]
    assert sc.yeniden_acma_karari(70, gecmis, 30.0) == "sinir"
    # Bir saat geçince eski açılışlar sayılmaz.
    assert sc.yeniden_acma_karari(70, gecmis, 3700.0) == "ac"


def test_kullanici_kapatinca_gozetmen_de_kapanir(sc):
    donus, cagrilar, beklemeler, _, kayit = _calistir(sc, [0])
    assert donus == 0
    assert len(cagrilar) == 1 and beklemeler == []
    komut, ortam = cagrilar[0]
    assert komut[1:] == ["--panel"]
    assert ortam["DALSAN_GOZETMEN"] == "1"
    assert ortam["DALSAN_ONCEKI_KAPANIS"] == ""
    # Panel PyInstaller'ın "yardımcı alt süreç"i değil, bağımsız bir program olarak kalkar.
    assert ortam["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    # Açılışta Windows'un "oturum açılınca başlat" listesine yazıldı.
    deger = kayit.depo[sc.RUN_ANAHTARI][sc.RUN_DEGERI]
    assert deger == '"C:\\Program Files\\NextGen Detector\\NextGen Detector.exe" --kendiliginden'


def test_bekci_kapatinca_panel_yeniden_acilir(sc):
    donus, cagrilar, beklemeler, satirlar, _ = _calistir(sc, [70, 0])
    assert donus == 0
    assert len(cagrilar) == 2
    assert cagrilar[1][1]["DALSAN_ONCEKI_KAPANIS"] == "bekci"
    assert cagrilar[1][1]["DALSAN_GOZETMEN"] == "1"
    assert beklemeler == [sc.YENIDEN_ACMA_BEKLEMESI_SN]
    assert any("yeniden açılıyor" in s for s in satirlar)


def test_cokme_ve_sunucu_durmasi_da_yeniden_acar(sc):
    _, cagrilar, _, _, _ = _calistir(sc, [1, 71, 0])
    assert [c[1]["DALSAN_ONCEKI_KAPANIS"] for c in cagrilar] == ["", "cokme:1", "sunucu"]


def test_sinir_dolunca_son_kez_bekci_yalniz_uyaracak_sekilde_acilir(sc):
    donus, cagrilar, _, satirlar, _ = _calistir(sc, [70, 70, 70, 70, 5, 0])
    assert len(cagrilar) == 5, "son panel kapanınca bir daha açılmaz"
    assert [c[1]["DALSAN_GOZETMEN"] for c in cagrilar] == ["1", "1", "1", "1", "0"]
    assert cagrilar[-1][1]["DALSAN_ONCEKI_KAPANIS"] == "sinir"
    assert donus == 5
    assert any("sınır" in s for s in satirlar)


def test_windows_kapanirken_panel_yeniden_acilmaz(sc):
    donus, cagrilar, beklemeler, satirlar, _ = _calistir(sc, [1], oturum_kapaniyor=lambda: True)
    assert donus == 0 and len(cagrilar) == 1 and beklemeler == []
    assert any("Windows kapanıyor" in s for s in satirlar)


def test_beklerken_windows_kapanmaya_baslarsa_acilmaz(sc):
    sorular = iter([False, True])
    donus, cagrilar, beklemeler, _, _ = _calistir(sc, [70], oturum_kapaniyor=lambda: next(sorular))
    assert donus == 0 and len(cagrilar) == 1 and beklemeler == [sc.YENIDEN_ACMA_BEKLEMESI_SN]


def test_windows_acilisinda_baslayinca_panele_bildirilir(sc):
    _, cagrilar, _, _, _ = _calistir(sc, [0], argumanlar=["--kendiliginden"])
    assert cagrilar[0][1]["DALSAN_ONCEKI_KAPANIS"] == "kendiliginden"


def test_panel_acilamazsa_gozetmen_sebebini_yazip_biter(sc):
    satirlar: list[str] = []

    def acilmayan(komut, env):
        raise OSError("erişim engellendi")

    donus = sc.gozetmeni_calistir(
        "x.exe",
        [],
        baslat=acilmayan,
        yaz=satirlar.append,
        kayit=_SahteKayit(),
        oturum_kapaniyor=lambda: False,
    )
    assert donus == 1
    assert any("erişim engellendi" in s for s in satirlar)


def test_acilis_notlari(sc):
    assert sc.acilis_notu("") == []
    assert "kendiliğinden başladı" in sc.acilis_notu("kendiliginden")[0]
    assert sc.acilis_notu("bekci")[0].startswith("[!] Analiz takıldığı")
    assert "çıkış kodu 3" in sc.acilis_notu("cokme:3")[0]
    assert sc.acilis_notu("sunucu")[0].startswith("[!] Sistem beklenmedik")
    assert sc.acilis_notu("sinir")[0].startswith("[HATA]")


# --------------------------------------------------------------- Windows açılışı


def test_acilis_kaydi_yazilir_okunur_ve_silinir(sc):
    kayit = _SahteKayit()
    program = r"D:\NextGen Detector\NextGen Detector.exe"
    assert sc.acilis_durumu(program, kayit) == "yok"
    assert sc.acilisa_ekle(program, kayit) is None
    assert sc.acilis_durumu(program, kayit) == "kayitli"
    assert sc.acilis_durumu(program.upper(), kayit) == "kayitli", "Windows yolları büyük/küçük"
    assert sc.acilis_durumu(r"E:\baska\NextGen Detector.exe", kayit) == "baska"
    assert sc.acilistan_cikar(kayit) is None
    assert sc.acilis_durumu(program, kayit) == "yok"
    assert sc.acilistan_cikar(kayit) is None, "zaten yoksa hata değil"


def test_gorev_yoneticisinde_kapatilan_baslangic_taninir(sc):
    kayit = _SahteKayit()
    program = r"C:\NextGen Detector\NextGen Detector.exe"
    sc.acilisa_ekle(program, kayit)
    kayit.depo[sc.BASLANGIC_ONAYI_ANAHTARI] = {sc.RUN_DEGERI: bytes([3]) + bytes(11)}
    assert sc.acilis_durumu(program, kayit) == "kapatilmis"
    kayit.depo[sc.BASLANGIC_ONAYI_ANAHTARI][sc.RUN_DEGERI] = bytes([2]) + bytes(11)
    assert sc.acilis_durumu(program, kayit) == "kayitli"


def test_kayit_defteri_yazilamazsa_sebep_doner(sc):
    class _Yasak(_SahteKayit):
        def CreateKeyEx(self, *a):  # noqa: N802
            raise PermissionError("erişim reddedildi")

    assert "erişim reddedildi" in sc.acilisa_ekle("x.exe", _Yasak())


def test_windows_disinda_kayit_defterine_dokunulmaz(sc, monkeypatch):
    monkeypatch.setattr(sc, "IS_WINDOWS", False)
    assert sc.acilisa_ekle("x") is None
    assert sc.acilistan_cikar() is None
    assert sc.acilis_durumu("x") == "desteklenmiyor"


# --------------------------------------------------------------- uyku, tek kopya


def test_uyku_engeli_bayraklari(sc):
    api = _SahteApi()
    assert sc.uyku_engeli(True, api) is True
    assert sc.uyku_engeli(False, api) is True
    assert api.bayraklar == [0x80000001, 0x80000000]
    assert sc.uyku_engeli(True, _SahteApi(durum_sonucu=0)) is False, "Windows reddetti"


def test_windows_disinda_uyku_engeli_yok(sc, monkeypatch):
    monkeypatch.setattr(sc, "IS_WINDOWS", False)
    assert sc.uyku_engeli(True) is False


def test_tek_kopya(sc):
    assert sc.tek_kopya_mi(_SahteApi()) is True
    ikinci = _SahteApi(muteks_var=True)
    assert sc.tek_kopya_mi(ikinci) is False
    assert ikinci.kapatilan == [42], "ikinci kopya muteksini bırakır"


def test_acik_panel_one_gelir_bulunamazsa_soylenir(sc):
    api = _SahteApi(pencere=7)
    assert sc.acik_paneli_one_getir(api) is True
    assert api.one_getirilen == [7] and api.kutular == []
    bulunamayan = _SahteApi(pencere=0)
    assert sc.acik_paneli_one_getir(bulunamayan) is False
    assert "zaten çalışıyor" in bulunamayan.kutular[0]


# --------------------------------------------------------------- günlük


def test_gunluk_yazilir_ve_sinirda_doner(sc, tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "GUNLUK_SINIRI", 200)
    yaz = sc.gunluk_yazici(tmp_path)
    for i in range(20):
        yaz(f"satır {i} - Türkçe ğüşiöç")
    dosya = tmp_path / sc.GUNLUK_ADI
    assert dosya.exists() and (tmp_path / (sc.GUNLUK_ADI + ".1")).exists()
    assert dosya.stat().st_size <= 400
    assert "satır 19" in dosya.read_text(encoding="utf-8")


# --------------------------------------------------------------- tutarlılık


def test_sabitler_backend_ve_panelle_ayni(sc):
    from app import kaynaklar
    from app.analiz import bekci

    assert sc.GOZETMEN_DEGISKENI == kaynaklar.GOZETMEN_DEGISKENI
    assert sc.BEKCI_KODU == bekci.YENIDEN_BASLATMA_KODU
    assert sc.RUN_DEGERI == kaynaklar.UYGULAMA_ADI
    assert f'"{sc.PANEL_BASLIGI}"' in BASLATICI.read_text(encoding="utf-8")
    assert _yukle("acilis_kancasi_test", KANCA).GOZETMEN_DEGISKENI == sc.GOZETMEN_DEGISKENI


def test_pakete_alinir():
    ortak = (KOK / "paketleme" / "paketleme_ortak.py").read_text(encoding="utf-8")
    assert '"surekli_calisma"' in ortak


def _fonksiyon(agac, ad):
    return next(d for d in ast.walk(agac) if isinstance(d, ast.FunctionDef) and d.name == ad)


def _cagrilar(dugum) -> set[str]:
    adlar = set()
    for c in ast.walk(dugum):
        if isinstance(c, ast.Call):
            if isinstance(c.func, ast.Name):
                adlar.add(c.func.id)
            elif isinstance(c.func, ast.Attribute):
                adlar.add(c.func.attr)
    return adlar


def test_panel_baglantilari():
    agac = ast.parse(BASLATICI.read_text(encoding="utf-8"))
    # Kapatma onaylanınca Windows açılış kaydı silinir.
    kapanis = _cagrilar(_fonksiyon(agac, "kapanirken"))
    assert {"askyesno", "acilistan_cikar", "sistemi_durdur"} <= kapanis
    # Sistem çalışırken uyku engellenir.
    assert "uyku_engeli" in _cagrilar(_fonksiyon(agac, "durumu_yenile"))
    # Gözetmen önce tek kopyaya bakar.
    assert {"tek_kopya_mi", "acik_paneli_one_getir", "gozetmeni_calistir"} <= _cagrilar(
        _fonksiyon(agac, "gozetmeni_calistir")
    )


def test_pencere_sureci_gozetmenden_once_ayrilir():
    """İzleme penceresi kopyası (--izleme-penceresi) gözetmen sanılırsa her
    pencere yeni bir gözetmen ve panel açardı."""
    metin = BASLATICI.read_text(encoding="utf-8")
    ana = metin[metin.index('if __name__ == "__main__":') :]
    assert (
        ana.index("pencere_sureci_mi")
        < ana.index("gozetmen_sureci_mi")
        < ana.index("arayuzu_baslat")
    )


# --------------------------------------------------------------- açılış kancası


def test_gozetimli_panelde_hata_penceresi_acilmaz(monkeypatch, tmp_path):
    """Başında kimse olmayan bilgisayarda kapatılmayı bekleyen bir hata penceresi
    süreci açık tutar ve gözetmen onu yeniden açamazdı."""
    kanca = _yukle("acilis_kancasi_test2", KANCA)
    gosterilen: list = []
    monkeypatch.setattr(kanca, "pencerede_goster", gosterilen.append)
    monkeypatch.setattr(kanca, "hatayi_yaz", lambda metin, kok=None: tmp_path / "x.log")

    monkeypatch.setenv("DALSAN_GOZETMEN", "1")
    kanca.hata_yakalayici(RuntimeError, RuntimeError("çöktü"), None)
    assert gosterilen == []

    monkeypatch.setenv("DALSAN_GOZETMEN", "0")
    kanca.hata_yakalayici(RuntimeError, RuntimeError("çöktü"), None)
    assert gosterilen == [tmp_path / "x.log"]

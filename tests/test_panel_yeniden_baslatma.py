"""Başlat betiğiyle kurulan sistemde bekçinin yeniden başlatma isteği.

BEKCI_TEPKISI=yeniden_baslat iken takılan analiz süreci 70 koduyla kapatır.
Docker ve systemd süreci yeniden açar. Başlat betiğiyle kurulan sistemde
sunucu Kontrol Paneli'nin alt sürecidir ve eskiden kimse yeniden açmıyordu:
ayar "yeniden başlat" derken sistem tamamen duruyordu (belge denetimi
24.09.2026; operatör: "Olan problemleri de çöz").
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

from app.analiz import bekci

KOK = Path(__file__).resolve().parents[1]
BASLATICI = KOK / "masaustu" / "dalsan_launcher.py"


def _panel():
    sys.modules.pop("panel_bekci", None)
    tanim = importlib.util.spec_from_file_location("panel_bekci", BASLATICI)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


def test_cikis_kodu_bekciyle_ayni():
    assert _panel().BEKCI_YENIDEN_BASLATMA_KODU == bekci.YENIDEN_BASLATMA_KODU


def test_yalniz_bekci_istegi_yeniden_baslatir():
    panel = _panel()
    gecmis: list[float] = []
    assert panel.surec_kapaninca(0, gecmis, 100.0) == ""  # olağan kapanış
    assert panel.surec_kapaninca(-15, gecmis, 100.0) == ""  # "Durdur" (SIGTERM)
    assert panel.surec_kapaninca(1, gecmis, 100.0) == ""  # çökme
    assert gecmis == []
    assert panel.surec_kapaninca(70, gecmis, 100.0) == "baslat"


def test_bir_saatte_ucten_fazla_yeniden_baslatmaz():
    """Analiz her açılışta yine takılıyorsa panel döngüye girmez."""
    panel = _panel()
    gecmis: list[float] = []
    kararlar = [panel.surec_kapaninca(70, gecmis, t) for t in (0.0, 100.0, 200.0, 300.0)]
    assert kararlar == ["baslat", "baslat", "baslat", "sinir"]
    # Bir saat geçince eski başlatmalar sayılmaz
    assert panel.surec_kapaninca(70, gecmis, 3700.0) == "baslat"


def test_cikti_okuyucu_kapaninca_karar_verir():
    """Karar, sunucunun çıktısını okuyan iş parçacığının sonunda verilir:
    süreç kapanınca akış biter ve kod oradan okunur."""
    agac = ast.parse(BASLATICI.read_text(encoding="utf-8"))
    okuyucu = next(
        d for d in ast.walk(agac) if isinstance(d, ast.FunctionDef) and d.name == "ciktiyi_oku"
    )
    cagrilar = {
        c.func.id
        for c in ast.walk(okuyucu)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert {"surec_kapaninca", "alt_surecte_baslat"} <= cagrilar


def test_gozetmen_degiskeninin_adi_backendle_ayni():
    from app import kaynaklar

    assert _panel().GOZETMEN_DEGISKENI == kaynaklar.GOZETMEN_DEGISKENI


def test_panel_alt_surece_yeniden_acacagini_bildirir():
    """Bekçi ancak süreci yeniden açan biri varken çıkar (kaynaklar.yeniden_acan_var_mi).
    Panel bunu alt sürecin ortamına yazmazsa "yeniden başlat" ayarı Başlat
    betiğiyle kurulan sistemde sessizce "yalnız uyar"a dönerdi."""
    agac = ast.parse(BASLATICI.read_text(encoding="utf-8"))
    baslatici = next(
        d
        for d in ast.walk(agac)
        if isinstance(d, ast.FunctionDef) and d.name == "alt_surecte_baslat"
    )
    popen = next(
        c
        for c in ast.walk(baslatici)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "Popen"
    )
    ortam = next(k.value for k in popen.keywords if k.arg == "env")
    assert "GOZETMEN_DEGISKENI" in ast.unparse(ortam)
    assert "'1'" in ast.unparse(ortam)

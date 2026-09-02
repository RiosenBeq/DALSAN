"""Tespit modelinin ekranda görünen adı: marka adı çıkar, dosya adı çıkmaz.

Kullanıcı yazılımcı değil; ana sayfada "yolox_tiny.onnx" yazması ne olduğunu
anlatmaz. Dosya adları, indirme adresleri ve .env anahtarları ise AYNEN
kalmalı — değişirse sistem modeli bulamaz. Bu testler tam olarak bu ayrımı
korur: görünen ad markalı, çalışan ad özgün.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.analiz.model_adi import MARKA, OZEL_MODEL_ADI, gorunen_model_adi
from app.analiz.model_indir import BILINEN_MODELLER

KOK = Path(__file__).resolve().parents[1]


def test_hizli_model_markali_gorunur():
    assert gorunen_model_adi("yolox_tiny.onnx") == "NextGen AI Hızlı"


def test_isabetli_model_markali_gorunur():
    assert gorunen_model_adi("yolox_s.onnx") == "NextGen AI İsabetli"


def test_taninmayan_dosya_ozel_model_sayilir():
    assert gorunen_model_adi("kendi_egittigim.onnx") == "NextGen AI (özel model)"
    assert gorunen_model_adi("") == OZEL_MODEL_ADI


def test_buyuk_harfli_dosya_adi_da_taninir():
    """Windows'ta dosya adı büyük harfle yazılabilir; ekranda yine ürün adı çıkar."""
    assert gorunen_model_adi("YOLOX_TINY.ONNX") == "NextGen AI Hızlı"
    assert gorunen_model_adi("  yolox_s.onnx  ") == "NextGen AI İsabetli"


def test_gorunen_adda_dosya_adi_sizmaz():
    """Hiçbir görünen ad teknik dosya adı ya da uzantı içermez."""
    adaylar = ["yolox_tiny.onnx", "yolox_s.onnx", "baska_model.onnx", "model.bin"]
    for dosya in adaylar:
        ad = gorunen_model_adi(dosya)
        assert ad.startswith(MARKA), f"{dosya} için ad markasız: {ad}"
        assert ".onnx" not in ad.lower()
        assert "yolox" not in ad.lower()


def test_indirilebilen_her_modelin_markali_adi_vardir():
    """Otomatik indirilen bir model eklenip görünen adı unutulursa test kırılır."""
    for dosya in BILINEN_MODELLER:
        assert gorunen_model_adi(dosya) != OZEL_MODEL_ADI, (
            f"{dosya} otomatik indiriliyor ama görünen adı tanımlı değil"
        )


def test_ana_sayfa_sablonu_dosya_adi_basmaz():
    """Şablon, model adını her zaman gorunen_model_adi'nden gelen değişkenden alır."""
    sablon = (KOK / "backend" / "app" / "web" / "templates" / "ana_sayfa.html").read_text(
        encoding="utf-8"
    )
    assert "{{ model_adi }}" in sablon
    assert ".onnx" not in sablon.lower()
    assert "yolox" not in sablon.lower()


def test_rotalar_model_adini_fonksiyondan_gecirir():
    """`model_dosyasi.name` doğrudan şablona verilirse ekranda dosya adı görünür."""
    kaynak = (KOK / "backend" / "app" / "web" / "rotalar.py").read_text(encoding="utf-8")
    ham = re.findall(r"^(?!.*gorunen_model_adi).*model_dosyasi\.name.*$", kaynak, re.MULTILINE)
    assert not ham, f"Ekrana ham dosya adı veren satır(lar) var: {ham}"


def test_ekrana_cikan_metinlerde_alt_bilesen_adi_gecmez():
    """Kullanıcıya gösterilen cümlelerde alt bileşen adı yer almaz.

    Atıf LICENSE-THIRD-PARTY'de ve kod yorumlarındadır (ADR-002). Burada
    denetlenen yalnızca ÇALIŞMA ZAMANI metinleri: docstring'ler, yorumlar ve
    teknik sabitler (indirme adresi, dosya adları) kapsam dışıdır — onlar
    ekrana değil, koda ve günlüğe aittir.
    """
    dosyalar = [
        KOK / "backend" / "app" / "analiz" / "model_indir.py",
        KOK / "backend" / "app" / "analiz" / "tespit.py",
        KOK / "backend" / "app" / "analiz" / "model_adi.py",
        KOK / "backend" / "app" / "web" / "rotalar.py",
    ]
    teknik_sabitler = {"_YAYIN_ADRESI", "BILINEN_MODELLER", "GORUNEN_ADLAR"}
    for dosya in dosyalar:
        agac = ast.parse(dosya.read_text(encoding="utf-8"))
        docstringler = {
            id(dugum.body[0].value)
            for dugum in ast.walk(agac)
            if isinstance(dugum, ast.Module | ast.ClassDef | ast.FunctionDef)
            and dugum.body
            and isinstance(dugum.body[0], ast.Expr)
            and isinstance(dugum.body[0].value, ast.Constant)
        }
        sabit_metinler = {
            id(alt)
            for atama in ast.walk(agac)
            if isinstance(atama, ast.Assign | ast.AnnAssign)
            for hedef in ([atama.target] if isinstance(atama, ast.AnnAssign) else atama.targets)
            if isinstance(hedef, ast.Name) and hedef.id in teknik_sabitler
            for alt in ast.walk(atama.value)
        }
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Constant) or not isinstance(dugum.value, str):
                continue
            if id(dugum) in docstringler or id(dugum) in sabit_metinler:
                continue
            assert "yolox" not in dugum.value.lower(), (
                f"{dosya.name}:{dugum.lineno} kullanıcıya çıkabilecek metinde alt bileşen adı: "
                f"{dugum.value!r}"
            )


def test_lisans_atfi_depo_kokunde_durur():
    """Marka adı ekranda görünürken alttaki yazılımın atfı kaybolmamalı."""
    lisans = (KOK / "LICENSE-THIRD-PARTY").read_text(encoding="utf-8")
    assert "YOLOX" in lisans
    assert "Megvii" in lisans
    assert "Apache" in lisans
    assert "ONNX Runtime" in lisans
    assert MARKA in lisans


def test_ana_sayfada_marka_adi_gorunur_dosya_adi_gorunmez(istemci, test_ayarlari):
    """Uçtan uca: sayfa açılınca "Tespit modeli" satırında ürün adı yazar.

    conftest geçici bir model dosyası (olmayan-model.onnx) verir; ekranda o ad
    DEĞİL, "NextGen AI (özel model)" görünmelidir.
    """
    metin = istemci.get("/").text
    assert MARKA in metin
    assert OZEL_MODEL_ADI in metin
    assert test_ayarlari.model_dosyasi.name not in metin
    assert "yolox" not in metin.lower()


def test_aktif_ayarlar_tablosunda_da_marka_adi_yazar(istemci):
    """Ayar tablosundaki 'Tespit modeli' satırı da ürün adını gösterir."""
    metin = istemci.get("/").text
    assert f"<tr><th>Tespit modeli</th><td>{OZEL_MODEL_ADI}</td></tr>" in metin


# ---- model hataları: ekranda ürün adı + yapılabilir adım, günlükte tam yol ----


def test_model_bulunamadi_hatasinda_ekranda_yol_yok(tmp_path):
    """Model kurulu değil mesajı: ekranda ürün adı, günlükte tam dosya yolu."""
    from app.analiz.tespit import ModelHatasi, Tespitci

    eksik = tmp_path / "models" / "yolox_tiny.onnx"
    with pytest.raises(ModelHatasi) as hata:
        Tespitci(eksik, "cpu")

    ekran = hata.value.kullanici_mesaji
    assert ekran.startswith(f"{MARKA} Hızlı"), f"Ekranda ürün adı yok: {ekran}"
    assert str(tmp_path) not in ekran, f"Ekrana dosya yolu sızmış: {ekran}"
    assert ".onnx" not in ekran.lower()
    assert "yolox" not in ekran.lower()
    assert "Kontrol Paneli" in ekran, "Kullanıcıya ne yapacağı söylenmeli"
    assert str(eksik) in hata.value.teknik_ayrinti, "Tam yol günlüğe yazılmalı"


def test_ozel_modelde_supervizor_markali_aciklama_verir(test_ayarlari):
    """Kendi modelini koyan kullanıcı da anlaşılır açıklamayı görür.

    Bu dal daha önce sessizce atlanıyordu; kullanıcı "dosya bulunamadı: /tam/yol"
    mesajıyla baş başa kalıyordu.
    """
    from app.analiz.model_indir import ModelIndirmeHatasi
    from app.analiz.supervizor import AnalizSupervizoru

    supervizor = AnalizSupervizoru(test_ayarlari)  # ayarlarda tanınmayan model
    with pytest.raises(ModelIndirmeHatasi) as hata:
        supervizor._modeli_hazirla()

    ekran = hata.value.kullanici_mesaji
    assert ekran.startswith(OZEL_MODEL_ADI), f"Ekranda ürün adı yok: {ekran}"
    assert str(test_ayarlari.model_dosyasi) not in ekran
    assert ".onnx" not in ekran.lower()
    assert str(test_ayarlari.model_dosyasi) in hata.value.teknik_ayrinti


def test_ekran_metinlerinde_terminal_komutu_yok():
    """CLAUDE.md §8: kullanıcıya terminal komutu değil, arayüz adımı söylenir.

    Docstring ve yorumlar kapsam dışıdır — betiğin adı kodda anılabilir,
    ekranda anılamaz.
    """
    dosyalar = [
        KOK / "backend" / "app" / "analiz" / "tespit.py",
        KOK / "backend" / "app" / "analiz" / "model_indir.py",
        KOK / "backend" / "app" / "analiz" / "supervizor.py",
    ]
    yasakli = ("indir.sh", "bash ", "pip install", "python -m")
    for dosya in dosyalar:
        agac = ast.parse(dosya.read_text(encoding="utf-8"))
        docstringler = {
            id(dugum.body[0].value)
            for dugum in ast.walk(agac)
            if isinstance(dugum, ast.Module | ast.ClassDef | ast.FunctionDef)
            and dugum.body
            and isinstance(dugum.body[0], ast.Expr)
            and isinstance(dugum.body[0].value, ast.Constant)
        }
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Constant) or not isinstance(dugum.value, str):
                continue
            if id(dugum) in docstringler:
                continue
            for komut in yasakli:
                assert komut not in dugum.value, (
                    f"{dosya.name}:{dugum.lineno} kullanıcıya çıkabilecek metinde "
                    f"terminal komutu: {dugum.value!r}"
                )

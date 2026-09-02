"""İki sessiz tuzağın nöbetçisi: tarayıcı önbelleği ve ekrana sızan teknik adres.

1. Önbellek kırıcı: JS/CSS değişip tarayıcı eskisini sunarsa, düzeltilmiş bir
   hata "hâlâ duruyor" görünür ve sorun yanlış yerde aranır. Kullanıcı
   yazılımcı değil; "sert yenile" bilinen bir hamle değildir (CLAUDE.md §8).
2. Model indirme hatası: ekranda ham GitHub adresi ne yapılacağını söylemez.
   Adres günlüğe yazılmaya devam etmeli — destek akışı oradan kopyalanıyor.
"""

from __future__ import annotations

import re
import ssl
import urllib.error
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SABLON_DIZINI = KOK / "backend" / "app" / "web" / "templates"
STATIK_DIZINI = KOK / "backend" / "app" / "web" / "static"

# href="/static/stil.css?v=7" ve src="/static/canli.js?v=7" satırlarını yakalar
_STATIK_CAGRI = re.compile(r'(?:src|href)="(/static/[^"?]+\.(?:js|css))(\?v=(\d+))?"')


def _statik_cagrilar() -> list[tuple[Path, str, str | None]]:
    """Şablonlardaki (dosya, statik yol, sürüm) üçlülerini toplar."""
    bulunanlar = []
    for sablon in sorted(SABLON_DIZINI.rglob("*.html")):
        for yol, _, surum in _STATIK_CAGRI.findall(sablon.read_text(encoding="utf-8")):
            bulunanlar.append((sablon, yol, surum or None))
    return bulunanlar


def test_her_js_ve_css_cagrisinda_surum_var():
    surumsuzler = [
        f"{sablon.relative_to(KOK)} → {yol}"
        for sablon, yol, surum in _statik_cagrilar()
        if not surum
    ]
    assert not surumsuzler, (
        "Sürümsüz statik dosya çağrısı, tarayıcının eski JS/CSS sunmasına yol açar "
        "(?v=N ekleyin):\n" + "\n".join(surumsuzler)
    )


def test_tum_statik_cagrilari_ayni_surumde():
    """Tek sürüm numarası: biri güncellenip diğeri unutulursa sayfa yarı eski,
    yarı yeni JS ile çalışır — teşhisi en zor durum budur."""
    surumler = {surum for _, _, surum in _statik_cagrilar() if surum}
    assert len(surumler) == 1, f"Tek bir sürüm numarası kullanılmalı, bulunan: {sorted(surumler)}"


def test_cagrilan_statik_dosyalar_gercekten_var():
    eksikler = [
        f"{sablon.relative_to(KOK)} → {yol}"
        for sablon, yol, _ in _statik_cagrilar()
        if not (STATIK_DIZINI / yol.removeprefix("/static/")).is_file()
    ]
    assert not eksikler, "Var olmayan statik dosya çağrılıyor:\n" + "\n".join(eksikler)


# ---- model indirme hatası: ekranda sade Türkçe, günlükte tam adres ----


def _metinler(hata: Exception):
    from app.analiz.model_indir import _YAYIN_ADRESI, _indirme_hata_metinleri

    hedef = Path("models/yolox_tiny.onnx")
    adres = _YAYIN_ADRESI + hedef.name
    kullanici, teknik = _indirme_hata_metinleri(adres, hedef, hata)
    return kullanici, teknik, adres


def test_indirme_hatasi_ekraninda_adres_yok():
    for hata in (
        urllib.error.URLError("[Errno 8] nodename nor servname provided"),
        urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")),
        TimeoutError("zaman aşımı"),
    ):
        kullanici, _, _ = _metinler(hata)
        dusuk = kullanici.lower()
        assert "http" not in dusuk, f"Ekrana adres sızmış: {kullanici}"
        assert "github" not in dusuk, f"Ekrana adres sızmış: {kullanici}"
        assert "Kontrol Panelinden yeniden başlatın" in kullanici, (
            "Kullanıcıya ne yapacağı söylenmeli"
        )


def test_indirme_hatasi_gunlugunde_tam_adres_duruyor():
    """Adres ekrandan kalktı diye destek akışından da kaybolmamalı."""
    for hata in (
        urllib.error.URLError("baglanti yok"),
        urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")),
    ):
        _, teknik, adres = _metinler(hata)
        assert adres in teknik, "Tam indirme adresi günlüğe yazılmalı"
        assert "models/yolox_tiny.onnx" in teknik, "Hedef dosya günlüğe yazılmalı"


def test_sertifika_hatasi_dogru_teshisi_koruyor():
    """Sertifika sorununda 'internetinizi kontrol edin' YANLIŞ teşhistir —
    kullanıcı saatlerce modemle uğraşır. Doğru çözüm korunmalı."""
    kullanici, _, _ = _metinler(
        urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))
    )
    assert "Install Certificates.command" in kullanici


def test_indirme_hatasi_kullanici_mesaji_ve_ayrinti_ayri():
    """Hata nesnesi ekran metnini ve günlük metnini ayrı taşımalı."""
    from app.analiz.model_indir import ModelIndirmeHatasi

    hata = ModelIndirmeHatasi("Sade mesaj.", "Sade mesaj. | adres: https://ornek/x.onnx")
    assert hata.kullanici_mesaji == "Sade mesaj."
    assert "https://ornek/x.onnx" in hata.teknik_ayrinti
    # Ayrıntı verilmezse eski davranış: ikisi de aynı
    assert ModelIndirmeHatasi("Tek metin.").teknik_ayrinti == "Tek metin."

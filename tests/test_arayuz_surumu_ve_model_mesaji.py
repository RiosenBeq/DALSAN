"""İki sessiz tuzağın nöbetçisi: tarayıcı önbelleği ve ekrana sızan teknik adres.

1. Önbellek kırıcı: JS/CSS değişip tarayıcı eskisini sunarsa, düzeltilmiş bir
   hata "hâlâ duruyor" görünür ve sorun yanlış yerde aranır. Kullanıcı
   yazılımcı değil; "sert yenile" bilinen bir hamle değildir (CLAUDE.md §8).
2. Model indirme hatası: ekranda ham GitHub adresi ne yapılacağını söylemez.
   Adres günlüğe yazılmaya devam etmeli - destek akışı oradan kopyalanıyor.
"""

from __future__ import annotations

import re
import ssl
import urllib.error
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SABLON_DIZINI = KOK / "backend" / "app" / "web" / "templates"
STATIK_DIZINI = KOK / "backend" / "app" / "web" / "static"

# href="/static/stil.css?v=7" ve src="/static/canli.js?v=7" satırlarını yakalar.
# .svg de kapsanır: simge sprite'ı ve logo da sürümlenmeli - sprite damgasız
# kalırsa yeni eklenen bir simge, tarayıcı eski dosyayı önbellekten verdiği
# için sessizce BOŞLUK olarak çizilir (eksik <use> hedefi hata üretmez).
_STATIK_CAGRI = re.compile(r'(?:src|href)="(/static/[^"?#]+\.(?:js|css|svg))(\?v=(\d+))?"')


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
    yarı yeni JS ile çalışır - teşhisi en zor durum budur."""
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


@pytest.mark.parametrize("kod", [404, 410])
def test_yayinda_olmayan_dosya_internet_sorunu_sayilmaz(kod):
    """Sunucu 404/410 dediyse internet çalışıyordur: kullanıcı modemle uğraşmasın,
    başka model seçip yeniden başlatsın; adres yine yalnız günlükte."""
    hata = urllib.error.HTTPError("https://ornek/x.onnx", kod, "Not Found", None, None)
    kullanici, teknik, adres = _metinler(hata)
    assert "yayın yerinde bulunamadı" in kullanici
    assert "İnternet bağlantısını kontrol" not in kullanici
    assert "“Tanıma modeli”" in kullanici and "yeniden başlatın" in kullanici
    assert "http" not in kullanici.lower() and adres in teknik


def test_sertifika_hatasi_dogru_teshisi_koruyor():
    """Sertifika sorununda 'internetinizi kontrol edin' YANLIŞ teşhistir -
    kullanıcı saatlerce modemle uğraşır. Doğru çözüm korunmalı."""
    kullanici, _, _ = _metinler(
        urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))
    )
    assert "Install Certificates.command" in kullanici


def test_saat_hatasi_sertifika_kurulumu_onermiyor():
    """Sertifika "henüz geçerli değil" derse sorun sertifika DEPOSU değil,
    bilgisayarın SAATİDİR. Buraya 'Install Certificates.command' yazmak
    kullanıcıyı yanlış yere gönderir; o dosya Windows'ta zaten yoktur."""
    for metin in (
        "certificate verify failed: certificate is not yet valid",
        "certificate verify failed: certificate has expired",
        "certificate is not yet valid or the system clock is incorrect",
    ):
        kullanici, _, _ = _metinler(urllib.error.URLError(ssl.SSLCertVerificationError(metin)))
        assert "Install Certificates" not in kullanici, f"yanlış teşhis: {kullanici}"
        assert "saat" in kullanici.lower(), f"saat çözümü söylenmeli: {kullanici}"
        assert "Kontrol Panelinden yeniden başlatın" in kullanici


def test_saat_hatasi_ekraninda_da_adres_yok():
    """Yeni dal da adres sızdırmamalı (diğer dallarla aynı kural)."""
    kullanici, teknik, adres = _metinler(
        urllib.error.URLError(ssl.SSLCertVerificationError("certificate is not yet valid"))
    )
    assert "http" not in kullanici.lower()
    assert adres in teknik, "Tam adres günlüğe yazılmalı"


def test_indirme_hatasi_kullanici_mesaji_ve_ayrinti_ayri():
    """Hata nesnesi ekran metnini ve günlük metnini ayrı taşımalı."""
    from app.analiz.model_indir import ModelIndirmeHatasi

    hata = ModelIndirmeHatasi("Sade mesaj.", "Sade mesaj. | adres: https://ornek/x.onnx")
    assert hata.kullanici_mesaji == "Sade mesaj."
    assert "https://ornek/x.onnx" in hata.teknik_ayrinti
    # Ayrıntı verilmezse eski davranış: ikisi de aynı
    assert ModelIndirmeHatasi("Tek metin.").teknik_ayrinti == "Tek metin."


# ---- bu deponun yayınından inen (forklift) model inmezse ----


@pytest.fixture
def forklift_modeli_kayitli(monkeypatch):
    """Kayıt betiğinin yazdığı gibi bir forklift modeli (docs/ILERLEME)."""
    from app.analiz import model_adi, model_indir

    ad = "nextgen_forklift_tiny_r9.onnx"
    monkeypatch.setitem(model_indir.DALSAN_MODELLERI, ad, "forklift-r9/tiny-v3-k1.onnx")
    monkeypatch.setitem(model_indir.FORKLIFT_TABANI, ad, "yolox_tiny.onnx")
    monkeypatch.setitem(model_indir.BILINEN_MODELLER, ad, "0" * 64)
    monkeypatch.setitem(model_adi.GORUNEN_ADLAR, ad, "NextGen AI Hızlı + Forklift")
    return Path("models") / ad


@pytest.mark.parametrize(
    "hata",
    [
        urllib.error.URLError("baglanti yok"),
        TimeoutError("zaman aşımı"),
        urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")),
    ],
)
def test_forklift_modeli_inmezse_hazir_modele_donus_soylenir(forklift_modeli_kayitli, hata):
    """İnternetsiz sahada forklift modeli seçilirse sistem insanı da görmez: mesaj
    hangi modelin inmediğini ve Ayarlar'dan hazır modele dönmeyi söyler."""
    from app.analiz.model_indir import _indirme_hata_metinleri

    kullanici, _ = _indirme_hata_metinleri("https://ornek/x", forklift_modeli_kayitli, hata)
    assert kullanici.startswith("NextGen AI Hızlı + Forklift indirilemedi")
    assert "“Tanıma modeli” listesinden “NextGen AI Hızlı” modeline dönüp" in kullanici
    assert ".onnx" not in kullanici and ".env" not in kullanici


def test_forklift_modeli_yayinda_yoksa_oneri_tekrarlanmaz(forklift_modeli_kayitli):
    """404/410 metni zaten başka modele geçmeyi söyler: ikinci öneri eklenmez."""
    from app.analiz.model_indir import _indirme_hata_metinleri

    hata = urllib.error.HTTPError("https://ornek/x.onnx", 404, "Not Found", None, None)
    kullanici, _ = _indirme_hata_metinleri("https://ornek/x", forklift_modeli_kayitli, hata)
    assert kullanici.count("“Tanıma modeli”") == 1


def test_hazir_model_inmezse_donus_onerilmez():
    """Hazır modelin dönülecek başka hazır modeli yok: metin eskisi gibi kalır."""
    kullanici, _, _ = _metinler(urllib.error.URLError("baglanti yok"))
    assert kullanici.startswith("NextGen AI Hızlı indirilemedi")
    assert "Beklemeden çalıştırmak" not in kullanici


def test_forklift_modeli_dogrulanamazsa_da_donus_soylenir(
    forklift_modeli_kayitli, tmp_path, monkeypatch
):
    """İnen dosyanın özeti tutmadı: aynı dönüş yolu söylenir."""
    import io

    from app.analiz import model_indir

    class Yanit(io.BytesIO):
        headers: dict = {}

    monkeypatch.setattr(model_indir.urllib.request, "urlopen", lambda *a, **k: Yanit(b"bozuk"))
    hedef = tmp_path / forklift_modeli_kayitli.name
    with pytest.raises(model_indir.ModelIndirmeHatasi) as hata:
        model_indir.modeli_indir(hedef)
    assert "indirildi ama doğrulanamadı" in hata.value.kullanici_mesaji
    assert "“NextGen AI Hızlı” modeline dönüp" in hata.value.kullanici_mesaji
    assert not hedef.with_suffix(".onnx.part").exists()


def test_model_hatalari_ayar_dosyasini_elle_duzenletmez():
    """Model Ayarlar'dan seçilir; paketlenmiş programda .env program klasöründe bile
    değildir ve yanında .env.example yoktur (docs/13)."""
    from app.analiz import model_indir, tespit

    metinler = [
        model_indir.ozel_model_hatasi(Path("models/benim.onnx")).kullanici_mesaji,
        tespit._uyumsuz_model(Path("models/benim.onnx"), "ayrıntı").kullanici_mesaji,
    ]
    for kaynak in ('["kedi"]', "bozuk-json"):
        with pytest.raises(tespit.ModelHatasi) as hata:
            tespit.sinif_eslemesi({tespit.UST_VERI_SINIF_ANAHTARI: kaynak})
        metinler.append(hata.value.kullanici_mesaji)
    for metin in metinler:
        assert "Ayarlar'daki “Tanıma modeli” listesinden" in metin, metin
        assert ".env.example" not in metin and "metin düzenleyici" not in metin, metin

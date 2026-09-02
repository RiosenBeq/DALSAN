"""Dar ekranda (telefon) form sayfaları yatay kaymaz.

ÖLÇÜLEN HATA: 375 px genişliğinde /kurallar/yeni ve /kurallar/{id}/duzenle
sayfaları 139 px yana kayıyordu. Kullanıcı sağa kaydırmadan "Kaydet"
düğmesini bile göremiyordu.

SEBEP: Izgara (grid) ve esnek kutu (flex) gözlerinin varsayılan en az
genişliği `min-width: auto`dur — yani göz, İÇİNDEKİ EN GENİŞ SATIR kadar yer
ister. Kural formundaki açılır listelerde uzun seçenekler var:

    "Bölge DIŞINDA olmak ihlal (örn. yaya yolunu kullanmamak)"

Bu satır <select>'in en az genişliğini belirliyor, o da sırayla etiketi,
formu, kartı ve sayfayı genişletiyordu. Kartın `max-width` değeri bunu
engellemez: `max-width`, içeriğin dayattığı EN AZ genişliği kırpmaz.

ÇÖZÜM: `.dikey-form` ve `.yatay-grup` içindeki gözlerde `min-width: 0`.

Bu testler CSS'i tarayıcı olmadan denetler; tarayıcıdaki ölçüm
(`document.documentElement.scrollWidth - clientWidth` = 0) elle doğrulandı.
Buradaki iş, o kuralın YANLIŞLIKLA SİLİNMESİNİ engellemektir.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
STIL = KOK / "backend" / "app" / "web" / "static" / "stil.css"
SABLONLAR = KOK / "backend" / "app" / "web" / "templates"

# Bu iki sayfa formu `.dikey-form` sınıfıyla kuruyor; kural oraya uygulanıyor.
FORM_SABLONLARI = ("kural_form.html", "kamera_form.html", "kamera_detay.html")


def _kurallar(css: str) -> list[tuple[list[str], dict[str, str]]]:
    """Basit CSS ayrıştırıcı: (seçici listesi, bildirimler) çiftleri.

    @media gibi iç içe blokları düzleştirir — bu testler için yeterli;
    aranan kurallar iç içe bloklarda değil.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = re.sub(r"@media[^{]*\{", "", css)
    cikti = []
    for blok in css.split("}"):
        if "{" not in blok:
            continue
        secici_metni, _, govde = blok.partition("{")
        seciciler = [" ".join(s.split()) for s in secici_metni.split(",") if s.strip()]
        bildirimler = {}
        for bildirim in govde.split(";"):
            ad, _, deger = bildirim.partition(":")
            if ad.strip() and deger.strip():
                bildirimler[ad.strip().lower()] = " ".join(deger.split()).lower()
        if seciciler and bildirimler:
            cikti.append((seciciler, bildirimler))
    return cikti


def _deger(kurallar, secici: str, ozellik: str) -> str | None:
    """Seçiciye uygulanan son (kazanan) değer."""
    bulunan = None
    for seciciler, bildirimler in kurallar:
        if secici in seciciler and ozellik in bildirimler:
            bulunan = bildirimler[ozellik]
    return bulunan


def test_form_gozleri_en_az_genislige_zorlanmaz():
    """`min-width: 0` silinirse uzun seçenekli select sayfayı yine kaydırır."""
    kurallar = _kurallar(STIL.read_text(encoding="utf-8"))
    for secici in (".dikey-form *", ".yatay-grup *"):
        assert _deger(kurallar, secici, "min-width") == "0", (
            f"'{secici}' için 'min-width: 0' kuralı yok. Bu kural silinirse "
            "telefonda kural formu sayfayı yatay kaydırır (139 px ölçüldü)."
        )


def test_form_alanlari_kutuyu_asamaz():
    """Kendi genişliğini dayatan bir alan kartın dışına taşmasın."""
    kurallar = _kurallar(STIL.read_text(encoding="utf-8"))
    for secici in (".dikey-form input", ".dikey-form select", ".dikey-form textarea"):
        assert _deger(kurallar, secici, "max-width") == "100%", (
            f"'{secici}' için 'max-width: 100%' kuralı yok."
        )


def test_form_genisligi_sabit_piksel_degil():
    """`.dikey-form.dar` 460 px'i SABİT genişlik olursa 375 px'lik ekran taşar.

    `max-width` daralabilir, `width` daralamaz — aradaki fark telefonda
    doğrudan yatay kaymaya dönüşür.
    """
    kurallar = _kurallar(STIL.read_text(encoding="utf-8"))
    sabitler = [
        (seciciler, bildirimler["width"])
        for seciciler, bildirimler in kurallar
        if any(s.startswith((".dikey-form", ".kart")) for s in seciciler)
        and re.fullmatch(r"\d+px", bildirimler.get("width", ""))
    ]
    assert not sabitler, f"Form/kart genişliği sabit piksel: {sabitler}"


def test_kural_formu_dikey_form_sinifini_kullanir():
    """CSS düzeltmesi bu sınıf üzerinden çalışıyor; şablon sınıfı bırakırsa
    düzeltme sayfaya hiç ulaşmaz."""
    for ad in FORM_SABLONLARI:
        govde = (SABLONLAR / ad).read_text(encoding="utf-8")
        assert "dikey-form" in govde, f"{ad} artık 'dikey-form' sınıfını kullanmıyor"


def test_form_sablonlarinda_satir_ici_sabit_genislik_yok():
    """Şablona yazılan `style="width: 460px"` CSS düzeltmesini ezerdi."""
    for ad in FORM_SABLONLARI:
        govde = (SABLONLAR / ad).read_text(encoding="utf-8")
        kacaklar = re.findall(r'style="[^"]*[^-]width:\s*\d+px[^"]*"', govde)
        assert not kacaklar, f"{ad} içinde satır içi sabit genişlik: {kacaklar}"

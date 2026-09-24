"""Depoya kopyalanmış arayüz varlıkları: simgeler ve yazı tipi.

`static/vendor/` klasörü, CLAUDE.md §4'teki "yeni kütüphane ekleme" yasağının
BİLİNÇLİ ve SINIRLI bir istisnasıdır. Buradaki testler istisnanın sınırlarını
korur - yani bir dahaki sefere "madem vendor klasörü var" diye bir CSS
çatısının içeri sızmasını engeller.

Korunan üç şey:

1. **CDN YOK.** Fabrika sunucusunda internet olmayabilir; olsa bile kurumsal
   güvenlik duvarı dış adresleri engelleyebilir. CDN'den gelmeyen bir yazı
   tipi, sistemin kendisi sorunsuz çalışırken arayüzü yarı çizilmiş
   gösterirdi.
2. **Türkçe harfler.** `latin` altkümesinde ş, ğ ve İ (büyükleriyle) YOKTUR;
   onlar `latin-ext`'tedir, ı ise `latin`'dedir. Yalnız biri konsaydı bu
   harfler yedek yazı tipine düşer ve satırlar iki farklı yazı tipiyle karışık
   görünürdü.
3. **Simge yazının YERİNE GEÇMEZ.** Yalnız simge konsaydı yazılım bilmeyen
   kullanıcı "bu resim ne demek" diye durmak zorunda kalırdı (CLAUDE.md §8).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
STATIK = KOK / "backend" / "app" / "web" / "static"
VENDOR = STATIK / "vendor"
STIL = STATIK / "stil.css"
SABLONLAR = KOK / "backend" / "app" / "web" / "templates"

# Toplam vendor boyutunun üst sınırı (KB). Sınır, klasörün sessizce bir
# "varlık çöplüğüne" dönüşmesini engeller: bir dahaki eklemede bu testi
# görmek, boyutu bilerek onaylamak demektir.
EN_COK_KB = 400


@pytest.fixture(scope="module")
def stil() -> str:
    return STIL.read_text(encoding="utf-8")


# ----------------------------------------------------------------- CDN yok


def test_hicbir_sablon_disaridan_varlik_cekmiyor():
    """Tek bir CDN adresi bile, internetsiz fabrikada arayüzü bozar."""
    disari = re.compile(r'(?:href|src)="https?://', re.I)
    suclular = [
        yol.name
        for yol in SABLONLAR.glob("*.html")
        if disari.search(yol.read_text(encoding="utf-8"))
    ]
    assert not suclular, f"dışarıdan varlık çeken şablonlar: {suclular}"


def test_stil_dosyasi_disaridan_varlik_cekmiyor(stil):
    assert "http://" not in stil
    assert "https://" not in stil
    assert "@import" not in stil, "@import de dışarıya çıkabilir; yollar yerel olmalı"


def test_yazi_tipi_yerel_dosyadan_geliyor(stil):
    assert stil.count("@font-face") == 2
    assert "/static/vendor/inter-latin.woff2" in stil
    assert "/static/vendor/inter-latin-ext.woff2" in stil


# --------------------------------------------------------- dosyalar yerinde


@pytest.mark.parametrize(
    "dosya",
    ["simgeler.svg", "inter-latin.woff2", "inter-latin-ext.woff2", "LISANSLAR.md"],
)
def test_vendor_dosyalari_depoda(dosya):
    assert (VENDOR / dosya).is_file(), f"{dosya} eksik - arayüz onsuz yarım çizilir"


def test_vendor_klasoru_sismiyor():
    toplam = sum(y.stat().st_size for y in VENDOR.iterdir() if y.is_file())
    assert toplam < EN_COK_KB * 1024, (
        f"static/vendor {toplam // 1024} KB oldu (sınır {EN_COK_KB} KB). "
        "Paketlenmiş uygulamaya olduğu gibi giriyor; büyütmeden önce gerçekten "
        "gerekli mi diye bakın."
    )


def test_turkce_harfler_icin_iki_altkume_de_var(stil):
    """`latin` altkümesinde ş, ğ ve İ YOKTUR; onlar latin-ext'tedir (ı latin'dedir).

    Yalnız biri konsaydı her Türkçe kelime yedek yazı tipine düşerdi.
    """
    assert (VENDOR / "inter-latin-ext.woff2").stat().st_size > 10_000
    # latin-ext bloğu Latin Extended-A aralığını (U+0100-) kapsamalı.
    assert "U+0100-02BA" in stil


def test_yazi_tipi_inmezse_sistem_yazisina_dusuluyor(stil):
    """Yazı tipi dosyası silinse ya da tarayıcı engellese bile arayüz
    okunabilir kalmalı; boş bir sayfa gösterilemez."""
    assert "-apple-system" in stil and "sans-serif" in stil
    assert "font-display: swap" in stil, "block olsaydı metin inene kadar GÖRÜNMEZDİ"


def test_yazi_tipleri_git_tarafindan_ikili_sayiliyor():
    """Satır sonu dönüşümü uygulanırsa woff2 dosyalarının İÇİ BOZULUR.

    Sonuç sinsidir: arayüzdeki her yazı sistem yazı tipine düşer ve bu
    YALNIZCA depoyu Windows'ta klonlayan kişide olur - Mac'te geliştiren
    hiç göremez. Simge dosyaları için aynı koruma zaten vardı (.ico/.icns).
    """
    import subprocess

    cikti = subprocess.run(
        ["git", "check-attr", "binary", "--", "backend/app/web/static/vendor/inter-latin.woff2"],
        cwd=KOK,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout
    assert cikti.strip().endswith("binary: set"), cikti


def test_lisanslar_kayitli():
    """ISC ve OFL'in tek koşulu telif bildiriminin korunmasıdır."""
    lisanslar = (KOK / "LICENSE-THIRD-PARTY").read_text(encoding="utf-8")
    assert "Lucide" in lisanslar
    assert "Inter" in lisanslar
    assert "SIL Open Font License" in lisanslar
    yerel = (VENDOR / "LISANSLAR.md").read_text(encoding="utf-8")
    assert "ISC" in yerel and "OFL" in yerel


def test_claude_md_istisnayi_yaziyor():
    """Kural değiştiyse kuralın yazdığı yer de değişmeli; yoksa bir sonraki
    oturum "kütüphane yasak" deyip bu dosyaları siler."""
    kurallar = (KOK / "CLAUDE.md").read_text(encoding="utf-8")
    assert "static/vendor/" in kurallar
    # İstisnanın SINIRI da yazmalı: çatılar hâlâ yasak.
    assert "Tailwind" in kurallar


# -------------------------------------------------------------- sprite


@pytest.fixture(scope="module")
def sprite() -> str:
    return (VENDOR / "simgeler.svg").read_text(encoding="utf-8")


def test_sprite_gecerli_ve_simge_tasiyor(sprite):
    import xml.etree.ElementTree as ET

    kok = ET.fromstring(sprite[sprite.index("<svg") :])
    simgeler = [c for c in kok if c.tag.endswith("symbol")]
    assert len(simgeler) >= 20
    for simge in simgeler:
        assert simge.get("id", "").startswith("s-")
        assert simge.get("viewBox") == "0 0 24 24"


def test_sablonlarda_cagrilan_her_simge_spritete_var(sprite):
    """Olmayan bir simge sessizce BOŞLUK olarak çizilir: hata yok, resim yok."""
    mevcut = set(re.findall(r'id="s-([\w-]+)"', sprite))
    cagrilar = set()
    for yol in SABLONLAR.glob("*.html"):
        cagrilar |= set(re.findall(r'simge\("([\w-]+)"', yol.read_text(encoding="utf-8")))
    eksik = cagrilar - mevcut
    assert not eksik, f"şablonlarda çağrılan ama sprite'ta olmayan simgeler: {sorted(eksik)}"


def test_sprite_renk_gommuyor(sprite):
    """Simge, üzerinde durduğu metnin rengini almalı (`currentColor`).

    Renk gömülü olsaydı karanlık kipte görünmez olurdu.
    """
    # Yalnızca SİMGELERİN kendisine bakılır; dosyanın başındaki açıklama
    # yorumu bu kuralı ANLATTIĞI için "currentColor" kelimesini içeriyor.
    govde = sprite[sprite.index("<symbol") :]
    assert "currentColor" not in govde, "renk sprite'ta değil CSS'te olmalı"
    assert 'stroke="#' not in govde and 'fill="#' not in govde
    assert "stroke: currentColor" in STIL.read_text(encoding="utf-8")


# ------------------------------------------- simge yazının yerine geçmiyor


def test_gezinme_baglantilarinda_simgenin_yaninda_yazi_var():
    """Yalnız simge konsaydı kullanıcı "bu resim ne demek" diye dururdu."""
    temel = (SABLONLAR / "temel.html").read_text(encoding="utf-8")
    for yazi in ("Kameralar", "Kurallar", "Olaylar", "KKD", "Anons", "Ana Sayfa"):
        assert f"}} {yazi}<" in temel or f"}} {yazi} " in temel, f"{yazi} yazısı kaybolmuş"


def test_simgeler_ekran_okuyucudan_gizli():
    """Okunsaydı her satırda "grafik" diye anlamsız bir kelime duyulurdu."""
    makro = (SABLONLAR / "simge.html").read_text(encoding="utf-8")
    assert 'aria-hidden="true"' in makro
    assert 'focusable="false"' in makro


def test_simge_tek_yerden_cagriliyor():
    """Her şablon kendi <svg><use> etiketini yazsaydı, sprite yolu değişince
    otuz yeri tek tek düzeltmek gerekirdi."""
    for yol in SABLONLAR.glob("*.html"):
        if yol.name == "simge.html":
            continue
        metin = yol.read_text(encoding="utf-8")
        assert "vendor/simgeler.svg" not in metin, f"{yol.name} sprite'ı doğrudan çağırıyor"


# ------------------------------------------------------------ canlı sayfa


def test_sayfa_simge_ve_yazi_tipini_gercekten_sunuyor(istemci):
    """Şablon doğru yazsa bile dosya sunulmuyorsa arayüz yine yarım kalır."""
    sayfa = istemci.get("/kameralar")
    assert sayfa.status_code == 200
    assert "vendor/simgeler.svg?v=" in sayfa.text and "#s-kamera" in sayfa.text

    for yol, tur in (
        ("/static/vendor/simgeler.svg", "svg"),
        ("/static/vendor/inter-latin.woff2", "font"),
        ("/static/vendor/inter-latin-ext.woff2", "font"),
    ):
        yanit = istemci.get(yol)
        assert yanit.status_code == 200, yol
        assert tur in yanit.headers.get("content-type", "") or yanit.content[:4] == b"wOF2"


# ------------------------------------------------------- CSS sözdizimi


@pytest.mark.parametrize("dosya", ["stil.css", "komuta.css"])
def test_css_suslu_parantezleri_dengeli(dosya):
    """Eksik ya da fazla bir `}` hata vermez: tarayıcı sonraki kuralları
    sessizce bozuk bildirimin içine yutar ve bir ekran (ör. dar ekrandaki
    tablolar) görünürde hiçbir sebep yokken bozulur. Metin arayan testler
    bunu göremez; denge burada sayılır."""
    metin = (KOK / "backend/app/web/static" / dosya).read_text(encoding="utf-8")
    govde = re.sub(r"/\*.*?\*/", "", metin, flags=re.S)
    derinlik = 0
    for satir_no, satir in enumerate(govde.splitlines(), 1):
        for karakter in satir:
            if karakter == "{":
                derinlik += 1
            elif karakter == "}":
                derinlik -= 1
                assert derinlik >= 0, f"{dosya}: fazladan '}}' (yorumsuz metinde satır {satir_no})"
    assert derinlik == 0, f"{dosya}: {derinlik} adet '{{' kapanmamış"

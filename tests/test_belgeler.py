"""Proje belgeleri uygulamanın içinde açılır (web/belge_rotalari.py).

Sayfalar "docs/15-UZAKTAN-ERISIM.md" gibi belgelere gönderir. Windows ve Mac
uygulamasında program klasörü yoktur, Docker'da belgeler imajın dışında
kalırdı: gönderme bir yere çıkmazdı (docs/ILERLEME, denetim 24.09.2026).
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SABLONLAR = KOK / "backend" / "app" / "web" / "templates"


def test_belge_listesi_her_belgeyi_basligiyla_gosterir(istemci):
    sayfa = istemci.get("/komuta/belgeler").text
    for yol in sorted((KOK / "docs").glob("*.md")):
        assert f'href="/komuta/belgeler/{yol.name}"' in sayfa, yol.name
    assert "Uzaktan" in sayfa  # 15-UZAKTAN-ERISIM.md'nin başlığından


def test_belge_duz_metin_olarak_ve_kacisli_gosterilir(istemci):
    yanit = istemci.get("/komuta/belgeler/15-UZAKTAN-ERISIM.md")
    assert yanit.status_code == 200
    metin = (KOK / "docs" / "15-UZAKTAN-ERISIM.md").read_text(encoding="utf-8")
    baslik = next(s[2:].strip() for s in metin.splitlines() if s.startswith("# "))
    assert f"<h2>{baslik}</h2>" in yanit.text
    assert '<pre class="belge-metni"' in yanit.text
    # Belgedeki HTML benzeri metin sayfaya işlenmez, kaçırılır
    assert "<script" not in yanit.text.split('<pre class="belge-metni"', 1)[1].split("</pre>")[0]


def test_docs_disindaki_dosya_acilmaz(istemci):
    for ad in ("CLAUDE.md", ".env", "yok.md", "..md", "15-UZAKTAN-ERISIM.txt"):
        yanit = istemci.get(f"/komuta/belgeler/{ad}")
        assert yanit.status_code == 404, ad
        assert "bu kurulumda yok" in yanit.text
    # Kodlanmış eğik çizgiyle üst klasöre çıkılamaz
    assert istemci.get("/komuta/belgeler/..%2FCLAUDE.md").status_code == 404


def test_sablonlardaki_belge_baglantilari_var_olan_belgelere_gider():
    baglantilar = set()
    for sablon in SABLONLAR.glob("*.html"):
        baglantilar |= set(
            re.findall(r'href="/komuta/belgeler/([^"]+)"', sablon.read_text(encoding="utf-8"))
        )
    baglantilar.discard("{{ b.ad }}")
    assert baglantilar, "hiçbir sayfa belgeye bağlanmıyor"
    for ad in baglantilar:
        assert (KOK / "docs" / ad).is_file(), f"kırık belge bağlantısı: {ad}"


def test_belgeler_uygulamayla_ve_docker_imajiyla_gelir():
    import importlib.util

    ortak_yolu = KOK / "paketleme" / "paketleme_ortak.py"
    tanim = importlib.util.spec_from_file_location("paketleme_ortak_belgeler", ortak_yolu)
    ortak = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(ortak)
    assert (str(KOK / "docs"), "docs") in ortak.veri_dosyalari(KOK)

    assert "COPY docs/ docs/" in (KOK / "Dockerfile").read_text(encoding="utf-8")
    haric = (KOK / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "docs/" not in haric and "!docs/*.md" in haric

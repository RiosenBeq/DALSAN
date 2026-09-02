"""Bölge çizimi KOLAY olmalı: kullanıcı nereye tıkladığını ve ne olacağını görsün.

Neden bu testler var:

Bölge çizimi bir zamanlar "düğmeye bas, tıkla, tıkla, kaydet"ten ibaretti.
Kullanıcı çizerken kenarın nereye gideceğini göremiyor, alanı nasıl
bitireceğini bilmiyor, yanlış konan köşeyi geri alamıyor (baştan başlıyor) ve
kaç köşe koyduğunu sayamıyordu. Yazılım bilmeyen bir kullanıcı için "yaya
geçidini tanıtmak" bu yüzden zor bir işti.

Şimdi çizim şunları veriyor ve bu testler onları koruyor:
  · fare gezerken kesikli canlı kenar önizlemesi,
  · en az 3 köşe varken büyüyen ilk noktaya tıklayarak alanı kapatma,
  · son köşeyi geri alma ve Esc ile iptal,
  · köşe sayacı + duruma göre değişen Türkçe kılavuz balonu,
  · seçilen bölge tipinin rengi ve Türkçe adı.

Koordinatların NORMALİZE (0-1) kaydedilmesi de burada korunuyor: kameranın
çözünürlüğü değişince çizilmiş bölgeler bozulmamalı.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.web.ortak import BOLGE_TIPLERI

KOK = Path(__file__).resolve().parents[1]
_JS = KOK / "backend" / "app" / "web" / "static" / "kamera_detay.js"
_CSS = KOK / "backend" / "app" / "web" / "static" / "stil.css"
_SABLON = KOK / "backend" / "app" / "web" / "templates" / "kamera_detay.html"


def _js() -> str:
    return _JS.read_text(encoding="utf-8")


def _css() -> str:
    return _CSS.read_text(encoding="utf-8")


def _sablon() -> str:
    return _SABLON.read_text(encoding="utf-8")


# ---- 1. canlı kenar önizlemesi ----


def test_fare_gezerken_kesikli_kenar_cizilir():
    """Kullanıcı, bir sonraki kenarın nereye gideceğini tıklamadan görmeli."""
    kaynak = _js()
    assert 'tuval.addEventListener("mousemove"' in kaynak, "fare hareketi izlenmiyor"
    assert "setLineDash" in kaynak, "canlı kenar kesikli çizilmiyor"
    assert re.search(r"KESIK\s*=\s*\[\s*7\s*,\s*6\s*\]", kaynak), "kesik deseni [7, 6] olmalı"


def test_fare_alandan_cikinca_onizleme_kenari_silinir():
    """İmleç görüntüden çıkınca havada asılı bir kenar kalmamalı."""
    assert 'tuval.addEventListener("mouseleave"' in _js()


# ---- 2. ilk noktaya tıklayıp kapatma ----


def test_ilk_nokta_buyuk_cizilir_ve_alani_kapatir():
    """Alanı bitirmenin yolu görünür olmalı: ilk köşe büyür, ona tıklamak kapatır."""
    kaynak = _js()
    assert re.search(r"ILK_NOKTA_R\s*=\s*8", kaynak), "kapatma noktası 8 px yarıçapla çizilmeli"
    assert re.search(r"NOKTA_R\s*=\s*5", kaynak), "diğer köşeler 5 px yarıçapla çizilmeli"
    assert re.search(r"KAPATMA_YARICAPI\s*=\s*14", kaynak), "kapatma hedefi 14 px olmalı"
    assert "Math.hypot" in kaynak, "ilk noktaya uzaklık ölçülmüyor"
    # kapatma yalnızca en az 3 köşe varken olmalı — 2 köşe alan değildir
    assert "bolgeNoktalari.length >= 3 &&" in kaynak


def test_kapali_alana_yeni_kose_eklenmez():
    """Alan kapandıktan sonraki tıklama köşe eklememeli, yoksa şekil bozulur."""
    kaynak = _js()
    govde = kaynak.split("function bolgeTiklamasi(", 1)[1]
    assert "if (kapandi) return;" in govde


# ---- 3. geri al ----


def test_son_koseyi_geri_al_dugmesi_var():
    """Yanlış konan köşe için baştan başlamak gerekmemeli."""
    assert 'id="cizim-geri"' in _sablon()
    kaynak = _js()
    assert "bolgeNoktalari.pop()" in kaynak, "geri alma son köşeyi silmiyor"
    govde = kaynak.split("geriDugmesi.addEventListener", 1)[1]
    assert "kapandi = false" in govde.split("});", 1)[0], (
        "kapalı alandan köşe silinince alan yeniden açılmalı"
    )


def test_geri_al_ve_temizle_kose_yokken_pasif():
    """Hiç köşe yokken basılacak düğme kullanıcıyı yanıltmamalı."""
    sablon = _sablon()
    assert re.search(r'id="cizim-geri"[^>]*disabled', sablon)
    assert re.search(r'id="cizim-temizle"[^>]*disabled', sablon)
    kaynak = _js()
    assert "geriDugmesi.disabled = sayi === 0" in kaynak
    assert "temizleDugmesi.disabled = sayi === 0" in kaynak


# ---- 4. Esc ----


def test_esc_cizimi_iptal_eder():
    """Kullanıcı yanlışlıkla çizime başlarsa çıkış yolu olmalı."""
    kaynak = _js()
    assert 'olay.key !== "Escape"' in kaynak, "Esc dinlenmiyor"
    govde = kaynak.split("function cizimiIptalEt()", 1)[1].split("\n  }", 1)[0]
    assert "mod = null" in govde
    assert "bolgeNoktalari = []" in govde
    assert "kapandi = false" in govde


def test_iptal_kilavuz_balonunu_gizler():
    """Mod kapanınca kılavuz balonu ekranda kalmamalı."""
    kaynak = _js()
    govde = kaynak.split("function kilavuzuGuncelle()", 1)[1]
    assert "if (!mod) { balon.hidden = true; return; }" in govde


# ---- 5. köşe sayacı ve adım adım kılavuz ----


def test_kose_sayaci_ve_kilavuz_balonu_sayfada_var():
    sablon = _sablon()
    assert 'id="kose-sayaci"' in sablon
    assert 'id="cizim-balonu"' in sablon
    assert 'id="balon-adim"' in sablon
    # balon çizim başlamadan görünmemeli
    assert re.search(r'id="cizim-balonu"[^>]*hidden', sablon)


def test_kilavuz_metni_duruma_gore_degisiyor():
    """Tek bir sabit cümle yetmez: kullanıcı hangi adımda olduğunu okumalı."""
    kaynak = _js()
    for parca in (
        "Bölgenin köşelerine sırayla tıklayın",  # 0 köşe
        "Köşe eklemeye devam edin",  # 1-2 köşe
        "İLK (büyük) noktaya tıklayın",  # >=3 köşe
        "Alan kapandı",  # kapandıktan sonra
        "Vazgeçmek için Esc",  # çıkış yolu
    ):
        assert parca in kaynak, f"kılavuzda eksik adım metni: {parca}"


def test_kilavuz_ve_sayac_turkce():
    """Kullanıcıya görünen her metin Türkçe (CLAUDE.md §8)."""
    kaynak = _js()
    assert '" köşe"' in kaynak
    assert "nokta" in kaynak
    for ingilizce in ("corner", "Click here", "Undo", "Cancel", "point(s)"):
        assert ingilizce not in kaynak, f"ekranda İngilizce metin: {ingilizce}"


# ---- 6. koordinatlar normalize kalıyor ----


def test_koordinatlar_normalize_kaydediliyor():
    """0-1 aralığı: kamera çözünürlüğü değişse de bölge geçerli kalmalı."""
    kaynak = _js()
    govde = kaynak.split("function oranHesapla(", 1)[1].split("\n  }", 1)[0]
    assert "kutu.width" in govde and "kutu.height" in govde, (
        "koordinat piksel olarak alınıyor — çözünürlük değişince bölge kayar"
    )
    assert "JSON.stringify(bolgeNoktalari)" in kaynak, "poligon gizli alana yazılmıyor"


# ---- 7. bölge tipine göre renk ve Türkçe etiket ----


def test_her_bolge_tipinin_rengi_stil_dosyasinda_tanimli():
    """Renkler tek yerde (stil.css :root) durmalı; JS'e sabit renk yazılmaz."""
    js = _js()
    css = _css()
    eslesme = dict(re.findall(r"(\w+):\s*\"(--bolge-[a-z-]+)\"", js))
    assert set(eslesme) == set(BOLGE_TIPLERI), (
        f"JS'teki tip listesi sunucununkiyle aynı olmalı: {sorted(eslesme)}"
    )
    for tip, degisken in eslesme.items():
        assert re.search(rf"{degisken}:\s*#[0-9a-f]{{6}};", css), (
            f"{tip} için {degisken} stil.css :root içinde tanımlı değil"
        )


def test_bolge_tipi_renkleri_birbirinden_farkli():
    """Aynı rengi iki tipe vermek, rengi işe yaramaz hale getirir."""
    renkler = re.findall(r"--bolge-[a-z-]+:\s*(#[0-9a-f]{6});", _css())
    assert len(renkler) == len(BOLGE_TIPLERI)
    assert len(set(renkler)) == len(renkler), f"tekrar eden bölge tipi rengi: {renkler}"


def test_secilen_tipin_rengi_ve_turkce_adi_gosteriliyor():
    """Kullanıcı hangi tipi çizdiğini renkten VE yazıdan görmeli.

    Türkçe ad, seçim kutusundaki metinden okunur — böylece tek kaynak sunucudaki
    BOLGE_TIPLERI tablosudur, JS'te ikinci bir Türkçe liste tutulmaz.
    """
    kaynak = _js()
    assert "tipSecimi.options[tipSecimi.selectedIndex].text" in kaynak
    assert 'seciliTipAdi() + " çiziyorsunuz"' in kaynak
    assert "tipRengiKutusu.style.background = seciliTipRengi()" in kaynak
    assert 'id="tip-rengi"' in _sablon(), "seçim kutusunun yanında renk örneği yok"
    # tip değişince çizilmekte olan bölge de yeni renge dönmeli
    assert "tipSecimi.addEventListener" in kaynak


def test_js_icinde_sabit_bolge_tipi_rengi_yok():
    """stil.css tek renk kaynağı: JS yalnızca kayıtlı bölge morunu bilir."""
    renkler = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", _js()))
    assert renkler == {"#A03CC8"}, (
        f"JS'e sabit renk yazılmış (stil.css değişkeni kullanın): {sorted(renkler)}"
    )


# ---- 8. kılavuz balonu cam dilinde ----


def test_kilavuz_balonu_koyu_cam_ve_tiklamayi_gecirir():
    """Balon görüntünün üstünde durur; tıklamayı yutarsa köşe konamaz."""
    css = _css()
    blok = css.split(".cizim-balonu {", 1)[1].split("}", 1)[0]
    assert "var(--koyu-cam)" in blok, "balon koyu cam olmalı"
    assert "backdrop-filter: var(--bulanik)" in blok
    assert "-webkit-backdrop-filter" in blok, "Safari öneki eksik"
    assert "pointer-events: none" in blok, "balon tıklamayı yutuyor"


def test_balon_gizliyken_gercekten_gorunmuyor():
    """Tarayıcıda yakalanan hata: .cizim-balonu'nun display:flex'i tarayıcının
    [hidden] kuralını yeniyordu. Bu satır olmadan, çizim başlamadan da boş bir
    koyu şerit görüntünün üstünde duruyordu."""
    css = _css()
    assert ".cizim-balonu[hidden] { display: none; }" in css, (
        "hidden özniteliği balonu gizlemiyor — sınıftaki display:flex onu yener"
    )
    # sınıf gerçekten flex olduğu için bu kural şart
    blok = css.split(".cizim-balonu {", 1)[1].split("}", 1)[0]
    assert "display: flex" in blok


def test_balon_tuvalin_olcusunu_bozmuyor():
    """Tarayıcıda yakalanan ikinci hata: balon .cizim-alani'nın İÇİNDEYKEN, dar
    ekranda görüntünün altına inince kutuyu uzatıyordu. Tuval `inset: 0` ile
    o kutuyu kapladığı için görüntüden taşıyor ve tıklanan yer ile çizilen nokta
    kayıyordu. Balon artık kardeş düğüm: ölçüyü etkileyemez."""
    sablon = _sablon()
    alan = sablon.split('<div class="cizim-alani onizleme-kutu">', 1)[1].split("</div>", 1)[0]
    assert "cizim-balonu" not in alan, "kılavuz balonu .cizim-alani içinde — tuvalin ölçüsünü bozar"
    assert 'class="cizim-sarmal"' in sablon, "balonu tutan sarmal yok"
    css = _css()
    assert ".cizim-sarmal { position: relative;" in css, (
        "balon geniş ekranda görüntünün üstünde durabilmek için konumlanmış bir sarmal ister"
    )


def test_dar_ekranda_balon_goruntunun_altina_iner():
    """Telefonda balon 200 px'lik önizlemenin yarısını kapatıyordu."""
    dar = _css().split("@media (max-width: 620px) {", 1)[1]
    assert ".cizim-balonu { position: static;" in dar


def test_yeni_stil_siniflari_sabit_renk_kullanmiyor():
    """Cam dili: yeni sınıflar da değişkenlerle boyanmalı."""
    css = _css()
    for sinif in (".cizim-balonu {", ".kose-sayaci {", ".tip-rengi {"):
        blok = css.split(sinif, 1)[1].split("}", 1)[0]
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", blok), f"{sinif} içinde sabit renk var"


# ---- 9. sayfa gerçekten bu öğelerle geliyor mu ----


def test_kamera_sayfasi_cizim_yardimcilarini_iceriyor(istemci, test_ayarlari):
    """Şablon değişse de kullanıcı bu öğeleri sayfada bulmalı."""
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "K1", "source_type": "file", "source_url": str(video), "sample_fps": "6"},
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])

    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    for parca in ("cizim-geri", "kose-sayaci", "cizim-balonu", "tip-rengi", "bolge-tipi"):
        assert parca in sayfa, f"sayfada eksik: {parca}"
    assert "Son köşeyi geri al" in sayfa
    for ad in BOLGE_TIPLERI.values():
        assert ad in sayfa, f"bölge tipi seçeneği eksik: {ad}"

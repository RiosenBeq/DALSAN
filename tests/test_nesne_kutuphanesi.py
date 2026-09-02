"""Nesne kütüphanesi: parmak izi, depo, arama, saklama koruması ve sayfa.

Bu özelliğin iki büyük riski var ve testlerin çoğu o ikisini bekler:

1. **Uydurma isim.** Emin olunmayan bir yere nesne adı yazmak, tarama raporunu
   güvenilmez yapar. Eşiğin altındaki en iyi skor bile kabul EDİLMEMELİ.
2. **Yanlış anlaşılma.** Kullanıcı bu sayfayı canlı tanıma sanabilir. Sayfada
   ve kılavuzda "canlı kameraları etkilemez" cümlesi KALMALI.

Üçüncü bir sessiz tuzak: bakım döngüsünün nesne fotoğraflarını silmesi. Onlar
kanıt değil TANIM'dır; silinirlerse kütüphane sessizce boşalır.
"""

from __future__ import annotations

import dataclasses
import os
import time as time_mod
from pathlib import Path

import cv2
import numpy as np
import pytest

from app import veritabani
from app.hatalar import DogrulamaHatasi
from app.nesneler import arama, depo
from app.nesneler.kutuphane import (
    VARSAYILAN_ESIK,
    Nesne,
    benzerlik,
    en_iyi_eslesme,
    parmakizi_cikar,
    renk_alt_siniri,
    renk_benzerligi,
)

# ---------------------------------------------------------------- yardımcılar


def desenli_nesne(ana_renk=(40, 40, 200), tohum: int = 1, boyut: int = 180) -> np.ndarray:
    """Belirli renkte, tekrarlanabilir desenli sahte bir nesne fotoğrafı."""
    rastgele = np.random.default_rng(tohum)
    gorsel = np.full((180, 180, 3), ana_renk, dtype=np.uint8)
    for _ in range(40):  # ORB'nin tutunacağı köşeler
        x, y = rastgele.integers(10, 160, size=2)
        cv2.rectangle(gorsel, (int(x), int(y)), (int(x) + 12, int(y) + 12), (250, 250, 250), -1)
    if boyut != 180:
        gorsel = cv2.resize(gorsel, (boyut, boyut), interpolation=cv2.INTER_AREA)
    return gorsel


def sahne(nesne: np.ndarray | None = None, x: int = 96, y: int = 96) -> np.ndarray:
    """400x400 fabrika benzeri arka plan; istenirse içine nesne yerleştirilir.

    (96, 96) noktası bilerek seçildi: 120 piksellik pencere ızgarası tam oraya
    denk gelir, yani "nesne bir pencerenin içine sığdı" durumu sınanır.
    """
    rastgele = np.random.default_rng(99)
    zemin = np.full((400, 400, 3), (30, 150, 60), dtype=np.uint8)
    for _ in range(120):
        a, b = rastgele.integers(0, 380, size=2)
        cv2.rectangle(zemin, (int(a), int(b)), (int(a) + 15, int(b) + 10), (20, 110, 40), -1)
    if nesne is not None:
        yuksek, genis = nesne.shape[:2]
        zemin[y : y + yuksek, x : x + genis] = nesne
    return zemin


def jpeg(tohum: int = 1) -> bytes:
    return cv2.imencode(".jpg", desenli_nesne(tohum=tohum))[1].tobytes()


@pytest.fixture
def baglanti(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    yield baglanti
    baglanti.close()


# ================================================== 1) parmak izi ve eşleşme


def test_ayni_nesne_yuksek_benzerlik():
    a = parmakizi_cikar(desenli_nesne(tohum=1))
    b = parmakizi_cikar(desenli_nesne(tohum=1))
    assert benzerlik(a, b) > 0.8


def test_farkli_renk_dusuk_benzerlik():
    kirmizi = parmakizi_cikar(desenli_nesne((40, 40, 200), tohum=1))
    yesil = parmakizi_cikar(desenli_nesne((40, 200, 40), tohum=7))
    assert benzerlik(kirmizi, yesil) < VARSAYILAN_ESIK


def test_celiskili_kanit_eslesme_saydirmaz():
    """(a) aynı renk + başka desen → iki ayrı gri pano,
    (b) başka renk + aynı desen → aynı ürünün başka renklisi. İkisi de eşik altında."""
    ayni_renk_baska_desen = benzerlik(
        parmakizi_cikar(desenli_nesne((40, 40, 200), tohum=1)),
        parmakizi_cikar(desenli_nesne((40, 40, 200), tohum=5)),
    )
    baska_renk_ayni_desen = benzerlik(
        parmakizi_cikar(desenli_nesne((40, 40, 200), tohum=1)),
        parmakizi_cikar(desenli_nesne((40, 200, 40), tohum=1)),
    )
    assert ayni_renk_baska_desen < VARSAYILAN_ESIK
    assert baska_renk_ayni_desen < VARSAYILAN_ESIK


def test_desensiz_nesne_yalniz_renkle_kolay_eslesemez():
    duz = np.full((180, 180, 3), (40, 40, 200), dtype=np.uint8)
    desenli = desenli_nesne((40, 40, 200), tohum=1)
    assert benzerlik(parmakizi_cikar(duz), parmakizi_cikar(desenli)) < VARSAYILAN_ESIK
    # Ama düz nesne KENDİSİYLE eşleşebilmeli (yoksa hiç tanınamazdı)
    assert benzerlik(parmakizi_cikar(duz), parmakizi_cikar(duz.copy())) >= VARSAYILAN_ESIK


def test_cok_kucuk_gorselden_parmakizi_cikmaz():
    assert parmakizi_cikar(np.zeros((8, 8, 3), dtype=np.uint8)) is None
    assert parmakizi_cikar(None) is None


def test_esik_altinda_isim_uydurulmaz():
    nesne = Nesne(id=1, ad="Pano", parmakizleri=[parmakizi_cikar(desenli_nesne(tohum=1))])
    bulunan, skor = en_iyi_eslesme(desenli_nesne(tohum=1), [nesne])
    assert bulunan is not None and skor > 0.5
    # Çok farklı görüntü → isim YAZILMAZ
    bulunan, _ = en_iyi_eslesme(desenli_nesne((40, 200, 40), tohum=9), [nesne])
    assert bulunan is None
    # Eşik yükseltilirse zayıf eşleşmeler de elenir
    bulunan, _ = en_iyi_eslesme(desenli_nesne((45, 45, 195), tohum=3), [nesne], esik=0.95)
    assert bulunan is None


def test_kutuphane_bos_ise_eslesme_yok():
    assert en_iyi_eslesme(desenli_nesne(), []) == (None, 0.0)


@pytest.mark.parametrize("esik", [0.20, 0.35, 0.42, 0.55, 0.75, 0.90])
def test_renk_on_elemesi_gercek_eslesmeyi_atmaz(esik):
    """Taramanın hız hilesi sonucu DEĞİŞTİRMEMELİ.

    `renk_alt_siniri(esik)` altındaki renk benzerliğine sahip hiçbir çift,
    desen ne kadar uyarsa uysun eşiği geçemez. Bu kırılırsa tarama, gerçek
    eşleşmeleri sessizce elemeye başlar — en teşhis edilmez hata türü.
    """
    taban = renk_alt_siniri(esik)
    izler = [
        parmakizi_cikar(desenli_nesne(renk, tohum=tohum))
        for renk in ((40, 40, 200), (40, 200, 40), (200, 60, 60), (180, 180, 180))
        for tohum in (1, 2, 3)
    ]
    izler += [
        parmakizi_cikar(np.full((180, 180, 3), renk, dtype=np.uint8))
        for renk in ((40, 40, 200), (200, 200, 200))
    ]
    for a in izler:
        for b in izler:
            if renk_benzerligi(a.renk, b.renk) < taban:
                assert benzerlik(a, b) < esik


# ================================================================ 2) depo


def test_nesne_ve_fotograf_ekleme(baglanti, test_ayarlari):
    nesne_id = depo.nesne_ekle(baglanti, "3. hol yangın dolabı", "kırmızı, cam kapaklı")
    for tohum in (1, 2, 3):
        depo.fotograf_ekle(
            baglanti,
            test_ayarlari.nesne_klasoru,
            nesne_id,
            f"aci{tohum}.jpg",
            jpeg(tohum),
            test_ayarlari.nesne_izinli_uzantilar,
            test_ayarlari.nesne_foto_en_buyuk_mb,
        )
    liste = depo.nesneleri_listele(baglanti)
    assert len(liste) == 1
    assert liste[0]["ad"] == "3. hol yangın dolabı"
    assert liste[0]["aciklama"] == "kırmızı, cam kapaklı"
    assert len(liste[0]["fotolar"]) == 3

    nesneler = depo.nesneleri_yukle(baglanti, test_ayarlari.nesne_klasoru)
    assert len(nesneler) == 1 and len(nesneler[0].parmakizleri) == 3


def _foto_ekle(baglanti, ayarlar, nesne_id, ad, icerik):
    return depo.fotograf_ekle(
        baglanti,
        ayarlar.nesne_klasoru,
        nesne_id,
        ad,
        icerik,
        ayarlar.nesne_izinli_uzantilar,
        ayarlar.nesne_foto_en_buyuk_mb,
    )


def test_ayni_isimde_iki_nesne_olmaz(baglanti):
    depo.nesne_ekle(baglanti, "Pano")
    with pytest.raises(DogrulamaHatasi) as hata:
        depo.nesne_ekle(baglanti, "Pano")
    assert "zaten var" in hata.value.kullanici_mesaji


def test_bos_ad_reddedilir(baglanti):
    with pytest.raises(DogrulamaHatasi):
        depo.nesne_ekle(baglanti, "   ")


def test_desteklenmeyen_uzanti_reddedilir(baglanti, test_ayarlari):
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    with pytest.raises(DogrulamaHatasi) as hata:
        _foto_ekle(baglanti, test_ayarlari, nesne_id, "belge.pdf", b"%PDF-1.4")
    assert "JPG" in hata.value.kullanici_mesaji


def test_cok_buyuk_dosya_reddedilir(baglanti, test_ayarlari):
    """Sınır .env'den gelir; koda gömülü olsaydı sahada değiştirilemezdi."""
    kucuk_sinir = dataclasses.replace(test_ayarlari, nesne_foto_en_buyuk_mb=1)
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    with pytest.raises(DogrulamaHatasi) as hata:
        _foto_ekle(baglanti, kucuk_sinir, nesne_id, "buyuk.jpg", b"x" * (2 * 1024 * 1024))
    assert "1 MB" in hata.value.kullanici_mesaji


def test_bozuk_gorsel_reddedilir_ve_diske_kalmaz(baglanti, test_ayarlari):
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    with pytest.raises(DogrulamaHatasi) as hata:
        _foto_ekle(baglanti, test_ayarlari, nesne_id, "bozuk.jpg", b"bu bir jpeg degil")
    assert "okunamadı" in hata.value.kullanici_mesaji
    assert list(test_ayarlari.nesne_klasoru.glob("*.jpg")) == []  # yarım dosya bırakmadı


def test_nesne_silinince_fotograflari_da_silinir(baglanti, test_ayarlari):
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    ad = _foto_ekle(baglanti, test_ayarlari, nesne_id, "a.jpg", jpeg())
    assert (test_ayarlari.nesne_klasoru / ad).exists()
    depo.nesne_sil(baglanti, test_ayarlari.nesne_klasoru, nesne_id)
    assert not (test_ayarlari.nesne_klasoru / ad).exists()
    assert depo.nesneleri_listele(baglanti) == []
    kalan = baglanti.execute("SELECT COUNT(*) AS n FROM library_object_photos").fetchone()["n"]
    assert kalan == 0  # ON DELETE CASCADE


def test_kayip_dosya_kutuphaneyi_bozmaz(baglanti, test_ayarlari):
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    ad = _foto_ekle(baglanti, test_ayarlari, nesne_id, "a.jpg", jpeg())
    (test_ayarlari.nesne_klasoru / ad).unlink()  # dosya elle silindi
    assert depo.nesneleri_yukle(baglanti, test_ayarlari.nesne_klasoru) == []


# =============================================================== 3) arama


@pytest.fixture
def tek_nesne():
    return [Nesne(id=1, ad="Yangın dolabı", parmakizleri=[parmakizi_cikar(desenli_nesne(tohum=1))])]


def test_taramada_nesne_bulunur(test_ayarlari, tek_nesne):
    gorsel = sahne(desenli_nesne(tohum=1, boyut=120))
    sonuc = arama.tara(
        gorsel, "sahne.jpg", tek_nesne, test_ayarlari.nesne_tarama_klasoru, VARSAYILAN_ESIK
    )
    assert [b.nesne_adi for b in sonuc.bulgular] == ["Yangın dolabı"]
    assert sonuc.bulgular[0].skor >= VARSAYILAN_ESIK
    assert (test_ayarlari.nesne_tarama_klasoru / sonuc.sonuc_gorseli).is_file()


def test_taramada_olmayan_nesne_uydurulmaz(test_ayarlari, tek_nesne):
    """Nesne karede YOKKEN isim yazılmamalı; uyarı ne yapılacağını söylemeli."""
    sonuc = arama.tara(
        sahne(None), "bos.jpg", tek_nesne, test_ayarlari.nesne_tarama_klasoru, VARSAYILAN_ESIK
    )
    assert sonuc.bulgular == []
    assert "Eşleşme bulunamadı" in sonuc.uyari


def test_taramada_baska_nesne_eslesme_saydirmaz(test_ayarlari, tek_nesne):
    baska = desenli_nesne((40, 200, 40), tohum=7, boyut=120)
    sonuc = arama.tara(
        sahne(baska), "baska.jpg", tek_nesne, test_ayarlari.nesne_tarama_klasoru, VARSAYILAN_ESIK
    )
    assert sonuc.bulgular == []


def test_kutuphane_bossa_tarama_yol_gosterir(test_ayarlari):
    sonuc = arama.tara(
        sahne(None), "kare.jpg", [], test_ayarlari.nesne_tarama_klasoru, VARSAYILAN_ESIK
    )
    assert sonuc.bulgular == []
    assert "Önce" in sonuc.uyari
    assert (test_ayarlari.nesne_tarama_klasoru / sonuc.sonuc_gorseli).is_file()


def test_yuksek_cita_eslesmeyi_eler(test_ayarlari, tek_nesne):
    gorsel = sahne(desenli_nesne(tohum=1, boyut=120))
    sonuc = arama.tara(gorsel, "sahne.jpg", tek_nesne, test_ayarlari.nesne_tarama_klasoru, 0.95)
    assert sonuc.bulgular == []
    assert sonuc.en_yuksek_skor > 0  # "en yüksek benzerlik" kullanıcıya söylenir


def test_pencereler_kenari_kapsar_ve_sayisi_sinirli():
    kutular = arama.pencereler(400, 400)
    assert len(kutular) <= arama.EN_COK_PENCERE
    # Sağ ve alt kenara hizalı pencere var mı? (aksi halde kenardaki nesne kaçar)
    assert any(k[2] == 400 for k in kutular)
    assert any(k[3] == 400 for k in kutular)
    # Hiçbir pencere görüntünün dışına taşmaz
    assert all(0 <= k[0] and 0 <= k[1] and k[2] <= 400 and k[3] <= 400 for k in kutular)


def test_eski_taramalar_temizlenir(test_ayarlari):
    for i in range(8):
        (test_ayarlari.nesne_tarama_klasoru / f"tarama-{i:02d}.jpg").write_bytes(b"x")
    arama.eski_taramalari_temizle(test_ayarlari.nesne_tarama_klasoru, en_fazla=3)
    assert len(list(test_ayarlari.nesne_tarama_klasoru.glob("tarama-*.jpg"))) == 3


# ================================================= 4) saklama (retention) koruması


def _eski_yap(dosya: Path, gun: int = 200) -> None:
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_bytes(b"jpeg")
    damga = time_mod.time() - gun * 86400
    os.utime(dosya, (damga, damga))


def test_varsayilan_yerlesimde_nesne_klasoru_goruntu_klasorunun_disinda(tmp_path):
    """Yerleşim kararı: nesne fotoğrafları bakım süpürgesinin ERİŞEMEYECEĞİ yerde.

    Bu ayrılmasaydı, saklama süresi dolunca kullanıcının tanıttığı nesneler
    kanıt fotoğrafı gibi silinirdi.
    """
    from app.ayarlar import ayarlari_yukle

    (tmp_path / ".env").write_text("", encoding="utf-8")
    ayarlar = ayarlari_yukle(tmp_path)
    assert not ayarlar.nesne_klasoru.is_relative_to(ayarlar.goruntu_klasoru)
    assert ayarlar.nesne_tarama_klasoru.is_relative_to(ayarlar.nesne_klasoru)
    assert ayarlar.nesne_klasoru.is_dir() and ayarlar.nesne_tarama_klasoru.is_dir()


def test_bakim_nesne_fotograflarini_silmez(baglanti, test_ayarlari):
    """Nesne fotoğrafı KANIT değil TANIM'dır: saklama süresi ona işlemez.

    Etiketli KKD örnekleri nasıl korunuyorsa (docs/06 §5) kütüphane de öyle
    korunur. Korunmasaydı kullanıcının tanıttığı nesneler 90 gün sonra sessizce
    kaybolur, tarama da sessizce boş dönerdi.
    """
    from app.analiz.supervizor import AnalizSupervizoru
    from app.loglama import log_al

    supervizor = AnalizSupervizoru.__new__(AnalizSupervizoru)  # iş parçacığı başlatmadan
    supervizor.ayarlar = test_ayarlari
    supervizor._log = log_al("test")

    olay_foto = test_ayarlari.goruntu_klasoru / "2026-01" / "olay.jpg"
    nesne_foto = test_ayarlari.nesne_klasoru / "nesne1-abcdef12.jpg"
    tarama_foto = test_ayarlari.nesne_tarama_klasoru / "tarama-0123456789.jpg"
    for dosya in (olay_foto, nesne_foto, tarama_foto):
        _eski_yap(dosya)

    supervizor._bakim_yap(baglanti)

    assert not olay_foto.exists(), "eski olay fotoğrafı silinmeliydi"
    assert nesne_foto.exists(), "nesne kütüphanesi fotoğrafı SİLİNMEMELİYDİ"
    assert tarama_foto.exists(), "tarama çıktısı bakım tarafından silinmemeli"


def test_nesne_klasoru_goruntu_klasorunun_icinde_olsa_da_korunur(baglanti, test_ayarlari):
    """Kullanıcı iki klasörü iç içe ayarlarsa da koruma çalışmalı."""
    from app.analiz.supervizor import AnalizSupervizoru
    from app.loglama import log_al

    ic_ice = dataclasses.replace(
        test_ayarlari,
        nesne_klasoru=test_ayarlari.goruntu_klasoru / "nesneler",
        nesne_tarama_klasoru=test_ayarlari.goruntu_klasoru / "nesneler" / "taramalar",
    )
    supervizor = AnalizSupervizoru.__new__(AnalizSupervizoru)
    supervizor.ayarlar = ic_ice
    supervizor._log = log_al("test")

    nesne_foto = ic_ice.nesne_klasoru / "nesne1-abcdef12.jpg"
    olay_foto = ic_ice.goruntu_klasoru / "2026-01" / "olay.jpg"
    for dosya in (nesne_foto, olay_foto):
        _eski_yap(dosya)

    supervizor._bakim_yap(baglanti)

    assert nesne_foto.exists(), "iç içe kurulumda da nesne fotoğrafı korunmalı"
    assert not olay_foto.exists()


# ================================================================== 5) sayfa


def test_nesneler_sayfasi_aciliyor(istemci):
    yanit = istemci.get("/nesneler")
    assert yanit.status_code == 200
    assert "Nesneler" in yanit.text
    assert "Henüz nesne tanıtılmadı" in yanit.text


def test_sayfada_canli_kamera_uyarisi_var(istemci):
    """Bu cümle KALDIRILAMAZ: özelliğin tek büyük yanlış anlaşılması budur."""
    metin = istemci.get("/nesneler").text
    assert "canlı kameraları ETKİLEMEZ" in metin
    assert "yalnızca" in metin and "yüklediğiniz fotoğraflarda aranır" in metin


def test_nesneler_raftan_ulasilabilir(istemci):
    for yol in ("/komuta", "/komuta/duvar", "/komuta/saglik", "/nesneler"):
        assert 'href="/nesneler"' in istemci.get(yol).text, yol


def test_kilavuzda_nesne_bolumu_ve_alan_farki_var(istemci):
    metin = istemci.get("/komuta/kilavuz").text
    assert "Kendi nesnenizi tanıtma" in metin
    # Bölge (ALAN) ile nesne farkı tek cümlede anlatılmalı
    assert "bölge çizilerek" in metin and "fotoğrafla" in metin


def test_nesne_ekleme_ve_fotograf_yukleme_akisi(istemci):
    yanit = istemci.post(
        "/nesneler/ekle",
        data={"ad": "Yangın dolabı", "aciklama": "kırmızı"},
        files=[("fotograflar", (f"aci{t}.jpg", jpeg(t), "image/jpeg")) for t in (1, 2, 3)],
    )
    assert yanit.status_code == 200
    assert "3 fotoğraf eklendi" in yanit.text
    assert "Yangın dolabı" in yanit.text

    sayfa = istemci.get("/nesneler").text
    assert "3 fotoğraf" in sayfa
    # Referans fotoğraflar sayfadan görüntülenebiliyor
    import re

    dosyalar = re.findall(r'/nesneler/foto/([^"]+)', sayfa)
    assert dosyalar
    assert istemci.get(f"/nesneler/foto/{dosyalar[0]}").status_code == 200


def test_fotografsiz_nesne_eklenemez(istemci):
    """Adı olan ama izi olmayan nesne, taramada hiçbir işe yaramaz — kurulmaz."""
    yanit = istemci.post("/nesneler/ekle", data={"ad": "Boş nesne"})
    assert "Fotoğraf seçilmedi" in yanit.text
    assert "Henüz nesne tanıtılmadı" in yanit.text


def test_bozuk_dosya_yuklenince_turkce_hata(istemci):
    yanit = istemci.post(
        "/nesneler/ekle",
        data={"ad": "Bozuk"},
        files=[("fotograflar", ("bozuk.jpg", b"jpeg degil", "image/jpeg"))],
    )
    assert "okunamadı" in yanit.text
    # Yarım nesne kalmamalı
    assert "Henüz nesne tanıtılmadı" in yanit.text


def test_tarama_akisi_nesneyi_bulur(istemci):
    istemci.post(
        "/nesneler/ekle",
        data={"ad": "Yangın dolabı"},
        files=[("fotograflar", ("a.jpg", jpeg(1), "image/jpeg"))],
    )
    kare = cv2.imencode(".jpg", sahne(desenli_nesne(tohum=1, boyut=120)))[1].tobytes()
    yanit = istemci.post(
        "/nesneler/tara",
        data={"esik_yuzde": "42"},
        files=[("kareler", ("kare.jpg", kare, "image/jpeg"))],
    )
    assert yanit.status_code == 200
    assert "1 eşleşme" in yanit.text
    assert "/nesneler/tarama-foto/" in yanit.text


def test_tarama_eslesme_yoksa_isim_yazmaz(istemci):
    istemci.post(
        "/nesneler/ekle",
        data={"ad": "Yangın dolabı"},
        files=[("fotograflar", ("a.jpg", jpeg(1), "image/jpeg"))],
    )
    kare = cv2.imencode(".jpg", sahne(None))[1].tobytes()
    yanit = istemci.post("/nesneler/tara", files=[("kareler", ("bos.jpg", kare, "image/jpeg"))])
    assert "eşleşme yok" in yanit.text
    assert "Eşleşme bulunamadı" in yanit.text


def test_tarama_dosya_sayisi_siniri(istemci, test_ayarlari):
    kare = cv2.imencode(".jpg", sahne(None))[1].tobytes()
    fazla = test_ayarlari.nesne_tarama_en_cok_dosya + 1
    yanit = istemci.post(
        "/nesneler/tara",
        files=[("kareler", (f"k{i}.jpg", kare, "image/jpeg")) for i in range(fazla)],
    )
    assert f"en fazla {test_ayarlari.nesne_tarama_en_cok_dosya} fotoğraf" in yanit.text


def test_tarama_bozuk_dosyada_durmaz(istemci):
    yanit = istemci.post(
        "/nesneler/tara", files=[("kareler", ("bozuk.jpg", b"jpeg degil", "image/jpeg"))]
    )
    assert yanit.status_code == 200
    assert "açılamadı" in yanit.text


def test_fotograf_yolu_disari_cikamaz(istemci):
    """Yol kaçışı: .env ya da veritabanı bu uçtan sızmamalı."""
    for yol in (
        "/nesneler/foto/..%2F..%2F.env",
        "/nesneler/tarama-foto/..%2F..%2F..%2F.env",
    ):
        assert istemci.get(yol).status_code == 404, yol


def test_nesne_silme(istemci):
    istemci.post(
        "/nesneler/ekle",
        data={"ad": "Silinecek"},
        files=[("fotograflar", ("a.jpg", jpeg(1), "image/jpeg"))],
    )
    import re

    sayfa = istemci.get("/nesneler").text
    nesne_id = re.search(r'action="/nesneler/(\d+)/sil"', sayfa).group(1)
    yanit = istemci.post(f"/nesneler/{nesne_id}/sil")
    assert "silindi" in yanit.text
    assert "Henüz nesne tanıtılmadı" in yanit.text

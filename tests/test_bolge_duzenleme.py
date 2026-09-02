"""Bölgeyi SİLMEDEN düzenleme ve geçici olarak kapatma.

Neden bu testler var:

Bölge yönetiminde iki gerçek boşluk vardı.

1. Güncelleme yoktu. Kullanıcı bölgenin yalnızca ADINI düzeltmek istese bile
   tek yolu bölgeyi silmekti; şemadaki ON DELETE CASCADE yüzünden silme, o
   bölgeye bağlı KURALLARI da götürüyordu. Geri alma yok. Bu dosyadaki en
   kritik test, güncellemenin kuralları silmediğini kanıtlayandır.

2. Geçici kapatma yoktu. `zones.enabled` sütunu şemada vardı ve analizde
   okunuyordu; eksik olan yalnızca rota ve düğmeydi. Bakım/tadilat sırasında
   bölgeyi susturmak için silmek gerekiyordu — yani yine kural kaybı.
"""

from __future__ import annotations

import json
from pathlib import Path

from app import veritabani

_JS = Path("backend/app/web/static/kamera_detay.js")


def _kamera_ekle(istemci, test_ayarlari) -> int:
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")  # form dosyanın varlığını denetler
    yanit = istemci.post(
        "/kameralar/yeni",
        data={"name": "K1", "source_type": "file", "source_url": str(video), "sample_fps": "6"},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return int(yanit.headers["location"].rsplit("/", 1)[1])


def _bolge_ekle(
    istemci,
    test_ayarlari,
    kamera_id: int,
    ad: str = "Rampa",
    tip: str = "pedestrian_path",
    poligon: str = "[[0.1,0.6],[0.9,0.6],[0.9,0.95],[0.1,0.95]]",
) -> int:
    yanit = istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={"name": ad, "zone_type": tip, "polygon": poligon},
        follow_redirects=False,
    )
    assert yanit.status_code == 303, yanit.text
    return _tek_satir(test_ayarlari, "SELECT MAX(id) AS m FROM zones")["m"]


def _tek_satir(test_ayarlari, sorgu: str, parametreler: tuple = ()):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute(sorgu, parametreler).fetchone()
        return dict(satir) if satir is not None else None
    finally:
        baglanti.close()


def _kamera_ve_bolge(istemci, test_ayarlari, tip="pedestrian_path", ad="Yürüyüş yolu"):
    kamera_id = _kamera_ekle(istemci, test_ayarlari)
    return kamera_id, _bolge_ekle(istemci, test_ayarlari, kamera_id, ad=ad, tip=tip)


# ---- 1. EN KRİTİK: güncelleme kuralları silmez ----


def test_bolge_guncellemesi_bagli_kurallari_silmez(istemci, test_ayarlari):
    """Bölgenin adı/tipi/çizimi değişince, o bölgeye bağlı kural OLDUĞU GİBİ
    kalmalı. Eskiden tek yol silmekti ve silme kuralı da götürüyordu."""
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    once = _tek_satir(test_ayarlari, "SELECT * FROM rules WHERE zone_id = ?", (bolge_id,))
    assert once is not None, "hazırlık: kural kurulamadı"

    yanit = istemci.post(
        f"/bolgeler/{bolge_id}/duzenle",
        data={
            "name": "Ana yürüyüş yolu",
            "zone_type": "restricted",
            "polygon": "[[0.2,0.2],[0.8,0.2],[0.8,0.8],[0.2,0.8]]",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert yanit.headers["location"] == f"/kameralar/{kamera_id}"

    sonra = _tek_satir(test_ayarlari, "SELECT * FROM rules WHERE zone_id = ?", (bolge_id,))
    assert sonra is not None, "bölge güncellemesi kuralı SİLDİ — veri kaybı"
    assert sonra["id"] == once["id"]
    assert sonra["params"] == once["params"], "kural parametreleri değişmemeli"
    assert sonra["enabled"] == once["enabled"]
    assert sonra["announcement_id"] == once["announcement_id"]
    sayi = _tek_satir(test_ayarlari, "SELECT COUNT(*) AS n FROM rules")["n"]
    assert sayi == 1, "kural ne silindi ne çoğaldı"


def test_bolge_silme_kurallari_hala_goturuyor(istemci, test_ayarlari):
    """Silmenin davranışı değişmedi (şemadaki CASCADE): bu yüzden ad/çizim
    düzeltmek için SİLME değil, DÜZENLEME kullanılmalı. Ekrandaki uyarı
    metni de bunu söylüyor."""
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)

    # Silme onayı, kullanıcıyı bu tuzaktan haberdar ediyor mu?
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "Sil değil, Düzenle" in detay

    istemci.post(f"/bolgeler/{bolge_id}/sil", follow_redirects=False)
    assert _tek_satir(test_ayarlari, "SELECT COUNT(*) AS n FROM rules")["n"] == 0


# ---- 2. güncellemenin kendisi ----


def test_bolgenin_adi_tipi_ve_cizimi_degistirilir(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    istemci.post(
        f"/bolgeler/{bolge_id}/duzenle",
        data={
            "name": "  Sevkiyat kapısı  ",
            "zone_type": "loading_area",
            "polygon": "[[0.1,0.1],[0.5,0.1],[0.5,0.5]]",
        },
        follow_redirects=False,
    )
    bolge = _tek_satir(test_ayarlari, "SELECT * FROM zones WHERE id = ?", (bolge_id,))
    assert bolge["name"] == "Sevkiyat kapısı", "baştaki/sondaki boşluk temizlenmeli"
    assert bolge["zone_type"] == "loading_area"
    assert json.loads(bolge["polygon"]) == [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5]]

    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "Sevkiyat kapısı" in detay
    assert "Yükleme alanı" in detay


def test_bos_poligon_kayitli_cizimi_korur(istemci, test_ayarlari):
    """Yalnızca adı düzeltmek isteyen kullanıcı çizime dokunmaz; form boş
    poligon gönderir ve kayıtlı çizim OLDUĞU GİBİ kalır."""
    _, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    once = _tek_satir(test_ayarlari, "SELECT polygon FROM zones WHERE id = ?", (bolge_id,))
    istemci.post(
        f"/bolgeler/{bolge_id}/duzenle",
        data={"name": "Yeni ad", "zone_type": "pedestrian_path", "polygon": ""},
        follow_redirects=False,
    )
    sonra = _tek_satir(test_ayarlari, "SELECT * FROM zones WHERE id = ?", (bolge_id,))
    assert sonra["polygon"] == once["polygon"], "çizime dokunulmadıysa korunmalı"
    assert sonra["name"] == "Yeni ad"


def test_gecersiz_guncelleme_bolgeyi_bozmaz(istemci, test_ayarlari):
    """İki noktalı 'alan' ya da boş ad reddedilir; kayıtlı bölge değişmez."""
    _, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    once = _tek_satir(test_ayarlari, "SELECT * FROM zones WHERE id = ?", (bolge_id,))

    yanit = istemci.post(
        f"/bolgeler/{bolge_id}/duzenle",
        data={"name": "X", "zone_type": "restricted", "polygon": "[[0.1,0.1],[0.9,0.1]]"},
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    assert "3 nokta" in yanit.json()["hata"]

    yanit = istemci.post(
        f"/bolgeler/{bolge_id}/duzenle",
        data={"name": "   ", "zone_type": "restricted", "polygon": ""},
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    assert "Bölge adı boş olamaz" in yanit.json()["hata"]

    sonra = _tek_satir(test_ayarlari, "SELECT * FROM zones WHERE id = ?", (bolge_id,))
    assert sonra["name"] == once["name"] and sonra["polygon"] == once["polygon"]
    assert sonra["zone_type"] == once["zone_type"]


def test_olmayan_bolgenin_guncellenmesi_404(istemci, test_ayarlari):
    _kamera_ekle(istemci, test_ayarlari)
    yanit = istemci.post(
        "/bolgeler/999/duzenle",
        data={"name": "Yok", "zone_type": "restricted", "polygon": ""},
        follow_redirects=False,
    )
    assert yanit.status_code == 404
    assert "Bölge bulunamadı" in yanit.json()["hata"]


def test_kkd_kurali_varken_tip_degistirilemez(istemci, test_ayarlari):
    """KKD kuralı YALNIZCA 'KKD zorunlu alan' bölgesinde çalışır. Tip başka bir
    şeye çevrilseydi kural kayıtta kalır ama hiçbir zaman uyarı üretmezdi —
    sessiz başarısızlık. Reddedilir; ne bölge ne kural bozulur."""
    _, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, tip="ppe_required", ad="Kaynakhane")
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)

    yanit = istemci.post(
        f"/bolgeler/{bolge_id}/duzenle",
        data={"name": "Kaynakhane", "zone_type": "restricted", "polygon": ""},
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    assert "KKD" in yanit.json()["hata"]
    bolge = _tek_satir(test_ayarlari, "SELECT * FROM zones WHERE id = ?", (bolge_id,))
    assert bolge["zone_type"] == "ppe_required"
    assert _tek_satir(test_ayarlari, "SELECT COUNT(*) AS n FROM rules")["n"] == 1

    # Aynı bölgenin ADI, tipe dokunulmadan değiştirilebilmeli
    yanit = istemci.post(
        f"/bolgeler/{bolge_id}/duzenle",
        data={"name": "Kaynak bölümü", "zone_type": "ppe_required", "polygon": ""},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert (
        _tek_satir(test_ayarlari, "SELECT name FROM zones WHERE id = ?", (bolge_id,))["name"]
        == "Kaynak bölümü"
    )


# ---- 3. düzenleme ekranı ----


def test_duzenle_baglantisi_ve_dolu_form(istemci, test_ayarlari):
    """'Düzenle' bölgeyi forma yükler: ad, tip ve KAYITLI ÇİZİM hazır gelir."""
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, ad="Ana yol")
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert f"/kameralar/{kamera_id}?duzenle={bolge_id}" in detay, "Düzenle düğmesi yok"

    duzenleme = istemci.get(f"/kameralar/{kamera_id}?duzenle={bolge_id}").text
    assert f'action="/bolgeler/{bolge_id}/duzenle"' in duzenleme
    assert 'value="Ana yol"' in duzenleme, "ad forma yüklenmemiş"
    # Bölge tipi seçili gelmeli: kullanıcı tipi yeniden seçmek zorunda kalmasın
    tip_secenegi = duzenleme.split('<option value="pedestrian_path"', 1)[1][:40]
    assert "selected" in tip_secenegi, "bölge tipi seçili gelmiyor"
    assert "Değişikliği Kaydet" in duzenleme
    assert f'href="/kameralar/{kamera_id}">Vazgeç</a>' in duzenleme
    assert "kurallarını" in duzenleme and "silmez" in duzenleme
    # Kayıtlı çizim gizli alana yazılır: JS çalışmasa bile kaybolmaz
    gizli = duzenleme.split('name="polygon"', 1)[1]
    assert "0.6" in gizli.split(">", 1)[0], "kayıtlı çizim forma yüklenmemiş"


def test_duzenlenen_bolge_tuvalde_iki_kez_cizilmez(istemci, test_ayarlari):
    """Düzenlenen bölge, 'çizilmekte olan bölge' olarak tuvale yüklenir; aynı
    zamanda kayıtlı bölgeler listesinde de kalırsa iki kez çizilir."""
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, ad="Ana yol")
    ikinci = _bolge_ekle(istemci, test_ayarlari, kamera_id, ad="Ikinci", tip="restricted")

    duzenleme = istemci.get(f"/kameralar/{kamera_id}?duzenle={bolge_id}").text
    mevcut = json.loads(duzenleme.split("window.MEVCUT_BOLGELER = ", 1)[1].split(";\n", 1)[0])
    idler = [b["id"] for b in mevcut]
    assert bolge_id not in idler, "düzenlenen bölge kayıtlılar arasında — iki kez çizilir"
    assert ikinci in idler, "diğer bölgeler görünmeye devam etmeli"

    duzenlenen = json.loads(
        duzenleme.split("window.DUZENLENEN_BOLGE = ", 1)[1].split(";</script>", 1)[0]
    )
    assert duzenlenen["id"] == bolge_id
    assert len(duzenlenen["poligon"]) == 4


def test_baska_kameranin_bolgesi_duzenleme_kipini_acmaz(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    ikinci_kamera = _kamera_ekle(istemci, test_ayarlari)
    sayfa = istemci.get(f"/kameralar/{ikinci_kamera}?duzenle={bolge_id}").text
    assert "window.DUZENLENEN_BOLGE = null" in sayfa
    assert "Yeni bölge çiz" in sayfa


def test_js_kayitli_cizimi_tuvale_yukler():
    """Tarayıcı tarafı: düzenlemede kayıtlı köşeler tuvale yüklenmezse kullanıcı
    her düzenlemede bölgeyi baştan çizmek zorunda kalır."""
    kaynak = _JS.read_text(encoding="utf-8")
    assert "window.DUZENLENEN_BOLGE" in kaynak
    assert "kayitliNoktalar" in kaynak
    # Boş çizim "dokunmadım" demektir; kaydet düğmesi o durumda da açık olmalı
    assert "duzenlenen && sayi === 0" in kaynak


# ---- 4. geçici kapatma ----


def test_bolge_kapatilir_ve_acilir(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, ad="Ana yol")
    assert (
        _tek_satir(test_ayarlari, "SELECT enabled FROM zones WHERE id = ?", (bolge_id,))["enabled"]
        == 1
    )

    yanit = istemci.post(
        f"/bolgeler/{bolge_id}/durum", data={"enabled": "0"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert (
        _tek_satir(test_ayarlari, "SELECT enabled FROM zones WHERE id = ?", (bolge_id,))["enabled"]
        == 0
    )

    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "kapalı" in detay, "kapalı bölge listede etiketlenmeli"
    assert 'class="pasif"' in detay, "kapalı bölge satırı soluk görünmeli"
    assert "Aç</button>" in detay, "kapalı bölgenin düğmesi 'Aç' olmalı"

    istemci.post(f"/bolgeler/{bolge_id}/durum", data={"enabled": "1"}, follow_redirects=False)
    assert (
        _tek_satir(test_ayarlari, "SELECT enabled FROM zones WHERE id = ?", (bolge_id,))["enabled"]
        == 1
    )
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "Kapat</button>" in detay


def test_kapatma_kurallari_ve_cizimi_korur(istemci, test_ayarlari):
    """Kapatmak silmek değildir: kural da çizim de yerinde kalır, açınca döner."""
    _, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    istemci.post("/kurallar/hazir", data={"zone_id": str(bolge_id)}, follow_redirects=False)
    once = _tek_satir(test_ayarlari, "SELECT * FROM zones WHERE id = ?", (bolge_id,))

    istemci.post(f"/bolgeler/{bolge_id}/durum", data={"enabled": "0"}, follow_redirects=False)

    assert _tek_satir(test_ayarlari, "SELECT COUNT(*) AS n FROM rules")["n"] == 1
    sonra = _tek_satir(test_ayarlari, "SELECT * FROM zones WHERE id = ?", (bolge_id,))
    assert sonra["polygon"] == once["polygon"]
    assert sonra["name"] == once["name"]


def test_kapali_bolge_analize_kapali_gider(istemci, test_ayarlari):
    """Sütun → analiz bağlantısı: kapalı bölge, kural motoruna 'aktif değil'
    olarak yüklenmeli. Kural motoru pasif bölgeyi zaten değerlendirmiyor
    (tests/rules/test_bolge_ihlali.py), kopan halka bu yükleme olurdu."""
    from app.analiz.supervizor import AnalizSupervizoru

    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    istemci.post(f"/bolgeler/{bolge_id}/durum", data={"enabled": "0"}, follow_redirects=False)

    supervizor = AnalizSupervizoru(test_ayarlari)  # iş parçacığı başlatılmaz
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        bolgeler = supervizor._bolgeleri_yukle(baglanti, kamera_id)
    finally:
        baglanti.close()
    assert len(bolgeler) == 1
    assert bolgeler[0].aktif is False


def test_kapali_bolge_tuvale_cizilmez(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    istemci.post(f"/bolgeler/{bolge_id}/durum", data={"enabled": "0"}, follow_redirects=False)
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    mevcut = json.loads(sayfa.split("window.MEVCUT_BOLGELER = ", 1)[1].split(";\n", 1)[0])
    assert mevcut[0]["aktif"] is False
    # Tuval pasif bölgeyi atlar
    assert "if (bolge.aktif === false) return;" in _JS.read_text(encoding="utf-8")


def test_olmayan_bolgenin_durumu_404(istemci, test_ayarlari):
    _kamera_ekle(istemci, test_ayarlari)
    yanit = istemci.post("/bolgeler/999/durum", data={"enabled": "0"}, follow_redirects=False)
    assert yanit.status_code == 404

"""Kılavuzlu arayüz: ekran açıklamaları, ilk kurulum listesi, kılavuz sayfası,
ipucu balonları ve öğretici boş durumlar.

Bu testlerin var oluş sebebi: sistemi yazılım bilmeyen bir kişi ilk kez
açacak. "Ekran açıldı" yetmez — ekranın NE YAPACAĞINI SÖYLEDİĞİNİ de korumak
gerekir. Buradaki testler üç şeyi kollar:

  1. Kurulum listesindeki her satır GERÇEK veritabanı durumundan gelir; sahte
     ilerleme yoktur ve tamamlanmamış bir adım "tamam" görünmez.
  2. Kılavuz metni teknik iz sızdırmaz (dosya adı, dosya yolu, depo adresi).
  3. Boş listeler "kayıt yok" demez: nedenini söyler ve doğru sayfaya düğme verir.
"""

from __future__ import annotations

import re

import pytest

from app import veritabani, zaman
from app.web.kilavuz import EKRAN_ACIKLAMALARI

KOMUTA_EKRANLARI = (
    "/komuta",
    "/komuta/duvar",
    "/komuta/inceleme",
    "/komuta/saglik",
    "/komuta/uyari",
    "/komuta/anons",
)

KILAVUZ_BOLUMLERI = (
    ("ne-yapar", "Sistem ne yapar"),
    ("baslat", "Nasıl başlatılır"),
    ("kamera", "Kamera nasıl eklenir"),
    ("bolge", "Bölge nasıl çizilir"),
    ("kural", "Kural nasıl kurulur"),
    ("uyari", "Uyarı gelince ne yapılır"),
    ("ayarlar", "Ayarları değiştirme"),
    ("sorun", "Bir şey çalışmazsa"),
)


# ------------------------------------------------------------------ yardımcılar


class SahteSupervizor:
    """Analiz iş parçacığı başlatmadan model durumunu taklit eder.

    Testlerde analiz kapalıdır (conftest: analiz=False), bu yüzden gerçek
    süpervizör yoktur. Kurulum listesinin ilk adımı onun durumunu okur;
    burada yalnızca o iki alan taklit edilir.
    """

    def __init__(self, model_durumu: str = "hazir", tespit_hatasi: str = "") -> None:
        self.model_durumu = model_durumu
        self.tespit_hatasi = tespit_hatasi


def _motoru_hazirla(istemci, durum: str = "hazir", hata: str = "") -> None:
    istemci.app.state.supervizor = SahteSupervizor(durum, hata)


def _kamera_ekle(istemci, ad: str = "Rampa 1", alan: str = "Sevkiyat") -> int:
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": ad,
            "area": alan,
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.5:554/1",
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    return int(yanit.headers["location"].rsplit("/", 1)[1])


def _yaz(test_ayarlari, sql: str, degerler: tuple = ()) -> None:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        baglanti.execute(sql, degerler)
        baglanti.commit()
    finally:
        baglanti.close()


def _kare_geldi(test_ayarlari, kamera_id: int) -> None:
    _yaz(
        test_ayarlari,
        "UPDATE cameras SET status = 'online', last_frame_at = ? WHERE id = ?",
        (zaman.simdi_utc(), kamera_id),
    )


def _bolge_ekle(test_ayarlari, kamera_id: int) -> None:
    _yaz(
        test_ayarlari,
        "INSERT INTO zones (camera_id, name, zone_type, polygon, updated_at) "
        "VALUES (?, 'Yaya yolu', 'pedestrian_path', '[[0.1,0.1],[0.9,0.1],[0.5,0.9]]', ?)",
        (kamera_id, zaman.simdi_utc()),
    )


def _kural_ekle(test_ayarlari, kamera_id: int) -> None:
    _yaz(
        test_ayarlari,
        "INSERT INTO rules (camera_id, rule_type, target_classes, params, updated_at) "
        "VALUES (?, 'zone_intrusion', '[\"person\"]', '{}', ?)",
        (kamera_id, zaman.simdi_utc()),
    )


def _adim_durumu(metin: str, baslik: str) -> str:
    """Kurulum listesindeki bir adımın CSS durum sınıfını okur."""
    kalip = re.compile(
        r'<li class="kurulum-adimi ([a-z]+)">(?:(?!</li>).)*?' + re.escape(baslik),
        re.S,
    )
    eslesme = kalip.search(metin)
    assert eslesme, f"Kurulum listesinde bulunamadı: {baslik}"
    return eslesme.group(1)


def _kurulumu_tamamla(istemci, test_ayarlari) -> int:
    """Beş zorunlu adımı da tamamlar; kamera id'sini döndürür."""
    _motoru_hazirla(istemci)
    kamera = _kamera_ekle(istemci)
    _kare_geldi(test_ayarlari, kamera)
    _bolge_ekle(test_ayarlari, kamera)
    _kural_ekle(test_ayarlari, kamera)
    return kamera


# ==================================================================
# 1) EKRAN AÇIKLAMA ŞERİDİ
# ==================================================================


@pytest.mark.parametrize("yol", KOMUTA_EKRANLARI)
def test_her_ekranda_aciklama_seridi_var(istemci, yol):
    metin = istemci.get(yol).text
    assert 'class="kilavuz-serit"' in metin, f"{yol} → açıklama şeridi yok"
    assert "Bu ekran ne işe yarar:" in metin
    assert "Ne yapmalısınız:" in metin


@pytest.mark.parametrize("yol", KOMUTA_EKRANLARI)
def test_serit_kapatilabilir_ve_geri_getirilebilir(istemci, yol):
    """Kapatma düğmesi VE kapalıyken görünecek geri açma düğmesi birlikte olmalı.

    Geri açma düğmesi olmasaydı, bir kez "Gizle"ye basan kullanıcı ekranın ne
    işe yaradığını bir daha hiçbir yerde bulamazdı.
    """
    metin = istemci.get(yol).text
    assert "data-serit-kapat=" in metin
    assert "data-serit-ac=" in metin
    # Tercih tarayıcıda tutulur: sayfayı kapatan/açan betik yüklenmiş olmalı.
    assert "/static/kilavuz.js?v=" in metin


def test_serit_metni_iki_cumleyi_gecmiyor():
    """Uzun açıklama okunmaz, okunmayan açıklama kapatılır ve bir daha açılmaz."""
    for ekran, metinler in EKRAN_ACIKLAMALARI.items():
        for anahtar in ("ne", "yap"):
            cumle = metinler[anahtar].count(".") + metinler[anahtar].count(";")
            assert cumle <= 2, f"{ekran}.{anahtar} çok uzun: {metinler[anahtar]}"


def test_kilavuz_sayfasinda_serit_yok(istemci):
    """Sayfanın tamamı zaten açıklama; üstüne bir de şerit koymak gürültü olurdu."""
    assert 'class="kilavuz-serit"' not in istemci.get("/komuta/kilavuz").text


# ==================================================================
# 2) İLK KURULUM KONTROL LİSTESİ
# ==================================================================


def test_bos_kurulumda_liste_ilk_adimi_gosteriyor(istemci):
    metin = istemci.get("/komuta").text
    assert "İlk kurulum" in metin
    assert "0 / 5 adım tamam" in metin
    assert "Henüz kamera eklenmedi" in metin
    assert 'href="/kameralar/yeni">Kamera ekle</a>' in metin


def test_sirasi_gelmeyen_adim_soluk_ve_dugmesiz(istemci):
    """Kullanıcı her an TEK bir sonraki hamle görmeli."""
    metin = istemci.get("/komuta").text
    assert _adim_durumu(metin, "En az bir kamera eklendi mi?") == "sira"
    assert _adim_durumu(metin, "Kamera görüntü veriyor mu?") == "beklemede"
    assert _adim_durumu(metin, "En az bir bölge çizildi mi?") == "beklemede"
    assert _adim_durumu(metin, "En az bir kural kuruldu mu?") == "beklemede"
    # Sırası gelmemiş adımın düğmesi çizilmez
    assert "Bölge çiz</a>" not in metin


def test_kamera_eklenince_sonraki_adim_aciliyor(istemci):
    _kamera_ekle(istemci)
    metin = istemci.get("/komuta").text
    assert _adim_durumu(metin, "En az bir kamera eklendi mi?") == "tamam"
    assert _adim_durumu(metin, "Kamera görüntü veriyor mu?") == "sira"
    assert "1 kamera tanımlı." in metin
    assert "1 / 5 adım tamam" in metin


def test_goruntu_gelince_bolge_adimi_aciliyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci)
    _kare_geldi(test_ayarlari, kamera)
    metin = istemci.get("/komuta").text
    assert _adim_durumu(metin, "Kamera görüntü veriyor mu?") == "tamam"
    assert _adim_durumu(metin, "En az bir bölge çizildi mi?") == "sira"
    # Bölge çizimi kamera sayfasındadır; bağlantı oraya gitmeli
    assert f'href="/kameralar/{kamera}#bolge-formu"' in metin


def test_bolge_cizilince_kural_adimi_aciliyor(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci)
    _kare_geldi(test_ayarlari, kamera)
    _bolge_ekle(test_ayarlari, kamera)
    metin = istemci.get("/komuta").text
    assert _adim_durumu(metin, "En az bir bölge çizildi mi?") == "tamam"
    assert _adim_durumu(metin, "En az bir kural kuruldu mu?") == "sira"
    # Hazır kural düğmesi bölgenin bulunduğu kameranın sayfasındadır
    assert f'href="/kameralar/{kamera}">Hazır kural ekle</a>' in metin


def test_kurulum_bitince_liste_rozete_donuyor(istemci, test_ayarlari):
    _kurulumu_tamamla(istemci, test_ayarlari)
    metin = istemci.get("/komuta").text
    assert "Sistem hazır." in metin
    assert 'class="kurulum-listesi"' not in metin
    # Rozete dönen kurulum, panonun kendisini gizlememeli
    assert "Alanlara göre ihlal yoğunluğu" in metin


def test_anons_istege_bagli_kurulumu_engellemiyor(istemci, test_ayarlari):
    """Test ayarlarında ANONS kapalıdır; sistem yine de "hazır" sayılmalı."""
    _kurulumu_tamamla(istemci, test_ayarlari)
    assert istemci.app.state.ayarlar.anons == "null"
    assert "Sistem hazır." in istemci.get("/komuta").text


def test_anons_adimi_istege_bagli_etiketli(istemci):
    metin = istemci.get("/komuta").text
    assert "Sesli anons kuruldu mu?" in metin
    assert "isteğe bağlı" in metin


def test_model_hazirlanirken_kamera_adimi_yine_de_acik(istemci):
    """Model inerken kurulumu durdurmak, kullanıcıyı boş yere bekletirdi."""
    _motoru_hazirla(istemci, "indiriliyor")
    metin = istemci.get("/komuta").text
    assert _adim_durumu(metin, "Tespit motoru hazır mı?") == "calisiyor"
    assert _adim_durumu(metin, "En az bir kamera eklendi mi?") == "sira"


def test_model_hatasi_adimda_gorunuyor(istemci):
    _motoru_hazirla(istemci, "hata", "NextGen AI Hızlı başlatılamadı. Kontrol Paneli'nde…")
    metin = istemci.get("/komuta").text
    assert _adim_durumu(metin, "Tespit motoru hazır mı?") == "sorun"
    assert "NextGen AI Hızlı başlatılamadı." in metin


def test_kurulum_listesi_gercek_sayilari_gosteriyor(istemci):
    _kamera_ekle(istemci, "Rampa 1", "Sevkiyat")
    _kamera_ekle(istemci, "Rampa 2", "Sevkiyat")
    metin = istemci.get("/komuta").text
    assert "2 kamera tanımlı." in metin


def test_kurulum_listesinde_tasarimin_ornek_verisi_yok(istemci):
    metin = istemci.get("/komuta").text
    for sahte in ("24 kamera", "6 bölüm", "34 ihlal", "192.168.1.4"):
        assert sahte not in metin, f"Tasarımdan sahte veri sızmış: {sahte}"


# ==================================================================
# 3) KILAVUZ SAYFASI
# ==================================================================


def test_kilavuz_sayfasi_aciliyor(istemci):
    yanit = istemci.get("/komuta/kilavuz")
    assert yanit.status_code == 200
    assert "Kullanım kılavuzu" in yanit.text


@pytest.mark.parametrize(("cengel", "baslik"), KILAVUZ_BOLUMLERI)
def test_kilavuzda_her_bolum_ve_icindekiler_var(istemci, cengel, baslik):
    metin = istemci.get("/komuta/kilavuz").text
    assert f'id="{cengel}"' in metin, f"Kılavuzda bölüm yok: {cengel}"
    assert f'href="#{cengel}"' in metin, f"İçindekilerde bağlantı yok: {cengel}"
    assert baslik in metin


def test_kilavuz_ilgili_ekranlara_baglaniyor(istemci):
    metin = istemci.get("/komuta/kilavuz").text
    for hedef in (
        "/kameralar/yeni",
        "/kameralar",
        "/kurallar",
        "/komuta/inceleme",
        "/komuta/saglik",
        "/komuta/uyari",
        "/olaylar",
        "/komuta",
    ):
        assert f'href="{hedef}"' in metin, f"Kılavuzdan {hedef} ekranına bağlantı yok"


@pytest.mark.parametrize("yol", (*KOMUTA_EKRANLARI, "/komuta/kilavuz"))
def test_kilavuz_raftan_her_ekrandan_ulasilabilir(istemci, yol):
    assert 'href="/komuta/kilavuz"' in istemci.get(yol).text


def test_kilavuzda_baslatma_ve_durdurma_anlatiliyor(istemci):
    metin = istemci.get("/komuta/kilavuz").text
    assert "Kontrol Paneli" in metin
    assert "Sistemi Başlat" in metin
    assert "Durdur" in metin
    assert "çift tıklayın" in metin


def test_kilavuzda_cizim_kolayliklari_anlatiliyor(istemci):
    """Çizim kolaylıkları anlatılmazsa kullanıcı onları hiç keşfetmez."""
    metin = istemci.get("/komuta/kilavuz").text
    assert "ilk nokta büyür" in metin
    assert "Son köşeyi geri al" in metin
    assert "Esc" in metin


def test_kilavuzda_yanlis_alarm_isaretlemesi_anlatiliyor(istemci):
    metin = istemci.get("/komuta/kilavuz").text
    assert "Yanlış alarm" in metin
    assert "Doğru uyarı" in metin


def test_kilavuzdaki_sorun_giderme_gercek_hata_metinlerini_kullaniyor(istemci):
    """Uydurulmuş hata cümlesi, kullanıcının ekranda gördüğüyle eşleşmez."""
    from app.analiz.kamera import KameraKaynagi

    kaynak = KameraKaynagi(1, "Rampa", "rtsp", "rtsp://10.0.0.5:554/1")
    gercek = kaynak._acilamama_sebebi()
    metin = istemci.get("/komuta/kilavuz").text
    # Ekranda görünen cümlenin ayırt edici parçası kılavuzda da geçmeli
    assert "Kullanıcı adı, şifre veya akış yolu yanlış olabilir" in gercek
    assert "Kullanıcı adı, şifre veya akış yolu yanlış olabilir" in metin
    assert "Kameraya ağ üzerinden ulaşılamıyor" in metin
    assert "Video dosyası bulunamadı" in metin


def test_kilavuzda_teknik_iz_yok(istemci):
    """Kullanıcıya görünen metinde dosya adı, uzantı, depo adresi olmamalı."""
    metin = istemci.get("/komuta/kilavuz").text.lower()
    for parca in ("yolox", ".onnx", "megvii", "github.com", "indir.sh", "models/"):
        assert parca not in metin, f"Kılavuza teknik iz sızmış: {parca}"


def test_kilavuzda_mutlak_dosya_yolu_yok(istemci):
    """Örnek olarak bile mutlak yol yazılmaz: her bilgisayarda farklıdır."""
    izler = re.findall(
        r"(?:[A-Za-z]:\\|/(?:Users|home|private|var|tmp|opt)/)", istemci.get("/komuta/kilavuz").text
    )
    assert not izler, f"Kılavuzda mutlak dosya yolu var: {sorted(set(izler))}"


def test_kilavuzda_tasarimin_ornek_verisi_yok(istemci):
    metin = istemci.get("/komuta/kilavuz").text
    for sahte in ("24 kamera", "6 bölüm", "7 bölge", "34 ihlal", "Vardiya 08:00"):
        assert sahte not in metin, f"Tasarımdan sahte veri: {sahte}"


def test_kilavuz_kurulum_durumunu_gercek_veriden_gosteriyor(istemci, test_ayarlari):
    assert "0 / 5 adımı tamam" in istemci.get("/komuta/kilavuz").text
    _kurulumu_tamamla(istemci, test_ayarlari)
    assert "Kurulumunuz tamam." in istemci.get("/komuta/kilavuz").text


# ==================================================================
# 4) İPUCU BALONLARI
# ==================================================================


def _ipuclari(metin: str) -> list[str]:
    return re.findall(r'aria-controls="(ipucu-[a-z0-9-]+)"', metin)


def test_kural_formunda_karmasik_alanlarin_ipucu_var(istemci):
    _kamera_ekle(istemci)
    metin = istemci.get("/kurallar/yeni").text
    for anahtar in (
        "ipucu-cooldown",
        "ipucu-golge-mod",
        "ipucu-mesafe-esigi",
        "ipucu-kkd-guven",
        "ipucu-kkd-pencere",
    ):
        assert f'id="{anahtar}"' in metin, f"İpucu yok: {anahtar}"
    assert 'class="ipucu-dugme"' in metin


def test_ipucu_klavyeyle_acilabiliyor(istemci):
    """Balon gerçek bir <button> olmalı: fare olmadan da açılabilsin."""
    _kamera_ekle(istemci)
    metin = istemci.get("/kurallar/yeni").text
    assert '<button type="button" class="ipucu-dugme" aria-expanded="false"' in metin
    assert 'role="tooltip"' in metin


def test_ipucu_anahtarlari_sayfada_benzersiz(istemci):
    _kamera_ekle(istemci)
    for yol in ("/kurallar/yeni", "/kameralar/1", "/komuta/uyari"):
        anahtarlar = _ipuclari(istemci.get(yol).text)
        assert len(anahtarlar) == len(set(anahtarlar)), f"{yol} → aynı ipucu id'si iki kez"


def test_kalibrasyon_ipucu_kamera_sayfasinda(istemci):
    kamera = _kamera_ekle(istemci)
    metin = istemci.get(f"/kameralar/{kamera}").text
    assert 'id="ipucu-kalibrasyon"' in metin
    assert "piksel" in metin and "metre" in metin


def test_golge_mod_ipucu_uyari_ekraninda(istemci, test_ayarlari):
    kamera = _kamera_ekle(istemci)
    _kural_ekle(test_ayarlari, kamera)
    metin = istemci.get("/komuta/uyari").text
    assert 'id="ipucu-zincir-golge"' in metin


# ==================================================================
# 5) ÖĞRETİCİ BOŞ DURUMLAR
# ==================================================================


@pytest.mark.parametrize(
    ("yol", "beklenen_dugme"),
    [
        ("/kameralar", "/kameralar/yeni"),
        ("/kurallar", "/kameralar"),
        ("/olaylar", "/kurallar"),
        ("/kkd", "/kameralar"),
    ],
)
def test_bos_listede_yol_gosteren_dugme_var(istemci, yol, beklenen_dugme):
    """Boş liste "kayıt yok" demez: nedenini söyler ve doğru sayfaya götürür."""
    metin = istemci.get(yol).text
    assert f'href="{beklenen_dugme}"' in metin, f"{yol} → boş durumda düğme yok"
    assert 'class="dugme' in metin


def test_bos_kural_listesi_neden_uyari_gelmedigini_soyluyor(istemci):
    metin = istemci.get("/kurallar").text
    assert "hiçbir uyarı üretmiyor" in metin
    assert 'href="/komuta/kilavuz#kural"' in metin


def test_olay_listesinde_iki_farkli_bos_durum_var(istemci):
    """Filtre yüzünden boş olmakla hiç olay olmaması aynı şey değildir."""
    hic = istemci.get("/olaylar").text
    assert "Henüz hiç olay kaydedilmedi." in hic

    filtreli = istemci.get("/olaylar?durum=reviewed").text
    assert "Bu filtreyle olay bulunamadı." in filtreli
    assert 'href="/olaylar">Filtreyi temizle</a>' in filtreli


def test_bolgesiz_kamerada_ne_yapilacagi_yaziyor(istemci):
    kamera = _kamera_ekle(istemci)
    metin = istemci.get(f"/kameralar/{kamera}").text
    assert "bu kamera hiçbir kural değerlendiremez" in metin
    assert 'href="/komuta/kilavuz#bolge"' in metin


# ==================================================================
# 6) TARAYICIDA BULUNAN HATANIN NÖBETÇİSİ
# ==================================================================


def test_hidden_ozniteligi_her_zaman_gizler():
    """Tarayıcıda görülüp düzeltilen gerçek bir hatanın nöbetçisi.

    Tarayıcının kendi `[hidden]{display:none}` kuralı en düşük önceliklidir;
    bizim `.kilavuz-serit { display: grid }` kuralımız onu sessizce eziyordu.
    Sonuç: "Gizle"ye basınca şerit kaybolmuyor, altına ikinci bir düğme
    ekleniyordu. Aynı tuzak ipucu balonunda da (display: block) vardı.
    """
    from pathlib import Path

    stil = (
        Path(__file__).resolve().parents[1] / "backend" / "app" / "web" / "static" / "stil.css"
    ).read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in stil, (
        "stil.css'teki genel [hidden] kuralı kaldırılmış: gizlenen şerit ve "
        "ipucu balonları ekranda durmaya devam eder."
    )

"""Uyarı zinciri: kural formu, anons sayfası, sağlık ucu ve silme onayı.

Bu dosyanın konusu "ihlal olduğunda kullanıcı bunu gerçekten duyuyor mu" —
sistemin var oluş sebebi budur (docs/01 §1).
"""

from __future__ import annotations

import json

from app import veritabani, zaman


def _kamera_ve_bolge(istemci, test_ayarlari, bolge_tipi="ppe_required", ad="Rampa"):
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "K1",
            "source_type": "file",
            "source_url": str(video),
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": ad,
            "zone_type": bolge_tipi,
            "polygon": "[[0.1,0.1],[0.9,0.1],[0.9,0.9]]",
        },
        follow_redirects=False,
    )
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        bolge_id = baglanti.execute("SELECT MAX(id) AS m FROM zones").fetchone()["m"]
    finally:
        baglanti.close()
    return kamera_id, bolge_id


# ---- kural formu: aynı adlı iki alan ----


def test_bolge_ihlali_kalis_suresi_kaydedilir(istemci, test_ayarlari):
    """ESKİ HATA: formda iki alan da name='min_dwell_s' taşıyordu; KKD
    fieldset'indeki gizli alan bölge ihlalininkini eziyordu ve kullanıcının
    girdiği kalış süresi SESSİZCE yok sayılıyordu."""
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, "loading_area")
    yanit = istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": str(kamera_id),
            "rule_type": "zone_intrusion",
            "zone_id": str(bolge_id),
            "target_classes": "person",
            "mode": "inside",
            "min_dwell_s": "7.5",
            "cooldown_s": "60",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        params = json.loads(baglanti.execute("SELECT params FROM rules").fetchone()["params"])
    finally:
        baglanti.close()
    assert params["min_dwell_s"] == 7.5


def test_gizli_alanlar_gonderilmesin_diye_fieldset_kapatilir(istemci, test_ayarlari):
    """Şablon tarafındaki koruma: görünmeyen fieldset disabled olmalı."""
    _kamera_ve_bolge(istemci, test_ayarlari)
    form = istemci.get("/kurallar/yeni").text
    assert "kutu.disabled = !secili" in form


def test_kkd_kurali_yanlis_bolge_tipine_baglanamaz(istemci, test_ayarlari):
    """KKD kuralı 'KKD zorunlu alan' dışında bir bölgeye bağlanırsa kaydedilir
    ama HİÇ çalışmazdı — sessiz başarısızlık."""
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari, "loading_area")
    yanit = istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": str(kamera_id),
            "rule_type": "ppe_violation",
            "zone_id": str(bolge_id),
            "required_ppe": "helmet",
            "cooldown_s": "120",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    assert "KKD zorunlu alan" in yanit.json()["hata"]


# ---- silme onayı ----


def test_kesme_isaretli_ad_onayi_bozmaz(istemci, test_ayarlari):
    """ESKİ HATA: onay metni onsubmit içine gömülüydü; adında kesme işareti olan
    kamera ("Rampa 1'in önü") JS'i bozup onay SORULMADAN siliniyordu."""
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Rampa 1'in önü",
            "source_type": "file",
            "source_url": str(video),
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    detay = istemci.get(f"/kameralar/{kamera_id}").text
    assert "onsubmit=" not in detay, "onay metni JS kaynağına gömülmemeli"
    assert "data-onay=" in detay


# ---- anons ----


def test_anons_sayfasi_mesajlari_listeler(istemci):
    metin = istemci.get("/anons").text
    assert "Anons mesajları" in metin
    assert "Lütfen baretinizi takınız." in metin
    assert "Anonsu Dene" in metin


def test_anons_metni_kaydedilir(istemci, test_ayarlari):
    yanit = istemci.post(
        "/anons/1/kaydet",
        data={"text": "Lütfen güvenli mesafeyi koruyunuz.", "audio_file": "", "enabled": "1"},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute("SELECT text FROM announcement_messages WHERE id = 1").fetchone()
    finally:
        baglanti.close()
    assert satir["text"] == "Lütfen güvenli mesafeyi koruyunuz."


def test_bos_anons_metni_reddedilir(istemci):
    yanit = istemci.post(
        "/anons/1/kaydet", data={"text": "   ", "enabled": "1"}, follow_redirects=False
    )
    assert yanit.status_code == 400


def test_olmayan_ses_dosyasi_reddedilir(istemci):
    yanit = istemci.post(
        "/anons/1/kaydet",
        data={"text": "Deneme", "audio_file": "veri/sesler/yok.wav", "enabled": "1"},
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    assert "bulunamadı" in yanit.json()["hata"]


def test_ses_dosyasi_proje_disina_cikamaz(istemci):
    yanit = istemci.post(
        "/anons/1/kaydet",
        data={"text": "Deneme", "audio_file": "../../etc/passwd", "enabled": "1"},
        follow_redirects=False,
    )
    assert yanit.status_code == 400


def test_analiz_kapaliyken_anons_denemesi_anlasilir_hata(istemci):
    yanit = istemci.post("/anons/1/dene", follow_redirects=False)
    assert yanit.status_code == 400
    assert "Analiz çalışmıyor" in yanit.json()["hata"]


def test_anons_bloklamadan_calar(test_ayarlari, monkeypatch):
    """HTTP anons sunucusu yanıt vermezse analiz iş parçacığı BEKLEMEMELİ:
    tek analiz iş parçacığı durursa TÜM kameralar kör kalır."""
    import time

    from app.olaylar.anons import AnonsYoneticisi

    yonetici = AnonsYoneticisi(test_ayarlari)

    def yavas_cal(anahtar, metin, ses):
        time.sleep(1.5)

    monkeypatch.setattr(yonetici._anonscu, "cal", yavas_cal)
    basladi = time.monotonic()
    yonetici.hemen_cal({"id": 1, "key": "helmet", "text": "Baret", "enabled": 1})
    gecen = time.monotonic() - basladi
    assert gecen < 0.5, f"anons çağrısı analiz döngüsünü {gecen:.2f} sn bloklamış"


# ---- sağlık ucu ----


def test_saglik_ucu_ucuz_ve_calisiyor(istemci):
    yanit = istemci.get("/saglik")
    assert yanit.status_code == 200
    veri = yanit.json()
    assert veri["durum"] == "calisiyor"
    assert veri["analiz"] is False  # testte analiz kapalı


# ---- canlı sayım ----


def test_canli_sayim_durum_jsonda_gelir(istemci, test_ayarlari):
    video = test_ayarlari.kok_dizin / "v.mp4"
    video.write_bytes(b"sahte")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "K1",
            "source_type": "file",
            "source_url": str(video),
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    veri = istemci.get(f"/kameralar/{kamera_id}/durum.json").json()
    assert "sayim" in veri


def test_ana_sayfada_canli_sayim_kutulari_var(istemci):
    metin = istemci.get("/").text
    assert "Canlı durum" in metin
    assert "son 24 saatte ihlal" in metin
    assert "incelenmemiş ihlal" in metin


def test_cevrimdisi_kamera_son_kare_zamanini_korur(test_ayarlari):
    """ "En son ne zaman görüntü geldi" bilgisi, kamera koptuğunda en çok
    ihtiyaç duyulan bilgidir; silinmemeli."""
    from app.analiz.kamera import DURUM_OFFLINE, DURUM_ONLINE

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        simdi = zaman.simdi_utc()
        baglanti.execute(
            "INSERT INTO cameras (name, source_type, source_url, status, last_frame_at, "
            "created_at, updated_at) VALUES ('K1','file','v.mp4',?,?,?,?)",
            (DURUM_ONLINE, simdi, simdi, simdi),
        )
        baglanti.commit()
        # Süpervizörün çevrimdışı dalında yaptığı güncelleme
        baglanti.execute(
            "UPDATE cameras SET status = ?, measured_fps = NULL WHERE id = 1", (DURUM_OFFLINE,)
        )
        baglanti.commit()
        satir = baglanti.execute("SELECT * FROM cameras WHERE id = 1").fetchone()
        assert satir["last_frame_at"] == simdi
    finally:
        baglanti.close()

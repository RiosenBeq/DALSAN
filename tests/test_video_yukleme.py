"""Video yükleyip kamerasız deneme (web/videolar.py + şema 006).

Bu testlerin bakmaya çalıştığı asıl soru şudur: kamerası olmayan bir kullanıcı,
elindeki bir video dosyasıyla sistemi baştan sona deneyebiliyor mu? Yani dosya
yükleniyor, bir kameraya dönüşüyor, üzerine bölge çizilebiliyor ve tek geçişte
"analiz bitti" diyebiliyor mu.

Gerçek bir video ÇÖZÜLMEZ: OpenCV'nin bir .mp4'ü açması bu testlerin konusu
değil (o, kamera katmanının işi ve tests/test_kamera_kaynagi.py'de ölçülüyor).
Burada web katmanı sınanır: doğrulama, dosyanın nereye yazıldığı, yarım
dosyanın bırakılmaması ve kamera satırının doğru kurulması.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest


def _yukle(istemci, ad="depo.mp4", icerik=b"sahte-video-verisi", **form):
    alanlar = {"name": "", "sample_fps": "6", "tek_gecis": "1"}
    alanlar.update({k: str(v) for k, v in form.items()})
    return istemci.post(
        "/videolar/yukle",
        files={"video": (ad, io.BytesIO(icerik), "video/mp4")},
        data=alanlar,
        follow_redirects=False,
    )


def _hata_metni(yanit) -> str:
    """303 yanıtındaki ?hata=… parametresini okunur metne çevirir."""
    from urllib.parse import unquote

    konum = yanit.headers["location"]
    return unquote(konum.split("hata=", 1)[1]) if "hata=" in konum else ""


# ---------------------------------------------------------------- mutlu yol


def test_yuklenen_video_kamera_olarak_kurulur(istemci, test_ayarlari):
    yanit = _yukle(istemci, "Sevkiyat Rampasi.mp4")
    assert yanit.status_code == 303
    # Doğrudan kamera sayfasına gidilmeli: sıradaki iş bölgeleri çizmek.
    assert yanit.headers["location"].startswith("/kameralar/")

    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    detay = istemci.get(f"/kameralar/{kamera_id}")
    assert detay.status_code == 200
    assert "Sevkiyat Rampasi" in detay.text

    yazilanlar = list(test_ayarlari.video_klasoru.iterdir())
    assert len(yazilanlar) == 1
    assert yazilanlar[0].read_bytes() == b"sahte-video-verisi"


def test_ad_verilmezse_dosya_adi_kullanilir(istemci):
    _yukle(istemci, "gece-vardiyasi.mp4")
    assert "gece-vardiyasi" in istemci.get("/videolar").text


def test_verilen_ad_dosya_adini_ezer(istemci):
    _yukle(istemci, "IMG_0042.mp4", name="Rampa önü — sabah")
    sayfa = istemci.get("/videolar").text
    assert "Rampa önü — sabah" in sayfa


def test_yuklenen_video_kameralar_listesinde_de_gorunur(istemci):
    """Yüklenen video SIRADAN bir kameradır; ayrı bir dünyada yaşamaz."""
    _yukle(istemci, "depo.mp4", name="Depo denemesi")
    assert "Depo denemesi" in istemci.get("/kameralar").text


def test_kameralar_sayfasi_video_sayfasina_yol_gosterir(istemci):
    """Kamerası olmayan kullanıcı bu sayfayı kendi bulmak zorunda kalmamalı."""
    assert "/videolar" in istemci.get("/kameralar").text


# ------------------------------------------------------------- doğrulamalar


def test_dosya_secilmezse_turkce_hata(istemci):
    yanit = istemci.post(
        "/videolar/yukle",
        data={"name": "", "sample_fps": "6"},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert "Dosya seçilmedi" in _hata_metni(yanit)


def test_video_olmayan_uzanti_reddedilir(istemci, test_ayarlari):
    yanit = _yukle(istemci, "rapor.pdf")
    assert "desteklenmiyor" in _hata_metni(yanit)
    # Reddedilen dosya diske YAZILMAMALI.
    assert list(test_ayarlari.video_klasoru.iterdir()) == []


def test_bos_dosya_reddedilir_ve_diskte_iz_birakmaz(istemci, test_ayarlari):
    yanit = _yukle(istemci, "bos.mp4", icerik=b"")
    assert "boş" in _hata_metni(yanit)
    assert list(test_ayarlari.video_klasoru.iterdir()) == []


def test_sinirdan_buyuk_video_yarim_dosya_birakmaz(istemci, test_ayarlari):
    """Yarım kalan bir video AÇILIR ve bir yerinde biter.

    Analiz onu sorunsuz oynatır; kullanıcı eksik sonucu tam sanar. Bu yüzden
    sınır aşılınca yazılanların silinmesi, hata mesajından daha önemlidir.
    """
    buyuk = b"x" * ((test_ayarlari.video_en_buyuk_mb + 1) * 1024 * 1024)
    yanit = _yukle(istemci, "cok-buyuk.mp4", icerik=buyuk)
    assert "çok büyük" in _hata_metni(yanit)
    assert list(test_ayarlari.video_klasoru.iterdir()) == []


def test_gecersiz_fps_reddedilir(istemci):
    assert "Örnekleme hızı" in _hata_metni(_yukle(istemci, "a.mp4", sample_fps="99"))


# ------------------------------------------------- dosya adı güvenliği (yol)


@pytest.mark.parametrize(
    "ad",
    [
        "../../../../.env.mp4",
        "..\\..\\Windows\\System32\\x.mp4",
        "/etc/passwd.mp4",
        "C:\\Users\\kurban\\gizli.mp4",
    ],
)
def test_dosya_adi_klasorun_disina_yazdiramaz(istemci, test_ayarlari, ad):
    """Dosya adı İSTEMCİDEN gelir; bir yol parçası olarak kullanılamaz."""
    yanit = _yukle(istemci, ad)
    assert yanit.status_code == 303
    yazilanlar = list(test_ayarlari.video_klasoru.iterdir())
    assert len(yazilanlar) == 1
    # Yazılan dosya GERÇEKTEN video klasörünün altında (sembolik yol yok).
    assert yazilanlar[0].resolve().parent == test_ayarlari.video_klasoru.resolve()
    assert ".." not in yazilanlar[0].name


def test_ayni_ad_iki_kez_yuklenince_ustune_yazilmaz(istemci, test_ayarlari):
    _yukle(istemci, "depo.mp4", icerik=b"birinci")
    _yukle(istemci, "depo.mp4", icerik=b"ikinci")
    icerikler = {y.read_bytes() for y in test_ayarlari.video_klasoru.iterdir()}
    assert icerikler == {b"birinci", b"ikinci"}


def test_turkce_ad_ascii_dosya_adina_iner():
    """Windows ↔ Mac kopyalamasında bozulmayan bir dosya adı üretilmeli."""
    from app.web.videolar import dosya_adini_sadelestir

    assert dosya_adini_sadelestir("Şırınga Ölçüm çekimi.mp4") == "Siringa-Olcum-cekimi"
    assert dosya_adini_sadelestir("../../gizli") == "gizli"
    assert dosya_adini_sadelestir("...") == ""


# --------------------------------------------------- tek geçiş / döngü seçimi


def test_tek_gecis_isaretliyse_loop_video_kapali(istemci, test_ayarlari):
    from app import veritabani

    yanit = _yukle(istemci, "a.mp4", tek_gecis="1")
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute(
            "SELECT loop_video FROM cameras WHERE id = ?", (kamera_id,)
        ).fetchone()
    finally:
        baglanti.close()
    assert satir["loop_video"] == 0
    assert "tek geçiş" in istemci.get("/videolar").text


def test_isaret_kaldirilirsa_video_donguye_girer(istemci, test_ayarlari):
    from app import veritabani

    yanit = istemci.post(
        "/videolar/yukle",
        files={"video": ("a.mp4", io.BytesIO(b"veri"), "video/mp4")},
        data={"name": "", "sample_fps": "6"},  # onay kutusu işaretsiz: alan HİÇ gelmez
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute(
            "SELECT loop_video FROM cameras WHERE id = ?", (kamera_id,)
        ).fetchone()
    finally:
        baglanti.close()
    assert satir["loop_video"] == 1
    assert "sürekli döner" in istemci.get("/videolar").text


# ------------------------------------------------ yeniden çalıştır / duraklat


def test_yeniden_calistir_damgayi_tazeler(istemci, test_ayarlari):
    """Damga tazelenmezse süpervizör biten videoyu yeniden kurmaz.

    Bu, düğmenin hiçbir şey yapmadığı ama hata da vermediği bir durumdur —
    kullanıcı basar, bekler ve sebebini asla öğrenemez.
    """
    from app import veritabani

    kamera_id = int(_yukle(istemci, "a.mp4").headers["location"].rsplit("/", 1)[1])
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        onceki = baglanti.execute(
            "SELECT updated_at FROM cameras WHERE id = ?", (kamera_id,)
        ).fetchone()["updated_at"]
        baglanti.execute(
            "UPDATE cameras SET status = 'finished', enabled = 0, "
            "updated_at = '2000-01-01T00:00:00Z' WHERE id = ?",
            (kamera_id,),
        )
        baglanti.commit()
    finally:
        baglanti.close()

    yanit = istemci.post(f"/videolar/{kamera_id}/yeniden", follow_redirects=False)
    assert yanit.status_code == 303

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute(
            "SELECT enabled, status, updated_at FROM cameras WHERE id = ?", (kamera_id,)
        ).fetchone()
    finally:
        baglanti.close()
    assert satir["enabled"] == 1
    assert satir["status"] != "finished"
    assert satir["updated_at"] > "2000-01-01T00:00:00Z"
    assert onceki  # ilk kayıtta damga zaten yazılmıştı


def test_duraklat_videoyu_ve_olaylari_saklar(istemci, test_ayarlari):
    from app import veritabani

    kamera_id = int(_yukle(istemci, "a.mp4").headers["location"].rsplit("/", 1)[1])
    istemci.post(f"/videolar/{kamera_id}/duraklat", follow_redirects=False)
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        assert (
            baglanti.execute("SELECT enabled FROM cameras WHERE id = ?", (kamera_id,)).fetchone()[
                "enabled"
            ]
            == 0
        )
    finally:
        baglanti.close()
    # Dosya duruyor: duraklatmak silmek değildir.
    assert len(list(test_ayarlari.video_klasoru.iterdir())) == 1


# ------------------------------------------------------------------- silme


def test_silme_kamerayi_ve_dosyayi_kaldirir(istemci, test_ayarlari):
    kamera_id = int(_yukle(istemci, "a.mp4").headers["location"].rsplit("/", 1)[1])
    yanit = istemci.post(f"/videolar/{kamera_id}/sil", follow_redirects=False)
    assert yanit.status_code == 303
    assert list(test_ayarlari.video_klasoru.iterdir()) == []
    assert istemci.get(f"/kameralar/{kamera_id}").status_code == 404


def test_video_klasoru_disindaki_dosya_bu_sayfadan_silinemez(istemci, test_ayarlari, tmp_path):
    """Kamera formuna ELLE yazılmış bir yol kullanıcının kendi dosyasıdır.

    Bu sayfanın silme düğmesi dosyayı da siliyor; başkasının masaüstündeki
    videoyu silmeye hakkımız yok, o yüzden burada hiç listelenmez.
    """
    disarida = tmp_path / "masaustu-videosu.mp4"
    disarida.write_bytes(b"kullanicinin kendi dosyasi")
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Elle girilen yol",
            "area": "",
            "source_type": "file",
            "source_url": str(disarida),
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])

    sayfa = istemci.get("/videolar").text
    assert "Elle girilen yol" not in sayfa

    # Uç doğrudan çağrılsa bile dosya silinmez (kamera kaydı gider, dosya kalır).
    istemci.post(f"/videolar/{kamera_id}/sil", follow_redirects=False)
    assert disarida.is_file()


def test_yan_klasordeki_dosya_bu_sayfaya_ait_sayilmaz(test_ayarlari):
    """'veri/videolar-eski/x.mp4' adı 'veri/videolar' ile BAŞLAR.

    Düz metin karşılaştırması bu dosyayı bu sayfaya ait sayar ve silme düğmesi
    başka bir klasördeki dosyayı silerdi.
    """
    from app.web.videolar import _klasorun_icinde

    klasor = test_ayarlari.video_klasoru.resolve()
    komsu = Path(str(klasor) + "-eski") / "x.mp4"
    assert not _klasorun_icinde(komsu, klasor)
    assert _klasorun_icinde(klasor / "x.mp4", klasor)


def test_olmayan_video_404_verir(istemci):
    assert istemci.post("/videolar/9999/sil", follow_redirects=False).status_code == 404


# -------------------------------------------------------------- boş durum


def test_bos_sayfa_sonraki_adimlari_ogretir(istemci):
    """CLAUDE.md §8: her adımın sonunda ne yapılacağı yazmalı."""
    sayfa = istemci.get("/videolar").text
    assert "Henüz video yüklenmedi" in sayfa
    assert "bölgeleri çizin" in sayfa

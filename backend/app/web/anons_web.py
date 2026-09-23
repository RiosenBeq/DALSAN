"""Anons (sesli uyarı) sayfası: mesaj metinleri, ses dosyası ve DENEME düğmesi.

Anons sistemi sahaya bağlanmadan önce burada denenir (docs/08 R3). Kullanıcı
"Anonsu Dene"ye basar; hoparlörden ses gelmiyorsa sebebi aynı sayfada yazar.
Böylece fabrikada "acaba çalışıyor mu" belirsizliği kalmaz.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ayarlar as ayarlar_modulu
from app.hatalar import AyarHatasi, DogrulamaHatasi
from app.olaylar import ses_cihazlari, test_sesi
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()

# Anons yolları .env'deki ANONS ayarına göre; burada yalnızca gösterilir
ANONS_ACIKLAMALARI = {
    "null": "Kapalı — yalnızca ekran uyarısı verilir, hoparlörden ses çıkmaz.",
    "ses_karti": "Bu bilgisayarın ses kartı — hoparlör/amfi doğrudan bilgisayara bağlı.",
    "http": "IP hoparlör / anons sunucusu — ihlalde adrese HTTP isteği gönderilir.",
}

# "Anonsu Dene" hangi ekrandan basıldıysa oraya döner. Ham yol DEĞİL anahtar
# alınır: dışarıdan verilen bir adrese yönlendirme (açık yönlendirme açığı)
# mümkün olmasın (olaylar_web.py'deki DONUS_YOLLARI ile aynı desen).
DONUS_YOLLARI = {"anons": "/anons?sonuc=denendi", "komuta": "/komuta/anons?sonuc=denendi"}


@router.get("/anons", response_class=HTMLResponse)
def anons_sayfasi(istek: Request, sonuc: str = "", baglanti=Depends(baglanti_al)):
    ayarlar = istek.app.state.ayarlar
    mesajlar = [
        dict(satir) for satir in baglanti.execute("SELECT * FROM announcement_messages ORDER BY id")
    ]
    for mesaj in mesajlar:
        mesaj["ses_var"] = (
            bool(mesaj["audio_file"]) and (ayarlar.kok_dizin / mesaj["audio_file"]).is_file()
        )

    supervizor = getattr(istek.app.state, "supervizor", None)
    return sablonlar.TemplateResponse(
        istek,
        "anons.html",
        {
            "aktif_sekme": "anons",
            "mesajlar": mesajlar,
            "anons_yolu": ayarlar.anons,
            "anons_aciklamasi": ANONS_ACIKLAMALARI.get(ayarlar.anons, ayarlar.anons),
            "anons_adresi": ayarlar.anons_http_adresi,
            "bekleme_sn": ayarlar.anons_bekleme_sn,
            "son_sonuc": getattr(supervizor, "_anons", None) and supervizor._anons.son_sonuc,
            "analiz_calisiyor": supervizor is not None,
            "sonuc_mesaji": sonuc,
            **ses_cikisi_baglami(ayarlar),
        },
    )


def ses_cikisi_baglami(ayarlar) -> dict:
    """ "Ses çıkışı" bölümünün verisi: hangi çıkışlar var, hangisi seçili, bağlı mı.

    Kendi fonksiyonunda: hem bu sayfa hem komuta kabuğundaki anons ekranı
    aynı tabloyu göstermeli. İki ayrı yerde üretilseydi biri hoparlörü bağlı,
    diğeri kopmuş gösterebilirdi.
    """
    cihazlar = ses_cihazlari.cihazlari_listele()
    secili = ayarlar.anons_ses_cihazi
    return {
        "ses_cihazlari": cihazlar,
        "secili_ses_cihazi": secili,
        "ses_secimi_destekleniyor": ses_cihazlari.secim_destekleniyor_mu(),
        # True = bağlı · False = seçili cihaz listede yok (koptu) · None = öğrenilemedi
        "ses_cihazi_bagli": ses_cihazlari.cihaz_bagli_mi(secili),
        "ses_cihazlari_okunabildi": bool(cihazlar),
    }


@router.post("/anons/ses-cikisi")
def ses_cikisini_kaydet(istek: Request, ses_cihazi: str = Form("")):
    """Seçilen ses çıkışını .env'e yazar (ANONS_SES_CIHAZI).

    Neden burada, Ayarlar sayfasında değil: seçenekler SABİT DEĞİL, o anda
    bilgisayara bağlı olan cihazlardan üretiliyor ve yanında "bağlı mı" ile
    "Test sesi çal" duruyor. Bunları Ayarlar sayfasının statik alan listesine
    sığdırmak, hoparlör kurulumunu iki ekrana bölerdi.

    Değer DOĞRULANMAZ (serbest metin): Bluetooth hoparlör o an kapalıysa
    listede görünmez; kullanıcının daha önce seçtiği adı silmek, hoparlörü
    açtığında ayarının kaybolmuş olması demekti.
    """
    ayarlar = istek.app.state.ayarlar
    degisiklik = {"ANONS_SES_CIHAZI": ses_cihazi.strip()}
    # Serbest metin ama TEK SATIR: satır sonu taşıyan bir ad .env'e yeni bir
    # satır (ör. boş YONETICI_SIFRESI) eklerdi (docs/AUDIT.md R14).
    try:
        ayarlar_modulu.env_degisikliklerini_dogrula(degisiklik)
    except AyarHatasi as hata:
        raise DogrulamaHatasi(
            "Ses çıkışının adı satır sonu ya da görünmeyen karakter içeremez; "
            "listeden yeniden seçin."
        ) from hata
    ayarlar_modulu.env_dosyasina_yaz(ayarlar.env_yolu, degisiklik)
    return RedirectResponse("/anons?sonuc=ses_cikisi", status_code=303)


@router.post("/anons/test-sesi")
def test_sesi_cal(istek: Request):
    """Mesaj kurmadan, doğrudan seçili çıkışa kısa bir test sesi çalar.

    Ayrı bir düğme: "Anonsu Dene" bir MESAJA ve ona bağlı bir .wav dosyasına
    ihtiyaç duyar. Hoparlörü ilk kez bağlayan kullanıcının elinde henüz ikisi
    de yoktur; "önce ses dosyası hazırlayın" demek, kurulumun ilk adımında
    duvara toslamaktır. Ses dosyası burada ÜRETİLİR (stdlib `wave`).
    """
    ayarlar = istek.app.state.ayarlar
    if ayarlar.anons != "ses_karti":
        raise DogrulamaHatasi(
            "Test sesi yalnızca “Bu bilgisayarın ses kartı” seçiliyken çalınır. "
            "IP hoparlör için mesajın yanındaki “Anonsu Dene” düğmesini kullanın."
        )
    hata = test_sesi.cal(ayarlar.anons_ses_cihazi)
    if hata:
        return RedirectResponse(f"/anons?sonuc=test_hata&ayrinti={quote(hata)}", status_code=303)
    return RedirectResponse("/anons?sonuc=test_calindi", status_code=303)


@router.post("/anons/{mesaj_id}/kaydet")
def mesaj_kaydet(
    istek: Request,
    mesaj_id: int,
    text: str = Form(...),
    audio_file: str = Form(""),
    enabled: str = Form("0"),
    baglanti=Depends(baglanti_al),
):
    """Anons metnini ve (varsa) kayıtlı WAV dosyasının yolunu günceller."""
    metin = text.strip()
    if not metin:
        raise DogrulamaHatasi("Anons metni boş olamaz.")
    ses = audio_file.strip()
    if ses:
        # Yol depo köküne göredir; dışarı çıkan yol kabul edilmez
        kok = istek.app.state.ayarlar.kok_dizin.resolve()
        tam = (kok / ses).resolve()
        if not tam.is_relative_to(kok):
            raise DogrulamaHatasi("Ses dosyası proje klasörünün içinde olmalı.")
        if not tam.is_file():
            raise DogrulamaHatasi(
                f"Ses dosyası bulunamadı: {ses} — Dosyayı proje klasörüne kopyalayıp "
                "yolunu 'veri/sesler/baret.wav' gibi yazın."
            )
        if tam.suffix.lower() != ".wav":
            raise DogrulamaHatasi(
                "Ses dosyası .wav olmalı. Windows'un ses çalıcısı yalnızca WAV çalar; "
                "MP3 Mac'te çalışıp fabrikada sessizce çalışmaz. Dosyayı WAV'a çevirin."
            )
        # POSIX biçiminde saklanır: Windows'ta kaydedilen 'veri\\sesler\\a.wav'
        # Linux fabrika sunucusunda tek bir dosya adı sanılır ve bulunamazdı.
        ses = PurePosixPath(Path(ses).as_posix()).as_posix()
    baglanti.execute(
        "UPDATE announcement_messages SET text = ?, audio_file = ?, enabled = ? WHERE id = ?",
        (metin, ses or None, 1 if enabled == "1" else 0, mesaj_id),
    )
    baglanti.commit()
    return RedirectResponse("/anons?sonuc=kaydedildi", status_code=303)


@router.post("/anons/{mesaj_id}/dene")
def mesaj_dene(
    istek: Request, mesaj_id: int, donus: str = Form("anons"), baglanti=Depends(baglanti_al)
):
    """Anonsu HEMEN çalar (cooldown uygulanmaz) — saha kurulumunu denemek için."""
    if donus not in DONUS_YOLLARI:
        raise DogrulamaHatasi(f"Bilinmeyen dönüş ekranı: {donus}")
    satir = baglanti.execute(
        "SELECT * FROM announcement_messages WHERE id = ?", (mesaj_id,)
    ).fetchone()
    if satir is None:
        raise DogrulamaHatasi("Anons mesajı bulunamadı.")
    supervizor = getattr(istek.app.state, "supervizor", None)
    if supervizor is None:
        raise DogrulamaHatasi(
            "Analiz çalışmıyor; anons denenemez. Kontrol Paneli'nden sistemi başlatın."
        )
    supervizor._anons.hemen_cal(dict(satir))
    return RedirectResponse(DONUS_YOLLARI[donus], status_code=303)

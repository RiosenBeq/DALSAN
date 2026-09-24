"""Anons (sesli uyarı) sayfası: mesaj metinleri, ses dosyası ve DENEME düğmesi.

Anons sistemi sahaya bağlanmadan önce burada denenir (docs/08 R3). Kullanıcı
"Anonsu Dene"ye basar; hoparlörden ses gelmiyorsa sebebi aynı sayfada yazar.
Böylece fabrikada "acaba çalışıyor mu" belirsizliği kalmaz.

Sesin hangi KANALDAN çıkacağı (ses çıkışı, Bluetooth hoparlör, IP hoparlör)
bu sayfada değil, Komuta → Anons ekranındaki kanal listesinde tanımlanır ve
denenir (web/hoparlorler.py, docs/17 K22). Burada yalnız özeti görünür.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import kaynaklar, zaman
from app.hatalar import DogrulamaHatasi
from app.olaylar.kanallar import KANAL_KISA_ADLARI, TUM_FABRIKA
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()

# "Anonsu Dene" hangi ekrandan basıldıysa oraya döner. Ham yol DEĞİL anahtar
# alınır: dışarıdan verilen bir adrese yönlendirme (açık yönlendirme açığı)
# mümkün olmasın (olaylar_web.py'deki DONUS_YOLLARI ile aynı desen).
DONUS_YOLLARI = {"anons": "/anons?sonuc=denendi", "komuta": "/komuta/anons?sonuc=denendi"}


def kanal_durumu(baglanti) -> dict:
    """Açık kanalların sayısı, türlere göre dökümü ve "Tüm fabrika" var mı."""
    satirlar = baglanti.execute("SELECT kind, area FROM speaker_zones WHERE enabled = 1").fetchall()
    turler = [
        f"{sum(1 for s in satirlar if s['kind'] == tur)} {ad}"
        for tur, ad in KANAL_KISA_ADLARI.items()
        if any(s["kind"] == tur for s in satirlar)
    ]
    return {
        "kanal_sayisi": len(satirlar),
        "kanal_dokumu": " · ".join(turler),
        "tum_fabrika_var": any(not s["area"] for s in satirlar),
        "tum_fabrika": TUM_FABRIKA,
    }


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
            "bekleme_sn": ayarlar.anons_bekleme_sn,
            "son_sonuc": getattr(supervizor, "_anons", None) and supervizor._anons.son_sonuc,
            "analiz_calisiyor": supervizor is not None,
            "sonuc_mesaji": sonuc,
            **kanal_durumu(baglanti),
        },
    )


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
            raise DogrulamaHatasi(
                f"Ses dosyası {kaynaklar.kok_klasoru_adi()} klasörünün içinde olmalı."
            )
        if not tam.is_file():
            raise DogrulamaHatasi(
                f"Ses dosyası bulunamadı: {ses} - Dosyayı "
                f"{kaynaklar.ekran_yolu('veri', 'sesler')} klasörüne kopyalayıp "
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
    # updated_at süpervizörün yapılandırma damgasına girer (AUDIT R19): damgasız
    # değişiklik çalışan sisteme inmiyor, yeni metin ya da WAV ancak yeniden
    # başlatınca çalınıyordu.
    baglanti.execute(
        "UPDATE announcement_messages SET text = ?, audio_file = ?, enabled = ?, "
        "updated_at = ? WHERE id = ?",
        (metin, ses or None, 1 if enabled == "1" else 0, zaman.simdi_utc(), mesaj_id),
    )
    baglanti.commit()
    return RedirectResponse("/anons?sonuc=kaydedildi", status_code=303)


@router.post("/anons/{mesaj_id}/dene")
def mesaj_dene(
    istek: Request, mesaj_id: int, donus: str = Form("anons"), baglanti=Depends(baglanti_al)
):
    """Anonsu HEMEN çalar (cooldown uygulanmaz) - saha kurulumunu denemek için."""
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
            f"Analiz çalışmıyor; anons denenemez. {kaynaklar.baslatma_tarifi(yeniden=False)}."
        )
    supervizor._anons.hemen_cal(dict(satir))
    return RedirectResponse(DONUS_YOLLARI[donus], status_code=303)

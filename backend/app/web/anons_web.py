"""Anons (sesli uyarı) sayfası: mesaj metinleri, ses dosyası ve DENEME düğmesi.

Anons sistemi sahaya bağlanmadan önce burada denenir (docs/08 R3). Kullanıcı
"Anonsu Dene"ye basar; hoparlörden ses gelmiyorsa sebebi aynı sayfada yazar.
Böylece fabrikada "acaba çalışıyor mu" belirsizliği kalmaz.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.hatalar import DogrulamaHatasi
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()

# Anons yolları .env'deki ANONS ayarına göre; burada yalnızca gösterilir
ANONS_ACIKLAMALARI = {
    "null": "Kapalı — yalnızca ekran uyarısı verilir, hoparlörden ses çıkmaz.",
    "ses_karti": "Bu bilgisayarın ses kartı — hoparlör/amfi doğrudan bilgisayara bağlı.",
    "http": "IP hoparlör / anons sunucusu — ihlalde adrese HTTP isteği gönderilir.",
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
            "anons_yolu": ayarlar.anons,
            "anons_aciklamasi": ANONS_ACIKLAMALARI.get(ayarlar.anons, ayarlar.anons),
            "anons_adresi": ayarlar.anons_http_adresi,
            "bekleme_sn": ayarlar.anons_bekleme_sn,
            "son_sonuc": getattr(supervizor, "_anons", None) and supervizor._anons.son_sonuc,
            "analiz_calisiyor": supervizor is not None,
            "sonuc_mesaji": sonuc,
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
            raise DogrulamaHatasi("Ses dosyası proje klasörünün içinde olmalı.")
        if not tam.is_file():
            raise DogrulamaHatasi(
                f"Ses dosyası bulunamadı: {ses} — Dosyayı proje klasörüne kopyalayıp "
                "yolunu 'veri/sesler/baret.wav' gibi yazın."
            )
        ses = str(Path(ses))
    baglanti.execute(
        "UPDATE announcement_messages SET text = ?, audio_file = ?, enabled = ? WHERE id = ?",
        (metin, ses or None, 1 if enabled == "1" else 0, mesaj_id),
    )
    baglanti.commit()
    return RedirectResponse("/anons?sonuc=kaydedildi", status_code=303)


@router.post("/anons/{mesaj_id}/dene")
def mesaj_dene(istek: Request, mesaj_id: int, baglanti=Depends(baglanti_al)):
    """Anonsu HEMEN çalar (cooldown uygulanmaz) — saha kurulumunu denemek için."""
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
    return RedirectResponse("/anons?sonuc=denendi", status_code=303)

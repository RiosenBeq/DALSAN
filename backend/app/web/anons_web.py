"""Anons paneli (docs/08 R3): mesajları düzenleme + deneme anonsu çalma.

Fabrikadaki anons sisteminin TÜRÜ henüz bilinmiyor. Bu sayfa üç olasılığın
üçünü de karşılayacak şekilde kuruldu; tür öğrenilince tek yapılacak,
.env dosyasındaki ANONS satırını değiştirip sistemi yeniden başlatmaktır:

    ANONS=null       → anons yok (sistem yalnız ekrana uyarır — MVP'de kabul, K6)
    ANONS=ses_karti  → sunucunun ses çıkışı amfiye kabloyla bağlı
    ANONS=http       → IP hoparlör / anons sunucusu (ANONS_HTTP_ADRESI ile)

Kural sayfasında bir kurala mesaj bağlandığında, ihlalde bu mesaj otomatik
duyurulur (supervizor._ihlali_kaydet → AnonsYoneticisi.duyur).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.hatalar import DogrulamaHatasi
from app.web.ortak import baglanti_al
from app.web.rotalar import sablonlar

router = APIRouter()

# .env'deki ANONS değeri → panelde gösterilecek açıklama
_TUR_ACIKLAMALARI = {
    "null": (
        "Anons kapalı. Sistem ihlalleri yalnızca ekrana yazar, hoparlörden ses çıkmaz. "
        "DALSAN'daki anons sisteminin türü öğrenilince buradan çıkılacak."
    ),
    "ses_karti": (
        "Sunucunun ses çıkışı kullanılıyor. Sunucu, fabrikadaki amfiye ses kablosuyla "
        "bağlı olmalı; her mesajın bir WAV ses dosyası tanımlı olmalı."
    ),
    "http": (
        "IP hoparlör / anons sunucusu kullanılıyor. Sistem, ihlal anında bu cihaza "
        "ağ üzerinden mesajı gönderir."
    ),
}


def _anons_yoneticisi(istek: Request):
    """Çalışan analiz süpervizörünün anons yöneticisi; analiz kapalıysa yenisi.

    Testlerde ve analiz kapalı çalışmada süpervizör yoktur; deneme anonsu
    yine de denenebilmeli (aynı ayarlarla aynı adaptör kurulur).
    """
    supervizor = getattr(istek.app.state, "supervizor", None)
    if supervizor is not None:
        return supervizor._anons
    from app.olaylar.anons import AnonsYoneticisi

    return AnonsYoneticisi(istek.app.state.ayarlar)


@router.get("/anons", response_class=HTMLResponse)
def anons_sayfasi(
    istek: Request,
    sonuc: str = "",
    basarili: str = "",
    baglanti=Depends(baglanti_al),
):
    ayarlar = istek.app.state.ayarlar
    mesajlar = [
        dict(satir)
        for satir in baglanti.execute(
            "SELECT m.*, "
            "(SELECT COUNT(*) FROM rules r WHERE r.announcement_id = m.id AND r.enabled = 1) "
            "AS kural_sayisi FROM announcement_messages m ORDER BY m.id"
        )
    ]
    return sablonlar.TemplateResponse(
        istek,
        "anons.html",
        {
            "aktif_sekme": "anons",
            "mesajlar": mesajlar,
            "anons_turu": ayarlar.anons,
            "anons_adi": _anons_yoneticisi(istek).ad,
            "tur_aciklamasi": _TUR_ACIKLAMALARI.get(ayarlar.anons, ""),
            "http_adresi": ayarlar.anons_http_adresi,
            "bekleme_sn": ayarlar.anons_bekleme_sn,
            "sonuc": sonuc,
            "basarili": basarili == "1",
        },
    )


@router.post("/anons/{mesaj_id}/deneme")
def deneme_anonsu(istek: Request, mesaj_id: int, baglanti=Depends(baglanti_al)):
    """Mesajı hemen çalar (cooldown uygulanmaz) ve sonucu sayfada gösterir."""
    mesaj = baglanti.execute(
        "SELECT * FROM announcement_messages WHERE id = ?", (mesaj_id,)
    ).fetchone()
    if mesaj is None:
        raise DogrulamaHatasi(f"Anons mesajı bulunamadı: {mesaj_id}")
    sonuc = _anons_yoneticisi(istek).deneme(dict(mesaj))
    return RedirectResponse(
        f"/anons?sonuc={sonuc.mesaj}&basarili={'1' if sonuc.basarili else '0'}",
        status_code=303,
    )


@router.post("/anons/{mesaj_id}/kaydet")
def mesaj_kaydet(
    mesaj_id: int,
    metin: str = Form(...),
    ses_dosyasi: str = Form(""),
    acik: str = Form(""),
    baglanti=Depends(baglanti_al),
):
    metin = metin.strip()
    if not metin:
        raise DogrulamaHatasi("Anons metni boş olamaz.")
    guncellenen = baglanti.execute(
        "UPDATE announcement_messages SET text = ?, audio_file = ?, enabled = ? WHERE id = ?",
        (metin, ses_dosyasi.strip() or None, 1 if acik else 0, mesaj_id),
    ).rowcount
    baglanti.commit()
    if guncellenen == 0:
        raise DogrulamaHatasi(f"Anons mesajı bulunamadı: {mesaj_id}")
    return RedirectResponse("/anons?sonuc=Mesaj kaydedildi.&basarili=1", status_code=303)

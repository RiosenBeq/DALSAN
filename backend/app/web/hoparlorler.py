"""Hoparlör bölgeleri: ekle / düzenle / sil / dene (şema 002, speaker_zones).

NEDEN VAR: bugüne kadar tek bir anons adresi vardı (.env → ANONS_HTTP_ADRESI)
ve ihlal hangi bölümde olursa olsun aynı hoparlörden duyuruluyordu. Bölge
tanımlandığında anons YALNIZCA ihlalin olduğu bölümde çalar — fabrikanın öbür
ucundaki çalışan kendisiyle ilgisi olmayan uyarıyı duymaz.

Eşleşme `area` alanıyla yapılır ve bu, kamera kartındaki "Bölüm" ile AYNI düz
metindir (ADR-007). Kullanıcıya öğrenmesi gereken ikinci bir kavram
çıkarılmadı: bölümü "Sevkiyat" olan kameranın ihlali, bölümü "Sevkiyat" olan
hoparlöre gider.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.olaylar.anons import AnonsHatasi, http_gonder
from app.web.ortak import baglanti_al, rtsp_maskele

router = APIRouter()

# Deneme yayınının metni. Sabit: kullanıcı hoparlörden ne duyacağını önceden
# bilsin ve gerçek bir uyarı sanmasın.
DENEME_ANAHTARI = "deneme"
DENEME_METNI = "DALSAN İSG hoparlör denemesi. Bu bir uyarı değildir."


def _adres_dogrula(adres: str) -> str:
    """Şemasız adres ('10.0.0.5/anons') her anonsta sessizce başarısız olurdu.

    Aynı kural .env'deki ANONS_HTTP_ADRESI için ayarlar.py'de de uygulanır;
    kullanıcı iki yerde aynı biçimi görsün.
    """
    adres = adres.strip()
    if not adres:
        raise DogrulamaHatasi("Hoparlörün adresi boş olamaz. Örnek: http://10.0.0.9:8080/anons")
    if not adres.startswith(("http://", "https://")):
        raise DogrulamaHatasi(
            "Hoparlör adresi http:// veya https:// ile başlamalı; şu an "
            f"'{adres}' yazıyor. Örnek: http://10.0.0.9:8080/anons"
        )
    return adres


@router.post("/hoparlorler/kaydet")
def hoparlor_kaydet(
    hoparlor_id: int = Form(0),
    name: str = Form(...),
    area: str = Form(""),
    address: str = Form(...),
    description: str = Form(""),
    enabled: str = Form("0"),
    baglanti=Depends(baglanti_al),
):
    """Yeni bölge ekler (hoparlor_id=0) ya da mevcut bölgeyi günceller."""
    ad = name.strip()
    if not ad:
        raise DogrulamaHatasi("Hoparlör bölgesine bir ad verin (örn. 'Sevkiyat rampaları').")
    adres = _adres_dogrula(address)
    # Bölüm boş bırakılabilir: '' = tüm fabrika (eşleşen bölüm bulunamazsa
    # kullanılan yedek hoparlör).
    bolum = area.strip()
    aciklama = description.strip()
    aktif = 1 if enabled == "1" else 0
    simdi = zaman.simdi_utc()

    if hoparlor_id:
        var = baglanti.execute(
            "SELECT 1 FROM speaker_zones WHERE id = ?", (hoparlor_id,)
        ).fetchone()
        if var is None:
            raise DogrulamaHatasi(
                "Hoparlör bölgesi bulunamadı. Silinmiş olabilir; sayfayı yenileyin."
            )
        baglanti.execute(
            "UPDATE speaker_zones SET name = ?, area = ?, address = ?, description = ?, "
            "enabled = ?, updated_at = ? WHERE id = ?",
            (ad, bolum, adres, aciklama, aktif, simdi, hoparlor_id),
        )
    else:
        baglanti.execute(
            "INSERT INTO speaker_zones (name, area, address, description, enabled, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (ad, bolum, adres, aciklama, aktif, simdi, simdi),
        )
    baglanti.commit()
    return RedirectResponse("/komuta/anons?sonuc=kaydedildi", status_code=303)


@router.post("/hoparlorler/{hoparlor_id}/sil")
def hoparlor_sil(hoparlor_id: int, baglanti=Depends(baglanti_al)):
    """Bölgeyi siler. Kural, kamera ve olay kayıtları ETKİLENMEZ: bölge yalnızca
    'anons hangi adrese gitsin' sorusunun cevabıdır. Silindikten sonra o bölümün
    anonsu .env'deki tek adrese döner."""
    baglanti.execute("DELETE FROM speaker_zones WHERE id = ?", (hoparlor_id,))
    baglanti.commit()
    return RedirectResponse("/komuta/anons?sonuc=silindi", status_code=303)


@router.post("/hoparlorler/{hoparlor_id}/dene")
def hoparlor_dene(istek: Request, hoparlor_id: int, baglanti=Depends(baglanti_al)):
    """Bu hoparlöre TEK bir deneme yayını gönderir.

    Anons ayarından (.env → ANONS) bağımsız çalışır: kullanıcı, ANONS=http'ye
    geçmeden önce kabloyu ve adresi sınayabilmeli. Bu yüzden başarı mesajı,
    denemenin ihlal anındaki anonsla aynı şey OLMADIĞINI da söyler.

    Rota senkron tanımlıdır: FastAPI senkron rotaları threadpool'da çalıştırır,
    böylece hoparlör 5 saniye yanıt vermezse arayüzün geri kalanı donmaz.
    """
    satir = baglanti.execute("SELECT * FROM speaker_zones WHERE id = ?", (hoparlor_id,)).fetchone()
    if satir is None:
        raise DogrulamaHatasi("Hoparlör bölgesi bulunamadı. Silinmiş olabilir; sayfayı yenileyin.")
    try:
        http_gonder(satir["address"], DENEME_ANAHTARI, DENEME_METNI)
    except AnonsHatasi as hata:
        # Adres MASKELİ gösterilir: hata ekranı da bir ekrandır, şifre oraya
        # da basılmamalı (docs/01 §3.6).
        raise DogrulamaHatasi(
            f"'{satir['name']}' hoparlörü denenemedi "
            f"({rtsp_maskele(satir['address'])}). {hata} "
            "Adresi Hoparlör bölgeleri listesinden düzeltebilirsiniz."
        ) from hata
    baglanti.execute(
        "UPDATE speaker_zones SET last_announced_at = ? WHERE id = ?",
        (zaman.simdi_utc(), hoparlor_id),
    )
    baglanti.commit()
    return RedirectResponse(f"/komuta/anons?sonuc=denendi&hoparlor={hoparlor_id}", status_code=303)

"""Uyarı kanalları: ekle / düzenle / sil / dene (speaker_zones; şema 002, 009).

Her satır bir kanaldır (docs/17 §7, K22): bu bilgisayarın bir ses çıkışı
(kablolu amfi ya da Bluetooth hoparlör; `kind='ses_karti'`, `device` = çıkışın
adı) ya da bir IP hoparlör (`kind='http'`, `address`). Olay, kameranın
BÖLÜMÜNDEKİ bütün açık kanallardan duyurulur; bölümde kanal yoksa "Tüm fabrika"
(bölüm boş) kanallarından.

Eşleşme `area` alanıyla yapılır ve bu, kamera kartındaki "Bölüm" ile AYNI düz
metindir (ADR-007): bölümü "Sevkiyat" olan kameranın ihlali, bölümü "Sevkiyat"
olan kanaldan duyurulur.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.olaylar import ses_cihazlari, test_sesi
from app.olaylar.anons import AnonsHatasi, hoparlor_adresini_dogrula, http_gonder
from app.olaylar.dagitici import ASAMA_TEST, SONUC_BASARISIZ, SONUC_TAMAM
from app.olaylar.kanallar import KANAL_TURLERI
from app.olaylar.teslim import teslim_satiri, teslim_yaz
from app.web.ortak import baglanti_al, maskeyi_coz, rtsp_maskele

router = APIRouter()

# Deneme yayınının metni. Sabit: kullanıcı hoparlörden ne duyacağını önceden
# bilsin ve gerçek bir uyarı sanmasın.
DENEME_ANAHTARI = "deneme"
DENEME_METNI = "DALSAN İSG hoparlör denemesi. Bu bir uyarı değildir."
_CIHAZ_EN_UZUN = 200


def _adres_dogrula(adres: str, http_bicimi: str) -> str:
    """Şemasız adres ('10.0.0.5/anons') her anonsta sessizce başarısız olurdu."""
    adres = adres.strip()
    if not adres:
        raise DogrulamaHatasi("Hoparlörün adresi boş olamaz. Örnek: http://10.0.0.9:8080/anons")
    if not adres.startswith(("http://", "https://")):
        raise DogrulamaHatasi(
            "Hoparlör adresi http:// veya https:// ile başlamalı; şu an "
            f"'{rtsp_maskele(adres)}' yazıyor. Örnek: http://10.0.0.9:8080/anons"
        )
    # GET biçiminde mesaj GÖVDEDE gönderilemez; adresin hangi mesajın
    # çalınacağını taşıması gerekir. Yer tutucusuz adres her ihlalde AYNI sesi
    # çalardı ve bu ancak sahada fark edilirdi.
    if http_bicimi == "get" and not any(yer in adres for yer in ("{anahtar}", "{metin}")):
        raise DogrulamaHatasi(
            "Anons biçimi GET (Ayarlar → Anons) ama adres hangi mesajın çalınacağını "
            "taşımıyor. Adrese {anahtar} yer tutucusunu ekleyin. Örnek: "
            "http://10.0.0.9/play?file={anahtar} (docs/14-ANONS-SISTEMI-BAGLAMA.md)."
        )
    # R30: bu bilgisayar ve bağlantı-yerel ağ kabul edilmez (gönderimde de denetlenir)
    try:
        hoparlor_adresini_dogrula(adres)
    except AnonsHatasi as hata:
        raise DogrulamaHatasi(str(hata)) from None
    return adres


def _cihaz_dogrula(cihaz: str) -> str:
    """Ses çıkışının adı: tek satır, kısa; Linux'ta boş olamaz (docs/17 §7.2).

    Listeye karşı DOĞRULANMAZ: Bluetooth hoparlör o an kapalıysa listede
    görünmez ve doğrulama, kullanıcının seçimini silerdi. Boş bırakmak
    "varsayılan çıkış" demekti ve ölçülemezdi: Bluetooth hoparlör koparsa
    işletim sistemi varsayılanı dahili hoparlöre devreder, anons "çaldı" der.
    Mac ve Windows'ta çıkış işletim sisteminden seçilir; orada boş kalır.
    """
    cihaz = cihaz.strip()
    if any(not karakter.isprintable() for karakter in cihaz) or len(cihaz) > _CIHAZ_EN_UZUN:
        raise DogrulamaHatasi("Ses çıkışının adı tek satır ve kısa olmalı; listeden seçin.")
    if not cihaz and ses_cihazlari.secim_destekleniyor_mu():
        raise DogrulamaHatasi(
            "Ses çıkışını seçin. Boş bırakılamaz: “varsayılan çıkış” denetlenemez; "
            "Bluetooth hoparlör koparsa ses sessizce bilgisayarın kendi hoparlörüne gider."
        )
    return cihaz


@router.post("/hoparlorler/kaydet")
def hoparlor_kaydet(
    istek: Request,
    hoparlor_id: int = Form(0),
    name: str = Form(...),
    area: str = Form(""),
    kind: str = Form("http"),
    address: str = Form(""),
    device: str = Form(""),
    description: str = Form(""),
    enabled: str = Form("0"),
    baglanti=Depends(baglanti_al),
):
    """Yeni kanal ekler (hoparlor_id=0) ya da mevcut kanalı günceller."""
    ad = name.strip()
    if not ad:
        raise DogrulamaHatasi("Kanala bir ad verin (örn. 'Sevkiyat rampaları').")
    if kind not in KANAL_TURLERI:
        raise DogrulamaHatasi(f"Bilinmeyen kanal türü: {kind}")
    kayitli = ""
    if hoparlor_id:
        satir = baglanti.execute(
            "SELECT address FROM speaker_zones WHERE id = ?", (hoparlor_id,)
        ).fetchone()
        if satir is None:
            raise DogrulamaHatasi("Kanal bulunamadı. Silinmiş olabilir; sayfayı yenileyin.")
        kayitli = satir["address"]
    if kind == "http":
        # Form adresi maskeli gösterir (R18); •••• kalırsa kayıtlı kimlik korunur
        adres = _adres_dogrula(
            maskeyi_coz(address, kayitli), istek.app.state.ayarlar.anons_http_bicimi
        )
        cihaz = ""
    else:
        adres, cihaz = "", _cihaz_dogrula(device)
    # Bölüm boş bırakılabilir: '' = Tüm fabrika (bölümünde kanal olmayan olayın
    # duyurulduğu yedek kanal).
    bolum = area.strip()
    aciklama = description.strip()
    aktif = 1 if enabled == "1" else 0
    simdi = zaman.simdi_utc()

    if hoparlor_id:
        baglanti.execute(
            "UPDATE speaker_zones SET name = ?, area = ?, kind = ?, address = ?, device = ?, "
            "description = ?, enabled = ?, updated_at = ? WHERE id = ?",
            (ad, bolum, kind, adres, cihaz, aciklama, aktif, simdi, hoparlor_id),
        )
    else:
        baglanti.execute(
            "INSERT INTO speaker_zones (name, area, kind, address, device, description, "
            "enabled, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (ad, bolum, kind, adres, cihaz, aciklama, aktif, simdi, simdi),
        )
    baglanti.commit()
    return RedirectResponse("/komuta/anons?sonuc=kaydedildi", status_code=303)


@router.post("/hoparlorler/{hoparlor_id}/sil")
def hoparlor_sil(hoparlor_id: int, baglanti=Depends(baglanti_al)):
    """Kanalı siler. Kural, kamera ve olay kayıtları ETKİLENMEZ: kanal yalnızca
    'anons nereden çalsın' sorusunun cevabıdır. Bölümde başka kanal kalmazsa o
    bölümün anonsu "Tüm fabrika" kanallarından duyurulur."""
    baglanti.execute("DELETE FROM speaker_zones WHERE id = ?", (hoparlor_id,))
    baglanti.commit()
    return RedirectResponse("/komuta/anons?sonuc=silindi", status_code=303)


@router.post("/hoparlorler/{hoparlor_id}/dene")
def hoparlor_dene(istek: Request, hoparlor_id: int, baglanti=Depends(baglanti_al)):
    """Bu kanaldan TEK bir deneme yayını: IP hoparlöre deneme metni, ses
    çıkışına üretilmiş bip sesi (docs/17 §7.8). Ses, kaydedilmiş satırın
    kendi çıkışından ve adresinden çıkar (R39).

    Analiz çalışıyorsa deneme o çıkışın uyarı kuyruğundan geçer: gerçek bir
    uyarıyla aynı hoparlörde üst üste binmez, kritik bir uyarı gelirse ona yer
    açar. Sonuç ve yazılım gecikmesi teslim kaydına `test` diye yazılır.

    Rota senkron tanımlıdır: FastAPI senkron rotaları threadpool'da çalıştırır,
    böylece hoparlör 5 saniye yanıt vermezse arayüzün geri kalanı donmaz.
    """
    satir = baglanti.execute("SELECT * FROM speaker_zones WHERE id = ?", (hoparlor_id,)).fetchone()
    if satir is None:
        raise DogrulamaHatasi("Kanal bulunamadı. Silinmiş olabilir; sayfayı yenileyin.")
    kanal = dict(satir)
    kuyruga_giris = zaman.simdi_utc()
    supervizor = getattr(istek.app.state, "supervizor", None)
    if supervizor is not None:
        sonuc, ayrinti, gecikme = _kuyruktan_dene(supervizor, kanal)
    else:
        sonuc, ayrinti, gecikme = _dogrudan_dene(istek, kanal)
        # Kuyruktan geçen denemeyi dağıtıcı kaydeder; burada yalnız doğrudan olan
        teslim_yaz(
            baglanti,
            teslim_satiri(
                kanal=kanal["kind"],
                asama=ASAMA_TEST,
                sonuc=sonuc,
                kuyruga_giris_utc=kuyruga_giris,
                kanal_id=hoparlor_id,
                ayrinti=ayrinti,
                baslama_utc=kuyruga_giris,
                bitis_utc=zaman.simdi_utc(),
            ),
        )
    if sonuc != SONUC_TAMAM:
        if kanal["kind"] == "ses_karti":
            raise DogrulamaHatasi(f"'{kanal['name']}' kanalından test sesi çalınamadı. {ayrinti}")
        # Adres MASKELİ gösterilir: hata ekranı da bir ekrandır, şifre oraya da
        # basılmamalı (docs/01 §3.6).
        raise DogrulamaHatasi(
            f"'{kanal['name']}' hoparlörü denenemedi "
            f"({rtsp_maskele(kanal['address'])}). {ayrinti} "
            "Adresi kanal listesinden düzeltebilirsiniz."
        )
    baglanti.execute(
        "UPDATE speaker_zones SET last_announced_at = ? WHERE id = ?",
        (zaman.simdi_utc(), hoparlor_id),
    )
    baglanti.commit()
    return RedirectResponse(
        f"/komuta/anons?sonuc=denendi&hoparlor={hoparlor_id}&gecikme={gecikme or 0}",
        status_code=303,
    )


def _deneme_icerigi(kanal: dict) -> tuple[str, str]:
    if kanal["kind"] == "ses_karti":
        return "test", "Test sesi"
    return DENEME_ANAHTARI, DENEME_METNI


def _kuyruktan_dene(supervizor, kanal: dict) -> tuple[str, str, int | None]:
    anahtar, metin = _deneme_icerigi(kanal)
    wav: Path | None = None
    if kanal["kind"] == "ses_karti":
        wav = Path(tempfile.gettempdir()) / f"nextgen-kanal-{kanal['id']}-test.wav"
        try:
            test_sesi.wav_uret(wav)
        except (OSError, ValueError) as hata:
            return SONUC_BASARISIZ, f"Test sesi üretilemedi: {hata}", None
    try:
        return supervizor._anons.kanali_dene(kanal, anahtar, metin, str(wav) if wav else None)
    finally:
        if wav is not None:
            wav.unlink(missing_ok=True)


def _dogrudan_dene(istek: Request, kanal: dict) -> tuple[str, str, int]:
    """Analiz kapalıyken: kuyruk yok, doğrudan çalar."""
    baslangic = time.monotonic()
    if kanal["kind"] == "ses_karti":
        hata = test_sesi.cal(kanal["device"])
        return (SONUC_BASARISIZ, hata, 0) if hata else (SONUC_TAMAM, "", 0)
    anahtar, metin = _deneme_icerigi(kanal)
    try:
        # Biçim .env'den GEÇİRİLİR. Geçirilmezse deneme her zaman JSON gönderir
        # ve GET bekleyen bir hoparlörde "deneme başarılı" yazarken gerçek
        # anons sessizce başarısız olurdu - anons.http_gonder'ın uyardığı tuzak.
        http_gonder(kanal["address"], anahtar, metin, istek.app.state.ayarlar.anons_http_bicimi)
    except AnonsHatasi as hata:
        return SONUC_BASARISIZ, str(hata), round((time.monotonic() - baslangic) * 1000)
    return SONUC_TAMAM, "", 0

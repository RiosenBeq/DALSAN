"""Uyarı kanallarının sağlığı (docs/17 §7.4, K20; R37).

"anons-saglik" iş parçacığı ANONS_SAGLIK_ARALIGI_SN'de (10) bir her açık
kanalı yoklar. Yoklamanın sonucu üç değerlidir: True (bağlı), False (değil),
None (öğrenilemedi). Durum makinesi:

    BAĞLI ──False──▶ ŞÜPHELİ ──(kesintisiz False ≥ ANONS_KOPUK_ESIGI_SN)──▶ KOPTU
      ▲                 │True                                               │
      └─────────────────┘                  (2 ardışık True) ────────────────┘
    None ──▶ BİLİNMİYOR: olay yok, ekranda gri, garantide sağlıklı SAYILMAZ

KOPTU'ya girişte bir kez AUDIO_CHANNEL_DOWN, çıkışta AUDIO_CHANNEL_UP yazılır.
Kısa bir aksaklık (Bluetooth'un bir yoklamada görünmemesi) olay üretmez. KOPTU
iken gelen None durumu değiştirmez: "öğrenemedik", "düzeldi" demek değildir.

`speaker_zones.health` KARARLAŞMIŞ değeri tutar: ŞÜPHELİ bir karar değildir,
kopma eşiği dolana kadar son karar (çoğunlukla "ok") korunur. Böylece ekran,
/saglik ve garanti göstergesi bir aksaklıkta titremez.

Ne yoklanır:
  ses çıkışı (Linux)  satırın çıkışı `pactl` listesinde mi (Bluetooth'ta aynı
                      adres de sayılır, profil soneki değişebilir); çalıcı yoksa
                      (container, R36) ya da ses sunucusuna bağlanılamıyorsa
                      (container'a ses soketi bağlanmamış) False; çıkış adı
                      boşsa None (R37)
  ses çıkışı (macOS)  varsayılan çıkış satırın beklediği mi; okunamazsa None
  ses çıkışı (Windows) her zaman None: varsayılan çıkış ek modülsüz okunamaz
  IP hoparlör         adresin host:port'una ≤3 sn TCP bağlantısı; R30 reddi False.
                      "Ulaşılabilir" duyuldu demek değildir.
"""

from __future__ import annotations

import socket
import sys
import urllib.parse
from dataclasses import dataclass

from app.olaylar import ses_cihazlari

HAL_BAGLI = "bagli"
HAL_SUPHELI = "supheli"
HAL_KOPTU = "koptu"
HAL_BILINMIYOR = "bilinmiyor"

# speaker_zones.health değerleri (şema 009); NULL = henüz yoklanmadı
SAGLIK_TAMAM = "ok"
SAGLIK_KOPUK = "down"
SAGLIK_BILINMIYOR = "unknown"

KOD_KOPTU = "AUDIO_CHANNEL_DOWN"
KOD_GELDI = "AUDIO_CHANNEL_UP"

# Belgelenmiş sabitler (docs/17 §6.2): histerezisin en küçük anlamlı biçimi ve
# IP hoparlör yoklamasının bekleme süresi
YUKARI_ARDISIK = 2
TCP_ZAMAN_ASIMI_SN = 3.0


@dataclass
class KanalHali:
    hal: str | None = None  # None = henüz yoklanmadı
    saglik: str | None = None  # kararlaşmış değer (ok/down/unknown); None = henüz yok
    yanlis_baslangic: float | None = None
    dogru_ardisik: int = 0
    acik_olay: int | None = None  # açık AUDIO_CHANNEL_DOWN olayının id'si
    aciklama: str = ""
    imza: tuple = ()  # yoklanan yapılandırma (tür, çıkış, adres); değişirse sıfırlanır


_KARARLAR = {
    HAL_BAGLI: SAGLIK_TAMAM,
    HAL_KOPTU: SAGLIK_KOPUK,
    HAL_BILINMIYOR: SAGLIK_BILINMIYOR,
}


def kanal_imzasi(kanal: dict) -> tuple:
    """Sağlığı belirleyen alanlar: bunlardan biri değişirse eski durum geçersizdir."""
    return (
        kanal.get("kind"),
        (kanal.get("device") or "").strip(),
        (kanal.get("address") or "").strip(),
    )


def ilerle(hali: KanalHali, sonuc: bool | None, simdi: float, esik_sn: float) -> str | None:
    """Durum makinesinin bir adımı (saf). Yazılacak olayın kodu ya da None.

    `hali.saglik` de güncellenir; ŞÜPHELİ'de değişmez (son karar korunur).
    """
    kod = _adim(hali, sonuc, simdi, esik_sn)
    if hali.hal in _KARARLAR:
        hali.saglik = _KARARLAR[hali.hal]
    return kod


def _adim(hali: KanalHali, sonuc: bool | None, simdi: float, esik_sn: float) -> str | None:
    if sonuc is None:
        if hali.hal != HAL_KOPTU:
            hali.hal = HAL_BILINMIYOR
            hali.yanlis_baslangic = None
        hali.dogru_ardisik = 0
        return None
    if sonuc:
        if hali.hal == HAL_KOPTU:
            hali.dogru_ardisik += 1
            if hali.dogru_ardisik < YUKARI_ARDISIK:
                return None
            hali.hal, hali.dogru_ardisik, hali.yanlis_baslangic = HAL_BAGLI, 0, None
            return KOD_GELDI
        hali.hal, hali.dogru_ardisik, hali.yanlis_baslangic = HAL_BAGLI, 0, None
        return None
    hali.dogru_ardisik = 0
    if hali.hal == HAL_KOPTU:
        return None
    if hali.hal != HAL_SUPHELI or hali.yanlis_baslangic is None:
        hali.hal, hali.yanlis_baslangic = HAL_SUPHELI, simdi
    if simdi - hali.yanlis_baslangic >= esik_sn:
        hali.hal = HAL_KOPTU
        return KOD_KOPTU
    return None


def kanal_yokla(
    kanal: dict,
    cihazlar: list[ses_cihazlari.SesCihazi] | None,
    *,
    secim: bool,
    calici_var: bool,
    adres_dogrula=None,
    platform: str | None = None,
    ses_sunucusu: bool | None = None,
) -> tuple[bool | None, str]:
    """Kanal şu an bağlı mı: (sonuç, açıklama). İstisna fırlatmaz.

    `cihazlar` bu turda bir kez okunmuş çıkış listesidir (boş = okunamadı).
    `adres_dogrula`: IP hoparlör adresinin R30 denetimi (olaylar/anons.py).
    `ses_sunucusu`: bu turun ses_cihazlari.ses_sunucusu_durumu() sonucu.
    `platform`: yalnız testler için (varsayılan sys.platform).
    """
    if kanal.get("kind") == "ses_karti":
        return _ses_cikisi_yokla(
            (kanal.get("device") or "").strip(),
            cihazlar,
            secim,
            calici_var,
            platform or sys.platform,
            ses_sunucusu,
        )
    return _ip_hoparlor_yokla((kanal.get("address") or "").strip(), adres_dogrula)


def _ses_cikisi_yokla(
    cihaz: str,
    cihazlar: list[ses_cihazlari.SesCihazi] | None,
    secim: bool,
    calici_var: bool,
    platform: str,
    ses_sunucusu: bool | None = None,
) -> tuple[bool | None, str]:
    if platform == "win32":
        return None, "Windows'ta çıkışın durumu ek modül olmadan okunamıyor"
    if not secim:  # macOS: yalnız varsayılan çıkış okunabilir (docs/17 §7.7)
        if not cihaz:
            return None, "beklenen çıkış yazılmamış"
        varsayilan = next((c for c in cihazlar or [] if c.varsayilan), None)
        if varsayilan is None:
            return None, "varsayılan çıkış okunamadı"
        if cihaz in (varsayilan.kimlik, varsayilan.ad):
            return True, ""
        return False, f"varsayılan çıkış başka bir cihaz: {varsayilan.ad}"
    if not calici_var:
        return False, "ses çalıcı yok (paplay/aplay); container'da ses yolu kurulmamış olabilir"
    if ses_sunucusu is False:
        return (
            False,
            "ses sunucusuna (PulseAudio/PipeWire) bağlanılamadı; container'da ses "
            "soketi bağlanmamış olabilir (docs/14 §2.4)",
        )
    if not cihaz:
        return None, "çıkış seçilmemiş (eski kayıt)"
    if not cihazlar:
        return None, "çıkış listesi okunamadı"
    if any(ses_cihazlari.ayni_cikis_mi(cihaz, c.kimlik) for c in cihazlar):
        return True, ""
    return False, "çıkış listede yok (Bluetooth hoparlör kapalı ya da menzil dışında olabilir)"


def _ip_hoparlor_yokla(adres: str, adres_dogrula) -> tuple[bool | None, str]:
    if not adres:
        return False, "adres boş"
    if adres_dogrula is not None:
        try:
            adres_dogrula(adres)
        except Exception as hata:  # noqa: BLE001 - R30 reddi "bağlı değil" demektir
            return False, str(hata)
    try:
        parca = urllib.parse.urlsplit(adres)
        sunucu = parca.hostname or ""
        port = parca.port or (443 if parca.scheme == "https" else 80)
    except ValueError:
        return False, "adres okunamadı"
    if not sunucu:
        return False, "adreste sunucu adı yok"
    try:
        with socket.create_connection((sunucu, port), timeout=TCP_ZAMAN_ASIMI_SN):
            return True, ""
    except OSError as hata:
        return False, f"bağlantı kurulamadı ({type(hata).__name__})"

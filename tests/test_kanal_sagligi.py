"""Uyarı kanallarının sağlığı: durum makinesi ve yoklama (docs/17 §7.4; Faz 4b).

- Durum makinesi: kesintisiz "bağlı değil" ANONS_KOPUK_ESIGI_SN'yi (30) doldurunca
  bir kez AUDIO_CHANNEL_DOWN; iki ardışık "bağlı" ile AUDIO_CHANNEL_UP. 29 sn
  olay üretmez. "Öğrenemedik" (None) olay üretmez.
- Yoklama: boş çıkış adı None (R37); listede olmayan bluez sink False; aynı
  adresli sink (profil soneki değişmiş) True; çalıcı yok False; TCP reddi False.
Gerçek ses ÇALINMAZ, gerçek ağa çıkılmaz (yalnız 127.0.0.1).
"""

from __future__ import annotations

import socket

from app.olaylar import anons
from app.olaylar.kanal_sagligi import (
    HAL_KOPTU,
    KOD_GELDI,
    KOD_KOPTU,
    KanalHali,
    ilerle,
    kanal_yokla,
)
from app.olaylar.ses_cihazlari import SesCihazi

BT = "bluez_output.AA_BB_CC_DD_EE_FF.1"
BT_YENI_SONEK = "bluez_output.AA_BB_CC_DD_EE_FF.a2dp-sink"
DAHILI = "alsa_output.pci-0000_00_1f.3.analog-stereo"


# ------------------------------------------------------------ durum makinesi


def test_29_sn_olay_uretmez_30_sn_bir_kez_koptu():
    hali = KanalHali()
    assert ilerle(hali, True, 0.0, 30) is None and hali.saglik == "ok"
    assert ilerle(hali, False, 10.0, 30) is None
    assert ilerle(hali, False, 39.0, 30) is None, "29 sn: kısa aksaklık olay üretmez"
    assert hali.saglik == "ok", "şüpheli bir karar değildir; son karar korunur"
    assert ilerle(hali, False, 40.0, 30) == KOD_KOPTU
    assert hali.saglik == "down"
    assert ilerle(hali, False, 50.0, 30) is None, "koptu olayı bir kez yazılır"


def test_iki_ardisik_bagli_geldi_uretir():
    hali = KanalHali(hal=HAL_KOPTU, saglik="down")
    assert ilerle(hali, True, 0.0, 30) is None, "tek 'bağlı' yetmez (histerezis)"
    assert ilerle(hali, False, 10.0, 30) is None, "araya giren kopukluk sayacı sıfırlar"
    assert ilerle(hali, True, 20.0, 30) is None
    assert ilerle(hali, True, 30.0, 30) == KOD_GELDI
    assert hali.saglik == "ok"


def test_kisa_aksaklik_sayaci_sifirlanir():
    hali = KanalHali()
    ilerle(hali, False, 0.0, 30)
    ilerle(hali, True, 20.0, 30)
    assert ilerle(hali, False, 25.0, 30) is None
    assert ilerle(hali, False, 54.0, 30) is None, "süre yeni aksaklıktan sayılır"
    assert ilerle(hali, False, 55.0, 30) == KOD_KOPTU


def test_bilinmiyor_olay_uretmez_ve_koptuyu_degistirmez():
    hali = KanalHali()
    assert ilerle(hali, True, 0.0, 30) is None
    assert ilerle(hali, None, 10.0, 30) is None
    assert hali.saglik == "unknown"
    koptu = KanalHali(hal=HAL_KOPTU, saglik="down")
    assert ilerle(koptu, None, 0.0, 30) is None
    assert (koptu.hal, koptu.saglik) == (HAL_KOPTU, "down"), "öğrenemedik ≠ düzeldi"


# ------------------------------------------------------------ yoklama


def _ses(device: str) -> dict:
    return {"kind": "ses_karti", "device": device}


def _cihazlar(*kimlikler: str) -> list[SesCihazi]:
    return [SesCihazi(kimlik=k, ad=k) for k in kimlikler]


def _yokla(kanal, cihazlar=(), secim=True, calici=True, platform="linux", **ek):
    return kanal_yokla(
        kanal, list(cihazlar), secim=secim, calici_var=calici, platform=platform, **ek
    )


def test_bos_cikis_adi_bilinmiyor_r37():
    """Varsayılan çıkış denetlenemez: "bağlı" demek yalan olurdu."""
    sonuc, neden = _yokla(_ses(""), _cihazlar(DAHILI))
    assert sonuc is None and "çıkış seçilmemiş" in neden


def test_bluetooth_sink_listede_yoksa_koptu_soneki_degistiyse_bagli():
    assert _yokla(_ses(BT), _cihazlar(DAHILI))[0] is False
    assert _yokla(_ses(BT), _cihazlar(DAHILI, BT))[0] is True
    # Yeniden bağlanan hoparlörün profil soneki değişebilir: aynı adres = aynı hoparlör
    assert _yokla(_ses(BT), _cihazlar(DAHILI, BT_YENI_SONEK))[0] is True


def test_calici_yoksa_koptu_liste_okunamazsa_bilinmiyor():
    assert _yokla(_ses(BT), _cihazlar(BT), calici=False)[0] is False
    assert _yokla(_ses(BT), ())[0] is None


def test_windows_her_zaman_bilinmiyor_macos_varsayilana_bakar():
    assert _yokla(_ses("Hoparlör"), platform="win32")[0] is None
    varsayilan = [SesCihazi(kimlik="JBL Flip", ad="JBL Flip", varsayilan=True)]
    assert _yokla(_ses("JBL Flip"), varsayilan, secim=False, platform="darwin")[0] is True
    assert _yokla(_ses("Dahili"), varsayilan, secim=False, platform="darwin")[0] is False
    assert _yokla(_ses("JBL Flip"), (), secim=False, platform="darwin")[0] is None


def test_ip_hoparlor_tcp_reddi_koptu_dinleyen_varsa_bagli():
    with socket.socket() as dinleyen:
        dinleyen.bind(("127.0.0.1", 0))
        dinleyen.listen(1)
        port = dinleyen.getsockname()[1]
        kanal = {"kind": "http", "address": f"http://127.0.0.1:{port}/anons"}
        assert _yokla(kanal)[0] is True
    # Soket kapandı: aynı port artık bağlantıyı reddeder
    sonuc, neden = _yokla(kanal)
    assert sonuc is False and "bağlantı kurulamadı" in neden


def test_ip_hoparlor_r30_reddi_koptu_sayilir():
    """Bu bilgisayarı gösteren adres yoklanmaz bile (SSRF, R30)."""
    kanal = {"kind": "http", "address": "http://127.0.0.1/anons"}
    sonuc, neden = _yokla(kanal, adres_dogrula=anons.hoparlor_adresini_dogrula)
    assert sonuc is False and neden

"""Bilgisayara bağlı ses ÇIKIŞLARINI listeler (Bluetooth hoparlör dahil).

NEDEN VAR - anons "ses kartı" kipinde çalınca ses, işletim sisteminin
VARSAYILAN çıkışına gider. Bunun iki sonucu vardı ve ikisi de sessizdi:

1. Kullanıcı fabrikaya Bluetooth bir hoparlör koyuyor, ama ses dizüstünün
   kendi hoparlöründen çıkıyor. Hiçbir hata yok; kimse fark etmiyor.
2. Bluetooth hoparlör kapanıyor ya da menzilden çıkıyor. Anons artık hiçbir
   yere gitmiyor ve ekranda bunu söyleyen tek satır yok.

Bu modül iki soruyu cevaplar: "bu bilgisayarda hangi ses çıkışları var" ve
"seçtiğim çıkış hâlâ bağlı mı".

CİHAZ SEÇİMİ HER YERDE YAPILAMAZ - dürüst olmak gerekiyor:

  Linux (fabrika sunucusu)  paplay/aplay çıkışı ADIYLA alır. Seçim GERÇEKTEN
                            çalışır; Bluetooth hoparlör de bir "sink"tir.
  macOS                     afplay'in cihaz seçeneği YOKTUR. Çıkış, macOS
                            Ses ayarlarından seçilir. Burada yalnızca
                            listelenir ve hangisinin varsayılan olduğu yazar.
  Windows                   winsound da varsayılana çalar.
                            Aynı şekilde: listelenir, seçim Windows'un Ses
                            ayarlarından yapılır.

Mac ve Windows'ta seçimi "çalışıyormuş gibi" göstermek, en kötü seçenekti:
kullanıcı listeden hoparlörü seçer, ses başka yerden çıkar ve sebebini
hiçbir zaman öğrenemezdi. Bunun yerine ekran ne yapılacağını söylüyor.

EK KURULUM YOK (CLAUDE.md §3): her platformda İŞLETİM SİSTEMİYLE HAZIR GELEN
araçlar kullanılıyor - pactl/aplay (Linux), system_profiler (macOS),
PowerShell (Windows). sounddevice/pyaudio gibi paketler PortAudio'nun yerel
ikili dosyalarını ister; paketlemede en kolay kırılan parça odur.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass

from app.loglama import log_al

_log = log_al("ses")

# Cihaz listesi komutunun en çok bekleyeceği süre. Bu çağrı bir web isteğinin
# içinden yapılıyor; takılan bir komut sayfayı da kilitlerdi.
_ZAMAN_ASIMI_SN = 5

# Adında bunlardan biri geçen çıkış Bluetooth sayılır. Linux'ta ad zaten
# "bluez_output..." olur; Mac ve Windows'ta tek ipucu addır.
_BLUETOOTH_IZLERI = ("bluez", "bluetooth", "airpods", "jbl", "soundlink", "bose")


@dataclass(frozen=True)
class SesCihazi:
    """Tek bir ses çıkışı."""

    # Komuta verilecek ad (Linux'ta `paplay --device=`). Seçimin çalışmadığı
    # platformlarda yalnızca listede ayırt etmeye yarar.
    kimlik: str
    ad: str  # kullanıcıya görünen ad
    varsayilan: bool = False
    bluetooth: bool = False


def secim_destekleniyor_mu() -> bool:
    """Bu işletim sisteminde çıkış cihazı PROGRAMDAN seçilebiliyor mu?

    Yalnızca Linux'ta True. Mac ve Windows'un hazır ses çalıcılarında cihaz
    seçeneği yoktur; oralarda seçim işletim sisteminin ses ayarlarındadır.
    """
    return not (sys.platform == "darwin" or sys.platform.startswith("win"))


def cihazlari_listele() -> list[SesCihazi]:
    """Bağlı ses çıkışları. Liste alınamazsa BOŞ döner (hata fırlatmaz).

    Boş liste "cihaz yok" değil, "öğrenemedik" demektir; ekran bunu ayrı bir
    cümleyle söyler. Burada istisna fırlatmak, ses çıkışını listeleyemediği
    için Anons SAYFASININ AÇILMAMASI anlamına gelirdi.
    """
    try:
        if sys.platform == "darwin":
            return _mac_cihazlari()
        if sys.platform.startswith("win"):
            return _windows_cihazlari()
        return _linux_cihazlari()
    except (OSError, subprocess.SubprocessError, ValueError) as hata:
        _log.warning(
            "Ses çıkışları listelenemedi; anons yine varsayılan çıkışa çalar.",
            extra={"ayrinti": repr(hata)},
        )
        return []


def cihaz_bagli_mi(kimlik: str) -> bool | None:
    """Seçili çıkış hâlâ bağlı mı? Liste alınamadıysa None ("bilinmiyor").

    None ile False AYRI tutuluyor: "hoparlörünüz koptu" demek ile "kontrol
    edemedik" demek aynı şey değildir ve birincisini yanlışlıkla söylemek
    kullanıcıyı olmayan bir arızanın peşine düşürür.
    """
    if not kimlik:
        return True  # varsayılan çıkış: işletim sistemi ne derse o
    cihazlar = cihazlari_listele()
    if not cihazlar:
        return None
    return any(cihaz.kimlik == kimlik for cihaz in cihazlar)


def _bluetooth_mu(*metinler: str) -> bool:
    birlesik = " ".join(metinler).lower()
    return any(iz in birlesik for iz in _BLUETOOTH_IZLERI)


def _calistir(komut: list[str]) -> str:
    """Komutu çalıştırıp çıktısını döndürür; başarısızsa boş metin."""
    sonuc = subprocess.run(
        komut,
        capture_output=True,
        timeout=_ZAMAN_ASIMI_SN,
        text=True,
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if sys.platform.startswith("win")
        else 0,
    )
    return sonuc.stdout if sonuc.returncode == 0 else ""


# ------------------------------------------------------------------- Linux


def _linux_cihazlari() -> list[SesCihazi]:
    """PulseAudio/PipeWire çıkışları (`pactl`). Bluetooth hoparlör de burada.

    `pactl` yoksa ALSA'ya (`aplay -L`) düşülür: kimi çıplak sunucuda
    PulseAudio kurulu olmaz.
    """
    if shutil.which("pactl"):
        varsayilan = _calistir(["pactl", "get-default-sink"]).strip()
        cihazlar = []
        for satir in _calistir(["pactl", "list", "short", "sinks"]).splitlines():
            parcalar = satir.split("\t")
            if len(parcalar) < 2:
                continue
            ad = parcalar[1]
            cihazlar.append(
                SesCihazi(
                    kimlik=ad,
                    ad=_linux_okunur_ad(ad),
                    varsayilan=ad == varsayilan,
                    bluetooth=_bluetooth_mu(ad),
                )
            )
        if cihazlar:
            return cihazlar
    if not shutil.which("aplay"):
        return []
    cihazlar = []
    for satir in _calistir(["aplay", "-L"]).splitlines():
        # Girintili satırlar açıklamadır; cihaz adı girintisiz satırdır.
        if satir[:1].isspace() or not satir.strip():
            continue
        ad = satir.strip()
        cihazlar.append(SesCihazi(kimlik=ad, ad=ad, bluetooth=_bluetooth_mu(ad)))
    return cihazlar


def _linux_okunur_ad(sink_adi: str) -> str:
    """'bluez_output.AC_12_.._1' gibi bir adı biraz insanlaştırır.

    Tam ad kimliktir ve değişmez; bu yalnızca listede okunan yazıdır.
    """
    if sink_adi.startswith("bluez_output"):
        return f"Bluetooth hoparlör ({sink_adi.split('.', 1)[-1]})"
    return sink_adi


# ------------------------------------------------------------------- macOS


def _mac_cihazlari() -> list[SesCihazi]:
    """macOS ses çıkışları (`system_profiler`, işletim sistemiyle gelir)."""
    ham = _calistir(["system_profiler", "-json", "SPAudioDataType"])
    if not ham:
        return []
    veri = json.loads(ham)
    cihazlar = []
    for kart in veri.get("SPAudioDataType", []):
        for girdi in kart.get("_items", []):
            # Yalnızca ÇIKIŞ yapabilen cihazlar: mikrofon listede işe yaramaz.
            if not girdi.get("coreaudio_device_output"):
                continue
            ad = girdi.get("_name", "")
            if not ad:
                continue
            tasima = str(girdi.get("coreaudio_device_transport", ""))
            cihazlar.append(
                SesCihazi(
                    kimlik=ad,
                    ad=ad,
                    varsayilan=girdi.get("coreaudio_default_audio_output_device") == "spaudio_yes",
                    bluetooth=_bluetooth_mu(tasima, ad),
                )
            )
    return cihazlar


# ----------------------------------------------------------------- Windows


# Ses ÇIKIŞ uçlarını listeler. Get-PnpDevice Windows 10/11'de hazırdır ve ek
# modül istemez (AudioDeviceCmdlets gibi paketler kurulum gerektirirdi).
_WINDOWS_KOMUTU = (
    "Get-PnpDevice -Class AudioEndpoint -Status OK -ErrorAction SilentlyContinue | "
    "Select-Object -ExpandProperty FriendlyName"
)


def _windows_cihazlari() -> list[SesCihazi]:
    """Windows ses çıkışları.

    VARSAYILAN İŞARETLENMEZ: hangi ucun varsayılan olduğunu ek modül kurmadan
    okumanın güvenilir bir yolu yok. Yanlış cihazı "varsayılan" diye
    göstermek, hiç göstermemekten kötüdür.
    """
    ham = _calistir(["powershell", "-NoProfile", "-Command", _WINDOWS_KOMUTU])
    cihazlar = []
    for satir in ham.splitlines():
        ad = satir.strip()
        if ad:
            cihazlar.append(SesCihazi(kimlik=ad, ad=ad, bluetooth=_bluetooth_mu(ad)))
    return cihazlar

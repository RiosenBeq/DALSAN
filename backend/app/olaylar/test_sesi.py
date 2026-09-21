"""Hoparlörü denemek için kısa bir test sesi üretir ve çalar.

NEDEN AYRI BİR SES — "Anonsu Dene" düğmesi bir MESAJA ve ona bağlı bir .wav
dosyasına ihtiyaç duyar. Hoparlörünü ilk kez bağlayan kullanıcının elinde
henüz ikisi de yoktur. Ona "önce bir ses dosyası hazırlayın" demek, kurulumun
daha ilk adımında duvara toslatmaktır; oysa o anda sorduğu soru çok basit:
**"bu hoparlörden ses çıkıyor mu?"**

SES DOSYA OLARAK GELMEZ, ÜRETİLİR. Depoya hazır bir .wav koymak da olurdu ama:
  * ikili bir dosya olurdu ve satır sonu dönüşümünden bozulma riski taşırdı
    (simgelerde bu gerçekten yaşandı, bkz. .gitattributes),
  * paketleme tarifine bir giriş daha eklemek gerekirdi,
  * ve gerekmiyor: iki saniyelik bir bip, standart kütüphanenin `wave`
    modülüyle otuz satırda üretiliyor. Yeni bağımlılık YOK (CLAUDE.md §3).

Ses bilerek bir "bip-bip" desenidir, tek düz ton değil: fabrika gürültüsünde
sabit bir uğultu makine sesine karışır, kesikli bir bip ayırt edilir.
"""

from __future__ import annotations

import array
import math
import struct
import tempfile
import wave
from pathlib import Path

from app.loglama import log_al
from app.olaylar.anons import AnonsHatasi, SesKartiAnonscu

_log = log_al("ses")

ORNEKLEME_HIZI = 22050  # Hz — konuşma/bip için fazlasıyla yeterli, dosya küçük
TON_HZ = 880.0  # yüksek la; fabrika uğultusunun üstünde kalır
BIP_SN = 0.18
SESSIZLIK_SN = 0.12
BIP_SAYISI = 3
# 0-1 arası. Tam ses (1,0) hem çirkin hem tehlikelidir: kulağa yakın bir
# hoparlörde deneme yapan kullanıcıyı irkiltir.
SES_SEVIYESI = 0.35


def wav_uret(hedef: Path) -> Path:
    """Kısa bir "bip-bip-bip" sesini 16-bit mono WAV olarak yazar."""
    ornekler = array.array("h")
    bip_ornek = int(ORNEKLEME_HIZI * BIP_SN)
    sessiz_ornek = int(ORNEKLEME_HIZI * SESSIZLIK_SN)
    tepe = int(32767 * SES_SEVIYESI)

    for _ in range(BIP_SAYISI):
        for n in range(bip_ornek):
            # Baştaki ve sondaki yumuşatma (fade) ŞART: birden başlayan bir
            # ton hoparlörde "tık" diye bir patlama sesi üretir ve kullanıcı
            # bunu arıza sanar.
            yumusatma = min(1.0, n / 200, (bip_ornek - n) / 200)
            ornekler.append(
                int(tepe * yumusatma * math.sin(2 * math.pi * TON_HZ * n / ORNEKLEME_HIZI))
            )
        ornekler.extend([0] * sessiz_ornek)

    with wave.open(str(hedef), "wb") as dosya:
        dosya.setnchannels(1)
        dosya.setsampwidth(2)
        dosya.setframerate(ORNEKLEME_HIZI)
        # Baytlar AÇIKÇA little-endian yazılır. array.tobytes() makinenin
        # kendi bayt sırasını kullanır; WAV ise her zaman little-endian'dır.
        # Büyük-endian bir makinede ses gürültüye dönerdi.
        dosya.writeframes(struct.pack(f"<{len(ornekler)}h", *ornekler))
    return hedef


def cal(cihaz: str = "") -> str:
    """Test sesini çalar. Başarılıysa boş metin, değilse Türkçe hata döner.

    İstisna FIRLATMAZ: çağıran taraf bir web isteğidir ve "hoparlör çalmadı"
    bir program hatası değil, kullanıcıya söylenecek bir sonuçtur.

    Ses dosyası GEÇİCİ klasöre yazılır ve hemen silinir: kullanıcının veri
    klasöründe, yedeklemeye giren, kimsenin ne olduğunu bilmediği bir .wav
    bırakmanın anlamı yok.
    """
    gecici = Path(tempfile.gettempdir()) / "nextgen-test-sesi.wav"
    try:
        wav_uret(gecici)
    except (OSError, ValueError) as hata:
        _log.error(f"Test sesi üretilemedi: {hata}")
        return f"Test sesi üretilemedi: {hata}"
    try:
        # Gerçek anonsun çaldığı YOLUN AYNISI kullanılır. Ayrı bir çalma kodu
        # yazılsaydı test çalar, gerçek anons sessizce çalmayabilirdi — yani
        # düğme tam da güvenilmesi gereken yerde yalan söylerdi.
        SesKartiAnonscu(cihaz).cal("test", "Test sesi", str(gecici))
    except AnonsHatasi as hata:
        return str(hata)
    finally:
        gecici.unlink(missing_ok=True)
    return ""

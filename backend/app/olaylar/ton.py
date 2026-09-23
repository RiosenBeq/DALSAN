"""Üretilen bip sesi: hoparlör denemesi ve ses dosyası olmayan uyarı.

SES DOSYA OLARAK GELMEZ, ÜRETİLİR. Depoya hazır bir .wav koymak da olurdu ama:
  * ikili bir dosya olurdu ve satır sonu dönüşümünden bozulma riski taşırdı
    (simgelerde bu gerçekten yaşandı, bkz. .gitattributes),
  * paketleme tarifine bir giriş daha eklemek gerekirdi,
  * ve gerekmiyor: kesikli bir bip, standart kütüphanenin `wave` modülüyle
    otuz satırda üretiliyor. Yeni bağımlılık YOK (CLAUDE.md §3). Ses bizim
    ürettiğimiz bir sinüs dalgasıdır; lisans sorusu doğurmaz (docs/16 §3).

Ses bilerek bir "bip-bip" desenidir, tek düz ton değil: fabrika gürültüsünde
sabit bir uğultu makine sesine karışır, kesikli bir bip ayırt edilir.

İki kullanımı var:
  * **Test sesi** (`test_sesi.py`, "Dene" düğmesi): kısık ve kısa. Deneme
    yapan kullanıcı çoğu zaman hoparlörün yanındadır.
  * **Uyarı tonu** (`anons.py`): mesaja ses dosyası bağlanmamışsa ya da dosya
    bulunamıyorsa ses çıkışı kanalı SUSMAZ, sözlü anons yerine bu ton çalar
    (operatör isteği 23.09.2026: risk anında hoparlörden uyarı verilsin).
    Gerçek bir uyarıdır: daha yüksek ve daha uzun.
"""

from __future__ import annotations

import array
import math
import os
import struct
import tempfile
import threading
import wave
from pathlib import Path

ORNEKLEME_HIZI = 22050  # Hz - konuşma/bip için fazlasıyla yeterli, dosya küçük
TON_HZ = 880.0  # yüksek la; fabrika uğultusunun üstünde kalır
BIP_SN = 0.18
SESSIZLIK_SN = 0.12
BIP_SAYISI = 3
# 0-1 arası. Tam ses (1,0) hem çirkin hem tehlikelidir: kulağa yakın bir
# hoparlörde deneme yapan kullanıcıyı irkiltir.
SES_SEVIYESI = 0.35

# Uyarı tonu: fabrika gürültüsünün üstünde duyulmalı. 0,8 tam sesin altında
# kalır (kırpılma yok); altı bip yaklaşık 1,8 sn sürer, sözlü bir anons kadar.
UYARI_SES_SEVIYESI = 0.8
UYARI_BIP_SAYISI = 6

_uyari_tonu: Path | None = None
_uyari_tonu_kilidi = threading.Lock()


def wav_uret(
    hedef: Path, *, ses_seviyesi: float = SES_SEVIYESI, bip_sayisi: int = BIP_SAYISI
) -> Path:
    """Kısa bir "bip-bip-bip" sesini 16-bit mono WAV olarak yazar."""
    ornekler = array.array("h")
    bip_ornek = int(ORNEKLEME_HIZI * BIP_SN)
    sessiz_ornek = int(ORNEKLEME_HIZI * SESSIZLIK_SN)
    tepe = int(32767 * ses_seviyesi)

    for _ in range(bip_sayisi):
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


def uyari_tonu_yolu() -> Path:
    """Uyarı tonunun WAV yolu; dosya yoksa üretir. OSError yükseltebilir.

    Süreç başına bir kez üretilir, silinirse yeniden. Geçici klasöre önce
    süreç numaralı bir adla yazılıp tek hamlede yerine konur: aynı anda
    çalan başka bir çıkış yarım yazılmış bir dosyayı çalmasın.
    """
    global _uyari_tonu
    with _uyari_tonu_kilidi:
        if _uyari_tonu is not None and _uyari_tonu.is_file():
            return _uyari_tonu
        hedef = Path(tempfile.gettempdir()) / "nextgen-uyari-tonu.wav"
        gecici = hedef.with_name(f"{hedef.stem}-{os.getpid()}.tmp")
        try:
            wav_uret(gecici, ses_seviyesi=UYARI_SES_SEVIYESI, bip_sayisi=UYARI_BIP_SAYISI)
            os.replace(gecici, hedef)
        finally:
            gecici.unlink(missing_ok=True)
        _uyari_tonu = hedef
        return hedef

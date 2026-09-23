"""Hoparlörü denemek için kısa bir test sesi üretir ve çalar.

NEDEN AYRI BİR SES - "Anonsu Dene" düğmesi bir MESAJA ve ona bağlı bir .wav
dosyasına ihtiyaç duyar. Hoparlörünü ilk kez bağlayan kullanıcının elinde
henüz ikisi de yoktur. Ona "önce bir ses dosyası hazırlayın" demek, kurulumun
daha ilk adımında duvara toslatmaktır; oysa o anda sorduğu soru çok basit:
**"bu hoparlörden ses çıkıyor mu?"**

Ses üretilir, dosya olarak gelmez; üretici ve gerekçesi `ton.py`'dedir (aynı
üretici, ses dosyası olmayan gerçek uyarının tonunu da üretir).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.loglama import log_al
from app.olaylar.anons import AnonsHatasi, SesKartiAnonscu

# Dışarıdan (Kanallar ekranı, testler) bu modülün adıyla kullanılır
from app.olaylar.ton import ORNEKLEME_HIZI, SES_SEVIYESI, wav_uret

__all__ = ["ORNEKLEME_HIZI", "SES_SEVIYESI", "cal", "wav_uret"]

_log = log_al("ses")


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
        # yazılsaydı test çalar, gerçek anons sessizce çalmayabilirdi - yani
        # düğme tam da güvenilmesi gereken yerde yalan söylerdi.
        SesKartiAnonscu(cihaz).cal("test", "Test sesi", str(gecici))
    except AnonsHatasi as hata:
        return str(hata)
    finally:
        gecici.unlink(missing_ok=True)
    return ""

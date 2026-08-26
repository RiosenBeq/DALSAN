"""JSON satır formatında log — hem ekrana hem veri/loglar/sistem.log dosyasına.

Her satır tek bir JSON nesnesidir: {"ts", "level", "bilesen", "mesaj"}.
Kontrol Paneli bu çıktıyı okuyup günlük penceresinde gösterir; kullanıcı
sorun olduğunda satırları olduğu gibi kopyalayıp Claude Code'a yapıştırır.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler

from app import zaman
from app.ayarlar import Ayarlar

_KOK_AD = "dalsan"


class _JsonSatirBicimi(logging.Formatter):
    def format(self, kayit: logging.LogRecord) -> str:
        bilesen = kayit.name.removeprefix(_KOK_AD + ".") if kayit.name != _KOK_AD else "sistem"
        satir = {
            "ts": zaman.simdi_utc(),
            "level": kayit.levelname,
            "bilesen": bilesen,
            "mesaj": kayit.getMessage(),
        }
        if kayit.exc_info:
            satir["ayrinti"] = self.formatException(kayit.exc_info)
        return json.dumps(satir, ensure_ascii=False)


def kur(ayarlar: Ayarlar) -> None:
    """Log sistemini bir kez kurar. İkinci çağrı eskisinin yerine geçer."""
    kok = logging.getLogger(_KOK_AD)
    kok.setLevel(logging.INFO)
    kok.propagate = False
    kok.handlers.clear()  # testlerde/yeniden kurulumda satırlar ikilenmesin

    bicim = _JsonSatirBicimi()

    ekran = logging.StreamHandler()
    ekran.setFormatter(bicim)
    kok.addHandler(ekran)

    # Dosya sınırsız büyümesin diye 5 MB'ta döner, son 3 kopya saklanır —
    # 7x24 çalışan sistemde log yüzünden disk dolmasın (docs/08 R8).
    dosya = RotatingFileHandler(
        ayarlar.log_dosyasi, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    dosya.setFormatter(bicim)
    kok.addHandler(dosya)


def log_al(bilesen: str) -> logging.Logger:
    """Bileşen adıyla logger döndürür: log_al('veritabani').info('...')"""
    return logging.getLogger(f"{_KOK_AD}.{bilesen}")

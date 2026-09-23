"""Ekran kanalı: şu an bağlı izleme ekranı (SSE istemcisi) sayısı (docs/17 §7.2).

Olay akışı (`/olaylar/akis`) açılırken sayaç artar, kapanırken azalır. Bu
yalnız BİLGİDİR: ekran uyarı garantisine sayılmaz (§7.4). Kontrol Paneli
izleme penceresini kendisi açtığı için sayaç simge durumundaki bir pencereyle
de 1 olur; "biri ekrana bakıyor" demek değildir.
"""

from __future__ import annotations

import threading

_kilit = threading.Lock()
_sayi = 0


def baglandi() -> None:
    global _sayi
    with _kilit:
        _sayi += 1


def ayrildi() -> None:
    global _sayi
    with _kilit:
        _sayi = max(0, _sayi - 1)


def istemci_sayisi() -> int:
    with _kilit:
        return _sayi

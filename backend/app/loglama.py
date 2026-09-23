"""JSON satır formatında log — hem ekrana hem veri/loglar/sistem.log dosyasına.

Her satır tek bir JSON nesnesidir: {"ts", "level", "bilesen", "mesaj"}.
Kontrol Paneli bu çıktıyı okuyup günlük penceresinde gösterir; kullanıcı
sorun olduğunda satırları olduğu gibi kopyalayıp Claude Code'a yapıştırır.

İKİ AKIŞ, İKİ AYRINTI SEVİYESİ (CLAUDE.md §8):
  * EKRAN (Kontrol Paneli'nin "Sistem günlüğü" penceresi): yalnızca `mesaj`.
    Kullanıcıya model dosyasının adı, mutlak dosya yolu ya da yığın izi
    gösterilmez — bunlar korkutur ve yazılım bilmeyen kullanıcının hiçbir
    işine yaramaz.
  * DOSYA (veri/loglar/sistem.log): aynı satır + `ayrinti` alanı. Teknik
    ayrıntı KAYBOLMAZ; destek ekibine iletilen dosya odur.

uvicorn'un günlükleri de aynı biçimde ve aynı dosyadadır (`bilesen`:
"uvicorn.error", "uvicorn.access"); erişim günlüğünden başarılı GET'ler elenir.

Teknik ayrıntı `extra={"ayrinti": "..."}` ile verilir:

    log_al("tespit").info("NextGen AI Hızlı yüklendi", extra={"ayrinti": str(yol)})
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler

from app import zaman
from app.ayarlar import Ayarlar

_KOK_AD = "dalsan"
# uvicorn'un kendi günlükleri (docs/17 §9.4): sunucu başladı/durdu, ASGI
# hataları ve HTTP erişim satırları.
_UVICORN_ADLARI = ("uvicorn", "uvicorn.error", "uvicorn.access")


class _JsonSatirBicimi(logging.Formatter):
    """`ayrintili=False` olan akışa teknik ayrıntı yazılmaz.

    Aynı kayıt iki kez biçimlendirilir: ekrana sade, dosyaya ayrıntılı.
    Böylece "ekranda dosya yolu görünmesin" kuralı ile "destek için ayrıntı
    kaybolmasın" ihtiyacı tek bir yerde, çağıran kodu ilgilendirmeden çözülür.
    """

    def __init__(self, ayrintili: bool) -> None:
        super().__init__()
        self.ayrintili = ayrintili

    def format(self, kayit: logging.LogRecord) -> str:
        bilesen = kayit.name.removeprefix(_KOK_AD + ".") if kayit.name != _KOK_AD else "sistem"
        satir = {
            "ts": zaman.simdi_utc(),
            "level": kayit.levelname,
            "bilesen": bilesen,
            "mesaj": kayit.getMessage(),
        }
        if self.ayrintili:
            parcalar = []
            ek = getattr(kayit, "ayrinti", None)
            if ek:
                parcalar.append(str(ek))
            if kayit.exc_info:
                parcalar.append(self.formatException(kayit.exc_info))
            if parcalar:
                satir["ayrinti"] = "\n".join(parcalar)
        return json.dumps(satir, ensure_ascii=False)


class _DalsanaAktar(logging.Handler):
    """uvicorn kaydını "dalsan" kök logger'ının işleyicilerine iletir.

    uvicorn'a ayrı işleyiciler bağlanmaz: Kontrol Paneli sonradan köke kendi
    akışını ekliyor (dalsan_launcher.py `_gunlugu_panele_bagla`); aktarma
    sayesinde uvicorn satırları da oraya düşer.
    """

    def emit(self, kayit: logging.LogRecord) -> None:
        logging.getLogger(_KOK_AD).handle(kayit)


def _basarili_okumayi_ele(kayit: logging.LogRecord) -> bool:
    """Erişim günlüğünde yalnız DEĞİŞTİREN istekler ve hatalar kalır.

    Kontrol Paneli /saglik'i 1,5 sn'de, komuta ekranları 5 sn'de bir yoklar;
    her başarılı GET yazılsaydı günde megabaytlarca satır, dönen dosyadaki
    (5 MB × 3) önemli satırları iki günde dışarı iterdi. POST/PUT/DELETE
    (kural, kamera, bölge değişikliği) ve 4xx/5xx yanıtlar her zaman yazılır.
    uvicorn'un erişim kaydı argümanları: (istemci, yöntem, yol, sürüm, durum).
    """
    argumanlar = kayit.args
    if not isinstance(argumanlar, tuple) or len(argumanlar) != 5:
        return True  # biçimi bilinmeyen satır atılmaz
    yontem, durum = argumanlar[1], argumanlar[4]
    try:
        return yontem not in ("GET", "HEAD") or int(durum) >= 400
    except (TypeError, ValueError):
        return True


def _uvicornu_bagla() -> None:
    """uvicorn günlüklerini aynı JSON biçimine ve dosyaya bağlar (docs/17 §9.4).

    uvicorn'a log yapılandırma dosyası verilmez: komut satırından (Docker,
    systemd, geliştirme) çalışırken uvicorn kendi düz metin işleyicilerini
    uygulamayı içe aktarmadan ÖNCE kurar, bu çağrı onları değiştirir.
    """
    aktarici = _DalsanaAktar()
    for ad in _UVICORN_ADLARI:
        logger = logging.getLogger(ad)
        logger.handlers.clear()
        logger.addHandler(aktarici)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    erisim = logging.getLogger("uvicorn.access")
    if _basarili_okumayi_ele not in erisim.filters:
        erisim.addFilter(_basarili_okumayi_ele)


def _ekran_akisini_hazirla() -> None:
    """Windows konsolu varsayılan olarak cp1254'tür; Türkçe karakter içeren bir
    log satırı UnicodeEncodeError verip LOG SİSTEMİNİ ÇÖKERTİR. UTF-8'e geçir,
    olmazsa bozuk karakteri hataya değil '?'e çevir."""
    for akis in (sys.stdout, sys.stderr):
        yeniden_yapilandir = getattr(akis, "reconfigure", None)
        if yeniden_yapilandir is None:
            continue
        try:
            yeniden_yapilandir(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Yönlendirilmiş ya da kapalı akışta yeniden yapılandırma başarısız
            # olabilir; log yine de çalışmalı.
            continue


def kur(ayarlar: Ayarlar) -> None:
    """Log sistemini bir kez kurar. İkinci çağrı eskisinin yerine geçer."""
    _ekran_akisini_hazirla()
    kok = logging.getLogger(_KOK_AD)
    kok.setLevel(logging.INFO)
    kok.propagate = False
    kok.handlers.clear()  # testlerde/yeniden kurulumda satırlar ikilenmesin

    # Ekran akışını Kontrol Paneli okuyup penceresinde gösteriyor: teknik
    # ayrıntı buraya YAZILMAZ, yalnızca dosyaya yazılır (modül başlığı).
    ekran = logging.StreamHandler()
    ekran.setFormatter(_JsonSatirBicimi(ayrintili=False))
    kok.addHandler(ekran)

    # Dosya sınırsız büyümesin diye 5 MB'ta döner, son 3 kopya saklanır —
    # 7x24 çalışan sistemde log yüzünden disk dolmasın (docs/08 R8).
    dosya = RotatingFileHandler(
        ayarlar.log_dosyasi, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    dosya.setFormatter(_JsonSatirBicimi(ayrintili=True))
    kok.addHandler(dosya)
    _uvicornu_bagla()


def log_al(bilesen: str) -> logging.Logger:
    """Bileşen adıyla logger döndürür: log_al('veritabani').info('...')"""
    return logging.getLogger(f"{_KOK_AD}.{bilesen}")

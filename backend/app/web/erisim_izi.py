"""Erişim izi (KVKK m.12 denetim izi; docs/17 §10.4, şema 010 `access_log`).

Kişisel veriye dokunan ya da onu koruyan ayarı değiştiren her istek bir satır
bırakır: kim (istemci adresi; tek şifreli sistemde başka "kim" yoktur), ne
zaman, ne yaptı, neye. Şifre, çerez, ayar değeri ve adres (RTSP, hoparlör)
ASLA yazılmaz: izin kendisi yeni bir sızıntı olmamalı.

Görüntüleme satırları (kanıt fotoğrafı, KKD kırpığı) aynı istemci aynı kaydı
`TEKRAR_ARALIGI_SN` içinde yeniden açarsa bir kez yazılır: olay listesindeki
küçük resimler ve sayfa yenilemeleri denetim izini gürültüye boğmasın. Bilgi
kaybı yoktur: "kim, hangi kaydı, hangi dakikada gördü" sorusu yine cevaplanır.
Değişiklik ve dışa aktarım satırları her seferinde yazılır.

İz yazılamazsa istek YİNE sonuçlanır ve günlüğe hata düşer: bir veritabanı
kilidi yüzünden İSG uzmanının kanıta bakamaması daha kötü bir sonuçtur.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from fastapi import Request

from app import zaman
from app.loglama import log_al

_log = log_al("erisim")

EYLEMLER = frozenset(
    {
        "view_snapshot",
        "view_ppe_crop",
        "export_csv",
        "export_dataset",
        "settings_change",
        "rule_change",
        "hold_change",
        "ppe_collection_gate",
    }
)
GORUNTULEME_EYLEMLERI = frozenset({"view_snapshot", "view_ppe_crop"})
TEKRAR_ARALIGI_SN = 60.0

# Ayarlar → KVKK ekranındaki Türkçe karşılıklar
EYLEM_ADLARI = {
    "view_snapshot": "kanıt fotoğrafı görüntülendi",
    "view_ppe_crop": "KKD kırpığı görüntülendi",
    "export_csv": "CSV dışa aktarıldı",
    "export_dataset": "KKD veri seti dışa aktarıldı",
    "settings_change": "ayar değiştirildi",
    "rule_change": "kural değiştirildi",
    "hold_change": "olay dondurma değişti",
    "ppe_collection_gate": "KKD veri toplama kapısı değişti",
}

_son_yazilan: dict[tuple, float] = {}
_kilit = threading.Lock()


def istemci_adresi(istek: Request) -> str:
    """Doğrudan bağlantı adresi (R7 ile aynı): başlıktan okunmaz, taklit edilemez."""
    return istek.client.host if istek.client else "bilinmiyor"


def erisim_yaz(
    baglanti: sqlite3.Connection, istek: Request, eylem: str, hedef: str | None = None
) -> None:
    """Bir erişim izi satırı yazar (ya da tekrar aralığındaysa atlar)."""
    if eylem not in EYLEMLER:
        _log.error(f"Tanınmayan erişim eylemi: {eylem!r}")  # yazılım hatası; iz yine yazılır
    istemci = istemci_adresi(istek)
    if eylem in GORUNTULEME_EYLEMLERI:
        anahtar = (istemci, eylem, hedef)
        simdi = time.monotonic()
        with _kilit:
            son = _son_yazilan.get(anahtar)
            if son is not None and simdi - son < TEKRAR_ARALIGI_SN:
                return
            _son_yazilan[anahtar] = simdi
            if len(_son_yazilan) > 10_000:  # uzun çalışmada sözlük büyümesin
                _son_yazilan.clear()
                _son_yazilan[anahtar] = simdi
    try:
        baglanti.execute(
            "INSERT INTO access_log (at, client, action, target) VALUES (?, ?, ?, ?)",
            (zaman.simdi_utc(), istemci, eylem, hedef),
        )
        baglanti.commit()
    except sqlite3.Error as hata:
        _log.error(f"Erişim izi yazılamadı ({eylem} {hedef}): {hata}")


def hedef_metni(hedef: str | None) -> tuple[str, str | None]:
    """Ekrandaki karşılık ve varsa bağlantı.

    "event:12 hold=1" → ("olay #12 dondu", "/olaylar/12").
    """
    if not hedef:
        return "-", None
    ana, _, ek = hedef.partition(" ")
    tur, _, kimlik = ana.partition(":")
    ekler = {
        "hold=1": "dondu",
        "hold=0": "çözüldü",
        "golge=1": "gölgeye alındı",
        "golge=0": "anonsu açıldı",
    }
    ek = ekler.get(ek, ek)
    if tur == "event" and kimlik.isdigit():
        return f"olay #{kimlik} {ek}".strip(), f"/olaylar/{kimlik}"
    if tur == "sample" and kimlik.isdigit():
        return f"KKD örneği #{kimlik}", None
    if tur == "rule" and kimlik:
        return f"kural #{kimlik.replace(',', ', #')} {ek}".strip(), None
    if tur == "camera" and kimlik.isdigit():
        return f"kamera #{kimlik} {ek}".strip(), f"/kameralar/{kimlik}"
    return hedef, None


def kayitlar(baglanti: sqlite3.Connection, erisim_sayisi: int = 200, imha_sayisi: int = 50) -> dict:
    """Ayarlar → KVKK ekranı: son erişimler, son imha koşuları, dondurulan olay sayısı."""
    erisimler = []
    for satir in baglanti.execute(
        "SELECT at, client, action, target FROM access_log ORDER BY id DESC LIMIT ?",
        (erisim_sayisi,),
    ):
        metin, bag = hedef_metni(satir["target"])
        erisimler.append(
            {
                "zaman": zaman.ekranda_goster(satir["at"]),
                "adres": satir["client"],
                "eylem": EYLEM_ADLARI.get(satir["action"], satir["action"]),
                "hedef": metin,
                "bag": bag,
            }
        )
    imhalar = []
    for satir in baglanti.execute(
        "SELECT * FROM purge_log ORDER BY id DESC LIMIT ?", (imha_sayisi,)
    ):
        try:
            politika = json.loads(satir["policy"])
        except (TypeError, ValueError):
            politika = {}
        imhalar.append(
            {
                "zaman": zaman.ekranda_goster(satir["ran_at"]),
                "olay": satir["events_deleted"],
                "foto": satir["photos_deleted"],
                "ornek": satir["samples_deleted"],
                "donmus": satir["held_skipped"],
                "politika": " · ".join(
                    f"{ad} {politika[anahtar]} gün"
                    for anahtar, ad in (
                        ("olay_gun", "olay"),
                        ("sistem_olay_gun", "sistem olayı"),
                        ("goruntu_gun", "fotoğraf"),
                        ("kkd_ham_veri_gun", "KKD örneği"),
                        ("uyari_kaydi_gun", "uyarı kaydı arşivi"),
                    )
                    if anahtar in politika
                ),
                # 011: arşivlenip silinen uyarı kaydı ve yazıldığı dosya
                "uyari": satir["alerts_archived"],
                "uyari_dosyasi": Path(satir["alert_archive_file"]).name
                if satir["alert_archive_file"]
                else "",
            }
        )
    dondurulmus = baglanti.execute("SELECT COUNT(*) FROM events WHERE hold = 1").fetchone()[0]
    return {"erisimler": erisimler, "imhalar": imhalar, "dondurulmus": dondurulmus}


def tekrar_bellegini_temizle() -> None:
    """Testler için: görüntüleme tekrar belleğini boşaltır."""
    with _kilit:
        _son_yazilan.clear()

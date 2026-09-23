"""Uyarı teslim kaydı (alert_deliveries, şema 009; docs/17 §7.3-10, §7.10).

Her uyarı denemesi bir satır bırakır: hangi olay, hangi kanal, sonuç ve
yazılım gecikmesi. "Anons çaldı mı" sorusunun cevabı ve uyarı garantisinin
(§7.4) ölçüsü buradadır. Ayrıntı MASKELİ yazılır: adres ve şifre günlüğe de
bu tabloya da düşmez (R18).

Yazma tek bir "uyari-kayit" iş parçacığında, kendi bağlantısıyla yapılır:
analiz iş parçacığı veritabanı yazmasını beklemez, çıkış işçileri de
birbirinin yazmasını. Yazılamayan satır uyarıyı durdurmaz; günlüğe düşer.
"""

from __future__ import annotations

import queue
import sqlite3
import statistics
import threading
import time
from pathlib import Path

from app import veritabani, zaman
from app.loglama import adres_maskele, log_al

_log = log_al("anons")

_AYRINTI_EN_UZUN = 500

# Sesli/uzak kanallar: garantiye ve teslim oranına bunlar sayılır (§7.4)
SESLI_KANALLAR = ("ses_karti", "http")


class TeslimKaydedici:
    """alert_deliveries ve speaker_zones.last_announced_at yazan tek iş parçacığı."""

    def __init__(self, veritabani_yolu: Path) -> None:
        self._yol = veritabani_yolu
        self._kuyruk: queue.Queue = queue.Queue()
        self._is: threading.Thread | None = None
        self._kilit = threading.Lock()

    def teslim(self, satir: dict) -> None:
        self._baslat()
        self._kuyruk.put(("teslim", satir))

    def son_anons(self, kanal_id: int, zaman_utc: str) -> None:
        self._baslat()
        self._kuyruk.put(("son_anons", (kanal_id, zaman_utc)))

    def bosalt(self, zaman_asimi: float) -> bool:
        """Sıradaki yazmalar bitene kadar bekler (testler ve kapanış)."""
        son = time.monotonic() + zaman_asimi
        while self._kuyruk.unfinished_tasks:
            if time.monotonic() > son:
                return False
            time.sleep(0.01)
        return True

    def durdur(self, zaman_asimi: float) -> None:
        self.bosalt(zaman_asimi)
        with self._kilit:
            if self._is is not None:
                self._kuyruk.put(("dur", None))
                self._is.join(timeout=1.0)
                self._is = None

    def _baslat(self) -> None:
        with self._kilit:
            if self._is is None or not self._is.is_alive():
                self._is = threading.Thread(target=self._dongu, name="uyari-kayit", daemon=True)
                self._is.start()

    def _dongu(self) -> None:
        baglanti: sqlite3.Connection | None = None
        try:
            while True:
                tur, veri = self._kuyruk.get()
                try:
                    if tur == "dur":
                        return
                    if baglanti is None:
                        baglanti = veritabani.baglanti_ac(self._yol)
                    if tur == "teslim":
                        _teslim_ekle(baglanti, veri)
                    else:
                        baglanti.execute(
                            "UPDATE speaker_zones SET last_announced_at = ? WHERE id = ?",
                            (veri[1], veri[0]),
                        )
                        baglanti.commit()
                except (sqlite3.Error, OSError) as hata:
                    _log.warning(f"Uyarı teslim kaydı yazılamadı: {hata}")
                    if baglanti is not None:
                        baglanti.close()
                    baglanti = None
                finally:
                    self._kuyruk.task_done()
        finally:
            if baglanti is not None:
                baglanti.close()


def teslim_satiri(
    *,
    kanal: str,
    asama: str,
    sonuc: str,
    kuyruga_giris_utc: str,
    olay_id: int | None = None,
    olay_kodu: str | None = None,
    kanal_id: int | None = None,
    ayrinti: str = "",
    baslama_utc: str | None = None,
    bitis_utc: str | None = None,
    kareden_baslamaya_ms: int | None = None,
) -> dict:
    return {
        "event_id": olay_id,
        "event_code": olay_kodu,
        "speaker_zone_id": kanal_id,
        "channel": kanal,
        "stage": asama,
        "result": sonuc,
        "detail": adres_maskele(ayrinti)[:_AYRINTI_EN_UZUN] or None,
        "queued_at": kuyruga_giris_utc,
        "started_at": baslama_utc,
        "finished_at": bitis_utc,
        "frame_to_start_ms": kareden_baslamaya_ms,
    }


_SUTUNLAR = (
    "event_id",
    "event_code",
    "speaker_zone_id",
    "channel",
    "stage",
    "result",
    "detail",
    "queued_at",
    "started_at",
    "finished_at",
    "frame_to_start_ms",
)
_EKLE = (
    f"INSERT INTO alert_deliveries ({', '.join(_SUTUNLAR)}) "
    f"VALUES ({', '.join('?' * len(_SUTUNLAR))})"
)


def _teslim_ekle(baglanti: sqlite3.Connection, satir: dict) -> None:
    """Satırı yazar. Kanal ya da olay bu arada silindiyse (yabancı anahtar)
    bağ boş bırakılır; iz kaybolmaz (şema 009: ON DELETE SET NULL / NULL)."""
    for bos_birakilan in ((), ("speaker_zone_id",), ("speaker_zone_id", "event_id")):
        degerler = [None if s in bos_birakilan else satir.get(s) for s in _SUTUNLAR]
        try:
            baglanti.execute(_EKLE, degerler)
            baglanti.commit()
            return
        except sqlite3.IntegrityError:
            baglanti.rollback()
    raise sqlite3.IntegrityError("alert_deliveries satırı yabancı anahtar yüzünden yazılamadı")


def teslim_yaz(baglanti: sqlite3.Connection, satir: dict) -> None:
    """Eşzamanlı yazma (web isteğinin kendi bağlantısıyla; kanal denemesi)."""
    try:
        _teslim_ekle(baglanti, satir)
    except sqlite3.Error as hata:
        _log.warning(f"Uyarı teslim kaydı yazılamadı: {hata}")


def _yuzdelik(degerler: list[int], yuzde: int) -> int | None:
    if not degerler:
        return None
    if len(degerler) == 1:
        return degerler[0]
    return round(statistics.quantiles(degerler, n=100, method="inclusive")[yuzde - 1])


def teslim_ozeti(baglanti: sqlite3.Connection, saat: int = 24) -> dict:
    """Son `saat` saatin teslim sayıları ve yazılım gecikmesi (p50/p90).

    Oran yalnız GERÇEK uyarıların (açılış, hatırlatma) sesli/uzak kanal
    denemelerinden hesaplanır: bastırılan (az önce zaten duyurulmuş) ve gölge
    kayıt deneme değildir, test sesi uyarı değildir. Deneme yoksa oran None:
    "ölçülemedi" yazılır, %100 değil.
    """
    sinir = zaman.saniye_once_utc(saat * 3600)
    satirlar = baglanti.execute(
        "SELECT channel, result, frame_to_start_ms, speaker_zone_id FROM alert_deliveries "
        "WHERE queued_at >= ? AND stage IN ('acildi', 'hatirlatma')",
        (sinir,),
    ).fetchall()
    sesli = [s for s in satirlar if s["channel"] in SESLI_KANALLAR]
    denemeler = [s for s in sesli if s["result"] not in ("suppressed_cooldown", "shadow")]
    caldi = [s for s in denemeler if s["result"] == "ok"]
    gecikmeler = sorted(s["frame_to_start_ms"] for s in caldi if s["frame_to_start_ms"] is not None)
    ekran = [s for s in satirlar if s["channel"] == "ekran"]
    sayilar: dict[str, int] = {}
    for s in sesli:
        sayilar[s["result"]] = sayilar.get(s["result"], 0) + 1
    kanal_basina: dict[int, dict[str, int]] = {}
    for s in sesli:
        if s["speaker_zone_id"] is None:
            continue
        sayac = kanal_basina.setdefault(s["speaker_zone_id"], {})
        sayac[s["result"]] = sayac.get(s["result"], 0) + 1
    return {
        "saat": saat,
        "deneme": len(denemeler),
        "caldi": len(caldi),
        "oran": (len(caldi) / len(denemeler)) if denemeler else None,
        "sayilar": sayilar,
        "kanal_basina": kanal_basina,
        "p50_ms": _yuzdelik(gecikmeler, 50),
        "p90_ms": _yuzdelik(gecikmeler, 90),
        "olculen": len(gecikmeler),
        "ekran_olay": len(ekran),
        "ekran_dinleyen_yok": sum(1 for s in ekran if s["result"] == "no_listener"),
        "golge": sum(1 for s in satirlar if s["result"] == "shadow"),
    }

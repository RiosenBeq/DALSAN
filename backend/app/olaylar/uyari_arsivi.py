"""Uyarı kayıtlarının dönemsel arşivi: önce masaüstüne, sonra temizlik.

Operatör isteği (23.09.2026): *"sistemde uyarı loglarını da tut 15 günde bir
de temizlensin ama öncesinde temizlenmeden olan loglar masaüstüne
kaydedilsin"*.

Uyarı kaydı = teslim kaydı (`alert_deliveries`): her uyarının hangi olay için,
hangi kanaldan, ne zaman ve hangi sonuçla (çaldı, çalamadı, gölge...) gittiği.
Olayın kendisi (olay listesi, kanıt fotoğrafı) burada SİLİNMEZ; onun süresi
OLAY_SAKLAMA_GUN'dür (docs/17 S5).

Döngü: bakım günde bir bakar. Sistemdeki en eski uyarı kaydı
UYARI_KAYDI_ARSIV_GUN günü doldurmuşsa o ana kadarki bütün kayıtlar önce
masaüstündeki klasöre CSV olarak yazılır; dosya diske işlenir ve geri okunup
satır sayısı doğrulanır; SONRA yalnız yazılan satırlar silinir. Dosya
yazılamazsa hiçbir satır silinmez ve bakım ertesi gün yeniden dener.

Dondurulan olayın (hukuki süreç, şema 010) teslim kaydı ne arşivlenir ne
silinir: kanıtın parçasıdır ve sistemde kalır. Dondurma kalkınca bir sonraki
döngüde arşive girer.
"""

from __future__ import annotations

import csv
import os
import sqlite3
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app import kaynaklar, zaman
from app.csv_yazici import CsvYazici
from app.rules.olay_kodu import OLAY_KODLARI, ONEM_ADLARI

# Masaüstündeki klasörün adı: CSV'ler masaüstüne tek tek dağılmasın
KLASOR_ADI = f"{kaynaklar.UYGULAMA_ADI} uyarı kayıtları"

BASLIKLAR = (
    "Uyarı zamanı",
    "Kamera",
    "Bölüm",
    "Uyarı",
    "Önem",
    "Olay no",
    "Aşama",
    "Kanal",
    "Kanal türü",
    "Sonuç",
    "Kare-ses (ms)",
    "Ayrıntı",
)

ASAMA_ADLARI = {
    "acildi": "açıldı",
    "hatirlatma": "hatırlatma",
    "kapandi": "kapandı",
    "test": "deneme",
}
KANAL_TURLERI = {"ses_karti": "ses çıkışı", "http": "IP hoparlör", "ekran": "ekran"}
SONUC_ADLARI = {
    "ok": "çaldı",
    "failed": "çalamadı",
    "shadow": "gölge modda, çalınmadı",
    "stale": "bayatladı, çalınmadı",
    "preempted": "kritik uyarı için kesildi",
    "no_listener": "açık izleme ekranı yok",
    "suppressed_cooldown": "tekrar, bastırıldı",
    "fallback": "bölüm kanalı koptu, “Tüm fabrika”dan duyuruldu",
}

# Arşive giren satırlar: olayı dondurulmamış (ya da olay satırı olmayan:
# deneme sesi, olay yazılamadığında giden fail-safe uyarı)
_KAPSAM = (
    "FROM alert_deliveries d "
    "LEFT JOIN events e ON e.id = d.event_id "
    "LEFT JOIN cameras c ON c.id = e.camera_id "
    "LEFT JOIN speaker_zones z ON z.id = d.speaker_zone_id "
    "WHERE (e.id IS NULL OR e.hold = 0)"
)
_SILME_PARCASI = 500  # SQLite parametre sınırının çok altında


class ArsivHatasi(Exception):
    """Arşiv dosyası yazılamadı ya da doğrulanamadı: hiçbir satır silinmedi."""


@dataclass(frozen=True)
class ArsivSonucu:
    satir: int  # arşivlenip silinen satır
    dosya: Path


def masaustu_klasoru(
    platform: str | None = None,
    ev: Path | None = None,
    ortam: Mapping[str, str] | None = None,
) -> Path | None:
    """Oturumdaki kullanıcının masaüstü; bulunamazsa None.

    Windows'ta bilinen klasör API'si sorulur (masaüstü OneDrive'a ya da ağa
    yönlendirilmiş olabilir). Linux'ta masaüstünün adı dile göre değişir
    (Türkçe Ubuntu'da "Masaüstü"): XDG `user-dirs.dirs` okunur. Sunucuda
    masaüstü yoksa None döner; çağıran veri klasörüne düşer.
    """
    platform = platform or sys.platform
    ev = ev or Path.home()
    ortam = os.environ if ortam is None else ortam
    if platform == "win32":
        adaylar = [_windows_masaustu(), Path(ortam.get("USERPROFILE", str(ev))) / "Desktop"]
    elif platform == "darwin":
        adaylar = [ev / "Desktop"]
    else:
        adaylar = [_xdg_masaustu(ev, ortam), ev / "Masaüstü", ev / "Desktop"]
    return next((a for a in adaylar if a is not None and a.is_dir()), None)


def _xdg_masaustu(ev: Path, ortam: Mapping[str, str]) -> Path | None:
    """`~/.config/user-dirs.dirs` içindeki XDG_DESKTOP_DIR (freedesktop.org).

    Değer "$HOME/" ise masaüstü kapatılmıştır; ev klasörünün köküne dosya
    bırakılmaz.
    """
    yapilandirma = Path(ortam.get("XDG_CONFIG_HOME") or ev / ".config")
    try:
        metin = (yapilandirma / "user-dirs.dirs").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for satir in metin.splitlines():
        satir = satir.strip()
        if not satir.startswith("XDG_DESKTOP_DIR="):
            continue
        deger = satir.split("=", 1)[1].strip().strip('"').replace("$HOME", str(ev))
        yol = Path(deger)
        if yol.is_absolute() and yol.resolve() != ev.resolve():
            return yol
    return None


def _windows_masaustu() -> Path | None:
    """SHGetKnownFolderPath(FOLDERID_Desktop). Windows dışında None."""
    try:
        import ctypes
        from ctypes import wintypes

        class _Guid(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
        kimlik = _Guid(
            0xB4BFCC3A,
            0xDB2C,
            0x424C,
            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
        )
        yol = ctypes.c_wchar_p()
        kabuk = ctypes.windll.shell32  # type: ignore[attr-defined]
        sonuc = kabuk.SHGetKnownFolderPath(ctypes.byref(kimlik), 0, None, ctypes.byref(yol))
        try:
            return Path(yol.value) if sonuc == 0 and yol.value else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(yol)  # type: ignore[attr-defined]
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def arsiv_klasoru(ayarlar) -> Path:
    """CSV'lerin yazılacağı klasör.

    Sıra: UYARI_KAYDI_ARSIV_KLASORU (göreli ise program klasörüne göre) →
    masaüstündeki "<uygulama> uyarı kayıtları" → veri/arsiv/uyari-kayitlari.
    Docker'da masaüstü yoktur: veri klasörü sunucudaki bağlı klasördür.
    """
    if ayarlar.uyari_kaydi_arsiv_klasoru:
        yol = Path(ayarlar.uyari_kaydi_arsiv_klasoru).expanduser()
        return yol if yol.is_absolute() else ayarlar.kok_dizin / yol
    masaustu = None if kaynaklar.kapsayicida_mi() else masaustu_klasoru()
    if masaustu is not None:
        return masaustu / KLASOR_ADI
    return ayarlar.veri_dizini / "arsiv" / "uyari-kayitlari"


def arsiv_zamani_geldi_mi(baglanti: sqlite3.Connection, gun: int) -> bool:
    """En eski (dondurulmamış) uyarı kaydı `gun` günü doldurdu mu?"""
    if gun <= 0:
        return False
    en_eski = baglanti.execute(f"SELECT MIN(d.queued_at) {_KAPSAM}").fetchone()[0]
    return en_eski is not None and en_eski <= zaman.gun_once_utc(gun)


def arsivle_ve_temizle(baglanti: sqlite3.Connection, ayarlar) -> ArsivSonucu | None:
    """Zamanı geldiyse kayıtları CSV'ye yazar, doğrular ve siler.

    Zamanı gelmediyse None. Dosya yazılamaz ya da doğrulanamazsa ArsivHatasi
    yükselir ve veritabanına dokunulmaz.
    """
    if not arsiv_zamani_geldi_mi(baglanti, ayarlar.uyari_kaydi_arsiv_gun):
        return None
    satirlar = baglanti.execute(
        "SELECT d.id, d.queued_at, d.event_id, d.event_code, d.stage, d.channel, "
        "d.result, d.detail, d.frame_to_start_ms, e.severity, c.name AS kamera, "
        f"c.area AS bolum, z.name AS kanal_adi {_KAPSAM} ORDER BY d.id"
    ).fetchall()
    if not satirlar:
        return None
    klasor = arsiv_klasoru(ayarlar)
    ilk = zaman.yerel_tarih_iso(satirlar[0]["queued_at"])
    son = zaman.yerel_tarih_iso(satirlar[-1]["queued_at"])
    try:
        dosya = _yaz_ve_dogrula(klasor, f"uyari-kayitlari_{ilk}_{son}", satirlar)
    except (OSError, csv.Error, UnicodeError) as hata:
        raise ArsivHatasi(f"{klasor}: {hata}") from hata

    kimlikler = [s["id"] for s in satirlar]
    silinen = 0
    for i in range(0, len(kimlikler), _SILME_PARCASI):
        parca = kimlikler[i : i + _SILME_PARCASI]
        # Yazma ile silme arasında dondurulan olayın kaydı yine silinmez
        silinen += baglanti.execute(
            f"DELETE FROM alert_deliveries WHERE id IN ({','.join('?' * len(parca))}) "
            "AND (event_id IS NULL OR event_id NOT IN (SELECT id FROM events WHERE hold = 1))",
            parca,
        ).rowcount
    baglanti.commit()
    return ArsivSonucu(satir=silinen, dosya=dosya)


def _yaz_ve_dogrula(klasor: Path, taban: str, satirlar: list[sqlite3.Row]) -> Path:
    """Geçici adla yazar, diske işler, yerine koyar ve geri okuyup sayar.

    Aynı adlı dosya varsa üzerine yazılmaz; "-2", "-3" eklenir. BOM'lu UTF-8:
    Excel Türkçe harfleri ancak böyle doğru açar (olay CSV'si de öyle).
    """
    klasor.mkdir(parents=True, exist_ok=True)
    hedef = klasor / f"{taban}.csv"
    sira = 2
    while hedef.exists():
        hedef = klasor / f"{taban}-{sira}.csv"
        sira += 1
    gecici = hedef.with_name(hedef.name + ".yaziliyor")
    try:
        with open(gecici, "w", encoding="utf-8-sig", newline="") as akim:
            yazici = CsvYazici(akim)
            yazici.writerow(BASLIKLAR)
            for satir in satirlar:
                yazici.writerow(_csv_satiri(satir))
            akim.flush()
            os.fsync(akim.fileno())
        os.replace(gecici, hedef)
    finally:
        gecici.unlink(missing_ok=True)
    with open(hedef, encoding="utf-8-sig", newline="") as akim:
        okunan = sum(1 for _ in csv.reader(akim, delimiter=";")) - 1
    if okunan != len(satirlar):
        raise OSError(f"{hedef.name} doğrulanamadı: {okunan}/{len(satirlar)} satır okundu")
    return hedef


def _csv_satiri(satir: sqlite3.Row) -> list:
    kod = satir["event_code"]
    tanim = OLAY_KODLARI.get(kod) if kod else None
    if satir["stage"] == "test":
        uyari = "Deneme sesi"
    else:
        uyari = tanim.ad if tanim else (kod or "")
    return [
        zaman.ekranda_goster(satir["queued_at"]),
        satir["kamera"] or "",
        satir["bolum"] or "",
        uyari,
        ONEM_ADLARI.get(satir["severity"], "") if satir["severity"] else "",
        satir["event_id"] if satir["event_id"] is not None else "",
        ASAMA_ADLARI.get(satir["stage"], satir["stage"]),
        satir["kanal_adi"] or "",
        KANAL_TURLERI.get(satir["channel"], satir["channel"]),
        SONUC_ADLARI.get(satir["result"], satir["result"]),
        satir["frame_to_start_ms"] if satir["frame_to_start_ms"] is not None else "",
        satir["detail"] or "",
    ]

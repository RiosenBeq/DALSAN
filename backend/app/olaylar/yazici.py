"""Olay kaydı: kanıt fotoğrafı ÖNCE, veritabanı kaydı SONRA (docs/02 §3).

Böylece fotoğrafsız olay kaydı ("yetim kayıt") oluşmaz; fotoğraf yazılamazsa
olay fotoğrafsız ama açıklamalı kaydedilir — olay asla kaybolmaz.

Şema 007'den beri her olay bir kod, bir önem ve bir bitiş taşır (docs/17
§6.1): `resolved_at` boşsa olay SÜRÜYORDUR. Anlık olayda bitiş başlangıçla
aynıdır. Süren olayı açan taraf kapatır (`olay_kapat`); süreç açılırken ve
düzgün kapanırken açık kalan her olay `acik_olaylari_kapat` ile kapatılır,
yoksa ekranda sonsuza kadar "sürüyor" görünürdü.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from app import zaman
from app.ayarlar import Ayarlar
from app.loglama import log_al
from app.rules.olay_kodu import (
    KAPANIS_SEBEPLERI,
    OLAY_KODLARI,
    ONEM_SISTEM,
    SUREN_SISTEM_KODLARI,
)
from app.rules.tipler import Ihlal

_log = log_al("olay")


def ihlal_yaz(
    baglanti: sqlite3.Connection,
    ayarlar: Ayarlar,
    ihlal: Ihlal,
    kural_kaydi: dict,
    kanit_jpeg: bytes | None,
) -> int:
    """İhlali events tablosuna yazar; olay id'sini döndürür."""
    simdi = zaman.simdi_utc()

    foto_yolu: str | None = None
    if kanit_jpeg is not None:
        foto_yolu = _fotograf_kaydet(ayarlar, ihlal.kamera_id, simdi, kanit_jpeg)

    # Kural veya kamera, değerlendirme ile kayıt arasında silinmiş olabilir
    # (süpervizörün 5 sn'lik konfig penceresi). Olay FK hatasıyla KAYBOLMAZ:
    # ilgili alan boş bırakılır; anlam rule_snapshot/details içinde saklıdır.
    kural_id: int | None = ihlal.kural_id
    if baglanti.execute("SELECT 1 FROM rules WHERE id = ?", (kural_id,)).fetchone() is None:
        kural_id = None
    kamera_id = _kamera_id_dogrula(baglanti, ihlal.kamera_id)

    # Kodsuz ihlal (motor dışından yazılan) eski olay gibi görünür: ekran kural
    # tipinin adını kullanır. Motor her ihlale kod atar (rules/motor.py).
    imlec = baglanti.execute(
        "INSERT INTO events (occurred_at, event_type, camera_id, rule_id, "
        "rule_snapshot, details, snapshot_path, status, event_code, severity, resolved_at) "
        "VALUES (?, 'violation', ?, ?, ?, ?, ?, 'new', ?, ?, ?)",
        (
            simdi,
            kamera_id,
            kural_id,
            json.dumps(kural_kaydi, ensure_ascii=False),
            json.dumps(
                {**ihlal.detaylar, "takip_idler": ihlal.takip_idler, "olculen": ihlal.olculen},
                ensure_ascii=False,
            ),
            foto_yolu,
            ihlal.kod or None,
            ihlal.onem or None,
            # Olay yaşam döngüsü gelene kadar (docs/17 §6.3) her ihlal anlıktır.
            simdi,
        ),
    )
    baglanti.commit()
    return int(imlec.lastrowid)


def sistem_olayi_yaz(
    baglanti: sqlite3.Connection,
    mesaj: str,
    kamera_id: int | None = None,
    detaylar: dict | None = None,
    *,
    kod: str,
) -> int:
    """Kamera koptu/geldi, disk azaldı gibi sistem olayları — aynı listede
    görünür (docs/01 §3.5): kamera 3 gün kapalıysa İSG bilmeli.

    `kod` zorunludur (rules/olay_kodu.py). Kapatanı olan kod (CAMERA_DOWN)
    açık doğar; kapatmak, olayı açan tarafın işidir. Olay id'sini döndürür.
    """
    tanim = OLAY_KODLARI.get(kod)
    if tanim is None or not tanim.sistem_mi:
        # Yazılım hatası: testler (test_olay_kodu) bunu yakalar. Olay yine de
        # yazılır — kodu yanlış diye kaybolan bir "kamera koptu" daha kötüdür.
        _log.error(f"Sistem olayı tanınmayan bir kodla yazıldı: {kod!r}")
    simdi = zaman.simdi_utc()
    imlec = baglanti.execute(
        "INSERT INTO events (occurred_at, event_type, camera_id, details, status, "
        "event_code, severity, resolved_at) VALUES (?, 'system', ?, ?, 'new', ?, ?, ?)",
        (
            simdi,
            _kamera_id_dogrula(baglanti, kamera_id),
            json.dumps({"mesaj": mesaj, **(detaylar or {})}, ensure_ascii=False),
            kod,
            ONEM_SISTEM,
            None if kod in SUREN_SISTEM_KODLARI else simdi,
        ),
    )
    baglanti.commit()
    return int(imlec.lastrowid)


def olay_kapat(
    baglanti: sqlite3.Connection, olay_id: int, sebep: str, bitis_utc: str | None = None
) -> bool:
    """Süren olayı kapatır: bitiş yazılır, sebep ayrıntıya eklenir.

    Zaten kapanmış (ya da silinmiş) olaya dokunmaz; döner: kapatıldı mı.
    """
    satir = baglanti.execute(
        "SELECT id, occurred_at, details FROM events WHERE id = ? AND resolved_at IS NULL",
        (olay_id,),
    ).fetchone()
    if satir is None:
        return False
    _kapat(baglanti, satir, sebep, bitis_utc or zaman.simdi_utc())
    baglanti.commit()
    return True


def acik_olaylari_kapat(
    baglanti: sqlite3.Connection, sebep: str, bitis_utc: str | None = None
) -> int:
    """Açık kalan BÜTÜN olayları kapatır (süreç açılışı ve kapanışı).

    Açılışta bulunan açık olay, önceki çalışmanın kapatamadığı olaydır
    (elektrik kesintisi, çökme): koşulun ne zaman bittiği bilinmez, bitiş
    olarak şimdi yazılır ve sebep bunu söyler. Döner: kapatılan olay sayısı.
    """
    bitis = bitis_utc or zaman.simdi_utc()
    satirlar = baglanti.execute(
        "SELECT id, occurred_at, details FROM events WHERE resolved_at IS NULL"
    ).fetchall()
    for satir in satirlar:
        _kapat(baglanti, satir, sebep, bitis)
    baglanti.commit()
    return len(satirlar)


def _kapat(baglanti: sqlite3.Connection, satir, sebep: str, bitis: str) -> None:
    if sebep not in KAPANIS_SEBEPLERI:
        _log.error(f"Olay tanınmayan bir sebeple kapatıldı: {sebep!r}")  # olay yine kapanır
    try:
        ayrinti = json.loads(satir["details"]) if satir["details"] else {}
    except json.JSONDecodeError:
        ayrinti = {"ham": satir["details"]}  # elle bozulmuş satır kapanışı engellemesin
    if not isinstance(ayrinti, dict):
        ayrinti = {"ham": ayrinti}
    ayrinti["kapanis_sebebi"] = sebep
    # Bitiş başlangıçtan önce olamaz. Bitiş monotonik saatle ölçülmüş bir
    # süreden geri hesaplanır (zaman.saniye_once_utc); duvar saati bu arada
    # geri alındıysa (NTP) süre eksiye düşer ve rapordaki toplamları bozardı.
    # Metin karşılaştırması doğrudur: ikisi de aynı biçimde UTC (zaman.py).
    baglanti.execute(
        "UPDATE events SET resolved_at = ?, details = ? WHERE id = ?",
        (max(bitis, satir["occurred_at"]), json.dumps(ayrinti, ensure_ascii=False), satir["id"]),
    )


def _kamera_id_dogrula(baglanti: sqlite3.Connection, kamera_id: int | None) -> int | None:
    """Silinmiş kameranın id'si yerine None döner (FK hatasıyla olay kaybolmasın)."""
    if kamera_id is None:
        return None
    var = baglanti.execute("SELECT 1 FROM cameras WHERE id = ?", (kamera_id,)).fetchone()
    return kamera_id if var is not None else None


def _fotograf_kaydet(ayarlar: Ayarlar, kamera_id: int, zaman_utc: str, jpeg: bytes) -> str | None:
    """Kanıt fotoğrafını veri/goruntuler/YYYY-AA/ altına yazar.

    Dönen yol, goruntu_klasoru köküne GÖRE tutulur — klasör taşınsa da
    kayıtlar geçerli kalır. Dosya adındaki rastgele son ek şarttır: zaman
    damgası saniye çözünürlüklü; aynı saniyede iki ihlal aynı ada düşüp
    birbirinin KANITINI ezerdi.
    """
    tarih = zaman_utc[:7]  # "2026-08"
    tekil = uuid.uuid4().hex[:8]
    dosya_adi = f"{zaman_utc.replace(':', '-').replace('+', 'Z')}-k{kamera_id}-{tekil}.jpg"
    goreli = str(Path(tarih) / dosya_adi)
    tam_yol = ayarlar.goruntu_klasoru / goreli
    try:
        tam_yol.parent.mkdir(parents=True, exist_ok=True)
        tam_yol.write_bytes(jpeg)
    except OSError as hata:
        # Fotoğraf yazılamadı diye olay kaybolmaz; sebep log'a düşer
        _log.error(
            f"Kanıt fotoğrafı diske yazılamadı: {hata}",
            extra={"ayrinti": f"dosya: {tam_yol}"},
        )
        return None
    return goreli

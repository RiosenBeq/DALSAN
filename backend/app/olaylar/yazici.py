"""Olay kaydı: kanıt fotoğrafı ÖNCE, veritabanı kaydı SONRA (docs/02 §3).

Böylece fotoğrafsız olay kaydı ("yetim kayıt") oluşmaz; fotoğraf yazılamazsa
olay fotoğrafsız ama açıklamalı kaydedilir — olay asla kaybolmaz.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from app import zaman
from app.ayarlar import Ayarlar
from app.loglama import log_al
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

    imlec = baglanti.execute(
        "INSERT INTO events (occurred_at, event_type, camera_id, rule_id, "
        "rule_snapshot, details, snapshot_path, status) "
        "VALUES (?, 'violation', ?, ?, ?, ?, ?, 'new')",
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
        ),
    )
    baglanti.commit()
    return int(imlec.lastrowid)


def sistem_olayi_yaz(
    baglanti: sqlite3.Connection,
    mesaj: str,
    kamera_id: int | None = None,
    detaylar: dict | None = None,
) -> None:
    """Kamera koptu/geldi, disk azaldı gibi sistem olayları — aynı listede
    görünür (docs/01 §3.5): kamera 3 gün kapalıysa İSG bilmeli."""
    baglanti.execute(
        "INSERT INTO events (occurred_at, event_type, camera_id, details, status) "
        "VALUES (?, 'system', ?, ?, 'new')",
        (
            zaman.simdi_utc(),
            _kamera_id_dogrula(baglanti, kamera_id),
            json.dumps({"mesaj": mesaj, **(detaylar or {})}, ensure_ascii=False),
        ),
    )
    baglanti.commit()


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
        _log.error(f"Kanıt fotoğrafı yazılamadı ({tam_yol}): {hata}")
        return None
    return goreli

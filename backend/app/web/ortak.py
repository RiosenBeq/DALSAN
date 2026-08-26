"""Web katmanının ortak yardımcıları: istek başına veritabanı bağlantısı,
RTSP maskeleme ve Türkçe etiket tabloları."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from fastapi import Request

from app import veritabani

# Kullanıcıya görünen Türkçe adlar (kod içi değerler İngilizce kalır)
BOLGE_TIPLERI = {
    "pedestrian_path": "Yaya yolu",
    "loading_area": "Yükleme alanı",
    "truck_parking": "Tır park alanı",
    "vehicle_area": "Araç sahası",
    "ppe_required": "KKD zorunlu alan",
    "restricted": "Yasak bölge",
}

KURAL_TIPLERI = {
    "zone_intrusion": "Bölge ihlali",
    "safe_distance": "Güvenli mesafe",
    "ppe_violation": "KKD (baret/yelek)",
}

OLAY_DURUMLARI = {"new": "Yeni", "reviewed": "İncelendi", "false_alarm": "Yanlış alarm"}

SINIFLAR = {"person": "İnsan", "forklift": "Forklift", "truck": "Tır/Araç"}


def baglanti_al(istek: Request) -> Iterator:
    """İstek başına SQLite bağlantısı (FastAPI dependency)."""
    baglanti = veritabani.baglanti_ac(istek.app.state.ayarlar.veritabani_yolu)
    try:
        yield baglanti
    finally:
        baglanti.close()


def rtsp_maskele(url: str) -> str:
    """rtsp://kullanici:sifre@ip/... → rtsp://••••@ip/...  (docs/01 §3.6)."""
    return re.sub(r"//[^/@]+@", "//••••@", url)


def guvenli_json(veri) -> str:
    """<script> bloğuna gömülecek JSON — HTML'e özel karakterler kaçırılır.

    json.dumps `<`, `>`, `&` karakterlerini kaçırmaz; kullanıcı verisi (örn.
    bölge adı) `</script><img onerror=...>` içerirse depolanan XSS olurdu.
    Unicode kaçışları JSON içinde birebir aynı metni temsil eder.
    """
    metin = json.dumps(veri, ensure_ascii=False)
    return metin.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

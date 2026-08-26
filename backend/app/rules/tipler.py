"""Kural motorunun saf veri tipleri (CLAUDE.md §6).

Bu dosya yalnızca stdlib kullanır. Görüntü/veritabanı katmanları bu tiplere
ÇEVİRİP verir; kural motoru dış dünyayı hiç görmez.

Koordinat sözleşmesi:
- Tespit kutuları PİKSEL cinsinden (x1, y1, x2, y2), kare boyutu ayrıca verilir.
- Bölge poligonları ve kalibrasyon noktaları NORMALİZE (0-1) koordinattır —
  böylece kare çözünürlüğü değişse de bölgeler geçerli kalır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# KKD kararının üç durumu — "belirsiz" HİÇBİR ZAMAN ihlal sayılmaz (docs/04 §1)
VAR = "var"
YOK = "yok"
BELIRSIZ = "belirsiz"

# Tespit sınıfları (tek yerde; model etiket eşlemesi analiz/tespit.py'de)
SINIF_INSAN = "person"
SINIF_FORKLIFT = "forklift"
SINIF_TIR = "truck"


@dataclass
class KkdGozlem:
    """KKD sınıflandırıcısının TEK karedeki çıktısı. Karar burada VERİLMEZ;
    karar, zamansal oylamayla rules/kkd.py'de verilir."""

    baret: str  # var | yok | belirsiz
    yelek: str
    baret_guven: float = 0.0
    yelek_guven: float = 0.0
    # Hangi olayın hangi model sürümüyle üretildiği bilinmeden "model
    # iyileşti mi" sorusu cevaplanamaz (docs/04 §9) — olay kaydına yazılır.
    model_surumu: str = ""


@dataclass
class Tespit:
    """Bir karede tespit edilip takip edilen tek nesne."""

    sinif: str
    kutu: tuple[float, float, float, float]  # piksel (x1, y1, x2, y2)
    takip_id: int
    guven: float = 0.0
    hiz_mps: float | None = None  # kalibrasyonsuz kamerada None
    kkd_gozlemi: KkdGozlem | None = None  # bu karede değerlendirildiyse

    def ayak_noktasi(self) -> tuple[float, float]:
        """Kutunun alt-orta noktası (zemin teması). Bölge ve mesafe kararları
        bu noktayla verilir; merkez nokta perspektifte yanıltır (docs/02 §6)."""
        x1, _, x2, y2 = self.kutu
        return ((x1 + x2) / 2.0, y2)


@dataclass
class Bolge:
    id: int
    # pedestrian_path | loading_area | truck_parking | vehicle_area |
    # ppe_required | restricted
    tip: str
    poligon: list[tuple[float, float]]  # normalize (0-1), en az 3 nokta
    aktif: bool = True


@dataclass
class Kalibrasyon:
    """Normalize görüntü düzlemi → zemin düzlemi (metre) homografisi."""

    homografi: list[list[float]]  # 3x3


@dataclass
class Kural:
    id: int
    kamera_id: int
    tip: str  # zone_intrusion | safe_distance | ppe_violation
    bolge_id: int | None
    hedef_siniflar: list[str]
    params: dict
    cooldown_s: float
    anons_id: int | None = None
    siddet: str = "warning"


@dataclass
class Ihlal:
    kural_id: int
    kamera_id: int
    takip_idler: list[int]
    bolge_id: int | None
    olculen: float | None  # mesafe (m), kalış süresi (sn) vb. — kurala göre
    detaylar: dict = field(default_factory=dict)  # olay kaydının details JSON'ı

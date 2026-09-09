"""Kural parametre şemaları — rules.params JSON'ı yazılmadan ÖNCE ve
yüklenirken bu modellerle doğrulanır (docs/02 §3).

Varsayılanlar docs/03'teki tablolardan alınmıştır; hepsi arayüzden
düzenlenebilir ve değişiklik yeniden başlatma gerektirmez.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.hatalar import DalsanHata


class KuralParametreHatasi(DalsanHata):
    http_kodu = 400


class BolgeIhlaliParams(BaseModel):
    """zone_intrusion — docs/03 §1"""

    mode: Literal["inside", "outside"] = "inside"
    min_dwell_s: float = Field(default=2.0, ge=0, le=600)


class MesafeParams(BaseModel):
    """safe_distance — docs/03 §2"""

    subject_classes: list[str] = ["person"]
    object_classes: list[str] = ["forklift", "truck"]
    distance_m: float = Field(default=3.0, gt=0, le=100)
    min_frames: int = Field(default=5, ge=1, le=100)
    require_moving_vehicle: bool = True
    min_speed_mps: float = Field(default=0.3, ge=0, le=20)


class KkdParams(BaseModel):
    """ppe_violation — docs/03 §3 ve docs/04 §7"""

    required_ppe: list[Literal["helmet", "vest"]] = ["helmet", "vest"]
    # Baret ve yelek eşikleri AYRIDIR: baret kişi boyunun ~1/8'i olduğundan
    # 120 px ister; yelek büyük yüzeyiyle 80 px'te güvenilirdir (docs/04 §3)
    min_person_height_px: int = Field(default=120, ge=20, le=2000)
    min_vest_height_px: int = Field(default=80, ge=20, le=2000)
    min_confidence: float = Field(default=0.70, ge=0, le=1)
    window_size: int = Field(default=15, ge=3, le=100)
    min_valid_observations: int = Field(default=8, ge=1, le=100)
    violation_ratio: float = Field(default=0.75, ge=0.5, le=1)
    min_dwell_s: float = Field(default=3.0, ge=0, le=600)
    require_full_bbox: bool = True


class HizParams(BaseModel):
    """vehicle_speed — docs/03 §4

    Birim m/sn'dir; Tespit.hiz_mps ile aynı olsun diye. Kullanıcı arayüzünde
    karşılığı km/sa olarak da yazılır (2,5 m/sn ≈ 9 km/sa).

    Varsayılan 2,5 m/sn uydurma değildir: docs/07-YOL-HARITASI.md #15 bu kural
    tipini "forklift 2,5 m/s üstünde" örneğiyle tarif eder. Fabrikanın kendi
    hız sınırı farklıysa arayüzden değiştirilir.
    """

    speed_limit_mps: float = Field(default=2.5, gt=0, le=30)
    # Kararın dayandığı ölçüm sayısı. Ortanca alınır; tek karelik sıçrama
    # ihlal üretmez. 5 ölçüm, 6 fps'te ~1 saniyelik gözlem demektir.
    window_size: int = Field(default=5, ge=3, le=60)


PARAM_SEMALARI: dict[str, type[BaseModel]] = {
    "zone_intrusion": BolgeIhlaliParams,
    "safe_distance": MesafeParams,
    "ppe_violation": KkdParams,
    "vehicle_speed": HizParams,
}


def params_dogrula(kural_tipi: str, params: dict) -> dict:
    """params JSON'ını tipine göre doğrular; hatada anlaşılır Türkçe mesaj."""
    sema = PARAM_SEMALARI.get(kural_tipi)
    if sema is None:
        raise KuralParametreHatasi(f"Bilinmeyen kural tipi: {kural_tipi}")
    try:
        return sema(**params).model_dump()
    except Exception as hata:  # pydantic.ValidationError — pydantic tipine bağımlı olmayalım
        raise KuralParametreHatasi(f"Kural parametreleri geçersiz ({kural_tipi}): {hata}") from hata

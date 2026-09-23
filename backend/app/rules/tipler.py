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

# Sistemin TANIDIĞI sınıfların tam listesi (web/ortak.py'deki SINIFLAR
# tablosu bunların TÜRKÇE ADLARIDIR; ikisi karıştırılmasın) — sıra ANLAMLIDIR: takip katmanı
# (analiz/takip.py) sınıf numarasını bu sıradan üretir.
#
# NEDEN TEK LİSTE: eskiden sınıf→numara eşlemesi takip.py içinde ayrı bir
# sözlüktü. Tespit modeline yeni bir sınıf eklendiğinde (ör. saha verisiyle
# ince ayar yapılmış gerçek bir forklift modeli) o sözlük unutulur ve takip
# katmanı KeyError verirdi; hata her karede tekrarlandığı için o kamera
# kalıcı olarak körleşirdi. Artık iki taraf da bu listeyi okur.
TANINAN_SINIFLAR: tuple[str, ...] = (SINIF_INSAN, SINIF_TIR, SINIF_FORKLIFT)

# Bölge tipleri: kodların TEK kaynağı (docs/17 §4.5). Şema 007'den sonra
# veritabanında CHECK kısıtı yoktur (her yeni tip için tabloyu yeniden kurmak
# rules.zone_id … ON DELETE CASCADE tuzağını tekrar tekrar açardı); süzgeç
# yazımda web/kameralar.py, yüklemede süpervizördür ve ikisi de bu kümeyi
# kullanır. Türkçe adlar web/ortak.BOLGE_TIPLERI'ndedir (test eşitliği korur).
# rules/ app.web'i import edemez (test_saflik), bu yüzden kodlar burada durur.
BOLGE_TIPI_KODLARI: tuple[str, ...] = (
    "pedestrian_path",
    "loading_area",
    "truck_parking",
    "vehicle_area",
    "ppe_required",
    "restricted",
    "crossing",  # yaya-araç geçidi: ayak noktası buradaysa bölge ihlali sayılmaz
    "ppe_exempt",  # KKD muaf alan: KKD bölgesinden oyulur (kabin, ofis köşesi)
)
# Kendileri kural değil, başka kuralların İSTİSNASI olan tipler: hazır kuralları
# yoktur (docs/17 §4.3).
ISTISNA_BOLGE_TIPLERI: frozenset[str] = frozenset({"crossing", "ppe_exempt"})


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
    tip: str  # BOLGE_TIPI_KODLARI'ndan biri
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
    tip: str  # zone_intrusion | safe_distance | ppe_violation | vehicle_speed
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
    # Olay kodu ve önemi (rules/olay_kodu.py). Değerlendirici DOLDURMAZ:
    # kural motoru, kural ve bölge tipinden atar. Boş = kodsuz (motor dışı yol).
    kod: str = ""
    onem: str = ""

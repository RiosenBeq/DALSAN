"""Forklift sınıflandırıcısı eğitimi (docs/08 R1 — /forklift verisiyle ince ayar).

Akış:
    1. Etiketli kareler okunur (yes/no; 'belirsiz' eğitime girmez)
    2. Aday araç kutusu kırpılır, öznitelik çıkarılır
    3. ZAMANA GÖRE bölme: son %20 test (docs/04 §5.4 — rastgele bölme YASAK;
       aynı aracın ardışık kareleri hem eğitime hem teste düşer, skor yalan olur)
    4. Lojistik regresyon eğitilir (numpy, saniyeler; ek bağımlılık yok)
    5. ESKİ ve YENİ model AYNI test kareleri üzerinde karşılaştırılır.
       Eski model = bugünkü sistem: hiçbir aracı forklift saymaz (docs/08 R1).
    6. Sonuç HER KOŞULDA sürümlü kaydedilir (vNNN.npz + vNNN.json);
       yeni model yalnızca ölçülebilir şekilde daha iyiyse devreye alınır
       (aktif.json güncellenir). Kötü model sessizce devreye GİRMEZ.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

from app import zaman
from app.analiz.forklift_siniflandirici import ForkliftSiniflandirici, arac_kirp, oznitelik
from app.ayarlar import Ayarlar
from app.loglama import log_al

# Eğitim ön koşulları. Hedef 300-800 etiketli kare (docs/08 R1); eğitim daha
# erken DENENEBİLİR ama her iki sınıftan da yeterli örnek olmadan anlamsızdır.
EN_AZ_POZITIF = 50  # 'Forklift' etiketli kare
EN_AZ_NEGATIF = 50  # 'Değil' etiketli kare
TEST_PAYI = 0.2
EN_AZ_TEST = 20
KARAR_ESIGI = 0.5

# Lojistik regresyon parametreleri — deterministik (rastgelelik yok)
_OGRENME_ADIMI = 0.5
_TUR_SAYISI = 300
_L2 = 1e-3


@dataclass
class EgitimSonucu:
    """Kullanıcıya sayılarla gösterilecek eğitim çıktısı."""

    hata: str | None = None  # doluysa eğitim çalışmadı, diğer alanlar boş
    surum: str = ""
    egitim_sayisi: int = 0
    test_sayisi: int = 0
    pozitif_sayisi: int = 0  # tüm veri setindeki 'Forklift' kareleri
    negatif_sayisi: int = 0
    atlanan_sayisi: int = 0  # dosyası okunamayan/bozuk kareler
    eski_isabet: float = 0.0  # mevcut sistemin aynı test karelerindeki isabeti
    eski_ad: str = ""  # neyle karşılaştırıldı: devredeki model mi, modelsiz sistem mi
    yeni_isabet: float = 0.0
    kesinlik: float = 0.0  # "forklift" dediklerinin ne kadarı gerçekten forklift
    duyarlilik: float = 0.0  # gerçek forkliftlerin ne kadarını yakaladı
    devreye_alindi: bool = False
    sebep: str = ""  # devreye alma/almama gerekçesi, kullanıcı diliyle
    detay: dict = field(default_factory=dict)


def egit(baglanti, ayarlar: Ayarlar) -> EgitimSonucu:
    """Eğitimi uçtan uca çalıştırır. Hata durumunda istisna değil, kullanıcıya
    gösterilecek Türkçe mesaj taşıyan EgitimSonucu döner."""
    log = log_al("forklift-egitim")

    satirlar = baglanti.execute(
        "SELECT frame_path, bbox, label FROM forklift_samples "
        "WHERE label IN ('yes', 'no') ORDER BY captured_at"
    ).fetchall()
    pozitif = sum(1 for s in satirlar if s["label"] == "yes")
    negatif = len(satirlar) - pozitif
    if pozitif < EN_AZ_POZITIF or negatif < EN_AZ_NEGATIF:
        return EgitimSonucu(
            hata=(
                f"Eğitim için en az {EN_AZ_POZITIF} 'Forklift' ve {EN_AZ_NEGATIF} 'Değil' "
                f"etiketli kare gerekli; şu an {pozitif} 'Forklift', {negatif} 'Değil' var. "
                "Kameralar çalıştıkça biriken kareleri etiketlemeye devam edin."
            ),
            pozitif_sayisi=pozitif,
            negatif_sayisi=negatif,
        )

    x_liste, y_liste, atlanan = _veri_hazirla(satirlar, ayarlar)
    if atlanan:
        log.warning(f"{atlanan} kare okunamadı/bozuk, eğitime alınmadı.")

    test_n = max(EN_AZ_TEST, int(len(y_liste) * TEST_PAYI))
    if len(y_liste) - test_n < EN_AZ_TEST:
        return EgitimSonucu(
            hata=f"Okunabilen kare sayısı çok az ({len(y_liste)}). Daha fazla kare etiketleyin.",
            pozitif_sayisi=pozitif,
            negatif_sayisi=negatif,
            atlanan_sayisi=atlanan,
        )
    x = np.stack(x_liste)
    y = np.array(y_liste, dtype=np.float64)
    x_egitim, y_egitim = x[:-test_n], y[:-test_n]
    x_test, y_test = x[-test_n:], y[-test_n:]
    if len(set(y_test.tolist())) < 2 or len(set(y_egitim.tolist())) < 2:
        return EgitimSonucu(
            hata=(
                "Zamana göre bölünen eğitim/test kümelerinden biri tek sınıftan oluşuyor "
                "(ör. son günlerde yalnızca 'Forklift' etiketlendi). Farklı günlerden hem "
                "'Forklift' hem 'Değil' kareleri etiketleyip yeniden deneyin."
            ),
            pozitif_sayisi=pozitif,
            negatif_sayisi=negatif,
            atlanan_sayisi=atlanan,
        )

    ortalama = x_egitim.mean(axis=0)
    sapma = x_egitim.std(axis=0) + 1e-6
    w, b = _lojistik_egit((x_egitim - ortalama) / sapma, y_egitim)

    p_test = _sigmoid(((x_test - ortalama) / sapma) @ w + b)
    tahmin = (p_test >= KARAR_ESIGI).astype(np.float64)
    yeni_isabet = float((tahmin == y_test).mean())

    # Eski model, AYNI test karelerinde değerlendirilir: devrede eğitilmiş bir
    # sürüm varsa o; yoksa bugünkü davranış (hiçbir araç forklift sayılmaz).
    eski = ForkliftSiniflandirici(ayarlar.forklift_model_klasoru)
    if eski.model_var:
        eski_tahmin = (eski.p_toplu(x_test) >= eski.esik).astype(np.float64)
        eski_ad = f"devredeki model ({eski.surum})"
    else:
        eski_tahmin = np.zeros_like(y_test)
        eski_ad = "mevcut sistem (forklift sınıfı yok)"
    eski_isabet = float((eski_tahmin == y_test).mean())
    dogru_forklift = float(((tahmin == 1.0) & (y_test == 1.0)).sum())
    kesinlik = dogru_forklift / max(1.0, float((tahmin == 1.0).sum()))
    duyarlilik = dogru_forklift / max(1.0, float((y_test == 1.0).sum()))

    sonuc = EgitimSonucu(
        surum=_siradaki_surum(ayarlar),
        egitim_sayisi=len(y_egitim),
        test_sayisi=test_n,
        pozitif_sayisi=pozitif,
        negatif_sayisi=negatif,
        atlanan_sayisi=atlanan,
        eski_isabet=eski_isabet,
        eski_ad=eski_ad,
        yeni_isabet=yeni_isabet,
        kesinlik=kesinlik,
        duyarlilik=duyarlilik,
    )
    sonuc.devreye_alindi = yeni_isabet > eski_isabet
    sonuc.sebep = (
        f"Yeni model aynı {test_n} test karesinde %{yeni_isabet * 100:.1f} isabet aldı; "
        f"{eski_ad} %{eski_isabet * 100:.1f} almıştı. Yeni model "
        + (
            "daha iyi — devreye alındı."
            if sonuc.devreye_alindi
            else "daha iyi değil — devreye ALINMADI."
        )
    )
    _kaydet(ayarlar, sonuc, w, b, ortalama, sapma)
    log.info(f"Forklift eğitimi bitti: {sonuc.surum} — {sonuc.sebep}")
    return sonuc


# ---- iç ----


def _veri_hazirla(satirlar, ayarlar: Ayarlar) -> tuple[list[np.ndarray], list[float], int]:
    import cv2

    x_liste: list[np.ndarray] = []
    y_liste: list[float] = []
    atlanan = 0
    for satir in satirlar:
        kare = cv2.imread(str(ayarlar.goruntu_klasoru / satir["frame_path"]))
        kutu = _piksel_kutu(satir["bbox"], kare)
        if kutu is None:
            atlanan += 1
            continue
        kirpik = arac_kirp(kare, kutu)
        if kirpik is None:
            atlanan += 1
            continue
        x_liste.append(oznitelik(kirpik))
        y_liste.append(1.0 if satir["label"] == "yes" else 0.0)
    return x_liste, y_liste, atlanan


def _piksel_kutu(bbox_json: str, kare) -> tuple[float, float, float, float] | None:
    if kare is None:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in json.loads(bbox_json))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        return None
    yukseklik, genislik = kare.shape[:2]
    return (x1 * genislik, y1 * yukseklik, x2 * genislik, y2 * yukseklik)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))


def _lojistik_egit(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """Tam yığın gradyan inişiyle lojistik regresyon — deterministik, saniyeler."""
    w = np.zeros(x.shape[1])
    b = 0.0
    n = len(y)
    for _ in range(_TUR_SAYISI):
        p = _sigmoid(x @ w + b)
        w -= _OGRENME_ADIMI * (x.T @ (p - y) / n + _L2 * w)
        b -= _OGRENME_ADIMI * float((p - y).mean())
    return w, b


def _siradaki_surum(ayarlar: Ayarlar) -> str:
    mevcutlar = sorted(ayarlar.forklift_model_klasoru.glob("v*.npz"))
    if not mevcutlar:
        return "v001"
    return f"v{int(mevcutlar[-1].stem[1:]) + 1:03d}"


def _kaydet(ayarlar: Ayarlar, sonuc: EgitimSonucu, w, b, ortalama, sapma) -> None:
    """Her eğitim sürümlü kaydedilir; yalnızca daha iyi olan devreye alınır."""
    klasor = ayarlar.forklift_model_klasoru
    klasor.mkdir(parents=True, exist_ok=True)
    np.savez(klasor / f"{sonuc.surum}.npz", w=w, b=b, ortalama=ortalama, sapma=sapma)
    kayit = {
        "surum": sonuc.surum,
        "egitim_zamani": zaman.simdi_utc(),
        "egitim_sayisi": sonuc.egitim_sayisi,
        "test_sayisi": sonuc.test_sayisi,
        "eski_isabet": round(sonuc.eski_isabet, 4),
        "yeni_isabet": round(sonuc.yeni_isabet, 4),
        "kesinlik": round(sonuc.kesinlik, 4),
        "duyarlilik": round(sonuc.duyarlilik, 4),
        "devreye_alindi": sonuc.devreye_alindi,
    }
    (klasor / f"{sonuc.surum}.json").write_text(
        json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if sonuc.devreye_alindi:
        aktif = dict(kayit, esik=KARAR_ESIGI)
        (klasor / "aktif.json").write_text(
            json.dumps(aktif, ensure_ascii=False, indent=2), encoding="utf-8"
        )

"""KKD veri seti: güne göre bölme ve dışa aktarım (docs/17 §5.8, docs/04 §5.4).

RASTGELE BÖLME YASAK. Aynı kişinin aynı saniyedeki beş karesi hem eğitime hem
teste düşerse model ezberler: test %98 çıkar, saha %70 (docs/04 §5.4). Bölmenin
birimi Türkiye yerel GÜNÜDÜR: bir günün bütün kameraları aynı kümeye düşer.
Böylece kamera × gün grubu hiçbir zaman iki kümede olmaz; aynı anı iki ayrı
kameradan gören kareler de ayrılmaz. Günler kronolojik ayrılır (docs/04 §5.4
örneği: 1.–5. gün eğitim, 6. doğrulama, 7.–8. test): model hep eğitimde
görmediği SONRAKİ günlerde sınanır.

Eğitim ürün dışıdır (docs/04 §6, S31): burada yalnız dışa aktarım var. Zip
stdlib `zipfile` ile yazılır:

- `goruntuler/<küme>/<örnek no>.jpg` — kırpıklar;
- `etiketler.csv` — virgüllü, UTF-8; eğitim betiği okur, kişi adı ya da kamera
  adı taşımaz;
- `bolme.json` — hangi gün ve kamera × gün grubu hangi kümede;
- `manifest.json` — sayılar, uyarılar ve her dosyanın sha256'sı.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app import zaman

# Zor örnek kodları (docs/17 §5.8, docs/kkd-politika.md §4). Tek kaynak burası;
# şemada CHECK yok (S22). Etiketçi KKD sayfasında işaretler.
ZOR_ORNEKLER = {
    "white_cap": "Beyaz kep, bone ya da saç",
    "reflective_jacket": "Reflektörlü mont",
    "night_glare": "Gece yansıması, parlama",
    "backpack": "Sırt çantası",
    "raincoat": "Yağmurluk",
    "driver_cab": "Kabindeki sürücü",
}

KUMELER = ("train", "val", "test")
# docs/04 §5.4 örneğinin oranları (8 günde 5 / 1 / 2): doğrulama %12,5, test %25.
# En az üç gün varsa her kümeye en az bir gün düşer.
_VAL_PAYI = 0.125
_TEST_PAYI = 0.25
BOLME_YONTEMI = (
    "Türkiye yerel gününe göre kronolojik: ilk günler train, sonraki val, son günler test "
    "(docs/04 §5.4; val %12,5, test %25, en az birer gün). Bir günün bütün kameraları "
    "aynı kümededir; rastgele bölme yoktur."
)
MANIFEST_SURUMU = 1

_CSV_SUTUNLARI = (
    "dosya",
    "kume",
    "ornek_id",
    "kamera_id",
    "gun",
    "alinma_utc",
    "baret",
    "yelek",
    "zor_ornek",
    "kaynak",
    "kisi_boyu_px",
    "netlik",
)


@dataclass(frozen=True)
class Ornek:
    id: int
    kamera_id: int | None
    alinma_utc: str
    gun: str  # Türkiye yerel günü, 'YYYY-AA-GG'
    dosya: str  # görüntü klasörüne göre kırpık yolu
    baret: str
    yelek: str
    zor: str | None
    kaynak: str
    boy_px: int | None
    netlik: float | None


def etiketli_ornekler(baglanti) -> list[Ornek]:
    """İki etiketi de verilmiş örnekler, alınma sırasıyla. Etiketsiz örnek
    eğitimde kullanılamaz; dışa aktarılmaz."""
    return [
        Ornek(
            id=satir["id"],
            kamera_id=satir["camera_id"],
            alinma_utc=satir["captured_at"],
            gun=zaman.yerel_tarih_iso(satir["captured_at"]),
            dosya=satir["crop_path"],
            baret=satir["helmet_label"],
            yelek=satir["vest_label"],
            zor=satir["hard_case"],
            kaynak=satir["source"],
            boy_px=satir["person_height_px"],
            netlik=satir["sharpness"],
        )
        for satir in baglanti.execute(
            "SELECT id, camera_id, captured_at, crop_path, helmet_label, vest_label, "
            "hard_case, source, person_height_px, sharpness FROM ppe_samples "
            "WHERE labeled_at IS NOT NULL AND helmet_label IS NOT NULL "
            "AND vest_label IS NOT NULL ORDER BY captured_at, id"
        )
    ]


def gun_bolmesi(gunler: Iterable[str]) -> dict[str, str]:
    """Her güne bir küme: {'2026-09-01': 'train', ...}. Kronolojik; en az üç
    gün varsa her kümeye en az bir gün. Üçten az günde doğrulama (ve bir günde
    test) boş kalır; bunu `uyarilar` söyler."""
    sirali = sorted(set(gunler))
    adet = len(sirali)
    if adet >= 3:
        val = max(1, round(adet * _VAL_PAYI))
        test = max(1, round(adet * _TEST_PAYI))
    else:
        # 2 gün: biri eğitim biri test; 1 gün: yalnız eğitim; hiç gün yoksa boş
        val, test = 0, max(0, adet - 1)
    egitim = adet - val - test
    kumeler = ["train"] * egitim + ["val"] * val + ["test"] * test
    return dict(zip(sirali, kumeler, strict=True))


def uyarilar(bolme: dict[str, str]) -> list[str]:
    """Bölmenin eksikleri, Türkçe; boşsa sorun yok."""
    sayilar = Counter(bolme.values())
    eksik = [kume for kume in KUMELER if not sayilar[kume]]
    if not eksik:
        return []
    return [
        f"{len(bolme)} günlük veri var; {', '.join(eksik)} kümesi boş. Doğrulama ve test için "
        "en az üç ayrı günün etiketli örneği gerekir (docs/04 §5.4)."
    ]


def ozet(ornekler: list[Ornek]) -> dict:
    """KKD sayfası için: küme başına örnek ve gün sayısı + uyarılar."""
    bolme = gun_bolmesi(o.gun for o in ornekler)
    kumeler = {kume: {"ornek": 0, "gun": 0} for kume in KUMELER}
    for kume in bolme.values():
        kumeler[kume]["gun"] += 1
    for ornek in ornekler:
        kumeler[bolme[ornek.gun]]["ornek"] += 1
    return {
        "ornek": len(ornekler),
        "kamera": len({o.kamera_id for o in ornekler}),
        "gun": len(bolme),
        "kumeler": kumeler,
        "uyarilar": uyarilar(bolme),
    }


def _sha256(veri: bytes) -> str:
    return hashlib.sha256(veri).hexdigest()


def disa_aktar(ornekler: list[Ornek], goruntu_klasoru: Path, hedef) -> dict:
    """Zip'i `hedef`e (dosya yolu ya da ikili dosya nesnesi) yazar; manifest'i döndürür.

    Diskte bulunmayan kırpık atlanır ve sayısı manifest'e yazılır: veritabanında
    var görünüp dosyası silinmiş bir örnek dışa aktarımı durdurmamalı. Kırpık
    yolu görüntü klasörünün dışına çıkamaz.
    """
    bolme = gun_bolmesi(o.gun for o in ornekler)
    kok = Path(goruntu_klasoru).resolve()
    ozetler: dict[str, str] = {}
    satirlar = []
    eksik = 0
    kume_sayaci: dict[str, Counter] = {kume: Counter() for kume in KUMELER}
    gruplar: dict[str, set] = {kume: set() for kume in KUMELER}
    # JPEG zaten sıkıştırılmış: yeniden sıkıştırmak yalnız zaman harcar
    with zipfile.ZipFile(hedef, "w", compression=zipfile.ZIP_STORED) as arsiv:
        for ornek in ornekler:
            kaynak = (kok / ornek.dosya).resolve()
            if not kaynak.is_relative_to(kok) or not kaynak.is_file():
                eksik += 1
                continue
            kume = bolme[ornek.gun]
            ad = f"goruntuler/{kume}/{ornek.id:07d}.jpg"
            veri = kaynak.read_bytes()
            arsiv.writestr(ad, veri)
            ozetler[ad] = _sha256(veri)
            gruplar[kume].add((ornek.kamera_id, ornek.gun))
            sayac = kume_sayaci[kume]
            sayac["ornek"] += 1
            sayac[f"baret_{ornek.baret}"] += 1
            sayac[f"yelek_{ornek.yelek}"] += 1
            sayac["zor"] += 1 if ornek.zor else 0
            satirlar.append(
                (
                    ad,
                    kume,
                    ornek.id,
                    "" if ornek.kamera_id is None else ornek.kamera_id,
                    ornek.gun,
                    ornek.alinma_utc,
                    ornek.baret,
                    ornek.yelek,
                    ornek.zor or "",
                    ornek.kaynak,
                    "" if ornek.boy_px is None else ornek.boy_px,
                    "" if ornek.netlik is None else ornek.netlik,
                )
            )

        tampon = io.StringIO()
        yazici = csv.writer(tampon, lineterminator="\n")
        yazici.writerow(_CSV_SUTUNLARI)
        yazici.writerows(satirlar)
        etiketler = tampon.getvalue().encode("utf-8")
        arsiv.writestr("etiketler.csv", etiketler)
        ozetler["etiketler.csv"] = _sha256(etiketler)

        bolme_metni = json.dumps(
            {
                "yontem": BOLME_YONTEMI,
                "gunler": {
                    kume: sorted(gun for gun, k in bolme.items() if k == kume) for kume in KUMELER
                },
                # Kamerası silinmiş örneğin kamera_id'si null'dır
                "kamera_gun_gruplari": {
                    kume: [
                        [kamera, gun]
                        for kamera, gun in sorted(gruplar[kume], key=lambda g: (g[1], g[0] or 0))
                    ]
                    for kume in KUMELER
                },
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        arsiv.writestr("bolme.json", bolme_metni)
        ozetler["bolme.json"] = _sha256(bolme_metni)

        manifest = {
            "surum": MANIFEST_SURUMU,
            "olusturma_utc": zaman.simdi_utc(),
            "ornek_sayisi": len(satirlar),
            "eksik_dosya": eksik,
            "kumeler": {kume: dict(kume_sayaci[kume]) for kume in KUMELER},
            "uyarilar": uyarilar(bolme)
            + ([f"{eksik} örneğin görüntü dosyası diskte yok; atlandı."] if eksik else []),
            # manifest.json kendisi listede değildir
            "dosyalar": ozetler,
        }
        arsiv.writestr(
            "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        )
    return manifest

"""Forklift eğitimi için sahadan toplanan kareler (operatör isteği 24.09.2026).

Operatör: "gidip fabrikadan daha çok görüntü çekip mi yükleyeyim ve sadece
yüklesem yeter mi ekstra kod vs. bir şey yapmam lazım mı". Açık veriyle (LOCO)
iki tam eğitim kapılardan geçemedi: model başka depolardaki forkliftlere
genelleyemiyor (docs/ILERLEME). Çare hedef ortamın kendisidir; bu modül o
veriyi toplar ve eğitime hazırlar:

1. **Toplama.** Kapı (forklift_collection_gate, şema 012) açıkken analiz,
   araç (tır) ya da forklift görünen kareyi kamera başına saatte en çok
   FORKLIFT_ORNEK_SAAT_LIMIT kez saklar; araçsız kareyi bunun altıda biri
   kadar (modelin boş sahnede forklift görmemesi de öğrenilmeli ve ölçülmeli).
   O karedeki araç kutuları etiketçiye öneri olur. Kare, uzun kenarı 1280
   pikseli geçmeyecek şekilde küçültülür (LOCO hazırlığıyla aynı sınır).
2. **Etiketleme.** Forklift sayfasında her kutu için "Forklift / Transpalet /
   Değil" seçilir, eksik kutu çizilir (web/forklift_web.py).
3. **Dışa aktarma.** Etiketli kareler Türkiye yerel gününe göre kronolojik
   bölünür (rastgele bölme yok; aynı anın kareleri iki kümeye düşmez) ve
   egitim/forklift'in beklediği COCO düzeninde zip olur.

Kareler yalnız bu bilgisayarda durur. Eğitim ürün dışındadır ve kapalı bir
bilgisayarda yapılır (CLAUDE.md, forklift eğitimi istisnası): müşteri
kamerasından tek kare bile herkese açık GitHub hattına girmez.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app import zaman
from app.rules.tipler import SINIF_INSAN

# Dışa aktarılan sınıflar ve COCO kimlikleri: egitim/forklift/ortak.py
# EK_SINIFLAR sırasıyla aynıdır (test denetler).
SINIFLAR = ("forklift", "pallet_jack")
SINIF_ADLARI = {"forklift": "Forklift", "pallet_jack": "Transpalet"}

# Kare, uzun kenarı bu kadar pikseli geçmeyecek şekilde küçültülür
# (egitim/forklift/veri.py --en-uzun-kenar varsayılanıyla aynı).
EN_UZUN_KENAR = 1280
JPEG_KALITESI = 90
# Araçsız kare, araçlı kareden bu kadar kat seyrek saklanır.
ARACSIZ_SEYREKLIK = 6
# Bir karede en çok kaç kutu etiketlenebilir (bozuk istek sınırı).
EN_COK_KUTU = 100
# Bundan küçük kutu (piksel, kısa kenar) etiket sayılmaz: yanlışlıkla tıklama.
EN_KUCUK_KUTU_PX = 4
KLASOR = "forklift-ornekler"
# Test kümesinin payı: kronolojik son günler (en az bir gün).
_TEST_PAYI = 0.25
# Test günlerindeki forklift kutusu bundan azsa uyarılır: oran birkaç kutuyla
# ölçülür, kapının hangi yanında olduğu güvenle söylenemez
# (egitim/forklift/veri.py AZ_TEST_KUTUSU ile aynı; test denetler).
AZ_TEST_KUTUSU = 50
MANIFEST_SURUMU = 1
TOPLAMA_ONAY_METNI = (
    "Çalışanlara aydınlatma yapıldı ve bu kareleri forklift modeli eğitimi için saklamanın "
    "hukuki dayanağı (Rev.02 ya da ek protokol) var"
)


# --------------------------------------------------------------- toplama


def oneriler(tespitler) -> list[dict]:
    """Kişi dışındaki tespitler (tır ya da forklift): etiketçiye kutu önerisi."""
    return [
        {
            "kutu": [round(float(deger), 1) for deger in tespit.kutu],
            "sinif": tespit.sinif,
            "puan": round(float(tespit.guven), 3),
        }
        for tespit in tespitler
        if tespit.sinif != SINIF_INSAN
    ]


def toplama_acik_mi(baglanti) -> bool:
    """Toplama kapısı. Okunamazsa KAPALI sayılır: şüphede kişisel veri toplanmaz."""
    try:
        satir = baglanti.execute(
            "SELECT enabled FROM forklift_collection_gate WHERE id = 1"
        ).fetchone()
    except sqlite3.Error:
        return False
    return bool(satir and satir["enabled"])


def toplama_durumu(baglanti) -> dict:
    satir = baglanti.execute(
        "SELECT enabled, changed_at, note FROM forklift_collection_gate WHERE id = 1"
    ).fetchone()
    if satir is None:
        return {"acik": False, "degisti": "", "not": ""}
    return {
        "acik": bool(satir["enabled"]),
        "degisti": zaman.ekranda_goster(satir["changed_at"]) if satir["changed_at"] else "",
        "not": satir["note"] or "",
    }


def ornek_sayisi(baglanti) -> int:
    return baglanti.execute("SELECT COUNT(*) FROM forklift_samples").fetchone()[0]


def _olcek(genislik: int, yukseklik: int, en_uzun: int = EN_UZUN_KENAR) -> float:
    """Küçültme oranı; asla büyütülmez."""
    return min(1.0, en_uzun / max(genislik, yukseklik, 1))


def kareyi_kaydet(
    baglanti, goruntu_klasoru: Path, kamera_id: int | None, kare, kutu_onerileri: list[dict]
) -> str | None:
    """Kareyi (küçültülmüş) diske, satırını veritabanına yazar.

    Döner: görüntü klasörüne göre yol; yazılamazsa None ve hata yükseltilmez
    (analiz, eğitim verisi yüzünden durmamalı - çağıran günlüğe yazar).
    """
    import cv2

    yukseklik, genislik = int(kare.shape[0]), int(kare.shape[1])
    oran = _olcek(genislik, yukseklik)
    if oran < 1.0:
        genislik_y, yukseklik_y = round(genislik * oran), round(yukseklik * oran)
        kare = cv2.resize(kare, (genislik_y, yukseklik_y), interpolation=cv2.INTER_AREA)
        genislik, yukseklik = genislik_y, yukseklik_y
    olcekli = [
        {**oneri, "kutu": [round(deger * oran, 1) for deger in oneri["kutu"]]}
        for oneri in kutu_onerileri
    ]
    simdi_utc = zaman.simdi_utc()
    # Aynı kameradan aynı saniyede iki kare gelebilir (araçlı ve araçsız
    # sayaçlar ayrıdır): kısa rastgele ek, dosyanın üstüne yazılmasını önler.
    goreli = str(
        Path(KLASOR)
        / simdi_utc[:7]
        / f"{simdi_utc.replace(':', '-').replace('+', 'Z')}-k{kamera_id}-{secrets.token_hex(3)}.jpg"
    )
    tam_yol = goruntu_klasoru / goreli
    tam_yol.parent.mkdir(parents=True, exist_ok=True)
    # cv2.imwrite yerine imencode + write_bytes: imwrite Türkçe karakterli
    # Windows yolunda hata vermeden False döner (bkz. KKD örnekleri).
    tamam, tampon = cv2.imencode(".jpg", kare, [cv2.IMWRITE_JPEG_QUALITY, JPEG_KALITESI])
    if not tamam:
        return None
    tam_yol.write_bytes(tampon.tobytes())
    kamera_var = (
        kamera_id is not None
        and baglanti.execute("SELECT 1 FROM cameras WHERE id = ?", (kamera_id,)).fetchone()
    )
    baglanti.execute(
        "INSERT INTO forklift_samples (camera_id, captured_at, frame_path, width, height, "
        "proposals) VALUES (?, ?, ?, ?, ?, ?)",
        (
            kamera_id if kamera_var else None,
            simdi_utc,
            goreli,
            genislik,
            yukseklik,
            json.dumps(olcekli, ensure_ascii=False),
        ),
    )
    baglanti.commit()
    return goreli


# --------------------------------------------------------------- etiket


class EtiketHatasi(ValueError):
    """Etiketleme sayfasından gelen kutu listesi geçersiz."""


def etiketleri_dogrula(ham, genislik: int, yukseklik: int) -> list[dict]:
    """Etiket listesini denetler, kutuları görüntünün içine kırpar.

    Beklenen: [{"kutu": [x1, y1, x2, y2], "sinif": "forklift" | "pallet_jack"}].
    Boş liste geçerlidir: "karede forklift yok".
    """
    if not isinstance(ham, list):
        raise EtiketHatasi("Etiket listesi bekleniyordu.")
    if len(ham) > EN_COK_KUTU:
        raise EtiketHatasi(f"Bir karede en çok {EN_COK_KUTU} kutu etiketlenebilir.")
    temiz: list[dict] = []
    for oge in ham:
        if not isinstance(oge, dict) or oge.get("sinif") not in SINIFLAR:
            raise EtiketHatasi("Kutunun sınıfı forklift ya da transpalet olmalı.")
        kutu = oge.get("kutu")
        if not isinstance(kutu, list) or len(kutu) != 4:
            raise EtiketHatasi("Kutu dört sayıdan oluşmalı.")
        try:
            x1, y1, x2, y2 = (float(deger) for deger in kutu)
        except (TypeError, ValueError) as hata:
            raise EtiketHatasi("Kutu dört sayıdan oluşmalı.") from hata
        x1, x2 = sorted((min(max(x1, 0.0), genislik), min(max(x2, 0.0), genislik)))
        y1, y2 = sorted((min(max(y1, 0.0), yukseklik), min(max(y2, 0.0), yukseklik)))
        if min(x2 - x1, y2 - y1) < EN_KUCUK_KUTU_PX:
            continue
        temiz.append(
            {
                "kutu": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                "sinif": oge["sinif"],
            }
        )
    return temiz


def etiketle(baglanti, ornek_id: int, ham) -> list[dict]:
    satir = baglanti.execute(
        "SELECT width, height FROM forklift_samples WHERE id = ?", (ornek_id,)
    ).fetchone()
    if satir is None:
        raise EtiketHatasi("Kare bulunamadı; silinmiş olabilir.")
    etiketler = etiketleri_dogrula(ham, satir["width"], satir["height"])
    baglanti.execute(
        "UPDATE forklift_samples SET labels = ?, labeled_at = ? WHERE id = ?",
        (json.dumps(etiketler, ensure_ascii=False), zaman.simdi_utc(), ornek_id),
    )
    baglanti.commit()
    return etiketler


def sonraki_etiketsiz(baglanti, sonra: int | None = None) -> int | None:
    """Sıradaki etiketlenmemiş kare (en eskisi önce). `sonra` verilirse ondan
    sonraki; "Atla" düğmesi için."""
    if sonra is None:
        satir = baglanti.execute(
            "SELECT id FROM forklift_samples WHERE labeled_at IS NULL ORDER BY captured_at, id "
            "LIMIT 1"
        ).fetchone()
    else:
        satir = baglanti.execute(
            "SELECT id FROM forklift_samples WHERE labeled_at IS NULL AND id > ? ORDER BY id "
            "LIMIT 1",
            (sonra,),
        ).fetchone()
    return satir["id"] if satir else None


def ornek_sil(baglanti, goruntu_klasoru: Path, ornek_id: int) -> bool:
    satir = baglanti.execute(
        "SELECT frame_path FROM forklift_samples WHERE id = ?", (ornek_id,)
    ).fetchone()
    if satir is None:
        return False
    (goruntu_klasoru / satir["frame_path"]).unlink(missing_ok=True)
    baglanti.execute("DELETE FROM forklift_samples WHERE id = ?", (ornek_id,))
    baglanti.commit()
    return True


def hepsini_sil(baglanti, goruntu_klasoru: Path) -> int:
    yollar = [s["frame_path"] for s in baglanti.execute("SELECT frame_path FROM forklift_samples")]
    for yol in yollar:
        try:
            (goruntu_klasoru / yol).unlink(missing_ok=True)
        except OSError:
            # Windows'ta kilitli dosya (Defender, yedekleme): satırı yine sil,
            # dosyayı bakımın görüntü temizliği sonra alır.
            continue
    baglanti.execute("DELETE FROM forklift_samples")
    baglanti.commit()
    return len(yollar)


def hamlari_sil(baglanti, goruntu_klasoru: Path, gun: int) -> int:
    """Etiketlenmemiş kareler süre dolunca silinir; etiketliler veri setidir."""
    sinir = zaman.gun_once_utc(gun)
    satirlar = baglanti.execute(
        "SELECT id, frame_path FROM forklift_samples WHERE labeled_at IS NULL AND captured_at < ?",
        (sinir,),
    ).fetchall()
    for satir in satirlar:
        try:
            (goruntu_klasoru / satir["frame_path"]).unlink(missing_ok=True)
        except OSError:
            continue
    baglanti.execute(
        "DELETE FROM forklift_samples WHERE labeled_at IS NULL AND captured_at < ?", (sinir,)
    )
    baglanti.commit()
    return len(satirlar)


# --------------------------------------------------------------- özet


def ozet(baglanti) -> dict:
    """Forklift sayfasının sayıları."""
    toplam = etiketli = forkliftsiz = 0
    kutular = dict.fromkeys(SINIFLAR, 0)
    gunler: set[str] = set()
    for satir in baglanti.execute("SELECT labels, labeled_at, captured_at FROM forklift_samples"):
        toplam += 1
        if satir["labeled_at"] is None:
            continue
        etiketli += 1
        gunler.add(zaman.yerel_tarih_iso(satir["captured_at"]))
        etiketler = json.loads(satir["labels"] or "[]")
        if not any(e["sinif"] == "forklift" for e in etiketler):
            forkliftsiz += 1
        for etiket in etiketler:
            kutular[etiket["sinif"]] = kutular.get(etiket["sinif"], 0) + 1
    return {
        "toplam": toplam,
        "etiketli": etiketli,
        "bekleyen": toplam - etiketli,
        "forklift_kutusu": kutular["forklift"],
        "transpalet_kutusu": kutular["pallet_jack"],
        "forkliftsiz_kare": forkliftsiz,
        "gun": len(gunler),
    }


# --------------------------------------------------------------- dışa aktarım


@dataclass(frozen=True)
class Kare:
    id: int
    kamera_id: int | None
    alinma_utc: str
    gun: str  # Türkiye yerel günü
    dosya: str  # görüntü klasörüne göre
    genislik: int
    yukseklik: int
    etiketler: tuple[dict, ...]

    @property
    def cikti_adi(self) -> str:
        # LOCO kareleriyle aynı klasöre karışabilir: "saha-" öneki çakışmayı önler.
        return f"saha-{self.id:06d}.jpg"


def etiketli_kareler(baglanti) -> list[Kare]:
    return [
        Kare(
            id=satir["id"],
            kamera_id=satir["camera_id"],
            alinma_utc=satir["captured_at"],
            gun=zaman.yerel_tarih_iso(satir["captured_at"]),
            dosya=satir["frame_path"],
            genislik=satir["width"],
            yukseklik=satir["height"],
            etiketler=tuple(json.loads(satir["labels"] or "[]")),
        )
        for satir in baglanti.execute(
            "SELECT id, camera_id, captured_at, frame_path, width, height, labels "
            "FROM forklift_samples WHERE labeled_at IS NOT NULL ORDER BY captured_at, id"
        )
    ]


def gun_bolmesi(gunler) -> dict[str, str]:
    """Her güne bir küme ("egitim" | "test"), kronolojik: son günler test.

    İki ve daha çok günde teste en az bir gün düşer; tek günde test boştur ve
    `uyarilar` bunu söyler.
    """
    sirali = sorted(set(gunler))
    adet = len(sirali)
    test = max(1, round(adet * _TEST_PAYI)) if adet >= 2 else 0
    return dict(zip(sirali, ["egitim"] * (adet - test) + ["test"] * test, strict=True))


def uyarilar(kareler: list[Kare], bolme: dict[str, str]) -> list[str]:
    notlar = []
    if "test" not in bolme.values():
        notlar.append(
            "Test kümesi boş: etiketli kareler tek günden. Model, eğitimde görmediği günlerde "
            "sınanabilsin diye en az iki ayrı günün karesini etiketleyin."
        )
    forklift_var = any(any(e["sinif"] == "forklift" for e in k.etiketler) for k in kareler)
    if not forklift_var:
        notlar.append("Hiçbir karede forklift kutusu yok; bu veriyle forklift öğrenilemez.")
    test_kareleri = [k for k in kareler if bolme.get(k.gun) == "test"]
    test_kutusu = sum(e["sinif"] == "forklift" for k in test_kareleri for e in k.etiketler)
    if forklift_var and test_kareleri and test_kutusu < AZ_TEST_KUTUSU:
        notlar.append(
            f"Test günlerinde yalnız {test_kutusu} forklift kutusu var (en az "
            f"{AZ_TEST_KUTUSU} önerilir): forklift bulma oranı bu kadar az kutuyla güvenle "
            "ölçülemez. Daha çok günün karesini etiketleyin."
        )
    if test_kareleri and all(k.etiketler for k in test_kareleri):
        # degerlendir.py fk_fp_goruntu_basi: paydası kutusuz karedir; sıfırsa
        # ölçülmez ve ölçülmeyen metrik kapıyı kaldırır.
        notlar.append(
            "Test günlerinde forkliftsiz (boş) kare yok: yanlış forklift alarmı ölçülemez ve "
            "o kapı kalır. Test günlerinin forklift görünmeyen karelerini de “Forklift yok” "
            "diye etiketleyin."
        )
    return notlar


def _coco(kareler: list[Kare]) -> dict:
    kimlik = {ad: no for no, ad in enumerate(SINIFLAR, 1)}
    goruntuler, etiketler = [], []
    for sira, kare in enumerate(kareler, 1):
        goruntuler.append(
            {
                "id": sira,
                "file_name": kare.cikti_adi,
                "width": kare.genislik,
                "height": kare.yukseklik,
                "gun": kare.gun,
                "kamera_id": kare.kamera_id,
            }
        )
        for etiket in kare.etiketler:
            x1, y1, x2, y2 = etiket["kutu"]
            genislik, yukseklik = round(x2 - x1, 1), round(y2 - y1, 1)
            etiketler.append(
                {
                    "id": len(etiketler) + 1,
                    "image_id": sira,
                    "category_id": kimlik[etiket["sinif"]],
                    "bbox": [x1, y1, genislik, yukseklik],
                    "area": round(genislik * yukseklik, 2),
                    "iscrowd": 0,
                }
            )
    return {
        "images": goruntuler,
        "annotations": etiketler,
        "categories": [{"id": no, "name": ad} for ad, no in kimlik.items()],
    }


BENIOKU = """NextGen Detector - forklift eğitim verisi (fabrikanın kendi kameraları)

Bu klasördeki görüntüler çalışanları da gösterebilir: kişisel veridir (KVKK).
İnternete, herkese açık bir depoya ya da paylaşılan bir klasöre KOYMAYIN.
Eğitim kapalı bir bilgisayarda yapılır: programın kaynak klasöründeki
egitim\\forklift\\Egit-Windows.bat dosyasının üstüne bu zip'i sürükleyip bırakın
(ayrıntı: egitim/forklift/YEREL-EGITIM.md). Çıkan model Forklift sayfasından kurulur.

Düzen (egitim/forklift/veri.py'nin LOCO çıktısıyla aynı):
  egitim/*.jpg, test/*.jpg        görüntüler
  annotations/egitim.json         COCO, kategoriler: 1 forklift, 2 pallet_jack
  annotations/test.json           COCO; test günleri eğitimde yoktur
  manifest.json                   sayılar, gün bölmesi, her dosyanın sha256'sı
"""


def disa_aktar(kareler: list[Kare], goruntu_klasoru: Path, zip_yolu: Path) -> dict:
    """Etiketli kareleri eğitim düzeninde zip'e yazar; manifest'i döndürür."""
    bolme = gun_bolmesi(k.gun for k in kareler)
    kumeler: dict[str, list[Kare]] = {"egitim": [], "test": []}
    eksik = 0
    ozetler: dict[str, str] = {}
    with zipfile.ZipFile(zip_yolu, "w", compression=zipfile.ZIP_STORED) as arsiv:
        for kare in kareler:
            kaynak = goruntu_klasoru / kare.dosya
            try:
                veri = kaynak.read_bytes()
            except OSError:
                eksik += 1
                continue
            kume = bolme[kare.gun]
            ad = f"{kume}/{kare.cikti_adi}"
            arsiv.writestr(ad, veri)
            ozetler[ad] = hashlib.sha256(veri).hexdigest()
            kumeler[kume].append(kare)
        for kume, uyeler in kumeler.items():
            veri = json.dumps(_coco(uyeler), ensure_ascii=False, indent=1).encode("utf-8")
            ad = f"annotations/{kume}.json"
            arsiv.writestr(ad, veri)
            ozetler[ad] = hashlib.sha256(veri).hexdigest()
        manifest = {
            "surum": MANIFEST_SURUMU,
            "olusturma_utc": zaman.simdi_utc(),
            "kare_sayisi": sum(len(uyeler) for uyeler in kumeler.values()),
            "eksik_dosya": eksik,
            "kumeler": {
                kume: {
                    "kare": len(uyeler),
                    "forklift_kutusu": sum(
                        1 for k in uyeler for e in k.etiketler if e["sinif"] == "forklift"
                    ),
                    "transpalet_kutusu": sum(
                        1 for k in uyeler for e in k.etiketler if e["sinif"] == "pallet_jack"
                    ),
                }
                for kume, uyeler in kumeler.items()
            },
            "gun_bolmesi": bolme,
            "bolme_yontemi": (
                "Türkiye yerel gününe göre kronolojik: son günler test (%25, en az bir gün). "
                "Rastgele bölme yoktur."
            ),
            "uyarilar": uyarilar(kareler, bolme),
            "sha256": ozetler,
        }
        arsiv.writestr(
            "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
        )
        arsiv.writestr("BENIOKU.txt", BENIOKU.encode("utf-8"))
    return manifest

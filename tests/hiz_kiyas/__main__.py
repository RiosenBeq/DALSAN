"""Tespit hızını ölçer ve ÖZET TABLOLARI basar.

Çalıştırma (depo kökünden):

    .venv/bin/python -m tests.hiz_kiyas
    .venv/bin/python -m tests.hiz_kiyas --tek --tur 50
    .venv/bin/python -m tests.hiz_kiyas --dort --sure 20
    .venv/bin/python -m tests.hiz_kiyas --kkd

Motoru DEĞİŞTİRMEZ; yalnız ölçer. Gerçek `app.analiz.tespit.Tespitci`
sınıfını kendi genel API'siyle çağırır, yani ölçülen şey sahada çalışan
yolun ta kendisidir: ön işleme + çıkarım + son işleme.

İKİ ÖLÇÜM:
  1. Tek akış - bir karenin uçtan uca süresi (ortanca, p90).
  2. Dört kamera - dört iş parçacığı TEK paylaşılan Tespitci'yi kilitle
     sırayla kullanır (sahadaki desen). docs/05 §3 bütçesi 4 × 6 fps'tir;
     ölçüm bu bütçenin yüzde kaçının karşılandığını söyler.
  3. KKD sınıflandırıcısı (docs/17 §5.2) - karedeki kişilerin tek toplu
     çağrısı. Yalnız models/kkd.onnx varsa (ve özeti tutuyorsa) koşar; bütçe
     aşılırsa önce KKD kadansı büyütülür, sonra GPU gerekir.

DİKKAT: sonuçlar çalıştığı makineye aittir. Fabrika sunucusunda (GPU'lu)
ölçüm ayrıca yapılmalıdır; geliştirme makinesinin sayısı oraya taşınmaz.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

# Depo kökündeki `backend/` klasörü uygulamanın paket köküdür; buradan
# çalıştırıldığında sys.path'e o eklenmelidir (pytest bunu pyproject.toml
# üzerinden kendisi yapar).
_KOK = Path(__file__).resolve().parents[2]
if str(_KOK / "backend") not in sys.path:
    sys.path.insert(0, str(_KOK / "backend"))

import numpy as np  # noqa: E402

from app.analiz.tespit import ModelHatasi, Tespitci  # noqa: E402

# Gerçek kameraların en yaygın çözünürlüğü; ön işlemenin küçültme maliyeti
# buna bağlıdır, o yüzden sabit 640x480 ile ölçmek yanıltıcı olurdu.
_COZUNURLUK = (1920, 1080)
_HEDEF_FPS = 6.0  # docs/05 §3 - kamera başına örnekleme hızı
_KAMERA = 4  # docs/00 - MVP kamera sayısı


def _sahte_kare(tohum: int = 7) -> np.ndarray:
    """Gürültülü kare. Sabit renkli bir kare son işlemede hiç aday
    üretmezdi ve ölçüm gerçekte olduğundan hızlı görünürdü."""
    rng = np.random.default_rng(tohum)
    return rng.integers(0, 256, size=(_COZUNURLUK[1], _COZUNURLUK[0], 3), dtype=np.uint8)


def _tespitci(model: Path, is_parcacigi: int) -> Tespitci:
    return Tespitci(
        model_dosyasi=model,
        cihaz="cpu",
        guven_esigi=0.35,
        insan_guven_esigi=0.28,
        nms_esigi=0.45,
        en_kucuk_kenar_px=12,
        is_parcacigi=is_parcacigi,
    )


def tek_akis(model: Path, is_parcacigi: int, tur: int, isinma: int = 3) -> dict:
    """Bir karenin uçtan uca süresi."""
    basla = time.perf_counter()
    t = _tespitci(model, is_parcacigi)
    yukleme_ms = (time.perf_counter() - basla) * 1000

    kare = _sahte_kare()
    for _ in range(isinma):
        t.tespit_et(kare)

    sureler = []
    for _ in range(tur):
        b = time.perf_counter()
        t.tespit_et(kare)
        sureler.append((time.perf_counter() - b) * 1000)
    sureler.sort()

    return {
        "model": model.name,
        "girdi_px": t._girdi_boyu,
        "cihaz": t.etkin_cihaz,
        "is_parcacigi": is_parcacigi or "otomatik",
        "yukleme_ms": round(yukleme_ms, 1),
        "ortanca_ms": round(statistics.median(sureler), 1),
        "p90_ms": round(sureler[int(len(sureler) * 0.9)], 1),
        "en_yavas_ms": round(sureler[-1], 1),
        "tek_akis_fps": round(1000 / statistics.median(sureler), 2),
    }


def dort_kamera(model: Path, is_parcacigi: int, sure_sn: float) -> dict:
    """Dört kamera, tek paylaşılan Tespitci, kilitle sıralı çıkarım."""
    t = _tespitci(model, is_parcacigi)
    kareler = [_sahte_kare(tohum=i) for i in range(_KAMERA)]
    t.tespit_et(kareler[0])  # ısınma

    sayac = [0] * _KAMERA
    gecikmeler: list[float] = []
    kilit = threading.Lock()
    dur = threading.Event()

    def kamera_isi(i: int) -> None:
        """Gerçek kamera gibi: hedef hızda kare üretir, GECİKENİ ATLAR
        (boru hattının geri basınç davranışı)."""
        aralik = 1.0 / _HEDEF_FPS
        sonraki = time.perf_counter()
        while not dur.is_set():
            simdi = time.perf_counter()
            if simdi < sonraki:
                time.sleep(min(sonraki - simdi, 0.01))
                continue
            while sonraki < simdi - aralik:
                sonraki += aralik  # birikmişse en yeni kareye atla
            b = time.perf_counter()
            t.tespit_et(kareler[i])
            gecen_ms = (time.perf_counter() - b) * 1000
            with kilit:
                gecikmeler.append(gecen_ms)
            sayac[i] += 1
            sonraki += aralik

    parcaciklar = [
        threading.Thread(target=kamera_isi, args=(i,), daemon=True) for i in range(_KAMERA)
    ]
    basla = time.perf_counter()
    for p in parcaciklar:
        p.start()
    time.sleep(sure_sn)
    dur.set()
    for p in parcaciklar:
        p.join(timeout=5)
    gecen = time.perf_counter() - basla

    toplam = sum(sayac)
    hedef = _KAMERA * _HEDEF_FPS * gecen
    gecikmeler.sort()
    return {
        "model": model.name,
        "cihaz": t.etkin_cihaz,
        "is_parcacigi": is_parcacigi or "otomatik",
        "sure_sn": round(gecen, 1),
        "hedef_cikarim": round(hedef),
        "gerceklesen_cikarim": toplam,
        "kamera_basi_fps": round(toplam / gecen / _KAMERA, 2),
        "butce_yuzde": round(100 * toplam / hedef, 1),
        "ortanca_ms": round(statistics.median(gecikmeler), 1),
        "p90_ms": round(gecikmeler[int(len(gecikmeler) * 0.9)], 1),
    }


def kkd_turu(tur: int, kisi: int = _KAMERA) -> dict | None:
    """KKD sınıflandırıcısının bir karedeki `kisi` kişilik toplu çağrısı.
    Model dosyası yoksa None: tur atlanır, uydurma sayı basılmaz."""
    from app.analiz.kkd_siniflandirici import KkdSiniflandirici

    yol = _KOK / "models" / "kkd.onnx"
    if not yol.exists():
        return None
    kkd = KkdSiniflandirici(yol)  # özet tutmazsa ModelHatasi
    rng = np.random.default_rng(3)
    kirpiklar = [rng.integers(0, 256, size=(256, 128, 3), dtype=np.uint8) for _ in range(kisi)]
    for _ in range(3):  # ısınma
        kkd.degerlendir_toplu(kirpiklar)
    sureler = []
    for _ in range(tur):
        baslangic = time.perf_counter()
        kkd.degerlendir_toplu(kirpiklar)
        sureler.append((time.perf_counter() - baslangic) * 1000)
    return {
        "model": kkd.model_surumu,
        "kisi": kisi,
        "ortanca_ms": statistics.median(sureler),
        "p90_ms": statistics.quantiles(sureler, n=10)[-1] if len(sureler) > 1 else sureler[0],
    }


def _modeller() -> list[Path]:
    """Diskte olan her bilinen model: hazır modeller ve seçilebilen forklift
    modelleri. Sahada çalışan model hangisiyse onun hızı da ölçülmüş olur."""
    from app.analiz.model_indir import BILINEN_MODELLER

    bulunan = [_KOK / "models" / ad for ad in BILINEN_MODELLER]
    return [m for m in bulunan if m.exists()]


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(
        prog="python -m tests.hiz_kiyas",
        description="Tespit motorunun hızını ölçer (motoru değiştirmez).",
    )
    ayristirici.add_argument("--tek", action="store_true", help="yalnız tek akış ölçümü")
    ayristirici.add_argument("--dort", action="store_true", help="yalnız dört kamera ölçümü")
    ayristirici.add_argument("--kkd", action="store_true", help="yalnız KKD sınıflandırıcı turu")
    ayristirici.add_argument("--tur", type=int, default=25, help="tek akışta kaç kare (25)")
    ayristirici.add_argument("--sure", type=float, default=12.0, help="dört kamera kaç sn (12)")
    ayristirici.add_argument("--json", action="store_true", help="tabloyu değil JSON'u bas")
    secenek = ayristirici.parse_args(argv)

    modeller = _modeller()
    if not modeller:
        print("Model dosyası yok. Önce şunu çalıştırın:  bash models/indir.sh", file=sys.stderr)
        return 1

    import onnxruntime

    hepsi = not (secenek.tek or secenek.dort or secenek.kkd)
    sonuc: dict = {
        "ortam": {
            "python": sys.version.split()[0],
            "onnxruntime": onnxruntime.__version__,
            "saglayicilar": onnxruntime.get_available_providers(),
        },
        "tek_akis": [],
        "dort_kamera": [],
        "kkd": None,
    }

    try:
        if secenek.tek or hepsi:
            for model in modeller:
                for ip in (0, 3, 1):
                    sonuc["tek_akis"].append(tek_akis(model, ip, secenek.tur))
        if secenek.dort or hepsi:
            for model in modeller:
                sonuc["dort_kamera"].append(dort_kamera(model, 0, secenek.sure))
        if secenek.kkd or hepsi:
            sonuc["kkd"] = kkd_turu(secenek.tur)
    except ModelHatasi as hata:
        print(hata.kullanici_mesaji, file=sys.stderr)
        return 1

    if secenek.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=2))
        return 0

    o = sonuc["ortam"]
    print(f"\nOrtam: Python {o['python']}, onnxruntime {o['onnxruntime']}")
    print(f"Çalıştırıcılar: {', '.join(o['saglayicilar'])}")
    cuda_var = any("CUDA" in s for s in o["saglayicilar"])
    print(f"CUDA çalıştırıcısı: {'VAR' if cuda_var else 'YOK (CPU ölçümü)'}")

    if sonuc["tek_akis"]:
        print(f"\n- Tek akış, {_COZUNURLUK[0]}x{_COZUNURLUK[1]} kare, {secenek.tur} tur -")
        print(f"{'model':18s} {'iş parç.':10s} {'ortanca':>9s} {'p90':>8s} {'fps':>7s}")
        for r in sonuc["tek_akis"]:
            print(
                f"{r['model']:18s} {str(r['is_parcacigi']):10s} "
                f"{r['ortanca_ms']:7.1f}ms {r['p90_ms']:6.1f}ms {r['tek_akis_fps']:7.2f}"
            )

    if sonuc["dort_kamera"]:
        print(f"\n- {_KAMERA} kamera × {_HEDEF_FPS:g} fps bütçesi (docs/05 §3) -")
        print(f"{'model':18s} {'bütçe':>8s} {'kam/fps':>9s} {'ortanca':>9s} {'p90':>8s}")
        for r in sonuc["dort_kamera"]:
            print(
                f"{r['model']:18s} {r['butce_yuzde']:7.1f}% {r['kamera_basi_fps']:9.2f} "
                f"{r['ortanca_ms']:7.1f}ms {r['p90_ms']:6.1f}ms"
            )
        print()

    if secenek.kkd or hepsi:
        r = sonuc["kkd"]
        if r is None:
            print("KKD modeli yok (models/kkd.onnx): sınıflandırıcı turu atlandı.\n")
        else:
            print(f"- KKD sınıflandırıcı, {r['kisi']} kişilik toplu çağrı, {secenek.tur} tur -")
            print(f"{r['model']}: ortanca {r['ortanca_ms']:.1f}ms, p90 {r['p90_ms']:.1f}ms\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

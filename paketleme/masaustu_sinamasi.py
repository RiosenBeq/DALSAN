"""Uyarı kaydı arşivinin masaüstü klasörünü GERÇEK işletim sisteminde sınar.

Birim testleri (tests/test_uyari_arsivi.py) Windows'un bilinen klasör
API'sini taklit eder; bu betik gerçeğine sorar. GitHub Actions üretim işi
(.github/workflows/uygulama-uret.yml) Windows ve Mac'te çalıştırır; elle de:

    python paketleme/masaustu_sinamasi.py

Windows:
  1. Bilinen klasör API'sinin (SHGetKnownFolderPath) verdiği masaüstü,
     Windows'un kendi cevabıyla ([Environment]::GetFolderPath) aynı olmalı.
     API sessizce düşerse program yedeğe (USERPROFILE\\Desktop) geçer ve
     cevap yine tutabilir: bu yüzden API'nin cevabı ayrıca istenir.
  2. Masaüstü kayıt defterinde başka bir klasöre yönlendirilir - OneDrive'ın
     "masaüstünü yedekle" düğmesinin yaptığı budur - ve soru yeni bir
     süreçte tekrarlanır: program yine Windows'la aynı cevabı vermeli, eski
     C:\\Users\\<ad>\\Desktop'a düşmemeli. Yönlendirme sonunda geri alınır.
Mac: ~/Desktop; yoksa masaüstü yok sayılır (arşiv veri klasörüne düşer).

Her durumda bulunan masaüstünde arşiv klasörü gerçekten açılır, içine Türkçe
adlı bir CSV yazılıp geri okunur ve silinir.

Bir adım tutmazsa sebebini yazar ve 1 ile biter. Ölçüt Windows'un kendi
cevabıdır: yönlendirme bir makinede işlemezse bu yazılır ama sınama düşmez,
çünkü doğru davranış yine Windows'la aynı yeri bulmaktır.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]

# Programın kendi cevabı YENİ bir süreçte alınır: kayıt defteri değişince
# bilinen klasörün eski değeri bu süreçte önbellekte kalmış olabilir.
PROGRAMIN_CEVABI = """
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.olaylar import uyari_arsivi as u

api = u._windows_masaustu()
masaustu = u.masaustu_klasoru()
gecici = Path(tempfile.gettempdir())
ayarlar = SimpleNamespace(uyari_kaydi_arsiv_klasoru="", veri_dizini=gecici, kok_dizin=gecici)
print(json.dumps({
    "api": str(api) if api else None,
    "masaustu": str(masaustu) if masaustu else None,
    "arsiv": str(u.arsiv_klasoru(ayarlar)),
    "metin": u.klasor_metni(ayarlar),
    "klasor_adi": u.KLASOR_ADI,
}))
"""

KULLANICI_KLASORLERI = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"


class SinamaHatasi(Exception):
    """Bir adım tutmadı; ileti sebebi anlatır."""


def programin_cevabi() -> dict:
    ortam = dict(os.environ, PYTHONPATH=str(KOK / "backend"), PYTHONIOENCODING="utf-8")
    ortam.pop("DALSAN_KAPSAYICI", None)
    sonuc = subprocess.run(
        [sys.executable, "-c", PROGRAMIN_CEVABI],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=ortam,
        timeout=60,
        check=False,
    )
    if sonuc.returncode != 0:
        raise SinamaHatasi(f"program cevap vermedi ({sonuc.returncode}): {sonuc.stderr.strip()}")
    return json.loads(sonuc.stdout.strip().splitlines()[-1])


def windowsun_cevabi() -> Path:
    komut = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Environment]::GetFolderPath('Desktop')"
    )
    sonuc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", komut],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    yol = sonuc.stdout.strip()
    if sonuc.returncode != 0 or not yol:
        raise SinamaHatasi(f"Windows masaüstünü söylemedi: {sonuc.stderr.strip()}")
    return Path(yol)


def ayni_yer(a: str | Path | None, b: str | Path | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def cevabi_denetle(beklenen: Path | None, cevap: dict, windows: bool) -> None:
    print(f"  program: {cevap['masaustu']}  (API: {cevap['api']})")
    if windows and not ayni_yer(cevap["api"], beklenen):
        raise SinamaHatasi(f"bilinen klasör API'si {cevap['api']} dedi, Windows {beklenen}")
    if not ayni_yer(cevap["masaustu"], beklenen):
        raise SinamaHatasi(f"program {cevap['masaustu']} dedi, beklenen {beklenen}")
    if beklenen is None:
        return
    arsiv = Path(beklenen) / cevap["klasor_adi"]
    if not ayni_yer(cevap["arsiv"], arsiv):
        raise SinamaHatasi(f"arşiv klasörü {cevap['arsiv']}, beklenen {arsiv}")
    if cevap["metin"] != f"Masaüstü › {cevap['klasor_adi']}":
        raise SinamaHatasi(f"ekrandaki yer yanlış: {cevap['metin']}")
    yazip_oku(arsiv)


def yazip_oku(arsiv: Path) -> None:
    """Arşiv klasörü açılabiliyor, içine Türkçe adlı dosya yazılıp okunabiliyor mu."""
    vardi = arsiv.exists()
    arsiv.mkdir(parents=True, exist_ok=True)
    dosya = arsiv / "sınama - çalıştı mı ğüşiöç.csv"
    metin = "Uyarı zamanı;Kamera\n23.09.2026 14:05;Yükleme rampası\n"
    try:
        dosya.write_text(metin, encoding="utf-8-sig")
        if dosya.read_text(encoding="utf-8-sig") != metin:
            raise SinamaHatasi(f"{dosya} geri okunduğunda farklı çıktı")
    finally:
        dosya.unlink(missing_ok=True)
        if not vardi:
            arsiv.rmdir()
    print(f"  yazıldı ve okundu: {arsiv}")


def windows_sinamasi() -> None:
    import winreg

    print("1. Masaüstü olduğu yerde")
    cevabi_denetle(windowsun_cevabi(), programin_cevabi(), windows=True)

    print("2. Masaüstü OneDrive'a yönlendirilmiş gibi")
    gecici = Path(tempfile.mkdtemp(prefix="dalsan-masaustu-"))
    hedef = gecici / "OneDrive - Fabrika A.Ş" / "Masaüstü"
    hedef.mkdir(parents=True)
    erisim = winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KULLANICI_KLASORLERI, 0, erisim) as anahtar:
        eski, tur = winreg.QueryValueEx(anahtar, "Desktop")
        winreg.SetValueEx(anahtar, "Desktop", 0, winreg.REG_EXPAND_SZ, str(hedef))
        try:
            windows = windowsun_cevabi()
            if ayni_yer(windows, hedef):
                print(f"  Windows yönlendirmeyi görüyor: {windows}")
            else:
                print(f"  UYARI: yönlendirme bu makinede işlemedi, Windows hâlâ {windows} diyor")
            cevabi_denetle(windows, programin_cevabi(), windows=True)
        finally:
            winreg.SetValueEx(anahtar, "Desktop", 0, tur, eski)
            shutil.rmtree(gecici, ignore_errors=True)
    print("  yönlendirme geri alındı")


def mac_sinamasi() -> None:
    masaustu = Path.home() / "Desktop"
    beklenen = masaustu if masaustu.is_dir() else None
    print(f"Masaüstü: {beklenen or 'yok (arşiv veri klasörüne düşer)'}")
    cevabi_denetle(beklenen, programin_cevabi(), windows=False)


def main() -> int:
    try:
        if sys.platform == "win32":
            windows_sinamasi()
        elif sys.platform == "darwin":
            mac_sinamasi()
        else:
            print("Bu sınama Windows ve Mac içindir; Linux'u birim testleri kapsar.")
            return 0
    except SinamaHatasi as hata:
        print(f"HATA: {hata}")
        return 1
    print("masaüstü sınaması tamam")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

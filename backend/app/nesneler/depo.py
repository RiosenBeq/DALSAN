"""Nesne kütüphanesinin veritabanı ve dosya işleri.

Fotoğraflar `veri/nesneler/` altına yazılır (.env → NESNE_KLASORU). Bu klasör
GÖRÜNTÜ KLASÖRÜNÜN DIŞINDADIR: bakım döngüsü (supervizor.py) saklama süresi
dolan kanıt fotoğraflarını siler, ama kullanıcının elle tanıttığı nesne
fotoğrafları bir kanıt değildir ve kendiliğinden silinmez — tıpkı etiketlenmiş
KKD örneklerinin korunduğu gibi (docs/06 §5).

Parmak izleri veritabanında TUTULMAZ; her ihtiyaçta fotoğraflardan yeniden
hesaplanır (gerekçe: backend/sema/003_nesne_kutuphanesi.sql).
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import cv2

from app import zaman
from app.hatalar import DogrulamaHatasi
from app.nesneler import teshis
from app.nesneler.kutuphane import Nesne, Parmakizi, parmakizi_cikar

# Ad alanının sınırı: ekranda tek satırda görünmeli
EN_UZUN_AD = 60
EN_UZUN_ACIKLAMA = 200


def nesne_ekle(baglanti: sqlite3.Connection, ad: str, aciklama: str = "") -> int:
    ad = ad.strip()
    aciklama = aciklama.strip()
    if not ad:
        raise DogrulamaHatasi("Nesne adı boş olamaz (örnek: '3. hol yangın dolabı').")
    if len(ad) > EN_UZUN_AD:
        raise DogrulamaHatasi(f"Nesne adı en fazla {EN_UZUN_AD} karakter olabilir.")
    if len(aciklama) > EN_UZUN_ACIKLAMA:
        raise DogrulamaHatasi(f"Açıklama en fazla {EN_UZUN_ACIKLAMA} karakter olabilir.")
    try:
        imlec = baglanti.execute(
            "INSERT INTO library_objects (name, description, created_at) VALUES (?, ?, ?)",
            (ad, aciklama, zaman.simdi_utc()),
        )
    except sqlite3.IntegrityError as hata:
        raise DogrulamaHatasi(
            f"'{ad}' adında bir nesne zaten var. Başka bir ad yazın ya da var olan "
            "nesneye yeni fotoğraf ekleyin.",
            f"library_objects benzersiz ad kısıtı: {hata!r}",
        ) from hata
    baglanti.commit()
    return int(imlec.lastrowid)


def fotograf_ekle(
    baglanti: sqlite3.Connection,
    klasor: Path,
    nesne_id: int,
    dosya_adi: str,
    icerik: bytes,
    izinli_uzantilar: tuple[str, ...],
    en_buyuk_mb: int,
) -> str:
    """Yüklenen fotoğrafı DOĞRULAR, diske yazar, kayda geçer.

    Üç kapı: uzantı, boyut ve "gerçekten açılabilen bir görüntü mü". Üçüncüsü
    şart: uzantısı .jpg olan bozuk ya da sahte bir dosya kütüphaneye girerse
    her taramada sessizce atlanır ve kullanıcı nesnesinin neden bulunmadığını
    anlayamaz.
    """
    uzanti = Path(dosya_adi).suffix.lower()
    if uzanti not in izinli_uzantilar:
        okunur = ", ".join(u.lstrip(".").upper() for u in izinli_uzantilar)
        raise DogrulamaHatasi(f"'{dosya_adi}' desteklenmiyor. Şu türde fotoğraf yükleyin: {okunur}")
    if len(icerik) > en_buyuk_mb * 1024 * 1024:
        raise DogrulamaHatasi(f"'{dosya_adi}' çok büyük (en fazla {en_buyuk_mb} MB).")
    var_mi = baglanti.execute("SELECT 1 FROM library_objects WHERE id = ?", (nesne_id,)).fetchone()
    if var_mi is None:
        raise DogrulamaHatasi("Nesne bulunamadı; silinmiş olabilir. Sayfayı yenileyin.")

    ad = f"nesne{nesne_id}-{uuid.uuid4().hex[:8]}{uzanti}"
    klasor.mkdir(parents=True, exist_ok=True)
    hedef = klasor / ad
    try:
        hedef.write_bytes(icerik)
    except OSError as hata:
        raise DogrulamaHatasi(
            f"'{dosya_adi}' kaydedilemedi: {hata.strerror or 'disk hatası'}.",
            f"nesne fotoğrafı yazılamadı: {hedef} — {hata!r}",
        ) from hata

    # Gerçekten okunabilir bir görüntü mü? (bozuk dosya kütüphaneyi kirletmesin)
    if cv2.imread(str(hedef)) is None:
        hedef.unlink(missing_ok=True)
        raise DogrulamaHatasi(
            f"'{dosya_adi}' okunamadı; bozuk ya da fotoğraf olmayan bir dosya olabilir."
        )

    baglanti.execute(
        "INSERT INTO library_object_photos (object_id, file, added_at) VALUES (?, ?, ?)",
        (nesne_id, ad, zaman.simdi_utc()),
    )
    baglanti.commit()
    return ad


def nesne_sil(baglanti: sqlite3.Connection, klasor: Path, nesne_id: int) -> None:
    for satir in baglanti.execute(
        "SELECT file FROM library_object_photos WHERE object_id = ?", (nesne_id,)
    ).fetchall():
        _dosya_sil(klasor / satir["file"])
    # ON DELETE CASCADE fotoğraf satırlarını da siler (şema 003)
    baglanti.execute("DELETE FROM library_objects WHERE id = ?", (nesne_id,))
    baglanti.commit()


def fotograf_sil(baglanti: sqlite3.Connection, klasor: Path, foto_id: int) -> None:
    satir = baglanti.execute(
        "SELECT file FROM library_object_photos WHERE id = ?", (foto_id,)
    ).fetchone()
    if satir is None:
        return
    _dosya_sil(klasor / satir["file"])
    baglanti.execute("DELETE FROM library_object_photos WHERE id = ?", (foto_id,))
    baglanti.commit()


def _dosya_sil(dosya: Path) -> None:
    """Dosya kilitliyse kayıt yine de silinir; yetim dosya, yetim kayıttan iyidir."""
    try:
        dosya.unlink(missing_ok=True)
    except OSError:
        # Windows'ta başka bir işlem (Defender, yedekleme) dosyayı açık tutabilir.
        # Sessizce geçmiyoruz: dosya bir sonraki silmede ya da elle temizlenir,
        # veritabanı kaydı ise şimdi gidiyor — ekranda kırık resim kalmaz.
        return


def nesneleri_listele(baglanti: sqlite3.Connection) -> list[dict]:
    """Arayüz için: nesneler ve fotoğrafları."""
    nesneler = []
    for satir in baglanti.execute("SELECT * FROM library_objects ORDER BY name"):
        fotolar = [
            {"id": f["id"], "dosya": f["file"], "eklendi": zaman.ekranda_goster(f["added_at"])}
            for f in baglanti.execute(
                "SELECT * FROM library_object_photos WHERE object_id = ? ORDER BY id",
                (satir["id"],),
            )
        ]
        nesneler.append(
            {
                "id": satir["id"],
                "ad": satir["name"],
                "aciklama": satir["description"],
                "fotolar": fotolar,
            }
        )
    return nesneler


def teshisleri_al(baglanti: sqlite3.Connection, klasor: Path) -> dict[int, teshis.NesneTeshisi]:
    """Nesne id → "ne kadar tanınabilir" karnesi.

    ÖNBELLEKLİ. Ölçüm, fotoğrafları diskten okuyup parmak izi çıkarmayı
    gerektirir (ölçüldü: fotoğraf başına ~19 ms); 10 nesne × 8 fotoğraf 1,6
    saniye eder ve bu sayfa her ekleme/silmeden sonra yeniden yüklenir.
    Sonuç bu yüzden `library_object_diagnosis` tablosunda tutulur.

    BAYATLAMAYA KARŞI: satırda ölçümün dayandığı fotoğraf id'leri de yazar.
    Fotoğraf eklenir/silinirse anahtar tutmaz ve teşhis kendiliğinden yeniden
    hesaplanır — elle "geçersiz kıl" adımı yoktur, unutulacak adım da yoktur.
    """
    onbellek = {
        satir["object_id"]: satir
        for satir in baglanti.execute("SELECT * FROM library_object_diagnosis")
    }
    karneler: dict[int, teshis.NesneTeshisi] = {}
    yazilacak: list[tuple] = []
    for satir in baglanti.execute("SELECT id FROM library_objects ORDER BY id"):
        nesne_id = int(satir["id"])
        foto_adlari = [
            (int(f["id"]), f["file"])
            for f in baglanti.execute(
                "SELECT id, file FROM library_object_photos WHERE object_id = ? ORDER BY id",
                (nesne_id,),
            )
        ]
        anahtar = ",".join(str(foto_id) for foto_id, _ in foto_adlari)
        kayit = onbellek.get(nesne_id)
        if kayit is not None and kayit["photo_key"] == anahtar:
            karneler[nesne_id] = teshis.teshisi_kur(
                len(foto_adlari), int(kayit["keypoints"]), float(kayit["consistency"])
            )
            continue
        izler = _parmakizleri_oku(klasor, [ad for _, ad in foto_adlari])
        nokta, tutarlilik = teshis.olcumler(izler)
        karneler[nesne_id] = teshis.teshisi_kur(len(izler), nokta, tutarlilik)
        yazilacak.append((nesne_id, anahtar, nokta, tutarlilik, zaman.simdi_utc()))
    if yazilacak:
        baglanti.executemany(
            "INSERT OR REPLACE INTO library_object_diagnosis "
            "(object_id, photo_key, keypoints, consistency, computed_at) VALUES (?, ?, ?, ?, ?)",
            yazilacak,
        )
        baglanti.commit()
    return karneler


def _parmakizleri_oku(klasor: Path, dosya_adlari: list[str]) -> list[Parmakizi]:
    """Okunabilen fotoğrafların parmak izleri; bozuk/kayıp dosya atlanır."""
    izler = []
    for ad in dosya_adlari:
        gorsel = cv2.imread(str(klasor / ad))
        if gorsel is None:
            continue
        izi = parmakizi_cikar(gorsel)
        if izi is not None:
            izler.append(izi)
    return izler


def nesneleri_yukle(baglanti: sqlite3.Connection, klasor: Path) -> list[Nesne]:
    """Eşleştirme için parmak izleriyle birlikte nesneler.

    Dosyası silinmiş ya da okunamayan fotoğraf ATLANIR: tek bozuk dosya yüzünden
    kütüphanenin tamamı çalışmaz duruma düşmemeli. Hiç parmak izi çıkmayan nesne
    listeye girmez — adı var, izi yok bir nesne taramada hiçbir işe yaramaz.
    """
    nesneler: list[Nesne] = []
    for satir in baglanti.execute("SELECT * FROM library_objects ORDER BY id"):
        adlar = [
            foto["file"]
            for foto in baglanti.execute(
                "SELECT file FROM library_object_photos WHERE object_id = ?", (satir["id"],)
            )
        ]
        izler = _parmakizleri_oku(klasor, adlar)
        if izler:
            nesneler.append(Nesne(id=satir["id"], ad=satir["name"], parmakizleri=izler))
    return nesneler

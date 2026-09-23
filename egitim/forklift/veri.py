"""LOCO verisini indirir ve forklift ek başının eğitimine hazırlar (docs/17 §12.3).

Operatör isteği 23.09.2026. Yalnız standart kütüphane, numpy ve OpenCV
kullanır; torch GEREKMEZ: CI'da veri işi eğitimden ayrı, hafif bir Python'la
çalışır ve sonucu önbelleğe alınır.

    python egitim/forklift/veri.py indir --hedef DIR
    python egitim/forklift/veri.py hazirla --kaynak DIR --hedef OUT
        [--en-uzun-kenar 1280] [--sinir N] [--forklift-tekrar 3]
    python egitim/forklift/veri.py agirlik --boy tiny --hedef yolox_tiny.pth

`indir`: LOCO etiket JSON'u ve LICENSE dosyası sabitlenmiş commit'ten iner;
SHA-256'ları ortak.py'deki değerle tutmazsa çıkış kodu 2. Görüntü arşivi
(~770 MB zip) ortak.LOCO_ARSIV_ADRESLERI sırasıyla denenir: her yönlendirme
adımı, son adres, Content-Type ve Content-Length günlüğe yazılır; dosya
DIR/loco.zip.part'a akarken SHA-256'sı hesaplanır; kopan bağlantı sunucu
izin verirse Range ile kaldığı yerden sürer. HTML sayfası ve zip olmayan içerik
reddedilir. Bitince her üyenin CRC'si denetlenir, dosya loco.zip adını alır ve
DIR/indirme.json yazılır. Arşivin özeti henüz sabitlenmedi
(ortak.LOCO_ARSIV_SHA256 None): günlükteki "LOCO_ARSIV_SHA256=<özet>" satırı
ilk gerçek indirmeden sonra ortak.py'ye yazılır; o andan sonra tutmayan arşiv
çıkış kodu 2 ile reddedilir.

`hazirla`: JSON'daki her görüntü zip'te bulunur, uzun kenarı en fazla
--en-uzun-kenar olacak biçimde küçültülür (asla büyütülmez) ve düz klasörlere
yazılır:

    OUT/egitim/000001.jpg ...     subset-2, 3, 5 (yazarların ortam ayrık bölmesi)
    OUT/test/000001.jpg ...       subset-1, 4
    OUT/annotations/egitim.json   COCO; forklift içeren her görüntü --forklift-tekrar
                                  kez listelenir (forklift az örnekli sınıftır)
    OUT/annotations/test.json     COCO; tekrarsız, görüntülerde "alt_kume" ve "kaynak_yol"
    OUT/hazirlik.json             sayılar, eksik görüntüler, özetler, ayarlar
    OUT/LICENSE                   LOCO lisansı (CC0 1.0), kaynakta varsa

Kategoriler: 1 forklift, 2 pallet_jack (LOCO "pallet_truck"). Palet, küçük yük
taşıyıcı ve kafes atılır (ortak.LOCO_ESLEME). Seçilen görüntülerin %2'sinden
fazlası zip'te yoksa ya da kullanılamıyorsa arşivin düzeni JSON'la uyuşmuyordur:
çıkış kodu 2 ve yarım veri seti bırakılmaz (hazırlık geçici klasörde yapılır,
yalnız başarıyla biterse OUT adını alır). Bir JSON yolu içeriği farklı birden
çok zip üyesine uyuyorsa (ör. önizleme ya da yinelenmiş bir ağaç) de çıkış
kodu 2: hangisinin asıl görüntü olduğu sessizce tahmin edilmez.

Çıkış kodları: 0 başarı; 1 indirme denemeleri tükendi (ağ, sunucu); 2 özet
tutmadı, içerik ya da girdi hatalı, arşiv JSON'la uyuşmuyor.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import ortak

ETIKET_DOSYASI = "loco-all-v1.json"
LISANS_DOSYASI = "LICENSE"
ARSIV_DOSYASI = "loco.zip"
INDIRME_KAYDI = "indirme.json"
HAZIRLIK_KAYDI = "hazirlik.json"
HAZIRLIK_SURUMU = 1

# Zip yerel dosya başlığının imzası: arşiv bu dört baytla başlar.
ZIP_IMZASI = b"PK\x03\x04"

# Seçilen görüntülerin en çok bu kadarı eksik ya da kullanılamaz olabilir;
# fazlası arşiv düzeninin JSON'daki yollarla uyuşmadığını gösterir.
EKSIK_ORANI_EN_FAZLA = 0.02
# Arşivdeki görüntünün en-boy oranı JSON'dakinden bu kadar saparsa kutular
# görüntüye oturmaz; görüntü kullanılmaz.
EN_BOY_TOLERANSI = 0.01
JPEG_KALITESI = 92

DENEME_SAYISI = 5
BEKLEME_SN = 10.0  # denemeler arası: 10, 20, 40, 80 sn
ZAMAN_ASIMI_SN = 60.0  # tek bir bağlantı ya da okuma adımı için
_PARCA_BAYT = 1024 * 1024
_ILERLEME_ADIMI_BAYT = 64 * 1024 * 1024
_KULLANICI_AJANI = "dalsan-forklift-veri/1"

FORKLIFT = ortak.EK_SINIFLAR[0]
# YOLOX COCODataset sınıf indeksini sıralı kategori kimliklerinden alır:
# forklift 1 -> 0, pallet_jack 2 -> 1 (ek başın çıkış sırası).
KATEGORILER = tuple({"id": no, "name": ad} for no, ad in enumerate(ortak.EK_SINIFLAR, 1))
_KATEGORI_KIMLIGI = {k["name"]: k["id"] for k in KATEGORILER}
_KATEGORI_ADI = {k["id"]: k["name"] for k in KATEGORILER}
BOLUMLER = {"egitim": ortak.EGITIM_ALT_KUMELERI, "test": ortak.TEST_ALT_KUMELERI}


class VeriHatasi(Exception):
    """veri.py'nin bilinçli hatalarının atası; `cikis_kodu` sürecin çıkış kodu olur."""

    cikis_kodu = 1


class IndirmeHatasi(VeriHatasi):
    """Bütün adresler ve denemeler tükendi (sunucu kapalı, ağ yok)."""


class ButunlukHatasi(VeriHatasi):
    """Özet tutmadı, içerik ya da girdi hatalı: yeniden denemek düzeltmez."""

    cikis_kodu = 2


class GoruntuHatasi(ValueError):
    """Arşivdeki görüntü kullanılamıyor (çözülemedi, boyutu JSON'la uyuşmuyor)."""


class _DenemeHatasi(Exception):
    """Tek bir indirme denemesi yarım kaldı; yarım dosya korunur, sonra sürer."""


class _IcerikHatasi(_DenemeHatasi):
    """Gelen içerik arşiv değil (HTML sayfası, zip imzası yok, bozuk zip)."""


# Yeniden denemeyle geçebilecek hatalar. urllib.error.URLError/HTTPError,
# TimeoutError, ConnectionResetError ve ssl.SSLError OSError'dur;
# IncompleteRead ve BadStatusLine http.client.HTTPException'dır.
_GECICI_HATALAR = (OSError, http.client.HTTPException, _DenemeHatasi)


def _yaz(ileti: str) -> None:
    print(ileti, flush=True)


def _zaman_damgasi() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _dosyayi_ozetle(yol: Path, ozet=None):
    """Dosyanın baytlarını SHA-256 nesnesine katar (verilmezse yenisini açar)."""
    ozet = ozet if ozet is not None else hashlib.sha256()
    with yol.open("rb") as dosya:
        for parca in iter(lambda: dosya.read(_PARCA_BAYT), b""):
            ozet.update(parca)
    return ozet


def dosya_ozeti(yol: Path) -> str:
    return _dosyayi_ozetle(yol).hexdigest()


# ---------------------------------------------------------------------------
# HTTP: urllib, yönlendirmeler günlüğe yazılır
# ---------------------------------------------------------------------------


class _GunlukluYonlendirme(urllib.request.HTTPRedirectHandler):
    """Yönlendirmeleri izler ve her adımı günlüğe yazar: kısa bağlantının hangi
    sunucuya gittiği CI günlüğünde görünsün. Range başlığı yeni isteğe geçer."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _yaz(f"  yönlendirme {code}: {req.full_url} -> {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ac(adres: str, ek_basliklar: dict[str, str] | None, zaman_asimi_sn: float):
    basliklar = {"User-Agent": _KULLANICI_AJANI, **(ek_basliklar or {})}
    istek = urllib.request.Request(adres, headers=basliklar)
    return urllib.request.build_opener(_GunlukluYonlendirme()).open(istek, timeout=zaman_asimi_sn)


def _yanit_satiri(yanit) -> str:
    b = yanit.headers
    satir = (
        f"  yanıt {yanit.status}: {yanit.geturl()} | Content-Type: {b.get('Content-Type')} | "
        f"Content-Length: {b.get('Content-Length')} | Accept-Ranges: {b.get('Accept-Ranges')}"
    )
    if b.get("Content-Range"):
        satir += f" | Content-Range: {b.get('Content-Range')}"
    return satir


def _tamsayi(metin: str | None) -> int | None:
    try:
        return int(metin) if metin is not None else None
    except ValueError:
        return None


def _icerik_araligi(metin: str | None) -> tuple[int | None, int | None]:
    """'bytes 100-999/1000' -> (100, 1000); toplam '*' ise None."""
    if not metin or not metin.startswith("bytes "):
        return None, None
    aralik, _, toplam = metin[len("bytes ") :].partition("/")
    return _tamsayi(aralik.partition("-")[0]), _tamsayi(toplam)


def _sonraki_esik(inen: int, toplam: int | None) -> int:
    adim = max(toplam // 10, _ILERLEME_ADIMI_BAYT // 8) if toplam else _ILERLEME_ADIMI_BAYT
    return (inen // adim + 1) * adim


def _akit(yanit, dosya, ozet, *, onceki: int = 0, toplam: int | None = None) -> int:
    """Yanıt gövdesini dosyaya yazar ve özete katar; yazılan bayt sayısını
    döndürür. İlerleme her %10'da (en az 8 MB arayla; toplam bilinmiyorsa her
    64 MB'de) yazılır: küçük dosyalar günlüğü doldurmaz."""
    inen = 0
    baslangic = time.monotonic()
    esik = _sonraki_esik(onceki, toplam)
    while parca := yanit.read(_PARCA_BAYT):
        dosya.write(parca)
        ozet.update(parca)
        inen += len(parca)
        if onceki + inen >= esik:
            gecen = max(time.monotonic() - baslangic, 1e-6)
            oran = f" (%{100 * (onceki + inen) // toplam})" if toplam else ""
            _yaz(f"  {(onceki + inen) / 1e6:.0f} MB indi{oran}, {inen / 1e6 / gecen:.1f} MB/sn")
            esik = _sonraki_esik(onceki + inen, toplam)
    return inen


def _bekle(uyu: Callable[[float], None], bekleme_sn: float, deneme: int) -> None:
    sure = bekleme_sn * 2 ** (deneme - 1)
    if sure > 0:
        _yaz(f"  {sure:.0f} sn beklenip yeniden denenecek")
        uyu(sure)


def dosya_indir(
    adres: str,
    hedef: Path,
    beklenen_sha256: str,
    *,
    deneme_sayisi: int = DENEME_SAYISI,
    bekleme_sn: float = BEKLEME_SN,
    zaman_asimi_sn: float = ZAMAN_ASIMI_SN,
    uyu: Callable[[float], None] = time.sleep,
) -> str:
    """Tek dosyayı indirir; SHA-256 sabitlenen değerle tutarsa `hedef` olur.

    Hedef zaten varsa ve özeti tutuyorsa yeniden inmez. Özet tutmazsa
    ButunlukHatasi: dosya kaynağında değişmiş ya da yolda değiştiriliyor,
    yeniden denemek düzeltmez. Ağ hatası artan beklemeyle yeniden denenir.
    """
    if hedef.is_file() and dosya_ozeti(hedef) == beklenen_sha256:
        _yaz(f"{hedef.name}: zaten var, SHA-256 tuttu ({beklenen_sha256})")
        return beklenen_sha256
    hedef.parent.mkdir(parents=True, exist_ok=True)
    parca = hedef.with_name(hedef.name + ".part")
    son_hata = ""
    for deneme in range(1, deneme_sayisi + 1):
        _yaz(f"{hedef.name}: indiriliyor (deneme {deneme}/{deneme_sayisi}) {adres}")
        try:
            with _ac(adres, None, zaman_asimi_sn) as yanit, parca.open("wb") as dosya:
                _yaz(_yanit_satiri(yanit))
                ozet = hashlib.sha256()
                toplam = _tamsayi(yanit.headers.get("Content-Length"))
                inen = _akit(yanit, dosya, ozet, toplam=toplam)
            if toplam is not None and inen != toplam:
                raise _DenemeHatasi(f"bağlantı erken kapandı: {inen}/{toplam} bayt indi")
        except _GECICI_HATALAR as hata:
            son_hata = repr(hata)
            _yaz(f"  başarısız: {son_hata}")
            parca.unlink(missing_ok=True)
            if deneme < deneme_sayisi:
                _bekle(uyu, bekleme_sn, deneme)
            continue
        inen_ozet = ozet.hexdigest()
        if inen_ozet != beklenen_sha256:
            parca.unlink(missing_ok=True)
            raise ButunlukHatasi(
                f"{hedef.name} SHA-256'sı sabitlenen değerle tutmuyor: beklenen "
                f"{beklenen_sha256}, inen {inen_ozet} ({inen} bayt, {adres}). Dosya "
                "kaynağında değişmiş ya da yolda değiştiriliyor; kullanılmadı ve silindi."
            )
        parca.replace(hedef)
        _yaz(f"{hedef.name}: {inen} bayt, SHA-256 tuttu ({inen_ozet})")
        return inen_ozet
    raise IndirmeHatasi(
        f"{hedef.name} indirilemedi ({deneme_sayisi} deneme): {adres} | son hata: {son_hata}"
    )


def etiketleri_indir(hedef_klasor: Path) -> dict[str, str]:
    """LOCO etiket JSON'u ve lisansı (sabitlenmiş commit, SHA-256 denetimli)."""
    return {
        ad: dosya_indir(adres, hedef_klasor / ad, ozet)
        for ad, (adres, ozet) in (
            (ETIKET_DOSYASI, ortak.LOCO_ETIKET),
            (LISANS_DOSYASI, ortak.LOCO_LISANS),
        )
    }


@dataclass
class _YarimArsiv:
    """İnmekte olan arşiv: .part dosyası ve sunucunun bildirdiği toplam boyut."""

    parca: Path
    toplam: int | None = None

    def sifirla(self) -> None:
        self.parca.unlink(missing_ok=True)
        self.toplam = None


def _arsiv_denemesi(adres: str, arsiv: _YarimArsiv, zaman_asimi_sn: float):
    """Bir adresten bir deneme. Yarım dosya varsa Range ile kaldığı yerden ister.

    Döner: (son adres, SHA-256 nesnesi). İçerik arşiv değilse (HTML, zip imzası
    yok) _IcerikHatasi: bu denemede dosyaya hiçbir şey yazılmamıştır, başka bir
    adresten kalmış yarım dosya korunur. Bağlantı erken kapanırsa _DenemeHatasi:
    yarım dosya korunur, sonraki deneme kaldığı yerden ister.
    """
    mevcut = arsiv.parca.stat().st_size if arsiv.parca.exists() else 0
    basliklar = {"Range": f"bytes={mevcut}-"} if mevcut else None
    with _ac(adres, basliklar, zaman_asimi_sn) as yanit:
        _yaz(_yanit_satiri(yanit))
        tur = yanit.headers.get("Content-Type") or ""
        if tur.split(";", 1)[0].strip().lower() == "text/html":
            raise _IcerikHatasi(f"HTML sayfası geldi (Content-Type: {tur}), arşiv değil")
        if yanit.status == 206:
            baslangic, toplam = _icerik_araligi(yanit.headers.get("Content-Range"))
            toplam = toplam if toplam is not None else arsiv.toplam
            baska_dosya = arsiv.toplam is not None and toplam != arsiv.toplam
            if baslangic != mevcut or baska_dosya:
                arsiv.sifirla()  # sunucudaki dosya değişmiş ya da aralık yanlış
                raise _DenemeHatasi(
                    f"sunucunun verdiği aralık tutarsız ({yanit.headers.get('Content-Range')}, "
                    f"elde {mevcut} bayt var); baştan indirilecek"
                )
        else:  # 200: sunucu Range'i yok saydı ya da yeni indirme
            baslangic, toplam = 0, _tamsayi(yanit.headers.get("Content-Length"))
        ilk = yanit.read(_PARCA_BAYT)
        if baslangic == 0 and not ilk.startswith(ZIP_IMZASI):
            raise _IcerikHatasi(f"içerik zip değil (ilk baytlar {ilk[:16]!r})")
        if baslangic:
            _yaz(f"  kaldığı yerden sürüyor: {baslangic} bayt zaten inmişti")
            ozet = _dosyayi_ozetle(arsiv.parca)
        else:
            if mevcut:
                _yaz("  sunucu kaldığı yerden vermedi; baştan indiriliyor")
            ozet = hashlib.sha256()
        arsiv.toplam = toplam
        with arsiv.parca.open("ab" if baslangic else "wb") as dosya:
            dosya.write(ilk)
            ozet.update(ilk)
            _akit(yanit, dosya, ozet, onceki=baslangic + len(ilk), toplam=toplam)
        son_adres = yanit.geturl()
    boyut = arsiv.parca.stat().st_size
    if arsiv.toplam is not None and boyut != arsiv.toplam:
        raise _DenemeHatasi(f"bağlantı erken kapandı: {boyut}/{arsiv.toplam} bayt indi")
    return son_adres, ozet


def _zip_denetle(yol: Path) -> int:
    """Tam inen dosya sağlam bir zip mi? Her üyenin CRC'si okunur (özet henüz
    sabitlenmediyken kaldığı yerden sürmüş bir indirmenin tek bütünlük
    denetimi budur). Üye sayısını döndürür."""
    if not zipfile.is_zipfile(yol):
        raise _IcerikHatasi("indirilen dosya zip değil (merkez dizini bulunamadı)")
    try:
        with zipfile.ZipFile(yol) as arsiv:
            bozuk = arsiv.testzip()
            adet = len(arsiv.infolist())
    except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError) as hata:
        raise _IcerikHatasi(f"zip okunamadı: {hata!r}") from hata
    if bozuk is not None:
        raise _IcerikHatasi(f"zip'te CRC'si tutmayan üye var: {bozuk}")
    return adet


def _gecerli_eski_arsiv(son: Path, kayit_yolu: Path, beklenen_sha256: str | None) -> dict | None:
    """Önceki bir `indir`in bıraktığı arşiv kaydıyla (ve sabitlenen özetle) tutuyorsa kaydı."""
    if not (son.is_file() and kayit_yolu.is_file()):
        return None
    try:
        kayit = json.loads(kayit_yolu.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(kayit, dict):
        return None
    ozet = dosya_ozeti(son)
    if ozet != kayit.get("sha256") or beklenen_sha256 not in (None, ozet):
        return None
    return kayit


def arsivi_indir(
    adresler: Sequence[str],
    hedef_klasor: Path,
    *,
    beklenen_sha256: str | None = None,
    beklenen_boyut: int | None = None,
    deneme_sayisi: int = DENEME_SAYISI,
    bekleme_sn: float = BEKLEME_SN,
    zaman_asimi_sn: float = ZAMAN_ASIMI_SN,
    uyu: Callable[[float], None] = time.sleep,
) -> dict:
    """Görüntü arşivini `adresler` sırasıyla dener; DIR/loco.zip + indirme.json.

    Her turda adresler sırayla denenir, tur başarısızsa artan beklemeyle yeni
    tur başlar. Kopan bağlantının yarım dosyası korunur ve sonraki deneme Range
    ile kaldığı yerden ister (sunucu vermezse baştan). HTML ya da zip olmayan
    içerik o deneme için reddedilir. `beklenen_sha256` verilmişse ve tutmazsa
    ButunlukHatasi (arşiv CRC denetiminden geçtiği için bozulma değil, başka
    bir dosya: yeniden indirmek düzeltmez).
    """
    hedef_klasor.mkdir(parents=True, exist_ok=True)
    son = hedef_klasor / ARSIV_DOSYASI
    kayit_yolu = hedef_klasor / INDIRME_KAYDI
    eski = _gecerli_eski_arsiv(son, kayit_yolu, beklenen_sha256)
    if eski is not None:
        _yaz(f"arşiv: {son} zaten var, SHA-256 kayıtla tuttu")
        print(f"LOCO_ARSIV_SHA256={eski['sha256']}", flush=True)
        return eski
    # Önceki bir süreçten kalan yarım dosyanın hangi sürümden olduğu bilinmez.
    arsiv = _YarimArsiv(hedef_klasor / (ARSIV_DOSYASI + ".part"))
    arsiv.sifirla()
    son_hatalar: dict[str, str] = {}
    for deneme in range(1, deneme_sayisi + 1):
        for adres in adresler:
            _yaz(f"arşiv: deneme {deneme}/{deneme_sayisi}: {adres}")
            try:
                son_adres, ozet = _arsiv_denemesi(adres, arsiv, zaman_asimi_sn)
                try:
                    uye_sayisi = _zip_denetle(arsiv.parca)
                except _IcerikHatasi:
                    arsiv.sifirla()  # tam indi ama bozuk: yarım dosya olarak işe yaramaz
                    raise
            except _IcerikHatasi as hata:
                son_hatalar[adres] = str(hata)
                _yaz(f"  reddedildi: {hata}")
                continue
            except urllib.error.HTTPError as hata:
                hata.close()
                if hata.code == 416:  # istenen aralık yok: yarım dosya işe yaramaz
                    arsiv.sifirla()
                son_hatalar[adres] = f"HTTP {hata.code} {hata.reason}"
                _yaz(f"  başarısız: HTTP {hata.code} {hata.reason}")
                continue
            except _GECICI_HATALAR as hata:
                son_hatalar[adres] = repr(hata)
                _yaz(f"  başarısız: {hata!r}")
                continue
            return _arsivi_kaydet(
                arsiv.parca,
                son,
                kayit_yolu,
                son_adres=son_adres,
                ozet=ozet.hexdigest(),
                uye_sayisi=uye_sayisi,
                beklenen_sha256=beklenen_sha256,
                beklenen_boyut=beklenen_boyut,
            )
        if deneme < deneme_sayisi:
            _bekle(uyu, bekleme_sn, deneme)
    arsiv.sifirla()
    ayrinti = " | ".join(f"{adres}: {neden}" for adres, neden in son_hatalar.items())
    raise IndirmeHatasi(
        f"LOCO görüntü arşivi {deneme_sayisi} turda hiçbir adresten inmedi. Son hatalar: "
        f"{ayrinti}. Sunucu geçici olarak kapalı olabilir; iş daha sonra yeniden çalıştırılabilir."
    )


def _arsivi_kaydet(
    parca: Path,
    son: Path,
    kayit_yolu: Path,
    *,
    son_adres: str,
    ozet: str,
    uye_sayisi: int,
    beklenen_sha256: str | None,
    beklenen_boyut: int | None,
) -> dict:
    boyut = parca.stat().st_size
    _yaz(f"arşiv indi: {son_adres} | {boyut} bayt | {uye_sayisi} üye | SHA-256 {ozet}")
    if beklenen_boyut is not None and boyut != beklenen_boyut:
        _yaz(
            f"  UYARI: boyut {boyut} bayt; 23.09.2026 yoklamasında {beklenen_boyut} bayttı. "
            "Arşiv sunucuda değişmiş olabilir."
        )
    if beklenen_sha256 is not None and ozet != beklenen_sha256:
        parca.unlink(missing_ok=True)
        raise ButunlukHatasi(
            f"LOCO görüntü arşivinin SHA-256'sı sabitlenen değerle tutmuyor: beklenen "
            f"{beklenen_sha256}, inen {ozet} ({boyut} bayt, {son_adres}). Arşiv sunucuda "
            "değişmiş olabilir; kaynağı doğrulanmayan veriyle eğitim yapılmaz. Yeni arşiv "
            "bilerek kabul edilecekse ortak.LOCO_ARSIV_SHA256 güncellenir."
        )
    if beklenen_sha256 is None:
        _yaz(
            "  arşiv özeti henüz sabitlenmedi (ortak.LOCO_ARSIV_SHA256 None): "
            "aşağıdaki değer ortak.py'ye yazılmalı"
        )
    parca.replace(son)
    kayit = {"adres": son_adres, "boyut": boyut, "sha256": ozet, "zaman": _zaman_damgasi()}
    kayit_yolu.write_text(json.dumps(kayit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"LOCO_ARSIV_SHA256={ozet}", flush=True)
    return kayit


# ---------------------------------------------------------------------------
# Hazırlık: saf işlevler (ağsız, görüntüsüz sınanır)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kutu:
    """Ek baş sınıfı ve COCO xywh kutusu (piksel)."""

    sinif: str
    x: float
    y: float
    w: float
    h: float


def _forklift_var(kutular: Iterable[Kutu]) -> bool:
    return any(k.sinif == FORKLIFT for k in kutular)


@dataclass(frozen=True)
class LocoGoruntu:
    """JSON'daki bir görüntü: yolu, alt kümesi, JSON'daki boyutu ve süzülmüş kutuları."""

    yol: str  # "/dataset/subset-3/2019-12-17_10/Cam1/1576578645.9.jpg"
    alt_kume: str
    genislik: int
    yukseklik: int
    kutular: tuple[Kutu, ...]

    @property
    def forklift_var(self) -> bool:
        return _forklift_var(self.kutular)


@dataclass(frozen=True)
class Kayit:
    """Yazılmış bir görüntü: dosya adı, yeni boyutu ve yeni piksellerdeki kutuları."""

    dosya_adi: str
    genislik: int
    yukseklik: int
    alt_kume: str
    kaynak_yol: str
    kutular: tuple[Kutu, ...]

    @property
    def forklift_var(self) -> bool:
        return _forklift_var(self.kutular)


def alt_kume_bul(yol: str) -> str:
    """'/dataset/subset-3/2019-12-17_10/Cam1/x.jpg' -> 'subset-3'.

    Yollar metin olarak bölünür, kabuğa hiç verilmez: 1644 yolda virgül var.
    """
    parcalar = yol.split("/")
    if len(parcalar) < 4 or parcalar[0] or not parcalar[2]:
        raise ButunlukHatasi(
            f"LOCO görüntü yolu beklenen biçimde değil: {yol!r} "
            "(beklenen: /dataset/subset-N/.../ad.jpg)"
        )
    return parcalar[2]


def loco_goruntuleri(belge: dict) -> tuple[list[LocoGoruntu], Counter]:
    """LOCO JSON'u -> görüntüler ve atılan kutu sayıları.

    Yalnız ortak.LOCO_ESLEME'deki sınıflar kalır (forklift, pallet_truck ->
    pallet_jack). Genişliği ya da yüksekliği 1 pikseli geçmeyen kutu (özgün
    piksel) atılır: eğitimde anlamsızdır, COCO alanı sıfıra iner.
    """
    try:
        kategori_adi = {k["id"]: k["name"] for k in belge["categories"]}
        kutular: dict[int, list[Kutu]] = defaultdict(list)
        atilan: Counter = Counter()
        for etiket in belge["annotations"]:
            sinif = ortak.LOCO_ESLEME.get(kategori_adi.get(etiket["category_id"], ""))
            if sinif is None:
                atilan["baska_sinif"] += 1
                continue
            x, y, w, h = (float(deger) for deger in etiket["bbox"])
            if w <= 1 or h <= 1:
                atilan["kucuk_kutu"] += 1
                continue
            kutular[etiket["image_id"]].append(Kutu(sinif, x, y, w, h))
        goruntuler = []
        for goruntu in belge["images"]:
            genislik, yukseklik = int(goruntu["width"]), int(goruntu["height"])
            if genislik <= 0 or yukseklik <= 0:
                raise ValueError(f"boyut yok: {goruntu['path']!r}")
            goruntuler.append(
                LocoGoruntu(
                    yol=goruntu["path"],
                    alt_kume=alt_kume_bul(goruntu["path"]),
                    genislik=genislik,
                    yukseklik=yukseklik,
                    kutular=tuple(kutular.get(goruntu["id"], ())),
                )
            )
    except (KeyError, TypeError, ValueError, AttributeError) as hata:
        raise ButunlukHatasi(f"LOCO etiket dosyası beklenen biçimde değil: {hata!r}") from hata
    return goruntuler, atilan


def bolumle(goruntuler: Iterable[LocoGoruntu]) -> tuple[dict[str, list[LocoGoruntu]], Counter]:
    """Yazarların bölmesi: {"egitim": [...], "test": [...]} ve tanınmayan alt kümeler."""
    bolumler: dict[str, list[LocoGoruntu]] = {ad: [] for ad in BOLUMLER}
    bilinmeyen: Counter = Counter()
    for goruntu in goruntuler:
        for ad, alt_kumeler in BOLUMLER.items():
            if goruntu.alt_kume in alt_kumeler:
                bolumler[ad].append(goruntu)
                break
        else:
            bilinmeyen[goruntu.alt_kume] += 1
    return bolumler, bilinmeyen


def sinirla(goruntuler: Iterable[LocoGoruntu], sinir: int | None) -> list[LocoGoruntu]:
    """Yol sırasıyla görüntüler. `sinir` verilmişse her alt kümeden en çok
    `sinir` tane: önce forklift içerenler, sonra ötekiler, ikisi de yol
    sırasıyla (duman koşusu da forklift görsün; sonuç her seferinde aynı)."""
    if sinir is None:
        return sorted(goruntuler, key=lambda g: g.yol)
    gruplar: dict[str, list[LocoGoruntu]] = defaultdict(list)
    for goruntu in goruntuler:
        gruplar[goruntu.alt_kume].append(goruntu)
    secilen: list[LocoGoruntu] = []
    for grup in gruplar.values():
        secilen.extend(sorted(grup, key=lambda g: (not g.forklift_var, g.yol))[:sinir])
    return sorted(secilen, key=lambda g: g.yol)


@dataclass(frozen=True)
class UyeDizini:
    """Zip üye adlarının arama dizini (bir kez kurulur)."""

    tam: dict[str, str]  # "/" ayraçlı ad -> üye adı
    sonek: dict[str, str]  # her "/" sınırındaki sonek ve tam ad -> üye adı
    # Birden çok FARKLI üyenin taşıdığı sonekler -> o üyelerin hepsi
    cakisan: dict[str, frozenset[str]] = field(default_factory=dict)


def uye_dizini(adlar: Iterable[str]) -> UyeDizini:
    """Arşivin kök klasörü bilinmiyor ("dataset/", "LOCO/v1/dataset/" ...):
    her üye, adının "/" sınırlarındaki bütün sonekleriyle dizine girer. Aynı
    soneki taşıyan birden çok üye varsa en kısa adlı (eşitse alfabetik ilk)
    seçilir: sonuç arşivin sırasına bağlı değildir. Böyle sonekler `cakisan`da
    da durur: seçimin sessiz kalmaması için hazirla onlara bakar
    (cakisan_uyeler). Windows'ta yazılmış zip'lerin "\\" ayracı "/" sayılır;
    klasör girdileri atlanır."""
    tam: dict[str, str] = {}
    sonek: dict[str, str] = {}
    cakisan: dict[str, set[str]] = {}
    for ad in adlar:
        duz = ad.replace("\\", "/")
        if duz.endswith("/"):
            continue
        tam.setdefault(duz, ad)
        anahtarlar = [duz] + [duz[i + 1 :] for i, harf in enumerate(duz) if harf == "/"]
        for anahtar in anahtarlar:
            onceki = sonek.get(anahtar)
            if onceki is not None and onceki != ad:
                cakisan.setdefault(anahtar, {onceki}).add(ad)
            if onceki is None or (len(ad), ad) < (len(onceki), onceki):
                sonek[anahtar] = ad
    return UyeDizini(tam, sonek, {k: frozenset(v) for k, v in cakisan.items()})


def _sonek_anahtari(yol: str) -> str:
    return yol.removeprefix("/dataset/").lstrip("/")


def uye_bul(dizin: UyeDizini, yol: str) -> str | None:
    """JSON yolunun zip üyesi: adı yol.lstrip("/") olan üye; yoksa adı, yolun
    baştaki "/dataset/" kısmı atılmış hâliyle biten üye; o da yoksa None."""
    tam = yol.lstrip("/")
    if tam in dizin.tam:
        return dizin.tam[tam]
    return dizin.sonek.get(_sonek_anahtari(yol))


def cakisan_uyeler(dizin: UyeDizini, yol: str) -> tuple[str, ...]:
    """Yol sonekten bulunuyorsa ve o soneki birden çok farklı üye taşıyorsa
    hepsi (ad sırasıyla); yoksa boş. Tam adla bulunan üye belirsiz değildir.

    Örnek: "LOCO/v1/dataset/subset-2/a/x.jpg" ve "onizleme/subset-2/a/x.jpg".
    uye_bul kısa adlıyı seçer; o bir önizleme ağacıysa eğitim sessizce düşük
    çözünürlüklü görüntü görürdü (kutular JSON boyutuyla ölçeklendiği için
    yine doğru yere düşer, yalnız "ölçeği farklı" uyarısı çıkardı).
    """
    if yol.lstrip("/") in dizin.tam:
        return ()
    return tuple(sorted(dizin.cakisan.get(_sonek_anahtari(yol), ())))


def olcek_hesapla(
    json_genislik: int, json_yukseklik: int, genislik: int, yukseklik: int, en_uzun_kenar: int
) -> tuple[int, int, float, float]:
    """Yazılacak boyut ve LOCO pikselinden yeni piksele çarpanlar: (w, h, fx, fy).

    Uzun kenar en çok `en_uzun_kenar` olur; görüntü asla büyütülmez. Çarpanlar
    JSON'daki boyuta göredir: arşivdeki görüntü farklı çözünürlükte ama aynı
    en-boy oranındaysa kutular yine doğru yere düşer. Oran farklıysa kutular
    görüntüye oturmaz: GoruntuHatasi.
    """
    json_orani = json_genislik / json_yukseklik
    if abs((genislik / yukseklik) / json_orani - 1) > EN_BOY_TOLERANSI:
        raise GoruntuHatasi(
            f"boyut JSON'la uyuşmuyor: arşivde {genislik}x{yukseklik}, "
            f"JSON'da {json_genislik}x{json_yukseklik}"
        )
    oran = min(1.0, en_uzun_kenar / max(genislik, yukseklik))
    yeni_genislik = max(1, round(genislik * oran))
    yeni_yukseklik = max(1, round(yukseklik * oran))
    return (
        yeni_genislik,
        yeni_yukseklik,
        yeni_genislik / json_genislik,
        yeni_yukseklik / json_yukseklik,
    )


def kutulari_olcekle(kutular: Iterable[Kutu], fx: float, fy: float) -> tuple[Kutu, ...]:
    """Kutuları yeni piksellere taşır (0,01 piksele yuvarlanır: JSON kısa ve kararlı kalır)."""
    return tuple(
        Kutu(
            k.sinif,
            round(k.x * fx, 2),
            round(k.y * fy, 2),
            round(k.w * fx, 2),
            round(k.h * fy, 2),
        )
        for k in kutular
    )


def coco_belgesi(
    kayitlar: Sequence[Kayit], *, forklift_tekrar: int = 1, bilgi: dict | None = None
) -> dict:
    """Yazılmış görüntülerden COCO belgesi.

    Görüntü kimlikleri 1'den başlar ve kayıt sırasını izler (dosya adındaki
    sıra no'suyla aynı). `forklift_tekrar` > 1 ise forklift içeren her görüntü
    toplam o kadar kez listelenir: ek girdiler yeni kimlikle aynı dosyayı
    gösterir ("asil_id" ilk girdinin kimliği), etiketleri de yeni kimlikle
    çoğaltılır. Forklift, LOCO'da el transpaletinden beş kat az örneklidir.
    """
    if forklift_tekrar < 1:
        raise ValueError(f"forklift_tekrar en az 1 olmalı: {forklift_tekrar}")
    goruntuler: list[dict] = []
    etiketler: list[dict] = []

    def ekle(kayit: Kayit, asil_id: int | None) -> int:
        kimlik = len(goruntuler) + 1
        giris = {
            "id": kimlik,
            "file_name": kayit.dosya_adi,
            "width": kayit.genislik,
            "height": kayit.yukseklik,
            "alt_kume": kayit.alt_kume,
            "kaynak_yol": kayit.kaynak_yol,
        }
        if asil_id is not None:
            giris["asil_id"] = asil_id
        goruntuler.append(giris)
        for kutu in kayit.kutular:
            etiketler.append(
                {
                    "id": len(etiketler) + 1,
                    "image_id": kimlik,
                    "category_id": _KATEGORI_KIMLIGI[kutu.sinif],
                    "bbox": [kutu.x, kutu.y, kutu.w, kutu.h],
                    "area": round(kutu.w * kutu.h, 2),
                    "iscrowd": 0,
                }
            )
        return kimlik

    asil_kimlikler = [ekle(kayit, None) for kayit in kayitlar]
    for _ in range(forklift_tekrar - 1):
        for kimlik, kayit in zip(asil_kimlikler, kayitlar, strict=True):
            if kayit.forklift_var:
                ekle(kayit, kimlik)
    belge: dict = {} if bilgi is None else {"info": bilgi}
    belge.update(
        images=goruntuler, annotations=etiketler, categories=[dict(k) for k in KATEGORILER]
    )
    return belge


def _bos_sayim() -> dict[str, int]:
    return {"goruntu": 0, "forklift_goruntu": 0, **{sinif: 0 for sinif in ortak.EK_SINIFLAR}}


def bolum_sayimi(kayitlar: Sequence[Kayit], belge: dict, alt_kumeler: Iterable[str]) -> dict:
    """Bir bölümün sayıları: benzersiz görüntü/kutu ve JSON'daki (tekrarlı) girdiler."""
    alt = {ad: _bos_sayim() for ad in alt_kumeler}
    kutu: Counter = Counter()
    for kayit in kayitlar:
        sayim = alt.setdefault(kayit.alt_kume, _bos_sayim())
        sayim["goruntu"] += 1
        sayim["forklift_goruntu"] += int(kayit.forklift_var)
        for k in kayit.kutular:
            sayim[k.sinif] += 1
            kutu[k.sinif] += 1
    kutu_kaydi = Counter(_KATEGORI_ADI[e["category_id"]] for e in belge["annotations"])
    return {
        "goruntu": len(kayitlar),
        "goruntu_kaydi": len(belge["images"]),
        "forklift_goruntu": sum(int(kayit.forklift_var) for kayit in kayitlar),
        "kutu": {sinif: kutu[sinif] for sinif in ortak.EK_SINIFLAR},
        "kutu_kaydi": {sinif: kutu_kaydi[sinif] for sinif in ortak.EK_SINIFLAR},
        "alt_kumeler": dict(sorted(alt.items())),
    }


# ---------------------------------------------------------------------------
# Hazırlık: görüntü ve dosya işleri
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IslenmisGoruntu:
    jpeg: bytes
    genislik: int
    yukseklik: int
    fx: float
    fy: float
    olcegi_farkli: bool  # arşivdeki boyut JSON'dakinden farklı (en-boy oranı aynı)


def goruntuyu_isle(
    veri: bytes, json_genislik: int, json_yukseklik: int, en_uzun_kenar: int
) -> IslenmisGoruntu:
    """Arşivdeki JPEG baytları -> küçültülmüş JPEG (kalite 92) ve kutu çarpanları.

    EXIF yönü BİLEREK uygulanmaz: JSON'daki genişlik/yükseklik ve kutular
    ham piksel düzenindedir; yazılan JPEG'de EXIF yoktur, eğitim de ham düzeni
    görür.
    """
    import cv2  # yalnız hazırlık gerektirir: `indir` salt standart kütüphaneyle çalışır
    import numpy as np

    if not veri:
        raise GoruntuHatasi("boş dosya")
    try:
        resim = cv2.imdecode(
            np.frombuffer(veri, dtype=np.uint8),
            cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION,
        )
    except cv2.error as hata:
        raise GoruntuHatasi(f"JPEG çözülemedi: {hata}") from hata
    if resim is None:
        raise GoruntuHatasi("JPEG çözülemedi")
    yukseklik, genislik = resim.shape[:2]
    yeni_genislik, yeni_yukseklik, fx, fy = olcek_hesapla(
        json_genislik, json_yukseklik, genislik, yukseklik, en_uzun_kenar
    )
    if (yeni_genislik, yeni_yukseklik) != (genislik, yukseklik):
        resim = cv2.resize(resim, (yeni_genislik, yeni_yukseklik), interpolation=cv2.INTER_AREA)
    tamam, kodlu = cv2.imencode(".jpg", resim, [cv2.IMWRITE_JPEG_QUALITY, JPEG_KALITESI])
    if not tamam:
        raise GoruntuHatasi("JPEG yazılamadı")
    return IslenmisGoruntu(
        jpeg=kodlu.tobytes(),
        genislik=yeni_genislik,
        yukseklik=yeni_yukseklik,
        fx=fx,
        fy=fy,
        olcegi_farkli=(genislik, yukseklik) != (json_genislik, json_yukseklik),
    )


def _bolumu_yaz(
    arsiv: zipfile.ZipFile,
    uyeler: dict[str, str | None],
    goruntuler: Sequence[LocoGoruntu],
    klasor: Path,
    en_uzun_kenar: int,
    sorunlar: list[tuple[str, str]],
) -> tuple[list[Kayit], str, int]:
    """Bir bölümün görüntülerini yazar. Döner: kayıtlar, görüntü özeti, ölçeği
    farklı görüntü sayısı. Kullanılamayan görüntü `sorunlar`a eklenir."""
    kayitlar: list[Kayit] = []
    ozet = hashlib.sha256()
    olcegi_farkli = 0
    baslangic = time.monotonic()
    for sira, goruntu in enumerate(goruntuler, 1):
        uye = uyeler[goruntu.yol]
        if uye is None:
            continue  # eksik: yazmaya başlamadan sayıldı
        try:
            islenmis = goruntuyu_isle(
                arsiv.read(uye), goruntu.genislik, goruntu.yukseklik, en_uzun_kenar
            )
        except GoruntuHatasi as hata:
            sorunlar.append((goruntu.yol, str(hata)))
            continue
        except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError) as hata:
            sorunlar.append((goruntu.yol, f"zip üyesi okunamadı: {hata!r}"))
            continue
        dosya_adi = f"{len(kayitlar) + 1:06d}.jpg"
        (klasor / dosya_adi).write_bytes(islenmis.jpeg)
        ozet.update(f"{dosya_adi} {hashlib.sha256(islenmis.jpeg).hexdigest()}\n".encode())
        olcegi_farkli += int(islenmis.olcegi_farkli)
        kayitlar.append(
            Kayit(
                dosya_adi=dosya_adi,
                genislik=islenmis.genislik,
                yukseklik=islenmis.yukseklik,
                alt_kume=goruntu.alt_kume,
                kaynak_yol=goruntu.yol,
                kutular=kutulari_olcekle(goruntu.kutular, islenmis.fx, islenmis.fy),
            )
        )
        if sira % 500 == 0:
            _yaz(
                f"  {klasor.name}: {sira}/{len(goruntuler)} ({time.monotonic() - baslangic:.0f} sn)"
            )
    return kayitlar, ozet.hexdigest(), olcegi_farkli


def _oran_denetimi(
    sorunlu: Sequence[str], secilen: int, ne: str, uye_ornekleri: Sequence[str]
) -> None:
    """Sorunlu görüntü %2'yi aşarsa durur. İleti iki tarafı da gösterir (JSON
    yolları ve arşivdeki gerçek üye adları): arşiv düzeni farklıysa tek bir
    başarısız koşunun günlüğü düzeltmeye yeter."""
    if len(sorunlu) > EKSIK_ORANI_EN_FAZLA * secilen:
        raise ButunlukHatasi(
            f"Seçilen {secilen} görüntünün {len(sorunlu)} tanesi {ne} "
            f"(%{100 * len(sorunlu) / secilen:.1f}; sınır %{100 * EKSIK_ORANI_EN_FAZLA:g}). "
            "Arşivin düzeni etiket dosyasındaki yollarla uyuşmuyor; veri seti yarım "
            f"hazırlanmadı. JSON'dan örnekler: {' | '.join(sorunlu[:5])}. Arşivdeki "
            f"üyelerden örnekler: {' | '.join(uye_ornekleri)}"
        )


def _cok_uyeli_yollar(
    arsiv: zipfile.ZipFile, dizin: UyeDizini, uyeler: dict[str, str | None]
) -> list[tuple[str, tuple[str, ...]]]:
    """Birden çok üyeye uyan seçilmiş yollar (yol sırasıyla).

    Üyelerin baytları aynıysa (CRC ve boyut) hangisinin okunduğu fark etmez:
    döner, hazırlık kaydına yazılır. Farklıysa hangisinin asıl görüntü olduğu
    bilinemez (ör. tam çözünürlük ve önizleme ağacı): ButunlukHatasi, hiçbir
    şey yazılmadan. Sessizce en kısa adlı üye seçilmez.
    """
    ayni: list[tuple[str, tuple[str, ...]]] = []
    farkli: list[tuple[str, tuple[str, ...]]] = []
    for yol in sorted(yol for yol, uye in uyeler.items() if uye is not None):
        adaylar = cakisan_uyeler(dizin, yol)
        if not adaylar:
            continue
        baytlar = {(arsiv.getinfo(ad).CRC, arsiv.getinfo(ad).file_size) for ad in adaylar}
        (ayni if len(baytlar) == 1 else farkli).append((yol, adaylar))
    if farkli:
        ornekler = " ; ".join(f"{yol}: {' | '.join(adaylar)}" for yol, adaylar in farkli[:3])
        raise ButunlukHatasi(
            f"Seçilen görüntülerden {len(farkli)} tanesinin yolu arşivde içeriği FARKLI "
            "birden çok üyeye uyuyor; hangisinin asıl görüntü olduğu bilinemez (ör. "
            "önizleme ya da yinelenmiş bir ağaç). Veri seti hazırlanmadı. Örnekler: "
            f"{ornekler}. Arşivin düzenine bakıp veri.py'deki üye aramasını (uye_bul) "
            "o düzene göre düzeltin."
        )
    if ayni:
        _yaz(
            f"UYARI: {len(ayni)} görüntünün yolu arşivde birden çok üyeye uyuyor; "
            f"baytları aynı, biri kullanıldı (ör. {ayni[0][0]}: {' | '.join(ayni[0][1])})"
        )
    return ayni


def _kayitli_arsiv_ozeti(kaynak: Path) -> str | None:
    yol = kaynak / INDIRME_KAYDI
    if not yol.is_file():
        return None
    try:
        kayit = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as hata:
        _yaz(f"UYARI: {yol} okunamadı ({hata!r}); arşiv özeti hazırlık kaydına yazılmadı")
        return None
    ozet = kayit.get("sha256") if isinstance(kayit, dict) else None
    return ozet if isinstance(ozet, str) else None


def _json_yaz(yol: Path, belge: dict) -> str:
    # Salt ASCII: pycocotools JSON'u platformun varsayılan kodlamasıyla açar.
    veri = json.dumps(belge, separators=(",", ":")).encode("ascii")
    yol.write_bytes(veri)
    return hashlib.sha256(veri).hexdigest()


def hazirla(
    kaynak: Path,
    hedef: Path,
    *,
    en_uzun_kenar: int = 1280,
    sinir: int | None = None,
    forklift_tekrar: int = 3,
) -> dict:
    """kaynak/loco-all-v1.json + kaynak/loco.zip -> hedef (COCO veri seti).

    Hedef yoksa ya da boş klasörse yazılır; doluysa ButunlukHatasi (eski ve
    yeni hazırlık karışmasın). Hazırlık hedefin yanındaki geçici klasörde
    yapılır ve yalnız başarıyla biterse hedef adını alır. hazirlik.json'u
    döndürür.
    """
    etiket_yolu = kaynak / ETIKET_DOSYASI
    arsiv_yolu = kaynak / ARSIV_DOSYASI
    for yol in (etiket_yolu, arsiv_yolu):
        if not yol.is_file():
            raise ButunlukHatasi(
                f"{yol} yok. Önce: python egitim/forklift/veri.py indir --hedef {kaynak}"
            )
    if hedef.exists() and (not hedef.is_dir() or any(hedef.iterdir())):
        raise ButunlukHatasi(
            f"Hedef klasör boş değil: {hedef}. Eski hazırlığın üstüne yazılmaz; "
            "klasörü silin ya da başka bir hedef verin."
        )
    baslangic = time.monotonic()
    ham = etiket_yolu.read_bytes()
    etiket_ozeti = hashlib.sha256(ham).hexdigest()
    try:
        belge = json.loads(ham)
    except ValueError as hata:
        raise ButunlukHatasi(f"{etiket_yolu} okunamadı: {hata}") from hata
    del ham
    goruntuler, atilan = loco_goruntuleri(belge)
    del belge
    bolumler, bilinmeyen = bolumle(goruntuler)
    secim = {ad: sinirla(liste, sinir) for ad, liste in bolumler.items()}
    secilen = sum(len(liste) for liste in secim.values())
    _yaz(
        f"etiketler: {len(goruntuler)} görüntü, seçilen {secilen} "
        + ", ".join(f"{ad} {len(liste)}" for ad, liste in secim.items())
        + (f"; tanınmayan alt küme: {dict(bilinmeyen)}" if bilinmeyen else "")
    )
    if secilen == 0:
        raise ButunlukHatasi(f"{etiket_yolu}: hazırlanacak görüntü yok")

    try:
        arsiv = zipfile.ZipFile(arsiv_yolu)
    except (zipfile.BadZipFile, OSError) as hata:
        raise ButunlukHatasi(f"{arsiv_yolu} zip olarak açılamadı: {hata!r}") from hata
    with arsiv:
        adlar = arsiv.namelist()
        dizin = uye_dizini(adlar)
        uyeler = {g.yol: uye_bul(dizin, g.yol) for liste in secim.values() for g in liste}
        eksik = sorted(yol for yol, uye in uyeler.items() if uye is None)
        uye_ornekleri = [ad for ad in adlar if not ad.endswith("/")][:3]
        _yaz(
            f"arşiv: {len(adlar)} üye (örnek: {' | '.join(uye_ornekleri)}); "
            f"seçilen görüntülerden {len(eksik)} tanesi arşivde yok"
        )
        _oran_denetimi(eksik, secilen, "arşivde yok", uye_ornekleri)
        cok_uyeli = _cok_uyeli_yollar(arsiv, dizin, uyeler)
        hedef.parent.mkdir(parents=True, exist_ok=True)
        gecici = Path(tempfile.mkdtemp(prefix=f".{hedef.name}-hazirlik-", dir=hedef.parent))
        tamam = False
        try:
            (gecici / "annotations").mkdir()
            sorunlar: list[tuple[str, str]] = []
            kayitlar: dict[str, list[Kayit]] = {}
            goruntu_ozetleri: dict[str, str] = {}
            olcegi_farkli = 0
            for ad, liste in secim.items():
                (gecici / ad).mkdir()
                kayitlar[ad], goruntu_ozetleri[ad], farkli = _bolumu_yaz(
                    arsiv, uyeler, liste, gecici / ad, en_uzun_kenar, sorunlar
                )
                olcegi_farkli += farkli
                _yaz(f"{ad}: {len(kayitlar[ad])} görüntü yazıldı")
            for yol, neden in sorunlar[:20]:
                _yaz(f"  kullanılamadı: {yol}: {neden}")
            _oran_denetimi(
                eksik + [yol for yol, _ in sorunlar],
                secilen,
                "arşivde yok ya da kullanılamıyor",
                uye_ornekleri,
            )
            if olcegi_farkli:
                _yaz(f"UYARI: {olcegi_farkli} görüntünün boyutu JSON'dakinden farklı (oran aynı)")

            belgeler = {}
            for ad, alt_kumeler in BOLUMLER.items():
                tekrar = forklift_tekrar if ad == "egitim" else 1
                bilgi = {
                    "aciklama": "LOCO (TU München, CC0 1.0): forklift ve el transpaleti",
                    "loco_commit": ortak.LOCO_COMMIT,
                    "bolum": ad,
                    "alt_kumeler": list(alt_kumeler),
                    "en_uzun_kenar": en_uzun_kenar,
                    "forklift_tekrar": tekrar,
                }
                belgeler[ad] = coco_belgesi(kayitlar[ad], forklift_tekrar=tekrar, bilgi=bilgi)
            json_ozetleri = {
                f"{ad}.json": _json_yaz(gecici / "annotations" / f"{ad}.json", belge)
                for ad, belge in belgeler.items()
            }
            rapor = {
                "surum": HAZIRLIK_SURUMU,
                "loco_commit": ortak.LOCO_COMMIT,
                "loco_etiket_sha256": etiket_ozeti,
                "loco_etiket_sabitlenen": etiket_ozeti == ortak.LOCO_ETIKET[1],
                "loco_arsiv_sha256": _kayitli_arsiv_ozeti(kaynak),
                "en_uzun_kenar": en_uzun_kenar,
                "sinir": sinir,
                "forklift_tekrar": forklift_tekrar,
                "json_sha256": json_ozetleri,
                "goruntu_sha256": goruntu_ozetleri,
                "listelenen_goruntu": len(goruntuler),
                "secilen_goruntu": secilen,
                "eksik_goruntu": len(eksik),
                "kullanilamayan_goruntu": len(sorunlar),
                "olcegi_farkli_goruntu": olcegi_farkli,
                "cok_uyeli_goruntu": len(cok_uyeli),
                "cok_uyeli_ornekler": [
                    f"{yol}: {' | '.join(adaylar)}" for yol, adaylar in cok_uyeli[:20]
                ],
                "eksik_ornekler": eksik[:20],
                "kullanilamayan_ornekler": [f"{yol}: {neden}" for yol, neden in sorunlar[:20]],
                "atilan_kutu": {n: atilan[n] for n in ("baska_sinif", "kucuk_kutu")},
                "taninmayan_alt_kume": dict(sorted(bilinmeyen.items())),
                "bolumler": {
                    ad: bolum_sayimi(kayitlar[ad], belgeler[ad], BOLUMLER[ad]) for ad in BOLUMLER
                },
            }
            (gecici / HAZIRLIK_KAYDI).write_text(
                json.dumps(rapor, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            if (kaynak / LISANS_DOSYASI).is_file():
                shutil.copyfile(kaynak / LISANS_DOSYASI, gecici / LISANS_DOSYASI)
            gecici.chmod(0o755)  # mkdtemp 0700 açar; veri seti yalnız sahibine kalmasın
            if hedef.exists():
                hedef.rmdir()  # boş olduğu yukarıda denetlendi
            gecici.rename(hedef)
            tamam = True
        finally:
            if not tamam:
                shutil.rmtree(gecici, ignore_errors=True)

    ozet_satiri = {
        "sure_sn": round(time.monotonic() - baslangic, 1),
        "eksik": len(eksik),
        "kullanilamayan": len(sorunlar),
        **{
            ad: {k: sayim[k] for k in ("goruntu", "goruntu_kaydi", "forklift_goruntu", "kutu")}
            for ad, sayim in rapor["bolumler"].items()
        },
    }
    _yaz(f"hazırlık bitti: {hedef}")
    print("HAZIRLIK_OZETI " + json.dumps(ozet_satiri, separators=(",", ":")), flush=True)
    return rapor


# ---------------------------------------------------------------------------
# Komut satırı
# ---------------------------------------------------------------------------


def _pozitif_tamsayi(metin: str) -> int:
    try:
        deger = int(metin)
    except ValueError as hata:
        raise argparse.ArgumentTypeError(f"tamsayı bekleniyordu: {metin!r}") from hata
    if deger < 1:
        raise argparse.ArgumentTypeError(f"en az 1 olmalı: {deger}")
    return deger


def _ayristirici() -> argparse.ArgumentParser:
    ayristirici = argparse.ArgumentParser(
        prog="veri.py", description="LOCO verisini indirir ve forklift ek başı için hazırlar."
    )
    komutlar = ayristirici.add_subparsers(dest="komut", required=True)
    indir = komutlar.add_parser("indir", help="etiketler, lisans ve görüntü arşivi")
    indir.add_argument("--hedef", type=Path, required=True, help="indirme klasörü")
    hazirla_ = komutlar.add_parser("hazirla", help="COCO JSON ve küçültülmüş görüntüler")
    hazirla_.add_argument("--kaynak", type=Path, required=True, help="`indir` klasörü")
    hazirla_.add_argument("--hedef", type=Path, required=True, help="veri seti klasörü")
    hazirla_.add_argument("--en-uzun-kenar", type=_pozitif_tamsayi, default=1280)
    hazirla_.add_argument(
        "--sinir", type=_pozitif_tamsayi, default=None, help="alt küme başına en çok görüntü"
    )
    hazirla_.add_argument("--forklift-tekrar", type=_pozitif_tamsayi, default=3)
    agirlik = komutlar.add_parser("agirlik", help="resmi YOLOX .pth (SHA-256 denetimli)")
    agirlik.add_argument("--boy", choices=sorted(ortak.RESMI_AGIRLIKLAR), required=True)
    agirlik.add_argument(
        "--hedef", type=Path, required=True, help=".pth dosyası ya da içine yazılacak klasör"
    )
    return ayristirici


def main(argv: Sequence[str] | None = None) -> int:
    secenekler = _ayristirici().parse_args(argv)
    try:
        if secenekler.komut == "indir":
            etiketleri_indir(secenekler.hedef)
            arsivi_indir(
                ortak.LOCO_ARSIV_ADRESLERI,
                secenekler.hedef,
                beklenen_sha256=ortak.LOCO_ARSIV_SHA256,
                beklenen_boyut=ortak.LOCO_ARSIV_BOYUTU,
            )
        elif secenekler.komut == "hazirla":
            hazirla(
                secenekler.kaynak,
                secenekler.hedef,
                en_uzun_kenar=secenekler.en_uzun_kenar,
                sinir=secenekler.sinir,
                forklift_tekrar=secenekler.forklift_tekrar,
            )
        else:
            adres, ozet = ortak.RESMI_AGIRLIKLAR[secenekler.boy]
            hedef = secenekler.hedef
            if hedef.suffix != ".pth":  # klasör verildi: yayındaki adla içine
                hedef = hedef / adres.rsplit("/", 1)[-1]
            dosya_indir(adres, hedef, ozet)
    except VeriHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr, flush=True)
        return hata.cikis_kodu
    return 0


if __name__ == "__main__":
    sys.exit(main())

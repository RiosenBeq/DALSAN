"""Yüklenen fotoğrafta tanıtılmış nesneyi arama.

CANLI KAMERAYI ETKİLEMEZ. Buraya yalnızca kullanıcının eliyle yüklediği
fotoğraf gelir; kamera akışı, kural motoru ve olay kayıtları bu koddan
habersizdir. Ekranda da aynı cümle yazar (web/nesne_rotalari.py).

NASIL ÇALIŞIR — "kayan pencere":
Yüklenen fotoğraf, farklı büyüklüklerde kare pencerelerle baştan sona gezilir;
her pencere kütüphanedeki parmak izleriyle karşılaştırılır. Eşiği geçen
pencereler işaretlenir, üst üste binenler tekleştirilir.

NEDEN TESPİT MODELİNE BAĞLANMADI: sistemin modeli yalnızca insan / forklift /
tır tanır. Kullanıcının tanıttığı nesne (pano, tüp, kalıp, kasa…) bu üç sınıfın
hiçbiri değildir; modelin bulduğu kutulara bakan bir arama, kullanıcının
tanıttığı nesnelerin çoğunu HİÇ göremezdi. Kayan pencere modelden bağımsızdır:
model henüz inmemişken bile bu sayfa çalışır.

HIZ: pahalı adım desen (ORB) çıkarımıdır. Her pencere önce UCUZ renk
karşılaştırmasından geçer; `kutuphane.renk_alt_siniri()` eşiği aşması matematiksel
olarak imkânsız pencereleri eler. Eleme sonucu değiştirmez, yalnız hızlandırır.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from app.nesneler.kutuphane import (
    Nesne,
    Parmakizi,
    desen_izi,
    en_iyi_eslesme_izinden,
    renk_alt_siniri,
    renk_benzerligi,
    renk_izi,
    standart_boy,
)

# Yüklenen fotoğraf önce bu uzun kenara küçültülür: 12 MP telefon fotoğrafında
# pencere sayısı ve süre boşuna katlanır, isabet artmaz.
EN_BUYUK_KENAR = 900
# Pencere kenarı: fotoğrafın KISA kenarının bu oranları kadar. Geniş aralık,
# "nesne karenin tamamı" ile "nesne uzakta küçük" durumlarının ikisini de tutar.
_PENCERE_ORANLARI = (1.0, 0.75, 0.55, 0.40, 0.30, 0.22, 0.16)
# Pencereler kenarın bu oranı kadar kaydırılır (0,4 = %60 örtüşme): nesne iki
# pencerenin arasına düşüp kaçmasın.
_ADIM_ORANI = 0.40
# Kenarı bundan küçük pencere üretilmez — 32 pikselin altında ne renk ne desen
# güvenilirdir.
_EN_KUCUK_PENCERE_PX = 32
# Üst sınırlar: en kötü durumda bile bir fotoğrafın taraması birkaç saniyede biter.
EN_COK_PENCERE = 420  # renk elemesine giren pencere
EN_COK_DESEN = 200  # desen (ORB) hesabına giren pencere
EN_COK_BULGU = 12  # tek fotoğrafta raporlanan en çok işaret
# İki işaret bu orandan fazla örtüşüyorsa aynı nesnedir; yüksek skorlu kalır.
_ORTUSME_SINIRI = 0.30
# Tarama çıktıları klasöründe tutulan en yeni dosya sayısı
SAKLANAN_TARAMA = 60

# İşaretli sonuç görüntüsündeki renkler (BGR) — canlı görüntüdeki sınıf
# renklerinden bilerek FARKLI (mor): bu kutular kural ihlali değildir.
_KUTU_RENGI = (200, 90, 160)
_KUTU_KALINLIGI = 3


@dataclass
class Bulgu:
    """Fotoğrafta işaretlenen tek bir eşleşme."""

    sira: int  # görüntüdeki numara ile tablodaki satırı bağlar
    nesne_adi: str
    skor: float  # 0-1
    kutu: tuple[int, int, int, int]

    @property
    def yuzde(self) -> int:
        return round(self.skor * 100)


@dataclass
class TaramaSonucu:
    dosya_adi: str
    sonuc_gorseli: str = ""  # tarama klasörü altındaki dosya adı ("" = yazılamadı)
    bulgular: list[Bulgu] = field(default_factory=list)
    en_yuksek_skor: float = 0.0
    uyari: str = ""

    @property
    def en_yuksek_yuzde(self) -> int:
        return round(self.en_yuksek_skor * 100)


def tara(
    gorsel: np.ndarray,
    dosya_adi: str,
    nesneler: list[Nesne],
    hedef_klasor: Path,
    esik: float,
) -> TaramaSonucu:
    """Tek bir fotoğrafı tarar ve işaretlenmiş sonucu diske yazar."""
    kucuk = _olcekle(gorsel)
    if not nesneler:
        return TaramaSonucu(
            dosya_adi=dosya_adi,
            sonuc_gorseli=_gorseli_yaz(kucuk, hedef_klasor),
            uyari=(
                "Kütüphanede tanıtılmış nesne yok. Önce yukarıdan bir nesne ekleyip "
                "farklı açılardan 3-8 fotoğrafını yükleyin."
            ),
        )

    bulgular, en_yuksek = _pencereleri_tara(kucuk, nesneler, esik)
    isaretli = _isaretle(kucuk, bulgular)

    if bulgular:
        uyari = ""
    elif en_yuksek > 0:
        uyari = (
            f"Eşleşme bulunamadı. Bu fotoğraftaki en yüksek benzerlik %{round(en_yuksek * 100)}, "
            f"kabul çıtası ise %{round(esik * 100)}. Nesnenin bu açıdan ve bu ışıkta bir "
            "fotoğrafını kütüphaneye eklemeyi deneyin."
        )
    else:
        uyari = "Eşleşme bulunamadı; bu fotoğrafta kütüphanedeki nesnelere benzeyen bir yer yok."

    return TaramaSonucu(
        dosya_adi=dosya_adi,
        sonuc_gorseli=_gorseli_yaz(isaretli, hedef_klasor),
        bulgular=bulgular,
        en_yuksek_skor=en_yuksek,
        uyari=uyari,
    )


# --------------------------------------------------------------- iç adımlar


def _olcekle(gorsel: np.ndarray) -> np.ndarray:
    """Uzun kenarı EN_BUYUK_KENAR'a indirir. Küçük fotoğraf BÜYÜTÜLMEZ."""
    yuksek, genis = gorsel.shape[:2]
    en_uzun = max(yuksek, genis)
    if en_uzun <= EN_BUYUK_KENAR:
        return gorsel
    oran = EN_BUYUK_KENAR / en_uzun
    return cv2.resize(
        gorsel, (round(genis * oran), round(yuksek * oran)), interpolation=cv2.INTER_AREA
    )


def pencereler(genis: int, yuksek: int) -> list[tuple[int, int, int, int]]:
    """Taranacak kare pencerelerin (x1, y1, x2, y2) listesi.

    Sağ ve alt kenara ayrıca birer pencere hizalanır: adım tam bölmediğinde
    fotoğrafın kenarındaki nesne hiç taranmadan kalırdı.
    """
    kisa = min(genis, yuksek)
    kutular: list[tuple[int, int, int, int]] = []
    gorulen: set[tuple[int, int, int, int]] = set()
    for oran in _PENCERE_ORANLARI:
        kenar = min(round(kisa * oran), genis, yuksek)
        if kenar < _EN_KUCUK_PENCERE_PX:
            continue
        adim = max(_EN_KUCUK_PENCERE_PX // 2, round(kenar * _ADIM_ORANI))
        xler = sorted({*range(0, max(genis - kenar, 0) + 1, adim), max(genis - kenar, 0)})
        yler = sorted({*range(0, max(yuksek - kenar, 0) + 1, adim), max(yuksek - kenar, 0)})
        for y in yler:
            for x in xler:
                kutu = (x, y, x + kenar, y + kenar)
                if kutu not in gorulen:
                    gorulen.add(kutu)
                    kutular.append(kutu)
    return _seyrelt(kutular, EN_COK_PENCERE)


def _seyrelt(ogeler: list, en_cok: int) -> list:
    """Sayı sınırı aşılırsa eşit aralıkla seyreltir (rastgele DEĞİL, tekrarlanabilir)."""
    if len(ogeler) <= en_cok:
        return ogeler
    adim = len(ogeler) / en_cok
    return [ogeler[int(i * adim)] for i in range(en_cok)]


def _pencereleri_tara(
    gorsel: np.ndarray, nesneler: list[Nesne], esik: float
) -> tuple[list[Bulgu], float]:
    yuksek, genis = gorsel.shape[:2]
    renk_tabani = renk_alt_siniri(esik)
    referans_renkleri = [izi.renk for nesne in nesneler for izi in nesne.parmakizleri]

    # 1) UCUZ geçiş: her pencerenin yalnız renk izi
    adaylar: list[tuple[float, tuple[int, int, int, int], np.ndarray, np.ndarray]] = []
    for kutu in pencereler(genis, yuksek):
        x1, y1, x2, y2 = kutu
        kirpik = standart_boy(gorsel[y1:y2, x1:x2])
        renk = renk_izi(kirpik)
        en_iyi_renk = max((renk_benzerligi(renk, r) for r in referans_renkleri), default=0.0)
        if en_iyi_renk < renk_tabani:
            continue
        adaylar.append((en_iyi_renk, kutu, kirpik, renk))

    # 2) PAHALI geçiş: renkte en umutlu pencerelerde desen (ORB) hesabı
    adaylar.sort(key=lambda a: a[0], reverse=True)
    eslesmeler: list[tuple[float, tuple[int, int, int, int], str]] = []
    en_yuksek = 0.0
    for _, kutu, kirpik, renk in adaylar[:EN_COK_DESEN]:
        izi = Parmakizi(renk=renk, desen=desen_izi(kirpik))
        nesne, skor = en_iyi_eslesme_izinden(izi, nesneler, esik)
        en_yuksek = max(en_yuksek, skor)
        if nesne is not None:
            eslesmeler.append((skor, kutu, nesne.ad))

    return _tekle(eslesmeler), en_yuksek


def _tekle(eslesmeler: list[tuple[float, tuple[int, int, int, int], str]]) -> list[Bulgu]:
    """Üst üste binen işaretleri teker: en yüksek skorlu kutu kalır."""
    eslesmeler.sort(key=lambda e: e[0], reverse=True)
    secilenler: list[tuple[float, tuple[int, int, int, int], str]] = []
    for skor, kutu, ad in eslesmeler:
        if any(_ortusme(kutu, onceki) > _ORTUSME_SINIRI for _, onceki, _ in secilenler):
            continue
        secilenler.append((skor, kutu, ad))
        if len(secilenler) >= EN_COK_BULGU:
            break
    return [
        Bulgu(sira=sira, nesne_adi=ad, skor=round(skor, 3), kutu=kutu)
        for sira, (skor, kutu, ad) in enumerate(secilenler, start=1)
    ]


def _ortusme(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """İki kutunun kesişim / birleşim oranı (IoU)."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    kesisim = max(x2 - x1, 0) * max(y2 - y1, 0)
    if kesisim == 0:
        return 0.0
    alan_a = (a[2] - a[0]) * (a[3] - a[1])
    alan_b = (b[2] - b[0]) * (b[3] - b[1])
    return kesisim / (alan_a + alan_b - kesisim)


def _isaretle(gorsel: np.ndarray, bulgular: list[Bulgu]) -> np.ndarray:
    """Bulunan yerleri numaralı kutuyla işaretler.

    Kutunun ÜZERİNE nesne adı yazılmaz, yalnızca SIRA NUMARASI konur: OpenCV'nin
    yazı tipleri Türkçe harfleri (ç, ğ, ı, ş, ü) çizemez ve ad "Yang?n dolab?"
    diye görünürdü. Numaranın karşılığı görüntünün altındaki tabloda yazar.
    """
    isaretli = gorsel.copy()
    for bulgu in bulgular:
        x1, y1, x2, y2 = bulgu.kutu
        cv2.rectangle(isaretli, (x1, y1), (x2, y2), _KUTU_RENGI, _KUTU_KALINLIGI)
        etiket = str(bulgu.sira)
        (yazi_g, yazi_y), _ = cv2.getTextSize(etiket, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        kutu_ust = max(y1 - yazi_y - 10, 0)
        cv2.rectangle(
            isaretli, (x1, kutu_ust), (x1 + yazi_g + 14, kutu_ust + yazi_y + 10), _KUTU_RENGI, -1
        )
        cv2.putText(
            isaretli,
            etiket,
            (x1 + 7, kutu_ust + yazi_y + 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return isaretli


def _gorseli_yaz(gorsel: np.ndarray, klasor: Path) -> str:
    klasor.mkdir(parents=True, exist_ok=True)
    ad = f"tarama-{uuid.uuid4().hex[:10]}.jpg"
    if not cv2.imwrite(str(klasor / ad), gorsel, [cv2.IMWRITE_JPEG_QUALITY, 85]):
        return ""
    return ad


def eski_taramalari_temizle(klasor: Path, en_fazla: int = SAKLANAN_TARAMA) -> int:
    """Tarama çıktıları birikmesin: en yeni N tanesi kalır.

    Bu klasör bakım döngüsünün saklama politikasına GİRMEZ (kanıt fotoğrafı
    değildir); budaması burada, her taramanın sonunda yapılır.
    """
    if not klasor.is_dir():
        return 0
    dosyalar = sorted(klasor.glob("tarama-*.jpg"), key=lambda d: d.stat().st_mtime, reverse=True)
    silinen = 0
    for eski in dosyalar[en_fazla:]:
        try:
            eski.unlink()
            silinen += 1
        except OSError:
            # Dosya başka bir işlem tarafından açık tutuluyor olabilir (Windows);
            # bir sonraki taramada yeniden denenir.
            continue
    return silinen

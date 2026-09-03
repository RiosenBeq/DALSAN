"""Kıyas takımının görüntülerini ÇİZER — depoda ikili dosya tutulmaz.

Neden fotoğraf yerine çizim: fotoğraf koysaydık depo şişerdi, dosyalar
zamanla kaybolur ya da değişirdi ve ölçüm tekrarlanamaz olurdu. Buradaki her
görüntü TOHUMLU (seeded) üretilir: aynı tohum her makinede aynı pikselleri
verir, dolayısıyla bugün ölçülen sayı yarın da aynı yerden ölçülür.

Takımda üç zorluk kademesi ve iki tuzak vardır:
  yüksek desenli  → yazılı pano, logolu kutu, barkod (motorun rahat işi)
  orta desenli    → halkalı tüp, çizgili baret
  düz renkli      → desensiz bidon, baret, boru (motorun bilinen zayıf yanı)
  tuzak 1         → AYNI renk, FARKLI desen  (yanlış isim yazdırmaya çalışır)
  tuzak 2         → FARKLI renk, AYNI desen  (ikinci yanlış isim tuzağı)

Ayrıca kütüphanede HİÇ OLMAYAN nesneler ve boş arka planlar üretilir; bunlara
isim yazılması en ağır kusurdur (docs/00-PROJE-BAGLAMI.md: yanlış alarm güveni
bitirir).

Yazılar bilerek ASCII'dir: OpenCV'nin yazı tipleri ç/ğ/ı/ş/ü çizemez. Bu
harfler burada yalnızca birer desendir, kullanıcıya görünmez.
"""

from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

# Nesne tuvalinin kenarı (piksel). Sahneye yerleştirilirken ölçeklenir.
TUVAL = 200
# Çizim = (BGR görüntü, maske). Maske 255 olan pikseller nesnenin kendisidir;
# 0 olanlar sahnenin arka planıyla dolar. Maske olmasaydı her nesne kare bir
# yama gibi yapışır, arka plan değişimi ölçülemezdi.
Cizim = tuple[np.ndarray, np.ndarray]
Cizici = Callable[[], Cizim]

_YAZI = cv2.FONT_HERSHEY_DUPLEX
_KOYU = (25, 25, 25)

# DÜZ (desensiz) kütüphane nesnelerinin gövde renkleri (BGR). Tek yerde durur,
# çünkü aşağıdaki "aynı renkte yabancı nesne" çizimleri BU sabitleri okur:
# takımın "aynı renk" özelliği böylece bir rastlantı değil, yapısal olur ve
# biri değişirse öteki kendiliğinden onunla değişir
# (tests/test_nesne_kiyas_kapisi.py bunu ayrıca sınar).
MAVI_BIDON = (176, 108, 44)
BEYAZ_BARET = (236, 236, 232)
GRI_BORU = (146, 148, 150)
GRI_PANO = (152, 152, 150)


def _tuval(renk: tuple[int, int, int]) -> np.ndarray:
    return np.full((TUVAL, TUVAL, 3), renk, dtype=np.uint8)


def _bos_maske() -> np.ndarray:
    return np.zeros((TUVAL, TUVAL), dtype=np.uint8)


def _dolu_maske() -> np.ndarray:
    return np.full((TUVAL, TUVAL), 255, dtype=np.uint8)


def _silindir_golgesi(gorsel: np.ndarray, kutu: tuple[int, int, int, int], dikey: bool) -> None:
    """Silindir izlenimi: kenarlar koyu, orta parlak. Yerinde (in-place) uygular."""
    x1, y1, x2, y2 = kutu
    uzunluk = (x2 - x1) if dikey else (y2 - y1)
    if uzunluk <= 1:
        return
    profil = 0.70 + 0.30 * np.sin(np.linspace(0.3, np.pi - 0.3, uzunluk))
    carpan = profil[None, :, None] if dikey else profil[:, None, None]
    bolge = gorsel[y1:y2, x1:x2].astype(np.float32) * carpan
    gorsel[y1:y2, x1:x2] = np.clip(bolge, 0, 255).astype(np.uint8)


# --------------------------------------------------------- yüksek desenli


def yazili_pano() -> Cizim:
    """Sarı zeminli, yazılı uyarı panosu — motorun en rahat işi."""
    gorsel = _tuval((40, 190, 235))
    cv2.rectangle(gorsel, (7, 7), (192, 192), _KOYU, 5)
    cv2.putText(gorsel, "DIKKAT", (18, 62), _YAZI, 1.05, _KOYU, 2, cv2.LINE_AA)
    cv2.putText(gorsel, "YUKSEK", (22, 104), _YAZI, 0.9, _KOYU, 2, cv2.LINE_AA)
    cv2.putText(gorsel, "GERILIM", (16, 142), _YAZI, 0.9, _KOYU, 2, cv2.LINE_AA)
    cv2.putText(gorsel, "B-17", (66, 178), _YAZI, 0.7, _KOYU, 2, cv2.LINE_AA)
    return gorsel, _dolu_maske()


def logolu_kutu() -> Cizim:
    """Karton kutu: logo, bant ve etiketler."""
    gorsel = _tuval((88, 130, 178))
    cv2.rectangle(gorsel, (0, 96), (199, 122), (68, 104, 148), -1)
    cv2.circle(gorsel, (100, 56), 30, (238, 238, 238), -1)
    cv2.circle(gorsel, (100, 56), 30, _KOYU, 3)
    ucgen = np.array([[100, 36], [84, 72], [116, 72]], dtype=np.int32)
    cv2.fillPoly(gorsel, [ucgen], _KOYU)
    cv2.rectangle(gorsel, (24, 138), (96, 174), (238, 238, 238), -1)
    cv2.rectangle(gorsel, (24, 138), (96, 174), _KOYU, 2)
    cv2.putText(gorsel, "NG-4", (30, 164), _YAZI, 0.7, _KOYU, 2, cv2.LINE_AA)
    cv2.putText(gorsel, "12 KG", (110, 164), _YAZI, 0.6, (240, 240, 240), 2, cv2.LINE_AA)
    return gorsel, _dolu_maske()


def barkod_etiketi() -> Cizim:
    """Beyaz etiket üzerinde değişen kalınlıkta çubuklar — çok yüksek desen."""
    gorsel = _tuval((246, 246, 244))
    cv2.rectangle(gorsel, (4, 4), (195, 195), (170, 170, 170), 2)
    x, sira = 16, 0
    while x < 182:
        kalinlik = 3 + (sira * 7) % 9
        cv2.rectangle(gorsel, (x, 22), (min(x + kalinlik, 182), 138), (18, 18, 18), -1)
        x += kalinlik + 3 + (sira * 5) % 7
        sira += 1
    cv2.putText(gorsel, "8 690 341 2", (20, 176), _YAZI, 0.62, (18, 18, 18), 2, cv2.LINE_AA)
    return gorsel, _dolu_maske()


# ------------------------------------------------------------ orta desenli


def halkali_tup() -> Cizim:
    """Mavi/yeşil halkalı gaz tüpü — sahada BULUNAMAYAN nesnenin benzeri."""
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    govde = (56, 34, 146, 192)
    cv2.rectangle(gorsel, govde[:2], govde[2:], (150, 118, 34), -1)
    cv2.ellipse(gorsel, (101, 34), (45, 26), 0, 180, 360, (150, 118, 34), -1)
    for y in (70, 108, 146):
        cv2.rectangle(gorsel, (56, y), (146, y + 13), (92, 176, 96), -1)
    cv2.rectangle(gorsel, (88, 6), (114, 24), (150, 150, 155), -1)
    _silindir_golgesi(gorsel, (56, 8, 146, 192), dikey=True)
    cv2.rectangle(maske, govde[:2], govde[2:], 255, -1)
    cv2.ellipse(maske, (101, 34), (45, 26), 0, 180, 360, 255, -1)
    cv2.rectangle(maske, (88, 6), (114, 24), 255, -1)
    return gorsel, maske


def cizgili_baret() -> Cizim:
    """Sarı baret, üzerinde iki koyu şerit."""
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    cv2.ellipse(gorsel, (100, 138), (72, 66), 0, 180, 360, (52, 196, 240), -1)
    cv2.ellipse(gorsel, (100, 138), (94, 20), 0, 180, 360, (46, 176, 218), -1)
    cv2.rectangle(gorsel, (92, 74), (108, 138), (36, 130, 168), -1)
    cv2.rectangle(gorsel, (58, 96), (72, 138), (36, 130, 168), -1)
    cv2.rectangle(gorsel, (128, 96), (142, 138), (36, 130, 168), -1)
    cv2.ellipse(maske, (100, 138), (72, 66), 0, 180, 360, 255, -1)
    cv2.ellipse(maske, (100, 138), (94, 20), 0, 180, 360, 255, -1)
    return gorsel, maske


# ------------------------------------------------------------- düz renkli


def duz_bidon() -> Cizim:
    """Tek renk mavi bidon — üzerinde hiç yazı/desen yok."""
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    cv2.rectangle(gorsel, (46, 26), (154, 190), MAVI_BIDON, -1)
    cv2.rectangle(gorsel, (66, 12), (134, 28), (168, 100, 40), -1)
    _silindir_golgesi(gorsel, (46, 12, 154, 190), dikey=True)
    cv2.rectangle(maske, (46, 26), (154, 190), 255, -1)
    cv2.rectangle(maske, (66, 12), (134, 28), 255, -1)
    return gorsel, maske


def duz_baret() -> Cizim:
    """Düz beyaz baret — desensiz; motorun tutunacağı tek şey renk."""
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    cv2.ellipse(gorsel, (100, 140), (74, 68), 0, 180, 360, BEYAZ_BARET, -1)
    cv2.ellipse(gorsel, (100, 140), (96, 20), 0, 180, 360, (224, 224, 220), -1)
    _silindir_golgesi(gorsel, (26, 70, 174, 158), dikey=True)
    cv2.ellipse(maske, (100, 140), (74, 68), 0, 180, 360, 255, -1)
    cv2.ellipse(maske, (100, 140), (96, 20), 0, 180, 360, 255, -1)
    return gorsel, maske


def gri_boru() -> Cizim:
    """Yatay gri boru — düz, desensiz."""
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    cv2.rectangle(gorsel, (10, 70), (190, 132), GRI_BORU, -1)
    _silindir_golgesi(gorsel, (10, 70, 190, 132), dikey=False)
    cv2.rectangle(maske, (10, 70), (190, 132), 255, -1)
    return gorsel, maske


# ------------------------- tuzak 1: AYNI renk, FARKLI desen (yanlış isim)


def _gri_pano_zemini() -> np.ndarray:
    gorsel = _tuval(GRI_PANO)
    cv2.rectangle(gorsel, (6, 6), (193, 193), (112, 112, 110), 4)
    return gorsel


def gri_pano_kareli() -> Cizim:
    gorsel = _gri_pano_zemini()
    for k in range(30, 190, 32):
        cv2.line(gorsel, (k, 10), (k, 190), (98, 98, 96), 3)
        cv2.line(gorsel, (10, k), (190, k), (98, 98, 96), 3)
    return gorsel, _dolu_maske()


def gri_pano_capraz() -> Cizim:
    gorsel = _gri_pano_zemini()
    for k in range(-160, 200, 28):
        cv2.line(gorsel, (k, 10), (k + 180, 190), (98, 98, 96), 3)
    return gorsel, _dolu_maske()


# ----------------------- tuzak 2: FARKLI renk, AYNI desen (yanlış isim)


def _cizgili_kasa(zemin: tuple[int, int, int], cizgi: tuple[int, int, int]) -> Cizim:
    gorsel = _tuval(zemin)
    cv2.rectangle(gorsel, (8, 8), (191, 191), cizgi, 5)
    for k in range(24, 190, 26):
        cv2.line(gorsel, (k, 12), (k, 188), cizgi, 4)
    cv2.line(gorsel, (12, 66), (188, 66), cizgi, 4)
    cv2.line(gorsel, (12, 132), (188, 132), cizgi, 4)
    return gorsel, _dolu_maske()


def sari_cizgili_kasa() -> Cizim:
    return _cizgili_kasa((48, 198, 236), (30, 120, 150))


def yesil_cizgili_kasa() -> Cizim:
    return _cizgili_kasa((78, 168, 76), (34, 96, 40))


# ------------------------------------ kütüphanede OLMAYAN nesneler (negatif)


def yangin_sondurucu() -> Cizim:
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    cv2.rectangle(gorsel, (68, 44), (132, 190), (44, 44, 196), -1)
    cv2.rectangle(gorsel, (86, 18), (114, 46), (60, 60, 60), -1)
    cv2.rectangle(gorsel, (68, 96), (132, 118), (240, 240, 240), -1)
    _silindir_golgesi(gorsel, (68, 18, 132, 190), dikey=True)
    cv2.rectangle(maske, (68, 44), (132, 190), 255, -1)
    cv2.rectangle(maske, (86, 18), (114, 46), 255, -1)
    return gorsel, maske


def kablo_makarasi() -> Cizim:
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    cv2.circle(gorsel, (100, 100), 84, (150, 60, 130), -1)
    cv2.circle(gorsel, (100, 100), 30, (90, 34, 78), -1)
    for aci in range(0, 360, 45):
        uc = (
            int(100 + 80 * np.cos(np.radians(aci))),
            int(100 + 80 * np.sin(np.radians(aci))),
        )
        cv2.line(gorsel, (100, 100), uc, (90, 34, 78), 4)
    cv2.circle(maske, (100, 100), 84, 255, -1)
    return gorsel, maske


def trafik_konisi() -> Cizim:
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    koni = np.array([[100, 18], [156, 176], [44, 176]], dtype=np.int32)
    cv2.fillPoly(gorsel, [koni], (36, 116, 238))
    cv2.rectangle(gorsel, (56, 96), (144, 122), (245, 245, 245), -1)
    cv2.rectangle(gorsel, (30, 176), (170, 192), (36, 100, 210), -1)
    cv2.fillPoly(maske, [koni], 255)
    cv2.rectangle(maske, (30, 176), (170, 192), 255, -1)
    return gorsel, maske


def lastik_yigini() -> Cizim:
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    for merkez_y, yaricap in ((150, 74), (96, 66), (48, 56)):
        cv2.circle(gorsel, (100, merkez_y), yaricap, (38, 38, 40), -1)
        cv2.circle(gorsel, (100, merkez_y), yaricap // 2, (70, 70, 72), 3)
        cv2.circle(maske, (100, merkez_y), yaricap, 255, -1)
    return gorsel, maske


# ------------- kütüphanede OLMAYAN ama AYNI RENKTE düz nesneler (negatif)
#
# Takımın en önemli bölümü burasıdır ve sonradan eklenmiştir. Eski takımdaki
# yabancı nesnelerin HEPSİ kütüphanedekilerden başka renkteydi (kırmızı
# söndürücü, mor makara, turuncu koni, siyah lastik); dolayısıyla motorun
# "iki taraf da desensiz" dalı — kararı YALNIZ renge bırakan dal — hiç
# sınanmıyordu. Bağımsız doğrulayıcı gerçek ürün yolunda tam oradan girip
# kütüphanede olmayan düz mavi bir kasaya "Düz mavi bidon" adını yazdırdı.
#
# Buradaki her nesne, kütüphanedeki DÜZ bir nesneyle AYNI gövde rengini
# (yukarıdaki sabitler) taşır ama BAŞKA biçimdedir. Doğru cevap hepsinde
# aynıdır: "eşleşme yok".
#
# NEDEN GÖLGELİ ÇİZİLİYORLAR: tek renkle doldurulmuş kusursuz düz bir yama
# gerçekte yoktur ve motoru da kırmaz — histogramı tek bir göze toplanır,
# gölgeli bir referansa benzemez (ölçüldü: gölgesiz kasa 0,21, gölgeli kasa
# 0,52). Gerçek bir kasanın/örtünün üstünde ışık kayar. Gölge eklemek takımı
# KOLAYLAŞTIRMAZ, gerçeğe yaklaştırır — ve motorun deliğini görünür kılan da
# tam olarak budur.


def mavi_kasa() -> Cizim:
    """Bidonla AYNI mavi, ama kasa: dik kenarlı, köşeli."""
    gorsel = _tuval(MAVI_BIDON)
    cv2.rectangle(gorsel, (6, 6), (193, 193), (160, 96, 38), 5)
    _silindir_golgesi(gorsel, (0, 0, TUVAL, TUVAL), dikey=True)
    return gorsel, _dolu_maske()


def mavi_palet() -> Cizim:
    """Bidonla AYNI mavi plastik palet: geniş yatay tahtalar."""
    gorsel = _tuval(MAVI_BIDON)
    for y in range(18, TUVAL - 10, 44):
        cv2.rectangle(gorsel, (8, y), (191, y + 30), (166, 100, 40), -1)
    _silindir_golgesi(gorsel, (0, 0, TUVAL, TUVAL), dikey=False)
    return gorsel, _dolu_maske()


def mavi_ortu() -> Cizim:
    """Bidonla AYNI mavi branda: kıvrımlardan gelen yumuşak gölge dalgaları."""
    gorsel = _tuval(MAVI_BIDON).astype(np.float32)
    dalga = 0.78 + 0.22 * np.sin(np.linspace(0, 3 * np.pi, TUVAL))
    gorsel = np.clip(gorsel * dalga[None, :, None], 0, 255).astype(np.uint8)
    return gorsel, _dolu_maske()


def mavi_duvar_parcasi() -> Cizim:
    """Bidonla AYNI maviye boyanmış duvar/pano parçası — hiç biçimi yok."""
    gorsel = _tuval(MAVI_BIDON)
    _silindir_golgesi(gorsel, (0, 0, TUVAL, TUVAL), dikey=False)
    return gorsel, _dolu_maske()


def gri_sac_levha() -> Cizim:
    """Gri boruyla AYNI gri, ama düz sac levha (silindir değil, yüzey)."""
    gorsel = _tuval(GRI_BORU)
    _silindir_golgesi(gorsel, (0, 0, TUVAL, TUVAL), dikey=False)
    return gorsel, _dolu_maske()


def gri_beton_blok() -> Cizim:
    """Gri panolarla AYNI gri beton blok — üstünde ızgara/çapraz deseni YOK."""
    gorsel = _tuval(GRI_PANO)
    _silindir_golgesi(gorsel, (0, 0, TUVAL, TUVAL), dikey=True)
    return gorsel, _dolu_maske()


def beyaz_cuval() -> Cizim:
    """Beyaz baretle AYNI beyaz, ama çuval: yuvarlak, şişkin."""
    gorsel = _tuval((250, 250, 250))
    maske = _bos_maske()
    cv2.ellipse(gorsel, (100, 106), (82, 90), 0, 0, 360, BEYAZ_BARET, -1)
    cv2.ellipse(maske, (100, 106), (82, 90), 0, 0, 360, 255, -1)
    _silindir_golgesi(gorsel, (18, 16, 182, 196), dikey=True)
    return gorsel, maske


def beyaz_levha() -> Cizim:
    """Beyaz baretle AYNI beyaz, düz levha — desensiz dikdörtgen."""
    gorsel = _tuval(BEYAZ_BARET)
    _silindir_golgesi(gorsel, (0, 0, TUVAL, TUVAL), dikey=True)
    return gorsel, _dolu_maske()


# --------------------------------------------------------------- arka plan

ARKA_PLAN_TURLERI = ("beton", "cim", "izgara", "palet", "koyu", "tugla")

# Zeminlerin taban renkleri (BGR)
_ZEMIN_RENKLERI = {
    "beton": (168, 170, 172),
    "cim": (46, 132, 62),
    "izgara": (120, 124, 128),
    "palet": (96, 138, 176),
    "koyu": (52, 54, 58),
    "tugla": (78, 92, 142),
}


def arka_plan(tur: str, genis: int, yuksek: int, tohum: int) -> np.ndarray:
    """Fabrikada rastlanan zeminlerin kabası. Aynı tohum → aynı zemin.

    ÖNEMLİ: aynı türün iki karesi BİRBİRİNİN AYNI OLMAMALIDIR. Gerçek bir
    beton zeminde ışık bir köşeden gelir, yağ lekesi vardır, çizik vardır;
    duvar kâğıdı gibi tekrar etmez. Kusursuz tekrar eden bir zemin ölçümü
    bozardı: iki ayrı pencere birbirine tıpatıp benzer, motor da "aynı yer"
    demek zorunda kalırdı. Bu yüzden her karede aydınlatma yönü, leke yerleri
    ve çizgi aralıkları tohuma göre değişir.
    """
    rastgele = np.random.default_rng(tohum)
    taban = _ZEMIN_RENKLERI.get(tur, _ZEMIN_RENKLERI["beton"])
    zemin = np.full((yuksek, genis, 3), taban, dtype=np.uint8)
    koyu = tuple(max(int(kanal) - 26, 0) for kanal in taban)

    if tur in ("beton", "cim", "koyu"):
        _benek(
            zemin, rastgele, int(rastgele.integers(180, 340)), koyu, int(rastgele.integers(3, 6))
        )
    elif tur == "izgara":
        aralik = int(rastgele.integers(20, 34))
        kaydir = int(rastgele.integers(0, aralik))
        for k in range(-kaydir, max(genis, yuksek) + aralik, aralik):
            cv2.line(zemin, (k, 0), (k, yuksek), koyu, 3)
            cv2.line(zemin, (0, k), (genis, k), koyu, 3)
    elif tur == "palet":
        aralik = int(rastgele.integers(28, 42))
        kaydir = int(rastgele.integers(0, aralik))
        for k in range(-kaydir, yuksek + aralik, aralik):
            cv2.rectangle(zemin, (0, k), (genis, k + aralik * 2 // 3), koyu, -1)
    else:  # tugla
        yukseklik = int(rastgele.integers(22, 34))
        uzunluk = int(rastgele.integers(48, 72))
        for satir, y in enumerate(range(-yukseklik, yuksek + yukseklik, yukseklik)):
            cv2.line(zemin, (0, y), (genis, y), koyu, 3)
            kaydir = 0 if satir % 2 == 0 else uzunluk // 2
            for x in range(kaydir, genis + uzunluk, uzunluk):
                cv2.line(zemin, (x, y), (x, y + yukseklik), koyu, 3)

    _lekeler(zemin, rastgele, taban)
    _cizikler(zemin, rastgele, koyu)
    zemin = _isik_gradyani(zemin, rastgele)
    gurultu = rastgele.normal(0, 4, zemin.shape)
    return np.clip(zemin.astype(np.float32) + gurultu, 0, 255).astype(np.uint8)


def _benek(zemin, rastgele, adet, renk, boy) -> None:
    yuksek, genis = zemin.shape[:2]
    for _ in range(adet):
        x = int(rastgele.integers(0, genis))
        y = int(rastgele.integers(0, yuksek))
        cv2.circle(zemin, (x, y), boy, renk, -1)


def _lekeler(zemin, rastgele, taban) -> None:
    """Büyük lekeler: yağ izi, boya, aşınma. Her karede başka yerdedir."""
    yuksek, genis = zemin.shape[:2]
    for _ in range(int(rastgele.integers(3, 7))):
        merkez = (int(rastgele.integers(0, genis)), int(rastgele.integers(0, yuksek)))
        eksen = (int(rastgele.integers(30, 90)), int(rastgele.integers(20, 70)))
        kayma = int(rastgele.integers(-22, 23))
        renk = tuple(int(np.clip(kanal + kayma, 0, 255)) for kanal in taban)
        cv2.ellipse(zemin, merkez, eksen, float(rastgele.integers(0, 180)), 0, 360, renk, -1)


def _cizikler(zemin, rastgele, renk) -> None:
    yuksek, genis = zemin.shape[:2]
    for _ in range(int(rastgele.integers(4, 10))):
        bas = (int(rastgele.integers(0, genis)), int(rastgele.integers(0, yuksek)))
        son = (bas[0] + int(rastgele.integers(-70, 71)), bas[1] + int(rastgele.integers(-50, 51)))
        cv2.line(zemin, bas, son, renk, int(rastgele.integers(1, 3)))


def _isik_gradyani(zemin: np.ndarray, rastgele) -> np.ndarray:
    """Işık bir yönden gelir: karenin bir ucu parlak, öteki ucu loştur."""
    yuksek, genis = zemin.shape[:2]
    yon = float(rastgele.uniform(0, 2 * np.pi))
    siddet = float(rastgele.uniform(0.10, 0.28))
    y_ekseni, x_ekseni = np.mgrid[0:yuksek, 0:genis].astype(np.float32)
    duzlem = (x_ekseni / genis) * np.cos(yon) + (y_ekseni / yuksek) * np.sin(yon)
    carpan = 1.0 + siddet * (duzlem - duzlem.mean()) * 2.0
    return np.clip(zemin.astype(np.float32) * carpan[..., None], 0, 255).astype(np.uint8)


# ------------------------------------------------- GERÇEKTEN desensiz zemin

# Yukarıdaki `arka_plan` zeminleri "boş" olsa da DESENSİZ değildir: benek,
# çizik, leke ve ızgara çizgileri ORB'ye tutunacak yer bırakır. Ölçüldü — bu
# zeminlerin tam karesinde 14-111 anahtar nokta çıkıyor, yani motorun
# "iki taraf da desensiz" dalına HİÇ girmiyorlar. Altı boş zemin sorgusu bu
# yüzden motorun en zayıf dalını sınamıyordu.
#
# Aşağıdakiler o boşluğu kapatır: bulanık, karanlık ya da tek renge boyanmış
# yüzeyler. Ölçüldü — taranan 420 pencerenin 420'sinde de ORB nokta sayısı
# SIFIRDIR, yani `kutuphane.EN_AZ_ANAHTAR_NOKTA`nın altındadır ve düz-düz dalı
# gerçekten çalışır. Bu ölçüm rapora da basılır (`__main__._desensiz_kaniti`)
# ve kalite kapısı bunu her koşuda yeniden doğrular; yoksa takım yine kör olur.
#
# Üçü bilerek kütüphanedeki DÜZ nesnelerin renginde boyanmıştır: "aynı renk +
# hiç desen" en tehlikeli birleşimdir.
DESENSIZ_ZEMIN_TURLERI = (
    "duz-boya",
    "karanlik",
    "bulanik-beton",
    "duz-mavi",
    "duz-gri",
    "duz-beyaz",
)

_DESENSIZ_ZEMIN_RENKLERI = {
    "duz-boya": (150, 146, 140),  # boyalı fabrika duvarı
    "karanlik": (34, 34, 36),  # ışıksız köşe
    "bulanik-beton": (168, 170, 172),  # odaktan çıkmış beton
    "duz-mavi": MAVI_BIDON,  # bidonla aynı mavi
    "duz-gri": GRI_BORU,  # boruyla aynı gri
    "duz-beyaz": BEYAZ_BARET,  # baretle aynı beyaz
}

# Desenin gerçekten silinmesi için gereken bulanıklık. Bunun altında JPEG'in
# 8x8 blok izleri bile ORB'ye tutunacak köşe verebiliyor.
_DESENSIZ_BULANIKLIK = 11
_DESENSIZ_GURULTU = 1.2
_DESENSIZ_ISIK_EGIMI = 0.06


def desensiz_zemin(tur: str, genis: int, yuksek: int, tohum: int) -> np.ndarray:
    """Tutunacak deseni OLMAYAN bir zemin karesi.

    `arka_plan`dan farkı: benek, çizik ve leke YOKTUR; yalnız çok hafif bir
    ışık eğimi ve gürültü kalır, sonra da bulanıklaştırılır. Işık eğimi
    bırakılır çünkü kusursuz tek renk bir kare gerçekte yoktur ve renk
    histogramını yapay biçimde tek bir göze toplardı.
    """
    rastgele = np.random.default_rng(tohum)
    taban = _DESENSIZ_ZEMIN_RENKLERI[tur]
    zemin = np.full((yuksek, genis, 3), taban, dtype=np.float32)
    yon = float(rastgele.uniform(0, 2 * np.pi))
    y_ekseni, x_ekseni = np.mgrid[0:yuksek, 0:genis].astype(np.float32)
    duzlem = (x_ekseni / genis) * np.cos(yon) + (y_ekseni / yuksek) * np.sin(yon)
    zemin *= (1.0 + _DESENSIZ_ISIK_EGIMI * (duzlem - duzlem.mean()) * 2.0)[..., None]
    zemin += rastgele.normal(0, _DESENSIZ_GURULTU, zemin.shape)
    kare = np.clip(zemin, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(kare, (_DESENSIZ_BULANIKLIK, _DESENSIZ_BULANIKLIK), 0)


# ------------------------------------------------------- bozma (distortion)


def donustur(gorsel: np.ndarray, maske: np.ndarray, derece: float, egim: float) -> Cizim:
    """Döndürme + perspektif: nesneye başka açıdan bakmanın karşılığı."""
    yuksek, genis = gorsel.shape[:2]
    kaynak = np.float32([[0, 0], [genis, 0], [genis, yuksek], [0, yuksek]])
    kayma = egim * genis
    hedef = np.float32(
        [[kayma, 0], [genis - kayma * 0.5, kayma * 0.4], [genis, yuksek], [kayma * 0.4, yuksek]]
    )
    perspektif = cv2.getPerspectiveTransform(kaynak, hedef)
    donme = cv2.getRotationMatrix2D((genis / 2, yuksek / 2), derece, 1.0)
    donme_3x3 = np.vstack([donme, [0, 0, 1]]).astype(np.float32)
    matris = donme_3x3 @ perspektif
    yeni = cv2.warpPerspective(gorsel, matris, (genis, yuksek), borderValue=(255, 255, 255))
    yeni_maske = cv2.warpPerspective(maske, matris, (genis, yuksek), borderValue=0)
    return yeni, yeni_maske


def olcekle(gorsel: np.ndarray, maske: np.ndarray, kenar: int) -> Cizim:
    yeni = cv2.resize(gorsel, (kenar, kenar), interpolation=cv2.INTER_AREA)
    yeni_maske = cv2.resize(maske, (kenar, kenar), interpolation=cv2.INTER_NEAREST)
    return yeni, yeni_maske


def yerlestir(zemin: np.ndarray, gorsel: np.ndarray, maske: np.ndarray, x: int, y: int) -> None:
    """Nesneyi sahnenin (x, y) noktasına maskesiyle yapıştırır (yerinde)."""
    yuksek, genis = gorsel.shape[:2]
    bolge = zemin[y : y + yuksek, x : x + genis]
    secim = maske[..., None] > 127
    zemin[y : y + yuksek, x : x + genis] = np.where(secim, gorsel, bolge)


def isik(gorsel: np.ndarray, carpan: float, ekle: float) -> np.ndarray:
    """Aydınlatma değişimi: fabrika ışığı saatten saate aynı değildir."""
    return cv2.convertScaleAbs(gorsel, alpha=carpan, beta=ekle)


def bulanik(gorsel: np.ndarray, cekirdek: int) -> np.ndarray:
    return cv2.GaussianBlur(gorsel, (cekirdek, cekirdek), 0)


def jpeg_bozulmasi(gorsel: np.ndarray, kalite: int) -> np.ndarray:
    """Telefondan/kameradan gelen sıkıştırma izleri."""
    _, veri = cv2.imencode(".jpg", gorsel, [cv2.IMWRITE_JPEG_QUALITY, kalite])
    return cv2.imdecode(veri, cv2.IMREAD_COLOR)


def gurultu_ekle(gorsel: np.ndarray, siddet: float, tohum: int) -> np.ndarray:
    rastgele = np.random.default_rng(tohum)
    bozuk = gorsel.astype(np.float32) + rastgele.normal(0, siddet, gorsel.shape)
    return np.clip(bozuk, 0, 255).astype(np.uint8)


def ort(gorsel: np.ndarray, kutu: tuple[int, int, int, int], renk: tuple[int, int, int]) -> None:
    """Nesnenin bir bölümünü kapatır: önünden forklift geçmiş gibi (yerinde)."""
    cv2.rectangle(gorsel, kutu[:2], kutu[2:], renk, -1)

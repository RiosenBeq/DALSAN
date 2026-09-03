"""Motoru kullanıcının diline çevirir: "benzerlik %33, çıta %42" değil,
"bu nesne zor tanınır, şunu yapın".

Burada üç soru cevaplanır:

1. **Bu nesne ne kadar tanınabilir?** (`nesne_teshisi`) — kullanıcı fotoğrafları
   yükler yüklemez söylenir. Yargı UYDURMA DEĞİLDİR: nesnenin KENDİ
   fotoğraflarından ölçülür ve aşağıdaki sayılara dayanır.
2. **Kaç fotoğraf yeter?** (`fotograf_notu`) — ölçülmüş bir sayıdır, yuvarlanmış
   bir tavsiye değil; ölçümün NEREYE KADAR yapıldığı da söylenir.
3. **"Eşleşme yok" çıktıysa ne yapmalı?** (`tarama_eylemi`) — yüzde göstermek
   yetmez; yüzdenin yanına TEK CÜMLELİK bir eylem konur.

--------------------------------------------------------------------- ÖLÇÜM

Bütün sınırlar `tests/nesne_kiyas` tam takımıyla (12 nesne × 4 referans
fotoğraf, 264 sorgu) elde ölçülmüştür. Ölçüm şunu gösterdi ve tasarım buna
göre kuruldu:

  ANAHTAR NOKTA SAYISI TEK BAŞINA HİÇBİR ŞEY SÖYLEMİYOR. "Gri pano A"nın
  197 anahtar noktası var ve 17 sorgunun HİÇBİRİNDE bulunamadı; "Logolu
  malzeme kutusu"nun 181 noktası var ve 17 sorgunun 4'ünde bulundu. Ayırt eden
  şey nokta sayısı değil, nesnenin kendi fotoğraflarının BİRBİRİNİ TANIYIP
  TANIMADIĞI.

Nesne başına ölçülen sayılar (çıta 0,24; her nesne 17 sorgu):

  nesne                     nokta  tutarlılık   bulundu   işaret yerinde
  Logolu malzeme kutusu       181       0,624      4/17         4
  Barkod etiketi              185       0,623      2/17         2
  Uyarı panosu (yazılı)       211       0,591      2/17         2
  Gri pano B (çapraz)           0       0,111      0/17         0
  Düz mavi bidon                7       0,062      0/17         0
  Çizgili baret                40       0,055      0/17         0
  Halkalı gaz tüpü             17       0,050      0/17         0
  Gri boru                     28       0,024      0/17         0
  Düz beyaz baret              31       0,023      0/17         0
  Sarı çizgili kasa           165       0,015      0/17         0
  Yeşil çizgili kasa          155       0,013      0/17         0
  Gri pano A (kareli)         197       0,009      0/17         0

Bu tablodan çıkan ÜÇ KOVA (aşağıdaki sınırlar bunları ayırır):

  KOLAY  (3 nesne)  → 8/51 bulundu (%15,7), 8/51 işaret nesnenin üstünde (%15,7)
  DÜZ    (2 nesne)  → 0/34 bulundu (%0),    0/34 işaret nesnenin üstünde (%0)
  ZOR    (7 nesne)  → 0/119 bulundu (%0),   0/119 işaret nesnenin üstünde (%0)

TABLO 2026-09'DA YENİDEN ÖLÇÜLDÜ ve okunuşu değişti. Eskiden DÜZ kova %35,7
buluyordu ama bulduklarının yalnız %7,1'inde işaret gerçekten nesnenin
üstündeydi — sistem doğru adı sahnenin başka bir köşesindeki aynı renkli
yamaya yazıyordu. Aynı kapıdan kütüphanede HİÇ OLMAYAN nesnelere de isim
yazılıyordu. "Renk taşımaz" kuralı o kapıyı kapattı: düz ve zor kovalar
sıfırlandı, kolay kova %69'dan %15,7'ye düştü, ama bulunan her nesnede işaret
artık gerçekten nesnenin üstünde (%100; eskiden %62).

DÜZ ile ZOR bugün aynı sayıyı veriyor; yine de ayrı kovalardır, çünkü ayıran
şey isabet değil ÖNERİDİR: düz nesnede kullanıcının yapabileceği bir şey
yoktur, zor nesnede daha iyi fotoğraf çekmek işe yarayabilir.

DÖRDÜNCÜ BİR KOVA DENENDİ VE VAZGEÇİLDİ: "orta" adında bir ara kademe
kurulduğunda o kova ZOR kovasından DAHA KÖTÜ çıkıyordu (%10,7'ye karşı %14,3).
Sıralaması bozuk bir ölçek, kullanıcıya yalan söyler; üç kovada kalındı.

Bu dosya `rules/` altında DEĞİLDİR ve olamaz: cv2 kullanır (CLAUDE.md §6).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.nesneler.kutuphane import (
    DESEN_TABAN_NOKTA,
    EN_AZ_ANAHTAR_NOKTA,
    VARSAYILAN_ESIK,
    Parmakizi,
    benzerlik,
    nokta_sayisi,
)

# --------------------------------------------------------------- sınırlar
#
# TUTARLILIK SINIRI — nesnenin kendi fotoğrafları birbirini bu kadar tanıyorsa
# "kolay tanınır" denir. YENİDEN ÖLÇÜLDÜ (2026-09, "renk taşımaz" kuralından
# sonra, 12 nesne): üç kolay nesne 0,591 / 0,623 / 0,624; dördüncü sıradaki
# nesne 0,111. Aradaki boşluk eskisinden çok daha geniştir (eskiden 0,591'e
# karşı 0,515), çünkü kararı renge kalan karşılaştırmalar artık düşük skor
# alıyor. Sınır boşluğun ortasına değil, ALTTAN paylı konuldu: bir nesneyi
# yanlışlıkla "kolay" ilan etmek, "zor" ilan etmekten daha kötüdür.
_TUTARLILIK_KOLAY = 0.45
# Bu iki sınır ölçüm sabiti DEĞİL, motorun kendi dallanma noktalarıdır:
#   nokta < EN_AZ_ANAHTAR_NOKTA  → motor nesneyi "desensiz" sayar, yalnız renge bakar
#   nokta < DESEN_TABAN_NOKTA    → desen skoru tam ağırlığına ULAŞAMAZ (payda tabanı)
# Teşhis onları buradan okur; motor değişirse teşhis de kendiliğinden değişir.

# NETLİK SINIRI — yüklenen fotoğrafın Laplace değişintisi (AYRINTI ölçüsü) bunun
# altındaysa "bulanık, karanlık ya da çok düşük kontrastlı" denir; üçü de bu
# ölçüyü düşürür ve üçünün de cevabı aynıdır (daha net, daha aydınlık kare).
# ÖLÇÜLDÜ (194 sorgu): bilerek bulanıklaştırılmış
# 28 sorgunun 26'sı bu sınırın altında kalıyor, buna karşılık bulanık OLMAYAN
# 166 sorgunun HİÇBİRİ altında değil (en düşüğü 57). Kütüphaneye yüklenen
# referans fotoğrafların en düşüğü ise 147 — yani net bir fotoğrafa yanlışlıkla
# "bulanık" denmiyor. Yanlış suçlama, kaçırmaktan kötüdür; sınır o yüzden
# ölçülen boşluğun bulanık tarafına yakın duruyor.
_NETLIK_SINIRI = 55.0
# "Kıl payı kaldı" sınırı: en yüksek benzerlik, çıtanın bu oranını geçtiyse
# eşleşme YAKINDI demektir ve doğru eylem "bu açıdan bir fotoğraf ekleyin"dir.
# Ölçüldü: kütüphanede olmayan nesneler sorulduğunda en yüksek yabancı skor
# ortalaması 0,13'tür; varsayılan çıtanın (0,24) 0,75'i 0,18 eder, yani
# yabancıların ortalaması bu sınırın ALTINDA kalır — "kıl payı" cümlesi
# kütüphanede hiç olmayan bir nesne için boşuna çıkmaz.
_YAKIN_PAYI = 0.75

# Ölçümden çıkan gerçek sayılar; ekranda da bu sayılar yazar (uydurma yok).
# İkisi de O KOVADAKİ BÜTÜN sorguların yüzdesidir: (bulundu, işaret nesnenin
# üstündeydi). YENİDEN ÖLÇÜLDÜ (2026-09, tam takım, 204 pozitif sorgu, çıta
# 0,24): "renk taşımaz" kuralı düz ve zor kovalarını SIFIRA indirdi; eski
# değerleri (36 ve 14) yalnız renge dayanan eşleşmelerdi ve aynı kapıdan
# kütüphanede olmayan nesnelere de isim yazılıyordu. Kolay kovada bulunan
# 8 sorgunun 8'inde işaret gerçekten nesnenin üstünde — eskiden bu oran çok
# daha düşüktü (bulunan 61 sorgunun 38'i).
_KOVA_ISABETI = {"kolay": (16, 16), "duz": (0, 0), "zor": (0, 0)}


@dataclass(frozen=True)
class NesneTeshisi:
    """Bir nesnenin "ne kadar tanınabilir" olduğunun ölçülmüş karnesi."""

    seviye: str  # "kolay" | "duz" | "zor" | "tek"
    rozet: str  # ekrandaki renk sınıfı: yesil | sari | kirmizi | gri
    baslik: str  # "Kolay tanınır"
    aciklama: str  # neden böyle — tek cümle
    oneri: str  # ne yapmalı — tek cümle
    fotograf_sayisi: int
    nokta: int  # anahtar nokta sayısının ortancası
    tutarlilik: float  # 0-1

    @property
    def tutarlilik_yuzde(self) -> int:
        return round(self.tutarlilik * 100)

    @property
    def bulunma_yuzdesi(self) -> int | None:
        """Ölçümde bu kovadaki nesnelerin kaçta kaçı bulunmuştu? (yüzde)"""
        kova = _KOVA_ISABETI.get(self.seviye)
        return None if kova is None else kova[0]

    @property
    def yerinde_yuzdesi(self) -> int | None:
        """Bu kovadaki sorguların kaçında işaret nesnenin üstündeydi? (yüzde)

        Payda `bulunma_yuzdesi` ile AYNIDIR (kovadaki bütün sorgular), çünkü
        ekrandaki cümle ikisini aynı paydaya bağlar: "bu düzeydeki nesnelerin
        %A'sı bulundu ve %B'sinde işaret gerçekten nesnenin üstündeydi".
        """
        kova = _KOVA_ISABETI.get(self.seviye)
        return None if kova is None else kova[1]


# ===================================================== 1) nesne teşhisi


def olcumler(parmakizleri: list[Parmakizi]) -> tuple[int, float]:
    """(anahtar nokta ortancası, tutarlılık) — teşhisin dayandığı iki sayı.

    TUTARLILIK: her fotoğrafın DİĞER fotoğraflara en iyi benzerliğinin
    ortalaması. Ortalama değil de "en iyi" alınır çünkü motor da öyle karar
    verir (`en_iyi_eslesme_izinden`: en iyi eşleşen açı kazanır). Tek fotoğraf
    varsa karşılaştıracak bir şey yoktur; 0 döner ve teşhis "ölçülemedi" der.

    ORTANCA (ortalama değil): tek bir bulanık fotoğraf ortalamayı aşağı
    çekip nesneyi haksız yere "düz" ilan edebilirdi.
    """
    if not parmakizleri:
        return 0, 0.0
    noktalar = sorted(nokta_sayisi(izi) for izi in parmakizleri)
    orta = noktalar[len(noktalar) // 2]
    if len(parmakizleri) < 2:
        return orta, 0.0
    en_iyiler = [
        max(benzerlik(izi, digeri) for sira_b, digeri in enumerate(parmakizleri) if sira_b != sira)
        for sira, izi in enumerate(parmakizleri)
    ]
    return orta, float(np.mean(en_iyiler))


def nesne_teshisi(parmakizleri: list[Parmakizi]) -> NesneTeshisi:
    """Nesnenin kendi fotoğraflarına bakarak "ne kadar tanınır" der."""
    nokta, tutarlilik = olcumler(parmakizleri)
    return teshisi_kur(len(parmakizleri), nokta, tutarlilik)


def teshisi_kur(fotograf_sayisi: int, nokta: int, tutarlilik: float) -> NesneTeshisi:
    """Ölçülmüş iki sayıdan Türkçe karneyi kurar (saklanan değerlerden de kurulur)."""
    if fotograf_sayisi < 2:
        return NesneTeshisi(
            seviye="tek",
            rozet="gri",
            baslik="Henüz ölçülemedi",
            aciklama=(
                "Tek fotoğrafla bu nesnenin ne kadar tanınacağı ölçülemez: sistem "
                "fotoğrafları birbiriyle karşılaştırarak karar verir."
            ),
            oneri="Nesnenin başka bir açıdan çekilmiş en az bir fotoğrafını daha ekleyin.",
            fotograf_sayisi=fotograf_sayisi,
            nokta=nokta,
            tutarlilik=tutarlilik,
        )

    if nokta < EN_AZ_ANAHTAR_NOKTA:
        # Motorun "desensiz" dalı: tutunacak tek iz renktir.
        return NesneTeshisi(
            seviye="duz",
            rozet="sari",
            baslik="Düz renkli — bulunamaz",
            aciklama=(
                "Nesnenin tutunacak bir deseni yok (yazı, logo, kenar çizgisi); geriye "
                "yalnızca renk kalıyor. Renk tek başına iki nesneyi birbirinden "
                "ayıramadığı için sistem bu nesneye isim YAZMAZ: ölçümde böyle "
                "nesnelerin hiçbiri bulunmadı. Bu bilerek verilmiş bir karardır — aynı "
                "renkteki bambaşka bir şeye bu nesnenin adını yazmaktansa susmak."
            ),
            oneri=(
                "Nesnenin yazılı, etiketli ya da desenli bir yüzü varsa ondan 2-3 "
                "fotoğraf ekleyin; sistemin tutunabileceği tek şey odur. Böyle bir yüz "
                "yoksa bu nesne bu yöntemle bulunamaz."
            ),
            fotograf_sayisi=fotograf_sayisi,
            nokta=nokta,
            tutarlilik=tutarlilik,
        )

    if tutarlilik >= _TUTARLILIK_KOLAY and nokta >= DESEN_TABAN_NOKTA:
        return NesneTeshisi(
            seviye="kolay",
            rozet="yesil",
            baslik="Kolay tanınır",
            aciklama=(
                "Belirgin bir deseni var ve yüklediğiniz fotoğraflar birbirini tanıyor — "
                "sistemin güvendiği iki kanıt da yerinde."
            ),
            oneri=(
                "Bu nesne için ek fotoğrafa gerek yok. Nesneyi bambaşka bir ışıkta ya da "
                "çok farklı bir açıdan da arayacaksanız o durumdan bir fotoğraf ekleyin."
            ),
            fotograf_sayisi=fotograf_sayisi,
            nokta=nokta,
            tutarlilik=tutarlilik,
        )

    # "Zor" kovasına İKİ ayrı sebeple düşülür ve kullanıcıya DOĞRU sebep
    # söylenmelidir; yanlış sebep, yanlış çabaya yol açar (fotoğrafları
    # değiştirmesi gerekirken nesneyi yeniden çerçevelemeye çalışır).
    if tutarlilik >= _TUTARLILIK_KOLAY:
        # Fotoğraflar birbirini tanıyor; eksik olan DESEN.
        aciklama = (
            "Fotoğraflarınız birbirini tanıyor ama nesnenin tutunacak deseni zayıf: "
            "sistemin ayırt edici olarak sayabileceği ayrıntı az. Bu nesne, ona "
            "benzeyen başka bir nesneyle karışabilir."
        )
        oneri = (
            "Nesnenin yazılı, etiketli ya da logolu bir yüzü varsa ondan yakın çekim "
            "2-3 fotoğraf ekleyin; ayırt eden şey renk değil, o ayrıntılardır."
        )
    else:
        # Desen var ama fotoğraflar birbirini tanımıyor.
        aciklama = (
            "Nesnenin deseni var ama yüklediğiniz fotoğraflar birbirini zor tanıyor: "
            "açı ya da ışık farkı çok büyük olabilir, ya da nesnenin görünen yüzü her "
            "fotoğrafta başka."
        )
        oneri = (
            "Nesnenin AYNI yüzünü gösteren, daha yakın ve daha aydınlık 2-3 fotoğraf "
            "ekleyin; birbirinden çok farklı kareler yerine birbirine yakın kareler "
            "işe yarıyor."
        )
    return NesneTeshisi(
        seviye="zor",
        rozet="kirmizi",
        baslik="Zor tanınır",
        aciklama=aciklama,
        oneri=oneri,
        fotograf_sayisi=fotograf_sayisi,
        nokta=nokta,
        tutarlilik=tutarlilik,
    )


# ============================================== 2) kaç fotoğraf yeterli


# YENİDEN ÖLÇÜLDÜ (2026-09, "renk taşımaz" kuralından sonra; tam takım,
# 12 nesne, 204 pozitif sorgu, çıta 0,24): kütüphane 1, 2, 3 ve 4 referans
# fotoğrafla ayrı ayrı kuruldu ve AYNI sorgular soruldu. Her koşuda yanlış isim
# 0, negatife yazılan isim 0 kaldı.
#
#   fotoğraf   bulundu          işaret nesnenin üstünde
#      1        3/204  (%1,5)          3  (%1,5)
#      2        4/204  (%2,0)          4  (%2,0)
#      3        7/204  (%3,4)          7  (%3,4)
#      4        8/204  (%3,9)          8  (%3,9)
#
# OKUNUŞU: her fotoğraf bulmayı artırıyor ve artık BULUNAN her nesnede işaret
# gerçekten nesnenin üstünde (eski ölçümde bulunanların yalnız yarısında
# öyleydi). Sayılar eskisinden düşük, çünkü yalnız renge dayanan eşleşmeler
# artık kabul edilmiyor; o eşleşmelerin bir kısmı doğru ada denk geliyordu ama
# aynı kapıdan kütüphanede olmayan nesnelere de isim yazılıyordu.
# DÜRÜSTÇE: ölçüm 4 fotoğrafa kadar yapıldı; 5 ve üstünün katkısı ÖLÇÜLMEDİ,
# o yüzden "4'ten sonrası boşa" denmiyor — "4'e kadarki katkı biliniyor" deniyor.
FOTOGRAF_EGRISI: tuple[tuple[int, int, int], ...] = (
    # (fotoğraf sayısı, 204 sorguda bulunan, işaret nesnenin üstünde olan)
    (1, 3, 3),
    (2, 4, 4),
    (3, 7, 7),
    (4, 8, 8),
)

# Ölçümün gittiği en uzak nokta; buraya kadar her fotoğrafın katkısı ölçüldü.
OLCULEN_FOTOGRAF = FOTOGRAF_EGRISI[-1][0]
# Altında teşhisin bile yapılamadığı sayı (karşılaştıracak ikinci kare yok)
EN_AZ_FOTOGRAF = 2


def fotograf_notu(sayi: int) -> str:
    """Ekranda fotoğraf sayısının yanında duran tek cümle."""
    if sayi < EN_AZ_FOTOGRAF:
        return (
            f"Tek fotoğraf yeterli değil: en az {EN_AZ_FOTOGRAF} fotoğraf olmadan bu "
            "nesnenin ne kadar tanınacağı ölçülemez."
        )
    if sayi < OLCULEN_FOTOGRAF:
        eksik = OLCULEN_FOTOGRAF - sayi
        return (
            f"{eksik} fotoğraf daha ekleyebilirsiniz: ölçümde {OLCULEN_FOTOGRAF}. fotoğrafa "
            "kadar her kare biraz daha çok nesne buldurdu."
        )
    return (
        f"Fotoğraf sayısı yeterli: ölçüm {OLCULEN_FOTOGRAF} fotoğrafa kadar yapıldı ve "
        "fazlasının katkısı ölçülmedi. Bir fotoğraf daha eklemek yerine, bulunamayan bir "
        "durum görürseniz TAM O kareyi ekleyin."
    )


# ================================ 3) "ne kadar emin olsun" — günlük dilde


@dataclass(frozen=True)
class CitaSecenegi:
    """Kullanıcının seçebileceği titizlik kademesi. "Eşik/skor" kelimesi YOK."""

    anahtar: str  # formdan gelen değer
    ad: str  # ekranda görünen ad
    sonuc: str  # bunu seçersem ne olur — tek cümle
    carpan: float  # .env'deki çıtanın katı


# NEDEN "DAHA ÇOK İŞARET ÇIKSIN" DİYE BİR SEÇENEK YOK:
# Ölçüm (tests/nesne_kiyas, 264 sorgu) çıtayı 0,10'dan 0,60'a tarar. Bugünkü
# çıta (0,24) "yanlış isim SIFIR kalırken en çok bulan" noktadır; bir adım
# aşağıda (0,22) sistem yanlış isim yazmaya başlar. Yani indirilecek pay yoktur
# — indirmek isabeti değil, YANLIŞ İSMİ artırır (docs/00: yanlış alarm güveni
# bitirir). Sahada gerçekten gerekiyorsa değer .env → NESNE_ESLESME_ESIGI'dir;
# ekranda tek tıkla erişilebilir bir tuzak olarak durmaz.
CITA_SECENEKLERI: tuple[CitaSecenegi, ...] = (
    CitaSecenegi(
        anahtar="otomatik",
        ad="Otomatik (önerilen)",
        sonuc=(
            "Sistem, ölçümle bulunmuş ayarını kullanır: yanlış isim yazmadan en çok "
            "nesneyi bulduğu nokta."
        ),
        carpan=1.0,
    ),
    CitaSecenegi(
        anahtar="temkinli",
        ad="Daha temkinli",
        sonuc=(
            "Sistem daha az işaret koyar. Ölçümde 204 sorgunun 8'i yerine 2'si "
            "bulundu; yanlış isim iki ayarda da sıfır. Nesnenin karede olduğunu "
            "bildiğiniz hâlde bulunamıyorsa bu seçeneği kullanmayın."
        ),
        # 1,25 kat = varsayılan 0,24 → 0,30. UYDURMA DEĞİL, ÖLÇÜLDÜ: eşik
        # taramasında 0,30 noktası isabeti %3,9'dan %1,0'e indiriyor ve yanlış
        # ismi sıfırda tutuyor.
        #
        # NEDEN 1,5'TEN 1,25'E İNDİ (2026-09): eski çarpan 0,36'ya denk geliyordu
        # ve o çıta eski motorda hâlâ 42 nesne buluyordu. "Renk taşımaz"
        # kuralından sonra 0,36'da HİÇBİR nesne bulunmuyor — yani seçenek
        # kullanıcıyı "hiç sonuç çıkmayan" bir ayara götüren bir tuzağa
        # dönüşmüştü. Çarpan, ölçümde hâlâ sonuç veren en yüksek kademeye çekildi.
        carpan=1.25,
    ),
)

VARSAYILAN_CITA_SECIMI = CITA_SECENEKLERI[0].anahtar


# ------------------- kurulu sunucunun ayarı ölçülen değerden farklıysa
#
# NEDEN VAR: .env dosyası git'e girmez. Motor değişip önerilen çıta 0,42'den
# 0,24'e indiğinde, DAHA ÖNCE KURULMUŞ bir sunucu kendi .env'inde 0,42 ile
# kalır. O sunucuda yeni motor sessizce daha kötü çalışır — ölçüldü: 0,42
# çıtada 204 sorgunun HİÇBİRİ bulunmuyor, 0,24 çıtada 8'i bulunuyor ve yanlış
# isim iki ayarda da sıfır. Yani yüksek çıta hiçbir şey kazandırmıyor, yalnız
# kaybettiriyor.
#
# Ayarı HABER VERMEDEN EZMEK yanlış olurdu: kullanıcı onu bilerek değiştirmiş
# olabilir. Onun yerine ekranda Türkçe bir not çıkar ve ne yapacağı yazar;
# değiştirmeyi seçerse Ayarlar sayfasındaki düğmeyle yapar (terminal yok).
#
# Sayılar `tests/nesne_kiyas` eşik eğrisinden alınmıştır (264 sorgu):
#   çıta 0,24 → 8/204 bulundu, yanlış isim 0   (ölçülen en iyi güvenli nokta)
#   çıta 0,30 → 2/204 bulundu, yanlış isim 0
#   çıta 0,36 ve üstü → 0/204 bulundu
#   çıta 0,22 → 13/204 bulundu ama YANLIŞ İSİM 1  (kırmızı çizgi aşıldı)
# Cümle "sizin ayarınız {N} nesne buldu" biçiminde kurulur: sayıdan SONRA ek
# gelmez. Gelseydi ek sayıya göre değişirdi ("8'i" ama "0'ı") ve bu dosya, tam
# da o hatayı düzelten süzgeci (web/ortak.py sayi_eki) kullanamaz — nesneler
# katmanı web katmanından bir şey import etmez.
_ESIK_EGRISI = {0.24: 8, 0.26: 4, 0.28: 3, 0.30: 2, 0.32: 2, 0.34: 1, 0.36: 0}
# Bu farktan küçük sapmalar not çıkarmaz: kullanıcı 0,25 yazmışsa uyarmak
# gürültüdür, davranış neredeyse aynıdır.
_ESIK_SAPMA_PAYI = 0.01


def _bulunan_metni(esik: float) -> str:
    """Bu çıtada kaç nesne bulunduğunu ANLATIR — ölçmediğimiz sayıyı UYDURMAZ.

    Eğri yalnızca çift yüzdeliklerde ölçüldü. Ölçülmemiş bir çıtada (0,25 gibi)
    eskiden "0 nesne" yazılıyordu; bu, ölçüm gibi görünen YANLIŞ bir sayıydı —
    0,25'te gerçekte 6 nesne bulunuyor. Artık ölçülmemiş çıta için iki komşu
    ölçümden bir ARALIK verilir. Eğri azalan olduğu için aralık matematiksel
    olarak doğrudur: daha yüksek çıta daha az bulur.
    """
    yuvarlak = round(esik, 2)
    if yuvarlak in _ESIK_EGRISI:
        sayi = _ESIK_EGRISI[yuvarlak]
        return "hiç nesne bulamaz" if sayi == 0 else f"{sayi} nesne buldu"

    olculen = sorted(_ESIK_EGRISI)
    altta = [e for e in olculen if e < yuvarlak]
    ustte = [e for e in olculen if e > yuvarlak]
    if altta and ustte:
        # Çıta iki ölçüm arasında: sonuç ikisinin arasındadır.
        return f"{_ESIK_EGRISI[ustte[0]]} ile {_ESIK_EGRISI[altta[-1]]} arası nesne buldu"
    if altta:
        # Ölçülen en yüksek çıtanın da üstünde. Orada sayı zaten 0 olduğu için
        # "en çok 0" demek yerine düz Türkçe söylenir.
        tavan = _ESIK_EGRISI[altta[-1]]
        return "hiç nesne bulamaz" if tavan == 0 else f"en çok {tavan} nesne buldu"
    return f"en az {_ESIK_EGRISI[ustte[0]]} nesne buldu"


def cita_notu(esik: float, onerilen: float = VARSAYILAN_ESIK) -> str:
    """Sunucunun çıtası ölçülen değerden farklıysa Türkçe not; değilse boş.

    Boş dönmesi olağan durumdur — not yalnızca gerçekten bir sapma varsa çıkar.
    """
    # round(): kayan nokta yüzünden abs(0,25 - 0,24) = 0,010000000000000009 çıkar
    # ve payı AŞAR; 0,23 ise aşmaz. Yuvarlamadan, bir adım yukarısı "eski kurulum"
    # sayılırken bir adım aşağısı sessizce kabul ediliyordu.
    if round(abs(esik - onerilen), 4) <= _ESIK_SAPMA_PAYI:
        return ""
    ortak = (
        f"Bu sunucuda sistem, bir yere isim yazmak için %{round(esik * 100)} benzerlik "
        f"arıyor. Ölçümle bulunan ve önerilen değer ise %{round(onerilen * 100)}. "
    )
    if esik > onerilen:
        return (
            ortak + "Bu ayar büyük olasılıkla programın eski bir sürümünden kalmıştır: tanıma "
            "yöntemi değişti ve çıta düşürüldü, ama sizin ayarınız dosyanızda olduğu gibi "
            f"kaldı. Yüksek çıta yanlış isimden korumaz (ölçümde iki ayarda da yanlış isim "
            f"sıfır), yalnızca nesne buldurmaz: 204 sorguluk ölçümde önerilen ayar 8 nesne "
            f"buldu, sizin ayarınız {_bulunan_metni(esik)}. "
            "Ayarlar sayfasındaki “Nesne arama titizliği” kutusuna "
            f"{onerilen:.2f} yazıp kaydedin."
        )
    return (
        ortak + "Çıtanız önerilenin ALTINDA. Ölçümde bir adım aşağıda (0,22) sistem yanlış isim "
        "yazmaya başlıyor — yani bu ayar, kütüphanenizde hiç olmayan bir şeye nesne adı "
        "yazdırabilir. Ayarlar sayfasındaki “Nesne arama titizliği” kutusuna "
        f"{onerilen:.2f} yazıp kaydedin."
    )


def cita_secenegi(anahtar: str) -> CitaSecenegi:
    """Form değerinden seçeneği bulur; tanınmayan değer Otomatik'e döner."""
    for secenek in CITA_SECENEKLERI:
        if secenek.anahtar == anahtar:
            return secenek
    return CITA_SECENEKLERI[0]


# ================================== 4) "eşleşme yok" deyince ne yapmalı


def netlik(bgr: np.ndarray) -> float:
    """Fotoğrafın ayrıntı ölçüsü (Laplace değişintisi). Düşük = bulanık ya da karanlık.

    Karanlık fotoğraf da düşük çıkar ve bu BİLEREK böyledir: ikisinin de
    kullanıcı için cevabı aynıdır — "daha net, daha aydınlık bir kare çekin".
    """
    gri = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gri, cv2.CV_64F).var())


def tarama_eylemi(
    gorsel: np.ndarray,
    en_yuksek_skor: float,
    esik: float,
    kutuphane_bos: bool = False,
    duz_kutuphane: bool = False,
    otomatik_esik: float | None = None,
) -> str:
    """Eşleşme çıkmadığında kullanıcının ATABİLECEĞİ tek adım.

    Sıra rastgele değil, EN UCUZ İŞTEN EN PAHALIYA doğrudur: önce tek tıkla
    düzelen bir şey var mı ("Daha temkinli" seçiliydi), sonra fotoğrafın
    kendisinde düzeltilebilecek bir kusur (ayrıntı azlığı), sonra eşleşme kıl
    payı mı kaçtı (o kareyi kütüphaneye eklemek), sonra kütüphanenin kendi
    sınırı mı (düz renkli nesneler), en sonda genel öneri.
    """
    if kutuphane_bos:
        return (
            "Önce yukarıdan bir nesne ekleyin: ad verip nesnenin en az 2, tercihen "
            f"{OLCULEN_FOTOGRAF} fotoğrafını yükleyin."
        )
    if otomatik_esik is not None and esik > otomatik_esik and en_yuksek_skor >= otomatik_esik:
        # Kullanıcı "Daha temkinli"yi seçmiş ve TAM DA ONUN YÜZÜNDEN kaçırmış.
        # Bunu söylemek çıtayı gevşetmek değildir: önerilen ayara GERİ DÖNMEKTİR
        # ve o ayar zaten "yanlış isim sıfır" noktasıdır. Kullanıcının kendi
        # seçiminin bedelini görmeden "sistem bulamıyor" sanması en kötüsü.
        return (
            "Bu fotoğrafta nesne, önerilen ayarda bulunuyordu. “Sistem ne kadar emin "
            "olsun?” listesini “Otomatik (önerilen)” konumuna getirip yeniden arayın."
        )
    if netlik(gorsel) < _NETLIK_SINIRI:
        # ÜÇ SEBEP DE SAYILIR ("bulanık" demekle yetinilmez): ölçülen şey
        # fotoğraftaki AYRINTI miktarıdır ve bu üçünde de düşer. Yalnız
        # "bulanık" deseydik, net ama karanlık bir fotoğrafta kullanıcıya
        # yanlış bir şey söylemiş olurduk — o da fotoğrafı yeniden çekerken
        # yanlış şeyi düzeltmeye çalışırdı.
        return (
            "Bu fotoğrafta ayrıntı az: bulanık, karanlık ya da çok düşük kontrastlı "
            "görünüyor. Aynı yerin daha net ve daha aydınlık bir karesini deneyin."
        )
    # "Yakınlık" hep ÖNERİLEN çıtaya göre ölçülür, kullanıcının seçtiğine göre
    # değil: aynı fotoğraf, kullanıcı titizliği değiştirdi diye başka bir teşhis
    # almamalı. (Titizliğin KENDİSİ sebepse, yukarıdaki dal onu zaten söyledi.)
    olcut = min(esik, otomatik_esik) if otomatik_esik is not None else esik
    if en_yuksek_skor >= olcut * _YAKIN_PAYI:
        return (
            "Kıl payı kaçtı. Çıtayı indirmek yerine, nesnenin BU açıdan ve bu ışıktan "
            "çekilmiş bir fotoğrafını kütüphaneye ekleyin — daha güvenli yol budur."
        )
    if duz_kutuphane:
        return (
            "Kütüphanenizdeki nesneler düz renkli ve desensiz; sistem bunlarda çekimser "
            "kalır. Nesnelerin yazılı ya da etiketli yüzünden fotoğraf ekleyin."
        )
    return (
        "Nesne bu karede küçük ya da yandan görünüyor olabilir; nesneye daha yakın, "
        "önden çekilmiş bir fotoğraf deneyin."
    )

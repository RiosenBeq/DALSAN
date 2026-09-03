"""KALİTE KAPISI: nesne kütüphanesi bugünkünden kötüye gitmesin.

Bu dosya bir ölçüm değil, bir BEKÇİDİR. Kıyas takımının küçük sürümünü
çalıştırır ve üç şeyi korur:

  1. KIRMIZI ÇİZGİ — sistem yanlış isim YAZMAZ. İki türü de ayrı ayrı sıfır
     olmalıdır (docs/00-PROJE-BAGLAMI.md: yanlış alarm güveni bitirir):
       KÜTÜPHANE İÇİ  → A nesnesine B nesnesinin adı. SIFIR, sert kural.
       KÜTÜPHANE DIŞI → kütüphanede olmayan bir şeye isim. 2026-09'a kadar
                        `xfail` ile işaretli açık bir borçtu; "renk taşımaz"
                        kuralıyla kapandı ve artık o da SIFIR, sert kural.
  2. TABAN İSABET — bugün bulabildiklerimizi yarın da bulabilmeliyiz.
  3. TAKIMIN KENDİSİ KÖR OLMASIN — sertleştirilmiş sorgular motorun en zayıf
     dalına gerçekten giriyor mu? Bu da her koşuda ölçülür; ölçülmezse bir
     sonraki "sadeleştirme" takımı sessizce eski kör hâline döndürebilir.

Tam takım (12 nesne, 264 sorgu, ~2,5 dakika) komut satırındadır:

    .venv/bin/python -m tests.nesne_kiyas

Aşağıdaki taban değerler o ölçümün küçük takımdaki karşılığıdır ve ELDE
ÖLÇÜLMÜŞTÜR (uydurulmamıştır). Motor iyileştiğinde bu sayılar yükseltilir;
düşürülmesi ancak bilerek verilen bir karara dayanabilir.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.nesneler import arama
from app.nesneler.kutuphane import EN_AZ_ANAHTAR_NOKTA, VARSAYILAN_ESIK
from tests.nesne_kiyas import cizim, olcum, takim

# --- 2026-09 ölçümü, "renk taşımaz" kuralından SONRA ---------------------
# Küçük takım: 9 nesne, 36 pozitif + 20 negatif sorgu. Negatiflerin 8'i
# "kütüphanedekiyle aynı renkte düz yabancı", 6'sı "gerçekten desensiz zemin".
#
#   eşik 0.24 → isabet 1/36, işareti yerinde 1, yanlış isim 0 + 0
#   eşik 0.22 → isabet 1/36, kütüphane DIŞI yanlış 1  (çıtanın ALTI)
#   eşik 0.42 → isabet 0/36, yanlış isim 0
#   doğru nesnenin ortalama en iyi skoru → 0.055
#
# İSABETİN NEDEN BU KADAR DÜŞTÜĞÜ (küçük takımda 8 → 1, tam takımda 61 → 8):
# yanlış isimlerin tamamı, kararı fiilen RENGE kalmış karşılaştırmalardan
# geliyordu; o kapıyı kapatmak aynı kapıdan geçen isabetleri de kapattı.
# Bilerek ödenen bedeldir (docs/00: yanlış alarm güveni bitirir). Kaybedilen
# isabetin bir kısmı zaten sahteydi — tam takımda bulunan 61 sorgunun yalnız
# 38'inde işaret gerçekten nesnenin üstündeydi; bugün 8'in 8'inde üstünde.
TABAN_ISABET = 1
TABAN_YERINDE = 1
TABAN_ISABET_DUSUK_ESIK = 1
TABAN_ORTALAMA_SKOR = 0.055

# Yanlış isim yazılmıyorken bile "ne kadar yaklaşıldığı" ölçülür: pay eriyorsa
# bir sonraki küçük değişiklik çıtayı aşar. Kırmızı çizgi kırılmadan önce
# ötmesi gereken yer burasıdır. Bu dört tavan eskiden çıtanın (0,24) dibindeydi
# (0,19-0,52); "renk taşımaz" kuralından sonra hepsi çıtanın yarısının altına
# indi — pay artık kıl payı değil.
TAVAN_NEGATIF_SKOR = 0.041  # eski (başka renkte) yabancı nesneler + boş zeminler
TAVAN_YANLIS_ADAY_SKORU = 0.049  # pozitif sorguda YANLIŞ kütüphane nesnesi
TAVAN_DESENSIZ_ZEMIN_SKORU = 0.047  # desensiz zeminler
TAVAN_DUZ_YABANCI_SKORU = 0.112  # kütüphanedekiyle AYNI renkte düz yabancı

# Ölçüm OpenCV sürümüne göre kıl payı oynayabilir; kapı gürültüye değil
# GERÇEK gerilemeye takılsın diye pay bırakılır. İsabet payı SIFIRDIR: taban
# artık 1'dir, bir sorguluk pay tabanı anlamsız kılardı.
_PAY_SORGU = 0
_PAY_SKOR = 0.03

# Düşük eşik: bugünkü çıtanın BİR ADIM altında kalan "az kalsın bulunuyordu"ları
# da korur. Bu eşik üründe KULLANILMAZ, yalnız erken uyarı içindir. Çıtanın
# altında yanlış isim çıkması beklenir (çıtayı oraya koymamızın sebebi budur);
# ölçülen sayı 1'dir ve ARTMAMALIDIR.
TANI_ESIGI = 0.22
TANI_ESIGINDE_BEKLENEN_KUTUPHANE_DISI = 1

# Kıyas takımının eski çıtası. Kayda geçirilir: "çıtayı yükseltelim olsun
# bitsin" önerisi ölçülmüş ve REDDEDİLMİŞTİR (aşağıdaki teste bak).
ESKI_ESIK = 0.42


@pytest.fixture(scope="module")
def kiyas():
    """Sertleştirilmiş küçük kıyas takımı bir kez üretilir ve bir kez taranır."""
    kucuk_takim = takim.takim_olustur(kucuk=True)
    return kucuk_takim, olcum.olc(kucuk_takim)


# ============================================================ kırmızı çizgi


def test_kirmizi_cizgi_kutuphane_ici_yanlis_isim_yazilmaz(kiyas):
    """A nesnesine B nesnesinin adı YAZILMAZ.

    En sinsi hatadır: rapor doğru görünür, yanlış nesneyi gösterir. Sahada
    "Gri pano A"nın önüne gitmesi gereken kişi "Gri pano B"nin önüne gider.
    Bugün sıfırdır; bu testin kırılması yeni kodun sahada yanlış nesneyi
    işaretlediği anlamına gelir.
    """
    _, kayitlar = kiyas
    ozet = olcum.esik_ozeti(kayitlar, VARSAYILAN_ESIK)
    hatalar = [h for h in olcum.yanlis_isimler(kayitlar, VARSAYILAN_ESIK) if h.kutuphane_ici]
    ayrinti = "; ".join(f"'{h.sorulan_metni}' → '{h.yazilan}' ({h.skor:.2f})" for h in hatalar)
    assert ozet.kutuphane_ici_yanlis == 0, f"kütüphane içi yanlış isim yazıldı: {ayrinti}"


def test_kirmizi_cizgi_kutuphane_disi_yanlis_isim_yazilmaz(kiyas):
    """Kütüphanede OLMAYAN bir şeye isim YAZILMAZ.

    2026-09'a kadar bu test `xfail` idi: motorun "iki taraf da desensiz" dalı
    kararı yalnız renge bırakıyor, tavanı 0,62 iken çıta 0,24'tü ve
    kütüphanedekiyle aynı renkte düz bir yabancı nesne (mavi kasa → "Düz mavi
    bidon") o aradan geçiyordu. "Renk taşımaz" kuralıyla kapandı; artık sert
    kuraldır ve bir daha gevşetilmez.
    """
    _, kayitlar = kiyas
    ozet = olcum.esik_ozeti(kayitlar, VARSAYILAN_ESIK)
    hatalar = [h for h in olcum.yanlis_isimler(kayitlar, VARSAYILAN_ESIK) if not h.kutuphane_ici]
    ayrinti = "; ".join(f"'{h.bozulma}' → '{h.yazilan}' ({h.skor:.2f})" for h in hatalar)
    assert ozet.kutuphane_disi_yanlis == 0, f"olmayan bir şeye isim yazıldı: {ayrinti}"


def test_cita_yukseltilirse_de_yanlis_isim_cikmaz(kiyas):
    """Çıtanın ÜSTÜNDEKİ her kademede de yanlış isim sıfır kalmalı.

    Kayda geçirilen olgu şudur: eski motorda çıtayı 0,42'ye geri çekmek deliği
    KAPATMIYORDU (küçük takımda 26 yanlış isim kalıyordu). Yani çözüm çıtada
    değil, `benzerlik()` içindeki formüldeydi. Bugün çıtanın üstündeki bütün
    kademelerde sıfırdır; bu test, "çıtayı oynatalım" refleksinin bir daha
    tahminle değil sayıyla tartışılmasını sağlar.
    """
    _, kayitlar = kiyas
    for esik in olcum.ESIK_ARALIGI:
        if esik < VARSAYILAN_ESIK:
            continue
        ozet = olcum.esik_ozeti(kayitlar, esik)
        assert ozet.yanlis_isimli_bulgu == 0, (
            f"eşik {esik:.2f}: {ozet.yanlis_isimli_bulgu} yanlış isim"
        )
    assert olcum.esik_ozeti(kayitlar, ESKI_ESIK).yanlis_isimli_bulgu == 0


def test_bulanik_kutuphane_nesnesi_kardesinin_adini_almaz(kiyas):
    """Deseni SİLİNEN bir kütüphane nesnesi, kardeşinin adını almaz.

    "Gri pano A" ile "Gri pano B" aynı gri, farklı desendir. Bulanıklık deseni
    sildiğinde geriye yalnız renk kalır ve ikisi ayırt edilemez hâle gelir.
    Doğru davranış "eşleşme yok"tur — kendi adı da yazılmayabilir, ama
    KARDEŞİNİN adı asla yazılmamalıdır.

    Eskiden yazılmıyordu ama kıl payıyla: kardeş her bulanıklık kademesinde en
    tepedeki adaydı ve skoru 0,20-0,22 ile çıtanın hemen altındaydı. Bulanıklık
    deseni sildiği için karar renge kalıyordu; "renk taşımaz" kuralı o skoru
    0,05'e indirdi. Tavan bu yüzden ayrıca sınanır: yazılmıyor olması yetmez,
    yaklaşmaması da gerekir.
    """
    _, kayitlar = kiyas
    bulanik = [
        kayit
        for kayit in kayitlar
        if kayit.sorgu.dogru_ad == "Gri pano A (kareli)" and "bulanıklık" in kayit.sorgu.bozulma
    ]
    assert bulanik, "takımda deseni silinmiş 'Gri pano A' sorgusu yok — takım kör"
    for kayit in bulanik:
        yazilanlar = [b.nesne_adi for b in kayit.bulgular(VARSAYILAN_ESIK)]
        assert "Gri pano B (çapraz)" not in yazilanlar, (
            f"bulanık 'Gri pano A' KARDEŞİNİN adını aldı ({kayit.sorgu.bozulma})"
        )
    tavan = max(kayit.yabanci_en_yuksek for kayit in bulanik)
    assert tavan <= TAVAN_YANLIS_ADAY_SKORU + _PAY_SKOR, (
        f"bulanık panoda kardeşin skoru yükseldi: {tavan:.3f}, "
        f"tavan {TAVAN_YANLIS_ADAY_SKORU} — çıta 0,24'e yaklaşıyor"
    )


# ================================================================ isabet


def test_isabet_taban_degerin_altina_dusmez(kiyas):
    _, kayitlar = kiyas
    ozet = olcum.esik_ozeti(kayitlar, VARSAYILAN_ESIK)
    assert ozet.isabet >= TABAN_ISABET - _PAY_SORGU, (
        f"isabet düştü: {ozet.isabet}/{ozet.pozitif}, taban {TABAN_ISABET}. "
        "Tam ölçüm için: .venv/bin/python -m tests.nesne_kiyas"
    )
    assert ozet.yerinde >= TABAN_YERINDE - _PAY_SORGU, (
        f"işareti nesnenin üstünde olan bulgu sayısı düştü: {ozet.yerinde}, taban {TABAN_YERINDE}"
    )


def test_dusuk_esikte_de_gerileme_yok(kiyas):
    """Bugünkü çıtanın altındaki 'az kalsın bulunuyordu'lar da korunur.

    Çıtanın hemen altındaki skorlar bozulursa üründe hemen görünmez ama
    isabeti artırma ihtimalimiz sessizce yok olur. Erken uyarı buradadır.
    """
    _, kayitlar = kiyas
    ozet = olcum.esik_ozeti(kayitlar, TANI_ESIGI)
    assert ozet.isabet >= TABAN_ISABET_DUSUK_ESIK - _PAY_SORGU, (
        f"düşük eşikte isabet düştü: {ozet.isabet}/{ozet.pozitif}, taban {TABAN_ISABET_DUSUK_ESIK}"
    )
    assert ozet.kutuphane_disi_yanlis <= TANI_ESIGINDE_BEKLENEN_KUTUPHANE_DISI, (
        f"çıtanın bir adım altında yanlış isim arttı: "
        f"{ozet.kutuphane_disi_yanlis}, beklenen en çok "
        f"{TANI_ESIGINDE_BEKLENEN_KUTUPHANE_DISI} — doğru ile yanlış arasındaki pay eriyor"
    )


def test_dogru_nesnenin_benzerlik_skoru_dusmez(kiyas):
    """Sayılabilir isabet değişmese bile skorlar aşınabilir; onu da ölç."""
    _, kayitlar = kiyas
    skorlar = [kayit.dogru_en_yuksek for kayit in kayitlar if kayit.sorgu.dogru_ad]
    ortalama = float(np.mean(skorlar))
    assert ortalama >= TABAN_ORTALAMA_SKOR - _PAY_SKOR, (
        f"doğru nesnenin ortalama skoru düştü: {ortalama:.3f}, taban {TABAN_ORTALAMA_SKOR}"
    )


# ====================================== yanlış adayın çıtaya yaklaşma payı


def test_yanlis_adayin_skoru_yukselmez(kiyas):
    """Yanlış isim yazılmıyor olması yetmez; yaklaşmaması da gerekir.

    Üç aile ayrı ayrı ölçülür, çünkü üçü ayrı şey söyler: eski (başka renkte)
    yabancılar motorun kolay işidir, desensiz zeminler düz-düz dalının boş
    hâlidir, düz yabancılar ise KAPATILAN deliğin ta kendisiydi (tavanı 0,518
    idi, bugün 0,112).
    """
    _, kayitlar = kiyas
    pozitifler = [k for k in kayitlar if k.sorgu.dogru_ad is not None]
    for zorluk, tavan in (
        ("negatif", TAVAN_NEGATIF_SKOR),
        ("desensiz-zemin", TAVAN_DESENSIZ_ZEMIN_SKORU),
        ("duz-yabanci", TAVAN_DUZ_YABANCI_SKORU),
    ):
        olculen = olcum.zorluk_tavani(kayitlar, zorluk)
        assert olculen <= tavan + _PAY_SKOR, (
            f"'{takim.ZORLUK_ADLARI[zorluk]}' ailesinde yanlış adayın skoru yükseldi: "
            f"{olculen:.3f}, tavan {tavan}"
        )
    yanlis_aday_tavani = max(k.yabanci_en_yuksek for k in pozitifler)
    assert yanlis_aday_tavani <= TAVAN_YANLIS_ADAY_SKORU + _PAY_SKOR, (
        f"yanlış nesnenin skoru yükseldi: {yanlis_aday_tavani:.3f}, tavan {TAVAN_YANLIS_ADAY_SKORU}"
    )


# ============================================ takımın kendisi kör olmasın


def test_desensiz_zeminler_gercekten_desensiz(kiyas):
    """Sertleştirilmiş zeminler motorun DÜZ-DÜZ dalına GERÇEKTEN giriyor mu?

    Bu takımın eski kör noktası tam buydu: "boş zemin" sorguları vardı ama
    hiçbiri desensiz değildi, dolayısıyla kararı yalnız renge bırakan dal hiç
    çalışmıyordu. Ölçülmeyen delik kapatılamaz — bu yüzden zeminlerin
    desensizliği her koşuda yeniden kanıtlanır.
    """
    _, kayitlar = kiyas
    kanit = olcum.desensiz_kaniti(kayitlar, "desensiz-zemin")
    assert len(kanit) == len(cizim.DESENSIZ_ZEMIN_TURLERI)
    for bozulma, tam_kare, desensiz, pencere, _ortanca in kanit:
        assert tam_kare < EN_AZ_ANAHTAR_NOKTA, (
            f"'{bozulma}' desensiz sayılmıyor: tüm karede {tam_kare} anahtar nokta var "
            f"(motorun sınırı {EN_AZ_ANAHTAR_NOKTA})"
        )
        assert desensiz == pencere, (
            f"'{bozulma}' zemininde {pencere - desensiz} pencere desenli çıktı — "
            "bu sorgu düz-düz dalını sınamıyor"
        )


def test_eski_bos_zeminler_duz_dala_girmiyordu(kiyas):
    """Yeni zeminlerin NEDEN gerektiğini kayda geçirir.

    Eski "boş zemin" sorgularının tam karesinde onlarca anahtar nokta vardır.
    Bu test, biri "zaten boş zeminimiz vardı" deyip yenilerini silmeye
    kalkarsa öter: eski zeminler motorun en zayıf dalını sınamıyordu.
    """
    _, kayitlar = kiyas
    eskiler = [
        satir for satir in olcum.desensiz_kaniti(kayitlar, "negatif") if "boş zemin" in satir[0]
    ]
    assert eskiler, "eski boş zemin sorguları kaybolmuş"
    assert all(tam_kare >= EN_AZ_ANAHTAR_NOKTA for _, tam_kare, _, _, _ in eskiler), (
        "eski boş zeminler artık desensiz görünüyor — o zaman ayrı bir desensiz "
        "zemin ailesine gerek kalmamış olabilir, ölçüp karar verin"
    )


def test_takimda_ayni_renkte_duz_yabanci_var():
    """Kapsam kontrolü: 'aynı renk + hiç desen' tuzağı takımda gerçekten var mı?

    Doğrulayıcının motoru kırdığı vaka budur. Kolay negatifleri (kırmızı
    söndürücü, mor makara) ölçüp "yanlış isim yok" demeyi engeller.
    """
    assert len(takim.DUZ_YABANCILAR) >= 8
    tam = takim.takim_olustur(kucuk=False)
    duz_yabanci_sorgu = sum(1 for s in tam.sorgular if s.zorluk == "duz-yabanci")
    assert duz_yabanci_sorgu >= 20, (
        f"aynı renkte düz yabancı sorgu sayısı yetersiz: {duz_yabanci_sorgu}"
    )

    kutuphane = {tanim.ad: tanim for tanim in takim.KUTUPHANE}
    for tanim in takim.DUZ_YABANCILAR:
        assert tanim.zorluk == "duz-yabanci"
        assert tanim.ikiz in kutuphane, f"'{tanim.ad}' ikizi kütüphanede yok: {tanim.ikiz}"
        # AYNI RENK yapısal olmalı: yabancının gövde rengi ikizininkiyle aynı.
        # Gölge iki tarafta da olduğu için maske ortancaları karşılaştırılır.
        fark = np.abs(
            _maske_ortancasi(tanim.cizici) - _maske_ortancasi(kutuphane[tanim.ikiz].cizici)
        )
        assert fark.max() <= 20, (
            f"'{tanim.ad}' ikizi '{tanim.ikiz}' ile aynı renkte değil (fark {fark.max():.0f}) "
            "— bu nesne artık 'aynı renk, farklı biçim' tuzağını kurmuyor"
        )

    # Üç renk ailesinin üçü de bulunmalı: mavi (doygun), gri ve beyaz
    # (doygunluğu düşük). Motor bu ikisinde farklı davranır.
    assert {tanim.ikiz for tanim in takim.DUZ_YABANCILAR} >= {
        "Düz mavi bidon",
        "Gri boru",
        "Düz beyaz baret",
    }


def test_takimda_deseni_silen_bulaniklik_var():
    """k=9 nesnenin desenini silmiyordu; k>=13 kademeleri duruyor mu?"""
    cekirdekler = sorted(t.bulaniklik for t in takim._SORGU_TARIFLERI if t.bulaniklik)
    assert max(cekirdekler) >= 17, f"deseni silen bulanıklık kademesi yok: {cekirdekler}"
    assert sum(1 for k in cekirdekler if k >= 13) >= 3, (
        f"deseni silen kademe sayısı yetersiz: {cekirdekler}"
    )
    # Küçük takım (kalite kapısı) da en az bir silici kademe görmeli, yoksa
    # "kardeşinin adını aldı" vakası kapının gözünden kaçar.
    assert any("17" in ad for ad in takim._KUCUK_BOZULMALAR)


def test_takimda_her_zorluk_ve_iki_tuzak_da_var():
    """Kolay nesneleri ölçüp 'iyileşti' demeyi engelleyen kapsam kontrolü."""
    zorluklar = {tanim.zorluk for tanim in takim.KUTUPHANE}
    assert zorluklar == {"yuksek", "orta", "duz", "benzer-renk", "benzer-desen"}
    for zorluk in ("benzer-renk", "benzer-desen"):
        assert sum(1 for t in takim.KUTUPHANE if t.zorluk == zorluk) == 2, (
            f"'{zorluk}' tuzağı çift olmalı: aynı/farklı renkte iki nesne"
        )
    assert len(takim.YABANCILAR) >= 4, "kütüphanede olmayan nesneler ölçülmeli"


# ======================================================= ölçümün kendisi


def test_olcum_gercek_taramayla_ayni_sonucu_verir(kiyas, test_ayarlari):
    """Kıyas, motorun kendi `arama.tara()` çıktısını ölçmelidir — taklidini değil.

    Ölçüm hızlansın diye her sorgu bir kez taranır ve eşik sonradan uygulanır.
    Bu kısayol sonucu değiştirmiş olsaydı, bütün taban değerler anlamsız
    olurdu. Burada birkaç sorgu gerçek tarama yolundan geçirilip karşılaştırılır.
    """
    kucuk_takim, kayitlar = kiyas
    for kayit in kayitlar[:4]:
        gercek = arama.tara(
            kayit.sorgu.gorsel,
            "kiyas.jpg",
            kucuk_takim.nesneler,
            test_ayarlari.nesne_tarama_klasoru,
            VARSAYILAN_ESIK,
        )
        beklenen = [(b.nesne_adi, b.skor, b.kutu) for b in gercek.bulgular]
        olculen = [(b.nesne_adi, b.skor, b.kutu) for b in kayit.bulgular(VARSAYILAN_ESIK)]
        assert olculen == beklenen, f"ölçüm ile gerçek tarama ayrıştı: {kayit.sorgu.etiket}"


def test_takim_tekrarlanabilir():
    """Aynı tohum → aynı pikseller. Olmasaydı taban değerler her gün kayardı."""
    once = takim.referans_gorselleri(takim.KUTUPHANE[0])
    sonra = takim.referans_gorselleri(takim.KUTUPHANE[0])
    assert all(np.array_equal(a, b) for a, b in zip(once, sonra, strict=True))


def _maske_ortancasi(cizici) -> np.ndarray:
    """Nesnenin (arka planı değil) kendi piksellerinin ortanca BGR rengi."""
    gorsel, maske = cizici()
    return np.median(gorsel[maske > 127].reshape(-1, 3), axis=0)

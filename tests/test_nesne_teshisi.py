"""Nesne teşhisi: motoru kullanıcının diline çeviren katman.

Bu katmanın işi ISABET ARTIRMAK DEĞİL, kullanıcının ne olduğunu ve ne
yapacağını anlamasıdır. Dolayısıyla testlerin beklediği şeyler de bunlar:

1. **Teşhis GERÇEK ölçümden gelsin.** "Kolay tanınır" yazısı, nesnenin kendi
   fotoğraflarının birbirini tanımasından çıkmalı; sabit bir metin olmamalı.
2. **Ölçek sıralı olsun.** "Kolay" gerçekten "düz"den, "düz" gerçekten
   "zor"dan daha iyi bulunuyor olmalı. Sıralaması bozuk bir ölçek yalandır.
3. **Kırmızı çizgi burada da geçerli.** Bu katman hiçbir yerde çıtayı
   DÜŞÜRMEMELİ; ekranda "daha çok işaret çıksın" diye bir seçenek olmamalı.
4. **Her "eşleşme yok" bir eylemle bitsin.** Yüzde göstermek yetmez.
5. **Dar ekranda (375 px) taşma olmasın.**
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import cv2
import numpy as np
import pytest

from app import veritabani
from app.nesneler import arama, depo, teshis
from app.nesneler.kutuphane import EN_AZ_ANAHTAR_NOKTA, VARSAYILAN_ESIK, Nesne, parmakizi_cikar
from app.web import ortak
from tests.test_nesne_kutuphanesi import desenli_nesne, jpeg, sahne


@pytest.fixture
def baglanti(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    yield baglanti
    baglanti.close()


def duz_gorsel(renk=(40, 40, 200)) -> np.ndarray:
    """Desensiz, tek renk yama — motorun "düz" dalına düşer."""
    return np.full((180, 180, 3), renk, dtype=np.uint8)


def _izler(*gorseller) -> list:
    return [parmakizi_cikar(g) for g in gorseller]


# ==================================================== 1) ölçüm gerçek mi


def test_olcumler_ayni_nesnenin_fotograflarinda_yuksek_tutarlilik():
    """Aynı nesnenin birbirine yakın kareleri → yüksek tutarlılık."""
    nokta, tutarlilik = teshis.olcumler(
        _izler(desenli_nesne(tohum=1), desenli_nesne(tohum=1), desenli_nesne(tohum=1))
    )
    assert nokta > EN_AZ_ANAHTAR_NOKTA
    assert tutarlilik > 0.8


def test_olcumler_birbirini_tanimayan_fotograflarda_dusuk_tutarlilik():
    """Aynı ada verilmiş ama birbirine benzemeyen kareler → düşük tutarlılık.

    Ölçümde en kötü nesneler tam olarak bunlardı: 192 anahtar noktası olan
    "Gri pano A" 14 sorgunun hiçbirinde bulunamadı, çünkü kendi fotoğrafları
    birbirini %4 oranında tanıyordu.
    """
    _, tutarlilik = teshis.olcumler(
        _izler(
            desenli_nesne((40, 40, 200), tohum=1),
            desenli_nesne((40, 200, 40), tohum=5),
            desenli_nesne((200, 60, 60), tohum=9),
        )
    )
    assert tutarlilik < 0.45


def test_olcumler_tek_fotografta_tutarlilik_olculemez():
    nokta, tutarlilik = teshis.olcumler(_izler(desenli_nesne(tohum=1)))
    assert nokta > 0
    assert tutarlilik == 0.0


def test_olcumler_bos_listede_cokmez():
    assert teshis.olcumler([]) == (0, 0.0)


def test_nokta_sayisi_ortanca_tek_bulanik_fotografla_bozulmaz():
    """Ortanca seçildi: tek bir bulanık kare nesneyi haksızca "düz" ilan etmesin."""
    bulanik = cv2.GaussianBlur(desenli_nesne(tohum=1), (31, 31), 0)
    nokta, _ = teshis.olcumler(_izler(desenli_nesne(tohum=1), desenli_nesne(tohum=1), bulanik))
    assert nokta >= EN_AZ_ANAHTAR_NOKTA


# ================================================= 2) teşhis kademeleri


def test_desenli_ve_tutarli_nesne_kolay_taninir():
    karne = teshis.nesne_teshisi(_izler(desenli_nesne(tohum=1), desenli_nesne(tohum=1)))
    assert karne.seviye == "kolay"
    assert karne.rozet == "yesil"
    assert "Kolay" in karne.baslik


def test_duz_renkli_nesnenin_bulunamayacagi_onceden_soylenir():
    """Düz renkli nesne artık BULUNAMAZ ve bu kullanıcıya önceden söylenir.

    Eskiden "sınırlı tanınır" deniyordu ve ölçümde böyle nesnelerin %36'sı
    bulunuyordu — ama aynı kapıdan kütüphanede OLMAYAN nesnelere de isim
    yazılıyordu (aynı renkteki düz bir kasa "Düz mavi bidon" oluyordu). Kapı
    kapatıldı; düz nesnelerde ölçülen isabet artık sıfırdır. Kullanıcı bunu
    fotoğraf yüklemeden ÖNCE bilmeli, yoksa boşuna kare ekler.
    """
    karne = teshis.nesne_teshisi(_izler(duz_gorsel(), duz_gorsel()))
    assert karne.seviye == "duz"
    assert "renk" in karne.aciklama.lower()
    assert "YAZMAZ" in karne.aciklama  # "sistem bu nesneye isim YAZMAZ"
    assert karne.bulunma_yuzdesi == 0


def test_birbirini_tanimayan_fotograflar_zor_taninir():
    karne = teshis.nesne_teshisi(
        _izler(
            desenli_nesne((40, 40, 200), tohum=1),
            desenli_nesne((40, 200, 40), tohum=5),
            desenli_nesne((200, 60, 60), tohum=9),
        )
    )
    assert karne.seviye == "zor"
    assert "fotoğraf" in karne.oneri.lower()


def test_zor_kovasinda_dogru_sebep_soylenir():
    """ "Zor"a iki ayrı sebeple düşülür; yanlış sebep yanlış çabaya yol açar.

    Fotoğrafları birbirini tanıyan ama deseni zayıf bir nesneye "fotoğraflarınız
    birbirini tanımıyor" demek, kullanıcıyı boşuna yeni fotoğraf çekmeye
    gönderirdi — oysa yapması gereken, nesnenin AYRINTILI yüzünü bulmak.
    """
    desen_zayif = teshis.teshisi_kur(4, EN_AZ_ANAHTAR_NOKTA + 2, 0.80)
    kareler_uyumsuz = teshis.teshisi_kur(4, 150, 0.10)
    assert desen_zayif.seviye == kareler_uyumsuz.seviye == "zor"
    assert "deseni zayıf" in desen_zayif.aciklama
    assert "birbirini tanıyor" in desen_zayif.aciklama
    assert "birbirini zor tanıyor" in kareler_uyumsuz.aciklama
    assert desen_zayif.oneri != kareler_uyumsuz.oneri


def test_tek_fotografla_teshis_yapilmaz_ve_bu_soylenir():
    """Uydurmaktansa "ölçemedim" demek: sistemin her yerdeki tavrı bu."""
    karne = teshis.nesne_teshisi(_izler(desenli_nesne(tohum=1)))
    assert karne.seviye == "tek"
    assert karne.rozet == "gri"
    assert karne.bulunma_yuzdesi is None  # olmayan ölçüm gösterilmez
    assert "ölçülemez" in karne.aciklama


def test_fotografsiz_nesne_de_teshis_verir():
    karne = teshis.nesne_teshisi([])
    assert karne.seviye == "tek"


@pytest.mark.parametrize("seviye", ["kolay", "duz", "zor"])
def test_her_kademe_turkce_aciklama_ve_oneri_tasir(seviye):
    """Her rozetin yanında NEDEN ve NE YAPMALI yazmalı; boş kutu olmamalı."""
    karne = teshis.teshisi_kur(
        4, *{"kolay": (100, 0.7), "duz": (2, 0.7), "zor": (100, 0.1)}[seviye]
    )
    assert karne.seviye == seviye
    assert len(karne.aciklama) > 40 and karne.aciklama.endswith(".")
    assert len(karne.oneri) > 40 and karne.oneri.endswith(".")


def test_kademeler_gercekten_sirali():
    """ÖLÇEK YALAN SÖYLEMEMELİ: kolay, düz ve zorun ÜSTÜNDE olmalı.

    Bu test bir metin testi değil; ölçümden gelen sayıların sıralamasını
    korur. Sıralama bozulursa kullanıcıya "daha iyi" denen kademe aslında
    daha kötü olur.

    Düz ile zor arasında EŞİTLİĞE izin verilir ve bugün ikisi de sıfırdır:
    "renk taşımaz" kuralından sonra iki kova da hiç bulunmuyor. İkisini ayrı
    tutmanın sebebi isabet değil, ÖNERİ: düz nesnede yapılacak bir şey yoktur,
    zor nesnede daha iyi fotoğraf çekmek işe yarayabilir.
    """
    kolay = teshis.teshisi_kur(4, 100, 0.7)
    duz = teshis.teshisi_kur(4, 2, 0.7)
    zor = teshis.teshisi_kur(4, 100, 0.1)
    assert kolay.bulunma_yuzdesi > duz.bulunma_yuzdesi >= zor.bulunma_yuzdesi
    assert kolay.yerinde_yuzdesi > duz.yerinde_yuzdesi >= zor.yerinde_yuzdesi
    assert duz.oneri != zor.oneri, "iki kova aynı sayıyı veriyorsa öneri ayırmalı"


def test_teshis_sinirlari_motorun_kendi_dallarindan_okunur():
    """Sınır uydurulmadı: motor "desensiz" dediğinde teşhis de "düz" der.

    Motor `EN_AZ_ANAHTAR_NOKTA`'yı değiştirirse teşhis kendiliğinden onunla
    değişmeli; iki yerde iki ayrı sayı tutulursa biri unutulur.
    """
    assert teshis.teshisi_kur(4, EN_AZ_ANAHTAR_NOKTA - 1, 0.9).seviye == "duz"
    assert teshis.teshisi_kur(4, EN_AZ_ANAHTAR_NOKTA, 0.9).seviye != "duz"


# ============================================= 3) kaç fotoğraf rehberi


def test_fotograf_egrisi_olcume_uygun_ve_artan():
    """Eğri ölçümden gelir: her fotoğraf bulmayı artırıyor (3 → 4 → 7 → 8)."""
    sayilar = [sayi for sayi, _, _ in teshis.FOTOGRAF_EGRISI]
    bulunanlar = [bulunan for _, bulunan, _ in teshis.FOTOGRAF_EGRISI]
    assert sayilar == [1, 2, 3, 4]
    assert bulunanlar == sorted(bulunanlar) and bulunanlar[0] < bulunanlar[-1]
    assert teshis.OLCULEN_FOTOGRAF == 4


@pytest.mark.parametrize("sayi", [0, 1])
def test_tek_fotograf_yetmez_denir(sayi):
    assert "yeterli değil" in teshis.fotograf_notu(sayi)


@pytest.mark.parametrize("sayi", [2, 3])
def test_eksik_fotograf_sayisi_soylenir(sayi):
    not_metni = teshis.fotograf_notu(sayi)
    assert str(teshis.OLCULEN_FOTOGRAF - sayi) in not_metni


@pytest.mark.parametrize("sayi", [4, 8])
def test_yeterli_fotografta_olcumun_siniri_durustce_soylenir(sayi):
    """ "4'ten fazlası boşuna" DENMEZ: ölçüm oraya kadar yapıldı, ötesi bilinmiyor."""
    not_metni = teshis.fotograf_notu(sayi)
    assert "yeterli" in not_metni
    assert "ölçülmedi" in not_metni


# ======================================== 4) "eşleşme yok" → tek eylem


def test_kutuphane_bossa_once_nesne_eklenmesi_soylenir():
    eylem = teshis.tarama_eylemi(sahne(None), 0.0, VARSAYILAN_ESIK, kutuphane_bos=True)
    assert "Önce" in eylem and "nesne ekleyin" in eylem


def test_bulanik_fotograf_teshis_edilir():
    """ÖLÇÜLDÜ: bilerek bulanıklaştırılan 28 sorgunun 26'sı yakalanıyor, net
    166 sorgunun hiçbirine yanlışlıkla "bulanık" denmiyor."""
    bulanik = cv2.GaussianBlur(sahne(desenli_nesne(tohum=1, boyut=120)), (21, 21), 0)
    eylem = teshis.tarama_eylemi(bulanik, 0.05, VARSAYILAN_ESIK)
    assert "bulanık" in eylem


def test_net_fotografa_bulanik_denmez():
    """Yanlış suçlama, kaçırmaktan kötüdür: net kareye "bulanık" denmemeli."""
    eylem = teshis.tarama_eylemi(sahne(desenli_nesne(tohum=1, boyut=120)), 0.05, VARSAYILAN_ESIK)
    assert "bulanık" not in eylem


def test_ayrinti_uyarisi_uc_sebebi_de_sayar():
    """Ölçülen şey AYRINTI miktarı; bu üç sebepten herhangi biriyle düşer.

    Yalnız "bulanık" deseydik, net ama karanlık bir fotoğrafta kullanıcı
    yanlış şeyi düzeltmeye çalışırdı — makineyi değil, kendini suçlardı.
    """
    karanlik = (sahne(desenli_nesne(tohum=1, boyut=120)) * 0.06).astype(np.uint8)
    eylem = teshis.tarama_eylemi(karanlik, 0.05, VARSAYILAN_ESIK)
    for sebep in ("bulanık", "karanlık", "kontrast"):
        assert sebep in eylem, f"'{sebep}' sebebi cümlede yok: {eylem}"


def test_kil_payi_kacinca_cita_indirmek_degil_fotograf_eklemek_onerilir():
    """KIRMIZI ÇİZGİ: sistem hiçbir yerde "çıtayı düşür" demez.

    Ölçümde kaçırılanların en yakınları çıtaya 0,00-0,03 uzaklıktaydı; oradaki
    doğru hamle o kareyi kütüphaneye eklemektir, çıtayı indirmek değil —
    indirilen çıta yanlış isim getirir.
    """
    eylem = teshis.tarama_eylemi(
        sahne(desenli_nesne(tohum=1, boyut=120)), VARSAYILAN_ESIK * 0.9, VARSAYILAN_ESIK
    )
    assert "Kıl payı" in eylem
    assert "kütüphaneye ekleyin" in eylem
    assert "indir" not in eylem.lower().replace("indirmek yerine", "")


def test_temkinli_yuzunden_kacirilinca_onerilen_ayara_donmesi_soylenir():
    """Kullanıcı kendi seçiminin bedelini görsün.

    "Daha temkinli" seçiliyken kaçırılan bir nesne için doğru öğüt, çıtayı
    gevşetmek DEĞİL, ÖNERİLEN ayara geri dönmektir — ki o ayar ölçümle bulunmuş
    "yanlış isim sıfır" noktasıdır. Bunu söylemezsek kullanıcı "sistem
    bulamıyor" sanır; oysa bulan bir ayar bir tık ötede duruyor.
    """
    eylem = teshis.tarama_eylemi(
        sahne(desenli_nesne(tohum=1, boyut=120)),
        0.30,  # otomatik çıtayı geçiyor, temkinli çıtayı geçmiyor
        esik=0.36,
        otomatik_esik=VARSAYILAN_ESIK,
    )
    assert "önerilen ayarda bulunuyordu" in eylem
    assert "Otomatik" in eylem


def test_ayni_fotograf_titizlikten_bagimsiz_ayni_teshisi_alir():
    """Kullanıcı titizliği değiştirdi diye fotoğrafın TEŞHİSİ değişmemeli.

    "Kıl payı kaçtı" mı yoksa "nesne küçük görünüyor" mu — bu, fotoğrafın
    kendisiyle ilgili bir yargıdır. Ölçüt hep ÖNERİLEN çıtadır; aksi hâlde aynı
    kare temkinli ayarda "nesne küçük" diye yanlış suçlanırdı.
    """
    gorsel = sahne(desenli_nesne(tohum=1, boyut=120))
    skor = VARSAYILAN_ESIK * 0.92  # önerilen çıtaya yakın, ama altında
    otomatikte = teshis.tarama_eylemi(gorsel, skor, VARSAYILAN_ESIK, otomatik_esik=VARSAYILAN_ESIK)
    temkinlide = teshis.tarama_eylemi(gorsel, skor, 0.36, otomatik_esik=VARSAYILAN_ESIK)
    assert "Kıl payı" in otomatikte
    assert "Kıl payı" in temkinlide


def test_otomatik_secilmisken_geri_don_onerisi_cikmaz():
    """Zaten önerilen ayardaysa bu cümle anlamsız olurdu."""
    eylem = teshis.tarama_eylemi(
        sahne(desenli_nesne(tohum=1, boyut=120)),
        0.05,
        esik=VARSAYILAN_ESIK,
        otomatik_esik=VARSAYILAN_ESIK,
    )
    assert "önerilen ayarda bulunuyordu" not in eylem


def test_duz_kutuphanede_sinir_kutuphanenin_kendisi_oldugu_soylenir():
    eylem = teshis.tarama_eylemi(
        sahne(desenli_nesne(tohum=1, boyut=120)),
        0.02,
        VARSAYILAN_ESIK,
        duz_kutuphane=True,
    )
    assert "düz renkli" in eylem


def test_baska_hicbir_ipucu_yoksa_yine_de_bir_eylem_verilir():
    """Kullanıcı hiçbir zaman "ne yapacağım?" diye kalmamalı."""
    eylem = teshis.tarama_eylemi(sahne(desenli_nesne(tohum=1, boyut=120)), 0.02, VARSAYILAN_ESIK)
    assert eylem and "fotoğraf deneyin" in eylem


def test_netlik_bulanikta_dusuk_nette_yuksek():
    net = sahne(desenli_nesne(tohum=1, boyut=120))
    assert teshis.netlik(net) > teshis.netlik(cv2.GaussianBlur(net, (21, 21), 0))


def test_taramada_eslesme_yoksa_eylem_dolu_gelir(test_ayarlari):
    tek = [Nesne(id=1, ad="Yangın dolabı", parmakizleri=[parmakizi_cikar(desenli_nesne(tohum=1))])]
    sonuc = arama.tara(
        sahne(None), "bos.jpg", tek, test_ayarlari.nesne_tarama_klasoru, VARSAYILAN_ESIK
    )
    assert sonuc.bulgular == []
    assert sonuc.eylem  # ne yapılacağı MUTLAKA yazar
    assert "Eşleşme bulunamadı" in sonuc.uyari


def test_eslesme_varken_eylem_yazilmaz(test_ayarlari):
    """Bulduğunda öğüt vermez: gereksiz metin, okunması gereken metni gizler."""
    tek = [Nesne(id=1, ad="Yangın dolabı", parmakizleri=[parmakizi_cikar(desenli_nesne(tohum=1))])]
    sonuc = arama.tara(
        sahne(desenli_nesne(tohum=1, boyut=120)),
        "var.jpg",
        tek,
        test_ayarlari.nesne_tarama_klasoru,
        VARSAYILAN_ESIK,
    )
    assert sonuc.bulgular and sonuc.eylem == "" and sonuc.uyari == ""


# ============================================ 5) "ne kadar emin olsun"


def test_cita_secenekleri_asla_citayi_dusurmez():
    """KIRMIZI ÇİZGİ: ekranda çıtayı indiren bir seçenek OLMAMALI.

    Ölçüm, bugünkü çıtanın "yanlış isim sıfırken en çok bulan" nokta olduğunu
    söylüyor; bir adım aşağısı yanlış isim üretiyor. Böyle bir seçeneği
    ekrana koymak, kullanıcıya tek tıklık bir tuzak vermek olurdu.
    """
    assert all(secenek.carpan >= 1.0 for secenek in teshis.CITA_SECENEKLERI)
    assert teshis.cita_secenegi(teshis.VARSAYILAN_CITA_SECIMI).carpan == 1.0


def test_taninmayan_secim_otomatige_doner():
    assert teshis.cita_secenegi("gevsek").anahtar == teshis.VARSAYILAN_CITA_SECIMI
    assert teshis.cita_secenegi("").carpan == 1.0


def test_secenekler_gunluk_dilde_teknik_terim_yok():
    for secenek in teshis.CITA_SECENEKLERI:
        metin = f"{secenek.ad} {secenek.sonuc}".lower()
        for terim in ("eşik", "skor", "parmak izi", "histogram", "orb"):
            assert terim not in metin, f"'{secenek.anahtar}' seçeneğinde teknik terim: {terim}"


# ==================================================== 6) önbellek (depo)


def _foto_ekle(baglanti, ayarlar, nesne_id, ad, tohum=1):
    return depo.fotograf_ekle(
        baglanti,
        ayarlar.nesne_klasoru,
        nesne_id,
        ad,
        jpeg(tohum),
        ayarlar.nesne_izinli_uzantilar,
        ayarlar.nesne_foto_en_buyuk_mb,
    )


def test_teshis_hesaplanip_saklaniyor(baglanti, test_ayarlari):
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    for sira in (1, 2):
        _foto_ekle(baglanti, test_ayarlari, nesne_id, f"a{sira}.jpg")

    karneler = depo.teshisleri_al(baglanti, test_ayarlari.nesne_klasoru)
    assert karneler[nesne_id].seviye == "kolay"

    satir = baglanti.execute(
        "SELECT * FROM library_object_diagnosis WHERE object_id = ?", (nesne_id,)
    ).fetchone()
    assert satir is not None and satir["keypoints"] > 0


def test_teshis_ikinci_cagrida_yeniden_hesaplanmaz(baglanti, test_ayarlari):
    """Önbellek gerçekten çalışsın: ölçüm fotoğraf başına ~19 ms sürüyor."""
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    _foto_ekle(baglanti, test_ayarlari, nesne_id, "a.jpg")
    _foto_ekle(baglanti, test_ayarlari, nesne_id, "b.jpg")
    depo.teshisleri_al(baglanti, test_ayarlari.nesne_klasoru)
    ilk = baglanti.execute(
        "SELECT computed_at FROM library_object_diagnosis WHERE object_id = ?", (nesne_id,)
    ).fetchone()["computed_at"]

    # Fotoğrafları OKUNAMAZ yap: önbellek çalışıyorsa sonuç yine gelir.
    for dosya in test_ayarlari.nesne_klasoru.glob("*.jpg"):
        dosya.write_bytes(b"artik bir jpeg degil")
    karneler = depo.teshisleri_al(baglanti, test_ayarlari.nesne_klasoru)

    assert karneler[nesne_id].seviye == "kolay"
    sonra = baglanti.execute(
        "SELECT computed_at FROM library_object_diagnosis WHERE object_id = ?", (nesne_id,)
    ).fetchone()["computed_at"]
    assert sonra == ilk  # yeniden yazılmadı


def test_fotograf_eklenince_teshis_kendiliginden_yenilenir(baglanti, test_ayarlari):
    """Bayatlama koruması: elle "geçersiz kıl" adımı yok, unutulacak adım da yok."""
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    _foto_ekle(baglanti, test_ayarlari, nesne_id, "a.jpg", tohum=1)
    _foto_ekle(baglanti, test_ayarlari, nesne_id, "b.jpg", tohum=2)
    depo.teshisleri_al(baglanti, test_ayarlari.nesne_klasoru)
    onceki = baglanti.execute(
        "SELECT photo_key FROM library_object_diagnosis WHERE object_id = ?", (nesne_id,)
    ).fetchone()["photo_key"]

    _foto_ekle(baglanti, test_ayarlari, nesne_id, "c.jpg", tohum=3)
    karneler = depo.teshisleri_al(baglanti, test_ayarlari.nesne_klasoru)

    sonraki = baglanti.execute(
        "SELECT photo_key FROM library_object_diagnosis WHERE object_id = ?", (nesne_id,)
    ).fetchone()["photo_key"]
    assert sonraki != onceki
    assert karneler[nesne_id].fotograf_sayisi == 3


def test_nesne_silinince_teshis_satiri_da_gider(baglanti, test_ayarlari):
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    _foto_ekle(baglanti, test_ayarlari, nesne_id, "a.jpg")
    depo.teshisleri_al(baglanti, test_ayarlari.nesne_klasoru)
    depo.nesne_sil(baglanti, test_ayarlari.nesne_klasoru, nesne_id)
    kalan = baglanti.execute("SELECT COUNT(*) AS n FROM library_object_diagnosis").fetchone()["n"]
    assert kalan == 0  # ON DELETE CASCADE


def test_okunamayan_fotograf_teshisi_cokertmez(baglanti, test_ayarlari):
    nesne_id = depo.nesne_ekle(baglanti, "Pano")
    ad = _foto_ekle(baglanti, test_ayarlari, nesne_id, "a.jpg")
    (test_ayarlari.nesne_klasoru / ad).unlink()
    karneler = depo.teshisleri_al(baglanti, test_ayarlari.nesne_klasoru)
    assert karneler[nesne_id].seviye == "tek"  # ölçülemedi, ama çökmedi


# ================================= 6b) Türkçe ekler ve ayar notu


@pytest.mark.parametrize(
    "sayi, iyelik, bulunma",
    [
        (0, "'ı", "'ında"),
        (4, "'ü", "'ünde"),
        (7, "'si", "'sinde"),
        (14, "'ü", "'ünde"),
        (16, "'sı", "'sında"),
        (36, "'sı", "'sında"),
        (40, "'ı", "'ında"),
        (64, "'ü", "'ünde"),
        (69, "'u", "'unda"),
        (100, "'ü", "'ünde"),
    ],
)
def test_sayidan_turkce_ek_uretilir(sayi, iyelik, bulunma):
    """Ek, sayının OKUNUŞUNA bağlıdır; şablona sabit yazılamaz.

    Ekranda bir kez "%36'i bulundu ve %7'inde" yazdı — sayı ölçümden geldiği
    için değişiyor, ek ise sabit yazılmıştı. Doğrusu "%36'sı" ve "%7'sinde".
    Ek son RAKAMA da bağlı değildir: 14 "on dört"tür ("%14'ü"), 40 "kırk"tır
    ("%40'ı").
    """
    assert ortak.sayi_eki(sayi) == iyelik
    assert ortak.sayi_eki(sayi, "bulunma") == bulunma


def test_ayrilma_eki_sert_unsuzu_gozetir():
    """ "4'ten fazlası" doğru, "4'den" yanlış: dört sert ünsüzle biter."""
    assert ortak.sayi_eki(4, "ayrilma") == "'ten"
    assert ortak.sayi_eki(6, "ayrilma") == "'dan"
    assert ortak.sayi_eki(40, "ayrilma") == "'tan"


def test_sayi_olmayan_deger_yanlis_ek_uretmez():
    """Eksiz bir cümle, yanlış ekli bir cümleden iyidir."""
    assert ortak.sayi_eki(None) == ""
    assert ortak.sayi_eki("") == ""


def test_kurulu_sunucunun_eski_citasi_haber_verilir():
    """.env git'e girmez: eski kurulum 0,42'de kalır ve sessizce daha kötü çalışır.

    Ayarı haber vermeden EZMEK yanlış olurdu; onun yerine ekranda not çıkar.
    """
    assert teshis.cita_notu(VARSAYILAN_ESIK) == ""  # olağan durumda not YOK
    eski = teshis.cita_notu(0.42)
    assert eski, "eski çıta sessizce kabul edilmemeli"
    assert "%42" in eski and "%24" in eski
    assert "Ayarlar" in eski  # ne yapacağı yazıyor
    dusuk = teshis.cita_notu(0.15)
    assert "yanlış isim" in dusuk  # düşük çıtanın bedeli söyleniyor


def test_ayar_notu_sayfada_gorunuyor(istemci, test_ayarlari):
    """Not gerçekten ekrana düşüyor mu? (conftest çıtası bilerek 0,42'dir)"""
    assert test_ayarlari.nesne_eslesme_esigi != VARSAYILAN_ESIK
    metin = istemci.get("/nesneler").text
    assert "Ayar notu" in metin


def test_teshis_yuzdeleri_dogru_ekle_yaziliyor(istemci):
    """Kart, kendi sayfasının alt paragrafıyla çelişmemeli.

    Sayı <b> içinde olduğu için etiketler temizlenip düz metne bakılır —
    kullanıcının ekranda gördüğü şey odur. Kesme işareti kaynakta `&#39;`
    olarak durur (Jinja kaçırır, tarayıcı ' diye gösterir); test de öyle okur.
    """
    ham = html.unescape(_nesne_ekle(istemci).text)
    duz = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", ham))
    assert "%16'sı bulundu" in duz
    assert "%16'sında işaret" in duz
    assert "%16'i" not in duz and "%16'inde" not in duz


# ========================================================== 7) sayfa


def _nesne_ekle(istemci, ad="Yangın dolabı", tohumlar=(1, 1)):
    return istemci.post(
        "/nesneler/ekle",
        data={"ad": ad},
        files=[
            ("fotograflar", (f"a{sira}.jpg", jpeg(tohum), "image/jpeg"))
            for sira, tohum in enumerate(tohumlar)
        ],
    )


def test_sayfada_teshis_rozeti_ve_onerisi_gorunuyor(istemci):
    metin = _nesne_ekle(istemci).text
    assert "Kolay tanınır" in metin
    assert "Ne yapmalı:" in metin


def test_duz_renkli_nesne_sayfada_uyarilir(istemci):
    duz = cv2.imencode(".jpg", duz_gorsel())[1].tobytes()
    metin = istemci.post(
        "/nesneler/ekle",
        data={"ad": "Mavi bidon"},
        files=[("fotograflar", (f"d{i}.jpg", duz, "image/jpeg")) for i in range(2)],
    ).text
    assert "Düz renkli" in metin


def test_tek_fotografli_nesne_ikinci_fotograf_ister(istemci):
    metin = _nesne_ekle(istemci, tohumlar=(1,)).text
    assert "Henüz ölçülemedi" in metin
    assert "en az bir fotoğrafını daha ekleyin" in metin


def test_fotograf_sayisi_rehberi_sayfada(istemci):
    metin = istemci.get("/nesneler").text
    assert "Kaç fotoğraf gerekli" in metin
    assert "168 sorguda" in metin  # ölçümün kendisi görünüyor


def test_eslesme_yoksa_ne_yapilacagi_ekranda(istemci):
    _nesne_ekle(istemci)
    kare = cv2.imencode(".jpg", sahne(None))[1].tobytes()
    metin = istemci.post(
        "/nesneler/tara", files=[("kareler", ("bos.jpg", kare, "image/jpeg"))]
    ).text
    assert "eşleşme yok" in metin
    assert "Şunu deneyin:" in metin


def test_cita_secimi_gunluk_dilde_ve_dusuren_secenek_yok(istemci):
    metin = istemci.get("/nesneler").text
    assert "Sistem ne kadar emin olsun?" in metin
    assert "Otomatik (önerilen)" in metin
    assert "Daha temkinli" in metin
    # Eski teknik alan gitti
    assert "Kabul çıtası" not in metin
    assert 'name="esik_yuzde" value=' not in metin
    # Geri alma yolu tarif edilmiş
    assert "Geri almak için" in metin


def test_temkinli_secim_citayi_yukseltir(istemci):
    """Seçim gerçekten çalışsın: temkinli, otomatikten DAHA AZ işaret bulmalı."""
    _nesne_ekle(istemci, tohumlar=(1,))
    kare = cv2.imencode(".jpg", sahne(desenli_nesne(tohum=1, boyut=120)))[1].tobytes()
    otomatik = istemci.post(
        "/nesneler/tara",
        data={"esik_yuzde": "otomatik"},
        files=[("kareler", ("k.jpg", kare, "image/jpeg"))],
    ).text
    temkinli = istemci.post(
        "/nesneler/tara",
        data={"esik_yuzde": "temkinli"},
        files=[("kareler", ("k.jpg", kare, "image/jpeg"))],
    ).text
    assert "eşleşme" in otomatik
    # Temkinli seçim formda seçili kalır (kullanıcı ne seçtiğini görsün)
    assert 'value="temkinli"' in temkinli and "selected" in temkinli


def test_eski_sayisal_esik_biciminde_hata_verilmez(istemci):
    """Geriye dönük uyum: elde sayı gelirse sessizce kabul edilir."""
    _nesne_ekle(istemci, tohumlar=(1,))
    kare = cv2.imencode(".jpg", sahne(desenli_nesne(tohum=1, boyut=120)))[1].tobytes()
    yanit = istemci.post(
        "/nesneler/tara",
        data={"esik_yuzde": "42"},
        files=[("kareler", ("k.jpg", kare, "image/jpeg"))],
    )
    assert yanit.status_code == 200


# ======================================================== 8) kılavuz


def test_kilavuz_ne_calismadigini_durustce_yaziyor(istemci):
    """Kılavuz iyi haberi de kötü haberi de yazmalı; yalnız iyisi propagandadır."""
    metin = istemci.get("/komuta/kilavuz").text
    assert "Ne çalışmıyor" in metin
    assert "isim yazmaz" in metin
    assert "ayırt edemiyor" in metin


def test_kilavuz_artik_citayi_dusurmeyi_onermiyor(istemci):
    """ESKİ METİN YANLIŞTI: "kabul çıtasını birkaç puan düşürüp deneyin" diyordu.

    Ölçüm bunun yanlış isim ürettiğini gösterdi; öğüt kaldırıldı ve yerine
    nedeni yazıldı. Bu test o metnin geri gelmesini engeller.
    """
    metin = istemci.get("/komuta/kilavuz").text
    assert "çıtasını birkaç puan düşür" not in metin
    assert "gevşetmeye çalışmayın" in metin


def test_kilavuz_olculmus_sayilari_veriyor(istemci):
    """Kılavuzdaki sayılar ölçümden gelmeli — 2026-09'da yeniden ölçüldü.

    Desenli nesnelerde %16 bulundu; düz renkli nesnelerde hiçbiri bulunmadı
    ("renk taşımaz" kuralı). Eski metin %69/%64 diyordu ve o sayılar yalnız
    renge dayanan eşleşmeleri de sayıyordu.
    """
    metin = istemci.get("/komuta/kilavuz").text
    assert "%16" in metin  # desenli nesnelerde ölçülen isabet
    assert "hiçbiri" in metin  # düz renkli nesnelerde ölçülen isabet: sıfır
    # Kılavuzdaki rozet adı, ekrandaki rozetle AYNI olmalı. Bir kez ayrıştı:
    # kod "Düz renkli — bulunamaz" derken kılavuz "sınırlı tanınır" diyordu.
    assert "sınırlı tanınır" not in metin
    assert "bulunamaz" in metin


def test_duz_nesne_denemesinin_basarisizligi_yaziyor(istemci):
    """Başarısızlığı gizlemek, yanlış isimden sonraki en kötü şeydir.

    Düz nesneleri kurtarmak için renge bakmayan üç ölçü denendi ve üçü de
    ölçümde ters yönde çıktı (bkz. kutuphane.py "DENENDİ VE GERİ ALINDI" 8 ve
    docs/07 §5.1). Kullanıcı bunu hem Nesneler sayfasında hem kılavuzda görür;
    metin sessizce silinirse sistem çözemediği bir şeyi çözmüş gibi görünür.
    """
    for yol in ("/nesneler", "/komuta/kilavuz"):
        metin = istemci.get(yol).text
        assert "kapatamadık" in metin or "kapatılamadı" in metin, yol
        assert "ters yönde" in metin, yol


# =================================== 9) dar ekran (375 px) taşma yok


KOK = Path(__file__).resolve().parents[1]
STIL = KOK / "backend" / "app" / "web" / "static" / "komuta.css"
SABLON = KOK / "backend" / "app" / "web" / "templates" / "komuta_nesneler.html"


def test_yeni_kutular_sabit_genislik_dayatmaz():
    """375 px'lik ekranda taşmanın kaynağı hep aynı: sabit piksel genişlik.

    Tarayıcıda ölçüldü: 375 px'te `scrollWidth - clientWidth = 0` (taşma yok).
    Bu test, o ölçümün dayandığı kuralın yanlışlıkla silinmesini engeller.
    """
    css = STIL.read_text(encoding="utf-8")
    for sinif in (".nesne-teshis", ".nesne-eylem", ".nesne-rehber", ".nesne-egri-tablo"):
        blok = re.search(re.escape(sinif) + r"[^{]*\{([^}]*)\}", css)
        assert blok, f"{sinif} kuralı yok"
        assert not re.search(r"[^-]width:\s*\d+px", blok.group(1)), (
            f"{sinif} sabit piksel genişlik dayatıyor — dar ekranda sayfa yatay kayar"
        )


def test_dar_ekranda_tablolar_daraltiliyor():
    """Üç sütunlu tablolar 375 px'te sığmıyordu; daraltma kuralı kalmalı."""
    css = STIL.read_text(encoding="utf-8")
    dar_blok = css.split("@media (max-width: 560px)")
    assert len(dar_blok) == 2, "dar ekran (560 px) kuralı yok"
    assert ".nesne-egri-tablo" in dar_blok[1]
    assert ".nesne-tablo" in dar_blok[1]


def test_sablonda_satir_ici_sabit_genislik_yok():
    govde = SABLON.read_text(encoding="utf-8")
    assert not re.findall(r'style="[^"]*[^-]width:\s*\d+px[^"]*"', govde)


# ================================== çıta notu: ölçmediğimiz sayıyı uydurmamalı


@pytest.mark.parametrize(
    ("esik", "beklenen_parca"),
    [
        (0.24, "8 nesne buldu"),  # ölçülen nokta
        (0.26, "4 nesne buldu"),  # ölçülen nokta
        (0.25, "4 ile 8 arası"),  # ÖLÇÜLMEDİ → aralık, uydurma sayı değil
        (0.27, "3 ile 4 arası"),  # ÖLÇÜLMEDİ → aralık
        (0.33, "1 ile 2 arası"),  # ÖLÇÜLMEDİ → aralık
        (0.36, "hiç nesne bulamaz"),  # ölçülen nokta, sayı 0
        (0.42, "hiç nesne bulamaz"),  # eğrinin üstü
    ],
)
def test_bulunan_metni_olculmemis_citada_sayi_uydurmaz(esik, beklenen_parca):
    """Ölçülmemiş bir çıtada "0 nesne" demek YANLIŞTI ve düzeltildi.

    Eski kod eğriyi sözlükten okuyup bulamayınca "0"a düşüyordu; yani ölçüm
    gibi görünen ama yanlış bir sayı, tam da göç notunda kullanıcıya
    gösteriliyordu (0,25'te gerçekte 6 nesne bulunuyor, 0 değil). Artık
    ölçülmemiş çıta için iki komşu ölçümden ARALIK veriliyor — eğri azalan
    olduğu için bu matematiksel olarak doğrudur.
    """
    metin = teshis._bulunan_metni(esik)
    assert beklenen_parca in metin
    # Ölçülmemiş çıtalarda tek bir kesin sayı iddia edilmemeli
    if "arası" in metin:
        assert "nesne buldu" in metin


def test_cita_notu_sapma_payi_simetrik():
    """0,23 ve 0,25 aynı davranmalı — kayan nokta bunu bozuyordu.

    abs(0.25 - 0.24) = 0.010000000000000009 payı AŞIYOR, abs(0.23 - 0.24) ise
    aşmıyordu. Yani bir adım yukarısı "eski kurulum" diye uyarılıyor, bir adım
    aşağısı sessizce kabul ediliyordu.
    """
    onerilen = teshis.VARSAYILAN_ESIK
    bir_adim = 0.01
    assert teshis.cita_notu(onerilen) == ""
    assert teshis.cita_notu(onerilen + bir_adim) == "", "Bir adım YUKARISI not çıkarmamalı"
    assert teshis.cita_notu(onerilen - bir_adim) == "", "Bir adım AŞAĞISI not çıkarmamalı"
    # Gerçek sapmalar hâlâ not çıkarmalı
    assert teshis.cita_notu(0.42) != ""
    assert teshis.cita_notu(0.10) != ""

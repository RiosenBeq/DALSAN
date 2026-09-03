"""Kıyas takımını çalıştırır ve ÖZET TABLOLARI basar.

Çalıştırma (depo kökünden):

    .venv/bin/python -m tests.nesne_kiyas              # tam takım
    .venv/bin/python -m tests.nesne_kiyas --kucuk      # hızlı, küçük takım
    .venv/bin/python -m tests.nesne_kiyas --gorseller veri/kiyas

Motoru DEĞİŞTİRMEZ; yalnız ölçer. Çıktıdaki üç sayı şunlardır:
isabet yüzdesi, yanlış isim adedi (SIFIR olmalı) ve "eşleşme yok" adedi.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Depo kökündeki `backend/` klasörü uygulamanın paket köküdür; buradan
# çalıştırıldığında sys.path'e o eklenmelidir (pytest bunu pyproject.toml
# üzerinden kendisi yapar).
_KOK = Path(__file__).resolve().parents[2]
if str(_KOK / "backend") not in sys.path:
    sys.path.insert(0, str(_KOK / "backend"))

from app.nesneler.kutuphane import EN_AZ_ANAHTAR_NOKTA, VARSAYILAN_ESIK  # noqa: E402

from . import olcum, takim  # noqa: E402

_CIZGI = "─" * 78
# Yanlış isim dökümünde basılan en çok satır: liste yüzlerce olabiliyor ve
# kullanıcı için önemli olan en yüksek skorlular ile TOPLAM sayıdır.
_EN_COK_YANLIS_SATIR = 15


def main() -> int:
    ayristirici = argparse.ArgumentParser(
        prog="python -m tests.nesne_kiyas",
        description="Nesne kütüphanesinin bugünkü isabetini ve yanlış isim sayısını ölçer.",
    )
    ayristirici.add_argument(
        "--kucuk", action="store_true", help="Küçük takım (hızlı deneme; pytest kapısıyla aynı)"
    )
    ayristirici.add_argument(
        "--esik",
        type=float,
        default=VARSAYILAN_ESIK,
        help=f"Kırılımların gösterileceği eşik (varsayılan {VARSAYILAN_ESIK})",
    )
    ayristirici.add_argument(
        "--gorseller", metavar="KLASOR", help="Takımın bütün fotoğraflarını bu klasöre yazar"
    )
    secenekler = ayristirici.parse_args()

    baslangic = time.time()
    print(_CIZGI)
    print("NESNE KÜTÜPHANESİ — KIYAS ÖLÇÜMÜ (motor değiştirilmedi, yalnız ölçüldü)")
    print(_CIZGI)

    kiyas = takim.takim_olustur(kucuk=secenekler.kucuk)
    print(
        f"Takım: {len(kiyas.nesneler)} nesne × 4 referans fotoğraf, "
        f"{len(kiyas.sorgular)} sorgu fotoğrafı "
        f"({sum(1 for s in kiyas.sorgular if s.dogru_ad is None)} tanesi negatif)."
    )
    if secenekler.gorseller:
        klasor = Path(secenekler.gorseller)
        adet = takim.gorselleri_yaz(kiyas, klasor)
        print(f"Görüntüler yazıldı: {klasor} ({adet} dosya)")

    kayitlar = olcum.olc(kiyas, ilerleme=_ilerleme, esik=secenekler.esik)
    print(f"\nTarama süresi: {time.time() - baslangic:.0f} saniye\n")

    _bugunku_sayilar(kayitlar, secenekler.esik)
    ozetler = olcum.esik_taramasi(kayitlar)
    _esik_egrisi(ozetler)
    en_iyi = olcum.en_iyi_guvenli_esik(ozetler)
    _zorluk_tablosu(kayitlar, secenekler.esik, "BUGÜNKÜ EŞİKTE")
    if en_iyi is not None and abs(en_iyi.esik - secenekler.esik) > 1e-9:
        _zorluk_tablosu(kayitlar, en_iyi.esik, "YANLIŞ İSİMSİZ EN İYİ EŞİKTE")
    _kacanlar(kayitlar, secenekler.esik)
    _yanlis_isimler(kayitlar, secenekler.esik)
    _desensiz_kaniti(kayitlar)
    _sert_vakalar(kayitlar)
    _sonuc_cumlesi(en_iyi, secenekler.esik, ozetler)
    return 0


def _ilerleme(sira: int, toplam: int, _kayit: olcum.SorguKaydi) -> None:
    print(f"\r  taranıyor… {sira}/{toplam}", end="", flush=True)
    if sira == toplam:
        print()


def _bugunku_sayilar(kayitlar: list[olcum.SorguKaydi], esik: float) -> None:
    ozet = olcum.esik_ozeti(kayitlar, esik)
    print(_CIZGI)
    print(f"1) BUGÜNKÜ TABAN SKOR  (eşik = {esik:.2f})")
    print(_CIZGI)
    print(f"  İsabet          : %{ozet.isabet_yuzde:.1f}  ({ozet.isabet}/{ozet.pozitif} sorgu)")
    print(
        f"  ...işaret nesnenin üstünde: %{ozet.yerinde_yuzde:.1f} "
        f"({ozet.yerinde}/{ozet.pozitif}) — gerisinde ad doğru, yer yanlış"
    )
    print(f"  YANLIŞ İSİM     : {ozet.yanlis_isimli_bulgu} adet   (sıfır olmalı)")
    print(
        f"    ...kütüphane DIŞI: {ozet.kutuphane_disi_yanlis} adet  "
        f"(olmayan bir şeye ad yazıldı — {ozet.negatif} negatif sorgu içinde)"
    )
    print(
        f"    ...kütüphane İÇİ : {ozet.kutuphane_ici_yanlis} adet  "
        f"(A nesnesine B'nin adı yazıldı — {ozet.pozitif} pozitif sorgu içinde)"
    )
    print(f"  'Eşleşme yok'   : {ozet.eslesme_yok} sorgu  ({len(kayitlar)} sorgunun içinde)")


def _esik_egrisi(ozetler: list[olcum.EsikOzeti]) -> None:
    print()
    print(_CIZGI)
    print("2) EŞİK EĞRİSİ — çıtayı indirince ne kazanılır, ne kaybedilir?")
    print(_CIZGI)
    print("   eşik | isabet |  isabet  | yerinde | YANLIŞ | kütüph. | kütüph. | eşleşme")
    print("        |        |  sayısı  |         |  İSİM  |  DIŞI   |   İÇİ   |   yok")
    print("  ------+--------+----------+---------+--------+---------+---------+---------")
    for ozet in ozetler:
        isaret = "  <-- yanlış isim" if not ozet.guvenli else ""
        print(
            f"   {ozet.esik:.2f} | %{ozet.isabet_yuzde:5.1f} |"
            f" {ozet.isabet:3d}/{ozet.pozitif:<4d} | %{ozet.yerinde_yuzde:5.1f} |"
            f" {ozet.yanlis_isimli_bulgu:6d} |"
            f" {ozet.kutuphane_disi_yanlis:7d} | {ozet.kutuphane_ici_yanlis:7d} |"
            f" {ozet.eslesme_yok:7d}{isaret}"
        )


def _zorluk_tablosu(kayitlar: list[olcum.SorguKaydi], esik: float, baslik: str) -> None:
    print()
    print(_CIZGI)
    print(f"3) ZORLUK KIRILIMI — {baslik} (eşik = {esik:.2f})")
    print(_CIZGI)
    print(
        "  nesne türü                           | sorgu | isabet | yerinde | yanlış"
        " | en iyi skor  | ideal"
    )
    print(
        "                                       |       |        |         |  isim "
        " | ort. / en az | çerçeve"
    )
    print(
        "  -------------------------------------+-------+--------+---------+-------"
        "-+--------------+--------"
    )
    for ozet in olcum.zorluk_kirilimi(kayitlar, esik):
        ad = takim.ZORLUK_ADLARI[ozet.zorluk]
        bos = ozet.negatif
        isabet = "     —" if bos else f"%{ozet.isabet_yuzde:5.1f}"
        yerinde = "      —" if bos else f" %{ozet.yerinde_yuzde:5.1f}"
        print(
            f"  {ad:36s} | {ozet.toplam:5d} | {isabet} | {yerinde} | {ozet.yanlis_isim:6d} |"
            f"  {ozet.ortalama_dogru_skor:.2f} / {ozet.en_dusuk_dogru_skor:.2f} |"
            f"  {ozet.ortalama_ideal_skor:.2f}"
        )
    print("  (en iyi skor = doğru nesnenin o fotoğrafta aldığı en yüksek benzerlik;")
    print("   negatif satırda: kütüphanedeki nesnelerin aldığı en yüksek benzerlik.")
    print("   ideal çerçeve = pencere nesneyi tam çerçeveleseydi çıkacak skor;")
    print("   aradaki fark PENCERE IZGARASININ kaybıdır, motorun değil.)")


def _kacanlar(kayitlar: list[olcum.SorguKaydi], esik: float) -> None:
    kacan = olcum.kacirilanlar(kayitlar, esik)
    print()
    print(_CIZGI)
    print(f"4) KAÇIRILANLAR (eşik = {esik:.2f}) — en çok yaklaşan 12 tanesi")
    print(_CIZGI)
    if not kacan:
        print("  Yok: bütün pozitif sorgular bulundu.")
        return
    for ad, bozulma, skor in kacan[:12]:
        fark = esik - skor
        print(f"  {ad:26s} | {bozulma:20s} | skor {skor:.2f} (çıtaya {fark:.2f} kaldı)")
    print(f"  ... toplam {len(kacan)} kaçırılan sorgu.")


def _yanlis_isimler(kayitlar: list[olcum.SorguKaydi], esik: float) -> None:
    hatalar = olcum.yanlis_isimler(kayitlar, esik)
    print()
    print(_CIZGI)
    print(f"5) YANLIŞ İSİMLER (eşik = {esik:.2f}) — kırmızı çizgi")
    print(_CIZGI)
    if not hatalar:
        print("  YOK. Sistem bu eşikte hiçbir fotoğrafa yanlış isim yazmadı.")
        return
    for baslik, kutuphane_ici in (
        ("KÜTÜPHANE DIŞI — kütüphanede olmayan bir şeye isim yazıldı", False),
        ("KÜTÜPHANE İÇİ  — A nesnesine B nesnesinin adı yazıldı", True),
    ):
        grup = [hata for hata in hatalar if hata.kutuphane_ici == kutuphane_ici]
        print(f"\n  {baslik}: {len(grup)} adet")
        if not grup:
            print("    yok.")
            continue
        if len(grup) > _EN_COK_YANLIS_SATIR:
            print(f"    (en yüksek skorlu {_EN_COK_YANLIS_SATIR} tanesi gösteriliyor)")
        for hata in grup[:_EN_COK_YANLIS_SATIR]:
            yer = "işaret nesnenin üstünde" if hata.isaret_nesnenin_ustunde else "işaret zeminde"
            print(
                f"    '{hata.sorulan_metni}' sorulmuşken '{hata.yazilan}' yazıldı"
                f" | {hata.bozulma} | skor {hata.skor:.2f} | {yer}"
            )


# Sertleştirilmiş vakaların iki çıtada yan yana ölçüldüğü tablo. 0,24 bugünkü
# çıta, 0,42 ise eski motorun çıtasıdır; ikisi birden basılır ki "çıtayı geri
# yükseltmek deliği kapatır mı" sorusu tahminle değil sayıyla cevaplansın.
_SERT_ESIKLER = (0.24, 0.42)
# Raporda ayrı ayrı gösterilen sertleştirilmiş sorgu aileleri.
_SERT_AILELER = ("duz-yabanci", "desensiz-zemin")


def _desensiz_kaniti(kayitlar: list[olcum.SorguKaydi]) -> None:
    """Sertleştirilmiş zeminler motorun DÜZ-DÜZ dalına gerçekten giriyor mu?

    Bu tablo olmadan takım kör kalır: bir sorgunun 'desensiz' görünmesi yetmez,
    ORB'nin de orada nokta bulamıyor olması gerekir. Karşılaştırma için eski
    boş zemin sorguları da basılır.
    """
    print()
    print(_CIZGI)
    print("6) DESEN KANITI — sorgular motorun en zayıf dalına gerçekten giriyor mu?")
    print(_CIZGI)
    print(f"  Motor bir pencereyi 'desensiz' saymak için {EN_AZ_ANAHTAR_NOKTA} anahtar noktadan")
    print("  AZ nokta ister; ancak o zaman kararı yalnız renge bırakan dal çalışır.")
    print()
    print("  sorgu                                | tüm kare | desensiz pencere | ortanca")
    print("                                       |   ORB    |    / taranan     |  ORB")
    print("  -------------------------------------+----------+------------------+--------")
    for zorluk in ("desensiz-zemin", "negatif"):
        for bozulma, tam, desensiz, pencere, ortanca in olcum.desensiz_kaniti(kayitlar, zorluk):
            if zorluk == "negatif" and "boş zemin" not in bozulma:
                continue  # eski yabancı NESNELER değil, yalnız eski boş zeminler
            print(f"  {bozulma:36s} | {tam:8d} | {desensiz:7d} / {pencere:<6d} | {ortanca:6.1f}")
    print("  (üstteki altı satır sertleştirmeyle EKLENDİ; alttakiler eski boş zeminlerdir.")
    print("   Eski zeminlerin tam karesinde onlarca ORB noktası var — yani düz-düz dalına")
    print("   hiç girmiyorlar ve motorun en zayıf yanını hiç sınamıyorlardı.)")


def _sert_vakalar(kayitlar: list[olcum.SorguKaydi]) -> None:
    """Sertleştirilmiş vakaların iki çıtadaki tablosu."""
    print()
    print(_CIZGI)
    print("7) SERTLEŞTİRİLMİŞ VAKALAR — bugünkü motor, iki çıtada")
    print(_CIZGI)
    print("   çıta | yanlış isim | kütüph. | kütüph. | isabet  | yerinde | ad yazılan düz")
    print("        |   işaret    |  DIŞI   |   İÇİ   |         |         | yabancı sorgu")
    print("  ------+-------------+---------+---------+---------+---------+---------------")
    duz_sorgular = [kayit for kayit in kayitlar if kayit.sorgu.zorluk == "duz-yabanci"]
    for esik in _SERT_ESIKLER:
        ozet = olcum.esik_ozeti(kayitlar, esik)
        # SORGU sayısı (işaret sayısı değil): tek bir fotoğraf aynı adı taşıyan
        # birden çok kutu alabildiği için ikisi karıştırılırsa tablo yanıltır.
        duz = sum(1 for kayit in duz_sorgular if kayit.bulgular(esik))
        print(
            f"   {esik:.2f} | {ozet.yanlis_isimli_bulgu:11d} |"
            f" {ozet.kutuphane_disi_yanlis:7d} | {ozet.kutuphane_ici_yanlis:7d} |"
            f" {ozet.isabet:3d}/{ozet.pozitif:<4d}|"
            f" {ozet.yerinde:3d}/{ozet.pozitif:<4d}|"
            f" {duz:8d} / {len(duz_sorgular):<4d}"
        )
    print()
    print("  Yanlış adayın çıkabildiği EN YÜKSEK skor (eşikten bağımsız erken uyarı):")
    for zorluk in _SERT_AILELER + ("negatif", "benzer-renk"):
        tavan = olcum.zorluk_tavani(kayitlar, zorluk)
        print(f"    {takim.ZORLUK_ADLARI[zorluk]:36s} {tavan:.3f}")


def _sonuc_cumlesi(
    en_iyi: olcum.EsikOzeti | None, esik: float, ozetler: list[olcum.EsikOzeti]
) -> None:
    print()
    print(_CIZGI)
    print("8) SONUÇ")
    print(_CIZGI)
    bugun = next((o for o in ozetler if abs(o.esik - esik) < 1e-9), None)
    if bugun is not None:
        print(
            f"  Bugünkü eşikte ({esik:.2f}) isabet %{bugun.isabet_yuzde:.1f}, "
            f"yanlış isim {bugun.yanlis_isimli_bulgu}."
        )
    if en_iyi is None:
        print("  Taranan hiçbir eşikte yanlış isim sıfıra inmedi — önce bu düzeltilmeli.")
        return
    print(
        f"  Yanlış isim SIFIR kalırken en yüksek isabeti veren eşik: {en_iyi.esik:.2f} "
        f"→ isabet %{en_iyi.isabet_yuzde:.1f} ({en_iyi.isabet}/{en_iyi.pozitif}), "
        f"işareti nesnenin üstünde olanlar %{en_iyi.yerinde_yuzde:.1f}."
    )
    print("  Bir sonraki aşamanın yol haritası bu satırdır: isabeti buradan yukarı")
    print("  taşıyacak her değişiklik, yanlış ismi sıfırda tutmak zorundadır.")


if __name__ == "__main__":
    raise SystemExit(main())

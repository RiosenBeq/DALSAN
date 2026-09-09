# 07 — Yol Haritası

MVP'de **geliştirilmeyen**, mimarinin engellemediği başlıklar. Bir özellik MVP'den
çıkarıldığında buraya satır olarak eklenir — böylece hiçbir fikir kaybolmaz ama
hiçbiri erken kodlanmaz.

---

## 1. Phase 2 — MVP sonrası (aynı 3-4 kamera)

Sıralama beklenen faydaya göre.

| # | Başlık | Tetikleyici / gerekçe | Büyüklük |
|---|---|---|---|
| 1 | **Olay video klibi** (öncesi/sonrası 5+5 sn) | Yanlış alarm incelemesinde ve İSG eğitiminde snapshot'tan çok daha güçlü. En sık istenecek özellik. | Orta |
| 2 | **KKD geri besleme döngüsü** | MVP'nin "Yanlış alarm" işaretleri + snapshot'ları zaten veri seti. Kalan iş: periyodik yeniden eğitim betiği + model sürüm yönetimi. Precision'ı zamanla yükseltir. | Orta |
| 3 | **Raporlamanın kalanı: vardiya karşılaştırması ve eğilim** | Dönem raporu YAPILDI (aşağıdaki kapananlar). Açık kalan: vardiya (08–16 / 16–24 / 24–08) kırılımı ve dönemler arası eğilim ("geçen aya göre %18 azaldı"). İkisi de vardiya tanımını sisteme sokmayı gerektirir; bugün sistemde vardiya kavramı YOK ve uydurulmadı. | Orta |
| 4 | **Bildirim kanalları** (e-posta, SMS/WhatsApp, mobil push) | Kritik ihlalin ekran başında kimse yokken duyulması. `EventSink` arayüzüne yeni sink. | Küçük-orta |
| 5 | **Kullanıcı yönetimi ve roller** (İSG yöneticisi / operatör / izleyici) | Birden çok departman kullanmaya başladığında; kim neyi değiştirdi izlenebilirliği. Auth zaten tek dependency'de. | Orta |
| 6 | **Yüz bulanıklaştırma** (snapshot'ta) | KVKK açısından değerli; KKD kapsamı genişledikçe önemi artar. Kişi bbox'ının üst bölgesine blur. | Küçük |
| 7 | **Tarayıcıda canlı görüntü** (overlay'li) | Operatörün NVR istemcisi ile sistem arasında geçiş yapmasını bitirir. | Orta |
| 8 | **Yeni KKD sınıfları** (gözlük, eldiven, iş ayakkabısı, maske) | KKD sınıflandırıcı **çok etiketli** tasarlandı → yeni etiket = yeni çıkış + veri. Ama her yeni sınıf yeni veri toplama seansı demektir. | Orta (sınıf başına) |
| 9 | **Vardiya/saat bazlı kural aktifliği** | Kurallar yalnızca üretim saatlerinde geçerli olsun istendiğinde. Kural tablosuna iki alan. | Küçük |
| 10 | **Kural şablonları / çoklu kameraya uygulama** | 4 kamerada gereksiz, 40 kamerada zorunlu. Phase 3'ün ön koşulu. | Orta |
| 11 | **Yeniden kimliklendirme (re-ID)** | Track ID değişince tekrar uyarı sorununu çözer. | Orta-büyük |
| 12 | **NVR kayıt entegrasyonu** | Olaydan NVR'daki tam kayda atlama. | Orta |
| 13 | **Düşme / hareketsizlik tespiti** | Ayrı model, ayrı veri, ayrı bedel. Teklifte kapsam dışı. | Büyük |
| 14 | **PLC / SCADA / ERP entegrasyonu** | Teklifte açıkça kapsam dışı. İhlalde hat/kapı sinyali senaryosu doğarsa. | Değişken |
| 17 | **Tanıtılan nesnenin CANLI kamerada aranması** | Nesne kütüphanesi (Nesneler sayfası, şema 003) bugün yalnızca kullanıcının YÜKLEDİĞİ fotoğrafta arıyor — kullanıcı kararıyla kapsam böyle sınırlandı. Canlıya taşımak ayrı bir iştir: parmak izi eşleştirmesi kare başına saniyeler sürer (kayan pencere), canlı boru hattı ise saniyede 6 kare işler. Doğru yol, tespit modeline nesne sınıfı öğretmek ya da eşleştirmeyi yalnızca model kutularıyla ve seyrek karelerde çalıştırmaktır. Ayrıca canlıda "yanlış eşleşme" artık bir uyarı/anons demektir; bugünkü doğruluk buna yetmiyor. | Orta-büyük |
| 18 | **Nesne aramada video yükleme** | Bugün yalnızca fotoğraf yüklenebiliyor. Video, eşit aralıklı kare örnekleyip her kareyi taramak demektir; kayan pencere taraması kare başına saniyeler sürdüğü için tek videonun taraması dakikalara çıkar. Önce tarama hızlandırılmalı. | Orta |
| 19 | **Sayımın kalıcı kaydı** (vardiya/gün raporu) | Bölge sayımı bugün BELLEKTE tutulur: sistem yeniden başlayınca "giren" sıfırlanır ve geçmiş gün karşılaştırılamaz. Kalıcı olması için sayaçları düzenli aralıkla yazan bir tablo gerekir. Bilerek ertelendi: önce sayının sahada DOĞRU olduğu görülmeli; yanlış bir sayıyı kalıcı kaydetmek, yanlışı rapora taşımaktır. | Küçük-orta |
| 20 | **Çizgi geçiş sayımı** (kapıdan kaç kişi geçti) | Bugün sayım BÖLGE bazlıdır: "içeride kaç var" ve "kaç tanesi girdi". Yön bilgisi (içeri mi çıktı mı) için çizgi ve geçiş yönü gerekir. Bölge sayımı çoğu İSG sorusuna yettiği için önce o yapıldı. | Orta |
| 21 | **Alan tanımada boya dışı ipuçları** | `alan_bulucu` bugün yalnız SARI ve BEYAZ boyayı arar. Zemini boyasız fabrikada hiçbir şey bulamaz. Bariyer, korkuluk, raf sırası gibi ipuçları için ayrı bir yaklaşım (çizgi/derinlik analizi) gerekir ve yanlış öneri oranı ölçülmeden açılmamalı. | Orta |
| 16 | **Anons kayıt defteri** (hoparlör gerçekten kaç kez çaldı) | Anons ekranı bugün "anons tetikleyen ihlal" sayıyor; tekrar aralığı bir kısmını bastırdığı için gerçek anons sayısı bundan azdır ve ekran bunu açıkça yazıyor. Kesin sayı için her başarılı/başarısız anonsu yazan küçük bir tablo gerekir. | Küçük |

---

### 1.1 Kapanan başlıklar (bu turda yapıldı)

| Eski başlık | Bugünkü durum |
|---|---|
| Giriş şifresi (#0) | **Kapandı:** `.env` → `YONETICI_SIFRESI`. Boşken giriş sorulmaz (tek makinelik kurulum, bugünkü davranış), doluyken her sayfa şifre ister. Ekrandan da ayarlanır (Ayarlar → Güvenlik) ve şifresizken kurulum listesi uyarır. |
| Yedekten geri yükleme (K7) | **Kapandı:** Kontrol Paneli'nde "Yedekten Geri Yükle" düğmesi. Sistem çalışırken reddeder, önce güvenlik kopyası alır, bayat WAL dosyalarını siler. Prova adımları `06-OPERASYON.md` §1.2.2'de. |
| Sunucu yeniden başlayınca otomatik açılış (K8) | **Kapandı:** Docker'da `restart: unless-stopped` hazırdı; Docker'sız kurulum için systemd birimi ve her ikisinin de PROVASI `06-OPERASYON.md` §1.2.1'e yazıldı. |
| Anons uç noktasının somut biçimi (R3) | Kapandı: üç HTTP biçimi (`json`/`form`/`get`) ve adres yer tutucuları eklendi; hangi cihaz için hangisinin seçileceği `14-ANONS-SISTEMI-BAGLAMA.md`'de. Sahadaki cihaz öğrenilince kod DEĞİL, ayar değişir. |
| Bölge çiziminin zahmeti | Kapandı: zemindeki boyadan otomatik alan önerisi, dikdörtgen kipi, köşe sürükleme ve ekran görüntüsü üzerine çizim. |
| Raporlama: PDF/Excel çıktı (#3'ün ana kısmı) | **Kapandı:** Komuta → Rapor. Kamera / kural / bölge / bölüm kırılımı, saatlik ve günlük dağılım. PDF için yeni kütüphane KURULMADI: sayfa yazdırmaya hazır (`@media print`), tarayıcının "PDF olarak kaydet" adımı yeterli. Excel çıktısı noktalı virgüllü + BOM'lu CSV. Vardiya ve eğilim kırılımı hâlâ açık — #3. |
| Dördüncü kural tipi: forklift hızı (#15) | **Kapandı:** `vehicle_speed`. Ertelemenin sebebi olan şema kısıtı `backend/sema/005_arac_hizi_kurali.sql` ile güvenli biçimde aşıldı — yabancı anahtar işlem dışında kapatılıp geri açılıyor ve `PRAGMA foreign_key_check` ile olay geçmişinin sağlam kaldığı doğrulanıyor. Karar mantığı `rules/hiz.py`, davranış tanımı `03-KURAL-MOTORU.md` §4. |
| "Kaç kişi geçti" sorusu | Kısmen: bölge bazlı canlı sayım eklendi (`rules/sayim.py`). Kalıcı kayıt ve yön bilgisi hâlâ açık — #19 ve #20. |

## 2. Phase 3 — Alçı Stokholü

Teklif Bölüm 11'de zaten ayrı faz olarak tanımlı. Ayrı saha analizi, ayrı ihtiyaç
analizi, ayrı teklif gerektirir.

Aynı pipeline üzerinde çalışır; eklenecekler:
- Yeni bölge tipleri (stok alanı, istif bölgesi)
- Yeni kural tipleri (doluluk eşiği, istif yüksekliği, yanlış alana istif)
- Doluluk / alan kullanım analizi (zamansal, kural değil raporlama)

Mimari hazırlık: yeni kural tipi eklemek `rules/` içine saf fonksiyon + şema + test
demek (bkz. `03-KURAL-MOTORU.md` §6). Başka dosyaya dokunulmaz.

---

## 3. Phase 4 — Fabrika geneli yayılım (tasarım, kod değil)

**Hedef:** Sistemin tüm fabrika bölümlerine yayılması (~30-40 kamera mertebesi).

Bu bölüm, MVP'de **hiçbir kod yazılmasını gerektirmez.** Amacı, bugün alınan
kararların yarın yeniden yazım gerektirmemesini sağlamaktır.

### 3.1 Ölçeklenme kırılma noktaları

| Kamera sayısı | Kırılan şey | Çözüm |
|---|---|---|
| ~8-10 | Tek GPU'nun çıkarım kapasitesi | `sample_fps` düşürme, daha küçük model, daha güçlü GPU |
| ~15-20 | Tek analizör sürecinin RTSP decode + CPU yükü | **Analizör bölümlendirmesi** (§3.2) |
| ~20-30 | Kamera listesi ekranı ve olay akışı kullanılamaz hale gelir | **Alan bazlı gruplama ve filtreleme** (§3.3) |
| ~20-30 | Her kameraya tek tek kural yazmak sürdürülemez | **Kural şablonları** (Phase 2 #10) |
| ~30-40 | SSE polling ve olay hacmi | `LISTEN/NOTIFY`, olay tablosu bölümlendirme (partition) |
| ~30-40 | Snapshot disk büyümesi | Alan bazlı retention, daha agresif süreler |

### 3.2 Analizör bölümlendirmesi — bugünün hazırlığı

**Bugün (ADR-008):** Analizör hangi kameralarla ilgileneceğini **tek bir fonksiyondan**
öğrenir: `get_assigned_cameras()` → bugün "tüm aktif kameralar" döner.

**O gün yapılacak iş:**
1. `cameras.analyzer_group` alanı ekle (tek migrasyon)
2. `get_assigned_cameras()` içine `WHERE analyzer_group = settings.ANALYZER_GROUP` ekle
3. `docker-compose.yml`'e ikinci/üçüncü analizör servisi ekle, farklı env ile

Toplam: ~15 satır. Broker yok, servis keşfi yok, koordinasyon yok — çünkü
analizörler birbirini tanımaz, yalnızca DB'yi paylaşır.

**Bugün bu alanı eklemiyoruz** çünkü tek analizör varken `analyzer_group` kullanılmayan
konfigürasyondur ve her yeni kamerada doldurulması gereken anlamsız bir alandır.

### 3.3 Alan (area) kavramının olgunlaşması

**Bugün (ADR-007):** `cameras.area` — indeksli düz metin alanı. Olay filtresinde kullanılır.

**Fabrika genelinde gereken:** `areas` tablosu — alan adı, sorumlu İSG kişisi,
alan bazlı retention süresi, alan bazlı yetki, alan raporu.

**Geçiş:** Tek migrasyon — `areas` tablosunu oluştur, mevcut `cameras.area` metin
değerlerinden satırları üret, `cameras.area_id` FK'sini doldur, eski kolonu düşür.
Veri kaybı yok çünkü metin alanı zaten tutarlı doldurulmuş olur.

### 3.4 Model yönetimi

Fabrika genelinde farklı bölümler farklı koşullara sahiptir (iç mekân/dış mekân,
tozlu/temiz, aydınlık/karanlık). İki seçenek:

| Yaklaşım | Artı | Eksi |
|---|---|---|
| **Tek model, tüm koşullardan veri** (tercih edilen) | Tek eğitim, tek sürüm, tek bakım | Her yeni bölüm veri toplaması gerektirir |
| Bölüm başına model | Yerel doğruluk yüksek | Sürüm kâbusu, n kat bakım |

**Karar:** Tek model. Yeni bölüm devreye alınırken o bölümün verisi ortak veri setine
eklenir ve model yeniden eğitilir. `events.details.model_version` bu yüzden MVP'den
itibaren yazılır — hangi olayın hangi modelle üretildiği bilinmeden bölüm ekleme
sonrası "model bozuldu mu" sorusu cevaplanamaz.

### 3.5 KKD'nin fabrika genelinde yayılması

Piksel eşiği kısıtı (`04-KKD` §3) her yeni bölüm için **yeniden ölçülür.**
KKD'nin yayılması "kuralı kopyalamak" değil, bölüm bölüm şu döngüdür:

```
Kamera açısı ölçümü → uygun bölge belirleme → o bölümün verisiyle veri toplama
→ yeniden eğitim → gölge mod → precision ölçümü → anons açma
```

Bu döngü bölüm başına 2-4 hafta sürer. Fabrika geneli KKD kapsamı **tek seferlik
bir kurulum değil, kademeli bir programdır** — planlama buna göre yapılmalıdır.

### 3.6 Yüksek erişilebilirlik

Sistem İSG süreçlerinde kritik hale gelirse: yedek analizör düğümü, DB replikasyonu,
izleme/alarm (sistem kendi kendini izler).

Bugün gerekli değil: tek sunucu + Docker restart + günlük yedek yeterli.
Bu, kameralar arttıkça değil, **sisteme bağımlılık arttıkça** gündeme gelir.

---

## 4. Yol haritasına alınmayanlar ve nedeni

| Başlık | Neden hayır |
|---|---|
| Bulut senkronizasyonu | On-prem tek tesis; çalışan görüntüsü açısından bulut ek KVKK yükü |
| Microservice ayrıştırması | Yük profili gerektirmiyor; iki süreç yeterli, sınırı analizör bölümlendirmesi çözer |
| Kubernetes | Tek sunucu, üç container |
| GraphQL | İstemci tek ve sabit; REST + OpenAPI yeterli |
| Elasticsearch | Olay hacmi PostgreSQL'in çok altında |
| Multi-tenancy | Tek şirket, tek tesis; fabrika geneli yayılım multi-tenancy değil, alan gruplamadır |

---

## 5. Nesne kütüphanesi — isabeti geri kazanma (2026-09'da açılan başlık)

"Renk taşımaz" kuralı yanlış ismi sıfıra indirdi (bkz.
`backend/app/nesneler/kutuphane.py` → `kabul_skoru`), bedeli isabette ödendi:
tam kıyas takımında 61/204 → 8/204. Kaybın bir kısmı zaten sahteydi (eski 61
bulgunun yalnız 38'inde işaret gerçekten nesnenin üstündeydi; bugün 8'in
8'inde), ama gerçek kayıp da var. Sıradaki iş, yanlış ismi sıfırda tutarak
isabeti yukarı taşımaktır.

**Ölçülmüş ilk aday: referansın deseni AYIRT EDİCİ mi?**
Kuralı gevşetmenin bedeli ölçüldü (12 nesne, 264 sorgu, çıta 0,24): desen
payından çıtanın tamamı yerine 0,8'i istenirse isabet 8 → 21 çıkıyor ama 1
yanlış isim geri geliyor; 0,5'te isabet 30 / yanlış isim 3; hiç istenmezse
isabet 33 / yanlış isim 4. **Yanlış isimlerin tamamı tek bir kütüphane
nesnesinden geliyor:** "Düz beyaz baret". O nesne aslında düz, ama gölgesinden
23-51 ORB noktası çıkardığı için motor onu "desenli" sayıyor ve beyaz bir
çuvalın 9 gürültü noktası geometri sınamasını geçebiliyor.

Yani doğru soru "çıtayı/oranı kaça çekelim" değil, **"bu referansın anahtar
noktaları desen mi, gürültü mü?"**dir. Ölçülebilir biçimi: bir referansın
noktaları kendi diğer fotoğraflarında da aynı yerlerde çıkıyor mu (teşhisin
tutarlılık ölçüsü zaten bunu yapıyor — "Düz beyaz baret" 0,023). Bu ölçü
`benzerlik()` kararına girerse, gürültülü referanslar kendiliğinden elenir ve
gerçek desenliler için kural gevşetilebilir.

Yapılmadan önce ölçülmesi gerekenler: kural gevşetildiğinde yanlış isim gerçekten
sıfır kalıyor mu (tam takım), ve isabet 8'den kaça çıkıyor.

### 5.1 Düz nesnelere "ikinci kanıt" — DENENDİ, OLMADI (2026-09)

Düz/desensiz nesnelerin isabeti sıfırdır. Bunu kurtarmanın tek meşru yolu,
renge dayanmayan **ikinci bir kanıt** bulmaktır ("renk taşımaz" kuralı
gevşetilemez). Üç aile ayrı ayrı ve birlikte ölçüldü; **üçü de reddedildi.**

Ölçüm: düz nesnelerin sorguları ile kütüphanedekiyle **aynı renkteki** yabancı
nesnelerin sorguları, ikisi de aynı bozulmalarla ve **ideal çerçeveyle** (yani
adaylara sahada hiç olmayacak kadar iyi bir şans tanınarak). Ölçülen sayı ayırt
gücüdür (AUC): "düz nesnenin kendi sorgusu, aynı renkteki yabancıdan yüksek
skor alıyor mu?" 0,50 yazı-turadır.

| aday ikinci kanıt | adil AUC |
|---|---|
| A — uzamsal renk düzeni (2x2 + merkez histogramları) | 0,190 |
| A' — baskın renk bölgesinin halka profili + doluluğu | 0,222 |
| B — kenar/siluet haritası (8x8) | 0,000 |
| B' — satır/sütun kenar profili | 0,000 |
| B'' — Hu momentleri (Otsu + en büyük kontur) | elendi (aşağıda) |
| C — kenar yönelim dağılımı 3x3x8 (HOG) | 0,381 |
| C' — kenar yönelim dağılımı 2x2x8 | 0,508 |
| P — parlaklık düzeni (8x8) | 0,143 |
| A+B+C birlikte | 0,016 |
| hepsi birlikte | 0,000 |
| ORACLE (her sorguda en iyi aday seçilse) | 0,333 |

**Hepsi 0,50'nin altında: bu kanıtlar zayıf değil, TERSİNE çalışıyor.** Sebebi
ölçülünce anlaşıldı: bir nesne ne kadar desensizse, aynı renkteki *başka* bir
desensiz nesnenin temiz referans fotoğrafına o kadar benzer. Yabancı düz
nesneler (mavi kasa, mavi örtü, gri sac levha) pürüzsüz oldukları için
referansa, sahnede dönmüş/bulanıklaşmış/yarısı örtülmüş **gerçek** nesneden
daha çok benziyor. Bu yüzden aynı nesnenin dört referansı birbirini, ikizini
tanıdığından daha az tanıyor (HOG: kendi 0,827 — ikizi 0,850). Sıralaması ters
olan bir kanıt hiçbir eşik, ağırlık ya da birleşimle düzelmez.

Hu momentleri ayrıca elendi: aynı nesnenin dört referansı arasındaki tutarlılık
0,110 çıktı (nesne kendini bile tanımıyor), çünkü Otsu eşiklemesi tarama
penceresinde nesneyi zeminden ayıramıyor.

**Bugünkü durum dürüstçe yazılıdır:** Nesneler sayfasındaki rozet "Düz renkli —
bulunamaz" der, sayfanın "Bu yöntem ne yapar, ne yapmaz" bölümü ve kılavuz da
bu denemenin yapıldığını ve başarısız olduğunu söyler.

**Sıradaki fikir (ölçülmedi): tarama penceresini nesnenin silüetine oturtmak.**
Bugün kare pencere ızgarası nesneyi hiçbir zaman referanstaki gibi
çerçevelemiyor; üstelik referans nesnenin kendi en-boy oranıyla kırpılıp
160x160'a **eziliyor**, yani yatık bir boru referansta ezilirken tarama
penceresinde ezilmiyor. Biçim kanıtı daha hesaplanmadan bozuluyor. Önce bu
çerçeveleme uyumsuzluğu giderilmeden biçim kanıtına yeniden girmenin anlamı
yok.

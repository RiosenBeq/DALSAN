# 07 — Yol Haritası

MVP'de **geliştirilmeyen**, mimarinin engellemediği başlıklar. Bir özellik MVP'den
çıkarıldığında buraya satır olarak eklenir — böylece hiçbir fikir kaybolmaz ama
hiçbiri erken kodlanmaz.

---

## 1. Phase 2 — MVP sonrası (aynı 3-4 kamera)

Sıralama beklenen faydaya göre.

| # | Başlık | Tetikleyici / gerekçe | Büyüklük |
|---|---|---|---|
| 0 | **Giriş şifresi** (tek yönetici şifresi, imzalı çerez) — **fabrika sunucusuna çıkmadan ÖNCE** | Geliştirme aşamasında kullanıcı kararıyla kaldırıldı (02.09.2026): sistem tek makinede, yalnızca 127.0.0.1'den açılıyor. Docker/0.0.0.0 ile ağa açılınca zorunlu. Eski kod git geçmişinde: `backend/app/web/giris.py` + `tests/test_giris.py` (commit 067a2b6). | Küçük |
| 1 | **Olay video klibi** (öncesi/sonrası 5+5 sn) | Yanlış alarm incelemesinde ve İSG eğitiminde snapshot'tan çok daha güçlü. En sık istenecek özellik. | Orta |
| 2 | **KKD geri besleme döngüsü** | MVP'nin "Yanlış alarm" işaretleri + snapshot'ları zaten veri seti. Kalan iş: periyodik yeniden eğitim betiği + model sürüm yönetimi. Precision'ı zamanla yükseltir. | Orta |
| 3 | **Raporlama ve dashboard** | "İSG performansının veriye dayalı izlenmesi" hedefinin devamı: kamera/kural/bölge/**alan** kırılımı, vardiya karşılaştırması, PDF/Excel çıktı. Olay tablosu zaten doğru indeksli. | Orta |
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
| 15 | **Dördüncü kural tipi: ani hareket / forklift hızı** ("forklift 2,5 m/s üstünde") | Komuta tasarımının uyarı zincirinde örnek olarak geçiyor ama MVP'de YOK. Ertelenmesinin nedeni teknik: `rules.rule_type` bir CHECK kısıtıyla üç tipe kapalı ve SQLite'ta CHECK değiştirmek tabloyu yeniden kurmak demektir; şema betikleri işlem içinde çalıştığı için `PRAGMA foreign_keys` etkisiz kalır ve yeniden kurma, kullanıcının kurallarını sessizce silme riski taşır. Doğru yol: `rules` tablosunu güvenli biçimde taşıyan ayrı bir göç (yeni tablo + kopyala + eski tabloyu bırak) ve `rules/hiz.py` içinde saf bir kural fonksiyonu. Hız verisi zaten var: `Tespit.hiz_mps` kalibre kamerada hesaplanıyor. | Orta |
| 17 | **Tanıtılan nesnenin CANLI kamerada aranması** | Nesne kütüphanesi (Nesneler sayfası, şema 003) bugün yalnızca kullanıcının YÜKLEDİĞİ fotoğrafta arıyor — kullanıcı kararıyla kapsam böyle sınırlandı. Canlıya taşımak ayrı bir iştir: parmak izi eşleştirmesi kare başına saniyeler sürer (kayan pencere), canlı boru hattı ise saniyede 6 kare işler. Doğru yol, tespit modeline nesne sınıfı öğretmek ya da eşleştirmeyi yalnızca model kutularıyla ve seyrek karelerde çalıştırmaktır. Ayrıca canlıda "yanlış eşleşme" artık bir uyarı/anons demektir; bugünkü doğruluk buna yetmiyor. | Orta-büyük |
| 18 | **Nesne aramada video yükleme** | Bugün yalnızca fotoğraf yüklenebiliyor. Video, eşit aralıklı kare örnekleyip her kareyi taramak demektir; kayan pencere taraması kare başına saniyeler sürdüğü için tek videonun taraması dakikalara çıkar. Önce tarama hızlandırılmalı. | Orta |
| 16 | **Anons kayıt defteri** (hoparlör gerçekten kaç kez çaldı) | Anons ekranı bugün "anons tetikleyen ihlal" sayıyor; tekrar aralığı bir kısmını bastırdığı için gerçek anons sayısı bundan azdır ve ekran bunu açıkça yazıyor. Kesin sayı için her başarılı/başarısız anonsu yazan küçük bir tablo gerekir. | Küçük |

---

## 2. Phase 3 — Alçı Stokholü

Teklif Bölüm 11'de zaten ayrı faz olarak tanımlı. Ayrı saha analizi, ayrı ihtiyaç
analizi, ayrı teklif gerektirir.

Aynı pipeline üzerinde çalışır; eklenecekler:
- Yeni bölge tipleri (stok alanı, istif bölgesi)
- Yeni kural tipleri (doluluk eşiği, istif yüksekliği, yanlış alana istif)
- Doluluk / alan kullanım analizi (zamansal, kural değil raporlama)

Mimari hazırlık: yeni kural tipi eklemek `rules/` içine saf fonksiyon + şema + test
demek (bkz. `03-KURAL-MOTORU.md` §5). Başka dosyaya dokunulmaz.

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

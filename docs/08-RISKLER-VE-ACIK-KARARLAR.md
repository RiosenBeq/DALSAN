# 08 — Riskler ve Açık Kararlar

## 1. Risk kaydı

| # | Risk | Etki | Yaklaşım |
|---|---|---|---|
| **R1** | **Forklift sınıfı hazır modellerde yok.** COCO'da forklift yok; "truck" olarak yanlış sınıflanır. | Yüksek | 1. haftada saha kameralarından 300-800 kare toplanıp etiketlenir; hazır ağırlıklar üzerine fine-tuning (3-4. hafta). Kamu setleri başlangıç noktası, **saha görüntüsü şart**. Bu, teklifin "kapsam dışı: yeni senaryolar" maddesine girmez — taahhüt edilen sınıfın kendisidir. |
| **R2** | **Dedektör lisansı** (ADR-002). Ultralytics AGPL-3.0. | Orta-yüksek | 1. haftada karar. Öneri: Apache-2.0 alternatif. `Detector` arayüzü arkasında izole. |
| **R3** | **Anons altyapısı entegre edilemeyebilir.** Teklif koşula bağlamış. | **Düşük** *(azaltıldı)* | Üç yol da kodda hazır: ses kartı (analog amfi), IP hoparlör için **üç ayrı HTTP biçimi** (`json`/`form`/`get`) ve adres yer tutucuları. Sahadaki cihaz öğrenilince kod değil AYAR değişir. Bağlama tarifi, cihaz soruları ve sorun giderme tablosu: `14-ANONS-SISTEMI-BAGLAMA.md`. Kapalı/özel bir sisteme hâlâ bağlanılamayabilir; MVP anonssuz da kabul edilebilir (K6). |
| **R4** | **Yanlış alarm yükü.** Sistem gereğinden hassassa güven kaybeder. | Yüksek | Tasarımda: kalış süresi, ardışık kare, cooldown, "araç hareketliyken", KKD zamansal oylaması. Süreçte: 7. hafta ölçüme dayalı ayarlama; olay durumu alanı oranı ölçülebilir kılar. |
| **R5** | **Kamera açıları analiz için elverişsiz olabilir.** Mevcut kameralar güvenlik için konumlandırılmış. | Yüksek | 1. hafta keşfinin birincil çıktısı kamera-bölge uygunluk tablosudur. Mesafe kuralı zemin görünürlüğü ister; **KKD piksel eşiği ister** (R9). Uygun olmayan kamera yazılı olarak kapsam dışı bırakılır. |
| **R6** | **Sunucu donanımı kapsam dışı.** GPU'lu sunucu yoksa proje başlayamaz. | Yüksek | Gereksinim 1. haftada yazılı iletilir; tedarik DALSAN'da; termin bu koşula bağlı (teklifin varsayımlar bölümü bunu zaten kapsıyor). |
| **R7** | Kamera saatleri senkron değilse zaman damgaları tutarsız. | Düşük | Zaman damgası **sunucuda** üretilir; sunucuda NTP. Runbook'ta not. |
| **R8** | Disk dolması (snapshot birikimi). | Orta | Retention + disk kullanımı loglaması; eşik altında sistem olayı. |
| **R9** | **KKD piksel eşiği sağlanamayabilir.** Kişi 120 px altındaysa baret kararı güvenilmez. | **Yüksek — KKD'nin varlık şartı** | 1. haftada her aday bölge için ölçüm (`04-KKD` §3). Sağlanamıyorsa bölge küçültülür veya o kamerada baret kuralı devre dışı bırakılır. Sonuç Rev.02'ye kamera-bölge tablosu olarak yazılır. |
| **R10** | **KKD negatif veri kıtlığı.** Uyumlu fabrikada "baretsiz" görüntü yok. | **Yüksek** | 2. haftada İSG refakatinde planlı çekim seansı (`04-KKD` §4.2). Kamu veri setiyle ön eğitim. Seans gecikirse KKD 8 haftaya sığmaz — ek protokolde DALSAN yükümlülüğü olarak yazılır. |
| **R11** | **KKD politika belirsizliği.** Mont yelek sayılır mı, kabindeki operatör kapsamda mı vb. | Orta-yüksek | Etiketlemeden **önce** 10 soruluk liste DALSAN İSG'ye sorulur (`04-KKD` §5.3); cevaplar `docs/kkd-politika.md`. Yanlış cevapla etiketlenen veri seti baştan bozuktur. |
| **R12** | **KKD'nin disiplin aracı olarak algılanması.** Çalışan direnci, kameradan kaçma, açı bozma. | Orta-yüksek | Konumlandırma: "hatırlatma", ceza değil. Çalışan bilgilendirmesi devreye almadan önce. Gölge mod. Sistem çıktısının disiplin süreçlerinde kullanılmayacağının yazılı olması. |
| **R13** | **KVKK uyumu.** Çalışan görüntüsünden davranışsal çıkarım. | Yüksek | DALSAN veri sorumlusu, NextGen veri işleyen. Aydınlatma metni, levhalar, işleme şartı, saklama süreleri, veri işleyen sözleşmesi — DALSAN hukuk birimince teyit edilir (`00-PROJE-BAGLAMI.md`). |
| **R14** | **Alçı tozu / beyaz baret kontrastı.** Kamu veri setlerinde bulunmayan koşul. | Orta | Veri toplama tozlu koşulları **kapsamalı**; augmentasyonda parlaklık/kontrast jitter. Yelek (hi-vis) bu koşuldan çok daha az etkilenir → gerekirse baret kuralı dar bölgeye, yelek kuralı geniş bölgeye. |

## 2. 1. hafta sonunda kapatılması gereken kararlar

| # | Karar | Kim verir |
|---|---|---|
| 1 | Dedektör modeli ve lisansı (ADR-002) | NextGen (maliyet doğarsa DALSAN onayı) |
| 2 | Kesin kamera listesi (3-4) ve her birinin uygunluğu | Birlikte — saha keşfi |
| 3 | **KKD bölgeleri + piksel eşiği ölçüm sonucu** | Birlikte — ölçümle |
| 4 | **KKD politika soruları (10 madde)** | DALSAN İSG |
| 5 | **Planlı çekim seansı tarihi ve katılımcıları** | DALSAN İSG |
| 6 | Anons entegrasyon yöntemi | Birlikte |
| 7 | Sunucu donanımı ve teslim tarihi | DALSAN |
| 8 | Bölge ve mesafe eşiklerinin ilk değerleri | DALSAN İSG |
| 9 | Veri saklama süreleri (KVKK politikasıyla uyumlu) | DALSAN |
| 10 | **Rev.02 / kapsam ek protokolü imzası** | Birlikte |

10 numara diğerlerinin kabıdır: 2, 3, 5 ve 9'un sonuçları ek protokole yazılır.

## 3. Kabul edilmiş sınırlar (risk değil, tasarım kararı)

Bunlar "sonra düzeltilecek eksik" değildir; bilinçli takaslardır ve müşteriye
bu şekilde anlatılır:

- Bölgeden 2-3 saniyede geçen ihlal **kaçırılabilir** (zamansal oylama gereği)
- Kameraya uzak kişi için KKD kararı **verilmez** (`unknown`)
- Kalibre edilmemiş kamerada mesafe kuralı **çalışmaz** (yaklaşık sonuç üretmez)
- Track ID değişirse aynı kişi için tekrar uyarı üretilebilir
- Ham video **saklanmaz** — yalnızca olay anı görüntüsü
- Sistem kesin tespit taahhüdü içermez; İSG prosedürlerinin yerine geçmez

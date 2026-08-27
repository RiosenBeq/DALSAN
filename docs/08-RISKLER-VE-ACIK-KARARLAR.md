# 08 — Riskler ve Açık Kararlar

## 1. Risk kaydı

| # | Risk | Etki | Yaklaşım |
|---|---|---|---|
| **R1** | **Forklift sınıfı hazır modellerde yok.** COCO'da forklift yok; "truck" olarak yanlış sınıflanır. | Yüksek | 1. haftada saha kameralarından 300-800 kare toplanıp etiketlenir; hazır ağırlıklar üzerine fine-tuning (3-4. hafta). Kamu setleri başlangıç noktası, **saha görüntüsü şart**. Bu, teklifin "kapsam dışı: yeni senaryolar" maddesine girmez — taahhüt edilen sınıfın kendisidir. **Durum: altyapı hazır** — sistem araç görülen karelerden otomatik örnek biriktirir, `/forklift` sayfasında tek tıkla etiketlenir, "Eğitimi çalıştır" düğmesi modeli eğitip eski/yeni isabeti aynı test kareleri üzerinde karşılaştırır ve **yalnızca daha iyiyse** devreye alır (bkz. §4). |
| **R2** | **Dedektör lisansı** (ADR-002). Ultralytics AGPL-3.0. | Orta-yüksek | 1. haftada karar. Öneri: Apache-2.0 alternatif. `Detector` arayüzü arkasında izole. |
| **R3** | **Anons altyapısı entegre edilemeyebilir.** Teklif koşula bağlamış. | Orta | 1. haftada tespit: analog amplifikatör (ses kartı) / IP hoparlör (HTTP) / kapalı sistem (kapsam dışı, yazılı mutabakat). MVP anonssuz da kabul edilebilir (K6). **Durum: üç olasılığın üçü de hazır** — `/anons` sayfasında yöntem görünür, mesajlar düzenlenir ve deneme anonsu çalınır. Tür öğrenilince yalnızca `.env` içindeki `ANONS` satırı değişir; kod değişmez (bkz. §5). |
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

## 4. Forklift veri toplama ve ince ayar (R1'in uygulaması)

**Toplama.** Analiz süpervizörü, araç (`truck`/`forklift`) tespit edilen karelerden
kamera başına saatte en çok `FORKLIFT_ORNEK_SAAT_LIMIT` (varsayılan 30) adet **tam
kare** yazar. Kırpık değil tam kare saklanır; dedektör ince ayarı kutu konumunu ister.
Aday araç kutusu normalize koordinatla `forklift_samples.bbox` içine yazılır.

**Etiketleme.** `/forklift` sayfası KKD sayfasıyla aynı düzendedir: her kart bir kare,
üzerinde sarı aday kutusu, altında üç düğme — **Forklift / Değil / Belirsiz**.
Etiketlenen kart listeden düşer. Hedef 300-800 etiketli kare.

**Eğitim.** "Eğitimi çalıştır" düğmesi `app/egitim/forklift_egitim.py` çağırır:

- Veri **zamana göre** bölünür (son %20 test) — rastgele bölme yasağı KKD ile aynıdır
  (`04-KKD` §5.4); aksi halde aynı aracın ardışık kareleri hem eğitime hem teste düşer
- `belirsiz` etiketli kareler eğitime **girmez**
- Eski ve yeni model **aynı test kareleri** üzerinde karşılaştırılır. "Eski" = devrede
  bir sürüm varsa o, yoksa bugünkü davranış (hiçbir araç forklift sayılmaz)
- Sonuç her koşulda `models/forklift/vNNN.npz` + `vNNN.json` olarak **sürümlü** kaydedilir
- Yeni model **yalnızca isabeti eskiyi geçerse** devreye alınır (`aktif.json` güncellenir);
  geçemezse sistemin davranışı değişmez ve sebebi ekranda yazar
- Devreye alınan model, süpervizörün 5 sn'lik konfig turunda **yeniden başlatmadan** yüklenir

**Model yoksa sınıf değişmez:** araç `tır` olarak kalır. Uydurma karar üretilmez —
`04-KKD` §1'deki "kanıtın yokluğu, ihlalin varlığı değildir" ilkesinin aynısı.

**Saklama.** Etiketlenmemiş kareler `KKD_HAM_VERI_SAKLAMA_GUN` sonunda silinir;
**etiketlenenler eğitim veri setidir ve retention'a tabi değildir.**

## 5. Anons altyapısı (R3'ün uygulaması)

Üç yöntem de kodda hazırdır ve `.env` içindeki tek satırla seçilir:

| `ANONS` değeri | Karşılığı | Ek ayar |
|---|---|---|
| `null` | Anons yok; yalnız ekran uyarısı (MVP'de kabul — K6) | — |
| `ses_karti` | Sunucunun ses çıkışı amfiye kabloyla bağlı | Her mesaja bir WAV dosyası |
| `http` | IP hoparlör / anons sunucusu | `ANONS_HTTP_ADRESI` |

`/anons` sayfası: yürürlükteki yöntemi, bekleme süresini ve her mesajın hangi kurallara
bağlı olduğunu gösterir; mesaj metni ve ses dosyası düzenlenir; **"Deneme anonsu çal"**
düğmesi mesajı anında çalar (bekleme uygulanmaz, kapalı mesaj da çalar — kurulum
doğrulamak içindir) ve sonucu Türkçe olarak ekrana yazar.

İhlalde otomatik anons, kurala bağlanmış mesaj üzerinden verilir. Anons cooldown'u
ekran uyarısından **bağımsızdır** (`ANONS_BEKLEME_SN`, varsayılan 30 sn): ekranda
yüzlerce olay görünse de hoparlör aynı kamera+mesaj için 30 saniyede bir konuşur.

DALSAN'dan anons sisteminin türü öğrenilince **yalnızca `.env` satırı değişir**; kod,
kurallar ve mesajlar aynı kalır.

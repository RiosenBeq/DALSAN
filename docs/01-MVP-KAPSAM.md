# 01 — MVP Kapsamı ve Karar Matrisi

> Bu dosya, tek başına duran önceki MVP analizinin yerini alır.
> Değişiklikler: kamera 8-10 → **3-4**, KKD (baret/yelek) kural tipi **eklendi**.

## 1. MVP tek cümleyle

3-4 mevcut kameradan RTSP ile görüntü alan; **insan, forklift, tır** tespit edip takip eden;
kamera başına tanımlı **bölge ihlali**, **güvenli mesafe** ve **KKD (baret/yelek)** kurallarını
değerlendiren; ihlalde izleme ekranına anlık uyarı düşüren (anons altyapısı uygunsa sesli uyarı
veren); her olayı **tarih/saat, kamera, kural ve kanıt görüntüsü** ile kaydeden; olayların
listelenip filtrelenebildiği, fabrika içinde tek sunucuda 7x24 çalışan sistem.

### Uçtan uca akış

```
Kamera (RTSP) → Kare örnekleme → Tespit (insan/forklift/tır) → Takip (kalıcı track ID)
   ├─ KKD bölgesindeki insan track'leri → KKD sınıflandırıcı (baret/yelek) → zamansal oylama
   └─ Tüm nesneler → Kural motoru (bölge ihlali · güvenli mesafe · KKD)
→ Cooldown filtresi → Uyarı (ekran SSE · anons uygunsa ses)
→ Olay kaydı (DB + overlay'li snapshot)
→ İzleme ekranı (canlı akış · geçmiş · filtre · durum işaretleme)
```

## 2. Kabul kriterleri

| # | Kriter |
|---|---|
| K1 | 3-4 kamera aynı anda bağlı; kopmada otomatik toparlanma; kamera durumu ekranda |
| K2 | İnsan, forklift, tır DALSAN görüntülerinde kabul edilebilir doğrulukla tespit ediliyor |
| K3 | Bölgeler ve kurallar arayüzden tanımlanıp değiştirilebiliyor; değişiklik yeniden başlatmasız devreye giriyor |
| K4 | Bölge ihlali ve mesafe ihlalleri ≤ 2 sn içinde ekrana düşüyor; aynı olay tekrar uyarı üretmiyor |
| K5 | Her olayın zaman, kamera, kural, nesne bilgisi ve kanıt görüntüsü kayıtlı; filtrelenebiliyor |
| K6 | Anons altyapısı uygunsa ihlalde tanımlı mesaj çalıyor; uygun değilse sistem bundan bağımsız çalışıyor |
| K7 | Yedek alma ve geri yükleme dokümante edilmiş ve **en az bir kez prova edilmiş** |
| K8 | Sunucu yeniden başladığında sistem otomatik ayağa kalkıyor |
| K9 | Kullanım dokümanı hazır (kamera ekleme, bölge çizme, kural ayarı, olay inceleme, yedek) |
| **K10** | **KKD kuralı, tanımlı KKD bölgelerinde ve piksel eşiği üstündeki kişiler için çalışıyor; "belirsiz" durumlar uyarı üretmiyor; track bazlı karar veriyor** |
| **K11** | **KKD için 7. haftada ölçüm yapılmış: en az 3 günlük gerçek saha verisinde track bazlı hassasiyet (precision) raporlanmış ve DALSAN ile birlikte eşikler ayarlanmış** |

## 3. Karar matrisi

**Sınıflandırma:** MUST HAVE · SHOULD HAVE · NICE TO HAVE · FUTURE
**MVP?:** ✅ MVP'de · ⚠️ MVP'de dar kapsamla · ❌ MVP'de değil

### 3.1 Görüntü alma ve kamera yönetimi

| Özellik | MVP? | Öncelik | Neden? | Geleceğe bırakılabilir mi? |
|---|---|---|---|---|
| RTSP ile mevcut kamera/NVR'dan görüntü (3-4 kamera) | ✅ | MUST | Sistemin girdisi. | Hayır |
| Kamera CRUD (ad, alan, RTSP URL, aktif, örnekleme fps) | ✅ | MUST | Kamera eklemek geliştiriciye bağlı olmamalı. | Hayır |
| Otomatik yeniden bağlanma + sağlık durumu (online/offline, son kare, gerçek fps) | ✅ | MUST | Fabrika ağında RTSP kopmaları rutin. 7x24 çalışma bunsuz olmaz. | Hayır |
| Son kare önizleme (JPEG, 1-2 sn'de yenilenen) | ⚠️ | SHOULD | Bölge çizimi ve kalibrasyon bunun üstünde yapılır. | Hayır — editörün ön koşulu |
| Video dosyasını kamera gibi kullanma (dev/test) | ✅ | MUST | Mac/Windows'ta fabrikasız geliştirme + regresyon testi. | Hayır |
| `cameras.area` alanı (bölüm adı, düz metin) | ✅ | MUST | Fabrika geneli yayılımın ilk adımı; filtreleme için. Tablo değil, tek alan. | Hayır (maliyeti sıfır) |
| Tarayıcıda canlı video (WebRTC/HLS) | ❌ | NICE | NVR istemcisi zaten veriyor; transcoding karmaşıklığı. | Evet → Phase 2 |
| NVR kayıt entegrasyonu | ❌ | FUTURE | Teklifte yok. | Evet |

### 3.2 Tespit ve takip

| Özellik | MVP? | Öncelik | Neden? | Geleceğe bırakılabilir mi? |
|---|---|---|---|---|
| İnsan tespiti | ✅ | MUST | Senaryo 1 + KKD'nin ön koşulu. | Hayır |
| Forklift tespiti | ✅ | MUST | Senaryo 2. Hazır modellerde sınıf yok → fine-tuning (Risk R1). | Hayır |
| Tır / ağır araç tespiti | ✅ | MUST | Senaryo 3. | Hayır |
| Nesne takibi (kalıcı track ID) | ✅ | MUST | Senaryo 4 + tekrar uyarıyı bastırmanın + KKD zamansal oylamasının ön koşulu. | Hayır |
| **Baret sınıflandırma (var/yok/belirsiz)** | ✅ | MUST | Yeni KKD kuralı. İki aşamalı: insan crop → sınıflandırıcı. | Hayır |
| **Yelek sınıflandırma (var/yok/belirsiz)** | ✅ | MUST | Baretten teknik olarak daha kolay (büyük yüzey + hi-vis renk). | Hayır |
| Kare örnekleme (5-8 fps) + GPU'da batch çıkarım | ✅ | MUST | 4 kamerayı tek GPU'da rahat taşır. | Hayır |
| Basit hız/yön tahmini | ⚠️ | SHOULD | "Araç hareket halinde mi" koşulu için; birkaç satır. | Kısmen |
| Yüz bulanıklaştırma (snapshot'ta) | ❌ | NICE | KVKK açısından değerli ama zorunlu değil; ham video zaten saklanmıyor. | Evet → Phase 2 |
| Düşme / hareketsizlik tespiti | ❌ | FUTURE | Ayrı model, ayrı veri, ayrı bedel. | Evet |

### 3.3 Bölge, kalibrasyon, kural motoru

| Özellik | MVP? | Öncelik | Neden? | Geleceğe bırakılabilir mi? |
|---|---|---|---|---|
| Poligon bölge tanımı (yaya yolu, sevkiyat/yükleme, tır alanı, **KKD zorunlu alan**) | ✅ | MUST | Üç kural tipinin de dayanağı. | Hayır |
| Bölge çizim editörü (son kare üzerine poligon) | ⚠️ | SHOULD | JSON ile de olur ama her saha ayarı geliştirici gerektirir. Yalın SVG editörü 1-2 gün. | Kısmen |
| **Kural tipi 1 — Bölge ihlali** | ✅ | MUST | Senaryo 5, 6, 7'yi tek tip karşılıyor. | Hayır |
| **Kural tipi 2 — Güvenli mesafe** | ✅ | MUST | Senaryo 8. | Hayır |
| **Kural tipi 3 — KKD ihlali** | ✅ | MUST | Yeni kapsam. Bölgeye bağlı, zamansal oylamalı, üç durumlu. | Hayır |
| Mesafe kalibrasyonu (4 nokta zemin homografisi) | ✅ | MUST | Kalibrasyonsuz piksel mesafesi anlamsız. Kalibre olmayan kamerada mesafe kuralı **pasif**. | Hayır |
| Kural parametreleri arayüzden düzenlenebilir | ✅ | MUST | Ayarlama haftası bunsuz çok yavaş; restart gerektirmemeli. | Hayır |
| Vardiya/saat bazlı kural aktifliği | ❌ | NICE | Kurala iki alan eklemek yeterli; keşifte çıkarsa. | Evet |
| Kural şablonu / kopyalama (çok kameraya uygulama) | ❌ | NICE | 4 kamerada gereksiz; 40 kamerada şart (bkz. yol haritası). | Evet → Phase 2 |
| Kural dili / kural zincirleme | ❌ | FUTURE | Üç kural tipi tüm senaryoları karşılıyor. | Evet |

### 3.4 Uyarı ve anons

| Özellik | MVP? | Öncelik | Neden? | Geleceğe bırakılabilir mi? |
|---|---|---|---|---|
| Uyarı üretimi + cooldown (kamera+kural+track bazlı) | ✅ | MUST | Cooldown'sız sistem dakikada yüzlerce uyarı üretir ve kullanılmaz olur. | Hayır |
| SSE ile ekrana anlık uyarı | ✅ | MUST | "İlgili ekranlara iletilmesi". Tek yön → WebSocket gereksiz. | Hayır |
| Anons adaptör arayüzü (Null / Ses kartı / HTTP) | ✅ | MUST | Bir arayüz + Null implementasyon; somut entegrasyonu keşfe bırakır. | Hayır |
| Anons somut entegrasyonu | ⚠️ | SHOULD | Teklif teslimatı ama "altyapı uygunluğu koşuluyla" (Risk R3). | Koşullu |
| Anons mesaj yönetimi + **KKD mesajları** ("Lütfen baretinizi takınız") | ⚠️ | SHOULD | Anons varsa şart. Anons cooldown'u ekrandan uzun olmalı. | Anonsla birlikte |
| E-posta / SMS / push bildirim | ❌ | FUTURE | Teklifte yok. | Evet → Phase 2 |
| TTS | ❌ | NICE | 4-5 sabit mesaj için kayıtlı WAV yeterli. | Evet |

### 3.5 Olay kaydı ve izleme ekranı

| Özellik | MVP? | Öncelik | Neden? | Geleceğe bırakılabilir mi? |
|---|---|---|---|---|
| Olay kaydı (zaman, kamera, kural, sınıf/track, ölçülen değer, bölge) | ✅ | MUST | Senaryo 11. | Hayır |
| Overlay'li snapshot (bbox + bölge + KKD etiketi) | ✅ | MUST | Kare zaten elde. Yanlış alarm ayıklaması ve KKD doğrulaması bunsuz yapılamaz. | Hayır |
| Olay listesi + filtre (tarih, kamera, kural tipi, durum, **alan**) | ✅ | MUST | Senaryo 12. | Hayır |
| Olay detayı (snapshot + meta) | ✅ | MUST | Listeyle aynı ekranda panel. | Hayır |
| Olay durumu: Yeni / İncelendi / Yanlış alarm + not | ⚠️ | SHOULD | Tek alan + tek buton. **K11'in ölçüm aracı** ve KKD veri geri beslemesinin kaynağı. | Hayır — KKD varsa şart |
| CSV dışa aktarma | ⚠️ | SHOULD | ~30 satır; "veriye dayalı izleme"nin en ucuz aracı. | Evet ama dahil |
| Kamera durum paneli | ⚠️ | SHOULD | Operatör "sistem çalışıyor mu" sorusunu ekrandan cevaplamalı. | Kısmen |
| Sistem olayları (kamera düştü/geldi) aynı listede | ⚠️ | SHOULD | Kamera 3 gün kapalıysa İSG bilmeli. Aynı tablo, `system` tipi. | Kısmen |
| Dashboard / grafik / periyodik rapor | ❌ | NICE | Olay tablosu "zemin"dir; rapor katmanı sonra. | Evet → Phase 2 |
| Isı haritası | ❌ | FUTURE | Teklifte yok. | Evet |

### 3.6 Güvenlik, erişim, işletim

| Özellik | MVP? | Öncelik | Neden? | Geleceğe bırakılabilir mi? |
|---|---|---|---|---|
| Tek yönetici şifresi (env, oturum çerezi) | ⏸ | MUST (fabrika) | Kural değiştirebilen ve anons tetikleyen sistem LAN'da bile şifresiz olmaz. **Geliştirme aşamasında kullanıcı kararıyla kapatıldı (02.09.2026):** sistem tek makinede, yalnızca 127.0.0.1'e bağlı çalışıyor. Fabrika sunucusuna çıkmadan önce geri eklenir → `07` #0. | Fabrika kurulumuna kadar |
| Kullanıcı yönetimi / roller | ❌ | FUTURE | Tek ekip. Auth tek dependency'de; sonradan kullanıcı tablosuyla değişir. | Evet → Phase 2 |
| RTSP kimlik bilgisi maskeleme | ✅ | MUST | Temel hijyen. | Hayır |
| Retention (olay N gün, snapshot M gün, otomatik silme) | ✅ | MUST | Disk dolunca sistem durur. **Ayrıca KVKK gereği.** | Hayır |
| Backup/restore script + prova | ✅ | MUST | K7. Test edilmemiş yedek yedek değildir. | Hayır |
| Docker Compose + healthcheck + restart policy | ✅ | MUST | K8. | Hayır |
| JSON yapılandırılmış log | ✅ | MUST | Teşhis çoğunlukla uzaktan log üstünden yapılacak. | Hayır |
| HTTPS / reverse proxy | ❌ | NICE | LAN içi tek istemci; gerekirse Caddy ile 1 saat. | Evet |
| Audit log (kim neyi değiştirdi) | ❌ | FUTURE | Tek kullanıcı varken anlamsız; `updated_at` + config log yeterli. | Evet |
| Çoklu tesis / multi-tenant | ❌ | FUTURE | Tek tesis. | Evet |
| PLC / SCADA / ERP | ❌ | FUTURE | Teklifte açıkça kapsam dışı. | Evet |
| Alçı Stokholü modülü | ❌ | FUTURE | Teklif Bölüm 11: ayrı faz, ayrı keşif. | Evet |

## 4. MVP'de olmayan ama mimaride yeri açık bırakılanlar

| Gelecek özellik | Bugün yapılan hazırlık (ek kod değil, tasarım kararı) |
|---|---|
| Kullanıcı/rol sistemi | Auth tek FastAPI dependency'sinde |
| Bildirim kanalları | `EventSink` arayüzü var; yeni sink = yeni sınıf |
| Video klip | `CameraSource` son N kareyi tutabilecek yapıda ama ring buffer yazılmıyor |
| Raporlama | Olay tablosu indeksli, UTC, JSONB detay → her rapor SQL ile üretilebilir |
| Fabrika geneli yayılım | `cameras.area` alanı + analizörün "hangi kameralar" sorusunun **tek fonksiyonda** olması |
| Yeni KKD sınıfları (gözlük, eldiven, ayakkabı) | KKD sınıflandırıcı **çok etiketli** tasarlanır; yeni etiket = yeni çıkış nöronu + veri |
| Yeni tespit sınıfları | Sınıf listesi tek enum + model etiket eşleme tablosunda |

## 5. 8 haftalık plana oturtma (güncel)

| Hafta | Çıktı |
|---|---|
| **1** | Saha keşfi; **KKD bölgelerinin ve kameralarının seçimi (piksel eşiği ölçümü ile)**; anons altyapısı tespiti; sunucu gereksinimi; Rev.02 kapsam ek protokolü; repo + Docker + Postgres + Alembic iskeleti. **R1, R2, R9 kapatılır.** |
| **2** | `CameraSource` + yeniden bağlanma + sağlık; kamera CRUD + liste ekranı; detector entegrasyonu; **KKD veri toplama başlar (planlı çekim seansı dahil)** |
| **3-4** | Forklift fine-tuning; tracker; bölge editörü; homografi kalibrasyonu; `rules/` + birim testleri; **KKD crop veri seti etiketleme + ilk sınıflandırıcı eğitimi** |
| **5** | Kural motoru (3 tip), cooldown, kural CRUD; restart'sız config yayılımı; olay + snapshot; **KKD kuralının pipeline'a bağlanması** |
| **6** | SSE + canlı uyarı paneli; anons entegrasyonu ve saha denemesi; anons mesajları (KKD dahil) |
| **7** | Olay listesi/filtre/durum/CSV; kamera durum paneli; **yanlış alarm ayarlaması + KKD track bazlı precision ölçümü (K11)**; retention; backup provası |
| **8** | Fabrika sunucusuna kurulum; 7x24 dayanıklılık gözlemi; runbook + kullanım dokümanı; K1-K11 doğrulaması |

**Kritik yol:** 1. hafta saha erişimi → 2. hafta KKD çekim seansı → 3-4. hafta etiketleme.
KKD veri toplama gecikirse KKD senaryosu 8 haftaya sığmaz. Bu, kapsam ek protokolünde
DALSAN'ın yükümlülüğü olarak yazılmalıdır.

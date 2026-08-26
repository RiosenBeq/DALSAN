# 10 — Yapay Zeka ile Çalışma Rehberi

Bu dosya sana yazılım öğretmez. **Yazılım bilmeden, yapay zekayla birlikte
sağlam bir sistem üretmenin yöntemini** anlatır.

---

## 1. Roller

| Kim | Ne yapar |
|---|---|
| **Sen** | Ne isteneceğine karar verirsin, sonucu denersin, doğru mu yanlış mı söylersin, DALSAN ile konuşursun |
| **Claude Code** | Kodu yazar, hatayı bulur, düzeltir, test yazar |
| **Bu dokümanlar** | Yapay zekanın her seferinde aynı kararları vermesini sağlar |

Kritik nokta: **Sen kodu okuyup onaylamayacaksın.** Bunun yerine **davranışı**
onaylayacaksın: "kamerayı ekledim, görüntü geldi mi?", "baretsiz geçtim, uyarı çıktı mı?"

Bu yüzden aşağıdaki iki alışkanlık her şeyden önemli.

---

## 2. İki vazgeçilmez alışkanlık

### Alışkanlık 1: Git — "geri alma düğmesi"

Git'i sürüm kontrol sistemi olarak değil, **her şey bozulduğunda geri dönebileceğin
kayıt noktası** olarak düşün. Oyunlardaki "kaydet" gibi.

Her çalışan aşamadan sonra Claude Code'a şunu yaz:

> "Şu an her şey çalışıyor. Kaydet ve ne yaptığımızı yaz."

Bir şey bozulduğunda:

> "Son çalışan hâle geri dön."

Bunu yapmazsan, 3 hafta sonra bozulan bir şeyi düzeltmek imkânsız hale gelir.
**Bu tek alışkanlık, projeyi kurtaracak ya da batıracak şeydir.**

### Alışkanlık 2: Testler — yapay zekanın kendi kendini kontrol etmesi

Test = "sistem şunu yapmalı" diye yazılmış küçük kontroller. Sen okumazsın, ama
Claude Code her değişiklikten sonra çalıştırır ve **bir şeyi bozduysa hemen anlar.**

Yazılım bilmeyen biri için testler lüks değil, **zorunluluktur** — çünkü senin
gözden kaçıracağın bozulmaları yakalayan tek mekanizma budur.

Her yeni kural veya özellikten sonra:

> "Bunun için test de yaz. Sonra bütün testleri çalıştır ve sonucu göster."

Cevap yeşilse devam. Kırmızıysa:

> "Testler kırmızı, düzelt."

---

## 3. Nasıl istek yazılır

### Kötü istek
> "KKD sistemi yap"

### İyi istek
> "docs/03-KURAL-MOTORU.md dosyasındaki `ppe_violation` kuralını yaz.
> Önce sadece `rules/ppe.py` dosyasını ve testlerini yap, kameraya bağlama.
> Testleri çalıştırıp sonucu göster."

Farkı yaratan üç şey:

1. **Hangi dokümana bakacağını söyle** — dokümanlar tam bu iş için var
2. **Küçük parça iste** — "sistemi yap" değil, "şu dosyayı yap"
3. **Sonunda ne göreceğini söyle** — "testleri çalıştır ve göster"

### Her oturumun ilk cümlesi

> "CLAUDE.md ve docs/ klasöründeki dokümanları oku. Kurallara uy."

Bunu her yeni sohbette tekrarla. Yapay zekanın hafızası oturumlar arasında sınırlıdır;
dokümanlar bu yüzden var.

---

## 4. Sıralama — hangi işi ne zaman

Bu sıra tesadüfi değil. Her adım bir öncekinin üstüne kurulur; atlarsan geri dönersin.

| Sıra | İş | Bittiğini nasıl anlarsın |
|---|---|---|
| 1 | Proje iskeleti + veritabanı + başlatıcı | Başlatıcıda "Sistem çalışıyor" yazısını görürsün |
| 2 | Kamera ekleme + görüntü alma | Eklediğin kameranın görüntüsünü ekranda görürsün |
| 3 | İnsan/forklift/tır tespiti | Görüntüde kutular çıkar |
| 4 | Bölge çizme | Fare ile alan çizip kaydedebilirsin |
| 5 | Kural motoru + testler | Testler yeşil |
| 6 | Olay kaydı + izleme ekranı | Bölgeye girince listede satır belirir |
| 7 | Mesafe kalibrasyonu | 4 nokta tıklarsın, mesafe metre cinsinden doğru çıkar |
| 8 | KKD veri toplama + etiketleme sayfası | Kırpılmış fotoğrafları düğmelerle etiketlersin |
| 9 | KKD modeli eğitimi | HTML raporda doğruluk ve hatalı örnekleri görürsün |
| 10 | KKD kuralı devrede | Baretsiz geçince (gölge modda) olay düşer |
| 11 | Anons | Hoparlörden ses gelir |
| 12 | Yedekleme + fabrikaya kurulum | Yedeği geri yükleyip çalıştığını görürsün |

**Kural:** Bir adım tam bitmeden sonrakine geçme. "Neredeyse çalışıyor" = çalışmıyor.

---

## 5. Bir şey bozulduğunda

Sırasıyla:

1. **Başlatıcıdaki günlük penceresine bak.** Kırmızı/`ERROR` satırlarını **olduğu gibi
   kopyala.**
2. Claude Code'a yapıştır ve şunu yaz:
   > "Şunu yapmaya çalıştım: [ne yaptın]. Bekliyordum: [ne olmalıydı].
   > Onun yerine bu oldu: [hata metni]. Düzelt."
3. Düzelmezse:
   > "Son çalışan hâle geri dön, sonra baştan daha küçük adımlarla dene."

**Yapma:** Hatayı kendin tahmin edip "şurayı değiştir" deme. Ne olduğunu anlat, çözümü
yapay zekaya bırak.

**Yapma:** Aynı isteği 5 kez tekrarlama. İki denemede olmuyorsa, işi daha küçük parçaya böl.

---

## 6. Tehlike işaretleri

Bunlardan birini görürsen dur:

| İşaret | Ne demek | Ne yap |
|---|---|---|
| "Bu geçici bir çözüm" | Kalıcı olur | "Geçici çözüm istemiyorum, doğru şekilde yap" |
| Aynı hata 3. kez dönüyor | Temelde bir sorun var | "Son çalışan hâle dön, sorunu baştan analiz et" |
| Bir istekte 10+ dosya değişiyor | İş çok büyük | "Bunu 3 adıma böl, sadece ilkini yap" |
| Testler kırmızı ama "sonra düzeltiriz" | Borç birikiyor | Devam etme, önce yeşile getir |
| Anlamadığın yeni bir araç ekleniyor | Parça sayısı artıyor | "Bu olmadan yapılabilir mi?" diye sor |
| "Çalışıyor" diyor ama sen denemedin | Belki çalışmıyor | **Her zaman kendin dene** |

Son madde en önemlisi: **yapay zekanın "tamam, çalışıyor" demesi kanıt değildir.**
Kanıt, senin ekranda görmendir.

---

## 7. Haftalık ritim

**Her hafta sonunda 15 dakika:**

1. Sistemi baştan başlat, çalıştığını gör
2. `veri/` klasörünü harici diske kopyala (yedek)
3. Claude Code'a: "Bu hafta ne yaptık? docs/ILERLEME.md dosyasına yaz."
4. Bir sonraki haftanın ilk işini not et

Dördüncü madde, ertesi hafta "nerede kalmıştım" kaybını önler.

---

## 8. Neyi asla yapay zekaya bırakmayacaksın

Bunlar teknik değil, **senin işin:**

- **KKD politika kararları** — mont yelek sayılır mı, kabindeki operatör kapsamda mı
  (DALSAN İSG'ye sorulacak, bkz. `04-KKD-BARET-YELEK.md` §5.3)
- **KVKK yükümlülükleri** — aydınlatma metni, levhalar (DALSAN'ın hukuk birimi)
- **Kapsam sözleşmesi** — Rev.02 ek protokolü
- **Eşiklerin son hâli** — sayıyı yapay zeka önerir, **kabul eden İSG yetkilisidir**
- **"Yeterince iyi mi?" kararı** — gölge mod sonuçlarına bakıp anonsu açma kararı

Yapay zeka bunlarda fikir verir, ama **sorumluluğu taşıyan sensin.** Bu ayrım, İSG
sistemlerinde teknik ayrımlardan daha önemlidir.

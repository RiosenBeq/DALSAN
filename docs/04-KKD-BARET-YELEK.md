# 04 — KKD (Baret / Yelek) Tespiti: Modelin Öğretilmesi

Bu dosya, KKD senaryosunun **nasıl kurulacağını** anlatır: veri nasıl toplanır, nasıl
etiketlenir, model nasıl eğitilir, eşikler nasıl ayarlanır, sonuç DALSAN'a nasıl sunulur.

KKD, bu projedeki **en yanlış anlaşılmaya açık** özelliktir. Sebebi teknik değil,
beklenti yönetimidir: insan "kamera baret takmayanı görür" diye düşünür; gerçekte
sistem yalnızca **yeterince büyük ve engellenmemiş** kişiler için karar verebilir.

---

## 1. Neden bu iş forklift tespitinden farklı

| | Forklift | Baret |
|---|---|---|
| Nesne boyutu | Büyük, görüntünün önemli kısmı | Kişi boyunun ~1/8'i |
| Karar tipi | "Var mı?" (pozitif tespit) | **"Yok mu?" (negatif tespit)** |
| Yanlış negatifin bedeli | Kaçırılan forklift | Kaçırılan ihlal — kabul edilebilir |
| Yanlış pozitifin bedeli | Nadir | **Yüksek** — çalışan haksız yere uyarılır, sisteme güven biter |
| Veri toplama | Normal operasyonda bol | **Negatif örnek yok** — herkes baret takıyor |

Son satır kritik: uyumlu bir fabrikada "baretsiz kişi" görüntüsü neredeyse yoktur.
Model negatif örnek görmeden "baretsiz"i öğrenemez. Çözüm Bölüm 4'te.

### Negatif tespit ilkesi — sisteme yazılan kural

> **Kanıtın yokluğu, ihlalin varlığı değildir.**

Model üç durum üretir: `yes` / `no` / `unknown`. Yalnızca `no`, ve yalnızca yeterli
zamansal destekle, olay üretir. `unknown` **hiçbir zaman** uyarı üretmez.
Bu kural `rules/ppe.py` içinde açıkça kodlanır ve testle korunur.

---

## 2. Teknik yaklaşım: iki aşamalı

**Seçilen yöntem:** İnsan tespiti (zaten var) → kişi kutusunu kırp → küçük **çok etiketli
sınıflandırıcı** çalıştır.

```
Kare
 └─ Detector → person bbox + track_id      (zaten pipeline'da var)
      └─ bbox KKD bölgesinde mi?  ─hayır─▶ atla
           └─ bbox yüksekliği ≥ eşik? ─hayır─▶ unknown, olay yok
                └─ crop (üstten %10 padding) → 128×256'ya resize
                     └─ PPE sınıflandırıcı → {helmet: p, vest: p, visibility: p}
                          └─ track'e yaz → zamansal oylama → karar
```

### Neden iki aşamalı, tek aşamalı değil

Tek aşamalı alternatif: dedektöre `helmet` / `head` / `vest` sınıfları eklemek ve
geometrik olarak kişiye eşlemek.

| | İki aşamalı (seçilen) | Tek aşamalı |
|---|---|---|
| Veri maliyeti | Kırpılmış görüntüyü klasöre atmak — **dakikada 100+ örnek** | Küçük nesne bbox'ı çizmek — dakikada ~10 |
| Yeniden etiketleme | Ucuz — eşik değişince crop'lar yeniden bakılır | Pahalı |
| "Belirsiz" durumu | Doğal (visibility çıkışı + düşük güven) | Zorlama |
| Yeni KKD sınıfı ekleme | Yeni çıkış nöronu + veri | Yeni sınıf + yeniden eğitim |
| Küçük nesnede başarı | Kırpma sayesinde çözünürlük korunur | Zayıf |
| Görsel açıklanabilirlik | Kişi kutusu renkle işaretlenir | Baretin etrafında kutu — daha güzel |

Tek dezavantajı görsel açıklanabilirlik; MVP'de kişi kutusunun renklendirilmesi
(yeşil = uyumlu, kırmızı = ihlal, gri = belirsiz) yeterlidir.

**Ayrıca:** iki aşamalı yöntem, insan dedektörünü zaten çalıştırdığımız için
ek GPU maliyeti neredeyse sıfırdır. 4 kamerada, 5 karede bir, kişi başına 128×256
bir sınıflandırma — ölçülemeyecek kadar ucuz.

---

## 3. En önemli kısıt: piksel boyu

Baret, kişi boyunun yaklaşık **1/8'i** kadardır. Yelek ise gövdenin ~1/3'ü.

| Kişi bbox yüksekliği | Baş bölgesi | Baret kararı | Yelek kararı |
|---|---|---|---|
| ≥ 200 px | ~25 px | Güvenilir | Güvenilir |
| 120–200 px | 15–25 px | **Sınırda — çalışır ama eşik yüksek tutulmalı** | Güvenilir |
| 80–120 px | 10–15 px | Güvenilmez → `unknown` | Sınırda |
| < 80 px | < 10 px | İmkânsız | Güvenilmez |

**Varsayılan eşikler:** `min_person_height_px`: baret için **120**, yelek için **80**.

### Bunun saha karşılığı

1080p kamera, tipik geniş açı lens:

| Kişinin kameraya mesafesi | Yaklaşık bbox yüksekliği |
|---|---|
| ~8 m | 250–350 px |
| ~15 m | 130–200 px |
| ~25 m | 80–120 px |
| ~40 m | 50–70 px |

**Sonuç:** KKD bölgeleri **yakın alan** olmalıdır — kapı/giriş noktaları, yükleme rampası
önü, yaya geçiş noktaları. Tüm sahaya KKD kuralı yazmak işe yaramaz; yalnızca yanlış
"belirsiz" yığını üretir.

### 1. haftada yapılacak ölçüm (atlanamaz)

Her aday kamera için:

1. Bir kişi, KKD uygulanması istenen bölgenin **en uzak noktasında** dursun
2. Kareyi kaydet, kişinin bbox yüksekliğini piksel olarak ölç
3. 120 px'in altındaysa → o bölge baret için uygun **değil**; ya bölge küçültülür,
   ya kamera açısı değişir (fiziksel değişiklik teklifte kapsam dışı), ya baret kuralı
   o kamerada yalnızca yakın alt-bölgeye uygulanır

Bu ölçümün sonucu Rev.02 kapsam ek protokolüne **kamera-bölge tablosu** olarak yazılır.

---

## 4. Veri toplama — "nasıl tanıtacaksın"

### 4.1 İki tür veriye ihtiyaç var

| Tür | Kaynak | Zorluk |
|---|---|---|
| **Pozitif** (baret var, yelek var) | Normal operasyon — bol | Kolay |
| **Negatif** (baret yok, yelek yok) | **Normal operasyonda yok** | Zor — planlı çekim şart |

### 4.2 Planlı çekim seansı (2. hafta)

Bu, DALSAN'ın sağlaması gereken en kritik destektir. Ek protokolde yazılmalıdır.

**Nasıl kurgulanır:**

- İSG sorumlusu refakatinde, **üretim durmuşken veya düşük yoğunlukta**, kontrollü
  bir zaman aralığı (1–2 saat)
- 4–6 gönüllü çalışan (farklı boy, kilo, cilt tonu, iş kıyafeti)
- Her gönüllü, **KKD bölgesinin dışında güvenli bir alanda değil**, tam olarak kuralın
  uygulanacağı bölgede ve o kameranın açısında yürüsün
- Senaryo listesi (her biri 2–3 dk):
  1. Baret + yelek (uyumlu) — yürüyerek, durarak, kameraya sırtı dönük
  2. Baret yok, yelek var
  3. Baret var, yelek yok
  4. İkisi de yok
  5. Baret elde taşınıyor (kolda/elinde) — **politika kararı gerektirir, bkz. 5.3**
  6. Kep/bere takılı, baret yok
  7. Hi-vis mont (yelek değil) — **politika kararı**
  8. İki kişi yan yana / üst üste binen kutular
  9. Forklift kabininde oturan kişi
  10. Kısmen engellenmiş (direk, palet, araç arkası)

**Güvenlik notu:** Baretsiz senaryolar gerçek risk taşıyan bir alanda oynatılıyorsa
İSG'nin onayı ve alanın geçici olarak izole edilmesi şarttır. Bu seans bir İSG
faaliyeti gibi planlanmalıdır, "hızlıca birkaç video çekelim" gibi değil.

**KVKK notu:** Gönüllülerden görüntülerinin model eğitiminde kullanılacağına dair
bilgilendirilmiş onay alınmalıdır. Bu, DALSAN'ın aydınlatma metninden ayrı bir adımdır.

### 4.3 Normal operasyondan toplama (1.–4. hafta boyunca sürekli)

Sistem 2. haftadan itibaren kişi tespiti yapabilir hale gelir. O andan itibaren:

- Her KKD bölgesindeki kişi crop'ları, **saatte sınırlı sayıda örneklenerek** diske yazılır
  (ör. kamera başına saatte 60 crop, rastgele zamanlarda — aynı kişinin ardışık 200 karesi
  değil)
- Bu, pozitif örnekleri ve **gerçek çeşitliliği** (ışık, toz, hava, vardiya, kıyafet)
  ücretsiz toplar
- Toplama, retention politikasına tabidir ve etiketleme bitince ham crop'lar silinir

### 4.4 Kamu veri setleri — başlangıç için, tek başına asla yeterli değil

Açık baret veri setleri (hard hat / safety helmet tipi setler, Roboflow Universe ve
benzeri kaynaklarda bulunur) modelin **ön eğitimi** için değerlidir: negatif örnek
kıtlığını kısmen kapatır.

Ama alan farkı (domain gap) büyüktür ve DALSAN'a özgü iki sebeple daha da büyüktür:

1. **Alçı tozu.** Beyaz toz + beyaz/açık renkli baret = düşük kontrast. Kamu veri
   setlerinde bu koşul yoktur.
2. **Kamera açısı.** Kamu setleri çoğunlukla göz hizası fotoğraflardır; güvenlik
   kameraları yukarıdan bakar. Yukarıdan bakışta baret **daha görünür** (avantaj),
   yüz ise görünmez (dezavantaj — "baş var ama baret yok" kararı zorlaşır).

**Kural:** Kamu verisiyle ön eğit, **DALSAN crop'larıyla ince ayar yap**, değerlendirmeyi
**yalnızca DALSAN verisiyle** yap. Kamu verisindeki başarı oranı müşteriye asla
rapor edilmez.

### 4.5 Hedef veri miktarı

| Veri | Hedef | Minimum |
|---|---|---|
| Toplam kişi crop'u (DALSAN) | 4.000–6.000 | 2.500 |
| Bunun içinde `helmet: no` | 800–1.500 | 500 |
| Bunun içinde `vest: no` | 800–1.500 | 500 |
| Bunun içinde `unknown` (engellenmiş/küçük) | 500+ | 300 |
| Farklı kişi sayısı | ≥ 15 | 8 |
| Farklı gün sayısı | ≥ 8 | 4 |
| Gece/yapay ışık örnekleri | ≥ %20 | %10 |

`unknown` örneklerini etiketlemek boşa iş değil: modelin "göremiyorum" demeyi öğrenmesi,
yanlış alarmı azaltan en güçlü tek unsurdur.

---

## 5. Etiketleme

### 5.1 Araç

- **CVAT** (kendi sunucunda, ücretsiz) veya **Label Studio** — sınıflandırma projesi
- Ya da en basiti: crop'ları klasörlere ayır → `helmet_yes/`, `helmet_no/`, `helmet_unknown/`
  ve aynısı yelek için. 4.000 crop için klasör yöntemi CVAT kurmaktan hızlıdır.
- **Öneri:** 5. haftadan sonra sistemin kendi olay ekranına küçük bir "etiketle" butonu
  eklenir; İSG ekibi olayları incelerken veri seti kendiliğinden büyür (bkz. Bölüm 9).

### 5.2 Etiket şeması

Her crop için **iki bağımsız etiket**:

```
helmet ∈ {yes, no, unknown}
vest   ∈ {yes, no, unknown}
```

| Etiket | Tanım |
|---|---|
| `helmet: yes` | Baş görünüyor ve baret takılı |
| `helmet: no` | Baş **açıkça görünüyor** ve baret yok |
| `helmet: unknown` | Baş görünmüyor, engellenmiş, çok küçük, hareket bulanıklığı var, kare kenarında kesik |
| `vest: yes` | Hi-vis yelek/mont giyilmiş |
| `vest: no` | Gövde **açıkça görünüyor** ve hi-vis yok |
| `vest: unknown` | Gövde engellenmiş, kesik, çok küçük |

**En sık yapılan etiketleme hatası:** emin olunamayan crop'a `no` demek.
Şüphe varsa **her zaman `unknown`**. Bu kural etiketçiye yazılı verilir.

### 5.3 Etiketlemeden ÖNCE DALSAN İSG ile kapatılacak politika soruları

Bunlar teknik değil, kural sorularıdır. Yanlış cevapla etiketlenen veri seti baştan
bozuktur ve yeniden etiketleme gerektirir.

| # | Soru | Neden önemli |
|---|---|---|
| 1 | Hi-vis **mont** yelek yerine geçer mi? | Kışın herkes mont giyer; "hayır" dersek kış boyu yanlış alarm |
| 2 | Baret elde/kolda taşınıyorsa ihlal mi? | Model bunu ayırt edebilir ama önce politika lazım |
| 3 | Kep/bere/bone baret sayılır mı? (Hayır olacaktır ama yazılı olmalı) | Etiket tutarlılığı |
| 4 | Forklift **kabininde** oturan operatöre baret kuralı uygulanır mı? | Kapalı kabinde çoğu tesiste muafiyet var |
| 5 | Tır **kabininde** kalan şoför? | Aynı |
| 6 | Ziyaretçi/misafir baretine (farklı renk) kural aynı mı? | Renk modeli etkiler |
| 7 | Baret rengi role göre değişiyor mu? Hepsi geçerli mi? | Model tüm renkleri görmeli |
| 8 | Ofis personeli KKD bölgesinden geçerken? | Bölge sınırı kararı |
| 9 | Yelek zorunluluğu tüm bölgede mi, yoksa yalnızca araç trafiği olan kısımda mı? | Bölge çizimi |
| 10 | Vardiya değişiminde KKD giyinme noktası bölge içinde mi? | Giyinirken ihlal üretmemeli |

Cevaplar `docs/kkd-politika.md` olarak yazılır ve etiketleme kılavuzunun ekidir.

### 5.4 Veri bölme — rastgele bölme YASAK

Crop'lar **zaman ve kamera** bazında bölünür:

```
train: 1.–5. günlerin verisi
val:   6. gün
test:  7.–8. gün + planlı çekim seansının bir bölümü
```

**Neden:** Rastgele bölmede aynı kişinin aynı saniyedeki 5 karesi hem train hem test'e
düşer. Model ezberler, test skoru %98 çıkar, sahada %70 olur. Bu hata bu alanda
en sık yapılan hatadır ve müşteriye yanlış vaat verilmesine yol açar.

---

## 6. Model ve eğitim

### 6.1 Mimari

- **Omurga:** ImageNet ön eğitimli hafif sınıflandırıcı — MobileNetV3-Large,
  EfficientNet-B0 veya ResNet-18 sınıfı. 4 kameralı bir sistemde bunların hepsi
  fazlasıyla hızlıdır; seçim bakım kolaylığına göre yapılır.
- **Giriş:** kişi crop'u, üstten %10 padding ile, **128×256** (portre en-boy korunur)
- **Çıkış:** 4 logit → `helmet_yes`, `helmet_no`, `vest_yes`, `vest_no`
  (her çift kendi içinde softmax; `unknown` **ayrı sınıf değil**, düşük güvenden türer)

Alternatif ve daha temiz olan: her KKD için 3 sınıflı softmax (`yes`/`no`/`unknown`).
`unknown`'ı etiketlediğimiz için bu mümkündür ve **tercih edilendir** — model
"göremiyorum"u açıkça öğrenir.

### 6.2 Augmentasyon

| Uygula | Uygulama |
|---|---|
| Renk/parlaklık/kontrast jitter | **Şart** — toz, gün ışığı, sodyum lamba |
| Rastgele oklüzyon (cutout) | **Şart** — palet/direk arkası |
| Yatay çevirme | Evet |
| Hafif döndürme (±10°) | Evet |
| Gauss bulanıklık + JPEG bozulması | Evet — RTSP sıkıştırma artefaktlarını taklit eder |
| Rastgele ölçekleme + yeniden büyütme | **Şart** — uzak/küçük kişileri simüle eder |
| **Dikey çevirme** | **Asla** — insan ters durmaz, model bozulur |

### 6.3 Sınıf dengesizliği

`no` örnekleri azdır. Sınıf ağırlıklı kayıp fonksiyonu veya azınlık sınıfın
fazladan örneklenmesi kullanılır. **Ama:** eğitim setini yapay olarak dengelemek,
gerçek dünyadaki oranı bozar; bu yüzden eşik ayarı **doğal dağılımlı val seti**
üzerinde yapılır.

### 6.4 Güven kalibrasyonu

Ham softmax çıktısı aşırı güvenlidir. Val seti üzerinde **sıcaklık ölçeklemesi
(temperature scaling)** uygulanır — 20 satır kod. Bunsuz `min_confidence: 0.7`
gibi bir eşik anlamsız bir sayıdır.

### 6.5 Eğitim maliyeti

Birkaç bin crop, hafif omurga → modern bir GPU'da **dakikalar**. Pahalı olan kısım
model değil, **veri ve etiketlemedir.** Plan yaparken efor buna göre dağıtılır:
%70 veri toplama + etiketleme + politika kararları, %10 eğitim, %20 eşik ayarı.

---

## 7. Kural motoruna bağlanma

Sınıflandırıcı **kare bazında** çıktı verir. Kural motoru **track bazında** karar verir.

### 7.1 Zamansal oylama

Her `person` track'i için son N değerlendirmenin (kare değil — 5 karede bir
değerlendiriliyor) kayan penceresi tutulur:

```python
# rules/ppe.py — saf mantık, CV bağımlılığı yok
def evaluate_ppe(track_history, params) -> PpeDecision:
    # 1. Bölge içinde mi ve yeterince uzun süredir mi
    # 2. Yeterli sayıda geçerli (unknown olmayan) gözlem var mı
    # 3. Geçerli gözlemlerin çoğunluğu 'no' mu ve güven eşiğin üstünde mi
    # 4. Değilse: unknown → olay yok
```

**Varsayılan parametreler:**

| Parametre | Varsayılan | Anlamı |
|---|---|---|
| `min_person_height_px` | 120 (baret) / 80 (yelek) | Altında değerlendirme yapılmaz |
| `min_confidence` | 0.70 | Kalibre edilmiş güven eşiği |
| `window_size` | 15 | Son 15 değerlendirme |
| `min_valid_observations` | 8 | En az 8'i `unknown` olmayacak |
| `violation_ratio` | 0.75 | Geçerli gözlemlerin ≥ %75'i `no` diyecek |
| `min_dwell_s` | 3.0 | Kişi bölgede en az 3 sn kalacak |
| `cooldown_s` | 180 | Aynı track için 3 dk tekrar uyarı yok |
| `require_full_bbox` | true | Kare kenarında kesik kutular değerlendirilmez |

Bu parametrelerin hepsi **arayüzden düzenlenebilir** ve değişiklik yeniden başlatma
gerektirmez. 7. haftadaki ayarlama tam olarak bu tablonun üzerinde yapılır.

### 7.2 Neden bu kadar muhafazakâr

Kişi 3 saniye bölgede kalacak, 15 gözlemin en az 8'i geçerli olacak, bunların
%75'i "yok" diyecek. Bu, tek karelik bir hatanın uyarıya dönüşmesini imkânsıza
yakın hale getirir.

Bedeli: bölgeden 2 saniyede geçen baretsiz kişi **kaçırılır.** Bu kabul edilmiş
bir takastır — `00-PROJE-BAGLAMI.md`'deki "yanlış alarm, kaçırılan ihlalden
daha maliyetlidir" ilkesinin doğrudan sonucudur.

---

## 8. Ölçme ve eşik ayarı (7. hafta — K11)

### 8.1 Doğru metrik

**Kare bazlı doğruluk (accuracy) raporlanmaz.** Anlamsızdır ve yanıltıcıdır.

Raporlanacak metrik: **track bazlı hassasiyet (precision)** —
"sistem ihlal dedi, gerçekten ihlal miydi?"

```
precision = doğru ihlal olayları / toplam ihlal olayları
```

Hedef: **≥ 0.90**. Yani üretilen her 10 uyarıdan en az 9'u gerçek olmalı.

Duyarlılık (recall) da ölçülür ve **dürüstçe raporlanır**, ama sözleşmeye
taahhüt olarak yazılmaz — çünkü "kaç ihlali kaçırdık" sorusunun gerçek cevabı
ancak tam manuel sayımla bilinir.

### 8.2 Ölçüm prosedürü

1. Sistem 3 gün boyunca KKD kuralı **aktif ama anonssuz** çalışır (gölge mod)
2. Üretilen tüm KKD olayları İSG ekibi ve NextGen tarafından birlikte incelenir
3. Her olay `İncelendi` veya `Yanlış alarm` olarak işaretlenir (bu alan MVP'de var)
4. Precision hesaplanır
5. Precision < 0.90 ise: eşikler sıkılaştırılır (güven ↑, oran ↑, bölge küçültülür)
   veya o bölge/kamera KKD kapsamından çıkarılır
6. Kabul edilebilir seviyeye gelince anons açılır

**Gölge mod, KKD'nin devreye alınmasının tek doğru yoludur.** İlk günden anonsla
başlamak, sistem henüz ayarlanmamışken çalışanı yanlış uyarır ve bir daha
düzelmeyecek bir güven kaybı yaratır.

### 8.3 Yanlış alarmın tipik kaynakları ve çaresi

| Kaynak | Belirti | Çare |
|---|---|---|
| Kişi çok uzak | `unknown` yerine `no` çıkıyor | `min_person_height_px` ↑ |
| Sırtı dönük, baret açıdan görünmüyor | Aralıklı `no` | `min_confidence` ↑, `violation_ratio` ↑ |
| Toz/parlama | Kümelenmiş yanlış alarm, belirli saatte | Augmentasyona o koşulun verisini ekle, yeniden eğit |
| Kişi bölge sınırında | Girip çıkıyor, tekrar uyarı | Bölgeyi içeri çek, `min_dwell_s` ↑ |
| Forklift kabinindeki operatör | Sürekli ihlal | Politika kararı (5.3 #4) + kabin alanını bölgeden çıkar |
| Hi-vis mont yelek sayılmıyor | Kışın patlama | Politika kararı (5.3 #1) + veriye mont ekle |
| İki kişi üst üste | Yanlış crop | `require_full_bbox` + oklüzyon oranı kontrolü |

---

## 9. Sürekli iyileşme döngüsü (MVP'de temeli, Phase 2'de tamamı)

MVP'de olan: olayların `Yanlış alarm` olarak işaretlenmesi + snapshot'ın saklanması.

Bu iki şey, Phase 2'deki döngünün **veri kaynağıdır**:

```
Olay üretilir → İSG "Yanlış alarm" der → crop + doğru etiket veri setine düşer
   → periyodik yeniden eğitim → model sürümü yükselir → precision artar
```

MVP'de bu döngü **otomatik değildir** ve olmamalıdır. Ama veriyi topladığı için
Phase 2'de yalnızca eğitim betiği yazmak kalır. Bu, "geleceğe hazırlık ≠ bugün
geliştirme" ilkesinin iyi bir örneğidir.

**Model sürümleme:** her eğitilen modele sürüm numarası verilir, `models/` altında
saklanır, hangi olayın hangi model sürümüyle üretildiği `events.details` içine
yazılır. Bu olmadan "model iyileşti mi" sorusu cevaplanamaz.

---

## 10. DALSAN'a sunum — özet mesaj

Toplantıda söylenecek üç cümle:

1. **"Sistem, tanımladığımız yakın alan bölgelerinde baret ve yelek durumunu
   değerlendirir; kameraya uzak veya görüşü engellenmiş kişiler için karar vermez
   ve bunları 'belirsiz' olarak işaretler."**

2. **"Hedefimiz her ihlali yakalamak değil; ürettiğimiz her uyarının doğru olması.
   İlk üç hafta sistemi sessiz modda çalıştırıp ürettiği uyarıları birlikte
   inceleyeceğiz, ondan sonra anonsu açacağız."**

3. **"Bunun çalışması için sizden iki şey gerekiyor: KKD kurallarınızın net yazılı
   cevabı (mont yelek sayılır mı, kabindeki operatöre uygulanır mı gibi) ve
   2. haftada 1-2 saatlik planlı bir çekim seansı."**

Söylenmemesi gerekenler: yüzde cinsinden doğruluk vaadi, "yapay zeka herkesi görür"
tipi ifadeler, KKD'nin disiplin süreçlerinde kullanılabileceği ihsası.

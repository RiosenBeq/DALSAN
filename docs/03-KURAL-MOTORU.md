# 03 — Kural Motoru

Dört kural tipi tüm senaryoları karşılar. Beşincisi eklenmeden önce mevcut
dördüyle çözülüp çözülemediği sorgulanır.

| Tip | Teklifteki senaryolar |
|---|---|
| `zone_intrusion` | 5 (yaya yolu), 6 (sevkiyat/yükleme alanı), 7 (tır konumlanma) |
| `safe_distance` | 8 (güvenli mesafe) |
| `ppe_violation` | **Yeni kapsam** — baret / yelek |
| `vehicle_speed` | **Yeni kapsam** — fabrika içi hız sınırı (docs/07 #15'ten geldi) |

Ortak çıktı: `Violation(rule_id, camera_id, track_ids, measured_value, zone_id, evidence)`.
Ortak filtre: cooldown. Ortak ilke: **kare değil, track bazlı karar.**

---

## 1. `zone_intrusion` — Bölge ihlali

**Soru:** Tanımlı sınıftan bir nesne, tanımlı bölgede, tanımlı süreden uzun kaldı mı?

| Parametre | Varsayılan | Anlam |
|---|---|---|
| `zone_id` | zorunlu | Hangi bölge |
| `target_classes` | zorunlu | `["person"]`, `["forklift","truck"]` vb. |
| `mode` | `inside` | `inside` = bölgede olmak ihlal · `outside` = bölge dışında olmak ihlal |
| `min_dwell_s` | 2.0 | Bölgede minimum kalış |
| `cooldown_s` | 120 | Track başına tekrar bastırma |
| `bitis_s` | 3.0 | Olayın bitmesi için koşulun görülmediği süre (§5.3; dört tipte ortak) |
| `gecit_haric` | true | Ayak noktası etkin bir **yaya-araç geçidindeyse** (bölge tipi `crossing`) ihlal sayılmaz |

**`mode` neden var:** "Yaya yolunu kullan" kuralı aslında "yaya yolu **dışında** insan"
kuralıdır. Tek parametreyle üç senaryo çözülür:

| Senaryo | zone_type | target | mode |
|---|---|---|---|
| Yaya yolu kullanımı | pedestrian_path | person | outside |
| Yükleme alanında yaya | loading_area | person | inside |
| Tır yanlış konumda | truck_parking | truck | outside |

**Karar noktası:** bbox alt-orta noktası (zemin teması) poligonun içinde mi.

**Geçit istisnası:** aynı kamerada çizilmiş etkin bir yaya-araç geçidi
(`crossing`) poligonundaki ayak noktası, bölgeden çıkmış gibi sayılır: araç
yolunu geçitten geçen yaya, yaya yolunu geçitten geçen forklift ve "yolun
dışında" kuralında yolu geçitten karşıya geçen kişi uyarı üretmez. Kuralın
kendi bölgesi geçitse istisna uygulanmaz.

---

## 2. `safe_distance` — Güvenli mesafe

**Soru:** İnsan ile forklift/tır arasındaki gerçek dünya mesafesi eşiğin altına düştü mü?

| Parametre | Varsayılan | Anlam |
|---|---|---|
| `subject_classes` | `["person"]` | Korunan taraf |
| `object_classes` | `["forklift","truck"]` | Riskli taraf |
| `distance_m` | 3.0 | Eşik (metre) |
| `min_frames` | 5 | Ardışık kaç değerlendirmede eşik altında olmalı |
| `require_moving_vehicle` | true | Araç duruyorsa uyarı üretme |
| `min_speed_mps` | 0.3 | "Hareket halinde" eşiği |
| `zone_id` | nullable | Boşsa tüm kare. Verilmişse ve bölge kapalıysa ya da yoksa kural çalışmaz (R21) |
| `cooldown_s` | 90 | Track çifti başına |
| `histerezis_m` | 0.5 | Açılmış olay, mesafe `distance_m + histerezis_m`'yi aşınca biter (§5.3); açılışı etkilemez |

**Kalibrasyon zorunluluğu:** Kamera kalibre edilmemişse bu kural **çalışmaz** —
sessizce yaklaşık bir sonuç üretmez, açıkça pasif kalır ve arayüzde "kalibrasyon
bekleniyor" olarak görünür. Kalibre edilmemiş piksel mesafesi perspektifle
kat kat değişir; üretilen sayı yanıltıcı olur.

**`require_moving_vehicle` neden var:** Park halindeki tırın yanında duran şoför,
mesafe kuralını sürekli ihlal eder ama gerçek risk yoktur. Bu tek parametre,
sevkiyat alanındaki yanlış alarmların büyük kısmını keser.

**Hesap:** Her iki nesnenin ayak noktası homografi ile zemin düzlemine yansıtılır,
öklid mesafesi metre cinsinden hesaplanır.

---

## 3. `ppe_violation` — KKD ihlali

**Soru:** KKD zorunlu bölgede, yeterince görünür bir kişi, gerekli KKD'yi
yeterince tutarlı biçimde takmıyor mu?

> Tam gerekçe, veri toplama ve eğitim için: `04-KKD-BARET-YELEK.md`

| Parametre | Varsayılan | Anlam |
|---|---|---|
| `zone_id` | **zorunlu** | KKD kuralı bölgesiz tanımlanamaz |
| `required_ppe` | `["helmet","vest"]` | Alt küme seçilebilir |
| `min_person_height_px` | 120 (baret) / 80 (yelek) | Altında değerlendirme yok |
| `min_confidence` | 0.70 | Kalibre edilmiş güven eşiği |
| `window_size` | 15 | Kayan pencere (değerlendirme sayısı) |
| `min_valid_observations` | 8 | Penceredeki `unknown` olmayan minimum gözlem |
| `violation_ratio` | 0.75 | Geçerli gözlemlerin bu oranı `no` demeli |
| `min_dwell_s` | 3.0 | Bölgede minimum kalış |
| `require_full_bbox` | true | Kare kenarında kesik kutu değerlendirilmez |
| `surucu_muaf` | true | Forklift/tır kabinindeki sürücü değerlendirilmez (aşağıda) |
| `surucu_ortusme_orani` | 0.6 | Kişi kutusunun bu kadarı araçla örtüşürse sürücü sayılır |
| `max_kisi_ortusmesi` | boş = kapalı | İki kişi kutusu bu IoU'yu aşarsa o an belirsiz |
| `min_netlik` | boş = kapalı | Kırpık netliği (Laplacian varyansı) altındaysa o an belirsiz |
| `cooldown_s` | 180 | Kişi **ve kalem** başına |

**Kalem başına olay (Faz 3d).** Baret ve yelek ayrı karar, ayrı olay ve ayrı
beklemedir: yalnız yelek eksikse yalnız `PPE_NO_VEST` (orta) açılır, ikisi eksikse
`PPE_NO_HELMET` (yüksek) ve `PPE_NO_VEST` iki ayrı olay olur. Olay anahtarı
`(kural, kamera, iz, kalem)`; bir kalemin kararı belirsize dönerse yalnız o
kalemin olayı `belirsiz` sebebiyle kapanır. `details.eksik_kkd` tek elemanlıdır;
ayrıntı iki kalemin kararını da taşır.

**Gölge ve model sürümü.** KKD kuralı gölge modda doğar (hazır kural da formdan
kurulan da); form anonsu açamaz. Anonsu Komuta → Uyarı zinciri açar ve o an yüklü
KKD model sürümünü `rules.approved_model_version`'a yazar. Süpervizör yüklü
modelin sürümünü bununla karşılaştırır: farklıysa ya da hiç onaylanmamışsa kuralı
gölgeye alır ve `PPE_MODEL_CHANGED` yazar. Olay kaydı sürer, hoparlör susar;
pencereler ve bekleme süreleri sıfırlanmaz (gölge kural imzasına girmez).

### Üç durumlu karar — motorun en önemli kuralı

```
yes     → uyumlu, olay yok
no      → ihlal adayı, zamansal oylamaya girer
unknown → HİÇBİR ZAMAN olay üretmez
```

`unknown` üretilen durumlar: kişi çok küçük · kare kenarında kesik · model güveni
eşik altı · baş/gövde görünmüyor (modelin "görünmüyor" çıkışı) · kabindeki sürücü
(`surucu_muaf`: ayak noktası forklift/tır kutusunda ya da kişi kutusu araçla
`surucu_ortusme_orani` kadar örtüşüyor) · üst üste iki kişi (`max_kisi_ortusmesi`)
· bulanık kırpık (`min_netlik`). Son üçü o karede İKİ kalemi de belirsiz yapar.
Örtüşme ve netlik eşikleri gölge moddaki ölçümle seçilir; ölçülene kadar kapalıdır.

**KKD muaf alan (`ppe_exempt`).** Zorunlu alanın içine çizilen muaf alan (kabin,
ofis köşesi) oyulur: içindeki kişi bölge dışında sayılır, değerlendirilmez. Oyma
iki yerde uygulanır: kural kararında (`rules/kkd.py`) ve kırpığı üreten kapıda
(`boru_hatti.kkd_bolgesinde_mi`). Böylece muaf alandan KKD sınıflandırması
yapılmaz, veri örneği de alınmaz (docs/17 §5.5). Kapalı muaf alan oymaz.

**Kanıtın yokluğu ihlalin varlığı değildir.** Bu cümle `rules/ppe.py` başına yorum
olarak yazılır ve testle korunur (`test_unknown_never_produces_event`).

### Olay kaydına yazılan kanıt

`events.details` içine:

```json
{
  "ppe": {
    "required": ["helmet"],
    "helmet": {"decision": "no", "valid_obs": 11, "negative_obs": 9, "mean_conf": 0.83},
    "vest": {"decision": "yes"},
    "person_height_px": 168,
    "model_version": "kkd-3f2a9c1b04de",
    "dwell_s": 5.2
  },
  "eksik_kkd": ["helmet"]
}
```

`model_version` sınıflandırıcının sürümüdür: dosya adı + sha256'nın ilk 12 hanesi
(docs/04 §6.6).

`model_version` olmadan "model iyileşti mi" sorusu cevaplanamaz. Zorunludur.

---

## 4. `vehicle_speed` — Araç hız sınırı

**Soru:** Forklift (ya da tır) fabrika içindeki hız sınırını aştı mı?

| Parametre | Varsayılan | Anlam |
|---|---|---|
| `target_classes` | `["forklift","truck"]` | Hız sınırına tabi araçlar |
| `speed_limit_mps` | 2.5 | Eşik (m/sn). 2,5 m/sn ≈ 9 km/sa |
| `window_size` | 5 | Kaç ölçümün **ortancasına** bakılır |
| `zone_id` | nullable | Boşsa tüm kare |
| `cooldown_s` | 90 | Track başına |

**Neden ayrı bir kural:** güvenli mesafe kuralı hızı yalnızca "araç hareket
halinde mi" sorusuna cevap vermek için kullanır. Yanında kimse olmadan hızlı
giden bir forklift, mesafe kuralına **görünmez**; oysa fabrika içi kazalarda hız
tek başına bir risktir.

**Kalibrasyon zorunluluğu** §2'dekiyle aynıdır ve aynı sebeptendir: hız, ayak
noktasının **zemindeki** yer değişiminden ölçülür. Kalibre edilmemiş kamerada
kural pasif kalır ve arayüzde "kalibrasyon bekleniyor" görünür.

**Neden ortanca, neden ortalama değil:** kare başına hız ölçümü gürültülüdür —
tespit kutusunun bir karelik oynaması ayak noktasını santimetrelerce kaydırır ve
0,2 saniyelik aralığa bölününce metre/saniyelik bir sıçrama gibi görünür. Beş
ölçümün dördü 0,5 m/sn, biri 20 m/sn ise **ortalama** 4,4 m/sn çıkar ve duran
forklift hız cezası yer; **ortanca** 0,5 m/sn kalır. Ekrana ve olay kaydına
yazılan sayı da bu ortancadır: kullanıcı sıçrama değerini değil aracın gerçek
hızını görür.

**Birim:** ayar `m/sn` tutulur (`Tespit.hiz_mps` ile aynı olsun diye), ekranda ve
olay kaydında `km/sa` karşılığı da yazılır — fabrika hız levhaları km/sa'dır.

**Hazır kural yok, bilerek:** bu kural en çok bölgesiz (tüm kare) anlamlıdır ve
"araç sahası" bölgesinin hazır kuralı zaten güvenli mesafedir. Kurallar
sayfasından tek formla kurulur.

---

## 5. Cooldown — ortak filtre

Anahtar: `(rule_id, camera_id, track_id)` — mesafe kuralında `(rule_id, camera_id, track_id_pair)`.

Track kaybolup yeni ID ile döndüğünde cooldown sıfırlanır. Bu bilinen bir sınırdır:
aynı kişi yeni track ID alırsa tekrar uyarı üretebilir. Track kalıcılığını artırmak
(ByteTrack `track_buffer` parametresi) bunu azaltır; tamamen çözmek yeniden kimliklendirme
(re-ID) gerektirir → Phase 2.

**Anons cooldown'u ayrıdır ve daha uzundur.** Ekranda 3 olay görünmesi sorun değil;
hoparlörün 3 kez bağırması sorundur.

---

## 5.1 Sayım, kural DEĞİLDİR

`rules/sayim.py` bu dosyadaki dört kural tipinin yanında durur ama onlardan
**ayrıdır**: ihlal üretmez, cooldown'a girmez, anons tetiklemez, olay yazmaz.
Yalnızca "bölgede kaç var" ve "kaç tanesi girdi" sorularını cevaplar.

Neden ayrı: bir sayı yanlışsa kimse yanlış uyarı almaz. Kural mantığıyla aynı
dosyaya konsaydı, sayım için yapılan her ayar ihlal kararını da riske atardı.

Sayım kural gerektirmez: bölge çizilen her kamerada kendiliğinden çalışır.
Ayrıntı ve üç sayının anlamı `02-MIMARI.md` §8'de.

## 5.2 Olay kodu ve önem

Her ihlal bir **olay kodu** ve bir **önem** taşır (şema 007, `docs/17` §6.1).
Değerlendirici bunları bilmez: kural motoru değerlendirmeden sonra atar
(`rules/motor.py` `_kodla`, sözlük `rules/olay_kodu.py`). Kod; kural tipinden,
bölge ihlalinde de yön + bölge tipi + ihlali **o an tetikleyen** sınıftan çıkar:

| Kural | Yön | Bölge tipi | Tetikleyen | Kod | Varsayılan önem |
|---|---|---|---|---|---|
| zone_intrusion | inside | vehicle_area | person | `PERSON_IN_VEHICLE_LANE` | Orta (bölgede araç varken Yüksek) |
| zone_intrusion | inside | pedestrian_path | forklift, truck | `VEHICLE_ON_WALKWAY` | Yüksek |
| zone_intrusion | inside | restricted | person | `RESTRICTED_ENTRY` | Yüksek |
| zone_intrusion | outside | pedestrian_path | person | `PERSON_OFF_WALKWAY` | Orta |
| zone_intrusion | inside | loading_area | person | `PERSON_IN_LOADING_AREA` | Orta |
| zone_intrusion | outside | truck_parking | truck | `VEHICLE_OUT_OF_POSITION` | Düşük |
| zone_intrusion | tabloya uymayan her birleşim | | | `ZONE_INTRUSION` (bölge tipi ayrıntıda) | Orta |
| safe_distance | | | | `VEHICLE_PERSON_PROXIMITY` | Kritik |
| ppe_violation | | | baret eksik / yalnız yelek eksik | `PPE_NO_HELMET` / `PPE_NO_VEST` | Yüksek / Orta |
| vehicle_speed | | | | `VEHICLE_OVERSPEED` | Yüksek |

Kural satırındaki `severity` `warning` ise (şema varsayılanı; bugünkü bütün
kurallar) kodun varsayılan önemi geçerlidir; `critical` / `high` / `medium` /
`low` yazılıysa o geçerlidir ve bağlam onu değiştirmez. Tanınmayan değer
varsayılana düşer. Baret ve yelek birlikte eksikse bugün tek olay yazılır ve
kodu baretinkidir; kalem başına ayrı olay Faz 3d'dedir.

**Kural formunda önem.** Formdaki *Önem* seçimi ya "Varsayılan"dır (`warning`)
ya da açık bir düzey. "Varsayılan"ın yanında kuralın üretebileceği olaylar ve
önemleri yazar ("Baret yok: Yüksek; Yelek yok: Orta") — tip, bölge tipi, yön ve
hedef sınıflardan hesaplanır (`rules/olay_kodu.py` `kural_olay_kodlari`,
tarayıcı `/kurallar/onem`'den sorar; eşlemenin ikinci kopyası yoktur). Kuralın
EN AĞIR olayının varsayılanından (bağlamsal yükseltme dahil) **hafif** bir
düzey seçmek sarı bir kutuda onay ister; sunucu da kaydederken denetler ve
onaysız kaydı reddeder. Örnek: araç yolundaki yaya için "Orta" seçmek, araç
varken yapılan Yüksek yükseltmesini kapatır — bu da varsayılanın altına inmektir.
Önemi yükseltmek onay istemez. Kurallar listesinin Önem sütunu, açık seçimi ya
da "varsayılan" notuyla kodun önemini gösterir.

## 5.3 Olay yaşam döngüsü: açıldı → hatırlatma → bitti

Bir ihlal artık tek bir anlık kayıt değil, başı ve sonu olan bir **olaydır**
(`rules/olay_durumu.py`, docs/17 §6.3). Değerlendiriciler değişmedi: ihlal
üretir ve tekrar bastırmayı (cooldown) kendileri uygular. Motor bu ihlalleri
olaya çevirir:

| Geçiş | Ne zaman | Sonuç |
|---|---|---|
| **açıldı** | Anahtarı (kural, kamera, iz) açık olmayan bir ihlal | Yeni olay satırı, bitişi boş ("sürüyor"); anons |
| **hatırlatma** | Olay açıkken kuralın bekleme süresi dolup yeniden ihlal | **Yeni satır yok**; anons tekrarlanır (gölge modda susar) |
| **bitti** | Koşul `bitis_s` (varsayılan 3 sn) boyunca görülmedi | Bitiş yazılır: koşulun **son görüldüğü an** |

Koşulun "sürüyor" sayılması girişten gevşektir (çıkış eşiği):

| Kural | Açılış | Sürüyor sayılır |
|---|---|---|
| Bölge | ayak noktası bölgede ve kalış ≥ `min_dwell_s` | ayak noktası bölgede (kalıştan bağımsız) ya da iz kayıp toleransı içinde |
| Mesafe | mesafe < `distance_m`, `min_frames` ardışık, araç hareketli | çift hâlâ `distance_m + histerezis_m` içinde (araç durdu diye bitmez) |
| KKD | oy "yok" | oy hâlâ "yok"; oy **belirsize** dönerse olay `belirsiz` sebebiyle biter, belirsiz dönemde hatırlatma olmaz |
| Hız | pencere ortancası ≥ sınır | son ortanca hâlâ sınırın üstünde |

Bitiş sebepleri olayın ayrıntısına yazılır (`kapanis_sebebi`): koşul bitti, oy
belirsizleşti, iz kayboldu, kural değişti (kural düzenlenince ya da silinince
açık olayı hemen biter; başka kuralların olayları sürer), kamera görüntüsü
kesildi, kamera ayarı değişti, sistem durdu, sistem yeniden başladı.

Kapandıktan sonra aynı kişi aynı kurala yeniden takılırsa yeni olay, ancak
kuralın bekleme süresi dolunca açılır — bugünkü tekrar bastırma kuralı.

## 5.4 Kural formu

- Parametre alanlarının varsayılanları şemadan gelir (`rules/parametreler.py`
  `varsayilan_params`; R25). Formda sayıların ikinci bir kopyası yoktur.
- `bitis_s` dört tipte ortak alandır; `gecit_haric` yalnız bölge ihlalinde,
  `histerezis_m` yalnız güvenli mesafede görünür.
- Kaydetmek, formda **olmayan** bir parametreyi varsayılana döndürmez: aynı
  tipteki kuralın önceki değeri korunur. Boş bırakılan sayı alanı da önceki
  değerde (yeni kuralda şema varsayılanında) kalır. Tip değiştirilirse eski
  tipin parametreleri taşınmaz.
- Cooldown yeni kuralda tipin varsayılanıyla dolar (§5) ve tip değişince —
  elle değiştirilmediyse — yeni tipinkine geçer.
- Şemanın her alanının formda karşılığı olduğunu `tests/test_kural_formu.py`
  denetler: karşılığı olmayan alan hiç değiştirilemezdi.

## 6. Yeni kural tipi ekleme prosedürü

1. `backend/app/rules/<tip>.py` — saf değerlendirici sınıfı (`degerlendir(baglam) -> list[Ihlal]`)
2. `backend/app/rules/parametreler.py` — `params` Pydantic modeli + `PARAM_SEMALARI` kaydı
3. `backend/app/rules/motor.py` — `DEGERLENDIRICILER` kaydı
3a. `backend/app/rules/olay_kodu.py` — `ihlal_kodu` içinde tipin olay kodu; kod
    sözlükte yoksa `OLAY_KODLARI`'na adı ve varsayılan önemiyle eklenir
    (`tests/rules/test_olay_kodu.py` kodsuz kalan tipi yakalar)
3b. Değerlendiricide `aktif_anahtarlar()` — koşulun hâlâ sürdüğü anahtarlar
    (§5.3 çıkış eşiği); şemaya ortak `bitis_s` alanı
4. `tests/rules/test_<tip>.py` — en az: pozitif durum, negatif durum, sınır durum, eksik/ölçülemeyen veri durumu, cooldown
5. Arayüz: `web/ortak.py` (`KURAL_TIPLERI`, `VARSAYILAN_COOLDOWN_SN`), `web/kurallar.py`
   (`_formdan_params`), `templates/kural_form.html` (alan kümesi)

Başka hiçbir dosyaya dokunulmaz. Bu şablon bozuluyorsa mimari sınır ihlal ediliyor demektir.

**Şema kısıtı da işin parçasıdır.** `rules.rule_type` bir CHECK kısıtıyla
kapalıdır; yeni tip için ayrı bir göç betiği gerekir. SQLite'ta CHECK
değiştirmek tabloyu yeniden kurmaktır ve bu, yabancı anahtar zorlaması AÇIKKEN
tüm olay geçmişinin kural bağlantısını **sessizce siler** (ölçülerek
doğrulandı). Doğru yol `backend/sema/005_arac_hizi_kurali.sql` dosyasında
örneklenmiştir: betiğin başına `-- DALSAN-SEMA: YABANCI-ANAHTAR-KAPALI` işaret
satırı konur; `app/veritabani.py` bunu görüp anahtarı işlem dışında kapatır,
sonra geri açar ve `PRAGMA foreign_key_check` ile bağlantıların sağlam kaldığını
doğrular.

---

## Ek — Hazır kurallar

Kamera sayfasındaki "Hazır kurallar" düğmeleri bölge tipine uyan kuralı tek
tıkla kurar (`web/ortak.py` `HAZIR_KURALLAR`, `EK_HAZIR_KURALLAR`). Eşikler
şemadan (`rules/parametreler.py`) gelir; aşağıda yalnız farklı olanlar var.

| Bölge tipi | Kural | Hedef · yön | Anons mesajı | Gölge |
|---|---|---|---|---|
| Yaya yolu | yaya yolu kuralı | kişi · dışında (kalış 5 sn) | `pedestrian_path` | hayır |
| Yaya yolu | **yaya yolunda araç** (ek) | forklift, tır · içinde (kalış 1 sn) | `vehicle_on_walkway` | **evet** |
| Araç sahası | güvenli mesafe | kişi ↔ forklift, tır | `safe_distance` | hayır |
| Araç sahası | **araç yolunda yaya** (ek) | kişi · içinde (kalış 1,5 sn) | `person_in_vehicle_lane` | **evet** |
| Yasak bölge | yasak bölge kuralı | kişi · içinde | `restricted_entry` (şema 007) | hayır |
| Yükleme alanı | yükleme alanı kuralı | kişi · içinde | — | hayır |
| Tır park alanı | tır konumlanma | tır · dışında | `vehicle_position` | hayır |
| KKD zorunlu alan | KKD (baret/yelek) | kişi | kullanıcı seçer | hayır |

Ek kurallar **gölge modda** doğar: olay yazılır, hoparlör susar. Sahada yanlış
alarm oranı görülmeden yeni bir kural anons yapmasın diye; operatör Kurallar
sayfasından gölgeyi kapatır. Aynı bölgede aynı kural (tip, yön, hedef) ikinci
kez kurulmaz; birincil ve ek kural yan yana durur. Yaya-araç geçidi ve KKD
muaf alan başka kuralların istisnasıdır, hazır kuralları yoktur.

## Ek — Yaya yolu (yürüyüş yolu) kuralı

Fabrikadaki çizili yürüyüş yolu, `zone_intrusion` kuralının **`mode=outside`**
biçimiyle karşılanır: yaya yolu bölgesinin **dışında** kalan kişi ihlal üretir.
Ayrı bir kural tipi eklenmedi — mevcut tip bu davranışı zaten kapsıyor
(CLAUDE.md §3: en az parça).

Arayüzde tek tıkla kurulur (kamera sayfası → "… için yaya yolu kuralı ekle").
Kurduğu değerler:

| Alan | Değer | Neden |
|---|---|---|
| `rule_type` | `zone_intrusion` | mevcut tip yeter |
| `zone_type` | `pedestrian_path` | başka tipte bölgeye kurulamaz |
| `target_classes` | `["person"]` | yol kuralı yalnızca insan içindir |
| `mode` | `outside` | yolu KULLANMAYAN kişi ihlaldir |
| `min_dwell_s` | 5,0 | yolun kenarına bir adım atan kişi uyarı üretmemeli |
| `cooldown_s` | 180 | aynı kişi için üç dakikada bir uyarı yeter |
| `announcement_id` | `pedestrian_path` | "Lütfen yaya yolunu kullanınız." |

**Karar noktası** diğer bölge kurallarıyla aynıdır: kutunun **alt-orta noktası**
(zemin teması). Bölge, üzerine basılan zemin alanı olarak çizilmelidir.

**Bilinen sınır:** kural, karede görünen HER kişiyi değerlendirir. Kameranın
görüş alanına yol dışında kalan çalışma istasyonları da giriyorsa, o alanlar
sürekli ihlal üretir. Böyle bir sahnede yolu değil, **yasak alanı** çizip
`mode=inside` kullanmak daha doğrudur.

## Ek — Uçtan uca senaryolar (regresyon takımı)

`tests/fixtures/senaryolar/*.json` dosyalarının her biri bir sahneyi ve o sahnede
beklenen olayları anlatır. `tests/test_uctan_uca_olaylar.py` her senaryo için
sentetik bir mp4 yazar ve kareleri gerçek hattan geçirir: takip (ByteTrack),
kural motoru, olay yaşam döngüsü ve süpervizörün olay yazma yolu. Dedektör
yerine senaryoyu okuyan bir sahte kullanılır; model gerekmez. Bulunan olaylar
kod, önem, başlangıç, bitiş ve bitiş sebebiyle ± toleransla karşılaştırılır;
veritabanındaki satırlar da denetlenir.

| Alan | Anlamı |
|---|---|
| `ad`, `aciklama` | Sahne neyi sınıyor; sahadan geldiyse hangi olay, hangi tarih |
| `fps`, `sure_s` | Örnekleme hızı ve sahnenin süresi (bitişten sonra en az `bitis_s` + 0,5 sn pay) |
| `kalibrasyon` | (isteğe bağlı) 3x3 homografi: normalize görüntü → metre |
| `bolgeler` | `id`, `tip` (bölge tipi kodu), `poligon` (normalize) |
| `kurallar` | `id`, `tip`, `bolge_id`, `hedefler`, `params` (şema varsayılanlarıyla tamamlanır), `cooldown_s` |
| `nesneler` | `sinif`, `boy` ve `en` (kareye oranla), `yol`: `[t, x, y]` ayak noktası anahtar kareleri (doğrusal ara değer), `gorunmez`: örtülü aralıklar |
| `beklenen` | `kod`, `onem`, `baslangic_s`, `bitis_s` (sürüyorsa `null`), `sebep`, `tolerans_s` |

**Sahadan gelen yanlış alarm buraya eklenir.** Olay detayındaki kanıt
fotoğrafından ve bölge çiziminden sahne kurulur, beklenen olay listesi (çoğu
zaman boş) yazılır. Önce test kırmızıya döner, düzeltme onu yeşile çevirir; aynı
hata ikinci kez gelmez.

Hangi kamerada yanlış alarm biriktiğini Komuta → Rapor'daki "yanlış alarm /
saat" tablosu gösterir. Oran yalnız incelemesi tam günlerden hesaplanır; önce
İnceleme ekranında işaretleme tamamlanmalıdır (`06-OPERASYON.md` §7).


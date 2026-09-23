# KKD politikası — DALSAN İSG cevapları (etiketleme kılavuzunun eki)

> **Durum: TASLAK — DALSAN İSG ile doldurulacak.** Etiketlemeden **önce**
> kapatılır (docs/04 §5.3, docs/08 R11). Yanlış cevapla etiketlenen veri seti
> baştan bozuktur ve yeniden etiketleme gerektirir.
>
> "Sistem varsayılanı" sütunu, cevap gelene kadar sistemin **bugün** nasıl
> davrandığını yazar (operatör 23.09.2026'da Faz 3 varsayılanlarını kabul etti,
> docs/17 §16 S3). Varsayılan bir cevap değildir; İSG farklı karar verirse satır
> değişir ve "Sistemdeki karşılığı" sütunundaki ayar ona göre yapılır.

## 1. Ön koşul: Rev.02 ek protokolü

| | |
|---|---|
| Rev.02 ek protokolü imza tarihi | ______ |
| İmzalayanlar | ______ |
| Çalışan aydınlatması yapıldı (tarih, yöntem) | ______ |

İmzadan önce KKD sayfasındaki **veri toplama kapısı kapalı** kalır; kapalıyken hiçbir
kişi görüntüsü saklanmaz (docs/04 §4, docs/17 §5.8). Açarken sayfa bu imzanın
yapıldığını ayrıca onaylatır ve açılışı Olaylar'a yazar.

## 2. Kapsam (docs/17 S3)

| Soru | Sistem varsayılanı | İSG cevabı |
|---|---|---|
| KKD hangi alanda aranır? | Yalnız çizilen "KKD zorunlu alan" içinde | ______ |
| Hangi alanlar muaf? | "KKD muaf alan" olarak çizilen poligonlar (kabin, ofis köşesi, giyinme noktası) zorunlu alandan oyulur: orada ne karar verilir ne kırpık toplanır | ______ |
| "Muaf alanlar dışında her yer" (dışlama kipi) isteniyor mu? | Hayır; bu kip yazılmadı (docs/07'de satır) | ______ |
| Politika sorularını kim, ne zaman cevaplayacak? | DALSAN İSG uzmanı + NextGen, etiketlemeden önce | ______ |

## 3. On politika sorusu (docs/04 §5.3)

"Sistemdeki karşılığı" cevabın nereye işlendiğini söyler: etiket kuralı (etiketçinin
seçeceği düğme), bölge çizimi ya da kural ayarı.

| # | Soru | Sistem varsayılanı | Sistemdeki karşılığı | İSG cevabı |
|---|---|---|---|---|
| 1 | Hi-vis **mont** yelek yerine geçer mi? | — (cevap bekleniyor) | Etiket: montlu kişi "Yelek: var" mı "yok" mu. Zor örnek kodu `reflective_jacket` | ______ |
| 2 | Baret elde/kolda taşınıyorsa ihlal mi? | — | Etiket: başta değilse "Baret: yok" mu | ______ |
| 3 | Kep/bere/bone baret sayılır mı? | Hayır (docs/04: "yazılı olmalı") | Etiket "Baret: yok". Zor örnek kodu `white_cap` (beyaz kep, bone, beyaz saç) | ______ |
| 4 | Forklift **kabininde** oturan operatöre baret kuralı uygulanır mı? | Hayır: sürücü muaf | Kural ayarı `surucu_muaf` (açık): araç kutusundaki kişi için gözlem "belirsiz" sayılır. Zor örnek kodu `driver_cab` | ______ |
| 5 | Tır **kabininde** kalan şoför? | Hayır: sürücü muaf | #4 ile aynı ayar | ______ |
| 6 | Ziyaretçi baretine (farklı renk) kural aynı mı? | — | Etiket: renk ne olursa olsun takılı baret "var"; veri toplamada o rengin örneği de alınır | ______ |
| 7 | Baret rengi role göre değişiyor mu? Hepsi geçerli mi? | — | Planlı çekimde her renkten örnek (docs/04 §4.2) | ______ |
| 8 | Ofis personeli KKD bölgesinden geçerken? | Kural herkese aynı | Bölge çizimi: geçiş yolu zorunlu alanın dışında mı | ______ |
| 9 | Yelek zorunluluğu tüm bölgede mi, yalnız araç trafiği olan kısımda mı? | Kuralın seçtiği kalemler bölgenin tamamında | Bölge çizimi: yelek yalnız trafikte ise o kısım için ayrı bölge ve yalnız yelek isteyen ayrı kural | ______ |
| 10 | Vardiya değişiminde KKD giyinme noktası bölge içinde mi? | — | Bölge çizimi: giyinme noktası "KKD muaf alan" | ______ |

## 4. Zor örnekler (etiketçiye)

Aşağıdakiler KKD sayfasında kırpığa **zor örnek** olarak işaretlenir. Veri setinde
ayrı sayılır ve değerlendirme raporunda ayrı kırılım olur (docs/17 §5.8–5.9).

| Kod | Ne |
|---|---|
| `white_cap` | Beyaz saç, şapka, kep, bone — beyaz baretle karışır |
| `reflective_jacket` | Reflektörlü mont — yelekle karışır |
| `night_glare` | Gece yansıması, far, parlama |
| `backpack` | Sırt çantası yeleği örter ya da yelek sanılır |
| `raincoat` | Yağmurluk |
| `driver_cab` | Kabin içindeki sürücü |

**En sık hata:** emin olunamayan kırpığa "yok" demek. Şüphe varsa her zaman
**belirsiz** (docs/04 §5.2).

## 5. Onay

| | Ad soyad | Tarih | İmza |
|---|---|---|---|
| DALSAN İSG | ______ | ______ | ______ |
| NextGen | ______ | ______ | ______ |

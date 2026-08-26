# 00 — Proje Bağlamı

## Taraflar

| | |
|---|---|
| **Geliştirici** | NextGen Yazılım — Mehmet Furkan Salihoğlu |
| **Müşteri** | DALSAN Alçı Sanayi ve Ticaret A.Ş. |
| **Kaynak doküman** | Proje Teklifi Rev. 01, 18 Ağustos 2026 |
| **Bedel** | 150.000 TL + KDV (yazılım ve entegrasyon) |
| **Termin** | Proje başlangıcından 8 hafta |

## Sistemin konumu

Sistem, DALSAN'ın mevcut İSG prosedürlerinin, saha denetimlerinin ve eğitim faaliyetlerinin
**yerine geçmez**. Bunları destekleyen bir **erken uyarı ve izleme katmanıdır**.

Bu cümle pazarlama dili değil, üç somut sonucu olan bir tasarım kararıdır:

1. **Teknik:** Sistem "kesin tespit" taahhüdü vermez. Kaçırılan ihlal bir hata değil,
   sistemin bilinen sınırıdır. Buna karşılık **yanlış alarm** ciddi bir kusurdur —
   çünkü güveni ve dolayısıyla kullanımı bitirir.
2. **Hukuki:** Sistem çıktısı disiplin işlemi veya ceza dayanağı olarak konumlandırılmaz.
3. **İnsani:** Çalışan sistemi "gözetleyen" değil "hatırlatan" olarak algılamalıdır.
   Aksi halde kameradan kaçma, açıyı bozma, sabotaj gibi davranışlar başlar.

## Kapsam sınırı — kamera sayısı revizyonu

Teklif Rev.01'de kamera kapsamı **8-10 kamera** olarak yazılmıştır.
**Güncel karar: MVP'de 3-4 kamera.**

Bu bir kapsam daralması değil, **kapsam takası**dır:

| | Rev.01 | MVP (güncel) |
|---|---|---|
| Kamera | 8-10 | **3-4** |
| Kural tipleri | Bölge ihlali, güvenli mesafe | Bölge ihlali, güvenli mesafe, **+ KKD (baret/yelek)** |
| Bedel | 150.000 TL + KDV | Değişmedi |

Serbest kalan kamera entegrasyon eforu, KKD senaryosunun veri toplama–etiketleme–eğitim
işine aktarılmıştır. Bu takas **yazılı olarak mutabık kalınmalı** (bkz. aşağıda "Rev.02").

## KKD senaryosu — teklif kapsamı ile ilişkisi

Teklif Rev.01, Bölüm 10'da şunu kapsam dışı bırakmıştır:

> "Özel model eğitimi gerektiren yeni senaryolar"

Baret ve yelek tespiti **tam olarak bu tanıma girer.** MVP'ye alınması ticari olarak
sessizce yapılamaz. Yapılması gereken:

**Teklif Rev.02 veya yazılı kapsam ek protokolü** — içeriği:

- Kamera kapsamının 3-4 olarak kesinleştirilmesi
- KKD senaryosunun (baret + yelek) kapsama alınması
- KKD'nin **hangi bölgelerde ve hangi koşullarda** çalışacağının açıkça yazılması
  (bkz. `04-KKD-BARET-YELEK.md` — piksel eşiği ve mesafe sınırı)
- Veri toplama için DALSAN'ın sağlayacağı desteğin yazılması
  (planlı çekim seansı, İSG refakati, çalışan bilgilendirmesi)
- Beklenen performansın **ölçülebilir ve koşullu** ifade edilmesi
  ("sistem KKD tespit eder" DEĞİL — bkz. aşağıdaki başlık)

Ek protokol imzalanmadan KKD veri toplamaya başlanmamalıdır. Sebebi hem ticari
hem de KVKK'dır.

## Performans beklentisinin doğru ifadesi

**Yanlış:** "Sistem baret takmayan çalışanları tespit eder."

**Doğru:** "Tanımlanan KKD bölgelerinde, kameraya olan mesafesi nedeniyle görüntüde
en az X piksel boyunda görünen ve gövdesi engellenmemiş kişiler için, sistem baret/yelek
durumunu değerlendirir ve ihlal şüphesinde uyarı üretir. Değerlendirme yapılamayan
durumlar 'belirsiz' olarak işaretlenir ve uyarı üretmez."

Bu ifade biçimi teslimatta yaşanacak tartışmaların çoğunu baştan keser. Sözleşmeye
bu dille girmelidir.

## KVKK — atlanamaz

Çalışanların görüntüsünün işlenmesi, üstelik **KKD uyumu gibi davranışsal bir çıkarım**
üretilmesi, KVKK kapsamında kişisel veri işlemedir. Sorumluluk dağılımı:

| Rol | Taraf |
|---|---|
| Veri sorumlusu | **DALSAN** |
| Veri işleyen | **NextGen Yazılım** |

Projeye başlamadan önce DALSAN tarafında hazır olması gereken (DALSAN'ın hukuk/KVKK
birimince teyit edilmeli — bu doküman hukuki görüş değildir):

- Çalışan aydınlatma metni (görüntü işleme + KKD analizi ayrıca belirtilerek)
- Kamera izlemesi yapılan alanlarda görünür bilgilendirme levhaları
- İşleme şartının belirlenmesi (İSG yükümlülüğü / meşru menfaat değerlendirmesi)
- VERBİS kaydının kapsamla uyumu
- Saklama sürelerinin politikayla uyumu (sistemde teknik olarak zorlanacak)
- İSG kurulu / çalışan temsilcisi bilgilendirmesi
- NextGen ile veri işleyen sözleşmesi

Sistem tarafındaki teknik karşılıklar (MVP'de uygulanır):

- Snapshot ve olay kayıtları için **zorunlu saklama süresi** ve otomatik silme
- Erişimin şifre ile sınırlanması
- RTSP kimlik bilgilerinin API yanıtlarında maskelenmesi
- Snapshot dizininin dışarıdan doğrudan erişime kapalı olması
- Ham video **kaydedilmez** — yalnızca olay anı görüntüsü saklanır

Phase 2 gizlilik seçeneği: snapshot'larda yüz bulanıklaştırma (bkz. `07-YOL-HARITASI.md`).

## Fabrika geneli hedef

DALSAN'ın orta vadeli hedefi sistemi **tüm fabrika bölümlerine** yaymaktır.
Bu, MVP'de hiçbir ek özellik geliştirilmesini gerektirmez; ancak birkaç mimari kararı
etkiler (kamera gruplama, analizör bölümlendirme, kural şablonları, depolama büyümesi).
Bu kararlar `07-YOL-HARITASI.md` Bölüm 3'te tasarım olarak yazılmıştır — **kod olarak değil.**

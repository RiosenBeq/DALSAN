# vendor/ — depoya KOPYALANMIŞ üçüncü parti dosyalar

Bu klasördeki dosyalar başka projelerden gelir ve **olduğu gibi depoda
durur.** İnternetten (CDN'den) çekilmezler.

## Neden CDN değil

Fabrika sunucusunda internet olmayabilir; olsa bile kurumsal güvenlik duvarı
dış adresleri engelleyebilir. CDN'den çekilen bir yazı tipi ya da simge
dosyası o durumda GELMEZ ve arayüz yarı çizilmiş görünür — üstelik sistemin
kendisi sorunsuz çalışırken. Teslim edilen uygulama (`.exe` / `.app`) da
çift tıklanıp açıldığı anda çalışmalıdır; bir ağ isteğini beklememelidir.

Toplam boyut yaklaşık **140 KB**'dir ve `backend/app/web/static` klasörü
paketleme tarifinde zaten bütün olarak pakete giriyor (paketleme_ortak.py);
bu dosyalar için ayrı bir adım yoktur.

## Dosyalar

| Dosya | Kaynak | Lisans |
|---|---|---|
| `simgeler.svg` | [Lucide](https://lucide.dev) — seçili 46 simgeden üretilmiş sprite, artı Lucide kuralıyla çizilmiş 1 DALSAN simgesi (yelek) | ISC (Lucide) · DALSAN çizimi projenin kendisinindir |
| `inter-latin.woff2` | [Inter](https://rsms.me/inter/) (fontsource, latin altkümesi) | SIL OFL 1.1 |
| `inter-latin-ext.woff2` | Inter (latin-ext altkümesi) | SIL OFL 1.1 |

**İki yazı tipi dosyası da gereklidir.** `latin` altkümesinde Türkçenin
ş, ğ, ı ve İ harfleri YOKTUR; onlar `latin-ext` içindedir. Yalnız biri
konsaydı arayüzdeki her Türkçe kelime yedek yazı tipine düşer ve satırlar
iki farklı yazı tipiyle karışık görünürdü. Hangi harfin hangi dosyadan
geleceğini `stil.css` içindeki `unicode-range` belirler; tarayıcı yalnız
gerekeni indirir.

`simgeler.svg`'deki Lucide simgeleri ELLE DEĞİŞTİRİLMEZ; yeni bir simge
gerekince Lucide deposundan alınır. Yöntem ve "bizim ad, Lucide adı"
listesi dosyanın başındaki yorumdadır. Lucide'de karşılığı olmayan öğeler
(yelek gibi) aynı çizgi kuralıyla çizilir ve dosyanın sonunda ayrı bir
bölümde durur; onlar üçüncü parti kod değildir.

## Lisans metinleri

* Lucide — ISC: <https://github.com/lucide-icons/lucide/blob/main/LICENSE>
* Inter — SIL Open Font License 1.1: <https://github.com/rsms/inter/blob/master/LICENSE.txt>

Her ikisi de ticari kullanıma, değiştirmeye ve yeniden dağıtıma izin verir.
Tek koşul telif bildiriminin korunmasıdır; bu dosya o bildirimdir.
Depo kökündeki `LICENSE-THIRD-PARTY` dosyasında da listelenirler.

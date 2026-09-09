# 15 — Uzaktan Erişim Kılavuzu

Sisteme fabrika dışından (evden, telefondan) girip bir sorunu görebilmek için.

> **Önce en önemli cümle:** Bu sistem **fabrika içindeki insanların
> görüntüsünü** taşır. Uzaktan erişim açmak, o görüntüleri fabrika ağının
> dışına çıkarma kararıdır ve bir **KVKK kararıdır** (`00-PROJE-BAGLAMI.md`,
> risk R13). DALSAN veri sorumlusudur; bu adımı atmadan önce hukuk biriminin
> onayını alın. Bu belge nasıl yapılacağını anlatır, yapılıp yapılmayacağına
> karar vermez.

---

## 1. Üç seviye var — hangisi size lazım?

| Seviye | Nereden erişilir | Kurulum | Risk |
|---|---|---|---|
| **A · Yalnız sunucu** *(bugünkü hâli)* | Sistemin kurulu olduğu bilgisayardan | Yok | Yok |
| **B · Fabrika ağı** | Fabrikadaki her bilgisayar/telefon | Tek satır ayar | Düşük — şifre şart |
| **C · Fabrika dışı** | Evden, telefondan, her yerden | §4'teki yollardan biri | **Yüksek** — doğru yapılmazsa |

Çoğu "bir sorun olduğunda müdahale" ihtiyacı için **B yeterlidir**: fabrikada
olduğunuz sürece telefondan bakabilirsiniz. Gerçekten fabrika dışından
gerekiyorsa C'ye geçin.

---

## 2. Seviye B — fabrika ağına açma

İki satır, ikisi de `.env` dosyasında (ya da **Komuta → Ayarlar**):

```
YONETICI_SIFRESI=buraya-guclu-bir-sifre
SUNUCU_ADRESI=0.0.0.0
```

Sistemi yeniden başlatın. Artık fabrikadaki başka bir bilgisayardan
`http://<sunucunun-ip-adresi>:8080` ile açılır.

> **Sistem sizi korur:** `SUNUCU_ADRESI` yerel olmayan bir değere ayarlanmış
> ama şifre boşsa **sistem açılmayı reddeder** ve sebebini yazar. Ağa açık +
> şifresiz bir kurulum kazayla oluşamaz.

Sunucunun IP adresini öğrenmek için (sunucuda):

```bash
hostname -I          # Linux
ipconfig             # Windows
ipconfig getifaddr en0   # Mac
```

**Docker kullanıyorsanız** ayrıca `docker-compose.yml` içindeki port satırını
`"8080:8080"` yapın (bugün `127.0.0.1:8080:8080` yazıyor).

---

## 3. Şifreyi seçerken

- **En az 12 karakter** kullanın. Sistem 6'nın altını reddeder ama 6 karakter
  ağa açık bir sistem için az.
- Fabrika adı, marka adı, `123456`, doğum tarihi **kullanmayın**.
- Şifreyi WhatsApp/e-posta ile paylaşmayın; sunucunun başında yazdırın.

Sistem, aynı adresten **arka arkaya 5 yanlış denemeden sonra o adresi 5 dakika
kilitler**. Kilitliyken doğru şifre bile kabul edilmez. Bu, saniyede yüzlerce
şifre deneyen bir betiği fiilen durdurur. Kilit adres bazlıdır: birinin yanlış
yazması başkasını engellemez.

---

## 4. Seviye C — fabrika dışından erişim

Üç yol var. **Sıralama tavsiye sırasıdır.**

### 4.1 En iyi yol: VPN veya Tailscale *(önerilen)*

Sistem internete **hiç açılmaz**. Siz fabrika ağının içine girersiniz; sistem
açısından fabrikadaymışsınız gibi olur.

**Şirketin VPN'i varsa:** DALSAN BT'ye "bu sunucuya VPN üzerinden erişmem
gerekiyor" deyin. Yazılım tarafında **yapılacak hiçbir şey yok** — Seviye B
ayarları yeterli.

**VPN yoksa Tailscale** (ya da benzeri) en pratik yoldur:

- Sunucuya ve telefonunuza/bilgisayarınıza kurulur, ikisi de aynı hesaba
  bağlanır.
- **Router ayarı, port açma, sabit IP gerekmez.** Kurumsal güvenlik
  duvarlarında en çok takılan adımlar bunlardır; Tailscale ikisini de atlar.
- Bağlantı uçtan uca şifrelidir.
- Kurulumdan sonra sunucunun size özel bir adresi olur; tarayıcıya onu
  yazarsınız.

> Bu, sisteme eklenen bir parça **değildir**: işletim sistemi düzeyinde çalışan
> ayrı bir programdır, DALSAN İSG yazılımı onu hiç bilmez. Öğrenmeniz gereken
> yeni bir ekran çıkmaz.

**Bu yolu seçerseniz `SUNUCU_ADRESI=0.0.0.0` yapın ve şifreyi koyun** (Seviye B),
gerisi VPN'in işidir.

### 4.2 İkinci yol: Cloudflare Tunnel benzeri bir tünel

Sunucudan **dışarı doğru** bir bağlantı kurulur; siz bir web adresinden
girersiniz. Router'da port açmak gerekmez ve bağlantı HTTPS olur.

Artıları: HTTPS hazır gelir, port açılmaz.
Eksileri: görüntüleriniz bir üçüncü taraf hizmetin üzerinden geçer — **KVKK
açısından ayrıca değerlendirilmelidir** (yurt dışına veri aktarımı sorusu).

### 4.3 Son çare: router'da port açma — **önerilmez**

Router'a "8080 portuna gelen istekleri sunucuya yönlendir" dedirtmek en kolay
görünen yoldur ve **en tehlikelisidir**:

- Sistem **düz HTTP** konuşur. Araya giren biri şifrenizi ve görüntüleri
  okuyabilir. HTTPS'siz bir şifre, uzak bağlantıda neredeyse şifresizdir.
- İnternete açık her adres, gün içinde otomatik tarayıcılar tarafından
  bulunur ve denenir.
- Fabrika kamerası görüntüsünün internete açık bir adreste durması ciddi bir
  KVKK sorumluluğudur.

Yine de zorundaysanız, **en azından** şunlar yapılmalıdır:

1. Önüne HTTPS yapan bir ters vekil (nginx/Caddy) koyun — sertifika ücretsizdir.
2. Varsayılan 8080 portunu kullanmayın.
3. Şifre en az 16 karakter olsun.
4. Router'da mümkünse **kaynak IP kısıtı** koyun (yalnız sizin ev IP'niz).
5. `veri/loglar/sistem.log` dosyasını düzenli okuyun: yanlış şifre denemeleri
   oraya "Yanlış şifre denemesi (adres)" satırı olarak düşer.

> Sistem ters vekil arkasında çalıştığını anlar: `X-Forwarded-Proto: https`
> gelirse oturum çerezini **yalnız HTTPS'te gönderilecek** biçimde işaretler,
> `X-Forwarded-For` başlığından da gerçek istemci adresini okuyup kilidi ona
> uygular.

---

## 5. Uzaktan bağlandığınızda ne yapabilirsiniz?

Arayüzün tamamı çalışır. Bir sorun anında bakılacak yerler:

| Soru | Nereye bakılır |
|---|---|
| Sistem ayakta mı? | `http://.../saglik` — tek satır cevap verir |
| Hangi kamera düşmüş? | **Komuta → Kamera sağlığı** |
| Ne zamandır düşük? | Aynı sayfada "ölçülen fps" ve son kare zamanı |
| Uyarılar geliyor mu? | **Komuta → Komuta ekranı** (bugünkü sayılar) |
| Hoparlör çalıştı mı? | **Komuta → Anons sistemi** — son anons sonucu yazar |
| Sistem ne diyor? | **Ana sayfa → Sistem günlüğü** ve `veri/loglar/sistem.log` |

**Uzaktan yapılamayan tek şey:** sistemi durdurup başlatmak ve yedekten geri
yükleme. Bunlar Kontrol Paneli'nde, sunucunun başındadır — bilerek. Uzaktan
"Durdur" düğmesi, yanlış tıklamayla fabrikayı izlemesiz bırakabilirdi.

Sunucuyu uzaktan yeniden başlatmanız gerekiyorsa BT'den sunucuya uzak masaüstü
/ SSH erişimi isteyin; bu, yazılımın değil işletim sisteminin işidir.

---

## 6. Kurulum sonrası kontrol listesi

- [ ] `YONETICI_SIFRESI` dolduruldu, en az 12 karakter
- [ ] Şifre bir yerde güvenli biçimde saklandı (yalnız yetkili kişide)
- [ ] `SUNUCU_ADRESI=0.0.0.0` yapıldı ve sistem yeniden başlatıldı
- [ ] Docker kullanılıyorsa port satırı `"8080:8080"` yapıldı
- [ ] Başka bir cihazdan giriş **denendi** ve şifre soruldu
- [ ] Yanlış şifreyle 5 kez denendi ve **kilit çalıştı**
- [ ] Fabrika dışı erişim için VPN/Tailscale seçildi (port açılmadı)
- [ ] KVKK açısından hukuk birimi bilgilendirildi (R13)
- [ ] Aydınlatma metni ve levhalar uzaktan erişimi de kapsıyor

---

## 7. Neler bilerek YAPILMADI

| Beklenebilecek özellik | Neden yok |
|---|---|
| Sistemin kendi HTTPS'i | Sertifika üretimi, yenilemesi ve saklanması sisteme üç yeni parça ekler. Bu işi ters vekiller (nginx/Caddy) zaten olgun biçimde yapıyor; VPN yolunda ise hiç gerekmiyor. |
| Uygulamanın içine gömülü VPN/tünel | İşletim sistemi düzeyinde bir iştir; sisteme gömmek onu bir ağ ürününe çevirirdi. Kullanıcının öğrenmesi gereken parça sayısı artmadan, dışarıdan çözülüyor. |
| Uzaktan "Durdur / Başlat" düğmesi | Yanlış bir tıklama fabrikayı izlemesiz bırakır. Bu iki düğme bilerek sunucunun başında (Kontrol Paneli'nde) kalıyor. |
| Kullanıcı hesapları ve roller | Bugün tek yönetici şifresi var. Birden çok kişi kendi hesabıyla girmeye başladığında gerekir — `07-YOL-HARITASI.md` #5. |
| İki adımlı doğrulama (SMS/uygulama) | Tek kullanıcılı bir sistemde VPN'in verdiği korumayı tekrar etmiş olurdu. Kullanıcı sayısı artarsa yol haritası #5 ile birlikte değerlendirilir. |

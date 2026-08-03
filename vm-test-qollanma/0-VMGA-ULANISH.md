# 0-QISM — VM'ga birinchi marta ulanish

Bu — boshqa qo'llanmalar (`1-LOYIHANI-ISHGA-TUSHIRISH.md`, `2-SQUIDGA-ULASH-RSYSLOG.md`)
boshlanishidan **oldingi** qadam: VM'ga qanday ulanish. Boshqa qo'llanmalarning barchasi
"VM'ga SSH orqali kirdingiz" degan joydan boshlanadi — mana shu qism aynan o'sha "kirish"
jarayonini tushuntiradi.

---

## 1. Sizga nima berilishi kerak

VM tayyor bo'lganda, sizga (odatda email yoki xabar orqali) quyidagi **3 narsa** berilishi
kerak — agar berilmagan bo'lsa, aynan shularni so'rang:

| # | Nima | Masalan |
|---|---|---|
| 1 | IP manzil | `95.123.45.67` |
| 2 | Foydalanuvchi nomi | `root` yoki `ubuntu` |
| 3 | Kirish usuli | Parol (matn) **yoki** SSH kalit fayli (`.pem`) |

---

## 2. Ulanish — o'z kompyuteringizda

Bu barcha buyruqlar **VM'da emas, sizning shaxsiy kompyuteringizda** bajariladi.

> **Nega `-L 8080:localhost:8080 -L 8000:localhost:8000` qo'shilgan**: keyingi
> qo'llanmalarda dashboard va uning health-check'i shu ikki portda ishga tushadi
> (`8080` — veb-interfeys, `8000` — backend). Bu flag'lar VM'dagi shu portlarni
> kompyuteringizdagi xuddi shu portlarga **shifrlangan SSH tunnel** orqali "ko'chirib"
> beradi — shu tufayli brauzeringizda `http://VM_IP:8080` o'rniga `http://localhost:8080`
> yozib, dashboard'ga **firewall'da hech qanday port ochmasdan, trafikni tarmoqqa ochiq
> qoldirmasdan** kirasiz. Bu shunchaki qulaylik emas — dashboard login parolini va sessiya
> tokenini ochiq (shifrlanmagan) tarmoq orqali yubormaslik uchun muhim. Keyingi
> qo'llanmalarning barchasi shu tunnel o'rnatilgan deb hisoblab yoziladi.

### Windows (PowerShell)

1. Windows tugmasini bosing, `terminal` deb yozing, "Terminal" dasturini oching (yoki
   "PowerShell").
2. **1-jadvaldagi haqiqiy qiymatlaringizni** shu ikki qatorga yozib, terminalga
   nusxalab, Enter bosing (`root`/IP — shunchaki misol, o'zingiznikini yozing):

```powershell
$FOYDALANUVCHI_NOMI = "root"
$IP_MANZIL = "95.123.45.67"
```

3. Endi shu buyruqni **o'zgartirmasdan, aynan shunday** nusxalab bajaring — u yuqorida
   kiritgan qiymatlaringizni o'zi ishlatadi:

```powershell
ssh -L 8080:localhost:8080 -L 8000:localhost:8000 "$FOYDALANUVCHI_NOMI@$IP_MANZIL"
```

> Windows 10/11'da SSH allaqachon o'rnatilgan — alohida dastur (PuTTY va h.k.) o'rnatish
> shart emas.

### Mac yoki Linux (yoki Windows'da Git Bash / WSL)

1. "Terminal" dasturini oching (Mac: Spotlight orqali `terminal` deb qidiring; Linux:
   odatda `Ctrl+Alt+T`).
2. **1-jadvaldagi haqiqiy qiymatlaringizni** shu ikki qatorga yozib, terminalga
   nusxalab, Enter bosing (`root`/IP — shunchaki misol, o'zingiznikini yozing):

```bash
FOYDALANUVCHI_NOMI="root"
IP_MANZIL="95.123.45.67"
```

3. Endi shu buyruqni **o'zgartirmasdan, aynan shunday** nusxalab bajaring — u yuqorida
   kiritgan qiymatlaringizni o'zi ishlatadi:

```bash
ssh -L 8080:localhost:8080 -L 8000:localhost:8000 $FOYDALANUVCHI_NOMI@$IP_MANZIL
```

> **Muhim eslatma**: `$FOYDALANUVCHI_NOMI` va `$IP_MANZIL` faqat **shu terminal oynasi
> ochiq turgan paytda** eslab qoladi. Terminalni yopsangiz, yangi oynada ishlasangiz yoki
> ertaga qaytib kelsangiz — 2-qadamni (qiymatlarni kiritishni) qayta bajarishingiz kerak
> bo'ladi, shundan keyin 3-qadamdagi buyruq yana o'zgarishsiz ishlayveradi.

### Agar `.pem` kalit fayli bilan kirsangiz

Yuqoridagi 2-qadamda `$FOYDALANUVCHI_NOMI`/`$IP_MANZIL`ni kiritib bo'lgan holda davom
eting. Kalit faylini kompyuteringizga saqlab (masalan `~/Downloads/mening-kalitim.pem`),
so'ng:

```bash
chmod 400 ~/Downloads/mening-kalitim.pem
ssh -i ~/Downloads/mening-kalitim.pem -L 8080:localhost:8080 -L 8000:localhost:8000 \
  $FOYDALANUVCHI_NOMI@$IP_MANZIL
```

(`chmod 400` — bu fayl ruxsatini "faqat siz o'qiy olasiz" qilib qo'yadi, SSH buni talab
qiladi, aks holda xato beradi.)

> Tunnel faqat shu SSH sessiyasi ochiq turgan paytda ishlaydi — terminalni yopsangiz yoki
> `exit` qilsangiz, brauzerdagi `localhost:8080` ham ishlashni to'xtatadi. Ish davomida shu
> terminalni ochiq qoldiring (yoki alohida oynada faqat tunnel uchun: yuqoridagi buyruqqa
> `-N` qo'shib, oxiridan buyruq satri o'rniga fon jarayoni sifatida ishlatish mumkin).

---

## 3. Birinchi marta ulanayotganda

Ekranda shunga o'xshash savol chiqadi:
```
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```
Bu — **xato emas**, oddiy tasdiqlash so'rovi. **`yes`** deb yozib, Enter bosing.

Agar parol so'ralsa — yozganingizda ekranda **hech narsa ko'rinmaydi** (nuqta ham,
yulduzcha ham) — bu normal, Windows/Mac/Linux barchasida shunday, xatolik emas. Parolni
yozib, Enter bosing.

Muvaffaqiyatli kirgach, terminal ko'rinishi o'zgaradi — odatda shunga o'xshash bo'ladi:
```
root@server-nomi:~#
```
Shu yozuvni ko'rsangiz — siz endi VM ichidasiz.

---

## 4. Tekshirish — to'g'ri VM'ga kirdingizmi

Ulangandan keyin shu buyruqni yozing:
```bash
whoami && hostname && lsb_release -d
```
Bu sizning foydalanuvchi nomingizni, server nomini va Ubuntu versiyasini ko'rsatadi —
hammasi kutganingizga mos kelsa, tayyor.

---

## 5. Uzulish (chiqish)

Ish tugagach, VM'dan chiqish uchun:
```bash
exit
```

Keyingi safar qayta kirish uchun: agar **shu terminal oynasi** hali ochiq bo'lsa, faqat
3-qadamdagi (`ssh -L ...`) buyruqni takrorlaysiz — `$FOYDALANUVCHI_NOMI`/`$IP_MANZIL` hali
eslab turadi. Agar **yangi** terminal oynasi bo'lsa, 2-qadamdan (qiymatlarni kiritishdan)
qaytadan boshlaysiz.

---

## Muammo jadvali

| Xato | Sababi | Yechimi |
|---|---|---|
| `Connection refused` | Server hali to'liq tayyor emas, yoki IP xato | 1-2 daqiqa kutib qayta urinib ko'ring; IP'ni qayta tekshiring |
| `Connection timed out` | Firewall `22`-portni yopib qo'ygan, yoki IP xato | VM beruvchidan `22`-port ochiqligini so'rang |
| `Permission denied (publickey,password)` | Foydalanuvchi nomi yoki parol xato | Ikkalasini ham katta-kichik harflarga e'tibor berib qayta tekshiring |
| `Host key verification failed` | Bu IP avval **boshqa** serverga tegishli bo'lgan | Xato matnida ko'rsatilgan `ssh-keygen -R IP_MANZIL` buyrug'ini ishlatib, qayta urinib ko'ring |
| `UNPROTECTED PRIVATE KEY FILE` | `.pem` fayl ruxsati noto'g'ri | `chmod 400 ~/Downloads/mening-kalitim.pem` buyrug'ini ishlating |
| `command not found: ssh` (faqat Windows'da, kam uchraydi) | Juda eski Windows versiyasi | "PowerShell" o'rniga "Command Prompt" sinab ko'ring, yoki Windows'ni yangilang |

Boshqa xato chiqsa — **xato matnini to'liq nusxalab yuboring**, birga hal qilamiz.

---

Ulanib bo'lgach, keyingi qadam: **`1-LOYIHANI-ISHGA-TUSHIRISH.md`** (dashboard'ni demo
rejimda ishga tushirish), so'ng **`2-SQUIDGA-ULASH-RSYSLOG.md`** (Squid boshqa serverda —
uning haqiqiy trafigini rsyslog orqali TLS ustida shu dashboard'ga ulash).

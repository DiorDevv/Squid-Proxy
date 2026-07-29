# 0-QISM — VM'ga birinchi marta ulanish

Bu — boshqa qo'llanmalar (`QOLLANMA.md`, `RSYSLOG-QOLLANMA.md`, `SSH-TAIL-QOLLANMA.md`)
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

### Windows

1. Windows tugmasini bosing, `terminal` deb yozing, "Terminal" dasturini oching (yoki
   "PowerShell").
2. Quyidagi buyruqni yozing (o'z ma'lumotlaringiz bilan almashtirib):

```bash
ssh FOYDALANUVCHI_NOMI@IP_MANZIL
```

Masalan:
```bash
ssh root@95.123.45.67
```

> Windows 10/11'da SSH allaqachon o'rnatilgan — alohida dastur (PuTTY va h.k.) o'rnatish
> shart emas.

### Mac yoki Linux

1. "Terminal" dasturini oching (Mac: Spotlight orqali `terminal` deb qidiring; Linux:
   odatda `Ctrl+Alt+T`).
2. Xuddi shu buyruq:

```bash
ssh FOYDALANUVCHI_NOMI@IP_MANZIL
```

### Agar `.pem` kalit fayli bilan kirsangiz

Kalit faylini kompyuteringizga saqlab (masalan `~/Downloads/mening-kalitim.pem`), so'ng:

```bash
chmod 400 ~/Downloads/mening-kalitim.pem
ssh -i ~/Downloads/mening-kalitim.pem FOYDALANUVCHI_NOMI@IP_MANZIL
```

(`chmod 400` — bu fayl ruxsatini "faqat siz o'qiy olasiz" qilib qo'yadi, SSH buni talab
qiladi, aks holda xato beradi.)

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

Keyingi safar qayta kirish uchun xuddi shu `ssh FOYDALANUVCHI_NOMI@IP_MANZIL` buyrug'ini
takrorlaysiz.

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

Ulanib bo'lgach, keyingi qadam uchun quyidagilardan birini tanlang:
- **`QOLLANMA.md`** — agar Squid va dashboard bitta serverda bo'lsa
- **`RSYSLOG-QOLLANMA.md`** — agar Squid boshqa serverda, rsyslog orqali
- **`SSH-TAIL-QOLLANMA.md`** — agar Squid boshqa serverda, sodda SSH usuli orqali

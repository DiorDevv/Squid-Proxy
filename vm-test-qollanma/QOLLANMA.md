# Squid Watch — Serverda test qilish qo'llanmasi

Bu fayl loyihani jismoniy serverga (VM'ga) yuklab, avval demo rejimda, keyin real Squid
bilan test qilish uchun bosqichma-bosqich qadamlarni o'z ichiga oladi.

Ikki bosqich bor:
- **1-BOSQICH** — Demo test (sun'iy trafik bilan, tez tekshirish uchun)
- **2-BOSQICH** — Real test (haqiqiy Squid proxy bilan)

Avval 1-bosqichni to'liq tugatib, hammasi ishlayotganiga ishonch hosil qilamiz, keyin 2-bosqichga o'tamiz.

---

## 0. Kerakli ma'lumotlar (oldindan tayyorlab qo'ying)

- [ ] Server IP manzili: `_______________`
- [ ] Foydalanuvchi nomi (masalan `root` yoki `ubuntu`): `_______________`
- [ ] Parol yoki SSH kalit fayli: `_______________`

---

## 1-BOSQICH: Demo test (Squid'siz, tez tekshirish)

### 1.1 Serverga ulanish

Terminalda (o'z kompyuteringizda):

```bash
ssh FOYDALANUVCHI@SERVER_IP
```

Masalan: `ssh root@192.168.1.50`

Birinchi marta ulanayotganda "Are you sure you want to continue connecting?" deb so'rasa —
`yes` deb yozing. Keyin parol so'raladi.

### 1.2 Serverda Docker bor-yo'qligini tekshirish

Serverga ulangandan keyin, o'sha yerda (server ichida) quyidagini yozing:

```bash
docker --version
docker compose version
```

Agar ikkalasi ham versiya raqamini ko'rsatsa — Docker tayyor, 1.4-qadamga o'ting.

Agar "command not found" desa — Docker o'rnatish kerak:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Shundan keyin serverdan chiqib (`exit`), qayta kiring (`ssh ...`) — bu Docker huquqlarini
yangilash uchun kerak.

### 1.3 Loyihani serverga ko'chirish

Ikki variant bor — birini tanlang.

#### A-variant: `git clone` orqali (tavsiya etiladi, agar loyiha GitHub'da bo'lsa)

Serverda (SSH orqali ulangan holda):

```bash
sudo apt install -y git   # agar git o'rnatilmagan bo'lsa
git clone https://github.com/DiorDevv/Squid-Proxy.git ~/squid-watch
cd ~/squid-watch
```

> **Muhim:** `.env` fayl git'ga **hech qachon yuklanmaydi** (u `.gitignore`da, chunki
> ichida parollar bor). `git clone` qilgandan keyin `.env` fayl serverda bo'lmaydi —
> uni alohida ko'chirish kerak (pastga qarang, "1.3.1 — .env faylni ko'chirish").

#### B-variant: `rsync` orqali (agar loyiha git'ga bog'liq bo'lmasin desangiz)

**O'z kompyuteringizda** (yangi terminal oynasida, serverga ulanmagan holda), loyiha
papkasidan turib:

```bash
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='frontend/dist' \
  "/home/dior/OpenCOde Loyihalar/Squid Proxy/" FOYDALANUVCHI@SERVER_IP:~/squid-watch/
```

Bu variant `.env` faylni ham birga ko'chiradi (chunki `--exclude` faqat `.git`,
`node_modules`, `dist` uchun), shuning uchun B-variantda 1.3.1-qadamni o'tkazib
yuborishingiz mumkin.

Internet/tarmoq tezligiga qarab bir necha daqiqa vaqt olishi mumkin.

#### 1.3.1 — `.env` faylni ko'chirish (faqat A-variant — git clone — tanlagan bo'lsangiz kerak)

**O'z kompyuteringizda**, alohida terminalda:

```bash
scp "/home/dior/OpenCOde Loyihalar/Squid Proxy/.env" FOYDALANUVCHI@SERVER_IP:~/squid-watch/.env
```

Bu tayyor (kuchli parollar bilan to'ldirilgan) `.env` faylni to'g'ridan-to'g'ri serverga
yuboradi. Bu fayl git orqali emas, faqat shu xavfsiz kanal (SSH/scp) orqali uzatiladi.

### 1.4 Konteynerlarni ishga tushirish

Serverga qaytib ulaning (`ssh FOYDALANUVCHI@SERVER_IP`), keyin:

```bash
cd ~/squid-watch
docker compose --profile demo up --build -d
```

- `--profile demo` — sun'iy (test) trafik generatorini ham qo'shib ishga tushiradi
- `-d` — orqa fonda (background) ishlaydi, terminalni band qilmaydi

Birinchi marta ishga tushirish bir necha daqiqa vaqt olishi mumkin (image'lar
qurilayotgani uchun).

### 1.5 Ishlayotganini tekshirish

```bash
docker compose ps
```

Barcha xizmatlar (`postgres`, `backend`, `frontend`, `demo-log-generator`) `running`/`healthy`
holatida bo'lishi kerak.

Keyin backend sog'lig'ini tekshiring:

```bash
curl http://localhost:8001/api/health
```

(Port raqami `.env` faylidagi `BACKEND_PORT` ga mos — hozircha `8001`)

### 1.6 Brauzerda ochish

O'z kompyuteringizning brauzerida oching:

```
http://SERVER_IP:8082
```

(`.env` dagi `FRONTEND_PORT=8082`)

Login qilish uchun `.env` faylidagi:
- Email: `admin@example.com`
- Parol: `TestPass12345`

Bir necha soniyadan keyin dashboardda sun'iy trafik (demo generator) ko'rina boshlashi kerak.

> Agar server firewall bilan himoyalangan bo'lsa (masalan `ufw`), 8082-portni ochish kerak
> bo'lishi mumkin: `sudo ufw allow 8082`

### 1.7 To'xtatish (kerak bo'lganda)

```bash
docker compose --profile demo down
```

---

## 2-BOSQICH: Real test (haqiqiy Squid proxy bilan)

1-bosqich muvaffaqiyatli o'tgandan keyingina bu bosqichga o'ting.

### 2.1 Demo rejimni to'xtatish

```bash
cd ~/squid-watch
docker compose --profile demo down
```

### 2.2 Squid proxy'ni o'rnatish

Serverda:

```bash
sudo apt update
sudo apt install -y squid
```

### 2.3 Squid log formatini sozlash (ENG MUHIM QADAM)

```bash
sudo nano /etc/squid/squid.conf
```

Faylda `access_log` qatorini toping va shunday qiling (agar yo'q bo'lsa, oxiriga qo'shing):

```
access_log /var/log/squid/access.log squid
```

> **Diqqat:** oxiridagi `squid` so'zi shart — bu native Squid log formati. Agar
> `common`/`combined` yoki boshqa nom yozilgan bo'lsa, dashboard "ulangan" ko'rinadi lekin
> hech qanday trafik ko'rsatmaydi va xato ham bermaydi. Aynan shu format kerak.

Saqlash: `Ctrl+O`, `Enter`, `Ctrl+X`.

### 2.4 Squid'ni qayta ishga tushirish

```bash
sudo systemctl restart squid
sudo systemctl status squid
```

`active (running)` ko'rinishi kerak.

### 2.5 docker-compose.yml'da real log papkasini ulash

`~/squid-watch/docker-compose.yml` faylida `backend` xizmati ichidagi `volumes` bo'limiga
real Squid log papkasini qo'shamiz (buni men sizga qadamda o'zim tahrirlab beraman —
shunchaki ayting).

Natijada backend konteyneri `squid_log_data` o'rniga to'g'ridan-to'g'ri
`/var/log/squid/access.log` faylini o'qiy boshlaydi.

### 2.6 Qayta ishga tushirish (demo profilisiz)

```bash
docker compose up --build -d
```

### 2.7 Haqiqiy trafik yaratish

Squid haqiqiy proxy sifatida ishlashi uchun, biror qurilma/brauzerni shu serverning
IP:3128 manziliga proxy qilib sozlang, so'ng bir nechta saytga kiring — bular Squid orqali
o'tib, `access.log`ga yoziladi.

### 2.8 Tekshirish

```bash
curl http://localhost:8001/api/health
```

Javobda `log_parse_failure_rate` `0` ga yaqin bo'lishi kerak (masalan `0.0`). Agar `1.0`
bo'lsa — demak 2.3-qadamdagi log format noto'g'ri sozlangan, qaytadan tekshiring.

Brauzerda `http://SERVER_IP:8082` ochib, endi **haqiqiy** trafik ko'rinishini tekshiring.

---

## 3-BOSQICH: Sig'imni (capacity) haqiqiy trafikka moslash

2-bosqich bir necha kun (kamida 3-5 kun, real trafik bilan) ishlab turgandan keyin,
default sozlamalar sizning trafik hajmingiz uchun yetarlimi — buni **taxmin qilish emas,
kuzatib bilish** kerak.

### 3.1 Xotira (ring buffer) yetarli-yetarli emasligini tekshirish

```bash
curl http://localhost:8001/api/health
```

Javobdagi ikkita maydonga qarang:
- `aggregator_backlog_ratio` — `1.0`ga yaqinlashsa, demak tizim ortda qolyapti
- `aggregator_events_likely_lost` — agar `true` bo'lsa, demak `RING_BUFFER_MAX_EVENTS`
  (`.env`dagi standart qiymat: `500000`) real trafik uchun yetarli emas, ba'zi hodisalar
  yo'qolayotgan bo'lishi mumkin — buni oshirish kerak.

Agar ikkalasi ham past/`false` bo'lsa — demak hozirgi sozlama yetarli, hech narsani
o'zgartirish shart emas.

### 3.2 Disk sig'imini tekshirish (baza qancha tez o'sayotgani)

```bash
docker exec -it $(docker compose ps -q postgres) \
  psql -U squid -d squid_dashboard -c "SELECT pg_size_pretty(pg_database_size('squid_dashboard'));"
```

Buni bir necha kun ketma-ket ishga tushirib, kunlik o'sish tezligini hisoblang. So'ng:

```
kerakli disk = kunlik o'sish × RETENTION_DAYS_RAW_EVENTS (.env, standart: 7)
```

Agar bu son serverdagi bo'sh diskdan katta bo'lsa — `RETENTION_DAYS_RAW_EVENTS`ni
kamaytiring (eski xom ma'lumot avtomatik arxivlanadi, yo'qolib ketmaydi — README'dagi
"Archiving" bo'limiga qarang).

### 3.3 RAM sarfini tekshirish

```bash
docker stats --no-stream
```

`backend` konteynerining real xotira sarfini ko'ring. Agar server RAM'i cheklangan va
3.1-qadamda `aggregator_events_likely_lost: false` bo'lsa, `RING_BUFFER_MAX_EVENTS`ni
xavfsiz kamaytirish mumkin (ma'lumot yo'qolmaydi — baza barcha holatda asosiy manba).

### 3.4 Sozlamalarni o'zgartirish

```bash
nano .env
# masalan: RING_BUFFER_MAX_EVENTS=1000000
#          RETENTION_DAYS_RAW_EVENTS=14
docker compose up -d
```

`.env`dagi bu qiymatlar `docker-compose.yml` orqali backend'ga avtomatik uzatiladi —
konteynerni qayta ishga tushirish (`up -d`) yetarli, qayta build shart emas.

---

## Kelajakda kodni yangilash (agar A-variant — git clone — ishlatgan bo'lsangiz)

Loyihaga o'z kompyuteringizda o'zgartirish kiritib, git'ga push qilganingizdan keyin,
serverda yangilanishni olish uchun:

```bash
cd ~/squid-watch
git pull
docker compose up --build -d
```

`.env` fayl git orqali kelmagani uchun, u serverda o'zgarishsiz qoladi — qayta ko'chirish
shart emas.

---

## Muammo yuzaga kelsa

- `docker compose logs -f backend` — backend loglarini jonli ko'rish
- `docker compose logs -f` — barcha xizmatlar loglari
- `docker compose ps` — qaysi xizmat ishlamayotganini ko'rish

Har qanday xato chiqsa, chiqqan xabarni to'liq nusxalab yuboring — birga hal qilamiz.

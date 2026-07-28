# Squid Watch — Serverda test qilish qo'llanmasi

Bu fayl loyihani jismoniy serverga (VM'ga) yuklab, avval demo rejimda, keyin real Squid
bilan (sizning holingizda — **4 ta Squid**: filiallar, bosh ofis, umumiy serverlar va yana
bittasi, hammasi bitta serverda) test qilish uchun bosqichma-bosqich qadamlarni o'z ichiga
oladi.

To'rtta bosqich bor:
- **0-BOSQICH** — VM talablari (buni tayyorlovchiga bering)
- **1-BOSQICH** — Demo test (sun'iy trafik bilan, tez tekshirish uchun)
- **2-BOSQICH** — Real test (4 ta haqiqiy Squid bilan, `LOG_SOURCES`)
- **3-BOSQICH** — Sig'imni (capacity) haqiqiy trafikka moslash

Avval 1-bosqichni to'liq tugatib, hammasi ishlayotganiga ishonch hosil qilamiz, keyin
2-bosqichga o'tamiz.

---

## 0-BOSQICH: VM talablari

VM tayyorlanayotganda quyidagi xususiyatlarni so'rang. Bu bitta serverda **4 ta Squid
jarayoni + Postgres + backend + frontend** birga ishlashini hisobga oladi.

| Resurs | Minimal | Tavsiya etiladi | Nega |
|---|---|---|---|
| vCPU | 4 | 8 | 4 ta Squid jarayoni (real proxy trafigi CPU talab qiladi) + Postgres + Python backend + nginx bitta mashinada resurs bo'lishadi |
| RAM | 8 GB | 16 GB | Postgres bufer keshi + backend'ning xotiradagi "ring buffer"i (standart 500,000 hodisa, 4 manbadan yig'ilgani uchun tezroq to'ladi) + 4 Squid jarayonining o'z xotirasi |
| Disk | 100 GB SSD | 200 GB SSD | Postgres bazasi (xom hodisalar 7 kun, agregatlar ~400 kun saqlanadi) + 4 Squid'ning o'z keshi + backup/arxiv fayllari |
| OS | Ubuntu 22.04/24.04 LTS | — | Docker rasmiy qo'llab-quvvatlaydi, qo'llanma shu asosda yozilgan |
| Tarmoq | Statik IP | — | Squid'larga proxy sifatida ulanadigan qurilmalar barqaror manzilga muhtoj |

**Bu boshlang'ich taxmin — aniq raqam sizning real trafik hajmingizga bog'liq.** Aniq
sig'imni taxmin qilib emas, **kuzatib** bilish kerak — buning uchun aynan shuning uchun
quyida **3-BOSQICH** bor: VM ishga tushib, bir necha kun real trafik bilan ishlagandan
keyin, RAM/disk yetarli-emasligini o'lchab, kerak bo'lsa sozlamalarni moslaymiz. Shuning
uchun "tavsiya etiladi" ustunidan boshlab, kam bo'lib qolsa keyin osongina kattalashtirish
mumkin bo'lgan turdagi VM (masalan bulutli provayderning "resizable" turi) tanlashni
maslahat beraman.

**Ochiq bo'lishi kerak bo'lgan portlar (firewall/xavfsizlik guruhida):**
- `22` — SSH (faqat administratorlar tarmog'idan, tavsiya etiladi)
- `8082` (yoki `.env`dagi `FRONTEND_PORT`) — dashboard veb-interfeysi
- `3128`–`3131` — 4 ta Squid'ning proxy portlari, **faqat** ular orqali proxy bo'ladigan
  ichki tarmoq(lar)dan kirish uchun, tashqi internetdan emas

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

## 2-BOSQICH: Real test (4 ta haqiqiy Squid bilan, `LOG_SOURCES`)

1-bosqich muvaffaqiyatli o'tgandan keyingina bu bosqichga o'ting.

Sizning holingizda **4 ta Squid bir serverda** ishlaydi: filiallar, bosh ofis, umumiy
serverlar va yana bittasi. Bu qism aynan shu holat uchun — har bir Squid o'z portida, o'z
log faylida ishlaydi, dashboard esa `LOG_SOURCES` orqali barcha to'rttasini bitta panelga
yig'adi (har biri alohida "branch" sifatida, "Filiallar bo'yicha" filtrlash bilan).

> Quyidagi nomlar (`filiallar`, `bosh-ofis`, `umumiy`, `4chi`) — vaqtinchalik. 4-Squid'ning
> aniq vazifasini eslaganingizda yoki barcha nomlarni tasdiqlaganingizda, shu qismdagi
> nomlarni birga real nomlarga almashtiramiz.

### 2.1 Demo rejimni to'xtatish

```bash
cd ~/squid-watch
docker compose --profile demo down
```

### 2.2 Squid paketini o'rnatish

Serverda:

```bash
sudo apt update
sudo apt install -y squid
```

Bu bitta `squid` binary'sini o'rnatadi — 4 ta nusxani shu bitta binary'dan, 4 xil
konfiguratsiya fayli bilan ishga tushiramiz (pastga qarang).

O'rnatilgandan keyin paket bilan birga kelgan standart `squid` xizmatini **to'xtatib**
qo'yamiz (o'rniga 4 ta alohida instance ishlaydi):

```bash
sudo systemctl stop squid
sudo systemctl disable squid
```

### 2.3 Har bir Squid uchun papkalarni tayyorlash

```bash
sudo mkdir -p /var/log/squid-filiallar /var/log/squid-bosh-ofis /var/log/squid-umumiy /var/log/squid-4chi
sudo mkdir -p /var/spool/squid-filiallar /var/spool/squid-bosh-ofis /var/spool/squid-umumiy /var/spool/squid-4chi
sudo chown -R proxy:proxy /var/log/squid-filiallar /var/log/squid-bosh-ofis /var/log/squid-umumiy /var/log/squid-4chi
sudo chown -R proxy:proxy /var/spool/squid-filiallar /var/spool/squid-bosh-ofis /var/spool/squid-umumiy /var/spool/squid-4chi
```

### 2.4 4 ta konfiguratsiya fayli (ENG MUHIM QADAM)

Har biri uchun alohida fayl — **hammasida** `access_log ... squid` (native format) bo'lishi
shart, aks holda dashboard "ulangan" ko'rinadi lekin trafik ko'rsatmaydi.

```bash
sudo tee /etc/squid/squid-filiallar.conf > /dev/null <<'EOF'
http_port 3128
pid_filename /run/squid-filiallar.pid
cache_effective_user proxy
cache_effective_group proxy

acl localnet src 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16   # o'z ichki tarmog'ingizga moslang
acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 443

http_access allow localnet
http_access deny all

access_log /var/log/squid-filiallar/access.log squid
cache_dir ufs /var/spool/squid-filiallar 100 16 256
coredump_dir /var/spool/squid-filiallar
refresh_pattern .   0  20%  4320
EOF

sudo tee /etc/squid/squid-bosh-ofis.conf > /dev/null <<'EOF'
http_port 3129
pid_filename /run/squid-bosh-ofis.pid
cache_effective_user proxy
cache_effective_group proxy

acl localnet src 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16
acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 443

http_access allow localnet
http_access deny all

access_log /var/log/squid-bosh-ofis/access.log squid
cache_dir ufs /var/spool/squid-bosh-ofis 100 16 256
coredump_dir /var/spool/squid-bosh-ofis
refresh_pattern .   0  20%  4320
EOF

sudo tee /etc/squid/squid-umumiy.conf > /dev/null <<'EOF'
http_port 3130
pid_filename /run/squid-umumiy.pid
cache_effective_user proxy
cache_effective_group proxy

acl localnet src 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16
acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 443

http_access allow localnet
http_access deny all

access_log /var/log/squid-umumiy/access.log squid
cache_dir ufs /var/spool/squid-umumiy 100 16 256
coredump_dir /var/spool/squid-umumiy
refresh_pattern .   0  20%  4320
EOF

sudo tee /etc/squid/squid-4chi.conf > /dev/null <<'EOF'
http_port 3131
pid_filename /run/squid-4chi.pid
cache_effective_user proxy
cache_effective_group proxy

acl localnet src 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16
acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 443

http_access allow localnet
http_access deny all

access_log /var/log/squid-4chi/access.log squid
cache_dir ufs /var/spool/squid-4chi 100 16 256
coredump_dir /var/spool/squid-4chi
refresh_pattern .   0  20%  4320
EOF
```

> **Diqqat:** `acl localnet src ...` qatoridagi IP diapazonlarini o'z ichki tarmog'ingizga
> moslang — bu qaysi qurilmalar shu Squid orqali proxy bo'lishga ruxsat olishini
> belgilaydi.

### 2.5 4 ta Squid'ni systemd orqali ishga tushirish

Har bir instance uchun umumiy shablon (`squid-instance@.service`) yaratamiz. Bu — rasmiy
Ubuntu `squid` paketi bilan birga keladigan `/lib/systemd/system/squid.service`ning aynan
o'zi (`Type=notify`, `--foreground -sYC`), faqat har bir instance o'z `-f` konfiguratsiya
fayli va o'z PID faylini ishlatadigan qilib moslashtirilgan:

```bash
sudo tee /etc/systemd/system/squid-instance@.service > /dev/null <<'EOF'
[Unit]
Description=Squid Proxy instance: %i
Documentation=man:squid(8)
After=local-fs.target network.target network-online.target nss-lookup.target

[Service]
Type=notify
PIDFile=/run/squid-%i.pid
Group=proxy
ExecStartPre=/usr/sbin/squid -f /etc/squid/squid-%i.conf --foreground -z
ExecStart=/usr/sbin/squid -f /etc/squid/squid-%i.conf --foreground -sYC
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
NotifyAccess=all
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now squid-instance@filiallar
sudo systemctl enable --now squid-instance@bosh-ofis
sudo systemctl enable --now squid-instance@umumiy
sudo systemctl enable --now squid-instance@4chi
```

Tekshirish:

```bash
sudo systemctl status squid-instance@filiallar squid-instance@bosh-ofis squid-instance@umumiy squid-instance@4chi
```

Barcha to'rttasi `active (running)` bo'lishi kerak. Agar biror instance ishga tushmasa:
`sudo journalctl -u squid-instance@filiallar -n 50` bilan xato sababini ko'ring (odatda —
konfiguratsiya xatosi yoki papka ruxsati).

### 2.6 `docker-compose.yml`'da 4 ta log manbasini ulash

`backend` xizmatining `volumes` bo'limiga 4 ta log papkasini qo'shamiz (bularni men sizga
qadamda o'zim tahrirlab beraman — shunchaki tayyor bo'lganingizda ayting), taxminan
shunday ko'rinishda:

```yaml
  backend:
    <<: *backend-common
    environment:
      LOG_SOURCES: >-
        [{"branch":"filiallar","path":"/data/squid-logs/filiallar/access.log"},
         {"branch":"bosh_ofis","path":"/data/squid-logs/bosh-ofis/access.log"},
         {"branch":"umumiy","path":"/data/squid-logs/umumiy/access.log"},
         {"branch":"4chi","path":"/data/squid-logs/4chi/access.log"}]
    volumes:
      - /var/log/squid-filiallar:/data/squid-logs/filiallar:ro
      - /var/log/squid-bosh-ofis:/data/squid-logs/bosh-ofis:ro
      - /var/log/squid-umumiy:/data/squid-logs/umumiy:ro
      - /var/log/squid-4chi:/data/squid-logs/4chi:ro
      - archive_data:/app/archives
```

(Bu `LOG_FILE_PATH` va yagona `squid_log_data` volume'ini almashtiradi — `LOG_SOURCES`
belgilangan bo'lsa, `LOG_FILE_PATH` e'tiborga olinmaydi.)

Har bir log papkasi Docker konteyneridan o'qilishi uchun, host tomonda ruxsat kerak bo'lishi
mumkin (biz bugun sinaganimizda ko'rganimizdek):

```bash
sudo chmod o+r /var/log/squid-filiallar/access.log /var/log/squid-bosh-ofis/access.log \
               /var/log/squid-umumiy/access.log /var/log/squid-4chi/access.log
```

### 2.7 Qayta ishga tushirish (demo profilisiz)

```bash
docker compose up --build -d
```

### 2.8 Haqiqiy trafik yaratish

Har bir Squid — o'z tarmoq segmenti (filiallar, bosh ofis, umumiy serverlar, 4-chi) uchun
proxy sifatida sozlanadi: shu segmentdagi qurilmalar/brauzerlarni tegishli Squid'ning
`SERVER_IP:PORT` manziliga (3128=filiallar, 3129=bosh-ofis, 3130=umumiy, 3131=4chi) proxy
qilib ko'rsating, so'ng bir nechta saytga kiring — bular tegishli Squid orqali o'tib, o'z
`access.log`iga yoziladi.

### 2.9 Tekshirish

```bash
curl http://localhost:8001/api/health
```

Javobdagi `log_sources` massivida **4 ta yozuv** ko'rinishi kerak (`filiallar`,
`bosh_ofis`, `umumiy`, `4chi`), har birining `parse_failure_rate`i alohida, `0`ga yaqin
bo'lishi kerak. Agar biror branch `1.0` ko'rsatsa — **faqat o'sha** filialning
`squid.conf`idagi log format noto'g'ri (2.4-qadamni qaytadan tekshiring); qolgan filiallar
bundan ta'sirlanmaydi (buni biz bugun aynan shu ssenariyda sinab tasdiqladik).

Brauzerda `http://SERVER_IP:8082` ochib, dashboarddagi filial tanlagichi (Branch selector)
orqali har bir filialni alohida ko'rib chiqing.

---

## 3-BOSQICH: Sig'imni (capacity) haqiqiy trafikka moslash

2-bosqich bir necha kun (kamida 3-5 kun, real trafik bilan) ishlab turgandan keyin,
0-bosqichdagi boshlang'ich VM taxmini (8-16GB RAM, 100-200GB disk) sizning haqiqiy trafik
hajmingiz (endi 4 ta manbadan yig'ilgan) uchun yetarlimi — buni **taxmin qilish emas,
kuzatib bilish** kerak.

### 3.1 Xotira (ring buffer) yetarli-yetarli emasligini tekshirish

```bash
curl http://localhost:8001/api/health
```

Javobdagi ikkita maydonga qarang:
- `aggregator_backlog_ratio` — `1.0`ga yaqinlashsa, demak tizim ortda qolyapti
- `aggregator_events_likely_lost` — agar `true` bo'lsa, demak `RING_BUFFER_MAX_EVENTS`
  (`.env`dagi standart qiymat: `500000`) **4 ta filialning birlashgan** trafigi uchun
  yetarli emas, ba'zi hodisalar yo'qolayotgan bo'lishi mumkin — buni oshirish kerak.

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

Bu — faqat Postgres bazasi uchun. Bundan tashqari har bir Squid'ning o'z `cache_dir`i
(2.4-qadamda har biriga 100MB ajratilgan, kerak bo'lsa kattalashtirish mumkin) alohida
disk joy egallaydi.

Agar kerakli disk serverdagi bo'sh diskdan katta bo'lsa — `RETENTION_DAYS_RAW_EVENTS`ni
kamaytiring (eski xom ma'lumot avtomatik arxivlanadi, yo'qolib ketmaydi — README'dagi
"Archiving" bo'limiga qarang).

### 3.3 RAM sarfini tekshirish

```bash
docker stats --no-stream
free -h
```

`docker stats` — `backend`/`postgres`/`frontend` konteynerlarining sarfini, `free -h` —
Squid'larning (ular Docker'da emas, to'g'ridan-to'g'ri VM'da ishlayapti) va umumiy tizim
xotirasini ko'rsatadi. Agar server RAM'i cheklangan va 3.1-qadamda
`aggregator_events_likely_lost: false` bo'lsa, `RING_BUFFER_MAX_EVENTS`ni xavfsiz
kamaytirish mumkin (ma'lumot yo'qolmaydi — baza barcha holatda asosiy manba).

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
- `sudo systemctl status squid-instance@<nom>` — qaysi Squid instance ishlamayotganini ko'rish
- `sudo journalctl -u squid-instance@<nom> -n 50` — o'sha Squid instance'ning xato sababini ko'rish

Har qanday xato chiqsa, chiqqan xabarni to'liq nusxalab yuboring — birga hal qilamiz.

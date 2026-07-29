# Squid Watch — Uzoq serverdagi Squid'ni ulash (1-filial: "filiallar")

Bu qo'llanmadagi **har bir kod bloki to'liq tayyor** — ichida hech narsani qo'lda
qidirib-almashtirish shart emas, shunchaki nusxalab, terminalga joylashtirib, Enter
bosasiz. Hozircha faqat **1 ta filial — "filiallar"** ulanadi. Yana filial qo'shish
kerak bo'lganda (masalan "bosh_ofis"), faylning eng oxiridagi qismga qarang — u yerda
nima o'zgarishini qisqa tushuntirib o'tilgan.

Ikkita kompyuter ishtirok etadi:

```
┌────────────────────────────┐              ┌────────────────────────────┐
│  FILIAL SERVERI              │              │  MARKAZIY SERVER (VM)       │
│  (Squid shu yerda ishlaydi,  │   rsyslog    │  (dashboard shu yerda:      │
│   siz uni boshqarmaysiz)     │  ──TLS──→    │   backend+frontend+baza)    │
│                                │   orqali     │                              │
│  Buni boshqaradigan ODAM      │   log        │  Buni SIZ boshqarasiz       │
│  ishlaydi (5-QISM ularga)     │   yuboradi   │                              │
└────────────────────────────┘              └────────────────────────────┘
```

---

## 1-QISM — VM so'rash

VM beruvchidan quyidagilarni so'rang:

| Talab | Qiymat |
|---|---|
| OS | Ubuntu 22.04 yoki 24.04 LTS |
| RAM | kamida 8 GB |
| Disk | kamida 100 GB |
| Kirish | SSH + **root/sudo** huquqi |
| Ochiq portlar | `22`, `8082`, `6514` (`6514` — faqat filial serverining IP'idan) |

VM tayyor bo'lgach, SSH orqali kiring:
```bash
ssh FOYDALANUVCHI@VM_IP
```

---

## 2-QISM — Loyihani serverga tushirish

VM ichida, ketma-ket nusxalab joylashtiring:

```bash
sudo apt update
sudo apt install -y git openssl rsyslog rsyslog-gnutls
```

```bash
docker --version || curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Shundan keyin `exit` deb yozib chiqing, so'ng qayta `ssh FOYDALANUVCHI@VM_IP` bilan kiring
(bu — Docker huquqini yangilash uchun, faqat bir marta kerak).

Qayta kirgach:
```bash
git clone https://github.com/DiorDevv/Squid-Proxy.git ~/squid-watch
cd ~/squid-watch
cp .env.example .env
```

Kuchli parollarni avtomatik generatsiya qilib, `.env`ga yozib qo'yamiz (qo'lda yozish
shart emas — quyidagi 4 ta buyruqni ketma-ket, o'zgartirmasdan nusxalab joylashtiring):

```bash
POSTGRES_PW=$(openssl rand -hex 24)
JWT_SEC=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
ADMIN_PW=$(openssl rand -hex 12)
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PW|; s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SEC|; s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$ADMIN_PW|" .env
```

```bash
echo "Dashboard parolingiz: $ADMIN_PW"
```

**Shu paroldni albatta yozib/saqlab qo'ying** — bu keyinroq dashboard'ga kirish uchun
kerak bo'ladi (email: `admin@example.com`).

---

## 3-QISM — Sertifikatlar yaratish

Bitta buyruq bloki bilan hammasi yaratiladi (nomlarni o'zgartirish shart emas — ular
shunchaki ichki belgilar, keyingi qismlarda ular bilan aynan mos keladi):

```bash
mkdir -p ~/squid-certs && cd ~/squid-certs

openssl genrsa -out ca-key.pem 4096
openssl req -x509 -new -nodes -key ca-key.pem -sha256 -days 3650 \
  -subj "/CN=SquidWatch CA" -out ca.pem

openssl genrsa -out central-key.pem 4096
openssl req -new -key central-key.pem -subj "/CN=central.squidwatch.local" -out central.csr
openssl x509 -req -in central.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out central.pem -days 825 -sha256

openssl genrsa -out branch-filiallar-key.pem 4096
openssl req -new -key branch-filiallar-key.pem -subj "/CN=branch-filiallar.squidwatch.local" \
  -out branch-filiallar.csr
openssl x509 -req -in branch-filiallar.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out branch-filiallar.pem -days 825 -sha256

cd ~/squid-watch
ls ~/squid-certs/*.pem
```

Oxirida 5 ta `.pem` fayl ko'rinishi kerak: `ca.pem`, `central.pem`, `central-key.pem`,
`branch-filiallar.pem`, `branch-filiallar-key.pem`.

> **Bu fayllar maxfiy.** Ulardan 3 tasini (`ca.pem`, `branch-filiallar.pem`,
> `branch-filiallar-key.pem`) filial serveriga o'tkazish kerak bo'ladi — buni **faqat**
> shifrlangan kanal orqali (SCP, yoki shifrlangan xabar) qiling, hech qachon oddiy
> email/chatga yopishtirmang.

---

## 4-QISM — Markaziy serverni sozlash

### 4.1 — Sertifikatlarni joyiga qo'yish

```bash
sudo mkdir -p /etc/rsyslog.d/certs /var/log/squid
sudo cp ~/squid-certs/ca.pem ~/squid-certs/central.pem ~/squid-certs/central-key.pem \
        /etc/rsyslog.d/certs/
```

### 4.2 — rsyslog qabul qiluvchi konfiguratsiyasi

Bu butun blokni nusxalab, terminalga joylashtiring (u to'liq tayyor faylni yaratadi):

```bash
sudo tee /etc/rsyslog.d/60-squid-receive.conf > /dev/null <<'EOF'
module(load="imtcp"
  StreamDriver.Name="gtls"
  StreamDriver.Mode="1"
  StreamDriver.AuthMode="x509/name"
  StreamDriver.PermittedPeer=["branch-filiallar.squidwatch.local"]
)

global(
  DefaultNetstreamDriverCAFile="/etc/rsyslog.d/certs/ca.pem"
  DefaultNetstreamDriverCertFile="/etc/rsyslog.d/certs/central.pem"
  DefaultNetstreamDriverKeyFile="/etc/rsyslog.d/certs/central-key.pem"
)

input(type="imtcp" port="6514")

template(name="squidRawLine" type="string" string="%msg%\n")
template(name="squidBranchFile" type="string" string="/var/log/squid/%programname:7:$%.log")

if $programname startswith "squid-" then {
  action(type="omfile" DynaFile="squidBranchFile" template="squidRawLine" fileCreateMode="0644")
  stop
}
EOF
```

```bash
sudo tee /etc/logrotate.d/squid-branches > /dev/null <<'EOF'
/var/log/squid/*.log {
  daily
  rotate 14
  compress
  delaycompress
  missingok
  notifempty
  copytruncate
}
EOF
```

```bash
sudo systemctl restart rsyslog
sudo systemctl status rsyslog --no-pager
```

`active (running)` yozuvini qidiring — qizil/xato bo'lmasligi kerak.

### 4.3 — Firewall

```bash
sudo ufw allow 8082
```

`6514`-portni **faqat** filial serverining IP'idan ochish uchun, o'sha IP ma'lum bo'lgach:
```bash
sudo ufw allow from FILIAL_SERVER_IP to any port 6514 proto tcp
```
(`FILIAL_SERVER_IP` o'rniga haqiqiy IP yozing — buni filial serverini boshqaruvchi odamdan
so'rang.)

### 4.4 — Dashboard'ni ulash

```bash
cd ~/squid-watch
cp docker-compose.override.yml.example docker-compose.override.yml

cat > docker-compose.override.yml <<'EOF'
services:
  backend:
    environment:
      LOG_SOURCES: '[{"branch":"filiallar","path":"/data/squid-logs/filiallar.log"}]'
    volumes:
      - /var/log/squid:/data/squid-logs:ro
EOF
```

```bash
docker compose up --build -d
docker compose ps
curl http://localhost:8001/api/health
```

`docker compose ps`da hammasi `running`/`healthy` bo'lishi kerak. `curl` natijasida
`log_sources`da `"branch": "filiallar"` ko'rinadi, lekin hozircha `"alive": false` bo'ladi
— bu normal, filial serveri hali ulanmagan (5-QISMdan keyin tuzaladi).

---

## 5-QISM — Filial serveriga yuboriladigan qism

**Bu qismni siz bajarmaysiz.** Quyidagi 5.1–5.3'ni **to'liq nusxalab**, filial serverini
boshqaradigan odamga yuboring. Ular 3-QISMda yaratilgan `ca.pem`, `branch-filiallar.pem`,
`branch-filiallar-key.pem` fayllariga muhtoj — bu 3 faylni ularga xavfsiz kanal orqali
alohida uzating.

---

> **Filial serveringizni sozlash uchun quyidagilarni bajaring:**
>
> ### 5.1 — Squid formatini tekshiring (ENG MUHIM)
>
> ```bash
> grep access_log /etc/squid/squid.conf
> ```
>
> Natija aynan shunday bo'lishi kerak (oxirida `squid` so'zi bilan):
> ```
> access_log /var/log/squid/access.log squid
> ```
>
> Agar boshqacha bo'lsa (`common`/`combined`, yoki yo'q) — shu qatorni yuqoridagidek
> tuzatib:
> ```bash
> sudo systemctl reload squid
> ```
>
> ### 5.2 — rsyslog o'rnatish va sertifikatlarni joylashtirish
>
> ```bash
> sudo apt update
> sudo apt install -y rsyslog rsyslog-gnutls
> sudo mkdir -p /etc/rsyslog.d/certs
> ```
>
> Sizga jo'natilgan `ca.pem`, `branch-filiallar.pem`, `branch-filiallar-key.pem`
> fayllarini `/etc/rsyslog.d/certs/` papkasiga joylashtiring, so'ng:
> ```bash
> sudo mv /etc/rsyslog.d/certs/branch-filiallar.pem /etc/rsyslog.d/certs/branch.pem
> sudo mv /etc/rsyslog.d/certs/branch-filiallar-key.pem /etc/rsyslog.d/certs/branch-key.pem
> ```
>
> ### 5.3 — Jo'natuvchi konfiguratsiyasi
>
> `CENTRAL_HOST_IP` o'rniga markaziy serverning haqiqiy IP manzilini yozib, shu blokni
> to'liq nusxalab joylashtiring:
>
> ```bash
> sudo tee /etc/rsyslog.d/60-squid-forward.conf > /dev/null <<'EOF'
> module(load="imfile" mode="inotify")
>
> global(
>   workDirectory="/var/spool/rsyslog"
> )
>
> input(
>   type="imfile"
>   File="/var/log/squid/access.log"
>   Tag="squid-filiallar:"
>   Severity="info"
>   Facility="local1"
>   PersistStateInterval="200"
> )
>
> global(
>   DefaultNetstreamDriver="gtls"
>   DefaultNetstreamDriverCAFile="/etc/rsyslog.d/certs/ca.pem"
>   DefaultNetstreamDriverCertFile="/etc/rsyslog.d/certs/branch.pem"
>   DefaultNetstreamDriverKeyFile="/etc/rsyslog.d/certs/branch-key.pem"
> )
>
> if $syslogtag startswith "squid-filiallar:" then {
>   action(
>     type="omfwd"
>     target="CENTRAL_HOST_IP"
>     port="6514"
>     protocol="tcp"
>     StreamDriver="gtls"
>     StreamDriverMode="1"
>     StreamDriverAuthMode="x509/name"
>     StreamDriverPermittedPeers="central.squidwatch.local"
>
>     queue.type="linkedlist"
>     queue.filename="squid_fwd_filiallar"
>     queue.maxdiskspace="2g"
>     queue.saveOnShutdown="on"
>     queue.spoolDirectory="/var/spool/rsyslog"
>     action.resumeRetryCount="-1"
>     action.resumeInterval="10"
>   )
>   stop
> }
> EOF
> ```
>
> ```bash
> sudo mkdir -p /var/spool/rsyslog
> sudo systemctl restart rsyslog
> sudo systemctl status rsyslog --no-pager
> ```
>
> `active (running)` bo'lishi kerak. Tayyor bo'lgach, shuni tasdiqlab xabar bering.
>
> **Firewall**: chiquvchi (outbound) TCP `6514` portga, markaziy server IP'iga ruxsat
> kerak (ko'pincha standart holatda ochiq bo'ladi, alohida sozlash shart emas).

---

## 6-QISM — Yakuniy tekshiruv

Filial serverida (ular tomonidan) Squid orqali biror sayt ochib ko'rilgach, siz markaziy
serverda:

```bash
sudo journalctl -u rsyslog -n 30 --no-pager
ls -la /var/log/squid/
```

`filiallar.log` fayli paydo bo'lishi kerak. So'ng:

```bash
curl http://localhost:8001/api/health
```

Natijada:
```json
"log_sources": [{"branch": "filiallar", "alive": true, "parse_failure_rate": 0.0}]
```

`alive: true` va `parse_failure_rate` `0`ga yaqin bo'lsa — hammasi ishlayapti.

Brauzerda: `http://VM_IP:8082` — email `admin@example.com`, parol 2-QISMda yozib
qo'yganingiz `ADMIN_PASSWORD` bilan kiring.

---

## Muammo jadvali

| Belgisi | Sabab | Yechim |
|---|---|---|
| `alive: false`, `/var/log/squid/filiallar.log` umuman yo'q | Fayl markaziy serverga kelmayapti | Ikkala tomonda `sudo journalctl -u rsyslog -n 50 --no-pager` bilan TLS xatosini qidiring |
| `alive: true`, lekin `parse_failure_rate: 1.0` | Squid noto'g'ri formatda yozyapti | 5.1-qadamni qaytadan tekshiring |
| TLS handshake xatosi (`journalctl`da) | Sertifikat nomlari mos kelmayapti | `central.conf`dagi `PermittedPeer` va `branch.conf`dagi `StreamDriverPermittedPeers` bir-biriga, `-subj "/CN=..."` bilan yaratilgan nomlarga mos kelishini tekshiring |
| Fayl bor, lekin backend ko'rmayapti | Fayl ruxsati | Markaziy serverda: `sudo chmod o+r /var/log/squid/filiallar.log` |

Har qanday xato chiqsa — to'liq xabar matnini nusxalab yuboring, birga hal qilamiz.

---

## Keyinroq yana filial qo'shish kerak bo'lsa

Masalan "bosh_ofis" nomli yangi filial qo'shish uchun, yuqoridagi qadamlarni takrorlaysiz,
faqat har joyda `filiallar` → `bosh_ofis` deb almashtirasiz:

- 3-QISM: yana bitta sertifikat juftligi (`branch-bosh_ofis.pem`/`-key.pem`)
- 4.2: markaziy `PermittedPeer` ro'yxatiga yangi hostname qo'shiladi (vergul bilan)
- 4.4: `LOG_SOURCES`ga yana bitta `{"branch":"bosh_ofis",...}` yozuvi va `volumes`da
  o'zgarish shart emas (`/var/log/squid` papkasi umumiy — barcha filiallarning fayllari
  shu bitta papkada, nomi bilan farqlanadi)
- 5-QISM: yangi filial serveriga xuddi shu ko'rsatma, `filiallar` o'rniga `bosh_ofis` bilan

Bu qadamlarni kerak bo'lganda men sizga yana to'liq tayyor holda yozib beraman — hozircha
shu bitta filial bilan ishlashni tugatib, tasdiqlab oling.

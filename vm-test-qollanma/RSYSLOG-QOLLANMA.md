# Squid Watch — Uzoq (alohida) serverdagi Squid'ni ulash (rsyslog orqali)

Bu qo'llanma — Squid boshqa (alohida) serverda, dashboard esa boshqa (yangi) VM'da
bo'lgan holat uchun. Ikkalasi orasida log fayl **tarmoq orqali, shifrlangan (TLS) holda**
ko'chiriladi — buni `rsyslog` degan dastur bajaradi.

Agar Squid va dashboard **bitta serverda** bo'lsa — bu qo'llanma sizga kerak emas, o'rniga
`vm-test-qollanma/QOLLANMA.md`dagi oddiyroq usulni ishlating.

---

## 0-QISM: Umumiy tushuncha (avval shuni o'qing)

Ikkita kompyuter bor:

```
┌───────────────────────────┐              ┌───────────────────────────┐
│  FILIAL SERVERI             │              │  MARKAZIY SERVER (VM)      │
│  (Squid allaqachon shu      │   rsyslog    │  (dashboard shu yerda      │
│   yerda ishlab turibdi,     │  ──TLS──→    │   ishlaydi: backend,       │
│   siz uni boshqara olmaysiz)│   log        │   frontend, baza)          │
│                              │   yuboradi   │                             │
│  Bu yerni boshqaradigan      │              │  Bu yerni SIZ boshqarasiz  │
│  ODAM ishlaydi               │              │                             │
└───────────────────────────┘              └───────────────────────────┘
```

**Nima sodir bo'ladi**: Filial serverida Squid o'z `access.log` fayliga yozib boradi. O'sha
serverga o'rnatilgan `rsyslog` bu faylni kuzatib turadi va har bir yangi qatorni **darhol**
markaziy serverga jo'natadi (shifrlangan tunnel orqali). Markaziy serverdagi `rsyslog` buni
qabul qilib, oddiy faylga yozadi — xuddi o'sha fayl shu yerda yaratilgandek. Dashboard
backend'i esa faqat shu (mahalliy) faylni o'qiydi — u qayerdan kelganini bilishi shart emas.

**Kimga nima tegishli**:
- **Siz** — faqat markaziy server (VM)ni boshqarasiz. Shu yerda 1-4-QISMlarni bajarasiz.
- **Filial serverini boshqaruvchi odam** — 5-QISMdagi ko'rsatmalarni bajaradi (siz shu
  qismni ularga jo'natasiz).

---

## 1-QISM: VM so'rash

VM beruvchidan so'rang:

| Talab | Qiymat |
|---|---|
| OS | Ubuntu 22.04 yoki 24.04 LTS |
| RAM | kamida 8 GB |
| Disk | kamida 100 GB |
| Kirish huquqi | SSH + **root/sudo** |
| Ochiq portlar | `22` (SSH), `8082` (dashboard), `6514` (rsyslog qabul qilish — faqat filial serverining IP'idan) |

VM tayyor bo'lib, unga SSH orqali kira oladigan bo'lgach, keyingi qismga o'ting.

---

## 2-QISM: Markaziy serverda loyihani tayyorlash

SSH orqali VM'ga kiring, so'ng:

```bash
sudo apt update
sudo apt install -y git

# Docker o'rnatish (agar hali yo'q bo'lsa)
docker --version || curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# Shundan keyin: exit deb chiqing, qayta ssh bilan kiring (huquq yangilanishi uchun)

git clone https://github.com/DiorDevv/Squid-Proxy.git ~/squid-watch
cd ~/squid-watch

cp .env.example .env
nano .env
```

`.env` faylida kamida shu 3 tasini kuchli qiymatga o'zgartiring:
- `POSTGRES_PASSWORD`
- `JWT_SECRET` (yaratish uchun: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`)
- `ADMIN_PASSWORD`

---

## 3-QISM: Sertifikatlar yaratish

`rsyslog` ikki server orasida TLS (shifrlash) ishlatadi — bu esa umumiy "ishonch markazi"
(CA) va har ikki tomon uchun alohida sertifikat talab qiladi. Buni **markaziy serverning
o'zida** yarataylik:

```bash
mkdir -p ~/squid-certs && cd ~/squid-certs

# O'z shaxsiy "ishonch markazi" (CA)
openssl genrsa -out ca-key.pem 4096
openssl req -x509 -new -nodes -key ca-key.pem -sha256 -days 3650 \
  -subj "/CN=SquidWatch CA" -out ca.pem

# Markaziy server uchun sertifikat
openssl genrsa -out central-key.pem 4096
openssl req -new -key central-key.pem -subj "/CN=central.squidwatch.local" -out central.csr
openssl x509 -req -in central.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out central.pem -days 825 -sha256

# Filial serveri uchun sertifikat
openssl genrsa -out branch-key.pem 4096
openssl req -new -key branch-key.pem -subj "/CN=branch-filiallar.squidwatch.local" -out branch.csr
openssl x509 -req -in branch.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out branch.pem -days 825 -sha256

ls ~/squid-certs
```

Natijada 6 ta `.pem` fayl bo'lishi kerak (+ ishlatilmaydigan `.csr` fayllar). Bu fayllar
**maxfiy** — hech qachon git'ga qo'ymang, faqat SSH/SCP orqali uzating.

> `/CN=...` qatoridagi nomlar shunchaki belgi — haqiqiy domen bo'lishi shart emas, lekin
> keyingi qismlarda **aynan shu nomlar bilan** ishlatiladi, o'zgartirmang (yoki hamma joyda
> birdek o'zgartiring).

---

## 4-QISM: Markaziy serverni sozlash

```bash
cd ~/squid-watch
sudo apt install -y rsyslog rsyslog-gnutls

sudo mkdir -p /etc/rsyslog.d/certs /var/log/squid
sudo cp ~/squid-certs/ca.pem ~/squid-certs/central.pem ~/squid-certs/central-key.pem \
        /etc/rsyslog.d/certs/

sudo cp deploy/rsyslog/central.conf /etc/rsyslog.d/60-squid-receive.conf
sudo nano /etc/rsyslog.d/60-squid-receive.conf
```

Faylda **`PermittedPeer`** qatorini toping va shunday qiling (faqat 1 ta filial uchun):
```
StreamDriver.PermittedPeer=["branch-filiallar.squidwatch.local"]
```

Saqlab chiqing, so'ng:

```bash
sudo cp deploy/rsyslog/squid-branches.logrotate /etc/logrotate.d/squid-branches
sudo systemctl restart rsyslog
sudo systemctl status rsyslog
```

`active (running)` ko'rinishi kerak, xato bo'lmasligi kerak.

**Firewall** (agar `ufw` ishlatilsa):
```bash
sudo ufw allow 8082
sudo ufw allow from FILIAL_SERVER_IP to any port 6514 proto tcp
```
(`FILIAL_SERVER_IP` — filial serverining haqiqiy IP manzili, buni filial serverini
boshqaruvchi odamdan so'rang.)

### Dashboard'ni ulash

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
nano docker-compose.override.yml
```

Ichini to'liq shunga almashtiring:
```yaml
services:
  backend:
    environment:
      LOG_SOURCES: '[{"branch":"filiallar","path":"/data/squid-logs/filiallar.log"}]'
    volumes:
      - /var/log/squid:/data/squid-logs:ro
```

```bash
docker compose up --build -d
docker compose ps          # hammasi "running"/"healthy" bo'lishi kerak
curl http://localhost:8001/api/health
```

Hozircha `log_sources`da `filiallar` ko'rinadi, lekin `alive: false` bo'ladi (chunki filial
serveri hali ulanmagan) — bu normal, keyingi qismdan keyin tuzaladi.

---

## 5-QISM: Filial serveriga yuboriladigan ko'rsatma

**Bu qismni siz bajarmaysiz** — quyidagini (5.1 va 5.2) filial serverini boshqaradigan
odamga yuboring, va 3-qismda yaratilgan 3 ta faylni (`ca.pem`, `branch.pem`,
`branch-key.pem`) ularga xavfsiz kanal orqali (masalan shifrlangan xabar, SCP) uzating —
hech qachon email/messenger orqali oddiy matn sifatida yubormang.

### 5.1 — Squid formatini tekshirish (ENG MUHIM)

```bash
grep access_log /etc/squid/squid.conf
```

Natija aynan shunday bo'lishi kerak (oxirida `squid` so'zi bilan):
```
access_log /var/log/squid/access.log squid
```

Agar boshqacha bo'lsa (masalan `common`/`combined`, yoki hech narsa yozilmagan) — shu
qatorni yuqoridagidek tuzatib:
```bash
sudo systemctl reload squid
```

### 5.2 — rsyslog o'rnatish va sozlash

```bash
sudo apt update
sudo apt install -y rsyslog rsyslog-gnutls

sudo mkdir -p /etc/rsyslog.d/certs
# ca.pem, branch.pem, branch-key.pem fayllarini shu papkaga joylashtiring
```

Loyihaning `deploy/rsyslog/branch.conf` faylini oling (undan nusxa ko'chiring yoki quyidagi
matnni to'g'ridan-to'g'ri yuboring), `/etc/rsyslog.d/60-squid-forward.conf` deb saqlang, va
ichida quyidagilarni almashtiring:

- Har joyda `BRANCH_TAG` → `filiallar`
- `CENTRAL_HOST` → markaziy serverning haqiqiy IP/hostname'i
- `StreamDriverPermittedPeers="central.example.internal"` →
  `StreamDriverPermittedPeers="central.squidwatch.local"`

So'ng:
```bash
sudo mkdir -p /var/spool/rsyslog
sudo systemctl restart rsyslog
sudo systemctl status rsyslog
```

**Firewall**: chiquvchi (outbound) TCP `6514` portga, markaziy server manziliga ruxsat
kerak (ko'pincha standart holatda ochiq bo'ladi).

---

## 6-QISM: Yakuniy tekshiruv

Filial serverida (ular tomonidan) biror sayt ochib ko'rilgach:

```bash
sudo journalctl -u rsyslog -n 30
```
Xato (masalan TLS handshake xatosi) bo'lmasligi kerak.

**Markaziy serverda** (sizda):
```bash
ls -la /var/log/squid/          # filiallar.log paydo bo'lishi kerak
curl http://localhost:8001/api/health
```

`log_sources` massivida:
```json
{"branch": "filiallar", "alive": true, "parse_failure_rate": 0.0}
```
ko'rinishi kerak — `alive: true` va `parse_failure_rate` `0`ga yaqin bo'lsa, hammasi to'g'ri
ishlayapti.

Brauzerda: `http://VM_IP:8082` — `.env`dagi email/parol bilan kiring, "Jonli hodisalar"da
haqiqiy trafik ko'rina boshlaydi.

---

## Muammo yuzaga kelsa

| Belgisi | Sabab | Yechim |
|---|---|---|
| `alive: false`, hech qanday yozuv yo'q | Fayl markaziy serverga umuman kelmayapti | Ikkala tomonda `sudo journalctl -u rsyslog -n 50` bilan TLS/sertifikat xatosini qidiring |
| `alive: true`, lekin `parse_failure_rate: 1.0` | Squid noto'g'ri formatda yozyapti | 5.1-qadamni qaytadan tekshiring (**faqat shu filial**ga ta'sir qiladi) |
| TLS handshake xatosi | Sertifikat `CN`lari mos kelmayapti | 3-qismda yaratilgan nomlar bilan `central.conf`/`branch.conf`dagi `PermittedPeer` nomlari **aynan bir xil** ekanini tekshiring |
| Fayl kelyapti, lekin backend ko'rmayapti | Fayl ruxsati | Markaziy serverda: `sudo chmod o+r /var/log/squid/filiallar.log` |

Har qanday xato chiqsa — to'liq xabar matnini nusxalab yuboring, birga hal qilamiz.

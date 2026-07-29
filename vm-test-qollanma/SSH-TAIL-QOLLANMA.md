# Squid Watch — Uzoq serverdagi Squid'ni ulash (SSH orqali, rsyslog'siz)

Bu — `rsyslog`ga muqobil, ancha sodda yo'l: sertifikat, TLS sozlamalari kerak emas, faqat
**SSH kalit**. Squid o'z joyida (boshqa serverda) qoladi, dashboard esa alohida VM'da
ishlaydi. Hozircha faqat **1 ta filial — "filiallar"** uchun.

## Umumiy tushuncha

```
┌────────────────────────────┐              ┌────────────────────────────┐
│  FILIAL SERVERI              │   SSH orqali │  MARKAZIY SERVER (VM)       │
│  (Squid shu yerda ishlaydi)  │  ───────→    │  (dashboard shu yerda)      │
│                                │  "tail -f"   │                              │
│  Faqat: SSH kalitni           │  natijasini  │  Doimiy SSH ulanib turadi,  │
│  authorized_keys'ga qo'shish  │  o'qiydi     │  yangi qatorlarni mahalliy  │
│  kerak bo'ladi                │              │  faylga yozib boradi        │
└────────────────────────────┘              └────────────────────────────┘
```

**Qanday ishlaydi**: markaziy serverda doimiy ishlaydigan kichik xizmat (systemd service)
filial serveriga SSH orqali ulanadi, u yerda `tail -f access.log` buyrug'ini ishga
tushiradi va undan chiqadigan har bir yangi qatorni mahalliy faylga yozib boradi. Aloqa
uzilib qolsa (tarmoq muammosi) — xizmat avtomatik qayta ulanishga harakat qiladi.

**rsyslog'dan farqi**: sertifikat/TLS sozlash shart emas — faqat SSH kalit. Kamchiligi:
agar aloqa uzilib turgan paytda filial serverida yangi qatorlar yozilsa, ular **qaytarib
olinmaydi** (rsyslog'dagi kabi diskka navbatga qo'yilmaydi) — aloqa tiklangach, faqat
o'sha paytdan keyingi yangi qatorlar davom etadi. Qisqa (bir necha soniya-daqiqa)
uzilishlar uchun bu odatda muammo emas, lekin uzoq (soatlab) uzilish bo'lsa, o'sha
davrdagi ma'lumot yo'qoladi.

---

## 1-QISM — VM so'rash

VM beruvchidan quyidagilarni so'rang:

| Talab | Qiymat |
|---|---|
| OS | Ubuntu 22.04 yoki 24.04 LTS |
| RAM | kamida 8 GB |
| Disk | kamida 100 GB |
| Kirish | SSH + **root/sudo** huquqi |
| Ochiq portlar | `22`, `8082` (chiquvchi SSH ulanishi uchun alohida port ochish shart emas — bu VM filial serveriga **o'zi ulanadi**, portni **filial serveri** o'z tomonida ochishi kerak, odatda SSH porti `22` allaqachon ochiq bo'ladi) |

VM tayyor bo'lgach, SSH orqali kiring:
```bash
ssh FOYDALANUVCHI@VM_IP
```

---

## 2-QISM — Loyihani serverga tushirish

```bash
sudo apt update
sudo apt install -y git openssl
```

```bash
docker --version || curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Shundan keyin `exit` deb chiqing, qayta `ssh FOYDALANUVCHI@VM_IP` bilan kiring (Docker
huquqini yangilash uchun, bir marta kerak).

Qayta kirgach:
```bash
git clone https://github.com/DiorDevv/Squid-Proxy.git ~/squid-watch
cd ~/squid-watch
cp .env.example .env
```

```bash
POSTGRES_PW=$(openssl rand -hex 24)
JWT_SEC=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
ADMIN_PW=$(openssl rand -hex 12)
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PW|; s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SEC|; s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$ADMIN_PW|" .env
echo "Dashboard parolingiz: $ADMIN_PW"
```

**Shu paroldni yozib qo'ying** — dashboard'ga kirish uchun kerak bo'ladi (email:
`admin@example.com`).

---

## 3-QISM — SSH kalit yaratish

Markaziy serverda, faqat shu maqsad uchun alohida SSH kalit yaratamiz (mavjud kalitlarga
tegmaymiz):

```bash
sudo mkdir -p /root/.ssh
sudo ssh-keygen -t ed25519 -f /root/.ssh/squid-tail-filiallar -N "" -C "squid-watch-tail-filiallar"
```

Ochiq kalitni (public key) ko'rish uchun:
```bash
sudo cat /root/.ssh/squid-tail-filiallar.pub
```

Chiqqan matnni (`ssh-ed25519 AAAA...` bilan boshlanadigan bitta uzun qator) **nusxalab
oling** — bu 4-QISMda filial serveriga kerak bo'ladi.

---

## 4-QISM — Filial serveriga yuboriladigan qism

**Bu qismni siz bajarmaysiz.** Quyidagini to'liq nusxalab, filial serverini boshqaradigan
odamga yuboring, va 3-QISMda ko'chirib olgan ochiq kalitni (`ssh-ed25519 AAAA...`) ham
birga yuboring.

---

> **Filial serveringizda quyidagilarni bajaring:**
>
> ### 4.1 — Squid formatini tekshiring (ENG MUHIM)
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
> Agar boshqacha bo'lsa — shu qatorni tuzatib, `sudo systemctl reload squid` deb qayta
> yuklang.
>
> ### 4.2 — Faqat log o'qish huquqiga ega, cheklangan foydalanuvchi yarating
>
> To'liq root emas, faqat shu bitta faylni o'qiy oladigan foydalanuvchi yaratamiz —
> xavfsizroq:
>
> ```bash
> sudo useradd --system --no-create-home --shell /usr/sbin/nologin squidwatch-reader
> sudo usermod -aG adm squidwatch-reader
> ```
>
> (`adm` guruhi Ubuntu'da odatda `/var/log/squid/`ni o'qishga ruxsat beradi; agar
> `access.log` boshqa guruhga tegishli bo'lsa — `ls -la /var/log/squid/access.log` bilan
> tekshirib, shu guruhga qo'shing.)
>
> ### 4.3 — Markaziy serverning ochiq kalitini qo'shish
>
> ```bash
> sudo mkdir -p /var/lib/squidwatch-reader/.ssh
> ```
>
> Sizga yuborilgan `ssh-ed25519 AAAA...` qatorini quyidagi faylga qo'shing (matnni
> `AAAA...` o'rniga real kalit bilan almashtirib):
>
> ```bash
> echo 'ssh-ed25519 AAAA... squid-watch-tail-filiallar' | sudo tee -a /var/lib/squidwatch-reader/.ssh/authorized_keys
> sudo chown -R squidwatch-reader:squidwatch-reader /var/lib/squidwatch-reader/.ssh
> sudo chmod 700 /var/lib/squidwatch-reader/.ssh
> sudo chmod 600 /var/lib/squidwatch-reader/.ssh/authorized_keys
> ```
>
> `nologin` foydalanuvchi uchun SSH'ga ruxsat berish uchun, `/etc/ssh/sshd_config`ga
> quyidagini qo'shing:
> ```bash
> echo -e "\nMatch User squidwatch-reader\n    AuthorizedKeysFile /var/lib/squidwatch-reader/.ssh/authorized_keys\n    ForceCommand /usr/bin/tail -F -n 0 /var/log/squid/access.log\n    AllowTcpForwarding no\n    X11Forwarding no" | sudo tee -a /etc/ssh/sshd_config
> sudo systemctl restart sshd
> ```
>
> (`ForceCommand` — bu foydalanuvchi SSH orqali ulanganda **faqat** shu bitta buyruqni
> bajara olishini ta'minlaydi, boshqa hech narsa qila olmaydi — qo'shimcha xavfsizlik
> qatlami.)
>
> Tayyor bo'lgach, markaziy server IP manzilini va foydalanuvchi nomini
> (`squidwatch-reader`) tasdiqlab xabar bering.

---

## 5-QISM — Markaziy serverda xizmatni sozlash

Filial serveridan **IP manzil** olgach (masalan `203.0.113.10`), quyidagini bajaring:

```bash
sudo mkdir -p /var/log/squid-filiallar
sudo chown root:root /var/log/squid-filiallar
```

Avval qo'lda bir marta ulanib, hammasi ishlashini tekshiring (bu ulanishni doimiy eslab
qoladi va keyingi ulanishlarni tezlashtiradi):

```bash
sudo ssh -i /root/.ssh/squid-tail-filiallar -o StrictHostKeyChecking=accept-new \
  squidwatch-reader@FILIAL_SERVER_IP
```

(`FILIAL_SERVER_IP` o'rniga haqiqiy IP yozing.) Agar hammasi to'g'ri sozlangan bo'lsa,
ekranda Squid'ning jonli log qatorlari oqib kela boshlaydi (agar hozir trafik bo'lsa) yoki
hech narsa chiqmasdan kutib turadi (agar trafik yo'q bo'lsa) — ikkalasi ham normal. `Ctrl+C`
bilan to'xtating.

Agar xato chiqsa (masalan "Permission denied") — 4-QISM to'g'ri bajarilganini filial
serveri administratoridan qayta so'rang.

### Doimiy xizmat (systemd) yaratish

`SQUIDUSER` va `FILIAL_SERVER_IP` so'ralganda haqiqiy qiymatlarni kiriting:

```bash
read -p "Filial serveridagi foydalanuvchi nomi (masalan squidwatch-reader): " SQUIDUSER
read -p "Filial serverining IP manzili: " BRANCH_IP

sudo tee /etc/systemd/system/squid-tail-filiallar.service > /dev/null <<EOF
[Unit]
Description=Stream Squid access.log from filiallar branch server via SSH
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/bin/sh -c '/usr/bin/ssh -i /root/.ssh/squid-tail-filiallar -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes $SQUIDUSER@$BRANCH_IP >> /var/log/squid-filiallar/access.log'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

(`ForceCommand` filial serverida allaqachon `tail -F -n 0 ...`ni bajaradi, shuning uchun
bu yerda buyruq qayta yozilmaydi — ulanish o'zi shu buyruqni ishga tushiradi.)

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now squid-tail-filiallar
sudo systemctl status squid-tail-filiallar --no-pager
```

`active (running)` ko'rinishi kerak.

---

## 6-QISM — Dashboard'ni ulash

```bash
cd ~/squid-watch
cp docker-compose.override.yml.example docker-compose.override.yml

cat > docker-compose.override.yml <<'EOF'
services:
  backend:
    environment:
      LOG_SOURCES: '[{"branch":"filiallar","path":"/data/squid-logs/filiallar/access.log"}]'
    volumes:
      - /var/log/squid-filiallar:/data/squid-logs/filiallar:ro
EOF
```

```bash
docker compose up --build -d
docker compose ps
```

Hammasi `running`/`healthy` bo'lishi kerak.

---

## 7-QISM — Yakuniy tekshiruv

Filial serverida (ular tomonidan) Squid orqali biror sayt ochilgach, bir necha soniyadan
keyin:

```bash
tail -f /var/log/squid-filiallar/access.log
```

Yangi qatorlar ko'rina boshlashi kerak (`Ctrl+C` bilan to'xtating). So'ng:

```bash
curl http://localhost:8001/api/health
```

Natijada:
```json
"log_sources": [{"branch": "filiallar", "alive": true, "parse_failure_rate": 0.0}]
```

`alive: true` va `parse_failure_rate` `0`ga yaqin bo'lsa — hammasi ishlayapti. Brauzerda:
`http://VM_IP:8082` — `admin@example.com` va 2-QISMda saqlagan parol bilan kiring.

---

## Muammo jadvali

| Belgisi | Sabab | Yechim |
|---|---|---|
| `Permission denied (publickey)` | Ochiq kalit noto'g'ri qo'shilgan yoki foydalanuvchi nomi xato | 4.3-qadamni qaytadan tekshiring; `sudo journalctl -u sshd -n 50` filial serverida xato sababini ko'rsatadi |
| `squid-tail-filiallar.service` doim qayta ishga tushmoqda | Ulanish uzilib-ulanib turibdi | `sudo journalctl -u squid-tail-filiallar -n 50 --no-pager` bilan aniq xatoni ko'ring |
| Xizmat ishlayapti, lekin `/var/log/squid-filiallar/access.log` bo'sh | Filial serverida trafik yo'q, yoki `ForceCommand` noto'g'ri sozlangan | Filial serverida `sudo -u squidwatch-reader tail -n 5 /var/log/squid/access.log` bilan fayl o'qilishini tekshiring |
| `alive: true`, lekin `parse_failure_rate: 1.0` | Squid noto'g'ri formatda yozyapti | 4.1-qadamni qaytadan tekshiring |

Har qanday xato chiqsa — to'liq xabar matnini nusxalab yuboring, birga hal qilamiz.

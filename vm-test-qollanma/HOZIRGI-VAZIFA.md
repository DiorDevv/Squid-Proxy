# To'liq ketma-ketlik — VM'dan dashboard ishga tushishigacha

## 1. VM'ga ulanish

O'z kompyuteringizda (Windows Terminal):

```bash
ssh FOYDALANUVCHI_NOMI@IP_MANZIL
```

`"Are you sure..."` chiqsa — `yes`. Parol so'rasa — kiriting (ekranda ko'rinmaydi).

---

## 2. Loyihani tushirish

```bash
sudo apt update
sudo apt install -y git openssl
```

```bash
docker --version || curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

```bash
exit
```

Qayta kiring:
```bash
ssh FOYDALANUVCHI_NOMI@IP_MANZIL
```

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

**Chiqqan parolni yozib qo'ying.** Email: `admin@example.com`.

---

## 3. SSH kalit yaratish

```bash
sudo mkdir -p /root/.ssh
sudo ssh-keygen -t ed25519 -f /root/.ssh/squid-tail-filiallar -N "" -C "squid-watch-tail-filiallar"
sudo cat /root/.ssh/squid-tail-filiallar.pub
```

Chiqqan `ssh-ed25519 AAAA...` qatorini nusxalab oling.

---

## 4. Squid administratoriga yuboring (to'liq nusxalab)

Ikkita variant bor — qaysi birini bajarish osonroq bo'lsa, o'shani tanlang.

### VARIANT A — agar serverga kiradigan MAVJUD hisobingiz bo'lsa (tavsiya, tezroq)

> **Squid serveringizda quyidagilarni bajaring:**
>
> #### A.1 — Log formatini tekshiring
> ```bash
> grep access_log /etc/squid/squid.conf
> ```
> Natija: `access_log /var/log/squid/access.log squid` (oxirida `squid` so'zi bilan).
> Boshqacha bo'lsa — shunga tuzatib, `sudo systemctl reload squid`.
>
> #### A.2 — Ushbu faylni o'qiy olishingizni tekshiring
> ```bash
> tail -n 3 /var/log/squid/access.log
> ```
> Xato chiqmasdan qatorlar ko'rinsa — davom eting. `Permission denied` chiqsa, VARIANT B'ga
> o'ting.
>
> #### A.3 — Kalitni qo'shing
> Quyidagi qatorda `AAAA...` o'rniga sizga yuborilgan haqiqiy kalitni qo'yib bajaring:
> ```bash
> mkdir -p ~/.ssh && chmod 700 ~/.ssh
> echo 'ssh-ed25519 AAAA... squid-watch-tail-filiallar' >> ~/.ssh/authorized_keys
> chmod 600 ~/.ssh/authorized_keys
> whoami   # natijasini menga ayting
> ```
>
> Tayyor bo'lgach, **server IP manzili** va yuqoridagi `whoami` natijasini (foydalanuvchi
> nomi) menga qaytaring.

### VARIANT B — mavjud hisob yo'q, yangi (cheklangan) hisob kerak

> **Squid serveringizda quyidagilarni bajaring:**
>
> #### B.1 — Log formatini tekshiring
> ```bash
> grep access_log /etc/squid/squid.conf
> ```
> Natija: `access_log /var/log/squid/access.log squid` (oxirida `squid` so'zi bilan).
> Boshqacha bo'lsa — shunga tuzatib, `sudo systemctl reload squid`.
>
> #### B.2 — Cheklangan foydalanuvchi yarating
> ```bash
> sudo useradd --system --no-create-home --shell /usr/sbin/nologin squidwatch-reader
> sudo usermod -aG adm squidwatch-reader
> ```
>
> #### B.3 — Ochiq kalitni qo'shing
> ```bash
> sudo mkdir -p /var/lib/squidwatch-reader/.ssh
> ```
> Quyidagi qatorda `AAAA...` o'rniga sizga yuborilgan haqiqiy kalitni qo'yib bajaring:
> ```bash
> echo 'ssh-ed25519 AAAA... squid-watch-tail-filiallar' | sudo tee -a /var/lib/squidwatch-reader/.ssh/authorized_keys
> sudo chown -R squidwatch-reader:squidwatch-reader /var/lib/squidwatch-reader/.ssh
> sudo chmod 700 /var/lib/squidwatch-reader/.ssh
> sudo chmod 600 /var/lib/squidwatch-reader/.ssh/authorized_keys
> ```
>
> #### B.4 — SSH sozlamasi
> ```bash
> echo -e "\nMatch User squidwatch-reader\n    AuthorizedKeysFile /var/lib/squidwatch-reader/.ssh/authorized_keys\n    ForceCommand /usr/bin/tail -F -n 0 /var/log/squid/access.log\n    AllowTcpForwarding no\n    X11Forwarding no" | sudo tee -a /etc/ssh/sshd_config
> sudo systemctl restart sshd
> ```
>
> Tayyor bo'lgach, **server IP manzilini** menga qaytaring (foydalanuvchi nomi:
> `squidwatch-reader`).

---

**VARIANT A tanlangan bo'lsa** — 5-qadamdagi buyruqlarda `squidwatch-reader` o'rniga
ularning haqiqiy foydalanuvchi nomini, va SSH buyrug'iga (5-qadamning qo'lda sinash
qismida) oxiriga `"tail -F -n 0 /var/log/squid/access.log"` qo'shimcha buyrug'ini qo'shing
— chunki VARIANT A'da `ForceCommand` yo'q, buyruq mijoz tomondan ko'rsatilishi kerak:

```bash
sudo ssh -i /root/.ssh/squid-tail-filiallar -o StrictHostKeyChecking=accept-new \
  FOYDALANUVCHI@FILIAL_SERVER_IP "tail -F -n 0 /var/log/squid/access.log"
```

Xuddi shu qo'shimcha buyruq 5-qadamdagi systemd faylining `ExecStart` qatoriga ham
qo'shiladi (pastda ikkala variant uchun alohida ko'rsatilgan).

---

## 5. IP kelgach — VM'da davom eting

```bash
sudo mkdir -p /var/log/squid-filiallar
sudo chown root:root /var/log/squid-filiallar
```

**Diqqat**: `SQUID_REMOTE_CMD` qiymatini tanlangan variantga qarab belgilang:

```bash
# VARIANT A (mavjud hisob, ForceCommand yo'q) uchun:
SQUID_REMOTE_CMD='tail -F -n 0 /var/log/squid/access.log'
# VARIANT B (squidwatch-reader, ForceCommand bor) uchun -- shunchaki bo'sh qoldiring:
SQUID_REMOTE_CMD=''
```

Qo'lda sinab ko'ring (`FOYDALANUVCHI` va `FILIAL_SERVER_IP` o'rniga haqiqiylarini yozing):
```bash
sudo ssh -i /root/.ssh/squid-tail-filiallar -o StrictHostKeyChecking=accept-new \
  FOYDALANUVCHI@FILIAL_SERVER_IP $SQUID_REMOTE_CMD
```
Xato chiqmasdan qatorlar oqib kela boshlasa (yoki hech narsa chiqmasdan kutib tursa) —
`Ctrl+C` bilan chiqing, davom eting. Xato chiqsa — matnini yuboring.

Doimiy xizmat yarating:
```bash
read -p "Filial serveridagi foydalanuvchi nomi: " SQUIDUSER
read -p "Filial serverining IP manzili: " BRANCH_IP

sudo tee /etc/systemd/system/squid-tail-filiallar.service > /dev/null <<EOF
[Unit]
Description=Stream Squid access.log from filiallar branch server via SSH
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/bin/sh -c '/usr/bin/ssh -i /root/.ssh/squid-tail-filiallar -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes $SQUIDUSER@$BRANCH_IP $SQUID_REMOTE_CMD >> /var/log/squid-filiallar/access.log'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now squid-tail-filiallar
sudo systemctl status squid-tail-filiallar --no-pager
```

`active (running)` bo'lishi kerak.

---

## 6. Dashboard'ni ulash

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

---

## 7. Tekshirish

```bash
curl http://localhost:8001/api/health
```

`log_sources`da `"branch": "filiallar", "alive": true` ko'rinishi kerak.

Brauzerda: `http://VM_IP:8082` — `admin@example.com` + 2-qadamda saqlagan parol.

---

Har qanday qadamda xato chiqsa — xato matnini to'liq nusxalab yuboring.

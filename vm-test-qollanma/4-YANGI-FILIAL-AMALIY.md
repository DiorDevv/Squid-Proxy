# Yangi filial qo'shish — proxyanalyzer VM uchun tayyor qadamlar

**Vaqtinchalik fayl** — real qiymatlar (`axmadjonov`, `~/squid-watch/ssh-logs`) bilan
to'ldirilgan, faqat shu VM'dagi joriy filial qo'shish ishi uchun. Filial qo'shib
bo'lgach, bu faylni o'chirib tashlang (`git rm vm-test-qollanma/4-YANGI-FILIAL-AMALIY.md`)
— doimiy, umumiy qo'llanma `3-YANGI-FILIAL-QOSHISH.md`da turadi.

To'ldiring:
- `YANGI_FILIAL` — yangi filialga tanlagan nomingiz (masalan `bosh_ofis`)
- `FILIAL_IP` — yangi filialning Squid serveri IP manzili

---

## 1-qadam — markaziy serverda (bu VM, `axmadjonov`) yangi kalit yarating

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_rsa_squidreader_YANGI_FILIAL
cat ~/.ssh/id_rsa_squidreader_YANGI_FILIAL.pub
```
(chiqqan qatorni nusxalab oling -- 2-qadamda kerak bo'ladi)

## 2-qadam — yangi filialning Squid serveriga kiring

```bash
ssh FOYDALANUVCHI@FILIAL_IP
```

`squidreader` hisobi yo'q bo'lsa:
```bash
sudo useradd -m -s /bin/bash squidreader
sudo -u squidreader mkdir -p /home/squidreader/.ssh
```

```bash
sudo -u squidreader nano /home/squidreader/.ssh/authorized_keys
```
Bitta qatorda (1-qadamdagi ochiq kalitni oxiriga qo'shib):
```
command="tail -F /var/log/squid/access.log",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA...
```
Saqlang, `exit`.

## 3-qadam — markaziy serverda env fayl

```bash
cd ~/squid-watch
sudo mkdir -p /etc/squid-ssh-stream
sudo cp deploy/systemd/squid-ssh-stream.env.example /etc/squid-ssh-stream/YANGI_FILIAL.env
sudo nano /etc/squid-ssh-stream/YANGI_FILIAL.env
```
```
SSH_KEY_PATH=/home/axmadjonov/.ssh/id_rsa_squidreader_YANGI_FILIAL
SQUID_SSH_USER=squidreader
SQUID_SSH_HOST=FILIAL_IP
SQUID_ACCESS_LOG_PATH=/var/log/squid/access.log
LOCAL_LOG_PATH=/home/axmadjonov/squid-watch/ssh-logs/YANGI_FILIAL.log
```

## 4-qadam — xizmatni ishga tushiring

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now squid-ssh-stream@YANGI_FILIAL
sudo systemctl status squid-ssh-stream@YANGI_FILIAL --no-pager
```

## 5-qadam — dashboard'ga tanishtiring

```bash
nano .env
```
`LOG_SOURCES` (mavjud `filiallar`ni saqlab, yangisini qo'shing):
```
LOG_SOURCES=[{"branch":"filiallar","path":"/home/axmadjonov/squid-watch/ssh-logs/filiallar.log"},{"branch":"YANGI_FILIAL","path":"/home/axmadjonov/squid-watch/ssh-logs/YANGI_FILIAL.log"}]
```
```bash
docker compose restart backend
```

## 6-qadam — tekshirish

```bash
tail -f /home/axmadjonov/squid-watch/ssh-logs/YANGI_FILIAL.log
```
Dashboard'da filial-tanlagichda `YANGI_FILIAL` paydo bo'lishi kerak.

---

**Tugagach:** `git rm vm-test-qollanma/4-YANGI-FILIAL-AMALIY.md && git commit -m "Remove temp branch-setup notes" && git push`

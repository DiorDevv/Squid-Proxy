# 2-QISM — Real Squid'ni dashboard'ga ulash (SSH orqali)

Bu qo'llanma **dashboard allaqachon VM'da ishlab turgan** holatdan boshlanadi (agar hali
ishga tushirmagan bo'lsangiz, avval `1-LOYIHANI-ISHGA-TUSHIRISH.md`ni bajaring). Endi
maqsad — Squid boshqa (alohida) serverda bo'lsa ham, uning haqiqiy trafigini shu
dashboard'da ko'rsatish.

## Nima uchun bu qadamlar kerak — qisqacha

Squid boshqa kompyuterda ishlagani uchun, dashboard turgan VM u yerdagi faylni
to'g'ridan-to'g'ri ko'ra olmaydi. Shuning uchun VM **doimiy ravishda** Squid serveriga SSH
orqali ulanib turadigan kichik xizmat ishga tushiradi — bu xizmat Squid'ning yangi log
qatorlarini "tinglab", ularni VM'dagi mahalliy faylga yozib boradi. Dashboard esa **shu
mahalliy faylni** o'qiydi — u qayerdan kelganini bilishi shart emas.

---

## 1-QADAM — SSH kalit yaratish (VM'da)

Bu kalit — VM'ning "shaxsiyat guvohnomasi": u orqali Squid serveri VM'ni tanib, unga
ulanishga ruxsat beradi. Kalit ikki qismdan iborat: **maxfiy** qism (VM'da qoladi, hech
qachon hech kimga berilmaydi) va **ochiq** qism (Squid serveriga beriladi, maxfiy emas).

```bash
sudo mkdir -p /root/.ssh
sudo ssh-keygen -t ed25519 -f /root/.ssh/squid-tail-filiallar -N "" -C "squid-watch-tail-filiallar"
```

Ochiq qismni ko'rish uchun:
```bash
sudo cat /root/.ssh/squid-tail-filiallar.pub
```

Natija `ssh-ed25519 AAAA...` bilan boshlanadigan uzun matn bo'ladi. **Shuni to'liq
nusxalab oling** — u keyingi qadamda kerak bo'ladi.

---

## 2-QADAM — Squid serveriga yuborish

Squid hisobini sizga beradigan odamga (yoki o'zingiz agar kirish huquqingiz bo'lsa) shu
ikki narsani yuboring/bajaring:

### 2.1 — Log formatini tekshirish

```bash
grep access_log /etc/squid/squid.conf
```

Natija **aynan** shunday bo'lishi kerak (oxirida `squid` so'zi bilan):
```
access_log /var/log/squid/access.log squid
```

Bu — Squid o'z loglarini dashboard tushunadigan formatda yozayotganini bildiradi. Agar
boshqacha bo'lsa (masalan `common` yoki `combined`, yoki hech narsa yozilmagan bo'lsa) —
shu qatorni yuqoridagidek tuzatib, keyin:
```bash
sudo systemctl reload squid
```

### 2.2 — Ochiq kalitni qo'shish

1-qadamda olingan `ssh-ed25519 AAAA...` qatorini, berilgan hisob nomidan turib, shu
buyruq bilan qo'shiladi:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAA...(sizning haqiqiy kalitingiz)... squid-watch' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Bu buyruq — "VM'dan keladigan, shu kalitga mos ulanishlarni qabul qil" degan ruxsat
yozuvi. Boshqa hech narsa o'zgarmaydi, hech qanday yangi dastur o'rnatilmaydi.

### 2.3 — Tasdiqlash

Shu ma'lumotlarni sizga (dashboard operatoriga) qaytarishlari kerak:
- **Server IP manzili** (masalan `203.0.113.10`)
- **Foydalanuvchi nomi** (hisob nomi, masalan `squiduser`)

---

## 3-QADAM — VM'da qo'lda sinash

IP va foydalanuvchi nomini olgach, avval **qo'lda, bir marta** ulanib, hammasi to'g'ri
ishlashini tekshiramiz — bu doimiy xizmatni ishga tushirishdan oldingi xavfsizlik
tekshiruvi.

`FOYDALANUVCHI` va `FILIAL_SERVER_IP` o'rniga haqiqiy qiymatlarni yozib bajaring:

```bash
sudo ssh -i /root/.ssh/squid-tail-filiallar -o StrictHostKeyChecking=accept-new \
  FOYDALANUVCHI@FILIAL_SERVER_IP "tail -F -n 0 /var/log/squid/access.log"
```

**Nima kutish kerak**: agar Squid orqali hozir kimdir internetga kirayotgan bo'lsa —
ekranda jonli log qatorlari oqib kela boshlaydi. Agar hozircha trafik bo'lmasa — ekran
bo'sh, hech narsa chiqmasdan kutib turadi (bu ham **normal**, xato emas — chunki `-n 0`
faqat *yangi* qatorlarni ko'rsatadi, eskilarini emas).

Tekshirib bo'lgach, `Ctrl+C` bosib chiqing.

**Agar xato chiqsa** (masalan `Permission denied`) — xato matnini to'liq nusxalab
yuboring, 2-qadamni birga qaytadan tekshiramiz.

---

## 4-QADAM — Doimiy xizmat (systemd) yaratish

Bu — VM qayta ishga tushsa ham, aloqa uzilib qolsa ham, **avtomatik** ishlab turadigan
doimiy jarayon. 3-qadamda qo'lda qilgan ishni endi doimiylashtiramiz.

Avval, mahalliy log fayli uchun joy tayyorlaymiz:

```bash
sudo mkdir -p /var/log/squid-filiallar
sudo chown root:root /var/log/squid-filiallar
```

Endi xizmat faylini yaratamiz. Terminalda so'ralganda, foydalanuvchi nomi va IP manzilni
kiriting (Enter bosishdan oldin haqiqiy qiymatlarni yozing):

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
ExecStart=/bin/sh -c '/usr/bin/ssh -i /root/.ssh/squid-tail-filiallar -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes $SQUIDUSER@$BRANCH_IP "tail -F -n 0 /var/log/squid/access.log" >> /var/log/squid-filiallar/access.log'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

**Bu faylda nima yozilgan** (tushunish uchun, o'zgartirish shart emas):
- `ExecStart` — VM ishga tushganda bajariladigan asosiy buyruq: Squid serveriga ulanib,
  log oqimini mahalliy faylga yozadi
- `Restart=always` — agar aloqa uzilsa (tarmoq muammosi, Squid server qayta ishga
  tushishi), bu xizmat 5 soniyadan keyin **avtomatik qayta urinadi**, siz hech narsa
  qilishingiz shart emas
- `WantedBy=multi-user.target` — VM qayta yuklansa ham, bu xizmat o'zi qayta ishga
  tushadi

Endi xizmatni ishga tushiramiz:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now squid-tail-filiallar
```

Ishlab turganini tekshirish:

```bash
sudo systemctl status squid-tail-filiallar --no-pager
```

Natijada yashil `active (running)` yozuvi ko'rinishi kerak.

---

## 5-QADAM — Dashboard'ni shu log fayliga ulash

Endi dashboard'ga "mana shu faylni o'qi" deb ko'rsatamiz.

```bash
cd ~/squid-watch
```

Agar `docker-compose.override.yml` fayli **allaqachon bor** bo'lsa (masalan
`ENVIRONMENT: development` qo'shgan bo'lsangiz), uni oching:
```bash
nano docker-compose.override.yml
```
va `backend:` → `environment:` ostiga shu ikki qatorni **qo'shing** (mavjudlarini
o'chirmasdan):
```yaml
      LOG_SOURCES: '[{"branch":"filiallar","path":"/data/squid-logs/filiallar/access.log"}]'
```
va `backend:` ostiga (agar hali yo'q bo'lsa) `volumes:` bo'limini qo'shing:
```yaml
    volumes:
      - /var/log/squid-filiallar:/data/squid-logs/filiallar:ro
```

Agar fayl **hali umuman yo'q** bo'lsa, to'liq yaratish uchun:
```bash
cat > docker-compose.override.yml <<'EOF'
services:
  backend:
    environment:
      ENVIRONMENT: development
      LOG_SOURCES: '[{"branch":"filiallar","path":"/data/squid-logs/filiallar/access.log"}]'
    volumes:
      - /var/log/squid-filiallar:/data/squid-logs/filiallar:ro
EOF
```

**Nima uchun bu kerak**: `LOG_SOURCES` — dashboard'ga qaysi fayl(lar)ni, qaysi nom
("filiallar") ostida ko'rsatishni aytadi. `volumes:` qatori — VM'dagi (Docker'dan
tashqarida yozilgan) faylni Docker konteyneri **ichidan ko'rinadigan** qilib beradi
(`:ro` — faqat o'qish uchun, konteyner uni o'zgartira olmaydi).

Endi qayta ishga tushiramiz:

```bash
docker compose up --build -d
```

---

## 6-QADAM — Yakuniy tekshiruv

Squid serverida (ular tomonidan) biror sayt ochilgach, bir necha soniyadan keyin:

```bash
curl http://localhost:8001/api/health
```

Natijada `log_sources` ro'yxatida shunga o'xshash yozuv ko'rinishi kerak:
```json
{"branch": "filiallar", "alive": true, "parse_failure_rate": 0.0}
```

- **`alive: true`** — VM Squid serveriga muvaffaqiyatli ulangan
- **`parse_failure_rate: 0.0`** (yoki 0'ga yaqin) — Squid'ning yozgan formati to'g'ri
  tushunilmoqda

Brauzeringizda `http://VM_IP:8082`ni oching — "Jonli hodisalar" bo'limida endi **haqiqiy**
trafik ko'rina boshlaydi.

---

## Muammo jadvali

| Belgisi | Sababi | Yechimi |
|---|---|---|
| 3-qadamda `Permission denied` | Kalit to'g'ri qo'shilmagan | 2.2-qadamni qayta tekshiring; kalitni to'liq, bo'linmasdan nusxalaganingizga ishonch hosil qiling |
| `squid-tail-filiallar` xizmati doim qayta ishga tushmoqda | Ulanish barqaror emas | `sudo journalctl -u squid-tail-filiallar -n 50 --no-pager` bilan aniq xatoni ko'ring |
| Xizmat ishlayapti, lekin `/var/log/squid-filiallar/access.log` bo'sh qoladi | Squid serverida hozircha trafik yo'q, yoki fayl o'qish huquqi yo'q | Squid serverida `tail -n 5 /var/log/squid/access.log` bajarib, o'sha hisobdan o'qib bo'lishini tekshiring |
| `alive: true`, lekin `parse_failure_rate: 1.0` | Squid noto'g'ri formatda yozyapti | 2.1-qadamni qaytadan tekshiring — **faqat shu filial**ga ta'sir qiladi, dashboard'ning qolgan qismi ishlayveradi |

Har qanday qadamda xato chiqsa — xato matnini **to'liq** nusxalab yuboring, birga hal
qilamiz.

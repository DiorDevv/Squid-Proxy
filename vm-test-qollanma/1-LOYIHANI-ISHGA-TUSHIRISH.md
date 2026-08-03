# Loyihani ishga tushirish (demo rejimda, Squid'siz)

Bu — `0-VMGA-ULANISH.md`dan keyingi qadam: Squid ulashdan oldin, dashboard'ning o'zi
to'g'ri ishlayotganini sun'iy (demo) trafik bilan tekshirib olamiz. VM'ga (tunnel bilan)
SSH orqali ulangan holda bajariladi — agar hali ulanmagan bo'lsangiz, avval
`0-VMGA-ULANISH.md`ni bajaring.

---

## 1. Kerakli dasturlarni o'rnatish

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

Qayta ulaning — pastda 4- va 6-qadamlarda kerak bo'lgani uchun, `-L` tunnel flag'lari
bilan (`0-VMGA-ULANISH.md`da tushuntirilgan):

- **Agar o'sha terminal oynasi hali ochiq** bo'lsa (`$FOYDALANUVCHI_NOMI`/`$IP_MANZIL`
  hali eslab turadi):
  ```bash
  ssh -L 8080:localhost:8080 -L 8000:localhost:8000 $FOYDALANUVCHI_NOMI@$IP_MANZIL
  ```
- **Agar yangi terminal** oynasi bo'lsa, avval qiymatlarni qayta kiriting:
  ```bash
  FOYDALANUVCHI_NOMI="root"          # <-- haqiqiy qiymatingiz bilan
  IP_MANZIL="95.123.45.67"           # <-- haqiqiy qiymatingiz bilan
  ssh -L 8080:localhost:8080 -L 8000:localhost:8000 $FOYDALANUVCHI_NOMI@$IP_MANZIL
  ```

---

## 2. Loyihani tushirish

```bash
git clone https://github.com/DiorDevv/Squid-Proxy.git ~/squid-watch
cd ~/squid-watch
cp .env.example .env
```

---

## 3. Parollarni avtomatik generatsiya qilish

```bash
POSTGRES_PW=$(openssl rand -hex 24)
JWT_SEC=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
ADMIN_PW=$(openssl rand -hex 12)
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PW|; s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SEC|; s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$ADMIN_PW|" .env
echo "Dashboard parolingiz: $ADMIN_PW"
```

**Chiqqan parolni albatta yozib/saqlab qo'ying.** Dashboard'ga kirish uchun kerak bo'ladi
(email: `admin@example.com`).

---

## 4. Ishga tushirish

```bash
docker compose --profile demo up --build -d
```

> `0-VMGA-ULANISH.md`dagi `-L 8080:localhost:8080 -L 8000:localhost:8000` bilan
> ulangan bo'lsangiz, boshqa hech qanday qo'shimcha sozlama shart emas — brauzer
> xavfsizlik cookie'si (login sessiyasini yangilab turadigan) `http://localhost` orqali
> to'g'ridan-to'g'ri ishlaydi. **`ENVIRONMENT: development` qo'shib cookie xavfsizligini
> pasaytirishga hojat yo'q** — bu, avvalgi versiyada shu yerda tavsiya qilingan bo'lsa-da,
> login sessiyasini shifrlanmagan tarmoq orqali o'g'irlashga imkon berardi. Agar biror
> sababga ko'ra tunnelsiz, to'g'ridan-to'g'ri `http://VM_IP:8080` orqali kirishni
> xohlasangiz — buni qilmang; buning o'rniga tunnel'dan foydalaning yoki haqiqiy TLS
> (HTTPS) sertifikat bilan reverse-proxy o'rnating (`README.md`'dagi "Deploying without
> Docker" bo'limiga qarang).

Birinchi marta bir necha daqiqa vaqt olishi mumkin (image'lar qurilyapti).

---

## 5. Tekshirish

```bash
docker compose ps
```

Barcha xizmatlar (`postgres`, `backend`, `frontend`, `demo-log-generator`) `running`/`healthy`
holatida bo'lishi kerak.

```bash
curl http://localhost:8000/api/health
```

Xato bo'lmasligi, `"status":"ok"` ko'rinishi kerak.

---

## 6. Brauzerda ochish

O'z kompyuteringizning brauzerida (SSH tunnel orqali):
```
http://localhost:8080
```

Kirish:
- Email: `admin@example.com`
- Parol: 3-qadamda saqlagan `ADMIN_PW`

Bir necha soniyadan keyin sun'iy (demo) trafik dashboardda ko'rina boshlaydi — jadval,
grafik, "Jonli hodisalar" ro'yxati to'lib boradi.

---

## Muammo chiqsa

```bash
docker compose logs -f backend
docker compose ps
```

Xato matnini to'liq nusxalab yuboring.

---

Shu bosqich muvaffaqiyatli o'tgach (dashboard ochilib, demo trafik ko'ringach) — keyingi
qadam **`2-SQUIDGA-ULASH-RSYSLOG.md`**: haqiqiy Squid trafigini rsyslog orqali shu
dashboard'ga ulash.

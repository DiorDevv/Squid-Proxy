# Loyihani ishga tushirish (demo rejimda, Squid'siz)

Bu — eng birinchi qadam: Squid ulashdan oldin, dashboard'ning o'zi to'g'ri ishlayotganini
sun'iy (demo) trafik bilan tekshirib olamiz. VM'ga SSH orqali ulangan holda bajariladi.

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

Qayta ulaning:
```bash
ssh FOYDALANUVCHI_NOMI@IP_MANZIL
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

Brauzer xavfsizlik cookie'sini (login sessiyasini yangilab turadigan) faqat HTTPS yoki
`http://localhost` orqali qabul qiladi — VM esa haqiqiy IP orqali (`http://VM_IP:8082`)
ochiladi, shuning uchun bitta sozlamani qo'shib qo'yamiz, aks holda login qilgach biroz
vaqtdan keyin kutilmaganda chiqib ketasiz:

```bash
cat > docker-compose.override.yml <<'EOF'
services:
  backend:
    environment:
      ENVIRONMENT: development
EOF
```

```bash
docker compose --profile demo up --build -d
```

Birinchi marta bir necha daqiqa vaqt olishi mumkin (image'lar qurilyapti).

---

## 5. Tekshirish

```bash
docker compose ps
```

Barcha xizmatlar (`postgres`, `backend`, `frontend`, `demo-log-generator`) `running`/`healthy`
holatida bo'lishi kerak.

```bash
curl http://localhost:8001/api/health
```

Xato bo'lmasligi, `"status":"ok"` ko'rinishi kerak.

---

## 6. Brauzerda ochish

O'z kompyuteringizning brauzerida:
```
http://VM_IP:8082
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
qadam Squid'ni ulash bo'ladi, bu alohida faylda beriladi.

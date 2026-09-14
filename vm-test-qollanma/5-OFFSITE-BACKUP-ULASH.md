# Off-site backup ulash — VM'dan qilinadigan ketma-ketlik

Bu qo'llanma **markaziy VM** (`~/squid-watch`, Docker Compose deployment) tomonidan
backup+arxivlarni **boshqa, alohida server**ga (off-site) `restic` orqali SFTP bilan
jo'natishni sozlaydi. Kod tomoni allaqachon tayyor (`db-offsite` servisi, commit
`087bf49`) — bu qo'llanma faqat **VM-side** qadamlarni bosqichma-bosqich yoritadi.

Quyidagi joylarda o'zingizning haqiqiy qiymatlaringizni qo'ying:

- `<TARGET_HOST>` — backup borib tushadigan boshqa serverning manzili (IP yoki domen)
- `<CENTRAL_USER>` — VM'da siz kirgan foydalanuvchi (masalan `axmadjonov`)

**Muhim:** `deploy/offsite/` papkasi `.gitignore`da — u ichidagi SSH kalit va restic
parol **`git pull` bilan avtomatik ko'chib kelmaydi**. Bu qo'llanmadagi 3-qadam ularni
VM'ning o'zida yaratadi.

---

## 1-QADAM — Kodni VM'da yangilang

```bash
cd ~/squid-watch
git fetch origin
git checkout feat/analytics-section   # yoki mos branch
git log --oneline -1                  # 087bf49 (yoki undan keyingi) borligini tasdiqlang
```

## 2-QADAM — Target serverda alohida foydalanuvchi tayyorlang

Backup borib tushadigan boshqa serverda (login-akkaunt emas, faqat shu ish uchun):

```bash
sudo useradd -m -s /usr/sbin/nologin squidoffsite
sudo install -d -o squidoffsite -g squidoffsite /srv/squid-watch-offsite
```

## 3-QADAM — VM'da yangi SSH keypair va restic parol yarating

```bash
cd ~/squid-watch
mkdir -p deploy/offsite/ssh
ssh-keygen -t ed25519 -N "" -f deploy/offsite/ssh/id_ed25519 -C squid-watch-offsite
chmod 600 deploy/offsite/ssh/id_ed25519
python3 -c "import secrets; print(secrets.token_urlsafe(48))" > deploy/offsite/restic-password
chmod 600 deploy/offsite/restic-password
```

Parolsiz (`-N ""`) kalit — chunki `db-offsite` kuzatuvsiz, avtomatik ishlaydi, hech kim
o'tirib passphrase kiritmaydi. Kalitni boshqa hech qayerda (masalan filial `squidreader`
kalitlari bilan) qayta ishlatmang.

## 4-QADAM — Ochiq kalitni target serverga o'rnating

```bash
ssh-copy-id -i deploy/offsite/ssh/id_ed25519.pub squidoffsite@<TARGET_HOST>
```

`ssh-copy-id` yo'q bo'lsa, `deploy/offsite/ssh/id_ed25519.pub` faylining tarkibini
target serverdagi `/home/squidoffsite/.ssh/authorized_keys`ga qo'lda joylashtiring.

## 5-QADAM — `known_hosts`ni oldindan to'ldiring

```bash
ssh-keyscan -H <TARGET_HOST> >> deploy/offsite/ssh/known_hosts
```

Bu — VM'ning o'zida, konteynerdan tashqarida bajarilishi shart (`db-offsite`
konteynerida `/root/.ssh` **read-only** mount qilingan, ichkaridan yozib bo'lmaydi).
Aks holda birinchi ulanishda "yes/no" so'raladi, konteyner esa buni tasdiqlay olmaydi.

## 6-QADAM — Ulanishni sinang

```bash
ssh -i deploy/offsite/ssh/id_ed25519 squidoffsite@<TARGET_HOST> "echo OK"
```

`OK` chiqsa — kalit va `known_hosts` to'g'ri sozlangan.

## 7-QADAM — `.env`ga qo'shing

```
OFFSITE_RESTIC_REPOSITORY=sftp:squidoffsite@<TARGET_HOST>:/srv/squid-watch-offsite
OFFSITE_RESTIC_PASSWORD_FILE=/offsite-config/restic-password
```

(`OFFSITE_INTERVAL_SECONDS`/`OFFSITE_KEEP_*` — default qiymatlar yetarli: kuniga bir
marta, 7 kunlik/8 haftalik/12 oylik saqlash.)

## 8-QADAM — Servisni ishga tushiring

```bash
docker compose up -d db-backup db-offsite
```

Birinchi ishga tushishda repository avtomatik `restic init` bo'ladi, so'ng darhol
birinchi sinxronlash boshlanadi.

## 9-QADAM — Tekshiring

```bash
docker compose logs -f db-offsite
docker compose exec backend cat /app/job_status/offsite.json
docker compose exec db-offsite restic -r "$OFFSITE_RESTIC_REPOSITORY" \
  --password-file /offsite-config/restic-password snapshots
```

`last_sync_ok: true` va `snapshots` ro'yxatida kamida bitta yozuv ko'rinsa — off-site
backup ishlayapti. Xuddi shu status **Settings → System Health** sahifasida ham
ko'rinadi.

## 10-QADAM — Parolni off-box saqlang

`deploy/offsite/restic-password` mazmunini **darhol** parol menejeriga yoki alohida
maxfiy joyga ko'chiring. Bu parol yo'qolsa, off-site nusxa umuman tiklab bo'lmaydigan
holga keladi — diskning o'zi buzilganda ham, backup ham o'qib bo'lmaydi.

## 11-QADAM — (tavsiya etiladi) Tiklashni sinab ko'ring

Hozirgacha bu loyihada restore hech qachon amalda sinalmagan. Bir marta qo'lda
tekshiring:

```bash
restic -r "$OFFSITE_RESTIC_REPOSITORY" --password-file deploy/offsite/restic-password \
  restore latest --target /tmp/restore-test
```

Fayllar chiqib kelsa — off-site nusxa nafaqat yozilyapti, balki **haqiqatan tiklanadigan**.

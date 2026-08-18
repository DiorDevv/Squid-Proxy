# Yangi filial qo'shish — SSH-pull orqali

Bu qo'llanma **allaqachon kamida bitta filial SSH-pull usulida (`squid-ssh-stream@...`)
ulangan** holatdan boshlanadi. Maqsad — shu usulda **yana bir** filialni qo'shish.

Quyidagi joylarda o'zingizning haqiqiy qiymatlaringizni qo'ying:

- `<YANGI_FILIAL>` — filial nomi (masalan `bosh_ofis`, faqat harf/raqam/`_`, bo'shliqsiz)
- `<FILIAL_IP>` — yangi filialning Squid serveri IP manzili
- `<CENTRAL_USER>` — markaziy (dashboard) serverda siz kirgan foydalanuvchi nomi
- `<SQUID_LOG_KATALOGI>` — markaziy serverda mahalliy loglar saqlanadigan katalog (mavjud
  filial(lar) uchun qaysi katalogni ishlatgan bo'lsangiz, xuddi shuni davom ettiring)

---

## 1-QADAM — Yangi filial uchun alohida SSH kalit yarating (markaziy serverda)

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_rsa_squidreader_<YANGI_FILIAL>
```

Har bir filial uchun **alohida** kalit yarating — bitta kalit o'g'irlansa, faqat o'sha
bitta filial xavf ostida qoladi, qolganlari emas.

## 2-QADAM — Filial Squid serverida kalitni cheklab qo'shing

Filial serverida, log o'qish uchun ajratilgan hisobning (masalan `squidreader`)
`~/.ssh/authorized_keys` fayliga, **bitta qatorda**, quyidagini qo'shing:

```
command="tail -F /var/log/squid/access.log",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA...
```

(`AAAA...` — 1-qadamda yaratilgan `.pub` faylning tarkibi). Bu — kalit o'g'irlansa ham,
u orqali **faqat** shu bitta `tail` buyrug'ini ishlatish mumkin, boshqa hech narsa
(shell, port-forward va h.k.) ishlamaydi.

## 3-QADAM — Markaziy serverda env fayl yarating

```bash
sudo mkdir -p /etc/squid-ssh-stream
sudo cp deploy/systemd/squid-ssh-stream.env.example /etc/squid-ssh-stream/<YANGI_FILIAL>.env
sudo nano /etc/squid-ssh-stream/<YANGI_FILIAL>.env
```

To'ldiring:

| O'zgaruvchi | Qiymat |
|---|---|
| `SSH_KEY_PATH` | `/home/<CENTRAL_USER>/.ssh/id_rsa_squidreader_<YANGI_FILIAL>` |
| `SQUID_SSH_USER` | filial serveridagi log-o'quvchi hisob (masalan `squidreader`) |
| `SQUID_SSH_HOST` | `<FILIAL_IP>` |
| `SQUID_ACCESS_LOG_PATH` | filial serveridagi asl log yo'li (masalan `/var/log/squid/access.log`) |
| `LOCAL_LOG_PATH` | `<SQUID_LOG_KATALOGI>/<YANGI_FILIAL>.log` — **mavjud filial(lar)ning fayli turgan xuddi shu katalog**, shunda logrotate ularni avtomatik qamrab oladi |

## 4-QADAM — Xizmatni ishga tushiring

```bash
sudo cp deploy/systemd/squid-ssh-stream@.service /etc/systemd/system/   # allaqachon bo'lsa, shart emas
sudo systemctl daemon-reload
sudo systemctl enable --now squid-ssh-stream@<YANGI_FILIAL>
sudo systemctl status squid-ssh-stream@<YANGI_FILIAL> --no-pager
```

## 5-QADAM — Backend'ga yangi filialni tanishtiring

`.env` faylida `LOG_SOURCES`ga yangi yozuv qo'shing (mavjud filial(lar)ni ham saqlab
qoling, faqat vergul bilan ajratib yangisini qo'shing):

```
LOG_SOURCES=[{"branch":"mavjud_filial","path":"<SQUID_LOG_KATALOGI>/mavjud_filial.log"},{"branch":"<YANGI_FILIAL>","path":"<SQUID_LOG_KATALOGI>/<YANGI_FILIAL>.log"}]
```

Backend'ni qayta ishga tushiring (Docker bo'lsa `docker compose restart backend`).

## 6-QADAM — Tekshirish

```bash
curl -s http://localhost:8000/api/health | grep -A5 log_sources
```

Yangi filial `parse_failure_rate: 0` (yoki `0`ga yaqin) bilan ko'rinishi kerak. Agar
doim `1.0` bo'lsa — filial serverining Squid logformat sozlamasi noto'g'ri (asosiy
`README.md`'dagi "Required Squid configuration" bo'limiga qarang), transport muammosi
emas.

Dashboard'da yuqoridagi filial-tanlagichda yangi filial paydo bo'lishi, va unga tegishli
trafik ko'rina boshlashi kerak.

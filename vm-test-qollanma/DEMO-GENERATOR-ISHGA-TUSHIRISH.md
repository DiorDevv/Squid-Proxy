# Demo log generatorni mustaqil (Docker'siz) ishga tushirish va to'xtatish

`backend/scripts/generate_demo_log.py` — sun'iy Squid trafigini yozadigan skript. Odatda
`docker compose --profile demo up` orqali avtomatik ishga tushadi, lekin uni **alohida,
Docker'siz** ham ishga tushirish mumkin. Hech qanday qo'shimcha kutubxona kerak emas
(faqat Python standart kutubxonasi).

---

## Ishga tushirish

### Oldingi planda (terminal band bo'ladi)

```bash
cd ~/squid-watch/backend
python3 scripts/generate_demo_log.py --output /tmp/access.log --rate 30
```

Log qatorlari real vaqtda shu yerda ko'rinib turadi.

### Fonda (background, terminal band bo'lmaydi)

```bash
cd ~/squid-watch/backend
nohup python3 scripts/generate_demo_log.py --output /tmp/access.log --rate 30 > /tmp/demo-gen.log 2>&1 &
```

Ishga tushgach, jarayon raqami (PID) ko'rsatiladi, masalan `[1] 12345`.

### Parametrlar

| Parametr | Ma'nosi | Standart |
|---|---|---|
| `--output` | Qayerga yozish | `./access.log` |
| `--rate` | Soniyasiga o'rtacha nechta qator | `30` |
| `--malformed-rate` | Qanchasi ataylab noto'g'ri formatda (parser sinovi uchun) | `0.01` |
| `--duration` | Necha soniyadan keyin to'xtaydi (bo'sh — cheksiz ishlaydi) | cheksiz |

Masalan, 5 daqiqa davomida, soniyasiga 50 qator:
```bash
python3 scripts/generate_demo_log.py --output /tmp/access.log --rate 50 --duration 300
```

---

## To'xtatish

**Oldingi planda ishlagan bo'lsa**: `Ctrl+C`.

**Fonda ishlagan bo'lsa**:
```bash
pkill -f generate_demo_log.py
```

Yoki avval tekshirib, keyin to'xtatish:
```bash
ps aux | grep generate_demo_log.py
kill PID_RAQAMI
```

---

## Eslatma

Bu skript **faqat faylga yozadi** — dashboard bilan o'zi bog'lanmaydi. Dashboard shu
faylni ko'rishi uchun, `.env` faylidagi `LOG_FILE_PATH` shu faylning yo'liga ishora
qilishi kerak (masalan `/tmp/access.log`), yoki agar Docker orqali ishlatilsa,
`docker-compose.override.yml`da tegishli `volumes:`/`LOG_SOURCES` sozlanishi kerak — bu
alohida qadam, `1-LOYIHANI-ISHGA-TUSHIRISH.md`da Docker orqali avtomatik bajariladi.

# Real Squid'ni dashboard'ga ulash — rsyslog orqali

Bu qo'llanma **dashboard allaqachon VM'da ishlab turgan** holatdan boshlanadi. Maqsad —
boshqa serverda ishlayotgan Squid'ning haqiqiy trafigini, `rsyslog` orqali, shifrlangan
tarzda dashboard'ga yetkazish.

**Muhim**: bu qo'llanmadagi deyarli barcha amallar — VM'ning **tizim darajasida**
(`/etc/...`), loyiha kodiga (`~/squid-watch` ichidagi fayllarga) **tegmaydi**. Faqat
oxirgi qadamda, bitta gitignored faylga (hech qachon `git`ga aralashmaydigan) ozgina
yoziladi.

---

## Umumiy chizma

```
[Filial server — Squid shu yerda]          [Markaziy server — VM, dashboard shu yerda]
                                              
Squid → access.log yozadi                    
    │                                        
rsyslog (jo'natuvchi) — faylni kuzatadi,      rsyslog (qabul qiluvchi) — 6514-portda
yangi qator kelishi bilan darhol,      ──→    "tinglab" turadi, sertifikati to'g'ri
o'zi, shifrlangan tarzda jo'natadi            kelganlardan qabul qilib, mahalliy
                                               faylga yozadi
                                                    │
                                               Dashboard — shu mahalliy faylni o'qiydi
```

Squid'ning IP manzili faqat **filial tomonidagi** rsyslog sozlamasida kerak (qayerga
jo'natishni bilish uchun). Dashboard va markaziy rsyslog Squid'ning IP'ini bilishi shart
emas.

---

## 1-QADAM — Sertifikatlar yaratish (VM'da)

Bu — ikkala tomon bir-birini "tanishi" uchun kerak. `~/squid-watch` papkasidan
**tashqarida**, alohida joyda yaratamiz:

```bash
mkdir -p ~/squid-certs && cd ~/squid-certs
```

```bash
openssl genrsa -out ca-key.pem 4096
openssl req -x509 -new -nodes -key ca-key.pem -sha256 -days 3650 \
  -subj "/CN=SquidWatch CA" -out ca.pem
```

```bash
openssl genrsa -out central-key.pem 4096
openssl req -new -key central-key.pem -subj "/CN=central.squidwatch.local" -out central.csr
openssl x509 -req -in central.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out central.pem -days 825 -sha256
```

```bash
openssl genrsa -out branch-key.pem 4096
openssl req -new -key branch-key.pem -subj "/CN=branch-filiallar.squidwatch.local" -out branch.csr
openssl x509 -req -in branch.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out branch.pem -days 825 -sha256
```

Tekshirish:
```bash
ls ~/squid-certs/*.pem
```

**5 ta** `.pem` fayl chiqishi kerak: `ca.pem`, `central.pem`, `central-key.pem`,
`branch.pem`, `branch-key.pem`. Oxirgi 3 tasi (`ca.pem`, `branch.pem`,
`branch-key.pem`) keyingi qadamda Squid serveriga (xavfsiz kanal orqali) uzatiladi.

---

## 2-QADAM — Markaziy serverni sozlash (VM'da)

```bash
sudo apt update
sudo apt install -y rsyslog rsyslog-gnutls
```

```bash
sudo mkdir -p /etc/rsyslog.d/certs /var/log/squid
sudo cp ~/squid-certs/ca.pem ~/squid-certs/central.pem ~/squid-certs/central-key.pem \
        /etc/rsyslog.d/certs/
```

Qabul qiluvchi konfiguratsiyasini yaratamiz (to'liq tayyor, o'zgartirish shart emas):

```bash
sudo tee /etc/rsyslog.d/60-squid-receive.conf > /dev/null <<'EOF'
module(load="imtcp"
  StreamDriver.Name="gtls"
  StreamDriver.Mode="1"
  StreamDriver.AuthMode="x509/name"
  StreamDriver.PermittedPeer=["branch-filiallar.squidwatch.local"]
)

global(
  DefaultNetstreamDriverCAFile="/etc/rsyslog.d/certs/ca.pem"
  DefaultNetstreamDriverCertFile="/etc/rsyslog.d/certs/central.pem"
  DefaultNetstreamDriverKeyFile="/etc/rsyslog.d/certs/central-key.pem"
)

input(type="imtcp" port="6514")

template(name="squidRawLine" type="string" string="%msg%\n")
template(name="squidBranchFile" type="string" string="/var/log/squid/%programname:7:$%.log")

if $programname startswith "squid-" then {
  action(type="omfile" DynaFile="squidBranchFile" template="squidRawLine" fileCreateMode="0644")
  stop
}
EOF
```

```bash
sudo tee /etc/logrotate.d/squid-branches > /dev/null <<'EOF'
/var/log/squid/*.log {
  daily
  rotate 14
  compress
  delaycompress
  missingok
  notifempty
  copytruncate
}
EOF
```

```bash
sudo systemctl restart rsyslog
sudo systemctl status rsyslog --no-pager
```

`active (running)` bo'lishi kerak, qizil xato bo'lmasligi kerak.

**Firewall** (agar `ufw` ishlatilsa) — filial serverining IP'i ma'lum bo'lgach:
```bash
sudo ufw allow from FILIAL_SERVER_IP to any port 6514 proto tcp
```

---

## 3-QADAM — Squid serveriga yuborish

Squid serverini boshqaradigan odamga **shu qismni to'liq nusxalab yuboring**, va
`~/squid-certs/ca.pem`, `branch.pem`, `branch-key.pem` fayllarini xavfsiz kanal orqali
(email emas — SCP yoki shifrlangan xabar) alohida uzating.

> **Sizning serveringizda quyidagilarni bajaring:**
>
> ### 3.1 — Log formatini tekshiring
> ```bash
> grep access_log /etc/squid/squid.conf
> ```
> Natija oxirida `squid` so'zi bilan tugashi kerak
> (`access_log /var/log/squid/access.log squid`). Boshqacha bo'lsa — tuzatib,
> `sudo systemctl reload squid`.
>
> ### 3.2 — rsyslog o'rnatish
> ```bash
> sudo apt update
> sudo apt install -y rsyslog rsyslog-gnutls
> sudo mkdir -p /etc/rsyslog.d/certs
> ```
> Sizga yuborilgan `ca.pem`, `branch.pem`, `branch-key.pem` fayllarini
> `/etc/rsyslog.d/certs/` papkasiga joylashtiring.
>
> ### 3.3 — Jo'natuvchi konfiguratsiyasi
> `CENTRAL_HOST_IP` o'rniga menga (dashboard operatoriga) tegishli serverning haqiqiy IP
> manzilini yozib, shu blokni to'liq bajaring:
> ```bash
> sudo tee /etc/rsyslog.d/60-squid-forward.conf > /dev/null <<'EOF'
> module(load="imfile" mode="inotify")
>
> global(
>   workDirectory="/var/spool/rsyslog"
> )
>
> input(
>   type="imfile"
>   File="/var/log/squid/access.log"
>   Tag="squid-filiallar:"
>   Severity="info"
>   Facility="local1"
>   PersistStateInterval="200"
> )
>
> global(
>   DefaultNetstreamDriver="gtls"
>   DefaultNetstreamDriverCAFile="/etc/rsyslog.d/certs/ca.pem"
>   DefaultNetstreamDriverCertFile="/etc/rsyslog.d/certs/branch.pem"
>   DefaultNetstreamDriverKeyFile="/etc/rsyslog.d/certs/branch-key.pem"
> )
>
> if $syslogtag startswith "squid-filiallar:" then {
>   action(
>     type="omfwd"
>     target="CENTRAL_HOST_IP"
>     port="6514"
>     protocol="tcp"
>     StreamDriver="gtls"
>     StreamDriverMode="1"
>     StreamDriverAuthMode="x509/name"
>     StreamDriverPermittedPeers="central.squidwatch.local"
>
>     queue.type="linkedlist"
>     queue.filename="squid_fwd_filiallar"
>     queue.maxdiskspace="2g"
>     queue.saveOnShutdown="on"
>     queue.spoolDirectory="/var/spool/rsyslog"
>     action.resumeRetryCount="-1"
>     action.resumeInterval="10"
>   )
>   stop
> }
> EOF
> ```
> ```bash
> sudo mkdir -p /var/spool/rsyslog
> sudo systemctl restart rsyslog
> sudo systemctl status rsyslog --no-pager
> ```
> `active (running)` bo'lishi kerak. Tayyor bo'lgach, tasdiqlab xabar bering.
>
> **Firewall**: chiquvchi TCP `6514` portga ruxsat kerak (odatda standart holatda
> ochiq).

---

## 4-QADAM — Dashboard'ni ulash (VM'da)

**Diqqat**: sizda `docker-compose.override.yml` fayli allaqachon bor (login muammosini
tuzatish uchun `ENVIRONMENT: development` qo'shilgan). Uni **butunlay almashtirmang**,
faqat kerakli qatorlarni qo'shing:

```bash
cd ~/squid-watch
cat docker-compose.override.yml
```

Faylni oching:
```bash
nano docker-compose.override.yml
```

Va `environment:` ostiga (mavjud `ENVIRONMENT: development` qatoridan keyin) shuni
qo'shing:
```yaml
      LOG_SOURCES: '[{"branch":"filiallar","path":"/data/squid-logs/filiallar.log"}]'
```

`backend:` ostiga (agar `volumes:` bo'limi hali yo'q bo'lsa) shuni qo'shing:
```yaml
    volumes:
      - /var/log/squid:/data/squid-logs:ro
```

Fayl **to'liq** shunga o'xshash ko'rinishi kerak (aniq tuzilishi joriy holatingizga
bog'liq — noaniqlik bo'lsa, `cat docker-compose.override.yml` natijasini menga yuboring,
men aniq qanday tahrirlashni ko'rsataman):

```yaml
services:
  backend:
    environment:
      ENVIRONMENT: development
      LOG_SOURCES: '[{"branch":"filiallar","path":"/data/squid-logs/filiallar.log"}]'
    volumes:
      - /var/log/squid:/data/squid-logs:ro
```

Saqlab, qayta ishga tushiring:
```bash
docker compose up --build -d
```

---

## 5-QADAM — Yakuniy tekshiruv

Squid serverida (ular tomonidan) biror sayt ochilgach:

```bash
sudo journalctl -u rsyslog -n 30 --no-pager
ls -la /var/log/squid/
```

`filiallar.log` fayli paydo bo'lishi kerak. So'ng:

```bash
curl http://localhost:8001/api/health
```

Natijada:
```json
"log_sources": [{"branch": "filiallar", "alive": true, "parse_failure_rate": 0.0}]
```

`alive: true` va `parse_failure_rate` `0`ga yaqin — hammasi to'g'ri ishlayapti.
Brauzerda `http://VM_IP:8082`ni oching — "Jonli hodisalar"da haqiqiy trafik ko'rinadi.

---

## Muammo jadvali

| Belgisi | Sababi | Yechimi |
|---|---|---|
| `filiallar.log` paydo bo'lmayapti | Fayl markaziy serverga kelmayapti | Ikkala tomonda `sudo journalctl -u rsyslog -n 50 --no-pager` bilan TLS xatosini qidiring |
| TLS handshake xatosi | Sertifikat nomlari mos kelmayapti | 1-qadamdagi `-subj "/CN=..."` nomlari va `PermittedPeer`/`StreamDriverPermittedPeers` bir xil ekanini tekshiring |
| `alive: true`, lekin `parse_failure_rate: 1.0` | Squid noto'g'ri formatda yozyapti | 3.1-qadamni qaytadan tekshiring |
| Fayl bor, dashboard ko'rmayapti | Fayl ruxsati | `sudo chmod o+r /var/log/squid/filiallar.log` |

Har qanday qadamda xato chiqsa — xato matnini **to'liq** nusxalab yuboring.

---

## Keyinroq yana filial qo'shish kerak bo'lsa

Masalan "bosh_ofis" nomli yangi filial qo'shish uchun, yuqoridagi qadamlarni takrorlaysiz,
faqat har joyda `filiallar` → `bosh_ofis` deb almashtirasiz:

- 1-QADAM: yana bitta sertifikat juftligi (`branch-bosh_ofis.pem`/`-key.pem`)
- 2-QADAM: markaziy `PermittedPeer` ro'yxatiga yangi hostname qo'shiladi (vergul bilan)
- 4-QADAM: `LOG_SOURCES`ga yana bitta `{"branch":"bosh_ofis",...}` yozuvi va `volumes`da
  o'zgarish shart emas (`/var/log/squid` papkasi umumiy — barcha filiallarning fayllari
  shu bitta papkada, nomi bilan farqlanadi)
- 3-QADAM: yangi filial serveriga xuddi shu ko'rsatma, `filiallar` o'rniga `bosh_ofis` bilan

Bu qadamlarni kerak bo'lganda to'liq tayyor holda so'rab oling.

# Real Squid'ni dashboard'ga ulash — rsyslog orqali

Bu qo'llanma **dashboard allaqachon VM'da ishlab turgan** holatdan boshlanadi (agar hali
ishga tushirmagan bo'lsangiz, avval `1-LOYIHANI-ISHGA-TUSHIRISH.md`ni bajaring). Maqsad —
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

**Firewall** (agar `ufw` ishlatilsa) — filial serverining IP'i ma'lum bo'lgach, shu ikki
qatorni to'ldirib bajaring (1-qator — haqiqiy qiymat bilan, 2-qator o'zgarishsiz):
```bash
FILIAL_SERVER_IP="203.0.113.10"          # <-- filial (Squid) serverining haqiqiy IP'i
sudo ufw allow from $FILIAL_SERVER_IP to any port 6514 proto tcp
```

---

## 3-QADAM — Squid serverida bajarish

**Agar Squid serverini boshqa odam boshqarsa**: shu bo'limni (3.1–3.3) to'liq nusxalab
unga yuboring, va `~/squid-certs/ca.pem`, `branch.pem`, `branch-key.pem` fayllarini
xavfsiz kanal orqali (email emas — SCP yoki shifrlangan xabar) alohida uzating.

**Agar Squid serverini SIZ o'zingiz boshqarsangiz** (masalan, hozir shu holatdasiz): bu
qadamlar **VM'da emas, Squid serverida** bajariladi, shuning uchun avval o'sha serverga
**yangi, alohida terminal oynasida** SSH bilan ulaning (hozirgi VM sessiyangizni
yopmang — u kerak bo'lib turadi):

```bash
ssh FOYDALANUVCHI@SQUID_SERVER_IP
```

(`FOYDALANUVCHI`/`SQUID_SERVER_IP` — Squid serveringizning haqiqiy foydalanuvchi
nomi/IP'i, `0-VMGA-ULANISH.md`dagi kabi tunnel flag'lari (`-L ...`) bu yerda **kerak
emas** — bu server dashboard'ni ishga tushirmaydi.)

Sertifikat fayllarini (`~/squid-certs/ca.pem`, `branch.pem`, `branch-key.pem`) VM'dan
Squid serveriga xavfsiz nusxalash uchun, **VM'dagi** terminalda (Squid serveridagida
emas) shu buyruqni bajaring:

```bash
scp ~/squid-certs/ca.pem ~/squid-certs/branch.pem ~/squid-certs/branch-key.pem \
  FOYDALANUVCHI@SQUID_SERVER_IP:~/
```

Endi Squid serveridagi terminalda (yuqorida ulangan) davom eting:

> **Squid serverida quyidagilarni bajaring:**
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
> Sizga yuborilgan (yoki o'zingiz `scp` bilan ko'chirgan) `ca.pem`, `branch.pem`,
> `branch-key.pem` fayllari — agar yuqoridagi `scp` buyrug'i bilan ko'chirgan bo'lsangiz,
> `~/` (uy papkasi)da turadi. Ularni to'g'ri joyga ko'chiring:
> ```bash
> sudo cp ~/ca.pem ~/branch.pem ~/branch-key.pem /etc/rsyslog.d/certs/
> ```
>
> ### 3.3 — Jo'natuvchi konfiguratsiyasi
> Avval shu birinchi qatorni **dashboard operatoridan olingan haqiqiy IP bilan**
> to'ldiring, qolgan hammasini (heredoc va undan keyingi `sed` qatorini) o'zgartirmasdan,
> aynan shunday nusxalab bajaring — `sed` qatori faylning ichidagi `CENTRAL_HOST_IP`
> so'zini siz kiritgan haqiqiy IP'ga avtomatik almashtiradi:
> ```bash
> CENTRAL_HOST_IP="203.0.113.5"          # <-- dashboard operatoridan olingan haqiqiy IP
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
> sudo sed -i "s/CENTRAL_HOST_IP/$CENTRAL_HOST_IP/" /etc/rsyslog.d/60-squid-forward.conf
> ```
> (Nega alohida `sed` qatori kerak: heredoc ichida rsyslog'ning o'zining `$syslogtag` kabi
> yozuvlari bor, ular bilan chalkashmasligi uchun heredoc o'zgaruvchisiz — o'zgarmas —
> holda yoziladi, `CENTRAL_HOST_IP` esa shu qo'shimcha qator bilan, faylni yaratib
> bo'lgandan keyin almashtiriladi.)
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

```bash
cd ~/squid-watch
```

Odatda bu bosqichda `docker-compose.override.yml` fayli **hali yo'q** (`1-LOYIHANI-ISHGA-TUSHIRISH.md` uni yaratmaydi — demo rejimi hech qanday override'siz ishlaydi). Shuni tekshirib ko'ring:

```bash
ls docker-compose.override.yml 2>/dev/null && echo "BOR" || echo "YO'Q"
```

**Agar "YO'Q" chiqsa** (odatiy holat) — to'liq yaratib qo'ying:
```bash
cat > docker-compose.override.yml <<'EOF'
services:
  backend:
    environment:
      LOG_SOURCES: '[{"branch":"filiallar","path":"/data/squid-logs/filiallar.log"}]'
    volumes:
      - /var/log/squid:/data/squid-logs:ro
EOF
```

**Agar "BOR" chiqsa** (masalan boshqa filial uchun avval sozlagan bo'lsangiz) — uni
**butunlay almashtirmang**, faqat kerakli qatorlarni qo'shing:
```bash
nano docker-compose.override.yml
```
`environment:` ostiga:
```yaml
      LOG_SOURCES: '[{"branch":"filiallar","path":"/data/squid-logs/filiallar.log"}]'
```
`backend:` ostiga (agar `volumes:` bo'limi hali yo'q bo'lsa):
```yaml
    volumes:
      - /var/log/squid:/data/squid-logs:ro
```
(Noaniqlik bo'lsa, `cat docker-compose.override.yml` natijasini menga yuboring, men
aniq qanday tahrirlashni ko'rsataman.)

Ikkala holatda ham, saqlab, qayta ishga tushiring:
```bash
docker compose up --build -d
```

---

## 5-QADAM — Yakuniy tekshiruv

Squid serverida (o'zingiz yoki uni boshqaradigan odam tomonidan) biror sayt ochilgach:

```bash
sudo journalctl -u rsyslog -n 30 --no-pager
ls -la /var/log/squid/
```

`filiallar.log` fayli paydo bo'lishi kerak. So'ng:

```bash
curl http://localhost:8000/api/health
```

Natijada:
```json
"log_sources": [{"branch": "filiallar", "alive": true, "parse_failure_rate": 0.0}]
```

`alive: true` va `parse_failure_rate` `0`ga yaqin — hammasi to'g'ri ishlayapti.
Brauzerda (SSH tunnel orqali) `http://localhost:8080`ni oching — "Jonli hodisalar"da
haqiqiy trafik ko'rinadi.

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

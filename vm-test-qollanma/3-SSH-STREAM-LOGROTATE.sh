#!/bin/sh
# proxyanalyzer VM uchun tayyor skript -- squid-ssh-stream@filiallar.service
# yozayotgan mahalliy log faylini (LOCAL_LOG_PATH) har kuni aylantirish
# uchun. Qiymatlar allaqachon to'ldirilgan:
#   User: axmadjonov
#   LOCAL_LOG_PATH: /home/axmadjonov/squid-watch/ssh-logs/filiallar.log
#
# Ishlatish (VM'da, `git pull` qilgandan keyin):
#   sudo sh vm-test-qollanma/3-SSH-STREAM-LOGROTATE.sh
#
# Nima qiladi: /etc/logrotate.d/squid-ssh-stream faylini yaratadi, so'ng
# sinab ko'radi (haqiqatan aylantirmasdan). Hozir ishlab turgan log
# oqimiga tegmaydi, restart talab qilmaydi -- logrotate ertadan boshlab
# o'z holicha (kuniga bir marta) ishga tushadi.

set -e

cat > /etc/logrotate.d/squid-ssh-stream <<'EOF'
/home/axmadjonov/squid-watch/ssh-logs/*.log {
    daily
    rotate 14
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
}
EOF

echo "Yozildi: /etc/logrotate.d/squid-ssh-stream"
echo "Sinov (-d = haqiqatan aylantirmasdan tekshirish):"
logrotate -d /etc/logrotate.d/squid-ssh-stream

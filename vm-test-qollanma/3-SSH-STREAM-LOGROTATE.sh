#!/bin/sh
# proxyanalyzer VM uchun tayyor skript -- squid-ssh-stream@filiallar.service
# yozayotgan mahalliy log faylini (LOCAL_LOG_PATH) har kuni aylantirish
# uchun. Qiymatlar allaqachon to'ldirilgan:
#   LOCAL_LOG_PATH: /home/axmadjonov/squid-watch/ssh-logs/filiallar.log
#
# `su root root`: squid-ssh-stream@filiallar hozircha (systemd hardening
# hali qo'llanmagani uchun) root sifatida ishlayapti -- shuning uchun
# filiallar.log root'ga tegishli. Agar keyinchalik squid-ssh-stream@
# .service'ga User=axmadjonov qo'shilsa (hardening qo'llansa), bu faylni
# qayta ishga tushirishdan oldin quyidagi qatorni
# "su axmadjonov axmadjonov" ga o'zgartiring -- aks holda fayl
# egaligi bilan mos kelmay, aylantirish "Permission denied" bilan
# muvaffaqiyatsiz tugaydi.
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
    su root root
}
EOF

echo "Yozildi: /etc/logrotate.d/squid-ssh-stream"
echo "Sinov (-d = haqiqatan aylantirmasdan tekshirish):"
logrotate -d /etc/logrotate.d/squid-ssh-stream

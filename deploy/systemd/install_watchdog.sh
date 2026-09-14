#!/bin/bash
# One-shot installer for squid-ssh-stream-watchdog -- see
# squid-ssh-stream-watchdog.sh's own header for what it does and why. Run
# this ON THE CENTRAL/DASHBOARD VM (where squid-ssh-stream@<branch>
# instances run), as root or via sudo. Safe to re-run: copies + enables
# are idempotent, and it triggers one immediate check at the end so a
# branch that's already wedged gets fixed right away instead of waiting
# for the first 5-minute tick.
#
# Usage (from the repo root, e.g. ~/squid-watch):
#   sudo deploy/systemd/install_watchdog.sh

set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo: sudo $0" >&2
  exit 1
fi

cd "$(dirname "$0")"

install -m 755 squid-ssh-stream-watchdog.sh /usr/local/bin/squid-ssh-stream-watchdog.sh
install -m 644 squid-ssh-stream-watchdog.service /etc/systemd/system/squid-ssh-stream-watchdog.service
install -m 644 squid-ssh-stream-watchdog.timer /etc/systemd/system/squid-ssh-stream-watchdog.timer

systemctl daemon-reload
systemctl enable --now squid-ssh-stream-watchdog.timer

echo "Installed. Running one check now (covers every branch under /etc/squid-ssh-stream/*.env)..."
systemctl start squid-ssh-stream-watchdog.service
sleep 2
journalctl -u squid-ssh-stream-watchdog.service -n 5 --no-pager

echo
echo "Done. Runs automatically every 5 minutes from now on:"
echo "  systemctl list-timers squid-ssh-stream-watchdog.timer"
echo "  journalctl -u squid-ssh-stream-watchdog.service -f"

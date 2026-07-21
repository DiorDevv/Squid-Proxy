#!/usr/bin/env bash
# One-VM local sanity test for the branch -> central rsyslog transport
# (see README.md's "Multi-branch deployment" section and deploy/rsyslog/
# branch.conf / central.conf, which this script wraps).
#
# Runs BOTH the "branch" and "central" rsyslog roles on the same machine,
# talking to each other over 127.0.0.1 -- validates the config logic
# (TLS, tag-based routing, file output) without needing real network/
# firewall setup between separate servers. It does NOT test cross-server
# firewall/hostname issues -- that's the next step, with a real branch (see
# README.md's "Rollout checklist").
#
# Run this on a disposable test VM, NOT your main machine -- it installs
# system packages and writes to /etc/rsyslog.d/.
#
# Usage: run from the repo root:
#   bash deploy/rsyslog/test-single-vm.sh
#
# Idempotent: safe to re-run (overwrites its own certs/configs each time).

set -euo pipefail

BRANCH_TAG="tashkent"
CERT_DIR="/etc/rsyslog.d/certs"
WORK_DIR="$(mktemp -d)"
BRANCH_ACCESS_LOG="/var/log/squid/access.log"
CENTRAL_BRANCH_LOG="/var/log/squid/${BRANCH_TAG}.log"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "==> [1/7] Installing packages (rsyslog, rsyslog-gnutls, openssl)"
sudo apt-get update -qq
sudo apt-get install -y -qq rsyslog rsyslog-gnutls openssl >/dev/null

echo "==> [2/7] Generating a scratch CA + central/branch certs (CN=localhost) in $WORK_DIR"
pushd "$WORK_DIR" >/dev/null

openssl genrsa -out ca-key.pem 4096 2>/dev/null
openssl req -x509 -new -nodes -key ca-key.pem -sha256 -days 3650 \
  -subj "/CN=SquidWatch Test CA" -out ca.pem 2>/dev/null

openssl genrsa -out central-key.pem 4096 2>/dev/null
openssl req -new -key central-key.pem -subj "/CN=localhost" -out central.csr 2>/dev/null
openssl x509 -req -in central.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -days 825 -out central.pem -extfile <(printf "subjectAltName=DNS:localhost") 2>/dev/null

openssl genrsa -out branch-key.pem 4096 2>/dev/null
openssl req -new -key branch-key.pem -subj "/CN=localhost" -out branch.csr 2>/dev/null
openssl x509 -req -in branch.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -days 825 -out branch.pem -extfile <(printf "subjectAltName=DNS:localhost") 2>/dev/null

popd >/dev/null

echo "==> [3/7] Installing certs to $CERT_DIR"
sudo mkdir -p "$CERT_DIR"
sudo cp "$WORK_DIR"/{ca.pem,central.pem,central-key.pem,branch.pem,branch-key.pem} "$CERT_DIR/"
sudo chmod 600 "$CERT_DIR"/*-key.pem
rm -rf "$WORK_DIR"

echo "==> [4/7] Installing rsyslog configs (central + branch, both on this VM)"
sudo mkdir -p /var/log/squid
sudo touch "$BRANCH_ACCESS_LOG"

sudo cp "$REPO_ROOT/deploy/rsyslog/central.conf" /etc/rsyslog.d/60-squid-receive.conf
# -z (NUL-separated) so the multi-line PermittedPeer=[...] array is treated
# as one match instead of failing to match line-by-line.
sudo sed -z -i 's/StreamDriver\.PermittedPeer=\[[^]]*\]/StreamDriver.PermittedPeer=["localhost"]/' \
  /etc/rsyslog.d/60-squid-receive.conf

sudo cp "$REPO_ROOT/deploy/rsyslog/branch.conf" /etc/rsyslog.d/61-squid-forward.conf
sudo sed -i \
  -e "s/BRANCH_TAG/${BRANCH_TAG}/g" \
  -e "s/CENTRAL_HOST/127.0.0.1/g" \
  -e 's/StreamDriverPermittedPeers="central.example.internal"/StreamDriverPermittedPeers="localhost"/' \
  /etc/rsyslog.d/61-squid-forward.conf

sudo cp "$REPO_ROOT/deploy/rsyslog/squid-branches.logrotate" /etc/logrotate.d/squid-branches

echo "==> [5/7] Restarting rsyslog"
sudo systemctl restart rsyslog
sleep 1
if ! systemctl is-active --quiet rsyslog; then
  echo "FAILED: rsyslog did not start -- check: sudo journalctl -u rsyslog -n 50"
  exit 1
fi
echo "    rsyslog is active."

echo "==> [6/7] Sending a marker line through the pipeline"
MARKER="SQUID_WATCH_TEST_$(date +%s)"
echo "$MARKER" | sudo tee -a "$BRANCH_ACCESS_LOG" >/dev/null

echo "    waiting up to 10s for it to reach $CENTRAL_BRANCH_LOG ..."
for _ in $(seq 1 10); do
  if sudo test -f "$CENTRAL_BRANCH_LOG" && sudo grep -q "$MARKER" "$CENTRAL_BRANCH_LOG" 2>/dev/null; then
    echo "==> [7/7] SUCCESS: marker line arrived at $CENTRAL_BRANCH_LOG"
    echo
    echo "Transport is working end-to-end. Next steps:"
    echo "  1. Point the backend at it: in backend/.env set"
    echo "     LOG_SOURCES=[{\"branch\":\"${BRANCH_TAG}\",\"path\":\"${CENTRAL_BRANCH_LOG}\"}]"
    echo "  2. Generate realistic traffic:"
    echo "     cd backend && python3 scripts/generate_demo_log.py --output ${BRANCH_ACCESS_LOG} --rate 10"
    echo "  3. Start the backend, then check: curl -s http://localhost:8000/api/health | python3 -m json.tool"
    echo "     -- log_sources[].branch == \"${BRANCH_TAG}\", alive == true, parse_failure_rate near 0"
    exit 0
  fi
  sleep 1
done

echo "FAILED: marker line did not arrive within 10s. Debug with:"
echo "  sudo journalctl -u rsyslog -n 100 --no-pager"
echo "  sudo cat /etc/rsyslog.d/60-squid-receive.conf /etc/rsyslog.d/61-squid-forward.conf"
exit 1

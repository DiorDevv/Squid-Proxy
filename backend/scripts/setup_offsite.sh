#!/bin/bash
# One-shot helper for wiring db-offsite to a real sftp: target -- the VM-side half of
# "Off-site copies" in README.md / vm-test-qollanma/5-OFFSITE-BACKUP-ULASH.md. Run this
# ON THE VM (where docker compose runs), never on a dev machine: it generates a keypair
# and a restic password directly under deploy/offsite/, which is gitignored on purpose --
# these secrets must never travel through git. Safe to re-run: every step is skipped if
# already done, so re-running after fixing one failed step just picks up where it left off.
#
# Usage (from the repo root):
#   TARGET_HOST=172.25.43.160 TARGET_USER=axmadjonov backend/scripts/setup_offsite.sh
#   TARGET_HOST=... TARGET_USER=... TARGET_PATH=/srv/backups backend/scripts/setup_offsite.sh
#
# TARGET_PATH defaults to the target user's home dir -- restic creates it itself, no
# pre-existing directory required as long as the parent (the home dir) is writable.

set -eu

: "${TARGET_HOST:?TARGET_HOST kerak, masalan: TARGET_HOST=172.25.43.160 TARGET_USER=axmadjonov $0}"
: "${TARGET_USER:?TARGET_USER kerak, masalan: TARGET_HOST=172.25.43.160 TARGET_USER=axmadjonov $0}"
TARGET_PATH="${TARGET_PATH:-/home/$TARGET_USER/squid-watch-offsite}"

cd "$(dirname "$0")/../.."
REPO_ROOT="$(pwd)"
SSH_DIR="deploy/offsite/ssh"
KEY_FILE="$SSH_DIR/id_ed25519"
PASSWORD_FILE="deploy/offsite/restic-password"
KNOWN_HOSTS="$SSH_DIR/known_hosts"

echo "== Target: sftp:${TARGET_USER}@${TARGET_HOST}:${TARGET_PATH} =="
echo

# --- 0) deploy/offsite/ must be writable by whoever runs this. Docker auto-creates it
# (root-owned) the first time db-offsite starts before any secrets exist there, so this
# is a common first-run blocker -- fail loud with the exact fix instead of a confusing
# "permission denied" mid-script.
if [ ! -w "deploy/offsite" ]; then
  echo "XATO: deploy/offsite/ papkasiga yozish huquqi yo'q (ehtimol Docker uni root"
  echo "egaligida avtomatik yaratgan). Avval shuni ishga tushiring:"
  echo "  sudo chown -R \$(whoami):\$(whoami) deploy/offsite"
  echo "so'ng bu skriptni qayta ishga tushiring."
  exit 1
fi
mkdir -p "$SSH_DIR"

# --- 1) Keypair -- passphrase-less on purpose: db-offsite runs unattended, nothing can
# type a passphrase into it. Don't reuse a key used anywhere else (e.g. squidreader).
if [ -f "$KEY_FILE" ]; then
  echo "[1/6] SSH keypair allaqachon bor, o'tkazib yuborildi ($KEY_FILE)"
else
  echo "[1/6] SSH keypair yaratilmoqda..."
  ssh-keygen -t ed25519 -N "" -f "$KEY_FILE" -C squid-watch-offsite
  chmod 600 "$KEY_FILE"
fi

# --- 2) Restic repository password -- the only thing standing between the off-site
# copy and being unrestorable if this disk is lost. The script only generates it; it's
# on the operator to copy it into a password manager (step 6 below repeats this).
if [ -s "$PASSWORD_FILE" ]; then
  echo "[2/6] Restic parol fayli allaqachon bor, o'tkazib yuborildi"
else
  echo "[2/6] Restic parol yaratilmoqda..."
  python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "$PASSWORD_FILE"
  chmod 600 "$PASSWORD_FILE"
fi

# --- 3) Install the public key on the target. Interactive (asks for the target
# account's password) unless key auth already works there -- can't be silent, since
# that's exactly the credential being bootstrapped here.
echo "[3/6] Ochiq kalit target serverga o'rnatilmoqda (parol so'ralishi mumkin)..."
if ssh -i "$KEY_FILE" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
    "${TARGET_USER}@${TARGET_HOST}" "echo already-authorized" >/dev/null 2>&1; then
  echo "      kalit allaqachon ishlayapti, o'tkazib yuborildi"
else
  ssh-copy-id -i "${KEY_FILE}.pub" "${TARGET_USER}@${TARGET_HOST}"
fi

# --- 4) Pre-populate known_hosts on the HOST -- db-offsite's container mounts
# deploy/offsite/ssh read-only, so it can never do this interactively itself.
echo "[4/6] known_hosts to'ldirilmoqda..."
touch "$KNOWN_HOSTS"
if ssh-keygen -F "$TARGET_HOST" -f "$KNOWN_HOSTS" >/dev/null 2>&1; then
  echo "      $TARGET_HOST allaqachon known_hosts'da, o'tkazib yuborildi"
else
  ssh-keyscan -H "$TARGET_HOST" >> "$KNOWN_HOSTS" 2>/dev/null
fi

# --- 5) Verify the exact same way db-offsite's container will connect: this key,
# no interactive prompts allowed (BatchMode=yes), known_hosts already populated.
echo "[5/6] Ulanish tekshirilmoqda..."
if ! ssh -i "$KEY_FILE" -o BatchMode=yes -o ConnectTimeout=5 \
    "${TARGET_USER}@${TARGET_HOST}" "echo OK"; then
  echo "XATO: SSH ulanish ishlamadi. .env ga tegilmadi -- yuqoridagi xatoni tuzating"
  echo "va skriptni qayta ishga tushiring."
  exit 1
fi

# --- 6) Wire .env: replace an existing OFFSITE_RESTIC_REPOSITORY / _ENABLED line in
# place (idempotent re-run with a different TARGET_*), append if missing entirely.
# PASSWORD_FILE always points at the container-internal mount path -- never the host
# path -- see docker-compose.yml's db-offsite volumes.
echo "[6/6] .env yozilmoqda..."
set_env() {
  key="$1"; value="$2"
  if grep -q "^${key}=" .env 2>/dev/null; then
    sed -i "s#^${key}=.*#${key}=${value}#" .env
  else
    echo "${key}=${value}" >> .env
  fi
}
set_env OFFSITE_ENABLED true
set_env OFFSITE_RESTIC_REPOSITORY "sftp:${TARGET_USER}@${TARGET_HOST}:${TARGET_PATH}"
set_env OFFSITE_RESTIC_PASSWORD_FILE /offsite-config/restic-password

echo
echo "Tayyor. Endi:"
echo "  docker compose up -d db-offsite"
echo "  docker compose logs -f db-offsite"
echo
echo "MUHIM: parolni off-box saqlang (parol menejeriga yozib qo'ying):"
echo "  cat $REPO_ROOT/$PASSWORD_FILE"

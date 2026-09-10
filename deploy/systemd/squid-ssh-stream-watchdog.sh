#!/usr/bin/env bash
#
# Restarts any squid-ssh-stream@<branch> instance whose local log file has
# stopped growing. The SSH-pull stream (squid-ssh-stream@.service) can wedge
# without exiting -- a half-open TCP connection that still answers
# ServerAlive probes, a remote `tail` that died, a stall right at log
# rotation -- and `Restart=always` only fires on an actual process exit, so
# a wedged stream sits there silently until someone runs `systemctl
# restart`. This does that automatically.
#
# Staleness = the mtime of LOCAL_LOG_PATH (from each branch's env file) is
# older than WATCHDOG_MAX_STALE_SECONDS. A healthy stream touches that file
# every few seconds; the default 600s is loose enough that a genuinely
# quiet branch at 3am isn't restarted needlessly, and a restart is a
# few-seconds reconnect anyway (the same gap the unit header already
# documents).
#
# Install on the central/dashboard server, alongside the @.service unit:
#   sudo cp deploy/systemd/squid-ssh-stream-watchdog.sh /usr/local/bin/
#   sudo chmod +x /usr/local/bin/squid-ssh-stream-watchdog.sh
#   sudo cp deploy/systemd/squid-ssh-stream-watchdog.{service,timer} /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now squid-ssh-stream-watchdog.timer
#
# Check it: `systemctl list-timers squid-ssh-stream-watchdog.timer`
#           `journalctl -u squid-ssh-stream-watchdog.service`

set -u

ENV_DIR="${WATCHDOG_ENV_DIR:-/etc/squid-ssh-stream}"
MAX_STALE="${WATCHDOG_MAX_STALE_SECONDS:-600}"

now="$(date +%s)"
restarted=0

shopt -s nullglob
for env_file in "$ENV_DIR"/*.env; do
    branch="$(basename "$env_file" .env)"

    # Pull LOCAL_LOG_PATH out without executing the whole env file.
    log_path="$(sed -n 's/^[[:space:]]*LOCAL_LOG_PATH[[:space:]]*=[[:space:]]*//p' "$env_file" | tail -n1)"
    log_path="${log_path%\"}"
    log_path="${log_path#\"}"
    [ -n "$log_path" ] || { echo "watchdog: $branch has no LOCAL_LOG_PATH, skipping"; continue; }

    # Only act on instances that are supposed to be running.
    systemctl is-active --quiet "squid-ssh-stream@${branch}.service" || continue

    if [ ! -e "$log_path" ]; then
        mtime=0
    else
        mtime="$(stat -c %Y "$log_path" 2>/dev/null || echo 0)"
    fi
    age=$(( now - mtime ))

    if [ "$age" -ge "$MAX_STALE" ]; then
        echo "watchdog: ${branch} log stale ${age}s (>= ${MAX_STALE}s), restarting squid-ssh-stream@${branch}"
        logger -t squid-ssh-stream-watchdog "restarting squid-ssh-stream@${branch}: local log stale ${age}s"
        systemctl restart "squid-ssh-stream@${branch}.service" || echo "watchdog: restart of ${branch} failed"
        restarted=$(( restarted + 1 ))
    fi
done

echo "watchdog: done, ${restarted} instance(s) restarted"

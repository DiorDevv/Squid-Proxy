#!/usr/bin/env bash
# Alerts if a branch server's rsyslog disk-assisted queue (see branch.conf's
# `queue.spoolDirectory`) is filling up -- the queue only grows this large
# when the central server or network link has been unreachable for a while,
# so this is the early warning that a branch is about to start dropping log
# data if the outage isn't resolved before `queue.maxdiskspace` is hit.
#
# Install (per branch server):
#   sudo cp deploy/rsyslog/check-queue-disk.sh /usr/local/bin/
#   sudo chmod +x /usr/local/bin/check-queue-disk.sh
#
# Run every 15 min via cron:
#   */15 * * * * /usr/local/bin/check-queue-disk.sh
# or a systemd timer (OnCalendar=*:0/15) calling a matching .service unit.
#
# Emits a CRIT line via `logger` (facility user, tag squid-queue-check) when
# over threshold, so it surfaces through whatever monitoring already
# consumes this server's syslog/journal (Nagios NRPE, Zabbix agent active
# checks, journald + alertmanager, etc.) -- deliberately not inventing a new
# alert channel here, same reasoning as the backend's own ALERT_WEBHOOK_URL
# being optional/pluggable rather than a bespoke notifier.

set -euo pipefail

SPOOL_DIR="${SQUID_QUEUE_SPOOL_DIR:-/var/spool/rsyslog}"
# Matches branch.conf's queue.maxdiskspace (2g default there); alert at 80%
# of that so there's time to act before rsyslog starts discarding messages.
THRESHOLD_MB="${SQUID_QUEUE_THRESHOLD_MB:-1600}"

if [[ ! -d "$SPOOL_DIR" ]]; then
  logger -p user.err -t squid-queue-check "spool directory $SPOOL_DIR does not exist"
  exit 1
fi

USED_MB=$(du -sm "$SPOOL_DIR" | cut -f1)

if (( USED_MB >= THRESHOLD_MB )); then
  logger -p user.crit -t squid-queue-check \
    "rsyslog queue at ${USED_MB}MB (threshold ${THRESHOLD_MB}MB) in $SPOOL_DIR -- central server/link likely down; log data will start being dropped if this keeps growing"
  exit 2
fi

exit 0

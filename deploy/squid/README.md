# 4 branch Squid instances for this deployment

Ready-to-copy configs for a **4-Squid-on-one-server** topology (all 4 branches and the
dashboard on the same machine), with branch names matching
`../../docker-compose.override.yml`'s `LOG_SOURCES` shape. This is a different setup from
the single-Squid, separate-server `rsyslog` path in `../../vm-test-qollanma/` — use this
directory only if you're actually running multiple Squid instances on one host; otherwise
`../../vm-test-qollanma/2-SQUIDGA-ULASH-RSYSLOG.md` covers connecting one remote Squid
server instead.

| File | Branch tag | Port | Log path (on host) |
|---|---|---|---|
| `squid-filiallar.conf` | `filiallar` | 3128 | `/var/log/squid-filiallar/access.log` |
| `squid-bosh_ofis.conf` | `bosh_ofis` | 3129 | `/var/log/squid-bosh_ofis/access.log` |
| `squid-serverlar.conf` | `serverlar` | 3130 | `/var/log/squid-serverlar/access.log` |
| `squid-trafik.conf` | `trafik` | 3131 | `/var/log/squid-trafik/access.log` |

`squid-instance@.service` is the shared systemd template that runs all 4 from one `squid`
binary. See its own header comment for the full install sequence (create
`/var/log/squid-*` and `/var/spool/squid-*` directories with the right ownership first,
then `systemctl enable --now squid-instance@<branch>` per branch).

**Before real production use** (not just VM testing): narrow each file's
`acl localnet src ...` line to that branch's actual internal network(s) --
the shipped default (`10.0.0.0/8 172.16.0.0/12 192.168.0.0/16`) is a safe,
broad placeholder for testing, not a real access boundary.

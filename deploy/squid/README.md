# 4 branch Squid instances for this deployment

Ready-to-copy configs for the 4-Squid-on-one-server setup this project's
`vm-test-qollanma/QOLLANMA.md` (2-BOSQICH) walks through, with branch names
finalized to match `../../docker-compose.override.yml`'s `LOG_SOURCES`:

| File | Branch tag | Port | Log path (on host) |
|---|---|---|---|
| `squid-filiallar.conf` | `filiallar` | 3128 | `/var/log/squid-filiallar/access.log` |
| `squid-bosh_ofis.conf` | `bosh_ofis` | 3129 | `/var/log/squid-bosh_ofis/access.log` |
| `squid-serverlar.conf` | `serverlar` | 3130 | `/var/log/squid-serverlar/access.log` |
| `squid-trafik.conf` | `trafik` | 3131 | `/var/log/squid-trafik/access.log` |

`squid-instance@.service` is the shared systemd template that runs all 4 from
one `squid` binary. See its own header comment, or
`vm-test-qollanma/QOLLANMA.md`'s 2.2–2.5 steps, for the full install sequence
(create `/var/log/squid-*` and `/var/spool/squid-*` directories with the
right ownership first).

**Before real production use** (not just VM testing): narrow each file's
`acl localnet src ...` line to that branch's actual internal network(s) --
the shipped default (`10.0.0.0/8 172.16.0.0/12 192.168.0.0/16`) is a safe,
broad placeholder for testing, not a real access boundary.

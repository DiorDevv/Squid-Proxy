#!/usr/bin/env python3
"""One-shot fix for a Docker build that can't resolve external domains --
see the "Docker build can't resolve external domains" section in
docker-compose.override.yml.example for the full diagnosis (a corporate/
internal DNS server that SERVFAILs anything outside its own zone, which
Docker's containers inherit even though the host itself resolves fine).

Resolves the hosts npm/pip/apt need via this machine's own working
resolver, shelling out to `getent ahostsv4` (not Python's socket module --
socket.gethostbyname() was found to fail on a real host where `getent`/
`curl` resolve the exact same name fine, apparently an NSS/systemd-resolved
integration quirk specific to that older resolver call) and writes them
into docker-compose.override.yml as `extra_hosts` under each service's
`build:` section. Safe to re-run: only inserts a
service's `build.extra_hosts` block if that service doesn't already have
one, and never touches any other existing content in the file (your real
LOG_SOURCES/volumes override, Postgres tuning command, etc. are left
exactly as they are).

Run this ON THE VM (or wherever the build actually happens), from the
repo root:
    python3 deploy/fix_build_dns.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

OVERRIDE_PATH = Path("docker-compose.override.yml")

# service -> hosts its build stage needs to reach
SERVICE_HOSTS = {
    "frontend": ["registry.npmjs.org"],
    "backend": ["pypi.org", "files.pythonhosted.org", "deb.debian.org"],
}


def resolve(host: str) -> str | None:
    # `getent ahostsv4` -- goes through the same NSS chain `curl`/most
    # system tools use, unlike Python's own socket.gethostbyname() (see
    # module docstring for why that matters here).
    try:
        result = subprocess.run(
            ["getent", "ahostsv4", host], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  ! could not run getent for {host}: {exc}", file=sys.stderr)
        return None
    if result.returncode != 0 or not result.stdout.strip():
        print(f"  ! could not resolve {host} from this machine (getent exit {result.returncode})", file=sys.stderr)
        return None
    return result.stdout.split()[0]


def extra_hosts_block(hosts: list[str]) -> str:
    lines = ["    build:", "      extra_hosts:"]
    for host in hosts:
        ip = resolve(host)
        if ip is None:
            continue
        lines.append(f'        - "{host}:{ip}"')
        print(f"  {host} -> {ip}")
    return "\n".join(lines) + "\n"


def insert_after_service_line(text: str, service: str, block: str) -> str:
    """Insert `block` as the first child under an existing top-level
    `  <service>:` line, before whatever's already there (environment:,
    volumes:, etc. -- key order under a service doesn't matter to Compose)."""
    marker = f"  {service}:\n"
    idx = text.find(marker)
    if idx == -1:
        raise ValueError(f"'{service}:' not found at the expected indentation")
    insert_at = idx + len(marker)
    return text[:insert_at] + block + text[insert_at:]


def append_new_service(text: str, service: str, block: str) -> str:
    if not text.endswith("\n"):
        text += "\n"
    return text + f"  {service}:\n" + block


def main() -> None:
    if not OVERRIDE_PATH.exists():
        # No existing override -- start one with just this fix. Still
        # needs a `services:` top-level key for Compose to accept it.
        OVERRIDE_PATH.write_text("services:\n")
        print(f"{OVERRIDE_PATH} did not exist, created a fresh one")

    text = OVERRIDE_PATH.read_text()
    changed = False

    for service, hosts in SERVICE_HOSTS.items():
        marker = f"  {service}:\n"
        if marker not in text:
            print(f"[{service}] not present in {OVERRIDE_PATH} -- adding a new service block")
            block = extra_hosts_block(hosts)
            text = append_new_service(text, service, block)
            changed = True
            continue

        # Idempotent: find this service's own indented region and check
        # whether it already declares extra_hosts anywhere inside it,
        # rather than just grepping the whole file (another service could
        # legitimately have its own extra_hosts too).
        start = text.find(marker) + len(marker)
        # End of this service's block = the next line at the same "  x:"
        # (2-space) indentation, or end of file.
        rest = text[start:]
        end_offset = len(rest)
        for line in rest.splitlines(keepends=True):
            if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
                end_offset = rest.find(line)
                break
        service_block = rest[:end_offset]

        if "extra_hosts" in service_block:
            print(f"[{service}] already has extra_hosts, left untouched")
            continue

        print(f"[{service}] adding build.extra_hosts")
        block = extra_hosts_block(hosts)
        text = insert_after_service_line(text, service, block)
        changed = True

    if changed:
        OVERRIDE_PATH.write_text(text)
        print(f"\nWrote {OVERRIDE_PATH}. Now: docker compose build frontend backend")
    else:
        print("\nNothing to change.")


if __name__ == "__main__":
    main()

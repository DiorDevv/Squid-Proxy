#!/usr/bin/env python3
"""Decrypts archive files written by app.services.archive_service.archive
when ARCHIVE_ENCRYPTION_KEY was set (see that module's "Encryption at rest"
section) -- turns a squid-events-<branch>-<since>_<until>.csv.gz.enc back
into the plain .csv.gz an unencrypted deployment would have written, which
`gzip -d` / `zcat` / pandas.read_csv(compression="gzip") etc. can then read
normally. Standalone: doesn't import the app or touch the database, so it
works from a copy of the archive files alone, with just the key.

Usage:
    ARCHIVE_ENCRYPTION_KEY=... python scripts/decrypt_archive.py \
        archives/squid-events-default-2026-08-01_2026-08-08.csv.gz.enc
    python scripts/decrypt_archive.py --key-file /path/to/key.txt archives/*.csv.gz.enc
"""

import argparse
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _decrypt_one(path: Path, fernet: Fernet, output_dir: Path | None) -> Path:
    if not path.name.endswith(".enc"):
        raise ValueError(f"{path} doesn't end in .enc -- doesn't look like an encrypted archive")
    ciphertext = path.read_bytes()
    try:
        plaintext = fernet.decrypt(ciphertext)
    except InvalidToken as exc:
        raise ValueError(
            f"{path}: decryption failed -- wrong key, or the file is truncated/corrupted"
        ) from exc
    # Path.with_suffix("") strips only the trailing ".enc", leaving the
    # original "....csv.gz" name -- an unencrypted deployment's own output.
    out_path = (output_dir or path.parent) / path.with_suffix("").name
    out_path.write_bytes(plaintext)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="+", type=Path, help="One or more .csv.gz.enc archive files")
    parser.add_argument(
        "--key", help="Fernet key (base64). Defaults to the ARCHIVE_ENCRYPTION_KEY env var."
    )
    parser.add_argument("--key-file", type=Path, help="Read the key from this file instead")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Write decrypted files here (default: alongside each input)",
    )
    args = parser.parse_args()

    key = (
        args.key
        or (args.key_file.read_text().strip() if args.key_file else None)
        or os.environ.get("ARCHIVE_ENCRYPTION_KEY")
    )
    if not key:
        parser.error("No key given -- pass --key, --key-file, or set ARCHIVE_ENCRYPTION_KEY")

    fernet = Fernet(key.encode())
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for path in args.files:
        try:
            out_path = _decrypt_one(path, fernet, args.output_dir)
        except (ValueError, FileNotFoundError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        print(f"{path} -> {out_path}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

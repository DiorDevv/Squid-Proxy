#!/usr/bin/env python3
"""Verifies a Squid Watch export was produced by a specific server and has
not been altered since -- offline, with no access back to that server.

Checks two independent things:
  1. Integrity: the export file's content matches the SHA-256 recorded in
     the manifest.
  2. Authenticity: the manifest itself carries a valid Ed25519 signature
     under the given public key.

Standalone by design (same reasoning as decrypt_archive.py) -- the whole
point is that whoever received an export (e.g. legal/compliance, who may
have no login and no network path to the server that made it) can run this
with nothing but the export file, the manifest, and the public key. It does
NOT import this project's backend; it reimplements the ~15 lines of
canonical_json()/verify() from app/services/export_signing.py rather than
depending on the full app being installed. Keep the two in sync if either
changes.

Only dependency: `pip install cryptography`.

Usage:
    python scripts/verify_export.py \
        --export squid-events-2026-09-01_2026-09-04.zip \
        --manifest squid-events-2026-09-01_2026-09-04.manifest.json

`--manifest` is the exact JSON body of GET /api/export/jobs/{id}/manifest,
saved to a file -- fetch and save it once, at the same time you download
the export itself, from an account with access to that job.

By default the public key embedded in --manifest is trusted for this run.
For real assurance get the public key through a *separate* channel (it's
meant to be published -- e.g. in this deployment's README or handed over
out of band) and pass --public-key to require an exact match, rather than
trusting whatever the manifest file itself claims.
"""

import argparse
import base64
import hashlib
import json
import sys
import zipfile
from pathlib import Path

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:
    print("Missing dependency: pip install cryptography", file=sys.stderr)
    sys.exit(2)


def canonical_json(manifest: dict) -> bytes:
    # Must match app/services/export_signing.py's canonical_json() exactly
    # -- this is what was actually signed.
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_signature(manifest: dict, signature_b64: str, public_key_b64: str) -> bool:
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.urlsafe_b64decode(public_key_b64.encode("ascii"))
        )
        public_key.verify(
            base64.urlsafe_b64decode(signature_b64.encode("ascii")), canonical_json(manifest)
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def content_sha256(export_path: Path) -> str:
    """The hash to compare against manifest["content_sha256"]: for a .zip
    export, the single data-file member inside it (csv/json -- what
    run_job's inner_filename() names it); for .xlsx, the file itself
    (xlsx exports have no outer zip, see result_filename's docstring in
    export_job_service.py)."""
    digest = hashlib.sha256()
    if export_path.suffix == ".zip":
        with zipfile.ZipFile(export_path) as zf:
            names = zf.namelist()
            if len(names) != 1:
                raise ValueError(
                    f"expected exactly one file inside the zip, found {len(names)}: {names}"
                )
            with zf.open(names[0]) as member:
                for chunk in iter(lambda: member.read(1024 * 1024), b""):
                    digest.update(chunk)
    else:
        with export_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--export", required=True, type=Path, help="the downloaded export file (.zip/.xlsx)")
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="GET /api/export/jobs/{id}/manifest's JSON body, saved to a file",
    )
    parser.add_argument(
        "--public-key",
        help="require this exact public key (base64url), rather than trusting the one in --manifest",
    )
    args = parser.parse_args()

    envelope = json.loads(args.manifest.read_text())
    manifest = envelope["manifest"]
    signature = envelope.get("signature")
    public_key = envelope.get("public_key")

    print(f"Export:   {args.export}")
    print(f"Job ID:   {manifest.get('job_id')}")
    print(f"Range:    {manifest.get('since')} .. {manifest.get('until')}")
    print(f"Rows:     {manifest.get('row_count')}")
    print()

    ok = True

    if args.public_key and public_key != args.public_key:
        print(f"FAIL  public key in manifest ({public_key}) does not match --public-key")
        ok = False
        public_key = args.public_key  # still check the signature against the one the caller trusts

    if signature is None or public_key is None:
        print("FAIL  this export was never signed (no signature/public key in the manifest) --")
        print("      integrity can still be checked below, but authenticity cannot be.")
        ok = False
    elif verify_signature(manifest, signature, public_key):
        print("PASS  signature is valid for this manifest under the given public key")
    else:
        print("FAIL  signature does NOT match -- the manifest was altered, or signed by a different key")
        ok = False

    try:
        actual = content_sha256(args.export)
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        print(f"FAIL  could not read --export: {exc}")
        return 1

    expected = manifest.get("content_sha256")
    if actual == expected:
        print("PASS  export content matches the manifest's recorded SHA-256")
    else:
        print("FAIL  export content does NOT match -- the file has been altered since it was produced")
        print(f"      expected: {expected}")
        print(f"      actual:   {actual}")
        ok = False

    print()
    print("VERIFIED" if ok else "NOT VERIFIED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

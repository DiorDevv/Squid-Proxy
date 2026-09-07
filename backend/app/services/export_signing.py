"""Signs export-job manifests with Ed25519 so a downloaded export can be
proven un-tampered *offline* -- checked against a published public key,
without a live API call back to this server (which the recipient may not
even have credentials for, e.g. a legal/compliance third party). See
scripts/verify_export.py, the standalone, dependency-light verifier this
pairs with.

Opt-in: EXPORT_SIGNING_PRIVATE_KEY unset means signing is a no-op (the
manifest is still built and stored, `signature` is just None) -- same
"off unless explicitly configured" posture as ARCHIVE_ENCRYPTION_KEY. An
Ed25519 key pair is asymmetric on purpose: the *private* key that signs
never leaves this server, while the *public* key handed to a verifier can
prove authenticity without being able to forge new signatures itself.
"""

import base64
import json
from typing import TYPE_CHECKING, Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.models.export_job import ExportJob

ALGORITHM = "ed25519"
_JSON_SEPARATORS = (",", ":")


def canonical_json(manifest: dict[str, Any]) -> bytes:
    """Deterministic encoding: sorted keys, no incidental whitespace -- what
    both sign() and a verifier must reproduce byte-for-byte from the same
    manifest dict for the signature to check out."""
    return json.dumps(manifest, sort_keys=True, separators=_JSON_SEPARATORS).encode("utf-8")


def build_manifest(job: "ExportJob", content_sha256: str) -> dict[str, Any]:
    """The facts a signature vouches for. `content_sha256` is the hash of
    the *uncompressed data file* (see run_job) -- what a verifier gets
    after extracting it from the delivered zip/xlsx -- not the outer zip's
    own bytes, which aren't stable across zip tools/versions.
    job.checksum_sha256 (the delivered artifact's own hash) is a separate,
    already-existing field for "is this the exact file the server sent",
    included here too for completeness."""
    return {
        "job_id": job.id,
        "format": job.format,
        "since": job.since.isoformat(),
        "until": job.until.isoformat(),
        "branch": job.branch,
        "blocked_only": job.blocked_only,
        "domain": job.domain,
        "category": job.category,
        "client_ip": job.client_ip,
        "row_count": job.row_count,
        "file_size_bytes": job.file_size_bytes,
        "content_sha256": content_sha256,
        "delivered_file_sha256": job.checksum_sha256,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _decode_seed(raw: str) -> bytes:
    seed = base64.urlsafe_b64decode(raw.encode("ascii"))
    if len(seed) != 32:
        raise ValueError("must decode to exactly 32 bytes")
    return seed


def _private_key() -> Ed25519PrivateKey | None:
    # Deliberately not cached: deriving an Ed25519 key from its 32-byte seed
    # is microseconds, and caching it (like get_settings() itself does)
    # would mean a test that monkeypatches get_settings() to change the key
    # keeps seeing the first one it ever loaded.
    raw = get_settings().EXPORT_SIGNING_PRIVATE_KEY
    if not raw:
        return None
    try:
        return Ed25519PrivateKey.from_private_bytes(_decode_seed(raw))
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "EXPORT_SIGNING_PRIVATE_KEY is set but isn't a valid base64url-encoded "
            "32-byte Ed25519 seed. Generate one with: python3 -c \"import base64, "
            'secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"'
        ) from exc


def signing_enabled() -> bool:
    return _private_key() is not None


def public_key_b64() -> str | None:
    """The public key a verifier needs -- safe to publish (README, the
    export UI, wherever). None if signing is disabled."""
    key = _private_key()
    if key is None:
        return None
    return base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).decode("ascii")


def sign(manifest: dict[str, Any]) -> str | None:
    """Base64url Ed25519 signature over canonical_json(manifest), or None
    if signing is disabled (EXPORT_SIGNING_PRIVATE_KEY unset)."""
    key = _private_key()
    if key is None:
        return None
    return base64.urlsafe_b64encode(key.sign(canonical_json(manifest))).decode("ascii")


def verify(manifest: dict[str, Any], signature_b64: str, public_key_b64_value: str) -> bool:
    """True iff signature_b64 is a valid signature over
    canonical_json(manifest) under public_key_b64_value. Never raises --
    any malformed input (bad base64, wrong length, wrong key) is simply
    "not valid", the same as a genuine forgery. Standalone (doesn't read
    settings/DB) so scripts/verify_export.py can call it with no server
    connection at all."""
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.urlsafe_b64decode(public_key_b64_value.encode("ascii"))
        )
        public_key.verify(
            base64.urlsafe_b64decode(signature_b64.encode("ascii")), canonical_json(manifest)
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


__all__ = [
    "ALGORITHM",
    "build_manifest",
    "canonical_json",
    "public_key_b64",
    "sign",
    "signing_enabled",
    "verify",
]

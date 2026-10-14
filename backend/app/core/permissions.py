"""Feature permissions layered on top of roles.

A role still decides who manages accounts (see user_service) and is the
default template for everything else. Each permission below gates one
feature area; an account either inherits its role's defaults
(User.permissions is None) or carries an explicit list chosen by whoever
manages it -- e.g. a viewer who may also export, or an admin who may not
touch alert settings.

A super admin always holds every permission, whatever is stored.
"""

from collections.abc import Iterable

EXPORT = "export"  # list exports: the "Who" list and blocked-page groups (Excel/CSV)
RAW_EXPORT = "raw_export"  # raw event exports and export jobs -- every URL, per person
WATCHLIST = "watchlist"  # view and manage the watchlist
REPORTS = "reports"  # send reports on demand
SUBJECT_ACCESS = "subject_access"  # per-person dossier (subject access request)
CATEGORIES = "categories"  # domain category overrides, import/export
ALERTS = "alerts"  # alert settings, rules, Telegram linking
AUDIT = "audit"  # audit log, data policy, system health

ALL_PERMISSIONS: tuple[str, ...] = (
    EXPORT,
    RAW_EXPORT,
    WATCHLIST,
    REPORTS,
    SUBJECT_ACCESS,
    CATEGORIES,
    ALERTS,
    AUDIT,
)

ROLE_DEFAULTS: dict[str, frozenset[str]] = {
    "superadmin": frozenset(ALL_PERMISSIONS),
    "admin": frozenset(ALL_PERMISSIONS),
    "auditor": frozenset({AUDIT, EXPORT}),
    "viewer": frozenset(),
}


def normalize(permissions: Iterable[str] | None) -> list[str] | None:
    """None stays None (inherit the role's defaults). Otherwise: known
    names only, de-duplicated, in catalogue order. Raises ValueError on an
    unknown name so a typo fails loudly instead of silently granting less."""
    if permissions is None:
        return None
    requested = set(permissions)
    unknown = requested - set(ALL_PERMISSIONS)
    if unknown:
        raise ValueError(
            f"Unknown permission(s): {', '.join(sorted(unknown))}. Valid: {', '.join(ALL_PERMISSIONS)}."
        )
    return [p for p in ALL_PERMISSIONS if p in requested]


def effective(role: str, stored: Iterable[str] | None) -> frozenset[str]:
    if role == "superadmin":
        return ROLE_DEFAULTS["superadmin"]
    if stored is None:
        return ROLE_DEFAULTS.get(role, frozenset())
    return frozenset(p for p in stored if p in ALL_PERMISSIONS)

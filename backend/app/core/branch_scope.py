"""Branch scope: which branches' data a request may read.

A user is either unrestricted (sees every branch) or limited to one or more
branch tags (Settings.effective_log_sources). Data-read routes receive the
resolved scope from api.deps.resolve_branch as a `BranchScope`:

  - None              -- every branch (unrestricted user, nothing selected)
  - "main"            -- exactly one branch
  - ("filial", "main") -- several branches at once (a multi-branch user who
                          didn't pick one), always sorted and de-duplicated

Services filter with branch_filter() instead of `column == branch`, so the
same code path serves all three shapes.

Rows that *belong* to a scope (an export job, an audit entry about a user)
store it as one string -- scope_tag() -- and read it back with
parse_scope_tag(). A single branch keeps its plain tag, so rows written
before multi-branch scopes existed read back unchanged.
"""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import ColumnElement

BranchScope = str | tuple[str, ...] | None

_TAG_SEPARATOR = ","


def normalize_branches(branches: Iterable[str] | None) -> tuple[str, ...] | None:
    """None stays None (unrestricted); anything else becomes a sorted,
    de-duplicated tuple. An empty collection also means unrestricted --
    "limited to no branches" is not a state an account can be in."""
    if branches is None:
        return None
    cleaned = tuple(sorted({b.strip() for b in branches if b and b.strip()}))
    return cleaned or None


def as_scope(branches: tuple[str, ...] | None) -> BranchScope:
    """A one-element tuple collapses to the plain string, so single-branch
    accounts keep producing exactly the queries/tags they always did."""
    if branches is None:
        return None
    return branches[0] if len(branches) == 1 else branches


def scope_branches(scope: BranchScope) -> tuple[str, ...] | None:
    if scope is None:
        return None
    if isinstance(scope, str):
        return (scope,)
    return tuple(scope)


def branch_filter(column: Any, scope: str | tuple[str, ...]) -> ColumnElement[bool]:
    """`column == scope` for one branch, `column IN (...)` for several.
    Callers keep their own `if branch:` / `if branch is not None:` guard --
    this is only ever reached with a non-None scope."""
    if isinstance(scope, str):
        return column == scope
    return column.in_(scope)


def branch_matches(value: str | None, scope: BranchScope) -> bool:
    """Python-side counterpart of branch_filter, for in-memory filtering."""
    if scope is None:
        return True
    if isinstance(scope, str):
        return value == scope
    return value in scope


def scope_tag(scope: BranchScope) -> str | None:
    if scope is None:
        return None
    if isinstance(scope, str):
        return scope
    return _TAG_SEPARATOR.join(scope)


def scope_label(scope: BranchScope, separator: str = ", ") -> str | None:
    """Human-readable form for file headers and names; None when
    unrestricted (callers substitute their own "all branches" wording)."""
    branches = scope_branches(scope)
    return separator.join(branches) if branches is not None else None


def parse_scope_tag(tag: str | None) -> BranchScope:
    if not tag:
        return None
    if _TAG_SEPARATOR not in tag:
        return tag
    return as_scope(normalize_branches(tag.split(_TAG_SEPARATOR)))


def scope_within(inner: BranchScope, outer: tuple[str, ...] | None) -> bool:
    """Is everything `inner` covers also inside `outer`? An unrestricted
    `outer` contains anything; an unrestricted `inner` is only inside an
    unrestricted `outer`."""
    if outer is None:
        return True
    inner_branches = scope_branches(inner)
    if inner_branches is None:
        return False
    return set(inner_branches) <= set(outer)

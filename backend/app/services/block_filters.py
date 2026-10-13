"""The Blocked page's shared filter language -- one parser for both the
raw-events "Requests" view and the aggregate "Analysis" view, so a filter
means exactly the same thing on either.

Each filter is a comma / whitespace separated list of terms:

  domains  `crl.*, *.pki.goog, ctldl.windowsupdate.com, !*.microsoft.com`
           A term with `*` is a wildcard over the whole domain; a term
           without one matches anywhere inside it; `=term` matches exactly.
           `!` excludes. Included terms are OR-ed together, excluded ones
           all apply.
  clients  `172.25.110.0/24, 10.0.0.5, 172.25.103.`
           A CIDR, a single IP, or a prefix ending in `.` / `.*`. A CIDR is
           expanded to octet-aligned prefixes, so it works on the plain
           string column on every database.
  users    `alice, bob` -- part of a login (`=alice` exactly); `-` means
           "no login".
"""

import ipaddress
import re
from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, false, or_, true

MAX_TERMS = 50
_SPLIT = re.compile(r"[\s,;]+")


class FilterError(ValueError):
    """A filter term that can't be parsed -- reported back as a 422."""


def _terms(raw: str | None) -> list[str]:
    terms = [t for t in _SPLIT.split(raw or "") if t]
    if len(terms) > MAX_TERMS:
        raise FilterError(f"too many terms (max {MAX_TERMS})")
    return terms


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _term_like(column, term: str):
    """`=x` exact, `*` wildcard, otherwise contains -- all case-insensitive."""
    if term.startswith("="):
        pattern = _escape_like(term[1:].lower())
    elif "*" in term:
        pattern = _escape_like(term.lower()).replace("*", "%")
    else:
        pattern = f"%{_escape_like(term.lower())}%"
    return column.ilike(pattern, escape="\\")


@dataclass(frozen=True)
class DomainFilter:
    include: tuple[str, ...]
    exclude: tuple[str, ...]

    def condition(self, column) -> ColumnElement[bool] | None:
        parts = []
        if self.include:
            parts.append(or_(*(_term_like(column, t) for t in self.include)))
        parts += [~_term_like(column, t) for t in self.exclude]
        return and_(*parts) if parts else None


def parse_domains(raw: str | None) -> DomainFilter | None:
    include, exclude = [], []
    for term in _terms(raw):
        negated = term.startswith("!")
        term = term.lstrip("!").strip()
        if not term or term.replace("*", "").lstrip("=") == "":
            continue
        (exclude if negated else include).append(term)
    if not include and not exclude:
        return None
    return DomainFilter(tuple(include), tuple(exclude))


@dataclass(frozen=True)
class ClientFilter:
    exact: tuple[str, ...]
    prefixes: tuple[str, ...]

    def condition(self, column) -> ColumnElement[bool]:
        parts = []
        if self.exact:
            parts.append(column.in_(self.exact))
        parts += [column.like(f"{_escape_like(p)}%", escape="\\") for p in self.prefixes]
        return or_(*parts) if parts else false()


def _cidr_prefixes(network: ipaddress.IPv4Network) -> list[str]:
    """The network as LIKE prefixes, rounded out to the next octet: a /22 is
    four "a.b.c." prefixes -- at most 128 for any prefix length."""
    if network.prefixlen == 32:
        return []
    octets = network.prefixlen // 8 + (1 if network.prefixlen % 8 else 0)
    if octets == 0:
        return [""]
    step = 2 ** (32 - octets * 8)
    count = max(1, network.num_addresses // step)
    start = int(network.network_address)
    prefixes = []
    for i in range(count):
        parts = str(ipaddress.IPv4Address(start + i * step)).split(".")[:octets]
        prefixes.append(".".join(parts) + ".")
    return prefixes


def parse_clients(raw: str | None) -> ClientFilter | None:
    exact: list[str] = []
    prefixes: list[str] = []
    for term in _terms(raw):
        if "/" in term:
            try:
                network = ipaddress.ip_network(term, strict=False)
            except ValueError as exc:
                raise FilterError(f"not a network: {term}") from exc
            if not isinstance(network, ipaddress.IPv4Network):
                raise FilterError(f"only IPv4 networks are supported: {term}")
            if network.prefixlen == 32:
                exact.append(str(network.network_address))
            else:
                prefixes += _cidr_prefixes(network)
        elif term.endswith(".*") or term.endswith("."):
            prefix = term[:-1] if term.endswith("*") else term
            if not re.fullmatch(r"(\d{1,3}\.){1,3}", prefix):
                raise FilterError(f"not an IP prefix: {term}")
            prefixes.append(prefix)
        else:
            try:
                exact.append(str(ipaddress.ip_address(term)))
            except ValueError as exc:
                raise FilterError(f"not an IP address: {term}") from exc
    if not exact and not prefixes:
        return None
    return ClientFilter(tuple(exact), tuple(prefixes))


@dataclass(frozen=True)
class UserFilter:
    terms: tuple[str, ...]
    no_login: bool

    def condition(self, column, *, empty_is_null: bool = False) -> ColumnElement[bool]:
        parts = [_term_like(column, t) for t in self.terms]
        if self.no_login:
            parts.append(or_(column.is_(None), column == "") if empty_is_null else column == "")
        return or_(*parts) if parts else true()


def parse_users(raw: str | None) -> UserFilter | None:
    terms = _terms(raw)
    if not terms:
        return None
    return UserFilter(tuple(t for t in terms if t != "-"), "-" in terms)


@dataclass(frozen=True)
class BlockFilters:
    """Everything but the time range and branch (those come from the shared
    range/branch dependencies)."""

    domains: DomainFilter | None = None
    clients: ClientFilter | None = None
    users: UserFilter | None = None
    proxy: str | None = None

    @property
    def needs_client_detail(self) -> bool:
        """Client/user filters only exist on the per-client aggregate."""
        return self.clients is not None or self.users is not None


def parse_filters(
    domains: str | None, clients: str | None, users: str | None, proxy: str | None
) -> BlockFilters:
    return BlockFilters(
        domains=parse_domains(domains),
        clients=parse_clients(clients),
        users=parse_users(users),
        proxy=proxy.strip() if proxy and proxy.strip() else None,
    )


def subnet_of(client_ip: str) -> str:
    """The /24 a client belongs to ("172.25.110.0/24"); non-IPv4 as-is."""
    parts = client_ip.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    return client_ip

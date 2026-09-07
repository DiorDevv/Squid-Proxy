# Product thesis

## What Squid Watch is

**Squid Watch is the system of record for what people on a network were allowed to
reach, what they were stopped from reaching, and who looked at that information.**

Its job is to produce **trustworthy, defensible evidence** about proxy activity —
evidence an auditor, a legal team, an HR investigation, or a regulator can rely on.
It is *not* a real-time SOC console, and it should stop trying to be one.

Every design question is settled by asking: *does this make the record more
complete, more accurate, more reproducible, or more accountable?* If not, it is out
of scope, however interesting.

## Why this framing and not "monitoring dashboard"

The codebase already leans this way and says so out loud:

- `ARCHITECTURE.md` — aggregates are read **only** from the database, never the ring
  buffer, "which is unacceptable for a compliance tool where the numbers need to be
  trustworthy." A single source of truth over live speed.
- Audit rows are written **in the same transaction** as the change they describe, so
  the two can never disagree.
- The audit table carries **no foreign key to `users`** on purpose — the entry must
  outlive the account, "the very record compliance needs."
- Raw detail is **encrypted and archived before it is purged**.
- `/api/health` surfaces silent-failure modes (`events_likely_lost`, aggregator
  backlog, unarchived purge) — i.e. it can *prove* there was no undetected data loss.

Those are the instincts of an evidence system. The "Network Operations Center"
language on top of them is borrowed from a different product and pulls the roadmap
toward live tiles, risk scores, and anomaly theatre that the foundation does not
actually serve. This document picks the side the foundation already chose.

## Consequences — what changes

### Emphasis drops (keep, stop investing, don't headline)

| Area | New status |
| --- | --- |
| "NOC" / live-console framing | Reframe as **Review**. Live view stays for triage; it is not the identity. |
| Branch **risk score** | A triage hint in a table. Stop adding signals. Never show a bare "score: 42" as a headline number — an unvalidated composite reads as authoritative and isn't. |
| **Config advisor** | Useful but orthogonal (it tunes `squid.conf`, not the record). One panel, parked. No expansion. |
| Analytics tab sprawl / "interesting charts" | Freeze. Every new chart must answer an evidence question, not be a visualisation. |
| Anomaly / alerting depth | Keep what exists. Not a headline capability. |
| Multi-instance / HA | **Lower priority.** A system of record needs *integrity and durability*, not live throughput. Single-process ingestion is acceptable **because** silent loss is already detectable (`/api/health`) and backups exist. Document the RTO; don't build Redis pub/sub yet. |

### Emphasis rises — roadmap, in order

1. **Read-access audit.** Log every view of a specific person's / client's / domain's
   activity, and every search and export, into the existing `audit_log_entries` with
   new `AuditAction` values (`CLIENT_ACTIVITY_VIEWED`, `EVENT_SEARCH_RUN`,
   `ANALYTICS_ACTOR_VIEWED`, `SUBJECT_DOSSIER_EXPORTED`). For a tool whose core
   function is watching employees, *"who looked at whom"* is the one thing that must
   be on the record and currently isn't. The plumbing already exists — this is cheap.

2. **Auditor role.** A third role between `viewer` and `admin`: everything a viewer
   sees, **plus** the audit log and the retention/policy pages, **minus** every
   mutation. The current two-role model can't express "read-only oversight,"
   which is exactly the role a compliance function occupies.

3. **Retention & lawful-basis surface.** A Settings page that states, in plain
   language, every retention window actually in effect (raw events, aggregates, ops
   aggregates, archives), what fields are collected, and the configured purpose.
   Mostly presentation over values `get_settings()` already holds — but it turns
   "we retain some stuff for a while" into a policy you can show.

4. **Data-subject tooling.**
   - *Subject access* — given an IP or username, produce one dossier (all events, all
     aggregates, watchlist hits, first/last seen) as a single verifiable export.
   - *Erasure* — hard-delete plus tombstone for one subject across `raw_events`, the
     aggregate tables, and the archive manifest.
   These are table-stakes wherever this tool touches the EU, not an "edge."

5. **Verifiable exports.** Sign every export (hash chain or detached signature) and
   ship a one-file verifier, so an export handed to a third party can be *proven*
   un-tampered. Builds directly on the export-job and archive-encryption work.

6. **Investigation search (the deferred "D"), reframed as casework.** Not a
   convenience feature — the evidence-gathering workspace. A saved query is a *case*;
   every run is audit-logged (see #1); results export as signed evidence (see #5).
   Build it *after* the audit and export plumbing it depends on, not before.

### Stays exactly as-is (already serving the thesis)

- DB-only aggregates as the single source of truth.
- Encrypted archiving before purge.
- Audit rows in the change's own transaction; no FK from audit to `users`.
- `/api/health` honest failure surface — reframe it internally as *evidence-integrity
  reporting*, because that is what it is.

## One-line pitch

> The defensible record of proxy access for your network — every request, every
> block, every person who reviewed it — reconcilable, exportable, and provable.

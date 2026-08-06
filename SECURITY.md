# Security Policy

## Supported versions

Only the latest commit on `main` (and the most recent tagged release) receives security fixes.
There's no long-term-support branch — upgrade to the latest release rather than expecting a
backport.

## Reporting a vulnerability

Please **do not open a public issue** for a security vulnerability — that discloses it to everyone,
including anyone running an unpatched copy, before a fix exists.

Instead, use GitHub's private vulnerability reporting:

1. Go to the [Security tab](https://github.com/DiorDevv/Squid-Proxy/security) of this repository.
2. Click **"Report a vulnerability"**.
3. Describe the issue: what's affected, how to reproduce it, and its impact. Attaching `GET
   /api/health`'s output is useful for anything related to log parsing or multi-branch ingestion,
   same as CONTRIBUTING.md notes for regular bug reports.

If private reporting isn't available to you for some reason, reach out to the maintainer directly
through their GitHub profile ([@DiorDevv](https://github.com/DiorDevv)) instead of filing a public
issue.

## What counts as a security issue here

This project handles browsing history and per-employee traffic data, so beyond the usual
(authentication bypass, injection, RCE), please also report:

- Any way to read another branch's data while scoped to one branch (see README's "Restricting a
  user to one branch")
- Any way a `viewer` role can perform an `admin`-only action
- Credential or session-token exposure (e.g. a log line, error message, or API response that
  leaks a password, JWT, or refresh token)
- A gap between what a security-relevant setting claims to do and what actually happens (e.g. an
  audit action that should be logged but isn't)

Non-issues: rate-limit tuning suggestions, missing security *hardening* (as opposed to an actual
vulnerability), and findings that require an attacker to already have admin access.

## Response expectations

This is a small project maintained outside of paid work hours — there's no SLA. Reports are
usually acknowledged within a few days. A confirmed vulnerability gets a fix and a GitHub Security
Advisory; credit is given to the reporter unless they ask otherwise.

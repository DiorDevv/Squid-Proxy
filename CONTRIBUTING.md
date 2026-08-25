# Contributing

Thanks for considering a contribution to Squid Watch.

## Reporting bugs / requesting features

Use the [issue templates](.github/ISSUE_TEMPLATE/) — they ask for the details that actually speed
up triage (steps to reproduce, expected vs. actual behavior, relevant logs). A bug report with
`GET /api/health`'s output attached is especially useful for anything related to log parsing or
multi-branch ingestion, since that endpoint exists specifically to surface those failure modes.

## Development setup

See the README's [Quick start (without Docker)](README.md#quick-start-without-docker) section for
getting the backend and frontend running locally. In short:

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # edit LOG_FILE_PATH, JWT_SECRET, ADMIN_PASSWORD
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Before opening a pull request

Run the same checks CI runs (`.github/workflows/ci.yml`) — a PR that fails these won't be
mergeable:

```bash
# Backend
cd backend && source .venv/bin/activate
pytest
ruff check .
mypy app

# Frontend
cd frontend
npm run build   # strict TypeScript build
npm run lint
npm run test
```

If your change touches the log parser, aggregator, retention, or archiving — anything where a
subtle bug could mean silently wrong or lost data for a compliance tool — please add a test that
would have caught it, not just a manual check.

## Pull request guidelines

- Keep PRs focused on one change; unrelated cleanup makes review harder and belongs in its own PR.
- Explain the *why* in the PR description, not just the *what* — the diff already shows what
  changed.
- If you're changing schema, add an Alembic migration (`backend/app/db/migrations/`) rather than
  relying on `init_db()`'s `create_all()`, which never alters an existing table — see the README's
  [Database migrations](README.md#database-migrations) section for why.
- New environment variables need an entry in `backend/.env.example` (or `frontend/.env.example`)
  with a comment explaining what they do, matching the existing style.

## Reporting a security issue

Please don't open a public issue for a security vulnerability. See if the repository has a
`SECURITY.md` with reporting instructions; otherwise, reach out to the maintainer directly through
their GitHub profile.

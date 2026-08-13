import os
from collections.abc import AsyncGenerator

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "admin-test-password-123")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.models import (  # noqa: F401
    client_aggregate,
    client_category_aggregate,
    client_hourly_aggregate,
    domain_aggregate,
    minute_aggregate,
    raw_event,
    refresh_token,
    user,
)
from app.models.db import Base, _ensure_aggregate_unique_indexes
from app.models.user import User, UserRole


@pytest_asyncio.fixture
async def db_engine():
    # StaticPool keeps a single underlying connection alive for the whole
    # engine, otherwise SQLite's `:memory:` database is connection-local and
    # each new pooled connection would see an empty, unrelated database.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Mirrors init_db(): the client_minute_aggregates expression-based
    # unique index can't be declared on the ORM model, so create_all alone
    # doesn't add it -- without it, bulk_upsert_sum's ON CONFLICT target
    # for that table wouldn't match any constraint on a fresh test DB.
    await _ensure_aggregate_unique_indexes(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_app(db_engine, monkeypatch):
    """The real FastAPI app, pointed at an isolated in-memory DB, with the
    log tailer / aggregator replaced by lightweight test doubles."""
    from app.models import db as db_module

    monkeypatch.setattr(db_module, "engine", db_engine)
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", session_factory)

    # aggregator/retention/bootstrap import AsyncSessionLocal directly at
    # module load time, so patching db_module alone doesn't reach them.
    import app.services.aggregator as aggregator_module
    import app.services.auth_bootstrap as bootstrap_module
    import app.services.retention as retention_module

    monkeypatch.setattr(bootstrap_module, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(aggregator_module, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(retention_module, "AsyncSessionLocal", session_factory)

    from app.main import create_app

    fastapi_app = create_app()

    # Replace the real lifespan with a lightweight test double so the app
    # boots without touching a real log file or spawning a real tailer.
    from contextlib import asynccontextmanager

    from app.core.security import WsTicketStore
    from app.services.event_store import RingBuffer
    from app.services.ws_manager import WebSocketManager

    @asynccontextmanager
    async def test_lifespan(_app):
        await db_module.init_db()
        await bootstrap_module.bootstrap_admin_user()
        _app.state.ring_buffer = RingBuffer(max_events=1000)
        _app.state.ws_manager = WebSocketManager()
        _app.state.ws_ticket_store = WsTicketStore(ttl_seconds=30)
        _app.state.log_tailers = {"default": _NullTailer()}
        yield

    fastapi_app.router.lifespan_context = test_lifespan

    async with test_lifespan(fastapi_app):
        yield fastapi_app


class _NullTailer:
    is_alive = False
    lines_seen = 0
    lines_parsed = 0


@pytest_asyncio.fixture
async def app_client(test_app) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def admin_token(app_client: AsyncClient) -> str:
    response = await app_client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-test-password-123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def viewer_token(app_client: AsyncClient, db_session: AsyncSession) -> str:
    db_session.add(
        User(email="viewer@example.com", hashed_password=hash_password("viewer-pass-123"), role=UserRole.VIEWER)
    )
    await db_session.commit()
    response = await app_client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "viewer-pass-123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def branch_a_admin_token(app_client: AsyncClient, db_session: AsyncSession) -> str:
    """An admin scoped to "branch-a" only -- for branch-isolation regression
    tests, where a second branch's users/exports/settings must be invisible
    and unreachable to this account (see api/deps.resolve_branch and the
    equivalent per-service enforcement in user_service.py)."""
    db_session.add(
        User(
            email="branch-a-admin@example.com",
            hashed_password=hash_password("branch-a-admin-pass-123"),
            role=UserRole.ADMIN,
            branch="branch-a",
        )
    )
    await db_session.commit()
    response = await app_client.post(
        "/api/auth/login",
        json={"email": "branch-a-admin@example.com", "password": "branch-a-admin-pass-123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter.reset()
    yield


@pytest.fixture
def auth_headers():
    def _make(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    return _make

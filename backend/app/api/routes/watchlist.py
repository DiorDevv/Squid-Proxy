from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.permissions import WATCHLIST
from app.schemas.watchlist import (
    CreateWatchlistEntryRequest,
    UpdateWatchlistEntryRequest,
    WatchlistEntryOut,
)
from app.services import watchlist_service
from app.services.watchlist_service import WatchlistConflict

router = APIRouter(
    prefix="/api/watchlist", tags=["watchlist"], dependencies=[Depends(require_permission(WATCHLIST))]
)


def _resolve_branch_for_write(requested: str, current_user: CurrentUser) -> str:
    """A branch-limited account may only create/scope entries within its own
    branches (or the shared "any branch" scope). An unrestricted one may
    target any branch, or "" for all."""
    if not current_user.is_restricted:
        return requested
    if requested and not current_user.can_access(requested):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You cannot watch another branch."
        )
    return requested  # "" (any) or one of their own branches


@router.get("", response_model=list[WatchlistEntryOut])
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[WatchlistEntryOut]:
    return await watchlist_service.list_entries(db, current_user.scope)


@router.post("", response_model=WatchlistEntryOut, status_code=status.HTTP_201_CREATED)
async def create_watchlist_entry(
    body: CreateWatchlistEntryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> WatchlistEntryOut:
    branch = _resolve_branch_for_write(body.branch, current_user)
    try:
        return await watchlist_service.create_entry(
            db, body.target_type, body.value, body.note, branch, current_user.user_id
        )
    except WatchlistConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That target is already on the watchlist."
        ) from exc


@router.patch("/{entry_id}", response_model=WatchlistEntryOut)
async def update_watchlist_entry(
    entry_id: str,
    body: UpdateWatchlistEntryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> WatchlistEntryOut:
    row = await watchlist_service.get_entry(db, entry_id)
    _assert_visible(row, current_user)
    updated = await watchlist_service.set_active(db, entry_id, body.active)
    assert updated is not None
    return updated


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    row = await watchlist_service.get_entry(db, entry_id)
    _assert_visible(row, current_user)
    await watchlist_service.delete_entry(db, entry_id)


def _assert_visible(row: object, current_user: CurrentUser) -> None:
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found.")
    entry_branch = getattr(row, "branch", "")
    if entry_branch and not current_user.can_access(entry_branch):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your branch.")

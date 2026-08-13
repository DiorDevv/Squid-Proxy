from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.schemas.users import (
    UserBranchUpdateRequest,
    UserCreateRequest,
    UserPasswordResetRequest,
    UserRoleUpdateRequest,
    UserSummary,
)
from app.services import user_service

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserSummary])
async def read_users(
    db: AsyncSession = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)
) -> list[UserSummary]:
    users = await user_service.list_users(db, actor_branch=current_user.branch)
    return [UserSummary.model_validate(u, from_attributes=True) for u in users]


@router.post("", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def create_user(
    request: Request,
    body: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UserSummary:
    user = await user_service.create_user(
        db,
        body.email,
        body.password,
        body.role,
        current_user.user_id,
        branch=body.branch,
        actor_branch=current_user.branch,
    )
    return UserSummary.model_validate(user, from_attributes=True)


@router.patch("/{user_id}/role", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def update_user_role(
    request: Request,
    user_id: str,
    body: UserRoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UserSummary:
    user = await user_service.update_role(
        db, user_id, body.role, current_user.user_id, actor_branch=current_user.branch
    )
    return UserSummary.model_validate(user, from_attributes=True)


@router.patch("/{user_id}/branch", response_model=UserSummary)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def update_user_branch(
    request: Request,
    user_id: str,
    body: UserBranchUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> UserSummary:
    user = await user_service.update_branch(
        db, user_id, body.branch, current_user.user_id, actor_branch=current_user.branch
    )
    return UserSummary.model_validate(user, from_attributes=True)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def reset_user_password(
    request: Request,
    user_id: str,
    body: UserPasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    await user_service.reset_password(
        db, user_id, body.new_password, current_user.user_id, actor_branch=current_user.branch
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def delete_user(
    request: Request,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    await user_service.delete_user(db, user_id, current_user.user_id, actor_branch=current_user.branch)

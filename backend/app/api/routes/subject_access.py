from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin, resolve_branch
from app.models.audit_log import AuditAction
from app.schemas.subject_access import SubjectDossierResponse, SubjectType
from app.services import audit_service, subject_access_service

router = APIRouter(prefix="/api", tags=["subject-access"], dependencies=[Depends(require_admin)])


@router.get("/subject-access/dossier", response_model=SubjectDossierResponse)
async def read_subject_dossier(
    subject_type: SubjectType = Query(),
    value: str = Query(min_length=1, max_length=255),
    branch: str | None = Depends(resolve_branch),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SubjectDossierResponse:
    """One signed document covering everything this deployment currently
    knows about one client IP or proxy-auth user (docs/PRODUCT.md #4) --
    admin-only because it includes watchlist status, itself an admin-only
    read (see watchlist.py). Every generation is audited (not
    deduplicated like the other read-access actions -- this is always a
    deliberate act, never a background poll)."""
    dossier = await subject_access_service.build_dossier(db, subject_type, value, branch)
    await audit_service.record_read_access(
        db,
        action=AuditAction.SUBJECT_DOSSIER_EXPORTED,
        actor_user_id=current_user.user_id,
        branch=branch,
        detail=f"{subject_type}={value}, generated_at={dossier.generated_at.isoformat()}",
    )
    return dossier

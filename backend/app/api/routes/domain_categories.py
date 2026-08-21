from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.schemas.domains import (
    DomainCategoryImportError,
    DomainCategoryImportResponse,
    DomainCategoryOut,
    SetDomainCategoryRequest,
)
from app.services import domain_category_service

router = APIRouter(
    prefix="/api/domain-categories", tags=["domain-categories"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[DomainCategoryOut])
async def read_domain_categories(db: AsyncSession = Depends(get_db)) -> list[DomainCategoryOut]:
    rows = await domain_category_service.list_all(db)
    return [DomainCategoryOut.model_validate(row, from_attributes=True) for row in rows]


@router.get("/export")
async def export_domain_categories(db: AsyncSession = Depends(get_db)) -> Response:
    rows = await domain_category_service.list_all(db)
    csv_text = domain_category_service.export_to_csv(rows)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="domain_categories.csv"'},
    )


@router.post("/import", response_model=DomainCategoryImportResponse)
@limiter.limit(get_settings().SENSITIVE_ACTION_RATE_LIMIT)
async def import_domain_categories(
    request: Request,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DomainCategoryImportResponse:
    raw = await file.read()
    csv_text = raw.decode("utf-8", errors="replace")
    applied, errors = await domain_category_service.import_from_csv(db, csv_text, current_user.user_id)
    return DomainCategoryImportResponse(
        applied=applied,
        errors=[
            DomainCategoryImportError(row=row, domain=domain, reason=reason)
            for row, domain, reason in errors
        ],
    )


@router.put("/{domain}", response_model=DomainCategoryOut)
async def set_domain_category(
    domain: str,
    body: SetDomainCategoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DomainCategoryOut:
    row = await domain_category_service.set_category(db, domain, body.category, current_user.user_id)
    return DomainCategoryOut.model_validate(row, from_attributes=True)

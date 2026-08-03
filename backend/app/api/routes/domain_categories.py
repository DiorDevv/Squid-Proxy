from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db, require_admin
from app.schemas.domains import DomainCategoryOut, SetDomainCategoryRequest
from app.services import domain_category_service

router = APIRouter(
    prefix="/api/domain-categories", tags=["domain-categories"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[DomainCategoryOut])
async def read_domain_categories(db: AsyncSession = Depends(get_db)) -> list[DomainCategoryOut]:
    rows = await domain_category_service.list_all(db)
    return [DomainCategoryOut.model_validate(row, from_attributes=True) for row in rows]


@router.put("/{domain}", response_model=DomainCategoryOut)
async def set_domain_category(
    domain: str,
    body: SetDomainCategoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DomainCategoryOut:
    row = await domain_category_service.set_category(db, domain, body.category, current_user.user_id)
    return DomainCategoryOut.model_validate(row, from_attributes=True)

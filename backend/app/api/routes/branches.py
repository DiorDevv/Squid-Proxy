"""Lists configured log sources/branches (see Settings.effective_log_sources)
so the frontend can populate a branch filter without hardcoding it. Config
is the source of truth here, not a DB table -- branches are an infra/
deployment concern (which log file(s) this instance tails), same category
as LOG_FILE_PATH/DATABASE_URL, not admin-editable business policy.
"""

from fastapi import APIRouter, Depends

from app.api.deps import require_any_role
from app.core.config import get_settings
from app.schemas.branches import Branch, BranchesResponse

router = APIRouter(prefix="/api", tags=["branches"], dependencies=[Depends(require_any_role)])


@router.get("/branches", response_model=BranchesResponse)
async def read_branches() -> BranchesResponse:
    settings = get_settings()
    items = [
        Branch(slug=source.branch, label=source.branch.replace("_", " ").replace("-", " ").title())
        for source in settings.effective_log_sources
    ]
    return BranchesResponse(items=items)

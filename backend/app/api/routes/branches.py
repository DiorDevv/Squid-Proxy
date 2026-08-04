"""Lists configured log sources/branches (see Settings.effective_log_sources)
so the frontend can populate a branch filter without hardcoding it. Config
is the source of truth here, not a DB table -- branches are an infra/
deployment concern (which log file(s) this instance tails), same category
as LOG_FILE_PATH/DATABASE_URL, not admin-editable business policy.
"""

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_current_user, require_any_role
from app.core.config import get_settings
from app.schemas.branches import Branch, BranchesResponse


def _to_branch(tag: str) -> Branch:
    return Branch(slug=tag, label=tag.replace("_", " ").replace("-", " ").title())


router = APIRouter(prefix="/api", tags=["branches"], dependencies=[Depends(require_any_role)])


@router.get("/branches", response_model=BranchesResponse)
async def read_branches(current_user: CurrentUser = Depends(get_current_user)) -> BranchesResponse:
    # A branch-scoped user only ever sees their own branch here -- this is
    # what makes the frontend's BranchSelector self-hide for them (it
    # already hides whenever there's <= 1 item, the same logic that hides
    # it for any single-branch deployment).
    if current_user.branch is not None:
        return BranchesResponse(items=[_to_branch(current_user.branch)])

    settings = get_settings()
    items = [_to_branch(source.branch) for source in settings.effective_log_sources]
    return BranchesResponse(items=items)

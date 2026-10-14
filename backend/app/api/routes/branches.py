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
    # A branch-limited user only ever sees their own branches here, in
    # config order -- with one, the frontend's BranchSelector self-hides (it
    # hides whenever there's <= 1 item, the same logic that hides it for any
    # single-branch deployment); with several it offers just those.
    settings = get_settings()
    items = [
        _to_branch(branch) for branch in settings.effective_branches if current_user.can_access(branch)
    ]
    if current_user.branches is not None:
        # A branch dropped from config since the account was set up still
        # shows, so the account isn't left with an empty picker.
        configured = set(settings.effective_branches)
        items += [_to_branch(branch) for branch in current_user.branches if branch not in configured]
    return BranchesResponse(items=items)

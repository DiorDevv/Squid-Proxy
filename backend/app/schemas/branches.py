from pydantic import BaseModel


class Branch(BaseModel):
    slug: str
    label: str


class BranchesResponse(BaseModel):
    items: list[Branch]

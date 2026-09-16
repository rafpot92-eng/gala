from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class ArticleUpdate(BaseModel):

    title: str = Field(
        min_length=1,
        max_length=500,
    )

    subtitle: str | None = None

    content: str = Field(
        min_length=1
    )

    change_summary: str | None = None

    version: int


class StatusChange(BaseModel):

    notes: str | None = None

    quality_score: int | None = Field(
        default=None, ge=1, le=5,
    )

    feedback: str | None = None


class SearchRequest(BaseModel):

    query: str

    limit: int = 10
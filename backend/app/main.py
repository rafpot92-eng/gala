from fastapi import (
    FastAPI,
    Depends,
)

from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .articles import router as articles_router
from .users import router as users_router
from .auth import require_role
from .db import get_connection


app = FastAPI(
    title="Meczyki Editorial API",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        settings.frontend_url
    ],

    allow_credentials=True,

    allow_methods=[
        "*"
    ],

    allow_headers=[
        "*"
    ],
)


app.include_router(
    users_router
)

app.include_router(
    articles_router
)


@app.get("/health")
def health():

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute("SELECT 1")

            cur.fetchone()

    return {
        "status": "ok"
    }


@app.get("/api/search")
def search(
    q: str,
    user=Depends(
        require_role(
            "viewer",
            "editor",
            "publisher",
        )
    ),
):

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    title,
                    subtitle,
                    category,
                    status,
                    created_at
                FROM generated_articles
                WHERE
                    title ILIKE %s
                    OR content ILIKE %s
                    OR subtitle ILIKE %s
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (
                    f"%{q}%",
                    f"%{q}%",
                    f"%{q}%",
                ),
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "title": row[1],
            "subtitle": row[2],
            "category": row[3],
            "status": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]
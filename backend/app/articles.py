from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from .auth import require_role
from .db import get_connection
from .schemas import (
    ArticleUpdate,
    StatusChange,
)


router = APIRouter(
    prefix="/api/generated",
    tags=["generated"],
)


def get_article(article_id: int):

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    title,
                    subtitle,
                    content,
                    category,
                    status,
                    word_count,
                    created_at,
                    updated_at,
                    published_at,
                    version
                FROM generated_articles
                WHERE id = %s
                """,
                (article_id,),
            )

            row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "title": row[1],
        "subtitle": row[2],
        "content": row[3],
        "category": row[4],
        "status": row[5],
        "word_count": row[6],
        "created_at": row[7],
        "updated_at": row[8],
        "published_at": row[9],
        "version": row[10],
    }


def write_audit_log(
    article_id,
    action,
    actor_id=None,
    old_status=None,
    new_status=None,
    notes=None,
    metadata=None,
):

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO editorial_audit_log (
                    article_id,
                    action,
                    old_status,
                    new_status,
                    actor_id,
                    notes,
                    metadata
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    article_id,
                    action,
                    old_status,
                    new_status,
                    actor_id,
                    notes,
                    metadata,
                ),
            )

        conn.commit()


@router.get("")
def list_articles(
    status: str | None = None,
    user=Depends(require_role(
        "viewer",
        "editor",
        "publisher",
    )),
):

    with get_connection() as conn:

        with conn.cursor() as cur:

            if status:

                cur.execute(
                    """
                    SELECT
                        id,
                        title,
                        subtitle,
                        category,
                        status,
                        word_count,
                        created_at,
                        updated_at
                    FROM generated_articles
                    WHERE status = %s
                    ORDER BY created_at DESC
                    LIMIT 100
                    """,
                    (status,),
                )

            else:

                cur.execute(
                    """
                    SELECT
                        id,
                        title,
                        subtitle,
                        category,
                        status,
                        word_count,
                        created_at,
                        updated_at
                    FROM generated_articles
                    ORDER BY created_at DESC
                    LIMIT 100
                    """
                )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "title": row[1],
            "subtitle": row[2],
            "category": row[3],
            "status": row[4],
            "word_count": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }
        for row in rows
    ]


@router.get("/{article_id}")
def get_article_endpoint(
    article_id: int,
    user=Depends(require_role(
        "viewer",
        "editor",
        "publisher",
    )),
):

    article = get_article(article_id)

    if not article:

        raise HTTPException(
            status_code=404,
            detail="Article not found",
        )

    return article


@router.patch("/{article_id}")
def edit_article(
    article_id: int,
    payload: ArticleUpdate,
    user=Depends(require_role(
        "editor",
        "publisher",
    )),
):

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    title,
                    subtitle,
                    content,
                    status,
                    version
                FROM generated_articles
                WHERE id = %s
                FOR UPDATE
                """,
                (article_id,),
            )

            row = cur.fetchone()

            if not row:

                raise HTTPException(
                    status_code=404,
                    detail="Article not found",
                )

            old_title = row[0]
            old_subtitle = row[1]
            old_content = row[2]
            article_status = row[3]
            current_version = row[4]

            if article_status not in {
                "draft",
                "ready_for_review",
            }:

                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Published or approved "
                        "articles cannot be edited."
                    ),
                )

            if payload.version != current_version:

                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Article was modified by "
                        "another user. Reload it."
                    ),
                )

            cur.execute(
                """
                SELECT COALESCE(
                    MAX(revision_number),
                    0
                )
                FROM article_revisions
                WHERE article_id = %s
                """,
                (article_id,),
            )

            revision_number = (
                cur.fetchone()[0] + 1
            )

            cur.execute(
                """
                INSERT INTO article_revisions (
                    article_id,
                    revision_number,
                    title,
                    subtitle,
                    content,
                    editor_id,
                    change_summary
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    article_id,
                    revision_number,
                    old_title,
                    old_subtitle,
                    old_content,
                    user["id"],
                    payload.change_summary,
                ),
            )

            cur.execute(
                """
                UPDATE generated_articles
                SET
                    title = %s,
                    subtitle = %s,
                    content = %s,
                    version = version + 1,
                    word_count =
                        array_length(
                            regexp_split_to_array(
                                trim(%s),
                                '\\s+'
                            ),
                            1
                        ),
                    updated_at = NOW()
                WHERE id = %s
                  AND version = %s
                """,
                (
                    payload.title,
                    payload.subtitle,
                    payload.content,
                    payload.content,
                    article_id,
                    current_version,
                ),
            )

        conn.commit()

    write_audit_log(
        article_id=article_id,
        action="edit",
        actor_id=user["id"],
        notes=payload.change_summary,
        metadata={
            "revision": revision_number,
        },
    )

    return get_article(article_id)


@router.get("/{article_id}/revisions")
def revisions(
    article_id: int,
    user=Depends(require_role(
        "viewer",
        "editor",
        "publisher",
    )),
):

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    r.id,
                    r.revision_number,
                    r.title,
                    r.subtitle,
                    r.content,
                    r.change_summary,
                    r.created_at,
                    u.name,
                    u.email
                FROM article_revisions r
                LEFT JOIN users u
                    ON u.id = r.editor_id
                WHERE r.article_id = %s
                ORDER BY r.revision_number DESC
                """,
                (article_id,),
            )

            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "revision_number": row[1],
            "title": row[2],
            "subtitle": row[3],
            "content": row[4],
            "change_summary": row[5],
            "created_at": row[6],
            "editor_name": row[7],
            "editor_email": row[8],
        }
        for row in rows
    ]


def change_status(
    article_id,
    new_status,
    user,
    notes=None,
):

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT status
                FROM generated_articles
                WHERE id = %s
                FOR UPDATE
                """,
                (article_id,),
            )

            row = cur.fetchone()

            if not row:

                raise HTTPException(
                    status_code=404,
                    detail="Article not found",
                )

            old_status = row[0]

            transitions = {
                "ready_for_review": {
                    "draft",
                },
                "draft": {
                    "ready_for_review",
                },
                "approved": {
                    "ready_for_review",
                },
                "published": {
                    "approved",
                },
            }

            allowed = transitions.get(
                new_status,
                set(),
            )

            if old_status not in allowed:

                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Cannot move article "
                        f"from {old_status} "
                        f"to {new_status}"
                    ),
                )

            published_sql = ""

            if new_status == "published":
                published_sql = (
                    ", published_at = NOW()"
                )

            cur.execute(
                f"""
                UPDATE generated_articles
                SET
                    status = %s,
                    updated_at = NOW()
                    {published_sql}
                WHERE id = %s
                """,
                (
                    new_status,
                    article_id,
                ),
            )

        conn.commit()

    write_audit_log(
        article_id=article_id,
        action=f"status_change:{new_status}",
        actor_id=user["id"],
        old_status=old_status,
        new_status=new_status,
        notes=notes,
    )

    return get_article(article_id)


@router.post("/{article_id}/review")
def send_to_review(
    article_id: int,
    payload: StatusChange | None = None,
    user=Depends(require_role(
        "editor",
        "publisher",
    )),
):

    return change_status(
        article_id,
        "ready_for_review",
        user,
        payload.notes if payload else None,
    )


@router.post("/{article_id}/reject")
def reject_article(
    article_id: int,
    payload: StatusChange | None = None,
    user=Depends(require_role(
        "editor",
        "publisher",
    )),
):

    return change_status(
        article_id,
        "draft",
        user,
        payload.notes if payload else None,
    )


@router.post("/{article_id}/approve")
def approve_article(
    article_id: int,
    payload: StatusChange | None = None,
    user=Depends(require_role(
        "editor",
        "publisher",
    )),
):

    return change_status(
        article_id,
        "approved",
        user,
        payload.notes if payload else None,
    )


@router.post("/{article_id}/publish")
def publish_article(
    article_id: int,
    payload: StatusChange | None = None,
    user=Depends(require_role(
        "publisher",
    )),
):

    return change_status(
        article_id,
        "published",
        user,
        payload.notes if payload else None,
    )
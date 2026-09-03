from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt

from fastapi import (
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials

from authlib.integrations.starlette_client import OAuth

from .config import settings
from .db import get_connection


oauth = OAuth()


DATABRICKS_AUTHORIZE_URL = (
    f"{settings.databricks_workspace_url}"
    "/oidc/v1/authorize"
)

DATABRICKS_TOKEN_URL = (
    f"{settings.databricks_workspace_url}"
    "/oidc/v1/token"
)

DATABRICKS_ISSUER = (
    settings.databricks_workspace_url
    "/oidc"
)


oauth.register(
    name="databricks",

    client_id=settings.databricks_client_id,

    client_secret=settings.databricks_client_secret,

    authorize_url=DATABRICKS_AUTHORIZE_URL,

    access_token_url=DATABRICKS_TOKEN_URL,

    client_kwargs={
        "scope": (
            "openid email profile"
        ),
    },
)


SESSION_COOKIE = "meczyki_session"


def create_session_token(
    user: dict,
) -> str:

    expires = (
        datetime.now(
            timezone.utc
        )
        + timedelta(
            minutes=settings.jwt_expire_minutes
        )
    )

    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "exp": expires,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm="HS256",
    )


def set_session_cookie(
    response,
    token: str,
):

    response.set_cookie(
        key=SESSION_COOKIE,

        value=token,

        httponly=True,

        secure=settings.cookie_secure,

        samesite=settings.cookie_samesite,

        domain=(
            settings.cookie_domain
            or None
        ),

        max_age=(
            settings.jwt_expire_minutes
            * 60
        ),

        path="/",
    )


def clear_session_cookie(
    response,
):

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        domain=(
            settings.cookie_domain
            or None
        ),
    )


def get_user_by_email(
    email: str,
):

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    email,
                    name,
                    role,
                    is_active
                FROM users
                WHERE LOWER(email) = LOWER(%s)
                """,
                (email,),
            )

            row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "email": row[1],
        "name": row[2],
        "role": row[3],
        "is_active": row[4],
    }


def get_or_create_user(
    email: str,
    name: str | None,
):

    existing = get_user_by_email(email)

    if existing:

        if not existing["is_active"]:
            raise HTTPException(
                status_code=403,
                detail="User account disabled",
            )

        return existing

    #
    # IMPORTANT:
    #
    # New users are NOT editors automatically.
    #
    # They get viewer access and an administrator
    # can promote them to editor/publisher.
    #

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                INSERT INTO users (
                    email,
                    name,
                    role
                )
                VALUES (
                    %s,
                    %s,
                    'viewer'
                )
                RETURNING
                    id,
                    email,
                    name,
                    role,
                    is_active
                """,
                (
                    email,
                    name,
                ),
            )

            row = cur.fetchone()

        conn.commit()

    return {
        "id": row[0],
        "email": row[1],
        "name": row[2],
        "role": row[3],
        "is_active": row[4],
    }


async def login(
    request: Request,
):

    redirect_uri = (
        f"{settings.backend_url}"
        "/api/auth/callback"
    )

    return await oauth.databricks.authorize_redirect(
        request,
        redirect_uri,
        scope="openid email profile",
    )


async def callback(
    request: Request,
):

    try:

        token = (
            await oauth.databricks
            .authorize_access_token(
                request
            )
        )

    except Exception:

        raise HTTPException(
            status_code=401,
            detail=(
                "Databricks authentication failed"
            ),
        )

    #
    # Authlib/OIDC will expose user information
    # through the userinfo / id_token depending
    # on the provider response.
    #

    userinfo = token.get("userinfo")

    if not userinfo:

        try:
            userinfo = (
                await oauth.databricks
                .userinfo(
                    token=token
                )
            )
        except Exception:

            raise HTTPException(
                status_code=401,
                detail=(
                    "Could not retrieve "
                    "Databricks user identity"
                ),
            )

    email = (
        userinfo.get("email")
        or userinfo.get("preferred_username")
    )

    if not email:

        raise HTTPException(
            status_code=400,
            detail=(
                "Databricks did not provide "
                "an email/username claim"
            ),
        )

    name = (
        userinfo.get("name")
        or userinfo.get("preferred_username")
        or email
    )

    user = get_or_create_user(
        email=email,
        name=name,
    )

    session_token = create_session_token(
        user
    )

    response = RedirectResponse(
        url=(
            f"{settings.frontend_url}"
            "/"
        ),
        status_code=302,
    )

    set_session_cookie(
        response,
        session_token,
    )

    return response


def get_current_user(
    request: Request,
):

    token = request.cookies.get(
        SESSION_COOKIE
    )

    if not token:

        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    try:

        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )

        user_id = int(
            payload["sub"]
        )

    except (
        jwt.InvalidTokenError,
        KeyError,
        ValueError,
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid session",
        )

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    email,
                    name,
                    role,
                    is_active
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )

            row = cur.fetchone()

    if not row:

        raise HTTPException(
            status_code=401,
            detail="User no longer exists",
        )

    if not row[4]:

        raise HTTPException(
            status_code=403,
            detail="User account disabled",
        )

    return {
        "id": row[0],
        "email": row[1],
        "name": row[2],
        "role": row[3],
    }


def require_role(
    *roles: str,
):

    def dependency(
        user=Depends(
            get_current_user
        ),
    ):

        if user["role"] not in roles:

            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions",
            )

        return user

    return dependency
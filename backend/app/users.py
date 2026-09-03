from fastapi import (
    APIRouter,
    Depends,
    Request,
)

from fastapi.responses import JSONResponse

from .auth import (
    callback,
    clear_session_cookie,
    get_current_user,
    login,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


@router.get("/login")
async def login_endpoint(
    request: Request,
):

    return await login(request)


@router.get("/callback")
async def callback_endpoint(
    request: Request,
):

    return await callback(request)


@router.get("/me")
def me(
    user=Depends(
        get_current_user
    ),
):

    return user


@router.post("/logout")
def logout():

    response = JSONResponse(
        {
            "ok": True
        }
    )

    clear_session_cookie(
        response
    )

    return response
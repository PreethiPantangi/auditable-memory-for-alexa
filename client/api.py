import logging

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from client.orchestrator import handle_user_message
from security.demo_access import (
    COOKIE_NAME,
    COOKIE_SECURE,
    SESSION_MAX_AGE,
    create_demo_session,
    require_demo_access,
    verify_demo_password,
)
from security.demo_users import is_allowed_demo_user

from .memory_api import router as memory_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Auditable Memory API")

app.include_router(
    memory_router,
    dependencies=[Depends(require_demo_access)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://auditable-memory-interface.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class DemoLoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    user_id: str
    message: str


def validate_demo_user(user_id: str) -> str:
    if not is_allowed_demo_user(user_id):
        raise HTTPException(
            status_code=403,
            detail="Demo user not allowed.",
        )

    return user_id


def validate_session_user(
    requested_user_id: str,
    authenticated_user_id: str,
) -> str:
    if requested_user_id != authenticated_user_id:
        raise HTTPException(
            status_code=403,
            detail="Access to another demo user's data is forbidden.",
        )

    return authenticated_user_id


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/demo/login")
async def demo_login(
    request: DemoLoginRequest,
    response: Response,
):
    username = request.username.strip()

    if not is_allowed_demo_user(username) or not verify_demo_password(request.password):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password.",
        )

    session_token = create_demo_session(username)

    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
        path="/",
    )

    return {
        "authenticated": True,
        "username": username,
    }


@app.get("/demo/session")
async def demo_session(
    username: str = Depends(require_demo_access),
):
    return {
        "authenticated": True,
        "username": username,
    }


@app.post("/demo/logout")
async def demo_logout(response: Response):
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=COOKIE_SECURE,
        httponly=True,
    )

    return {"authenticated": False}


@app.post("/chat")
async def chat(
    request: ChatRequest,
    username: str = Depends(require_demo_access),
):
    user_id = validate_demo_user(request.user_id)

    user_id = validate_session_user(
        requested_user_id=user_id,
        authenticated_user_id=username,
    )

    try:
        result = await handle_user_message(
            user_id=user_id,
            message=request.message,
        )
        return result

    except Exception:
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to process request",
        )

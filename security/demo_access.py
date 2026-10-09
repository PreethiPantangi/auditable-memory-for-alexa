import os
import secrets
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from itsdangerous import (
    BadSignature,
    SignatureExpired,
    URLSafeTimedSerializer,
)

from security.demo_users import is_allowed_demo_user

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEMO_ACCESS_PASSWORD = os.getenv("DEMO_ACCESS_PASSWORD", "")
DEMO_SESSION_SECRET = os.getenv("DEMO_SESSION_SECRET", "")
COOKIE_SECURE = os.getenv("DEMO_COOKIE_SECURE", "false").lower() == "true"

SESSION_MAX_AGE = 60 * 60 * 8
COOKIE_NAME = "adh_demo_session"

if len(DEMO_ACCESS_PASSWORD) < 32 or len(DEMO_SESSION_SECRET) < 32:
    raise RuntimeError("Configure strong DEMO_ACCESS_PASSWORD and DEMO_SESSION_SECRET.")

serializer = URLSafeTimedSerializer(
    DEMO_SESSION_SECRET,
    salt="adh-demo-access-v2",
)


def verify_demo_password(password: str) -> bool:
    return secrets.compare_digest(
        password,
        DEMO_ACCESS_PASSWORD,
    )


def create_demo_session(username: str) -> str:
    if not is_allowed_demo_user(username):
        raise ValueError("Demo user not allowed.")

    return serializer.dumps(
        {
            "access": "demo",
            "username": username,
            "issued_at": int(time.time()),
        }
    )


def require_demo_access(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Demo access required.",
        )

    try:
        payload = serializer.loads(
            token,
            max_age=SESSION_MAX_AGE,
        )
    except (BadSignature, SignatureExpired):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired demo session.",
        )

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=401,
            detail="Invalid demo session payload.",
        )

    if payload.get("access") != "demo":
        raise HTTPException(
            status_code=403,
            detail="Demo access denied.",
        )

    username = payload.get("username")

    if not isinstance(username, str) or not is_allowed_demo_user(username):
        raise HTTPException(
            status_code=403,
            detail="Invalid demo session user.",
        )

    return username


def require_matching_demo_user(
    user_id: str,
    username: str = Depends(require_demo_access),
) -> str:
    if user_id != username:
        raise HTTPException(
            status_code=403,
            detail="Access to another user's memories is forbidden.",
        )

    return username

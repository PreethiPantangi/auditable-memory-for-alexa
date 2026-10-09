import os


def get_allowed_demo_users() -> frozenset[str]:
    raw = os.getenv("ALLOWED_DEMO_USERS", "")

    users = frozenset(user.strip() for user in raw.split(",") if user.strip())

    if not users:
        raise RuntimeError("ALLOWED_DEMO_USERS must contain at least one user.")

    return users


ALLOWED_DEMO_USERS = get_allowed_demo_users()


def is_allowed_demo_user(user_id: str) -> bool:
    return isinstance(user_id, str) and user_id in ALLOWED_DEMO_USERS

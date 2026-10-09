from typing import Any


def success_response(data: Any) -> dict:
    response = {"success": True, "data": data}

    return response


def error_response(code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}

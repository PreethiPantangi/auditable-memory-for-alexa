import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from client.mcp_client import call_mcp_tool
from security.demo_access import require_matching_demo_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["Insights"])


class InsightActionRequest(BaseModel):
    user_id: str = Field(min_length=1)


async def execute_insight_tool(
    tool_name: str,
    arguments: dict,
) -> dict:
    try:
        result = await call_mcp_tool(
            tool_name=tool_name,
            args=arguments,
        )
    except Exception:
        logger.exception("Insight MCP call failed: %s", tool_name)
        raise HTTPException(
            status_code=502,
            detail="Insight service unavailable.",
        )

    # Your MCP tools return application-level envelopes.
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=502,
            detail="Invalid insight service response.",
        )

    if result.get("success") is True:
        return result.get("data") or {}

    error = result.get("error") or {}
    code = error.get("code", "INSIGHT_OPERATION_FAILED")

    status_codes = {
        "INSIGHT_NOT_FOUND": 404,
        "INSIGHT_ALREADY_REJECTED": 409,
        "INSIGHT_ALREADY_CONFIRMED": 409,
        "DEMO_USER_NOT_ALLOWED": 403,
        "UNSUPPORTED_DOMAIN": 400,
    }

    raise HTTPException(
        status_code=status_codes.get(code, 502),
        detail={
            "code": code,
            "message": error.get("message", "Insight operation failed."),
        },
    )


@router.get("")
async def list_insights(
    user_id: str = Depends(require_matching_demo_user),
):
    return await execute_insight_tool(
        "list_insights",
        {"user_id": user_id},
    )


@router.get("/{insight_id}/evidence")
async def get_insight_evidence(
    insight_id: int,
    user_id: str = Depends(require_matching_demo_user),
):
    return await execute_insight_tool(
        "get_insight_evidence",
        {
            "user_id": user_id,
            "insight_id": insight_id,
        },
    )


@router.post("/derive")
async def derive_insights(
    request: InsightActionRequest,
    user_id: str = Depends(require_matching_demo_user),
):
    if request.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Access to another demo user's data is forbidden.",
        )

    return await execute_insight_tool(
        "save_insight_candidates",
        {"user_id": user_id},
    )


@router.post("/{insight_id}/confirm")
async def confirm_insight(
    insight_id: int,
    request: InsightActionRequest,
    user_id: str = Depends(require_matching_demo_user),
):
    if request.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Access to another demo user's data is forbidden.",
        )

    return await execute_insight_tool(
        "confirm_insight",
        {
            "user_id": user_id,
            "insight_id": insight_id,
        },
    )


@router.post("/{insight_id}/reject")
async def reject_insight(
    insight_id: int,
    request: InsightActionRequest,
    user_id: str = Depends(require_matching_demo_user),
):
    if request.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Access to another demo user's data is forbidden.",
        )

    return await execute_insight_tool(
        "reject_insight",
        {
            "user_id": user_id,
            "insight_id": insight_id,
        },
    )

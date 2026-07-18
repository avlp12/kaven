"""에이전트 라우터 — AI 에이전트 연동용 매니페스트/컨텍스트/이벤트 쿼리."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from src.kaven.agent_service import build_agent_context, build_agent_manifest, query_events
from src.kaven.log_store import default_log_dir

router = APIRouter(prefix="/agent", tags=["agent"])


def _validate_date(date: str | None) -> None:
    if date is not None and (len(date) != 8 or not date.isdigit()):
        raise HTTPException(status_code=400, detail="Date must be YYYYMMDD format")


@router.get("/manifest")
def agent_manifest() -> dict[str, Any]:
    """에이전트 디스커버리용 매니페스트 — 엔드포인트/MCP 도구/스키마 어휘 카탈로그."""
    return build_agent_manifest()


@router.get("/context")
def agent_context(
    date: str | None = None,
    max_events: int = 20,
    severity_min: int = 0,
) -> dict[str, Any]:
    """LLM 프롬프트 주입용 압축 마크다운 브리핑."""
    _validate_date(date)
    return build_agent_context(
        default_log_dir(), date=date, max_events=max_events, severity_min=severity_min
    )


@router.get("/events")
def agent_events(
    date: str | None = None,
    severity_min: int | None = None,
    region: str | None = None,
    category: str | None = None,
    signal: str | None = None,
    q: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """평탄화된 이벤트 쿼리 — 중복 제거 + 좌표/ID enrichment 적용."""
    _validate_date(date)
    return query_events(
        default_log_dir(),
        date=date,
        severity_min=severity_min,
        region=region,
        category=category,
        signal=signal,
        q=q,
        limit=limit,
    )

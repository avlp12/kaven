"""작전 콘솔(COP) 라우터 — 통합 상황 요약."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from src.kaven.log_store import default_log_dir
from src.kaven.ops_summary import build_ops_summary

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/summary")
def ops_summary(date: str | None = None) -> dict[str, Any]:
    """
    작전 콘솔(COP)용 통합 요약 — 지역 상태 + 전체 이벤트(좌표 포함)
    + 자산 영향 + 감시 구역을 한 번에 반환.
    """
    if date is not None and (len(date) != 8 or not date.isdigit()):
        raise HTTPException(status_code=400, detail="Date must be YYYYMMDD format")
    return build_ops_summary(default_log_dir(), date)

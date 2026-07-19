"""인텔 라우터 — 일일 리포트 / 지역 가이드 / 지도 데이터."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from src.kaven.aggregates import guide_overview, map_points, region_detail
from src.kaven.log_store import available_dates, default_log_dir
from src.kaven.report_generator import generate_daily_report

router = APIRouter(tags=["intel"])


@router.get("/report")
def daily_report_today() -> dict[str, Any]:
    """오늘의 일일 리포트 반환."""
    return generate_daily_report(default_log_dir())


@router.get("/report/dates")
def list_report_dates() -> dict[str, list[str]]:
    """리포트 가능한 날짜 목록 반환.

    주의: `/report/{date}`보다 먼저 등록해야 `dates`가 경로 파라미터로
    매칭되지 않는다 (기존 v0.0.06까지의 라우트 순서 버그 수정).
    """
    return {"dates": available_dates(default_log_dir())}


@router.get("/report/{date}")
def daily_report_by_date(date: str) -> dict[str, Any]:
    """특정 날짜(YYYYMMDD)의 일일 리포트 반환."""
    if len(date) != 8 or not date.isdigit():
        raise HTTPException(status_code=400, detail="Date must be YYYYMMDD format")
    report = generate_daily_report(default_log_dir(), date)
    if report["total_events"] == 0:
        raise HTTPException(status_code=404, detail=f"No events found for {date}")
    return report


@router.get("/guide")
def guide() -> dict[str, Any]:
    """모든 감시 지역의 현재 상태 요약."""
    return guide_overview(default_log_dir())


@router.get("/guide/{region}")
def guide_region(region: str, days: int = 7) -> dict[str, Any]:
    """특정 지역의 상세 현황 + 히스토리."""
    detail = region_detail(default_log_dir(), region, days)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown region: {region}")
    return detail


@router.get("/map/data")
def map_data() -> dict[str, Any]:
    """지도 시각화용 데이터 — 지역별 최신 이벤트 + 좌표."""
    return map_points(default_log_dir())

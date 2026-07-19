"""포트폴리오 라우터 — 자산별 투자 영향 집계."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from src.kaven.aggregates import portfolio_history
from src.kaven.log_store import default_log_dir

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("")
def portfolio_overview(days: int = 7) -> dict[str, Any]:
    """투자 영향 대시보드 — 자산별 이벤트 히트맵."""
    assets = portfolio_history(default_log_dir(), days)
    return {"days": days, "asset_count": len(assets), "assets": assets}


@router.get("/{asset_name}")
def portfolio_asset_detail(asset_name: str, days: int = 14) -> dict[str, Any]:
    """특정 자산의 상세 이벤트 히스토리."""
    assets = portfolio_history(default_log_dir(), days)
    match = next((a for a in assets if a["name"] == asset_name), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_name}")
    return match

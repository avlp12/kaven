"""시스템 라우터 — 헬스체크 / 수집 설정 조회."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.kaven.config_loader import load_config
from src.kaven.version import __version__

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kaven-web-api", "version": __version__}


@router.get("/config")
def current_config() -> dict[str, Any]:
    """
    현재 로드된 감시 구역/피드/키워드 설정을 반환.
    enabled=false 항목 포함 (전체 상태 확인용).
    """
    cfg = load_config()
    summary = {}
    for key, items in cfg.items():
        enabled_count = sum(1 for x in items if x.get("enabled", True))
        summary[key] = {
            "total": len(items),
            "enabled": enabled_count,
            "disabled": len(items) - enabled_count,
            "items": items,
        }
    return summary

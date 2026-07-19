"""시스템 라우터 — 헬스체크 / 수집 설정 조회 / 자산 설정 저장."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.kaven.config_loader import load_config, update_config_section
from src.kaven.version import __version__

router = APIRouter(tags=["system"])

ASSET_TYPES = {"commodity", "index", "currency", "equity", "bond", "crypto", "other"}


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


class AssetItem(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    type: str = "other"
    description: str = ""
    enabled: bool = True


class AssetsPayload(BaseModel):
    assets: list[AssetItem] = Field(max_length=100)


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "asset"


@router.put("/config/assets")
def save_assets(payload: AssetsPayload) -> dict[str, Any]:
    """
    추적 자산 목록 저장 — config.json의 `assets` 섹션만 갱신 (다른 섹션 보존).
    포트폴리오/워치리스트의 자산 메타(type/description)와 표시 여부(enabled)에 반영된다.
    """
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for a in payload.assets:
        name = a.name.strip()
        if not name:
            continue
        if name in seen:
            raise HTTPException(status_code=400, detail=f"duplicate asset name: {name}")
        if a.type not in ASSET_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"invalid type {a.type!r} — allowed: {sorted(ASSET_TYPES)}")
        seen.add(name)
        items.append({
            "id": _slug(name),
            "name": name,
            "type": a.type,
            "description": a.description.strip() or name,
            "enabled": a.enabled,
        })
    if not items:
        raise HTTPException(status_code=400, detail="assets list is empty")
    path = update_config_section("assets", items)
    return {"saved": len(items), "config_path": str(path)}

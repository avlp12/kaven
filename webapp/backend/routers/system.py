"""시스템 라우터 — 헬스체크 / 수집 설정 조회 / 설정 저장."""

from __future__ import annotations

import os
import re
import shlex
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.kaven.anthropic_auth import auth_mode as anthropic_auth_mode
from src.kaven.cli_providers import provider_status
from src.kaven.config_loader import load_config, update_config_section
from src.kaven.version import __version__
from webapp.backend.security import require_admin

router = APIRouter(tags=["system"])

ASSET_TYPES = {"commodity", "index", "currency", "equity", "bond", "crypto", "other"}
DEFAULT_ALLOWED_CLI_COMMANDS = {"claude", "codex", "cursor-agent", "gemini", "ant"}


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "kaven-web-api",
        "version": __version__,
        # 분석 경로별 자격증명 상태 (비밀값 미노출)
        "analysis": {
            "openai_compatible": bool(os.getenv("OPENAI_BASE_URL", "").strip()),
            "gemini": bool(os.getenv("GEMINI_API_KEY", "").strip()),
            "anthropic": anthropic_auth_mode(),  # api_key | oauth | none
            "anthropic_base_url": bool(os.getenv("ANTHROPIC_BASE_URL", "").strip()),
            "cli_providers": provider_status(),
        },
    }


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


class SectionPayload(BaseModel):
    """범용 설정 섹션 저장 payload. (하위호환: v0.0.12의 `assets` 키도 허용)"""

    items: list[dict[str, Any]] | None = Field(default=None, max_length=200)
    assets: list[dict[str, Any]] | None = Field(default=None, max_length=200)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "item"


def _bad(msg: str) -> HTTPException:
    return HTTPException(status_code=400, detail=msg)


def _num(item: dict, field: str, lo: float, hi: float) -> float:
    raw_value = item.get(field)
    try:
        if not isinstance(raw_value, (str, int, float)):
            raise TypeError
        v = float(raw_value)
    except (TypeError, ValueError):
        raise _bad(f"{field} must be a number") from None
    if not (lo <= v <= hi):
        raise _bad(f"{field} out of range [{lo}, {hi}]: {v}")
    return v


def _base(item: dict, key_field: str) -> dict[str, Any]:
    """공통 필드 검증 — 식별 필드 필수, id/enabled 정규화."""
    key = str(item.get(key_field, "")).strip()
    if not key:
        raise _bad(f"{key_field} is required")
    return {"id": item.get("id") or _slug(key), key_field: key,
            "enabled": bool(item.get("enabled", True))}


def _validate_zone(item: dict, with_baseline: bool) -> dict[str, Any]:
    out = _base(item, "name")
    lat_min, lat_max = _num(item, "lat_min", -90, 90), _num(item, "lat_max", -90, 90)
    lon_min, lon_max = _num(item, "lon_min", -180, 180), _num(item, "lon_max", -180, 180)
    if lat_min >= lat_max or lon_min >= lon_max:
        raise _bad("min must be < max for lat/lon bounds")
    out.update(lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max)
    if with_baseline and item.get("baseline_ships") not in (None, ""):
        out["baseline_ships"] = int(_num(item, "baseline_ships", 1, 100000))
    return out


def _validate_feed(item: dict) -> dict[str, Any]:
    out = _base(item, "name")
    url = str(item.get("url", "")).strip()
    if not re.match(r"^https?://", url):
        raise _bad(f"url must start with http(s):// — got {url!r}")
    out["url"] = url
    return out


def _validate_keyword(item: dict) -> dict[str, Any]:
    return {**_base(item, "query"), }


def _validate_cli_provider(item: dict) -> dict[str, Any]:
    out = _base(item, "name")
    command = str(item.get("command", "")).strip()
    try:
        argv = shlex.split(command)
    except ValueError as e:
        raise _bad(f"invalid command: {e}") from None
    if not argv:
        raise _bad("command is required")
    allowed = DEFAULT_ALLOWED_CLI_COMMANDS | {
        command.strip()
        for command in os.getenv("KAVEN_ALLOWED_CLI_COMMANDS", "").split(",")
        if command.strip()
    }
    if argv[0] not in allowed:
        raise _bad(f"command executable must be allowed — allowed: {sorted(allowed)}")
    out.update(id=item.get("id") or _slug(argv[0]), command=command)
    return out


def _validate_asset(item: dict) -> dict[str, Any]:
    out = _base(item, "name")
    a_type = str(item.get("type", "other"))
    if a_type not in ASSET_TYPES:
        raise _bad(f"invalid type {a_type!r} — allowed: {sorted(ASSET_TYPES)}")
    out.update(type=a_type, description=str(item.get("description", "")).strip() or out["name"])
    return out


def _validate_region(item: dict) -> dict[str, Any]:
    out = _base(item, "code")
    out["code"] = _slug(out["code"])
    name = str(item.get("name", "")).strip()
    if not name:
        raise _bad("name is required")
    out.update(
        name=name,
        name_en=str(item.get("name_en", "")).strip() or name,
        lat=_num(item, "lat", -90, 90),
        lng=_num(item, "lng", -180, 180),
        description=str(item.get("description", "")).strip(),
        description_en=str(item.get("description_en", "")).strip()
                       or str(item.get("description", "")).strip(),
    )
    return out


# 섹션 → (검증 함수, 중복 판정 키)
EDITABLE_SECTIONS: dict[str, tuple[Any, str]] = {
    "assets": (_validate_asset, "name"),
    "regions": (_validate_region, "code"),
    "ais_zones": (lambda i: _validate_zone(i, with_baseline=True), "name"),
    "adsb_zones": (lambda i: _validate_zone(i, with_baseline=False), "name"),
    "news_feeds": (_validate_feed, "name"),
    "news_keywords": (_validate_keyword, "query"),
    "social_keywords": (_validate_keyword, "query"),
    "cli_providers": (_validate_cli_provider, "name"),
}


@router.put("/config/{section}")
def save_config_section(
    section: str,
    payload: SectionPayload,
    _admin: None = Depends(require_admin),
) -> dict[str, Any]:
    """
    설정 섹션 저장 — config.json의 해당 섹션만 갱신 (다른 섹션 보존).

    편집 가능 섹션: assets, regions, ais_zones, adsb_zones,
    news_feeds, news_keywords, social_keywords.
    """
    if section not in EDITABLE_SECTIONS:
        raise HTTPException(
            status_code=404,
            detail=f"unknown section {section!r} — editable: {sorted(EDITABLE_SECTIONS)}")
    validate, dup_key = EDITABLE_SECTIONS[section]

    raw_items = payload.items if payload.items is not None else payload.assets
    if raw_items is None:
        raise _bad("body must contain 'items'")

    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if not str(raw.get(dup_key, "")).strip():
            continue  # 빈 행은 조용히 스킵 (편집기 잔여 행)
        item = validate(raw)
        key = item[dup_key]
        if key in seen:
            raise _bad(f"duplicate {dup_key}: {key}")
        seen.add(key)
        items.append(item)
    if not items:
        raise _bad(f"{section} list is empty")

    path = update_config_section(section, items)
    return {"section": section, "saved": len(items), "config_path": str(path)}

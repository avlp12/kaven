"""
Kaven Aggregates — 지역 히스토리·가이드·지도·포트폴리오 집계 로직.

기존 webapp/backend/app.py에 섞여 있던 도메인 집계를 코어로 이동.
webapp 라우터와 MCP 서버가 공용으로 사용한다.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from src.kaven.config_loader import get_assets
from src.kaven.log_store import load_day_events, recent_dates
from src.kaven.regions import region_info
from src.kaven.report_generator import generate_daily_report


def asset_meta() -> dict[str, dict[str, Any]]:
    """
    설정(config.json `assets` 섹션, 기본값 내장)에서 자산 메타 로드.

    Returns: {자산명: {"type", "description", "enabled"}}
    """
    meta: dict[str, dict[str, Any]] = {}
    for a in get_assets(only_enabled=False):
        name = a.get("name", "").strip()
        if not name:
            continue
        meta[name] = {
            "type": a.get("type", "other"),
            "description": a.get("description", name),
            "enabled": a.get("enabled", True),
        }
    return meta


def _display(date_str: str) -> str:
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"


# ── Region ──────────────────────────────────────────────────────


def region_history(log_dir: Path, region: str, days: int = 7) -> list[dict[str, Any]]:
    """최근 N일간 특정 지역의 severity 히스토리 (과거→오늘 순)."""
    history = []
    for date_str in recent_dates(days):
        events = [ev for ev in load_day_events(log_dir, date_str) if ev.get("region") == region]
        history.append({
            "date": _display(date_str),
            "max_severity": max((e.get("severity", 0) for e in events), default=0),
            "event_count": len(events),
        })
    history.reverse()
    return history


def guide_overview(log_dir: Path) -> dict[str, Any]:
    """모든 감시 지역의 현재 상태 요약."""
    report = generate_daily_report(log_dir)
    regions = []
    for code, info in region_info().items():
        region_data = report.get("by_region", {}).get(code, {})
        regions.append({
            "code": code,
            "name": info["name"],
            "name_en": info.get("name_en", info["name"]),
            "lat": info["lat"],
            "lng": info["lng"],
            "description": info["description"],
            "description_en": info.get("description_en", info["description"]),
            "current_severity": region_data.get("max_severity", 0),
            "event_count": region_data.get("event_count", 0),
        })
    regions.sort(key=lambda x: -x["current_severity"])
    return {
        "date": report["date"],
        "max_severity": report["max_severity"],
        "regions": regions,
    }


def region_detail(log_dir: Path, region: str, days: int = 7) -> dict[str, Any] | None:
    """특정 지역의 상세 현황 + 히스토리. 미등록 지역이면 None."""
    info = region_info(include_disabled=True).get(region)
    if info is None:
        return None
    report = generate_daily_report(log_dir)
    region_data = report.get("by_region", {}).get(region, {})
    return {
        "code": region,
        "name": info["name"],
        "name_en": info.get("name_en", info["name"]),
        "lat": info["lat"],
        "lng": info["lng"],
        "description": info["description"],
        "description_en": info.get("description_en", info["description"]),
        "current_severity": region_data.get("max_severity", 0),
        "today_events": region_data.get("events", []),
        "history": region_history(log_dir, region, days),
    }


def map_points(log_dir: Path) -> dict[str, Any]:
    """지도 시각화용 데이터 — 지역별 최고 severity 이벤트 + 좌표."""
    report = generate_daily_report(log_dir)
    points = []
    for code, info in region_info().items():
        region_data = report.get("by_region", {}).get(code, {})
        if not region_data.get("events"):
            continue
        top_event = max(region_data["events"], key=lambda e: e.get("severity", 0))
        points.append({
            "region": code,
            "lat": info["lat"],
            "lng": info["lng"],
            "name": info["name"],
            "severity": top_event.get("severity", 0),
            "event": top_event.get("event", ""),
        })
    return {"date": report["date"], "points": points}


# ── Portfolio ───────────────────────────────────────────────────


def portfolio_history(log_dir: Path, days: int = 7) -> list[dict[str, Any]]:
    """자산별 이벤트 히스토리 집계."""
    asset_daily: dict[str, list[dict]] = defaultdict(list)
    all_assets: dict[str, dict] = defaultdict(
        lambda: {"total_events": 0, "max_severity": 0, "signals": defaultdict(int)}
    )

    for date_str in recent_dates(days):
        display = _display(date_str)
        day_events: dict[str, list] = defaultdict(list)
        for ev in load_day_events(log_dir, date_str):
            for asset in ev.get("affected_assets", []):
                day_events[asset].append(ev)

        seen_assets = set()
        for asset, evts in day_events.items():
            seen_assets.add(asset)
            max_sev = max(e.get("severity", 0) for e in evts)
            asset_daily[asset].append({
                "date": display,
                "max_severity": max_sev,
                "event_count": len(evts),
            })
            all_assets[asset]["total_events"] += len(evts)
            all_assets[asset]["max_severity"] = max(all_assets[asset]["max_severity"], max_sev)
            for ev in evts:
                all_assets[asset]["signals"][ev.get("signal", "watch")] += 1

        # 해당 날에 언급 안 된 자산은 0으로 채움
        for asset in asset_daily:
            if asset not in seen_assets:
                asset_daily[asset].append({"date": display, "max_severity": 0, "event_count": 0})

    for asset in asset_daily:
        asset_daily[asset].sort(key=lambda x: x["date"])

    meta_map = asset_meta()
    assets = []
    for asset, info in all_assets.items():
        meta = meta_map.get(asset, {"type": "other", "description": asset, "enabled": True})
        if not meta.get("enabled", True):
            continue  # 설정에서 비활성화된 자산은 집계에서 제외
        dominant = max(info["signals"].items(), key=lambda x: x[1])[0] if info["signals"] else "watch"
        assets.append({
            "name": asset,
            "type": meta["type"],
            "description": meta["description"],
            "total_events": info["total_events"],
            "max_severity": info["max_severity"],
            "dominant_signal": dominant,
            "signals": dict(info["signals"]),
            "history": asset_daily.get(asset, []),
        })

    assets.sort(key=lambda x: (-x["max_severity"], -x["total_events"]))
    return assets

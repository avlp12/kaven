"""
Kaven Ops Summary — 작전 콘솔(COP)·에이전트용 통합 집계.

지역 상태, 전체 이벤트(좌표 포함), 자산 영향, 감시 구역(watchzone)을
하나의 payload로 묶어서 반환한다. LLM 없이 규칙 기반으로 동작.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from src.kaven.config_loader import load_config
from src.kaven.log_store import dedup_events, load_day_events, today_str
from src.kaven.regions import REGION_INFO
from src.kaven.version import __version__

# 하위호환 alias (v0.0.06까지 webapp.backend.ops.REGION_COORDS)
REGION_COORDS = REGION_INFO


def event_id(ev: dict[str, Any]) -> str:
    """이벤트 선택/추적용 안정적 ID (내용 기반 해시)."""
    key = f"{ev.get('event', '')[:80]}|{ev.get('region', '')}|{ev.get('severity', 0)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def enrich_event(ev: dict[str, Any]) -> dict[str, Any]:
    """원본 이벤트에 안정적 ID + 지역 좌표/이름을 부착한 평탄화 dict."""
    region = ev.get("region", "other")
    coords = REGION_INFO.get(region, {})
    return {
        "id": event_id(ev),
        "event": ev.get("event", ""),
        "severity": ev.get("severity", 0),
        "category": ev.get("category", "other"),
        "signal": ev.get("signal", "watch"),
        "confidence": ev.get("confidence"),
        "region": region,
        "region_name": coords.get("name", region),
        "lat": coords.get("lat"),
        "lng": coords.get("lng"),
        "time": ev.get("event_time") or ev.get("_started_at", ""),
        "affected_assets": ev.get("affected_assets", []),
        "source_url": ev.get("source_url", ""),
        "reasoning": ev.get("reasoning", ""),
    }


def watchzones() -> list[dict[str, Any]]:
    """AIS/ADS-B 감시 구역을 지도 오버레이용으로 병합."""
    cfg = load_config()
    zones: list[dict[str, Any]] = []
    for kind, key in (("ais", "ais_zones"), ("adsb", "adsb_zones")):
        for z in cfg.get(key, []):
            zones.append({
                "id": z.get("id", ""),
                "name": z.get("name", z.get("id", "")),
                "kind": kind,
                "enabled": z.get("enabled", True),
                "lat_min": z.get("lat_min"),
                "lat_max": z.get("lat_max"),
                "lon_min": z.get("lon_min"),
                "lon_max": z.get("lon_max"),
            })
    return zones


def build_ops_summary(log_dir: Path, date_str: str | None = None) -> dict[str, Any]:
    """
    작전 콘솔용 통합 요약 생성.

    Returns:
        {
            "version": str,
            "date": "YYYY-MM-DD",
            "threat_level": int (0-5, 해당일 최대 severity),
            "totals": {"runs", "events", "unique_events"},
            "regions": [{code, name, lat, lng, description, severity, event_count}],
            "events": [enrich_event() 결과, 시간 내림차순],
            "categories": {category: count},
            "assets": [{name, count, max_severity}],
            "watchzones": [{id, name, kind, enabled, lat_min, ...}],
        }
    """
    if date_str is None:
        date_str = today_str()
    display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    all_events = load_day_events(log_dir, date_str)
    unique = dedup_events(all_events)
    run_ids = {ev.get("_run_id") for ev in all_events if ev.get("_run_id")}

    events_out: list[dict[str, Any]] = []
    region_events: dict[str, list[dict[str, Any]]] = {}
    categories: dict[str, int] = {}
    asset_stats: dict[str, dict[str, int]] = {}

    for ev in unique:
        severity = ev.get("severity", 0)
        events_out.append(enrich_event(ev))
        region_events.setdefault(ev.get("region", "other"), []).append(ev)
        cat = ev.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1
        for asset in ev.get("affected_assets", []):
            stat = asset_stats.setdefault(asset, {"count": 0, "max_severity": 0})
            stat["count"] += 1
            stat["max_severity"] = max(stat["max_severity"], severity)

    events_out.sort(key=lambda e: e.get("time", ""), reverse=True)

    regions_out: list[dict[str, Any]] = []
    for code, info in REGION_INFO.items():
        evts = region_events.get(code, [])
        regions_out.append({
            "code": code,
            "name": info["name"],
            "name_en": info.get("name_en", info["name"]),
            "lat": info["lat"],
            "lng": info["lng"],
            "description": info["description"],
            "description_en": info.get("description_en", info["description"]),
            "severity": max((e.get("severity", 0) for e in evts), default=0),
            "event_count": len(evts),
        })
    regions_out.sort(key=lambda r: (-r["severity"], -r["event_count"]))

    from src.kaven.aggregates import asset_meta  # 순환 import 방지 (지연)
    meta_map = asset_meta()
    assets_out = [
        {"name": name, "count": stat["count"], "max_severity": stat["max_severity"]}
        for name, stat in asset_stats.items()
        if meta_map.get(name, {}).get("enabled", True)
    ]
    assets_out.sort(key=lambda a: (-a["max_severity"], -a["count"]))

    return {
        "version": __version__,
        "date": display_date,
        "threat_level": max((e.get("severity", 0) for e in unique), default=0),
        "totals": {
            "runs": len(run_ids),
            "events": len(all_events),
            "unique_events": len(unique),
        },
        "regions": regions_out,
        "events": events_out,
        "categories": categories,
        "assets": assets_out,
        "watchzones": watchzones(),
    }

"""
Kaven Ops Summary — Palantir Maven 스타일 작전 콘솔(COP)용 통합 집계.

프론트엔드 COP 화면이 한 번의 요청으로 그려지도록
지역 상태, 전체 이벤트(좌표 포함), 자산 영향, 감시 구역(watchzone)을
하나의 payload로 묶어서 반환한다. LLM 없이 규칙 기반으로 동작.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.kaven.config_loader import load_config
from src.kaven.report_generator import _dedup_events, _load_day_events
from src.kaven.version import __version__

# 감시 지역 좌표 + 설명 (guide/map/ops 공용)
REGION_COORDS: dict[str, dict[str, Any]] = {
    "hormuz": {"lat": 26.5, "lng": 56.3, "name": "호르무즈 해협",
               "description": ("세계 원유 해상 운송의 약 20%가 통과하는 전략적 요충지. "
                               "한국 원유 수입의 70%가 이 해역을 경유.")},
    "taiwan": {"lat": 23.7, "lng": 121.0, "name": "대만 해협",
               "description": "글로벌 반도체 공급망의 핵심 지역. 대만 TSMC는 세계 파운드리의 60% 점유."},
    "korea": {"lat": 37.5, "lng": 127.0, "name": "한반도",
              "description": "KOSPI, 원/달러 환율에 직접적 영향을 미치는 최고 우선순위 감시 지역."},
    "ukraine": {"lat": 48.4, "lng": 31.2, "name": "우크라이나",
                "description": "유럽 에너지·곡물 공급에 영향. 러시아-우크라이나 분쟁 장기화."},
    "india_pak": {"lat": 30.0, "lng": 70.0, "name": "인도·파키스탄",
                  "description": "남아시아 핵 보유국 간 긴장. 에너지·무역 경로 교란 가능성."},
    "southcn": {"lat": 14.0, "lng": 114.0, "name": "남중국해",
                "description": "세계 해상 무역의 30%가 통과. 미중 해양 패권 경쟁의 핵심 지역."},
    "redsa": {"lat": 14.0, "lng": 42.0, "name": "홍해·예멘",
              "description": "수에즈 운하 접근 해역. 후티 반군의 선박 공격으로 국제 물류 차질."},
    "sahel": {"lat": 15.0, "lng": 0.0, "name": "사헬",
              "description": "서아프리카 지정학 불안정 지역. 에너지·광물 공급망 영향."},
    "global": {"lat": 0, "lng": 0, "name": "전지구",
               "description": "특정 지역에 국한되지 않는 글로벌 이벤트."},
}


def _event_id(ev: dict[str, Any]) -> str:
    """이벤트 선택/추적용 안정적 ID (내용 기반 해시)."""
    key = f"{ev.get('event', '')[:80]}|{ev.get('region', '')}|{ev.get('severity', 0)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _watchzones() -> list[dict[str, Any]]:
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
            "threat_level": int (0-5, 오늘의 최대 severity),
            "totals": {"runs", "events", "unique_events"},
            "regions": [{code, name, lat, lng, description, severity, event_count}],
            "events": [{id, event, severity, category, signal, region,
                        region_name, lat, lng, time, affected_assets,
                        source_url, reasoning, confidence}],
            "categories": {category: count},
            "assets": [{name, count, max_severity}],
            "watchzones": [{id, name, kind, enabled, lat_min, ...}],
        }
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    all_events = _load_day_events(log_dir, date_str)
    unique = _dedup_events(all_events)
    run_ids = {ev.get("_run_id") for ev in all_events if ev.get("_run_id")}

    events_out: list[dict[str, Any]] = []
    region_events: dict[str, list[dict[str, Any]]] = {}
    categories: dict[str, int] = {}
    asset_stats: dict[str, dict[str, int]] = {}

    for ev in unique:
        region = ev.get("region", "other")
        coords = REGION_COORDS.get(region, {})
        severity = ev.get("severity", 0)
        events_out.append({
            "id": _event_id(ev),
            "event": ev.get("event", ""),
            "severity": severity,
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
        })
        region_events.setdefault(region, []).append(ev)
        cat = ev.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1
        for asset in ev.get("affected_assets", []):
            stat = asset_stats.setdefault(asset, {"count": 0, "max_severity": 0})
            stat["count"] += 1
            stat["max_severity"] = max(stat["max_severity"], severity)

    events_out.sort(key=lambda e: e.get("time", ""), reverse=True)

    regions_out: list[dict[str, Any]] = []
    for code, info in REGION_COORDS.items():
        evts = region_events.get(code, [])
        regions_out.append({
            "code": code,
            "name": info["name"],
            "lat": info["lat"],
            "lng": info["lng"],
            "description": info["description"],
            "severity": max((e.get("severity", 0) for e in evts), default=0),
            "event_count": len(evts),
        })
    regions_out.sort(key=lambda r: (-r["severity"], -r["event_count"]))

    assets_out = [
        {"name": name, "count": stat["count"], "max_severity": stat["max_severity"]}
        for name, stat in asset_stats.items()
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
        "watchzones": _watchzones(),
    }

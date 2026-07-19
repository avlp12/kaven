"""
Kaven Agent Service — AI 에이전트 연동용 쿼리·컨텍스트·매니페스트.

에이전트(LLM 도구 호출)가 소비하기 좋은 형태를 제공한다:
- ``query_events``: run 중첩 구조 대신 평탄한 이벤트 목록 + 필터
- ``build_agent_context``: LLM 프롬프트에 그대로 주입 가능한 압축 브리핑
- ``build_agent_manifest``: 사용 가능한 엔드포인트/도구/어휘의 기계가독 카탈로그

REST(`/agent/*`)와 MCP 서버(`src/kaven/mcp_server.py`)가 공용으로 사용.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.kaven.log_store import dedup_events, load_day_events, today_str
from src.kaven.ops_summary import build_ops_summary, enrich_event
from src.kaven.regions import CATEGORIES, REGION_INFO, SEVERITY_LEVELS, SIGNALS, region_info
from src.kaven.version import __version__


def query_events(
    log_dir: Path,
    date: str | None = None,
    severity_min: int | None = None,
    region: str | None = None,
    category: str | None = None,
    signal: str | None = None,
    q: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    평탄화된 이벤트 목록 조회 (에이전트 친화 스키마).

    /runs와 달리 run 중첩 없이 이벤트 단위로 반환하며,
    중복 제거 + 좌표/ID enrichment가 적용된다.
    """
    if date is None:
        date = today_str()
    region_map = region_info(include_disabled=True)
    events = [enrich_event(ev, region_map) for ev in dedup_events(load_day_events(log_dir, date))]

    def _match(e: dict[str, Any]) -> bool:
        if severity_min is not None and e["severity"] < severity_min:
            return False
        if region and e["region"] != region:
            return False
        if category and e["category"] != category:
            return False
        if signal and e["signal"] != signal:
            return False
        if q:
            haystack = " ".join([
                e["event"], e["region"], e["region_name"], e["category"],
                e["reasoning"], " ".join(e["affected_assets"]),
            ]).lower()
            if q.lower() not in haystack:
                return False
        return True

    matched = [e for e in events if _match(e)]
    matched.sort(key=lambda e: (-e["severity"], e.get("time", "")), reverse=False)
    limited = matched[: max(0, limit)]
    return {
        "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
        "total": len(events),
        "matched": len(matched),
        "returned": len(limited),
        "events": limited,
    }


def build_agent_context(
    log_dir: Path,
    date: str | None = None,
    max_events: int = 20,
    severity_min: int = 0,
) -> dict[str, Any]:
    """
    LLM 컨텍스트 주입용 압축 마크다운 브리핑.

    Returns:
        {"date", "threat_level", "event_count", "context"(markdown str)}
    """
    summary = build_ops_summary(log_dir, date)
    events = [e for e in summary["events"] if e["severity"] >= severity_min]
    events.sort(key=lambda e: -e["severity"])
    events = events[: max(1, max_events)]

    lines = [
        f"# KAVEN OPS BRIEFING — {summary['date']} (UTC)",
        f"THREAT LEVEL: {summary['threat_level']}/5 "
        f"({SEVERITY_LEVELS.get(summary['threat_level'], '정보 없음')})",
        f"RUNS {summary['totals']['runs']} · EVENTS {summary['totals']['events']} "
        f"· UNIQUE {summary['totals']['unique_events']}",
        "",
        "## ACTIVE REGIONS",
    ]
    active = [r for r in summary["regions"] if r["event_count"] > 0]
    if active:
        for r in active:
            lines.append(f"- {r['code']} ({r['name']}): S{r['severity']}, {r['event_count']} events")
    else:
        lines.append("- (no active regions)")

    lines.extend(["", f"## TOP EVENTS (max {max_events}, severity desc)"])
    if events:
        for e in events:
            time_str = (e.get("time") or "")[11:16] or "--:--"
            assets = ", ".join(e["affected_assets"]) or "-"
            lines.append(
                f"- [S{e['severity']}][{e['category']}][{e['region']}] {e['event']}"
                f" (signal={e['signal']}; assets={assets}; {time_str}Z; id={e['id']})"
            )
    else:
        lines.append("- (no events)")

    if summary["assets"]:
        lines.extend(["", "## ASSET IMPACT"])
        for a in summary["assets"]:
            lines.append(f"- {a['name']}: {a['count']} events, max S{a['max_severity']}")

    return {
        "date": summary["date"],
        "threat_level": summary["threat_level"],
        "event_count": len(events),
        "context": "\n".join(lines),
    }


# ── Manifest ────────────────────────────────────────────────────

# MCP 서버와 매니페스트가 공유하는 도구 정의
AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "kaven_ops_summary",
        "description": ("당일(또는 지정일)의 통합 상황 요약: 위협 수준, 지역별 상태, "
                        "전체 이벤트(좌표 포함), 자산 영향, 감시 구역."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYYMMDD (생략 시 오늘, UTC)"},
            },
        },
    },
    {
        "name": "kaven_events",
        "description": "평탄화된 이벤트 목록 조회. severity/지역/카테고리/신호/키워드 필터 지원.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYYMMDD (생략 시 오늘)"},
                "severity_min": {"type": "integer", "minimum": 1, "maximum": 5},
                "region": {"type": "string", "description": f"지역 코드: {', '.join(REGION_INFO)}"},
                "category": {"type": "string", "description": f"카테고리: {', '.join(CATEGORIES)}"},
                "signal": {"type": "string", "description": f"투자 신호: {', '.join(SIGNALS)}"},
                "query": {"type": "string", "description": "본문/자산/지역 키워드 검색"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "kaven_agent_context",
        "description": "LLM 프롬프트에 주입하기 좋은 압축 마크다운 브리핑.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYYMMDD (생략 시 오늘)"},
                "max_events": {"type": "integer", "default": 20},
                "severity_min": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "kaven_region",
        "description": "특정 감시 지역의 상세 현황 + 최근 N일 severity 히스토리.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "description": f"지역 코드: {', '.join(REGION_INFO)}"},
                "days": {"type": "integer", "default": 7},
            },
            "required": ["region"],
        },
    },
    {
        "name": "kaven_daily_report",
        "description": "규칙 기반 일일 브리핑(마크다운) + 지역/카테고리/자산 집계.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYYMMDD (생략 시 오늘)"},
            },
        },
    },
    {
        "name": "kaven_portfolio",
        "description": "지정학 이벤트의 투자 자산별 영향 집계 (최근 N일 히트맵 데이터).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7},
                "asset": {"type": "string", "description": "특정 자산명 (생략 시 전체)"},
            },
        },
    },
    {
        "name": "kaven_config",
        "description": "현재 수집 설정(감시 구역/피드/키워드, enabled 여부) 조회.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "kaven_run_collection",
        "description": "수집→분석→알림 파이프라인을 1회 즉시 실행. 수 분 소요될 수 있음.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def build_agent_manifest() -> dict[str, Any]:
    """에이전트 디스커버리용 매니페스트 — 엔드포인트/도구/어휘 카탈로그."""
    return {
        "service": "kaven",
        "version": __version__,
        "description": ("지정학 조기경보 시스템. AIS/ADS-B/뉴스/소셜 수집 → LLM 분석 → "
                        "severity(1-5) 이벤트 생성. 본 API로 이벤트·지역·자산 영향 조회 가능."),
        "openapi_url": "/openapi.json",
        "endpoints": [
            {"method": "GET", "path": "/agent/manifest", "description": "이 매니페스트"},
            {"method": "GET", "path": "/agent/context",
             "description": "LLM 주입용 압축 브리핑",
             "params": ["date?", "max_events?", "severity_min?"]},
            {"method": "GET", "path": "/agent/events",
             "description": "평탄화 이벤트 쿼리",
             "params": ["date?", "severity_min?", "region?", "category?", "signal?", "q?", "limit?"]},
            {"method": "GET", "path": "/ops/summary", "description": "통합 상황 요약", "params": ["date?"]},
            {"method": "GET", "path": "/report/{date}", "description": "일일 브리핑(마크다운 포함)"},
            {"method": "GET", "path": "/guide/{region}", "description": "지역 상세 + 히스토리", "params": ["days?"]},
            {"method": "GET", "path": "/portfolio", "description": "자산 영향 집계", "params": ["days?"]},
            {"method": "GET", "path": "/config", "description": "수집 설정 조회"},
            {"method": "POST", "path": "/runs/once", "description": "수집 파이프라인 1회 실행"},
            {"method": "GET", "path": "/runs/stream", "description": "SSE 실시간 run 스트림"},
        ],
        "mcp": {
            "transport": "stdio",
            "command": "python -m src.kaven.mcp_server",
            "tools": [{"name": t["name"], "description": t["description"]} for t in AGENT_TOOLS],
        },
        "vocabulary": {
            "severity_levels": {str(k): v for k, v in SEVERITY_LEVELS.items()},
            "categories": CATEGORIES,
            "signals": SIGNALS,
            "regions": {code: info.get("name", code) for code, info in region_info().items()},
            "event_fields": [
                "id", "event", "severity", "category", "signal", "confidence",
                "region", "region_name", "lat", "lng", "time",
                "affected_assets", "source_url", "reasoning",
            ],
        },
    }

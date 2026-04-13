"""
Kaven Daily Report Generator — 일일 분석 리포트 자동 생성

하루 동안 쌓인 이벤트를 지역별·카테고리별로 집계하고,
마크다운 형식의 일일 브리핑을 생성한다.
LLM 없이 규칙 기반으로 동작하므로 API 키 없이도 리포트 생성 가능.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# severity 이모지 + 라벨
_SEV = {
    1: ("⚪", "일상"),
    2: ("🔵", "모니터링"),
    3: ("🟡", "주의"),
    4: ("🟠", "경보"),
    5: ("🔴", "긴급"),
}

_CATEGORY_KO = {
    "energy": "⛽ 에너지",
    "semiconductor": "🔬 반도체",
    "currency": "💱 환율",
    "conflict": "⚔️ 분쟁",
    "other": "📌 기타",
}

_REGION_KO = {
    "hormuz": "호르무즈 해협",
    "taiwan": "대만 해협",
    "korea": "한반도",
    "ukraine": "우크라이나",
    "india_pak": "인도·파키스탄",
    "southcn": "남중국해",
    "redsa": "홍해·예멘",
    "sahel": "사헬",
    "global": "전지구",
    "other": "기타",
}


def _load_day_events(log_dir: Path, date_str: str) -> list[dict[str, Any]]:
    """특정 날짜의 모든 이벤트를 로드."""
    events: list[dict[str, Any]] = []
    for prefix in ("kaven_", "maven_"):
        path = log_dir / f"{prefix}{date_str}.jsonl"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    run = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for ev in run.get("events", []):
                    ev["_run_id"] = run.get("run_id", "")
                    ev["_started_at"] = run.get("started_at", "")
                    events.append(ev)
    return events


def _dedup_events(events: list[dict]) -> list[dict]:
    """같은 event 텍스트(앞 60자)의 중복 제거. 가장 높은 severity만 유지."""
    seen: dict[str, dict] = {}
    for ev in events:
        key = ev.get("event", "")[:60].strip().lower()
        if key not in seen or ev.get("severity", 0) > seen[key].get("severity", 0):
            seen[key] = ev
    return list(seen.values())


def generate_daily_report(log_dir: Path, date_str: str | None = None) -> dict[str, Any]:
    """
    일일 리포트 생성.

    Args:
        log_dir: 로그 디렉터리 경로
        date_str: YYYYMMDD 형식 날짜. None이면 오늘.

    Returns:
        {
            "date": "2026-04-13",
            "total_runs": int,
            "total_events": int,
            "unique_events": int,
            "max_severity": int,
            "by_region": {region: {events, max_severity, ...}},
            "by_category": {category: count},
            "affected_assets": {asset: count},
            "timeline": [{time, event, severity}],
            "markdown": str  # 완성된 마크다운 리포트
        }
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    display_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    all_events = _load_day_events(log_dir, date_str)
    unique = _dedup_events(all_events)

    if not unique:
        return {
            "date": display_date,
            "total_runs": 0,
            "total_events": 0,
            "unique_events": 0,
            "max_severity": 0,
            "by_region": {},
            "by_category": {},
            "affected_assets": {},
            "timeline": [],
            "markdown": f"# Kaven 일일 리포트 — {display_date}\n\n이벤트 없음.",
        }

    # 집계
    run_ids = {ev.get("_run_id") for ev in all_events if ev.get("_run_id")}
    max_sev = max(ev.get("severity", 0) for ev in unique)

    by_region: dict[str, list[dict]] = defaultdict(list)
    by_category: dict[str, int] = defaultdict(int)
    asset_counts: dict[str, int] = defaultdict(int)
    timeline: list[dict] = []

    for ev in unique:
        region = ev.get("region", "other")
        by_region[region].append(ev)
        by_category[ev.get("category", "other")] += 1
        for asset in ev.get("affected_assets", []):
            asset_counts[asset] += 1
        timeline.append({
            "time": ev.get("event_time") or ev.get("_started_at", ""),
            "event": ev.get("event", ""),
            "severity": ev.get("severity", 0),
            "region": region,
        })

    timeline.sort(key=lambda x: x.get("time", ""))

    # 마크다운 생성
    md = _build_markdown(
        display_date, len(run_ids), len(all_events), unique,
        max_sev, by_region, by_category, asset_counts, timeline,
    )

    # 지역별 요약 dict
    region_summary = {}
    for region, evts in by_region.items():
        region_summary[region] = {
            "name": _REGION_KO.get(region, region),
            "event_count": len(evts),
            "max_severity": max(e.get("severity", 0) for e in evts),
            "events": [{"event": e.get("event", ""), "severity": e.get("severity", 0)} for e in evts],
        }

    return {
        "date": display_date,
        "total_runs": len(run_ids),
        "total_events": len(all_events),
        "unique_events": len(unique),
        "max_severity": max_sev,
        "by_region": region_summary,
        "by_category": dict(by_category),
        "affected_assets": dict(sorted(asset_counts.items(), key=lambda x: -x[1])),
        "timeline": timeline,
        "markdown": md,
    }


def _build_markdown(
    date: str,
    total_runs: int,
    total_events: int,
    unique: list[dict],
    max_sev: int,
    by_region: dict[str, list[dict]],
    by_category: dict[str, int],
    asset_counts: dict[str, int],
    timeline: list[dict],
) -> str:
    """마크다운 형식 일일 리포트 생성."""
    sev_emoji, sev_label = _SEV.get(max_sev, ("⚪", "정보"))
    lines = [
        f"# {sev_emoji} Kaven 일일 리포트 — {date}",
        "",
        f"**오늘의 위험 수준**: {sev_emoji} Lv.{max_sev}/5 ({sev_label})",
        f"**총 실행 횟수**: {total_runs}회 | **전체 이벤트**: {total_events}건 | **고유 이벤트**: {len(unique)}건",
        "",
        "---",
        "",
        "## 📍 지역별 현황",
        "",
    ]

    # 지역별 — severity 높은 순
    sorted_regions = sorted(
        by_region.items(),
        key=lambda x: max(e.get("severity", 0) for e in x[1]),
        reverse=True,
    )
    for region, evts in sorted_regions:
        region_name = _REGION_KO.get(region, region)
        region_max = max(e.get("severity", 0) for e in evts)
        region_emoji, _ = _SEV.get(region_max, ("⚪", ""))
        lines.append(f"### {region_emoji} {region_name} (Lv.{region_max})")
        for ev in sorted(evts, key=lambda e: -e.get("severity", 0)):
            signal = ev.get("signal", "watch")
            assets = ", ".join(ev.get("affected_assets", []))
            lines.append(f"- **[{ev.get('severity', 0)}]** {ev.get('event', '')}")
            if ev.get("reasoning"):
                lines.append(f"  - 분석: {ev['reasoning'][:200]}")
            if assets:
                lines.append(f"  - 신호: `{signal}` | 영향 자산: {assets}")
        lines.append("")

    # 카테고리 요약
    lines.extend(["## 📂 카테고리 분포", ""])
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        cat_ko = _CATEGORY_KO.get(cat, cat)
        lines.append(f"- {cat_ko}: {count}건")
    lines.append("")

    # 영향 자산
    if asset_counts:
        lines.extend(["## 💼 영향 자산 (언급 빈도순)", ""])
        for asset, count in sorted(asset_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {asset}: {count}건")
        lines.append("")

    # 타임라인
    if timeline:
        lines.extend(["## ⏱ 이벤트 타임라인", ""])
        for t in timeline:
            time_str = t.get("time", "")[:16] if t.get("time") else "시각 불명"
            sev_e, _ = _SEV.get(t.get("severity", 0), ("⚪", ""))
            lines.append(f"- `{time_str}` {sev_e} {t.get('event', '')}")
        lines.append("")

    return "\n".join(lines)

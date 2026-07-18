"""src.kaven.agent_service 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.kaven.agent_service import (
    AGENT_TOOLS,
    build_agent_context,
    build_agent_manifest,
    query_events,
)

_TEMP_DIRS: list[TemporaryDirectory] = []  # prevent GC during test run

_DATE = "20260413"


def _make_log_dir() -> Path:
    tmpdir = TemporaryDirectory()
    _TEMP_DIRS.append(tmpdir)
    log_dir = Path(tmpdir.name)
    runs = [
        {"run_id": "r1", "started_at": "2026-04-13T01:00:00+00:00", "events": [
            {"event": "호르무즈 유조선 통행 급감", "severity": 4, "category": "energy",
             "signal": "hedge", "region": "hormuz", "affected_assets": ["WTI"]},
            {"event": "대만 해협 군사 훈련", "severity": 3, "category": "conflict",
             "signal": "watch", "region": "taiwan", "affected_assets": ["TSMC"]},
        ]},
        {"run_id": "r2", "started_at": "2026-04-13T02:00:00+00:00", "events": [
            {"event": "북한 미사일 발사", "severity": 5, "category": "conflict",
             "signal": "sell", "region": "korea", "affected_assets": ["KOSPI"]},
        ]},
    ]
    with (log_dir / f"kaven_{_DATE}.jsonl").open("w", encoding="utf-8") as f:
        for run in runs:
            f.write(json.dumps(run, ensure_ascii=False) + "\n")
    return log_dir


def test_query_events_no_filter_returns_all():
    result = query_events(_make_log_dir(), date=_DATE)
    assert result["total"] == 3
    assert result["matched"] == 3
    assert result["date"] == "2026-04-13"
    # severity 내림차순 정렬
    assert [e["severity"] for e in result["events"]] == [5, 4, 3]


def test_query_events_filters():
    log_dir = _make_log_dir()

    by_sev = query_events(log_dir, date=_DATE, severity_min=4)
    assert by_sev["matched"] == 2

    by_region = query_events(log_dir, date=_DATE, region="korea")
    assert by_region["matched"] == 1
    assert by_region["events"][0]["region_name"] == "한반도"

    by_signal = query_events(log_dir, date=_DATE, signal="hedge")
    assert by_signal["matched"] == 1

    by_q = query_events(log_dir, date=_DATE, q="유조선")
    assert by_q["matched"] == 1


def test_query_events_limit():
    result = query_events(_make_log_dir(), date=_DATE, limit=1)
    assert result["matched"] == 3
    assert result["returned"] == 1
    assert result["events"][0]["severity"] == 5


def test_agent_context_contains_briefing_sections():
    ctx = build_agent_context(_make_log_dir(), date=_DATE)
    assert ctx["threat_level"] == 5
    md = ctx["context"]
    assert "KAVEN OPS BRIEFING — 2026-04-13" in md
    assert "THREAT LEVEL: 5/5" in md
    assert "## ACTIVE REGIONS" in md
    assert "korea" in md
    assert "북한 미사일 발사" in md
    assert "## ASSET IMPACT" in md
    assert "KOSPI" in md


def test_agent_context_severity_filter_and_cap():
    ctx = build_agent_context(_make_log_dir(), date=_DATE, max_events=1, severity_min=4)
    assert ctx["event_count"] == 1
    assert "북한 미사일 발사" in ctx["context"]
    assert "대만 해협 군사 훈련" not in ctx["context"]


def test_manifest_structure():
    manifest = build_agent_manifest()
    assert manifest["service"] == "kaven"
    paths = {e["path"] for e in manifest["endpoints"]}
    assert {"/agent/manifest", "/agent/context", "/agent/events", "/ops/summary"} <= paths
    mcp_tools = {t["name"] for t in manifest["mcp"]["tools"]}
    assert mcp_tools == {t["name"] for t in AGENT_TOOLS}
    vocab = manifest["vocabulary"]
    assert "hormuz" in vocab["regions"]
    assert "conflict" in vocab["categories"]
    assert "5" in vocab["severity_levels"]

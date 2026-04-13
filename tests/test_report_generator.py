"""report_generator 단위 테스트."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_a, **_k: None))
sys.modules.setdefault(
    "collectors",
    types.SimpleNamespace(
        ais_collector=types.SimpleNamespace(collect=None),
        adsb_collector=types.SimpleNamespace(collect=None),
        news_collector=types.SimpleNamespace(collect=None),
        social_collector=types.SimpleNamespace(collect=None),
    ),
)
sys.modules.setdefault("analyzer", types.SimpleNamespace(analyze=None))
sys.modules.setdefault("signal_generator", types.SimpleNamespace(process_signals=None))

from src.kaven.report_generator import generate_daily_report


_TEMP_DIRS: list[TemporaryDirectory] = []  # prevent GC during test run


def _make_log_dir(events_per_run: list[list[dict]], date: str = "20260413") -> Path:
    """임시 로그 디렉터리 생성 + JSONL 작성."""
    tmpdir = TemporaryDirectory()
    _TEMP_DIRS.append(tmpdir)
    log_dir = Path(tmpdir.name)
    log_file = log_dir / f"kaven_{date}.jsonl"
    with log_file.open("w", encoding="utf-8") as f:
        for i, events in enumerate(events_per_run):
            run = {
                "run_id": f"{date}_{i:06d}",
                "started_at": f"2026-04-13T{i:02d}:00:00+00:00",
                "events": events,
            }
            f.write(json.dumps(run, ensure_ascii=False) + "\n")
    return log_dir


def test_empty_day_returns_zero_events():
    """이벤트가 없는 날은 빈 리포트."""
    report = generate_daily_report(Path("/nonexistent"), "99990101")
    assert report["total_events"] == 0
    assert report["unique_events"] == 0
    assert "이벤트 없음" in report["markdown"]


def test_single_event_report():
    """이벤트 1건이면 리포트에 해당 이벤트 포함."""
    events = [[{
        "event": "호르무즈 해협 선박 통행량 급감",
        "severity": 4,
        "category": "energy",
        "signal": "hedge",
        "region": "hormuz",
        "affected_assets": ["WTI", "KOSPI"],
        "reasoning": "유가 급등 우려",
    }]]
    log_dir = _make_log_dir(events)
    report = generate_daily_report(log_dir, "20260413")

    assert report["total_events"] == 1
    assert report["unique_events"] == 1
    assert report["max_severity"] == 4
    assert "hormuz" in report["by_region"]
    assert report["by_region"]["hormuz"]["max_severity"] == 4
    assert "호르무즈" in report["markdown"]
    assert "WTI" in report["markdown"]


def test_dedup_same_event_across_runs():
    """같은 이벤트가 여러 run에서 반복되면 unique_events에선 1건."""
    same_event = {
        "event": "호르무즈 해협 선박 통행량 급감",
        "severity": 4,
        "category": "energy",
        "region": "hormuz",
        "affected_assets": ["WTI"],
    }
    events = [[same_event], [same_event], [same_event]]
    log_dir = _make_log_dir(events)
    report = generate_daily_report(log_dir, "20260413")

    assert report["total_events"] == 3
    assert report["unique_events"] == 1


def test_multiple_regions_sorted_by_severity():
    """여러 지역이 있으면 severity 높은 순으로 정렬."""
    events = [[
        {"event": "호르무즈 위기", "severity": 5, "category": "energy", "region": "hormuz", "affected_assets": []},
        {"event": "대만 긴장", "severity": 2, "category": "semiconductor", "region": "taiwan", "affected_assets": []},
    ]]
    log_dir = _make_log_dir(events)
    report = generate_daily_report(log_dir, "20260413")

    md = report["markdown"]
    # 호르무즈가 대만보다 먼저 나와야 함 (severity 높은 순)
    hormuz_pos = md.find("호르무즈")
    taiwan_pos = md.find("대만")
    assert hormuz_pos < taiwan_pos, "호르무즈(sev 5)가 대만(sev 2)보다 먼저 나와야 함"


def test_affected_assets_aggregation():
    """영향 자산 빈도가 정확히 집계."""
    events = [[
        {"event": "이벤트 A", "severity": 3, "category": "energy", "region": "hormuz", "affected_assets": ["WTI", "KOSPI"]},
        {"event": "이벤트 B", "severity": 3, "category": "conflict", "region": "taiwan", "affected_assets": ["삼성전자", "KOSPI"]},
    ]]
    log_dir = _make_log_dir(events)
    report = generate_daily_report(log_dir, "20260413")

    assert report["affected_assets"]["KOSPI"] == 2
    assert report["affected_assets"]["WTI"] == 1
    assert report["affected_assets"]["삼성전자"] == 1


def test_category_distribution():
    """카테고리 분포 집계."""
    events = [[
        {"event": "에너지1", "severity": 3, "category": "energy", "region": "hormuz", "affected_assets": []},
        {"event": "에너지2", "severity": 2, "category": "energy", "region": "redsa", "affected_assets": []},
        {"event": "분쟁1", "severity": 4, "category": "conflict", "region": "ukraine", "affected_assets": []},
    ]]
    log_dir = _make_log_dir(events)
    report = generate_daily_report(log_dir, "20260413")

    assert report["by_category"]["energy"] == 2
    assert report["by_category"]["conflict"] == 1

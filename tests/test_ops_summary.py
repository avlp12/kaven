"""webapp.backend.ops build_ops_summary 단위 테스트."""

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

from webapp.backend.ops import REGION_COORDS, build_ops_summary


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


def test_empty_day_returns_zero_threat():
    """이벤트가 없는 날은 threat_level 0, 지역은 전부 severity 0."""
    summary = build_ops_summary(Path("/nonexistent"), "99990101")
    assert summary["threat_level"] == 0
    assert summary["totals"]["unique_events"] == 0
    assert summary["events"] == []
    assert len(summary["regions"]) == len(REGION_COORDS)
    assert all(r["severity"] == 0 for r in summary["regions"])


def test_event_enriched_with_coords_and_id():
    """이벤트에 지역 좌표/이름/안정적 ID가 부여된다."""
    log_dir = _make_log_dir([[{
        "event": "호르무즈 해협 선박 통행량 급감",
        "severity": 4,
        "category": "energy",
        "signal": "hedge",
        "region": "hormuz",
        "affected_assets": ["WTI"],
    }]])
    summary = build_ops_summary(log_dir, "20260413")
    assert summary["threat_level"] == 4
    ev = summary["events"][0]
    assert ev["lat"] == REGION_COORDS["hormuz"]["lat"]
    assert ev["lng"] == REGION_COORDS["hormuz"]["lng"]
    assert ev["region_name"] == "호르무즈 해협"
    assert len(ev["id"]) == 12

    # 같은 내용이면 같은 ID (안정성)
    summary2 = build_ops_summary(log_dir, "20260413")
    assert summary2["events"][0]["id"] == ev["id"]


def test_regions_sorted_by_severity():
    """지역 목록은 severity 내림차순 정렬."""
    log_dir = _make_log_dir([[
        {"event": "대만 해협 군사 훈련", "severity": 3, "region": "taiwan"},
        {"event": "한반도 미사일 발사", "severity": 5, "region": "korea"},
    ]])
    summary = build_ops_summary(log_dir, "20260413")
    assert summary["regions"][0]["code"] == "korea"
    assert summary["regions"][0]["severity"] == 5
    assert summary["regions"][1]["code"] == "taiwan"


def test_asset_aggregation():
    """자산 통계는 count + max_severity 집계, 정렬 포함."""
    log_dir = _make_log_dir([[
        {"event": "이벤트 A", "severity": 5, "region": "korea", "affected_assets": ["KOSPI"]},
        {"event": "이벤트 B", "severity": 2, "region": "hormuz", "affected_assets": ["WTI", "KOSPI"]},
    ]])
    summary = build_ops_summary(log_dir, "20260413")
    assets = {a["name"]: a for a in summary["assets"]}
    assert assets["KOSPI"]["count"] == 2
    assert assets["KOSPI"]["max_severity"] == 5
    assert assets["WTI"]["count"] == 1
    assert summary["assets"][0]["name"] == "KOSPI"  # max_severity 우선 정렬


def test_dedup_applied():
    """동일 이벤트 텍스트는 중복 제거되고 최고 severity 유지."""
    dup = {"event": "호르무즈 해협 봉쇄 위협 고조", "region": "hormuz"}
    log_dir = _make_log_dir([
        [{**dup, "severity": 3}],
        [{**dup, "severity": 5}],
    ])
    summary = build_ops_summary(log_dir, "20260413")
    assert summary["totals"]["events"] == 2
    assert summary["totals"]["unique_events"] == 1
    assert summary["events"][0]["severity"] == 5


def test_watchzones_included():
    """감시 구역(AIS/ADS-B)이 kind와 bounding box와 함께 포함된다."""
    summary = build_ops_summary(Path("/nonexistent"), "99990101")
    kinds = {z["kind"] for z in summary["watchzones"]}
    assert kinds == {"ais", "adsb"}
    for z in summary["watchzones"]:
        assert z["lat_min"] is not None
        assert z["lon_max"] is not None
        assert "enabled" in z


def test_unknown_region_has_no_coords():
    """좌표 미등록 지역 이벤트는 lat/lng None으로 안전 처리."""
    log_dir = _make_log_dir([[{"event": "미상 지역 이벤트", "severity": 2, "region": "atlantis"}]])
    summary = build_ops_summary(log_dir, "20260413")
    ev = summary["events"][0]
    assert ev["lat"] is None
    assert ev["region_name"] == "atlantis"

"""src.kaven.log_store 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.kaven.log_store import (
    available_dates,
    day_log_paths,
    dedup_events,
    default_log_dir,
    iter_all_runs,
    load_day_events,
)

_TEMP_DIRS: list[TemporaryDirectory] = []  # prevent GC during test run


def _write_log(log_dir: Path, filename: str, runs: list[dict]) -> None:
    with (log_dir / filename).open("w", encoding="utf-8") as f:
        for run in runs:
            f.write(json.dumps(run, ensure_ascii=False) + "\n")


def _tmp_dir() -> Path:
    tmpdir = TemporaryDirectory()
    _TEMP_DIRS.append(tmpdir)
    return Path(tmpdir.name)


def test_day_log_paths_prefers_kaven_and_reads_maven():
    """kaven_/maven_ 두 prefix 모두 인식, kaven_ 우선."""
    log_dir = _tmp_dir()
    _write_log(log_dir, "kaven_20260101.jsonl", [{"run_id": "a", "events": []}])
    _write_log(log_dir, "maven_20260101.jsonl", [{"run_id": "b", "events": []}])
    paths = day_log_paths(log_dir, "20260101")
    assert [p.name for p in paths] == ["kaven_20260101.jsonl", "maven_20260101.jsonl"]


def test_load_day_events_attaches_run_meta():
    """이벤트에 _run_id/_started_at 메타가 부착된다."""
    log_dir = _tmp_dir()
    _write_log(log_dir, "kaven_20260101.jsonl", [
        {"run_id": "r1", "started_at": "2026-01-01T01:00:00+00:00",
         "events": [{"event": "e1", "severity": 2}]},
    ])
    events = load_day_events(log_dir, "20260101")
    assert len(events) == 1
    assert events[0]["_run_id"] == "r1"
    assert events[0]["_started_at"].startswith("2026-01-01")


def test_load_day_events_skips_corrupt_lines():
    """파싱 불가 라인은 무시하고 나머지는 정상 로드."""
    log_dir = _tmp_dir()
    path = log_dir / "kaven_20260101.jsonl"
    path.write_text(
        'not-json\n{"run_id": "ok", "events": [{"event": "e", "severity": 1}]}\n',
        encoding="utf-8",
    )
    events = load_day_events(log_dir, "20260101")
    assert len(events) == 1


def test_iter_all_runs_sorted_desc():
    """전체 run은 started_at 내림차순."""
    log_dir = _tmp_dir()
    _write_log(log_dir, "kaven_20260101.jsonl", [
        {"run_id": "old", "started_at": "2026-01-01T01:00:00+00:00", "events": []},
    ])
    _write_log(log_dir, "kaven_20260102.jsonl", [
        {"run_id": "new", "started_at": "2026-01-02T01:00:00+00:00", "events": []},
    ])
    runs = iter_all_runs(log_dir)
    assert [r["run_id"] for r in runs] == ["new", "old"]


def test_available_dates_merges_prefixes():
    """kaven_/maven_ 파일 날짜를 합쳐 최신순으로 반환."""
    log_dir = _tmp_dir()
    _write_log(log_dir, "kaven_20260102.jsonl", [])
    _write_log(log_dir, "maven_20260101.jsonl", [])
    assert available_dates(log_dir) == ["20260102", "20260101"]


def test_dedup_keeps_highest_severity():
    """동일 텍스트는 최고 severity만 유지."""
    events = [
        {"event": "같은 사건", "severity": 2},
        {"event": "같은 사건", "severity": 4},
        {"event": "다른 사건", "severity": 1},
    ]
    unique = dedup_events(events)
    assert len(unique) == 2
    assert max(e["severity"] for e in unique) == 4


def test_default_log_dir_env_override(monkeypatch):
    """KAVEN_LOG_DIR 환경변수로 로그 디렉터리 override."""
    monkeypatch.setenv("KAVEN_LOG_DIR", "/tmp/kaven-test-logs")
    assert default_log_dir() == Path("/tmp/kaven-test-logs")
    monkeypatch.delenv("KAVEN_LOG_DIR")
    assert default_log_dir().name == "logs"

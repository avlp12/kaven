"""
Kaven Log Store — JSONL 실행 로그 읽기 단일 소스.

기존에 webapp/app.py, report_generator, ops 집계에 각각 중복돼 있던
로그 파일 탐색/파싱/중복제거 로직을 한곳에 모은다.

로그 파일명: ``kaven_YYYYMMDD.jsonl`` (구버전 ``maven_*.jsonl`` 읽기 호환).
로그 디렉터리: ``KAVEN_LOG_DIR`` 환경변수 → 기본 ``src/kaven/logs``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_FILE_PREFIXES = ("kaven_", "maven_")  # maven_은 하위호환


def default_log_dir() -> Path:
    """로그 디렉터리 결정 (KAVEN_LOG_DIR 환경변수 override 지원)."""
    env = os.environ.get("KAVEN_LOG_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return Path(__file__).parent / "logs"


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def day_log_paths(log_dir: Path, date_str: str) -> list[Path]:
    """특정 날짜의 존재하는 로그 파일 목록 (kaven_ 우선, maven_ 하위호환)."""
    return [
        p for p in (log_dir / f"{prefix}{date_str}.jsonl" for prefix in _FILE_PREFIXES)
        if p.exists()
    ]


def iter_day_runs(log_dir: Path, date_str: str) -> list[dict[str, Any]]:
    """특정 날짜의 run 레코드 전체 (파싱 실패 라인은 skip)."""
    runs: list[dict[str, Any]] = []
    for path in day_log_paths(log_dir, date_str):
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    runs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return runs


def load_day_events(log_dir: Path, date_str: str) -> list[dict[str, Any]]:
    """특정 날짜의 모든 이벤트. run 메타(`_run_id`, `_started_at`)를 부착."""
    events: list[dict[str, Any]] = []
    for run in iter_day_runs(log_dir, date_str):
        for ev in run.get("events", []):
            ev["_run_id"] = run.get("run_id", "")
            ev["_started_at"] = run.get("started_at", "")
            events.append(ev)
    return events


def iter_all_runs(log_dir: Path) -> list[dict[str, Any]]:
    """모든 로그 파일의 run 레코드 (started_at 내림차순)."""
    runs: list[dict[str, Any]] = []
    for prefix in _FILE_PREFIXES:
        for log_file in Path(log_dir).glob(f"{prefix}*.jsonl"):
            with log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        runs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    runs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return runs


def available_dates(log_dir: Path) -> list[str]:
    """로그가 존재하는 날짜(YYYYMMDD) 목록, 최신순."""
    dates: set[str] = set()
    for prefix in _FILE_PREFIXES:
        for p in Path(log_dir).glob(f"{prefix}*.jsonl"):
            dates.add(p.stem.replace(prefix, ""))
    return sorted(dates, reverse=True)


def recent_dates(days: int) -> list[str]:
    """오늘부터 과거 N일의 날짜 문자열 (오늘 포함, 최신순)."""
    today = datetime.now(timezone.utc)
    return [(today - timedelta(days=d)).strftime("%Y%m%d") for d in range(days)]


def dedup_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 event 텍스트(앞 60자)의 중복 제거. 가장 높은 severity만 유지."""
    seen: dict[str, dict[str, Any]] = {}
    for ev in events:
        key = ev.get("event", "")[:60].strip().lower()
        if key not in seen or ev.get("severity", 0) > seen[key].get("severity", 0):
            seen[key] = ev
    return list(seen.values())

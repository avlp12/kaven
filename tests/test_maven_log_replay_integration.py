"""Maven 샘플 로그 리플레이 통합 테스트.

src/maven/logs/maven_20260403.jsonl 파일의 실제 이벤트를 순차 리플레이하여
dedup 로직이 동일 사건을 안정적으로 제거하는지 검증한다.
"""

import json
import os
import sys
import types
from pathlib import Path

# maven.py가 `from collectors import ...` 등 로컬 임포트를 사용하므로
# src/maven을 sys.path에 추가하고, 무거운 의존성을 스텁으로 대체
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "maven"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for mod_name in ("feedparser",):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

from src.maven.maven import (
    _deduplicate_events,
    _update_cache,
    _content_fingerprint,
)

SAMPLE_LOG = Path(__file__).resolve().parent.parent / "src" / "maven" / "logs" / "maven_20260403.jsonl"


def _load_runs() -> list[dict]:
    """샘플 로그에서 모든 run을 로드."""
    assert SAMPLE_LOG.exists(), f"샘플 로그 없음: {SAMPLE_LOG}"
    runs = []
    with open(SAMPLE_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    return runs


def test_replay_sample_log_deduplicates_and_stays_stable():
    """
    220개 run을 순차 리플레이했을 때:
    1. 첫 run에서 이벤트가 1건 이상 나와야 한다 (신규).
    2. 이후 동일 이벤트가 반복되면 dedup에 의해 걸러져야 한다.
    3. 전체 run 대비 실제 발송 건수가 합리적인 범위여야 한다
       (전부 통과하면 dedup 고장, 전부 차단이면 과도한 차단).
    """
    runs = _load_runs()
    assert len(runs) > 0, "로그가 비어 있음"

    cache = {"date": "2026-04-03", "sent": []}
    total_events = 0
    total_passed = 0

    for run in runs:
        events = run.get("events", [])
        if not events:
            continue
        total_events += len(events)

        passed = _deduplicate_events(events, cache)
        total_passed += len(passed)

        # 통과한 이벤트를 캐시에 기록
        _update_cache(cache, passed)

    # 최소 1건 이상 통과 (첫 run의 신규 이벤트)
    assert total_passed >= 1, f"통과 이벤트 0건 — dedup이 모든 것을 차단"

    # 전체 이벤트 대비 통과율이 50% 미만이어야 함 (같은 이벤트가 반복되므로)
    pass_rate = total_passed / max(total_events, 1)
    assert pass_rate < 0.50, (
        f"통과율 {pass_rate:.1%} — dedup이 충분히 작동하지 않음 "
        f"(총 {total_events}건 중 {total_passed}건 통과)"
    )


def test_replay_cache_does_not_grow_unbounded():
    """동일 이벤트가 반복되면 캐시 항목 수가 무한 증가하면 안 된다."""
    runs = _load_runs()
    cache = {"date": "2026-04-03", "sent": []}

    for run in runs:
        events = run.get("events", [])
        if not events:
            continue
        passed = _deduplicate_events(events, cache)
        _update_cache(cache, passed)

    # 220개 run이지만 고유 이벤트는 소수 → 캐시 항목 50개 미만이어야 합리적
    cache_size = len(cache["sent"])
    assert cache_size < 50, (
        f"캐시 항목 {cache_size}개 — 병합이 제대로 안 됨 (무한 증가 위험)"
    )

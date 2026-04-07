from __future__ import annotations

import json
import logging
import sys
import types
from pathlib import Path

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))
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

from src.kaven import kaven


def test_replay_sample_log_deduplicates_and_stays_stable() -> None:
    kaven.logger.setLevel(logging.WARNING)

    log_path = Path("src/kaven/logs/maven_20260403.jsonl")
    assert log_path.exists(), "샘플 리플레이 로그 파일이 필요합니다."

    cache = {"date": "2026-04-07", "sent": []}
    raw_count = 0
    sendable_count = 0

    # 통합 리플레이: run_once 결과 로그를 순차 재주입
    with log_path.open(encoding="utf-8") as fp:
        for idx, line in enumerate(fp):
            run = json.loads(line)
            events = run.get("events", [])
            raw_count += len(events)

            deduped = kaven._deduplicate_events(events, cache)
            sendable_count += len(deduped)
            kaven._update_cache(cache, deduped)

            if idx >= 199:  # 테스트 시간 제어
                break

    assert raw_count > 0
    assert sendable_count > 0
    assert sendable_count < raw_count

    # 반복 이벤트가 많은 샘플 로그에서 dedup 비율이 충분히 낮아야 함
    dedup_ratio = sendable_count / raw_count
    assert dedup_ratio < 0.20

    # 캐시는 발송 가능 이벤트보다 커질 수 없어야 함
    assert len(cache["sent"]) <= sendable_count

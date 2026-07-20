from __future__ import annotations

import json
import os
import sys
import types
import asyncio
from pathlib import Path


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

from src.kaven import kaven, signal_generator


def test_social_only_inputs_produce_stable_trigger_signatures() -> None:
    first = {
        "social": [
            {
                "url": "https://x.com/reporter/status/12345?s=20",
                "text": "Breaking report",
                "timestamp": "2026-07-20T01:00:00Z",
            },
            {
                "author": "observer",
                "text": "  Strait   traffic is DOWN  sharply ",
                "timestamp": "2026-07-20T01:00:00Z",
            },
        ]
    }
    repeated = {
        "social": [
            {
                "url": "https://x.com/reporter/status/12345?ref=home",
                "text": "Edited preview text",
                "timestamp": "2026-07-20T02:00:00Z",
            },
            {
                "author": "observer",
                "text": "strait traffic is down sharply",
                "timestamp": "2026-07-20T02:00:00Z",
            },
        ]
    }

    signatures = kaven._trigger_signatures(first)

    assert len(signatures) == 2
    assert signatures == kaven._trigger_signatures(repeated)
    assert any(signature.startswith("social:url:") for signature in signatures)
    assert any(signature.startswith("social:hash:") for signature in signatures)


def test_analysis_result_distinguishes_explicit_empty_from_invalid() -> None:
    assert kaven._analysis_events({"events": [], "status": "ok"}) == ([], True)
    assert kaven._analysis_events({"events": [], "valid": True}) == ([], True)
    assert kaven._analysis_events([]) == ([], True)  # legacy analyzer compatibility

    assert kaven._analysis_events({"events": [], "status": "error"}) == ([], False)
    assert kaven._analysis_events({"events": "not-a-list", "status": "ok"}) == ([], False)
    assert kaven._analysis_events(None) == ([], False)


def test_invalid_analysis_does_not_consume_input_signature(monkeypatch, tmp_path: Path) -> None:
    collected = {"news": [{"url": "https://example.test/new"}], "social": [], "ais": [], "adsb": []}

    async def collect():
        return collected

    async def analyze(_collected):
        return {"events": [], "status": "error", "error": "provider unavailable"}

    async def process(_events):
        raise AssertionError("invalid analysis must not reach delivery")

    monkeypatch.setattr(kaven, "LOG_DIR", tmp_path)
    monkeypatch.setattr(kaven, "run_collectors", collect)
    monkeypatch.setitem(sys.modules, "analyzer", types.SimpleNamespace(analyze=analyze))
    monkeypatch.setitem(sys.modules, "signal_generator", types.SimpleNamespace(process_signals=process))

    result = asyncio.run(kaven.run_once())
    cache = json.loads((tmp_path / "sent_cache.json").read_text())

    assert result["events"] == []
    assert cache["seen_inputs"] == {}


def test_failed_delivery_is_not_cached_and_input_remains_retryable(monkeypatch, tmp_path: Path) -> None:
    collected = {"news": [{"url": "https://example.test/new"}], "social": [], "ais": [], "adsb": []}
    event = {"event": "긴급 사건", "severity": 4, "signal": "hedge", "affected_assets": []}

    async def collect():
        return collected

    async def analyze(_collected):
        return [event.copy()]

    async def process(_events):
        return {
            "sent": 0,
            "logged": 1,
            "errors": ["telegram down"],
            "event_results": [
                {"index": 0, "required_channels": ["topic"], "sent_channels": [], "delivery_complete": False}
            ],
        }

    monkeypatch.setattr(kaven, "LOG_DIR", tmp_path)
    monkeypatch.setattr(kaven, "run_collectors", collect)
    monkeypatch.setitem(sys.modules, "analyzer", types.SimpleNamespace(analyze=analyze))
    monkeypatch.setitem(sys.modules, "signal_generator", types.SimpleNamespace(process_signals=process))

    asyncio.run(kaven.run_once())
    cache = json.loads((tmp_path / "sent_cache.json").read_text())

    assert cache["sent"] == []
    assert cache["seen_inputs"] == {}


def test_process_signals_reports_success_per_event_and_channel(monkeypatch) -> None:
    calls: list[str] = []

    async def topic(_text, _chat_id, _thread_id):
        calls.append("topic")

    async def dm(_text, _user_id):
        calls.append("dm")
        raise RuntimeError("DM unavailable")

    monkeypatch.setattr(signal_generator, "_send_telegram", topic)
    monkeypatch.setattr(signal_generator, "_send_telegram_dm", dm)

    result = asyncio.run(
        signal_generator.process_signals(
            [
                {"event": "일반", "severity": 4},
                {"event": "긴급", "severity": 5},
            ]
        )
    )

    assert calls == ["topic", "topic", "dm"]
    assert result["event_results"] == [
        {
            "index": 0,
            "required_channels": ["topic"],
            "sent_channels": ["topic"],
            "delivery_complete": True,
            "errors": [],
        },
        {
            "index": 1,
            "required_channels": ["topic", "dm"],
            "sent_channels": ["topic"],
            "delivery_complete": False,
            "errors": ["dm: DM unavailable"],
        },
    ]


def test_process_result_selects_only_successfully_delivered_events() -> None:
    events = [{"event": "성공", "severity": 4}, {"event": "실패", "severity": 4}]
    result = {
        "event_results": [
            {"index": 0, "delivery_complete": True},
            {"index": 1, "delivery_complete": False},
        ]
    }

    assert kaven._successfully_processed_events(events, result) == ([events[0]], False)


def test_save_sent_cache_replaces_file_atomically(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(kaven, "LOG_DIR", tmp_path)
    replacements: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def recording_replace(source, destination):
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(kaven.os, "replace", recording_replace)

    kaven._save_sent_cache({"date": "2026-07-20", "sent": [], "seen_inputs": {}})

    assert len(replacements) == 1
    source, destination = replacements[0]
    assert source != destination
    assert destination == tmp_path / "sent_cache.json"
    assert not source.exists()
    assert json.loads(destination.read_text())["date"] == "2026-07-20"


def test_process_signals_retries_only_channels_not_already_delivered(monkeypatch) -> None:
    calls: list[str] = []

    async def topic(_text, _chat_id, _thread_id):
        calls.append("topic")

    async def dm(_text, _user_id):
        calls.append("dm")

    monkeypatch.setattr(signal_generator, "_send_telegram", topic)
    monkeypatch.setattr(signal_generator, "_send_telegram_dm", dm)

    result = asyncio.run(
        signal_generator.process_signals(
            [{"event": "긴급", "severity": 5, "_delivered_channels": ["topic"]}]
        )
    )

    assert calls == ["dm"]
    assert result["event_results"][0]["sent_channels"] == ["topic", "dm"]
    assert result["event_results"][0]["delivery_complete"] is True


def test_partial_delivery_ledger_is_persisted_and_reapplied() -> None:
    event = {"event": "긴급", "severity": 5, "region": "korea", "source_url": "https://example.test/1"}
    cache = {"sent": [], "seen_inputs": {}, "partial_deliveries": {}}
    result = {
        "event_results": [
            {"index": 0, "sent_channels": ["topic"], "delivery_complete": False}
        ]
    }

    kaven._record_delivery_progress(cache, [event], result)
    prepared = kaven._apply_delivery_progress([event.copy()], cache)

    assert prepared[0]["_delivered_channels"] == ["topic"]


def test_run_lock_rejects_concurrent_execution(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(kaven, "LOG_DIR", tmp_path)

    with kaven._run_lock():
        try:
            with kaven._run_lock():
                raise AssertionError("second lock acquisition must fail")
        except kaven.RunAlreadyInProgress:
            pass

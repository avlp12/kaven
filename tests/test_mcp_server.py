"""src.kaven.mcp_server JSON-RPC 처리 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.kaven.agent_service import AGENT_TOOLS
from src.kaven.mcp_server import PROTOCOL_VERSION, handle_message

_TEMP_DIRS: list[TemporaryDirectory] = []  # prevent GC during test run

_DATE = "20260413"


def _use_temp_log_dir(monkeypatch) -> Path:
    tmpdir = TemporaryDirectory()
    _TEMP_DIRS.append(tmpdir)
    log_dir = Path(tmpdir.name)
    run = {"run_id": "r1", "started_at": "2026-04-13T01:00:00+00:00", "events": [
        {"event": "북한 미사일 발사", "severity": 5, "category": "conflict",
         "signal": "sell", "region": "korea", "affected_assets": ["KOSPI"]},
    ]}
    (log_dir / f"kaven_{_DATE}.jsonl").write_text(
        json.dumps(run, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("KAVEN_LOG_DIR", str(log_dir))
    return log_dir


def test_initialize_handshake():
    resp = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert resp["result"]["serverInfo"]["name"] == "kaven"
    assert "tools" in resp["result"]["capabilities"]


def test_initialized_notification_returns_none():
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_matches_agent_tools():
    resp = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {t["name"] for t in AGENT_TOOLS}
    for tool in resp["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object"


def test_tools_call_ops_summary(monkeypatch):
    _use_temp_log_dir(monkeypatch)
    resp = handle_message({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "kaven_ops_summary", "arguments": {"date": _DATE}},
    })
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["threat_level"] == 5
    assert payload["totals"]["unique_events"] == 1


def test_tools_call_events_filter(monkeypatch):
    _use_temp_log_dir(monkeypatch)
    resp = handle_message({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "kaven_events",
                   "arguments": {"date": _DATE, "region": "korea", "severity_min": 5}},
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["matched"] == 1
    assert payload["events"][0]["event"] == "북한 미사일 발사"


def test_tools_call_unknown_tool_is_tool_error():
    resp = handle_message({
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {"name": "nope", "arguments": {}},
    })
    assert resp["result"]["isError"] is True


def test_unknown_method_returns_jsonrpc_error():
    resp = handle_message({"jsonrpc": "2.0", "id": 6, "method": "resources/list"})
    assert resp["error"]["code"] == -32601

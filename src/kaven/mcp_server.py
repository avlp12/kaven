"""
Kaven MCP Server — AI 에이전트용 Model Context Protocol 서버 (stdio).

외부 SDK 의존성 없이 MCP stdio transport(개행 구분 JSON-RPC 2.0)를 직접 구현.
Claude Code / Claude Desktop 등 MCP 클라이언트에 다음과 같이 등록한다:

    # Claude Code
    claude mcp add kaven -- python -m src.kaven.mcp_server

    # claude_desktop_config.json
    {"mcpServers": {"kaven": {
        "command": "python", "args": ["-m", "src.kaven.mcp_server"],
        "cwd": "/path/to/kaven"}}}

로그 디렉터리는 ``KAVEN_LOG_DIR`` 환경변수로 override 가능.

제공 도구는 ``src/kaven/agent_service.py``의 ``AGENT_TOOLS`` 참조.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from src.kaven.agent_service import (
    AGENT_TOOLS,
    build_agent_context,
    query_events,
)
from src.kaven.aggregates import portfolio_history, region_detail
from src.kaven.config_loader import load_config
from src.kaven.log_store import default_log_dir
from src.kaven.ops_summary import build_ops_summary
from src.kaven.report_generator import generate_daily_report
from src.kaven.version import __version__

PROTOCOL_VERSION = "2024-11-05"


# ── Tool dispatch ───────────────────────────────────────────────


def _tool_run_collection() -> dict[str, Any]:
    """수집 파이프라인 1회 실행 (heavy import는 지연 로드)."""
    import asyncio

    from src.kaven.kaven import run_once
    return asyncio.run(run_once())


def call_tool(name: str, args: dict[str, Any]) -> Any:
    """도구 이름 → 코어 함수 디스패치. 미등록 도구는 ValueError."""
    log_dir = default_log_dir()
    date = args.get("date")

    if name == "kaven_ops_summary":
        return build_ops_summary(log_dir, date)
    if name == "kaven_events":
        return query_events(
            log_dir,
            date=date,
            severity_min=args.get("severity_min"),
            region=args.get("region"),
            category=args.get("category"),
            signal=args.get("signal"),
            q=args.get("query"),
            limit=int(args.get("limit", 50)),
        )
    if name == "kaven_agent_context":
        return build_agent_context(
            log_dir,
            date=date,
            max_events=int(args.get("max_events", 20)),
            severity_min=int(args.get("severity_min", 0)),
        )
    if name == "kaven_region":
        detail = region_detail(log_dir, args.get("region", ""), int(args.get("days", 7)))
        if detail is None:
            raise ValueError(f"unknown region: {args.get('region')!r}")
        return detail
    if name == "kaven_daily_report":
        return generate_daily_report(log_dir, date)
    if name == "kaven_portfolio":
        assets = portfolio_history(log_dir, int(args.get("days", 7)))
        asset_name = args.get("asset")
        if asset_name:
            match = next((a for a in assets if a["name"] == asset_name), None)
            if match is None:
                raise ValueError(f"asset not found: {asset_name!r}")
            return match
        return {"asset_count": len(assets), "assets": assets}
    if name == "kaven_config":
        return load_config()
    if name == "kaven_run_collection":
        return _tool_run_collection()

    raise ValueError(f"unknown tool: {name!r}")


# ── JSON-RPC handling ───────────────────────────────────────────


def _result(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    """
    MCP JSON-RPC 메시지 1건 처리. notification이면 None 반환.

    지원 메서드: initialize, ping, tools/list, tools/call.
    """
    method = msg.get("method", "")
    msg_id = msg.get("id")
    is_notification = "id" not in msg

    if method == "initialize":
        return _result(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "kaven", "version": __version__},
        })
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": AGENT_TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            payload = call_tool(name, args)
            text = json.dumps(payload, ensure_ascii=False, default=str)
            return _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
        except ValueError as e:
            return _result(msg_id, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        except Exception as e:  # 도구 내부 오류도 프로토콜은 유지
            return _result(msg_id, {
                "content": [{"type": "text", "text": f"tool execution failed: {e}"}],
                "isError": True,
            })

    if is_notification:
        return None
    return _error(msg_id, -32601, f"method not found: {method}")


def main() -> None:
    """stdio 루프 — stdin에서 개행 구분 JSON-RPC를 읽고 stdout으로 응답."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps(_error(None, -32700, "parse error"), ensure_ascii=False), flush=True)
            continue
        response = handle_message(msg)
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

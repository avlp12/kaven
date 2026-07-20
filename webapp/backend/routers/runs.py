"""실행 로그(runs) 라우터 — 목록/최신/파일/1회 실행/SSE 스트림."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.kaven.log_store import (
    available_dates,
    day_log_paths,
    default_log_dir,
    iter_all_runs,
    today_str,
)
from webapp.backend.security import require_admin

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/latest")
def latest_run() -> dict[str, Any]:
    paths = day_log_paths(default_log_dir(), today_str())
    if not paths:
        raise HTTPException(status_code=404, detail="No run log found for today")

    last_line = None
    with paths[0].open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last_line = line
    if not last_line:
        raise HTTPException(status_code=404, detail="Log file is empty")
    parsed = json.loads(last_line)
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=500, detail="Latest run log is not a JSON object")
    return parsed


@router.get("")
def list_runs(
    limit: int = 20,
    severity_min: int | None = None,
    category: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    runs = iter_all_runs(default_log_dir())
    filtered: list[dict[str, Any]] = []

    for run in runs:
        events = run.get("events", [])
        keep_events = []
        for event in events:
            if severity_min is not None and event.get("severity", 0) < severity_min:
                continue
            if category and event.get("category") != category:
                continue
            if q and q.lower() not in json.dumps(event, ensure_ascii=False).lower():
                continue
            keep_events.append(event)

        # 필터가 없으면 이벤트가 0건인 run도 목록에 보여준다.
        no_filter = severity_min is None and not category and not q
        if keep_events or no_filter:
            copied = dict(run)
            copied["events"] = keep_events if keep_events else events
            filtered.append(copied)

        if len(filtered) >= limit:
            break

    return {"runs": filtered, "count": len(filtered)}


@router.post("/once")
async def trigger_run_once(_admin: None = Depends(require_admin)) -> dict[str, Any]:
    from src.kaven.kaven import RunAlreadyInProgress, run_once  # heavy import는 호출 시점에

    try:
        result = await run_once()
    except RunAlreadyInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="Run result is not a JSON object")
    return result


@router.get("/files")
def list_run_files() -> dict[str, list[str]]:
    log_dir = default_log_dir()
    files = sorted([p.name for p in log_dir.glob("kaven_*.jsonl")])
    if not files:  # 하위호환
        files = sorted([p.name for p in log_dir.glob("maven_*.jsonl")])
    return {"files": files}


@router.get("/dates")
def list_run_dates() -> dict[str, list[str]]:
    return {"dates": available_dates(default_log_dir())}


async def _stream_latest_run() -> AsyncIterator[str]:
    last_run_id = None
    while True:
        try:
            latest = latest_run()
            run_id = latest.get("run_id")
            if run_id != last_run_id:
                payload = json.dumps({"type": "run_update", "run": latest}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                last_run_id = run_id
            else:
                yield "data: {\"type\":\"heartbeat\"}\n\n"
        except Exception as e:
            err = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        await asyncio.sleep(5)


@router.get("/stream")
async def stream_runs() -> StreamingResponse:
    return StreamingResponse(_stream_latest_run(), media_type="text/event-stream")

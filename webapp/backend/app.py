from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from src.kaven.kaven import LOG_DIR, run_once

app = FastAPI(title="Kaven Web API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kaven-web-api"}


@app.get("/runs/latest")
def latest_run() -> dict[str, Any]:
    today_file = LOG_DIR / f"maven_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
    if not today_file.exists():
        raise HTTPException(status_code=404, detail="No run log found for today")

    last_line = None
    with today_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last_line = line

    if not last_line:
        raise HTTPException(status_code=404, detail="Log file is empty")

    return json.loads(last_line)


def _iter_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for log_file in sorted(Path(LOG_DIR).glob("maven_*.jsonl")):
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


@app.get("/runs")
def list_runs(
    limit: int = 20,
    severity_min: int | None = None,
    category: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    runs = _iter_runs()
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

        if keep_events:
            copied = dict(run)
            copied["events"] = keep_events
            filtered.append(copied)

        if len(filtered) >= limit:
            break

    return {"runs": filtered, "count": len(filtered)}


@app.post("/runs/once")
async def trigger_run_once() -> dict[str, Any]:
    return await run_once()


@app.get("/runs/files")
def list_run_files() -> dict[str, list[str]]:
    files = sorted([p.name for p in Path(LOG_DIR).glob("maven_*.jsonl")])
    return {"files": files}


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


@app.get("/runs/stream")
async def stream_runs() -> StreamingResponse:
    return StreamingResponse(_stream_latest_run(), media_type="text/event-stream")

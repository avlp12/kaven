from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.kaven.kaven import LOG_DIR, run_once
from src.kaven.report_generator import generate_daily_report
from src.kaven.version import __version__

app = FastAPI(title="Kaven Web API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kaven-web-api", "version": __version__}


@app.get("/runs/latest")
def latest_run() -> dict[str, Any]:
    today = datetime.now(timezone.utc).strftime('%Y%m%d')
    candidates = [
        LOG_DIR / f"kaven_{today}.jsonl",
        LOG_DIR / f"maven_{today}.jsonl",  # 하위호환
    ]
    today_file = next((p for p in candidates if p.exists()), None)
    if today_file is None:
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
    log_files = list(Path(LOG_DIR).glob("kaven_*.jsonl")) + list(Path(LOG_DIR).glob("maven_*.jsonl"))
    for log_file in sorted(log_files):
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

        # 필터가 없으면 이벤트가 0건인 run도 목록에 보여준다.
        no_filter = severity_min is None and not category and not q
        if keep_events or no_filter:
            copied = dict(run)
            copied["events"] = keep_events if keep_events else events
            filtered.append(copied)

        if len(filtered) >= limit:
            break

    return {"runs": filtered, "count": len(filtered)}


@app.post("/runs/once")
async def trigger_run_once() -> dict[str, Any]:
    return await run_once()


@app.get("/runs/files")
def list_run_files() -> dict[str, list[str]]:
    files = sorted([p.name for p in Path(LOG_DIR).glob("kaven_*.jsonl")])
    if not files:  # 하위호환
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


# ── Daily Report ────────────────────────────────────────────────


@app.get("/report")
def daily_report_today() -> dict[str, Any]:
    """오늘의 일일 리포트 반환."""
    return generate_daily_report(LOG_DIR)


@app.get("/report/{date}")
def daily_report_by_date(date: str) -> dict[str, Any]:
    """특정 날짜(YYYYMMDD)의 일일 리포트 반환."""
    if len(date) != 8 or not date.isdigit():
        raise HTTPException(status_code=400, detail="Date must be YYYYMMDD format")
    report = generate_daily_report(LOG_DIR, date)
    if report["total_events"] == 0:
        raise HTTPException(status_code=404, detail=f"No events found for {date}")
    return report


@app.get("/report/dates")
def list_report_dates() -> dict[str, list[str]]:
    """리포트 가능한 날짜 목록 반환."""
    dates = set()
    for p in Path(LOG_DIR).glob("kaven_*.jsonl"):
        dates.add(p.stem.replace("kaven_", ""))
    for p in Path(LOG_DIR).glob("maven_*.jsonl"):
        dates.add(p.stem.replace("maven_", ""))
    return {"dates": sorted(dates, reverse=True)}


# ── Region Guide ────────────────────────────────────────────────


_REGION_COORDS = {
    "hormuz": {"lat": 26.5, "lng": 56.3, "name": "호르무즈 해협",
               "description": "세계 원유 해상 운송의 약 20%가 통과하는 전략적 요충지. 한국 원유 수입의 70%가 이 해역을 경유."},
    "taiwan": {"lat": 23.7, "lng": 121.0, "name": "대만 해협",
               "description": "글로벌 반도체 공급망의 핵심 지역. 대만 TSMC는 세계 파운드리의 60% 점유."},
    "korea": {"lat": 37.5, "lng": 127.0, "name": "한반도",
              "description": "KOSPI, 원/달러 환율에 직접적 영향을 미치는 최고 우선순위 감시 지역."},
    "ukraine": {"lat": 48.4, "lng": 31.2, "name": "우크라이나",
                "description": "유럽 에너지·곡물 공급에 영향. 러시아-우크라이나 분쟁 장기화."},
    "india_pak": {"lat": 30.0, "lng": 70.0, "name": "인도·파키스탄",
                  "description": "남아시아 핵 보유국 간 긴장. 에너지·무역 경로 교란 가능성."},
    "southcn": {"lat": 14.0, "lng": 114.0, "name": "남중국해",
                "description": "세계 해상 무역의 30%가 통과. 미중 해양 패권 경쟁의 핵심 지역."},
    "redsa": {"lat": 14.0, "lng": 42.0, "name": "홍해·예멘",
              "description": "수에즈 운하 접근 해역. 후티 반군의 선박 공격으로 국제 물류 차질."},
    "sahel": {"lat": 15.0, "lng": 0.0, "name": "사헬",
              "description": "서아프리카 지정학 불안정 지역. 에너지·광물 공급망 영향."},
    "global": {"lat": 0, "lng": 0, "name": "전지구",
               "description": "특정 지역에 국한되지 않는 글로벌 이벤트."},
}


def _region_history(log_dir: Path, region: str, days: int = 7) -> list[dict]:
    """최근 N일간 특정 지역의 severity 히스토리."""
    from datetime import timedelta
    history = []
    today = datetime.now(timezone.utc)
    for d in range(days):
        dt = today - timedelta(days=d)
        date_str = dt.strftime("%Y%m%d")
        display = dt.strftime("%Y-%m-%d")
        events = []
        for prefix in ("kaven_", "maven_"):
            path = log_dir / f"{prefix}{date_str}.jsonl"
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        run = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    for ev in run.get("events", []):
                        if ev.get("region") == region:
                            events.append(ev)
        max_sev = max((e.get("severity", 0) for e in events), default=0)
        history.append({
            "date": display,
            "max_severity": max_sev,
            "event_count": len(events),
        })
    history.reverse()
    return history


@app.get("/guide")
def guide_overview() -> dict[str, Any]:
    """모든 감시 지역의 현재 상태 요약."""
    report = generate_daily_report(LOG_DIR)
    regions = []
    for code, info in _REGION_COORDS.items():
        region_data = report.get("by_region", {}).get(code, {})
        regions.append({
            "code": code,
            "name": info["name"],
            "lat": info["lat"],
            "lng": info["lng"],
            "description": info["description"],
            "current_severity": region_data.get("max_severity", 0),
            "event_count": region_data.get("event_count", 0),
        })
    regions.sort(key=lambda x: -x["current_severity"])
    return {
        "date": report["date"],
        "max_severity": report["max_severity"],
        "regions": regions,
    }


@app.get("/guide/{region}")
def guide_region(region: str, days: int = 7) -> dict[str, Any]:
    """특정 지역의 상세 현황 + 히스토리."""
    if region not in _REGION_COORDS:
        raise HTTPException(status_code=404, detail=f"Unknown region: {region}")
    info = _REGION_COORDS[region]
    history = _region_history(LOG_DIR, region, days)

    # 오늘의 이벤트
    report = generate_daily_report(LOG_DIR)
    region_data = report.get("by_region", {}).get(region, {})
    events = region_data.get("events", [])

    return {
        "code": region,
        "name": info["name"],
        "lat": info["lat"],
        "lng": info["lng"],
        "description": info["description"],
        "current_severity": region_data.get("max_severity", 0),
        "today_events": events,
        "history": history,
    }


# ── Map Data ────────────────────────────────────────────────────


@app.get("/map/data")
def map_data() -> dict[str, Any]:
    """지도 시각화용 데이터 — 지역별 최신 이벤트 + 좌표."""
    report = generate_daily_report(LOG_DIR)
    points = []
    for code, info in _REGION_COORDS.items():
        region_data = report.get("by_region", {}).get(code, {})
        if not region_data.get("events"):
            continue
        top_event = max(region_data["events"], key=lambda e: e.get("severity", 0))
        points.append({
            "region": code,
            "lat": info["lat"],
            "lng": info["lng"],
            "name": info["name"],
            "severity": top_event.get("severity", 0),
            "event": top_event.get("event", ""),
        })
    return {"date": report["date"], "points": points}


# ── Portfolio (Investment Impact) ───────────────────────────────

_ASSET_META = {
    "WTI": {"type": "commodity", "description": "서부 텍사스 원유 (에너지 벤치마크)"},
    "KOSPI": {"type": "index", "description": "한국 종합주가지수"},
    "원/달러": {"type": "currency", "description": "USD/KRW 환율"},
    "삼성전자": {"type": "equity", "description": "반도체·전자 (KRX 005930)"},
    "SK하이닉스": {"type": "equity", "description": "메모리 반도체 (KRX 000660)"},
    "TSMC": {"type": "equity", "description": "글로벌 파운드리 1위 (TWSE 2330)"},
    "현대차": {"type": "equity", "description": "자동차 (KRX 005380)"},
    "LG에너지솔루션": {"type": "equity", "description": "배터리 (KRX 373220)"},
}


def _portfolio_history(log_dir: Path, days: int = 7) -> dict[str, Any]:
    """자산별 이벤트 히스토리 집계."""
    from datetime import timedelta
    from collections import defaultdict

    today = datetime.now(timezone.utc)
    asset_daily: dict[str, list[dict]] = defaultdict(list)  # asset -> [{date, severity, count, events}]
    all_assets: dict[str, dict] = defaultdict(lambda: {"total_events": 0, "max_severity": 0, "signals": defaultdict(int)})

    for d in range(days):
        dt = today - timedelta(days=d)
        date_str = dt.strftime("%Y%m%d")
        display = dt.strftime("%Y-%m-%d")

        day_events: dict[str, list] = defaultdict(list)
        for prefix in ("kaven_", "maven_"):
            path = log_dir / f"{prefix}{date_str}.jsonl"
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        run = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    for ev in run.get("events", []):
                        for asset in ev.get("affected_assets", []):
                            day_events[asset].append(ev)

        # 모든 자산에 대해 날짜별 엔트리 기록
        seen_assets = set()
        for asset, evts in day_events.items():
            seen_assets.add(asset)
            max_sev = max(e.get("severity", 0) for e in evts)
            asset_daily[asset].append({
                "date": display,
                "max_severity": max_sev,
                "event_count": len(evts),
            })
            all_assets[asset]["total_events"] += len(evts)
            all_assets[asset]["max_severity"] = max(all_assets[asset]["max_severity"], max_sev)
            for ev in evts:
                sig = ev.get("signal", "watch")
                all_assets[asset]["signals"][sig] += 1

        # 해당 날에 언급 안 된 자산은 0으로 채움
        for asset in asset_daily:
            if asset not in seen_assets:
                asset_daily[asset].append({"date": display, "max_severity": 0, "event_count": 0})

    # 날짜순 정렬
    for asset in asset_daily:
        asset_daily[asset].sort(key=lambda x: x["date"])

    # 결과 조합
    assets = []
    for asset, info in all_assets.items():
        meta = _ASSET_META.get(asset, {"type": "other", "description": asset})
        dominant_signal = max(info["signals"].items(), key=lambda x: x[1])[0] if info["signals"] else "watch"
        assets.append({
            "name": asset,
            "type": meta["type"],
            "description": meta["description"],
            "total_events": info["total_events"],
            "max_severity": info["max_severity"],
            "dominant_signal": dominant_signal,
            "signals": dict(info["signals"]),
            "history": asset_daily.get(asset, []),
        })

    assets.sort(key=lambda x: (-x["max_severity"], -x["total_events"]))
    return assets


@app.get("/portfolio")
def portfolio_overview(days: int = 7) -> dict[str, Any]:
    """투자 영향 대시보드 — 자산별 이벤트 히트맵."""
    assets = _portfolio_history(LOG_DIR, days)
    return {
        "days": days,
        "asset_count": len(assets),
        "assets": assets,
    }


@app.get("/portfolio/{asset_name}")
def portfolio_asset_detail(asset_name: str, days: int = 14) -> dict[str, Any]:
    """특정 자산의 상세 이벤트 히스토리."""
    all_assets = _portfolio_history(LOG_DIR, days)
    match = next((a for a in all_assets if a["name"] == asset_name), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_name}")
    return match

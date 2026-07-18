"""
Kaven Web API — FastAPI 앱 조립.

엔드포인트 구현은 ``webapp/backend/routers/``, 도메인 로직은 ``src/kaven/``
(log_store / ops_summary / aggregates / agent_service)에 있다.
이 모듈은 앱 생성과 미들웨어/라우터 연결만 담당한다.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.kaven.version import __version__
from webapp.backend.routers import agent, intel, ops, portfolio, runs, system


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kaven Web API",
        version=__version__,
        description=(
            "지정학 조기경보 시스템 Kaven의 REST API. "
            "AI 에이전트 연동은 GET /agent/manifest 참조 (MCP: python -m src.kaven.mcp_server)."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (system.router, runs.router, ops.router, agent.router, intel.router, portfolio.router):
        app.include_router(r)
    return app


app = create_app()

"""구독(OAuth)/CLI 브리지 모델 연결 테스트 — anthropic_auth · cli_providers · /health."""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_a, **_k: None))

from src.kaven import anthropic_auth
from src.kaven.anthropic_auth import OAUTH_BETA_HEADER, auth_mode, resolve_auth
from src.kaven.cli_providers import available_providers, provider_status, run_cli

_TEMP_DIRS: list[TemporaryDirectory] = []  # prevent GC during test run


def _tmp() -> Path:
    tmpdir = TemporaryDirectory()
    _TEMP_DIRS.append(tmpdir)
    return Path(tmpdir.name)


def _clear_anthropic_env(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(anthropic_auth, "_ant_cache", {"token": None, "at": 0.0})


# ── anthropic_auth ──────────────────────────────────────────────


def test_api_key_takes_precedence_over_oauth(monkeypatch):
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "oauth-token")
    mode, headers = resolve_auth()
    assert mode == "api_key"
    assert headers == {"x-api-key": "sk-test"}
    assert auth_mode() == "api_key"


def test_auth_token_yields_oauth_headers(monkeypatch):
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "oauth-token")
    mode, headers = resolve_auth()
    assert mode == "oauth"
    assert headers["authorization"] == "Bearer oauth-token"
    assert headers["anthropic-beta"] == OAUTH_BETA_HEADER
    assert auth_mode() == "oauth"


def test_no_credentials_resolves_none(monkeypatch):
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setattr(anthropic_auth.shutil, "which", lambda _cmd: None)
    assert resolve_auth() is None
    assert auth_mode() == "none"


def test_ant_cli_fallback_and_cache(monkeypatch):
    """ant CLI 프로필 → oauth 모드, TTL 내 재호출은 캐시 사용."""
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setattr(anthropic_auth.shutil, "which", lambda _cmd: "/usr/bin/ant")
    calls = {"n": 0}

    def fake_run(argv, **_kwargs):
        calls["n"] += 1
        assert argv == ["ant", "auth", "print-credentials", "--access-token"]
        return types.SimpleNamespace(returncode=0, stdout="ant-token\n", stderr="")

    monkeypatch.setattr(anthropic_auth.subprocess, "run", fake_run)
    mode, headers = resolve_auth()
    assert mode == "oauth"
    assert headers["authorization"] == "Bearer ant-token"
    resolve_auth()  # TTL 내 두 번째 호출
    assert calls["n"] == 1


# ── cli_providers ───────────────────────────────────────────────


def _write_cli_config(monkeypatch, providers) -> None:
    cfg = _tmp() / "config.json"
    cfg.write_text(json.dumps({"cli_providers": providers}), encoding="utf-8")
    monkeypatch.setenv("KAVEN_CONFIG", str(cfg))


def test_provider_status_reports_installed(monkeypatch):
    _write_cli_config(monkeypatch, [
        {"id": "py", "name": "Python", "enabled": True, "command": "python3 -c"},
        {"id": "ghost", "name": "Ghost", "enabled": False, "command": "no-such-cli-xyz -p"},
    ])
    status = {p["id"]: p for p in provider_status()}
    assert status["py"]["installed"] is True
    assert status["ghost"]["installed"] is False
    assert status["ghost"]["enabled"] is False


def test_available_providers_selector(monkeypatch):
    _write_cli_config(monkeypatch, [
        {"id": "py", "name": "Python", "enabled": True, "command": "python3 -c"},
        {"id": "sh", "name": "Shell", "enabled": True, "command": "sh -c"},
        {"id": "off1", "name": "Disabled", "enabled": False, "command": "sh -c"},
        {"id": "ghost", "name": "Missing", "enabled": True, "command": "no-such-cli-xyz"},
    ])
    monkeypatch.delenv("KAVEN_CLI_PROVIDER", raising=False)
    assert [p["id"] for p in available_providers()] == ["py", "sh"]  # 비활성/미설치 제외

    monkeypatch.setenv("KAVEN_CLI_PROVIDER", "sh")
    assert [p["id"] for p in available_providers()] == ["sh"]

    monkeypatch.setenv("KAVEN_CLI_PROVIDER", "off")
    assert available_providers() == []


def test_run_cli_appends_prompt_and_captures_stdout():
    provider = {"id": "echo", "command": "echo"}
    out = asyncio.run(run_cli(provider, "hello world"))
    assert out == "hello world"


def test_run_cli_failures_return_none():
    assert asyncio.run(run_cli({"id": "ghost", "command": "no-such-cli-xyz"}, "x")) is None
    assert asyncio.run(run_cli({"id": "false", "command": "false"}, "x")) is None
    assert asyncio.run(run_cli({"id": "empty", "command": ""}, "x")) is None


# ── /health + PUT /config/cli_providers ─────────────────────────


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from webapp.backend.routers.system import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_health_reports_analysis_status(monkeypatch):
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "oauth-token")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    _write_cli_config(monkeypatch, [
        {"id": "py", "name": "Python", "enabled": True, "command": "python3 -c"},
    ])
    body = _client().get("/health").json()
    analysis = body["analysis"]
    assert analysis["anthropic"] == "oauth"
    assert analysis["anthropic_base_url"] is False
    assert analysis["openai_compatible"] is False
    assert analysis["gemini"] is True
    assert analysis["cli_providers"][0]["id"] == "py"
    assert analysis["cli_providers"][0]["installed"] is True


def test_put_cli_providers_validates_and_persists(monkeypatch):
    cfg = _tmp() / "config.json"
    monkeypatch.setenv("KAVEN_CONFIG", str(cfg))
    monkeypatch.setenv("KAVEN_ALLOWED_CLI_COMMANDS", "mycli")
    client = _client()

    res = client.put("/config/cli_providers", json={"items": [
        {"name": "My Bridge", "command": "mycli -p --flag"},
    ]})
    assert res.status_code == 200
    saved = json.loads(cfg.read_text(encoding="utf-8"))["cli_providers"]
    assert saved[0]["id"] == "mycli"
    assert saved[0]["command"] == "mycli -p --flag"

    bad = client.put("/config/cli_providers", json={"items": [
        {"name": "Broken", "command": "unbalanced 'quote"},
    ]})
    assert bad.status_code == 400

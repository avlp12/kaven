"""구독(OAuth)/CLI 브리지 모델 연결 테스트 — anthropic_auth · cli_providers · /health."""

from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
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


def _python_command(code: str | None = None) -> str:
    argv = [sys.executable]
    if code is not None:
        argv.extend(["-c", code])
    return subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)


def test_provider_status_reports_installed(monkeypatch):
    _write_cli_config(monkeypatch, [
        {"id": "py", "name": "Python", "enabled": True, "command": _python_command()},
        {"id": "ghost", "name": "Ghost", "enabled": False, "command": "no-such-cli-xyz -p"},
    ])
    status = {p["id"]: p for p in provider_status()}
    assert status["py"]["installed"] is True
    assert status["ghost"]["installed"] is False
    assert status["ghost"]["enabled"] is False


def test_available_providers_selector(monkeypatch):
    _write_cli_config(monkeypatch, [
        {"id": "py", "name": "Python", "enabled": True, "command": _python_command()},
        {"id": "sh", "name": "Shell", "enabled": True, "command": _python_command()},
        {"id": "off1", "name": "Disabled", "enabled": False, "command": _python_command()},
        {"id": "ghost", "name": "Missing", "enabled": True, "command": "no-such-cli-xyz"},
    ])
    monkeypatch.delenv("KAVEN_CLI_PROVIDER", raising=False)
    assert [p["id"] for p in available_providers()] == ["py", "sh"]  # 비활성/미설치 제외

    monkeypatch.setenv("KAVEN_CLI_PROVIDER", "sh")
    assert [p["id"] for p in available_providers()] == ["sh"]

    monkeypatch.setenv("KAVEN_CLI_PROVIDER", "off")
    assert available_providers() == []


def test_run_cli_appends_prompt_and_captures_stdout():
    provider = {"id": "echo", "command": _python_command("import sys; print(sys.argv[-1])")}
    out = asyncio.run(run_cli(provider, "hello world"))
    assert out == "hello world"


def test_run_cli_failures_return_none():
    assert asyncio.run(run_cli({"id": "ghost", "command": "no-such-cli-xyz"}, "x")) is None
    assert asyncio.run(run_cli(
        {"id": "false", "command": _python_command("raise SystemExit(1)")}, "x"
    )) is None
    assert asyncio.run(run_cli({"id": "empty", "command": ""}, "x")) is None


def test_login_command_resolution():
    from src.kaven.cli_providers import login_command_for

    assert login_command_for({"id": "codex", "command": "codex exec"}) == "codex login"
    assert login_command_for({"id": "claude", "command": "claude -p"}) == "claude"
    assert login_command_for(
        {"id": "custom", "command": "mycli -p", "login_command": "mycli auth login"}
    ) == "mycli auth login"
    assert login_command_for({"id": "unknown", "command": "somecli -p"}) == "somecli"


def test_windows_executable_resolution(monkeypatch):
    """Windows: 확장자 없는 npm 유닉스 심 대신 .cmd 래퍼를 우선 해석.

    확장자 없는 심이 잡히면 cmd에서 '액세스가 거부되었습니다'로 실패한다.
    """
    import sys as _sys

    from src.kaven import cli_providers as cp

    monkeypatch.setattr(_sys, "platform", "win32")
    table = {
        "codex.cmd": "C:\\npm\\codex.cmd",
        "codex": "C:\\npm\\codex",          # 확장자 없는 심 — 선택되면 안 됨
        "tool": "C:\\bin\\tool.ps1",        # .ps1만 있는 경우 → powershell 위임
        "spacy.exe": "C:\\Program Files\\Spacy\\spacy.exe",  # 공백 경로
    }
    monkeypatch.setattr(cp.shutil, "which", lambda n: table.get(n))
    monkeypatch.setattr(cp, "_windows_path_is_usable", lambda path: True)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert cp._resolve_executable("codex") == "C:\\npm\\codex.cmd"
    assert cp._exec_argv(["codex", "login"]) == ["cmd", "/c", "C:\\npm\\codex.cmd", "login"]
    assert cp._exec_argv(["tool"])[:4] == ["powershell", "-ExecutionPolicy", "Bypass", "-File"]
    # posix=False 분해 — 백슬래시 경로/따옴표 보존 처리
    assert cp._split_command('"C:\\Program Files\\x\\cli.cmd" login') == \
        ["C:\\Program Files\\x\\cli.cmd", "login"]

    # 배치 라인 — .cmd는 call, 공백 경로는 따옴표 (cmd는 \" 이스케이프 미지원)
    assert cp._windows_batch_line(["codex", "login"]) == "call C:\\npm\\codex.cmd login"
    assert cp._windows_batch_line(["spacy", "login"]) == \
        '"C:\\Program Files\\Spacy\\spacy.exe" login'

    # MS Store 앱 실행 별칭(%LOCALAPPDATA%\Microsoft\WindowsApps) 우선
    alias_root = _tmp()
    alias_dir = alias_root / "Microsoft" / "WindowsApps"
    alias_dir.mkdir(parents=True)
    (alias_dir / "codex.exe").write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(alias_root))
    assert cp._resolve_executable("codex") == str(alias_dir / "codex.exe")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    # 터미널 스폰 — 임시 배치 파일 생성 + 따옴표 불필요한 파일명으로 실행
    import tempfile as _tf
    tmpdir = str(_tmp())
    monkeypatch.setattr(_tf, "gettempdir", lambda: tmpdir)
    calls = {}
    monkeypatch.setattr(cp.subprocess, "Popen",
                        lambda argv, **kw: calls.update(argv=argv, **kw))
    assert cp._spawn_in_terminal("spacy login") is True
    bat = Path(tmpdir) / "kaven_cli_login.cmd"
    assert '"C:\\Program Files\\Spacy\\spacy.exe" login' in bat.read_text(encoding="utf-8")
    assert calls["argv"][:6] == ["cmd", "/c", "start", "Kaven CLI Login", "cmd", "/k"]
    assert calls["argv"][6] == "kaven_cli_login.cmd"
    assert calls["cwd"] == tmpdir


def test_windows_executable_resolution_skips_inaccessible_candidate(monkeypatch):
    """A PATH hit is not installed when Windows denies execute access."""
    import sys as _sys

    from src.kaven import cli_providers as cp

    blocked = (
        "C:\\Program Files\\WindowsApps\\OpenAI.Codex_1.0.0.0_x64__test"
        "\\app\\resources\\codex.exe"
    )
    table = {
        "codex.exe": blocked,
        "codex.cmd": "C:\\npm\\codex.cmd",
    }
    monkeypatch.setattr(_sys, "platform", "win32")
    monkeypatch.setattr(cp.shutil, "which", lambda name: table.get(name))
    monkeypatch.setattr(cp, "_windows_path_is_usable", lambda path: path != blocked)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert cp._resolve_executable("codex") == "C:\\npm\\codex.cmd"

    table["codex.cmd"] = None
    assert cp._resolve_executable("codex") is None
    monkeypatch.setattr(
        cp,
        "_configured_providers",
        lambda: [{"id": "codex", "name": "Codex", "command": "codex exec"}],
    )
    assert cp.provider_status() == [
        {"id": "codex", "name": "Codex", "enabled": True, "installed": False}
    ]


def test_launch_login_headless_extracts_url(monkeypatch):
    """터미널 없는 환경 — 백그라운드 실행 + 초기 출력에서 로그인 URL 추출."""
    from src.kaven import cli_providers as cp

    command = _python_command(
        "print('Open https://example.com/device?code=ABC to sign in')"
    )
    monkeypatch.setattr(cp, "_spawn_in_terminal", lambda _cmd: False)

    result = cp.launch_login({"id": "fake", "command": command,
                              "login_command": command})
    assert result["mode"] == "headless"
    assert result["urls"] == ["https://example.com/device?code=ABC"]


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
        {"id": "py", "name": "Python", "enabled": True, "command": _python_command()},
    ])
    body = _client().get("/health").json()
    analysis = body["analysis"]
    assert analysis["anthropic"] == "oauth"
    assert analysis["anthropic_base_url"] is False
    assert analysis["openai_compatible"] is False
    assert analysis["gemini"] is True
    assert analysis["cli_providers"][0]["id"] == "py"
    assert analysis["cli_providers"][0]["installed"] is True


def test_credentials_roundtrip_and_env_precedence(monkeypatch):
    """Settings UI 자격증명: 저장/삭제, env 우선, resolve_auth 연동."""
    from src.kaven.config_loader import get_credentials, update_credentials

    cfg = _tmp() / "config.json"
    cfg.write_text(json.dumps({"news_keywords": [{"id": "x", "query": "q"}]}), encoding="utf-8")
    monkeypatch.setenv("KAVEN_CONFIG", str(cfg))
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setattr(anthropic_auth.shutil, "which", lambda _cmd: None)

    update_credentials({"anthropic_auth_token": "stored-token", "bogus_key": "x"})
    assert get_credentials() == {"anthropic_auth_token": "stored-token"}  # 미허용 키 무시
    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved["news_keywords"]  # 다른 섹션 보존

    mode, headers = resolve_auth()  # 저장된 토큰으로 OAuth
    assert mode == "oauth" and headers["authorization"] == "Bearer stored-token"

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "env-token")  # env가 우선
    assert resolve_auth()[1]["authorization"] == "Bearer env-token"

    update_credentials({"anthropic_auth_token": ""})  # 빈 값 = 연결 해제
    assert get_credentials() == {}
    assert "credentials" not in json.loads(cfg.read_text(encoding="utf-8"))


def test_put_credentials_endpoint(monkeypatch):
    cfg = _tmp() / "config.json"
    monkeypatch.setenv("KAVEN_CONFIG", str(cfg))
    _clear_anthropic_env(monkeypatch)
    monkeypatch.setattr(anthropic_auth.shutil, "which", lambda _cmd: None)
    for var in ("OPENAI_BASE_URL", "GEMINI_API_KEY", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    client = _client()

    res = client.put("/config/credentials", json={
        "gemini_api_key": "g-secret", "openai_base_url": "https://api.x.ai/v1"})
    assert res.status_code == 200
    assert res.json() == {"saved": ["gemini_api_key", "openai_base_url"], "cleared": []}
    assert "g-secret" not in res.text  # 응답에 비밀값 미포함

    analysis = client.get("/health").json()["analysis"]
    assert analysis["gemini"] is True and analysis["openai_compatible"] is True
    assert analysis["stored"]["gemini_api_key"] is True
    assert analysis["stored"]["anthropic_api_key"] is False

    # GET /config 응답으로 자격증명이 새어나가지 않아야 함
    assert "credentials" not in client.get("/config").json()
    assert "g-secret" not in client.get("/config").text

    assert client.put("/config/credentials", json={"nope": "x"}).status_code == 400
    assert client.put("/config/credentials",
                      json={"openai_base_url": "ftp://x"}).status_code == 400

    res = client.put("/config/credentials", json={"gemini_api_key": ""})  # 해제
    assert res.json()["cleared"] == ["gemini_api_key"]
    assert client.get("/health").json()["analysis"]["gemini"] is False


def test_cli_login_endpoint(monkeypatch):
    from src.kaven import cli_providers as cp

    command = _python_command("print('Visit https://login.example.com/start')")
    _write_cli_config(monkeypatch, [
        {"id": "fake", "name": "Fake", "enabled": True,
         "command": command, "login_command": command},
        {"id": "ghost", "name": "Ghost", "enabled": True, "command": "no-such-cli-xyz"},
    ])
    monkeypatch.setattr(cp, "_spawn_in_terminal", lambda _cmd: False)
    client = _client()

    res = client.post("/cli/fake/login")
    assert res.status_code == 200
    body = res.json()
    assert body["provider"] == "fake" and body["mode"] == "headless"
    assert body["urls"] == ["https://login.example.com/start"]

    assert client.post("/cli/nope/login").status_code == 404
    assert client.post("/cli/ghost/login").status_code == 400  # 미설치


def test_put_cli_providers_validates_and_persists(monkeypatch):
    cfg = _tmp() / "config.json"
    monkeypatch.setenv("KAVEN_CONFIG", str(cfg))
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

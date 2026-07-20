"""
CLI 에이전트 브리지 — 구독(OAuth) 기반 모델을 공식 CLI를 통해 사용.

API 키 없이 구독으로 모델을 쓰는 제공자들은 대부분 자체 CLI로 로그인한다:
- Claude Pro/Max  → `claude` (Claude Code CLI) / `ant`
- ChatGPT Plus/Pro → `codex` (OpenAI Codex CLI)
- Cursor 구독      → `cursor-agent`
- Google 계정      → `gemini` (Gemini CLI)

Kaven은 설치·로그인된 CLI를 감지해 분석 프롬프트를 위임한다.
목록은 config.json `cli_providers` 섹션으로 커스터마이즈 가능
(예: 다른 CLI를 쓰는 Grok/사내 게이트웨이 등 추가).

명령은 문자열로 저장하며(shlex 분리) 프롬프트는 마지막 인자로 전달된다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from typing import Any

logger = logging.getLogger("kaven.cli_providers")

CLI_TIMEOUT_SECONDS = 180
_MAX_OUTPUT_CHARS = 200_000

# 제공자별 OAuth 로그인 명령 기본값 — config 항목의 `login_command`로 override 가능.
# claude/gemini는 별도 login 서브커맨드 없이 첫 실행 시 로그인 플로우가 시작된다.
DEFAULT_LOGIN_COMMANDS: dict[str, str] = {
    "claude": "claude",
    "codex": "codex login",
    "cursor": "cursor-agent login",
    "gemini": "gemini",
}


def _configured_providers() -> list[dict[str, Any]]:
    from src.kaven.config_loader import load_config  # 지연 import (순환 방지)

    return load_config().get("cli_providers", [])


def provider_status() -> list[dict[str, Any]]:
    """설정된 CLI 제공자 각각의 설치 여부 (비밀값 없음, 상태 표시용)."""
    out = []
    for p in _configured_providers():
        cmd = shlex.split(str(p.get("command", "")))
        out.append({
            "id": p.get("id", ""),
            "name": p.get("name", p.get("id", "")),
            "enabled": p.get("enabled", True),
            "installed": bool(cmd) and shutil.which(cmd[0]) is not None,
        })
    return out


def available_providers() -> list[dict[str, Any]]:
    """활성화 + 설치된 제공자 목록 (설정 순서 유지).

    `KAVEN_CLI_PROVIDER` 환경변수:
        - 미설정/"auto": 전부 후보
        - "off": CLI 브리지 비활성
        - 특정 id: 해당 제공자만
    """
    selector = os.getenv("KAVEN_CLI_PROVIDER", "").strip().lower()
    if selector == "off":
        return []
    providers = []
    for p in _configured_providers():
        if not p.get("enabled", True):
            continue
        if selector and selector != "auto" and p.get("id") != selector:
            continue
        cmd = shlex.split(str(p.get("command", "")))
        if not cmd or shutil.which(cmd[0]) is None:
            continue
        providers.append(p)
    return providers


def login_command_for(provider: dict[str, Any]) -> str:
    """제공자의 OAuth 로그인 명령 — login_command 필드 → 알려진 기본값 → 실행 바이너리."""
    explicit = str(provider.get("login_command", "")).strip()
    if explicit:
        return explicit
    by_id = DEFAULT_LOGIN_COMMANDS.get(str(provider.get("id", "")))
    if by_id:
        return by_id
    argv = shlex.split(str(provider.get("command", "")))
    return argv[0] if argv else ""


def _spawn_in_terminal(cmd_str: str) -> bool:
    """가능하면 새 터미널 창에서 로그인 명령 실행 (대화형 플로우 지원).

    성공 시 True. 터미널을 못 찾으면 False (헤드리스 폴백 사용).
    """
    try:
        if sys.platform == "win32":
            # start의 첫 따옴표 인자는 창 제목 — /k로 로그인 후에도 창 유지
            subprocess.Popen(["cmd", "/c", "start", "Kaven CLI Login", "cmd", "/k", cmd_str])
            return True
        if sys.platform == "darwin":
            import json as _json
            subprocess.Popen(["osascript",
                              "-e", 'tell application "Terminal" to activate',
                              "-e", f'tell application "Terminal" to do script {_json.dumps(cmd_str)}'])
            return True
        shell_cmd = f"{cmd_str}; exec ${{SHELL:-bash}}"
        if shutil.which("gnome-terminal"):
            subprocess.Popen(["gnome-terminal", "--", "sh", "-c", shell_cmd])
            return True
        for term in ("x-terminal-emulator", "konsole", "xfce4-terminal", "xterm"):
            if shutil.which(term):
                subprocess.Popen([term, "-e", f"sh -c '{shell_cmd}'"])
                return True
    except Exception as e:
        logger.warning(f"터미널 실행 실패: {e}")
    return False


def launch_login(provider: dict[str, Any]) -> dict[str, Any]:
    """제공자 CLI의 OAuth 로그인 플로우 실행.

    1) 데스크톱 환경이면 새 터미널 창에서 실행 (브라우저/디바이스 코드 등
       대화형 플로우를 사용자가 직접 완료)
    2) 헤드리스면 백그라운드로 실행 후 초기 출력에서 로그인 URL을 추출해 반환

    Returns: {"mode": "terminal"|"headless", "urls": [...], "output": "..."}
    """
    cmd_str = login_command_for(provider)
    argv = shlex.split(cmd_str)
    if not argv:
        raise ValueError("login command is empty")
    if shutil.which(argv[0]) is None:
        raise FileNotFoundError(f"{argv[0]} is not installed on the server")

    if _spawn_in_terminal(cmd_str):
        return {"mode": "terminal", "urls": [], "output": ""}

    # 헤드리스 폴백 — 로그인 프로세스는 계속 실행되도록 두고 초기 출력만 수집
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, text=True, errors="replace",
    )
    lines: list[str] = []

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.append(line)
                if len(lines) >= 80:
                    break
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout=8)
    output = "".join(lines)[-2000:]
    urls = re.findall(r"https?://[^\s\"'<>]+", output)
    return {"mode": "headless", "urls": urls[:5], "output": output}


async def run_cli(provider: dict[str, Any], prompt: str,
                  timeout: float = CLI_TIMEOUT_SECONDS) -> str | None:
    """제공자 CLI에 프롬프트를 전달하고 stdout 텍스트를 반환 (실패 시 None)."""
    argv = shlex.split(str(provider.get("command", "")))
    if not argv:
        return None
    argv = [*argv, prompt]
    pid = provider.get("id", argv[0])
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except FileNotFoundError:
        return None
    except asyncio.TimeoutError:
        logger.warning(f"CLI provider {pid}: {timeout}s 타임아웃")
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except Exception as e:
        logger.warning(f"CLI provider {pid} 실행 실패: {e}")
        return None

    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", "replace")[:200]
        logger.warning(f"CLI provider {pid} exit={proc.returncode}: {err}")
        return None
    text = (stdout or b"").decode("utf-8", "replace")[:_MAX_OUTPUT_CHARS].strip()
    return text or None

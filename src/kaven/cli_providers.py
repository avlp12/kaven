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
import shlex
import shutil
from typing import Any

logger = logging.getLogger("kaven.cli_providers")

CLI_TIMEOUT_SECONDS = 180
_MAX_OUTPUT_CHARS = 200_000


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

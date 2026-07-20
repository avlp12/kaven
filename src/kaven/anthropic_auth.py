"""
Anthropic 인증 해석 — API 키 또는 구독(OAuth) 자격증명.

Claude Pro/Max 등 구독 사용자는 API 키 없이 `ant auth login`으로 OAuth
로그인만 해두면 Kaven이 자동으로 해당 자격증명을 사용한다.

우선순위 (첫 번째로 발견되는 것 사용):
1. ``ANTHROPIC_API_KEY``   → ``x-api-key`` 헤더 (기존 방식)
2. ``ANTHROPIC_AUTH_TOKEN`` → ``Authorization: Bearer`` + OAuth beta 헤더
3. ``ant`` CLI OAuth 프로필 (``ant auth login`` 후 저장됨)
   → ``ant auth print-credentials --access-token``으로 단기 토큰 발급
     (만료 전 재발급은 ant가 처리; 여기서는 짧게 캐시만 한다)

OAuth 토큰은 ``x-api-key``가 아니라 ``Authorization: Bearer``로 전달해야 하며
``anthropic-beta: oauth-2025-04-20`` 헤더가 함께 필요하다.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time

logger = logging.getLogger("kaven.anthropic_auth")

OAUTH_BETA_HEADER = "oauth-2025-04-20"

# ant CLI 토큰 캐시 (초) — print-credentials 호출 비용 절약용.
# 토큰 자체 갱신은 ant가 알아서 하므로 TTL은 짧게 유지.
_ANT_TOKEN_TTL_SECONDS = 240
_ant_cache: dict[str, object] = {"token": None, "at": 0.0}


def _ant_cli_token() -> str | None:
    """`ant auth login` 프로필이 있으면 단기 액세스 토큰 발급 (실패 시 None)."""
    if not shutil.which("ant"):
        return None
    now = time.monotonic()
    cached = _ant_cache.get("token")
    cached_at = _ant_cache.get("at", 0.0)
    cached_at_value = float(cached_at) if isinstance(cached_at, (int, float, str)) else 0.0
    if cached and now - cached_at_value < _ANT_TOKEN_TTL_SECONDS:
        return str(cached)
    try:
        proc = subprocess.run(
            ["ant", "auth", "print-credentials", "--access-token"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as e:
        logger.debug(f"ant CLI 토큰 발급 실패: {e}")
        return None
    token = proc.stdout.strip() if proc.returncode == 0 else ""
    if not token:
        return None
    _ant_cache["token"] = token
    _ant_cache["at"] = now
    return token


def resolve_auth() -> tuple[str, dict[str, str]] | None:
    """
    Anthropic 요청용 인증 헤더 해석.

    Returns:
        (mode, headers) — mode는 "api_key" 또는 "oauth".
        사용 가능한 자격증명이 없으면 None.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        return "api_key", {"x-api-key": api_key}

    token = os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip() or _ant_cli_token()
    if token:
        return "oauth", {
            "authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA_HEADER,
        }
    return None


def auth_mode() -> str:
    """현재 인증 방식 — "api_key" | "oauth" | "none" (비밀값 미노출, 상태 표시용)."""
    resolved = resolve_auth()
    return resolved[0] if resolved else "none"

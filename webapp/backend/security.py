"""웹 API의 상태 변경 엔드포인트에 사용하는 공용 관리자 인증."""

from __future__ import annotations

import ipaddress
import os
import secrets

from fastapi import HTTPException, Request, status

DEFAULT_ALLOWED_ORIGINS = "http://127.0.0.1:8080,http://localhost:8080"


def allowed_origins() -> list[str]:
    """CORS와 loopback CSRF 검사가 공유하는 명시적 origin 목록."""
    return [
        origin.strip()
        for origin in os.getenv("KAVEN_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
        if origin.strip()
    ]


def _is_local_client(host: str) -> bool:
    """실제 루프백 주소와 Starlette TestClient의 전용 호스트만 허용한다."""
    if host == "testclient":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_admin(request: Request) -> None:
    """관리자 토큰을 확인하거나, 토큰 미설정 시 로컬 호출만 허용한다."""
    expected = os.getenv("KAVEN_ADMIN_TOKEN", "").strip()
    if not expected:
        client_host = request.client.host if request.client else ""
        if not _is_local_client(client_host):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin mutations are restricted to loopback clients",
            )
        request_host = request.url.hostname or ""
        if request_host not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin mutations require a loopback Host header",
            )
        origin = request.headers.get("origin", "").strip()
        if origin and origin not in allowed_origins():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Untrusted browser Origin",
            )
        return

    authorization = request.headers.get("authorization", "")
    supplied = request.headers.get("x-kaven-admin-token", "")
    if authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not supplied:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin token")

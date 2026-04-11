"""Convex 원격 전송 정책 회귀 테스트 (이슈 #7).

정책 요약:
- 기본 동작: 외부(Convex) 전송 비활성화 — 로컬 로그만 보존
- ``CONVEX_SITE_URL`` 설정 시에만 원격 POST 허용
- 경로는 ``CONVEX_EVENT_PATH`` (기본 ``/addKavenRun``)
- 하드코딩된 엔드포인트는 존재해서는 안 됨
"""

from __future__ import annotations

import sys
import types
from unittest import mock

# 무거운 런타임 의존성 스텁 (기존 dedup 테스트와 동일한 패턴)
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_a, **_k: None))
sys.modules.setdefault(
    "collectors",
    types.SimpleNamespace(
        ais_collector=types.SimpleNamespace(collect=None),
        adsb_collector=types.SimpleNamespace(collect=None),
        news_collector=types.SimpleNamespace(collect=None),
        social_collector=types.SimpleNamespace(collect=None),
    ),
)
sys.modules.setdefault("analyzer", types.SimpleNamespace(analyze=None))
sys.modules.setdefault("signal_generator", types.SimpleNamespace(process_signals=None))

from src.kaven import kaven


# ── 헬퍼 ────────────────────────────────────────────────────────────


def _sample_log_entry() -> dict:
    return {
        "run_id": "20260411_120000",
        "started_at": "2026-04-11T12:00:00+00:00",
    }


def _sample_events() -> list[dict]:
    return [{"event": "테스트 이벤트", "severity": 3}]


# ── 1. 기본: CONVEX_SITE_URL 미설정 시 외부 전송 없음 ───────────────


def test_upload_skipped_when_convex_site_url_unset(monkeypatch, caplog):
    """CONVEX_SITE_URL이 없으면 urlopen이 호출되지 않아야 한다."""
    monkeypatch.delenv("CONVEX_SITE_URL", raising=False)
    monkeypatch.delenv("CONVEX_EVENT_PATH", raising=False)

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        kaven._upload_remote_if_enabled(
            _sample_log_entry(), _sample_events(), {"sent": 1, "logged": 1}
        )

    mock_urlopen.assert_not_called()


def test_upload_skipped_when_convex_site_url_empty_string(monkeypatch):
    """빈 문자열/공백도 미설정과 동일 취급."""
    monkeypatch.setenv("CONVEX_SITE_URL", "   ")

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        kaven._upload_remote_if_enabled(
            _sample_log_entry(), _sample_events(), {"sent": 0, "logged": 0}
        )

    mock_urlopen.assert_not_called()


def test_upload_skipped_when_events_empty(monkeypatch):
    """events가 비어 있으면 설정이 있어도 전송하지 않음."""
    monkeypatch.setenv("CONVEX_SITE_URL", "https://example.convex.site")

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        kaven._upload_remote_if_enabled(
            _sample_log_entry(), [], {"sent": 0, "logged": 0}
        )

    mock_urlopen.assert_not_called()


# ── 2. CONVEX_SITE_URL 설정 시 엔드포인트 조합 ──────────────────────


def test_upload_uses_configured_site_url_and_default_path(monkeypatch):
    """CONVEX_SITE_URL 설정 시 /addKavenRun 기본 경로로 POST."""
    monkeypatch.setenv("CONVEX_SITE_URL", "https://example.convex.site")
    monkeypatch.delenv("CONVEX_EVENT_PATH", raising=False)

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        # Request context manager 동작 흉내
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = b'{"ok":true}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        kaven._upload_remote_if_enabled(
            _sample_log_entry(), _sample_events(), {"sent": 1, "logged": 1}
        )

    assert mock_urlopen.called, "CONVEX_SITE_URL 설정 시 urlopen이 호출되어야 함"

    # 전달된 Request 객체의 full_url 확인
    call_args = mock_urlopen.call_args
    req = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
    assert req.full_url == "https://example.convex.site/addKavenRun"
    assert req.get_method() == "POST"


def test_upload_respects_custom_event_path(monkeypatch):
    """CONVEX_EVENT_PATH 오버라이드가 적용되어야 한다."""
    monkeypatch.setenv("CONVEX_SITE_URL", "https://example.convex.site")
    monkeypatch.setenv("CONVEX_EVENT_PATH", "/customRoute")

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        kaven._upload_remote_if_enabled(
            _sample_log_entry(), _sample_events(), {"sent": 0, "logged": 0}
        )

    req = mock_urlopen.call_args.args[0]
    assert req.full_url == "https://example.convex.site/customRoute"


def test_upload_path_missing_leading_slash_is_fixed(monkeypatch):
    """CONVEX_EVENT_PATH에 leading slash가 없어도 정상 조합."""
    monkeypatch.setenv("CONVEX_SITE_URL", "https://example.convex.site")
    monkeypatch.setenv("CONVEX_EVENT_PATH", "addKavenRun")

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        kaven._upload_remote_if_enabled(
            _sample_log_entry(), _sample_events(), {}
        )

    req = mock_urlopen.call_args.args[0]
    assert req.full_url == "https://example.convex.site/addKavenRun"


def test_upload_trailing_slash_in_site_url_is_stripped(monkeypatch):
    """site_url 끝에 trailing slash가 있어도 중복 `//` 없이 조합."""
    monkeypatch.setenv("CONVEX_SITE_URL", "https://example.convex.site/")
    monkeypatch.delenv("CONVEX_EVENT_PATH", raising=False)

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        kaven._upload_remote_if_enabled(
            _sample_log_entry(), _sample_events(), {}
        )

    req = mock_urlopen.call_args.args[0]
    assert req.full_url == "https://example.convex.site/addKavenRun"


# ── 3. 실패 복원력 ─────────────────────────────────────────────────


def test_upload_failure_does_not_raise(monkeypatch):
    """원격 실패는 예외로 전파되지 않아야 한다 (로컬 로그 보존 우선)."""
    monkeypatch.setenv("CONVEX_SITE_URL", "https://example.convex.site")

    with mock.patch("urllib.request.urlopen", side_effect=OSError("network")):
        # 예외가 밖으로 전파되지 않아야 함
        kaven._upload_remote_if_enabled(
            _sample_log_entry(), _sample_events(), {"sent": 0}
        )


# ── 4. 하드코딩 엔드포인트 부재 (회귀 방지) ─────────────────────────


def test_no_hardcoded_convex_endpoint_in_source():
    """기존 하드코딩 endpoint가 소스에 남아 있지 않아야 한다."""
    import inspect
    source = inspect.getsource(kaven)
    assert "exciting-cod-257.convex.site" not in source, (
        "하드코딩된 convex endpoint가 여전히 남아 있음 — 이슈 #7 회귀"
    )
    assert "addMavenRun" not in source, (
        "구 Maven endpoint 경로가 여전히 남아 있음 — 이슈 #7 회귀"
    )

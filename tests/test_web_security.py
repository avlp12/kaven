"""P0 regressions for mutation authentication, CORS, and web CLI configuration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from webapp.backend.app import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("KAVEN_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("KAVEN_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("KAVEN_ALLOWED_CLI_COMMANDS", raising=False)
    return TestClient(create_app())


def _asset_payload() -> dict:
    return {"items": [{"name": "Gold", "type": "commodity"}]}


def test_mutations_without_token_allow_testclient_loopback_compatibility(client: TestClient) -> None:
    with patch("webapp.backend.routers.system.update_config_section", return_value="config.json") as save:
        response = client.put("/config/assets", json=_asset_payload())
    assert response.status_code == 200
    save.assert_called_once()


def test_mutations_without_token_reject_non_loopback_client(client: TestClient) -> None:
    external = TestClient(client.app, client=("203.0.113.8", 12345))
    assert external.put("/config/assets", json=_asset_payload()).status_code == 403
    # Authentication runs before the heavy run_once import/execution.
    assert external.post("/runs/once").status_code == 403


def test_loopback_mutation_rejects_untrusted_browser_origin(client: TestClient) -> None:
    with patch("src.kaven.kaven.run_once", new=AsyncMock(return_value={"executed": True})) as run:
        denied = client.post("/runs/once", headers={"Origin": "https://evil.example"})
        allowed = client.post("/runs/once", headers={"Origin": "http://localhost:8080"})

    assert denied.status_code == 403
    assert allowed.status_code == 200
    run.assert_awaited_once()


def test_admin_token_required_and_supported_in_both_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAVEN_ADMIN_TOKEN", "correct-horse")
    client = TestClient(create_app())

    assert client.put("/config/assets", json=_asset_payload()).status_code == 401
    assert client.post("/runs/once").status_code == 401
    assert (
        client.put(
            "/config/assets",
            json=_asset_payload(),
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 403
    )

    with patch("webapp.backend.routers.system.update_config_section", return_value="config.json"):
        bearer = client.put(
            "/config/assets",
            json=_asset_payload(),
            headers={"Authorization": "Bearer correct-horse"},
        )
        custom = client.put(
            "/config/assets",
            json=_asset_payload(),
            headers={"X-Kaven-Admin-Token": "correct-horse"},
        )
    assert bearer.status_code == 200
    assert custom.status_code == 200


def test_cors_uses_default_local_allowlist_and_disables_credentials(client: TestClient) -> None:
    allowed = client.options(
        "/health",
        headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"},
    )
    denied = client.options(
        "/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:8080"
    assert "access-control-allow-credentials" not in allowed.headers
    assert "access-control-allow-origin" not in denied.headers


def test_cors_allowed_origins_env_is_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAVEN_ALLOWED_ORIGINS", "https://one.example, https://two.example ")
    client = TestClient(create_app())
    response = client.options(
        "/health",
        headers={"Origin": "https://two.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "https://two.example"


@pytest.mark.parametrize("command", ["sh -c id", "python -c 'print(1)'", "curl https://example.com"])
def test_web_cli_provider_rejects_dangerous_executables(client: TestClient, command: str) -> None:
    response = client.put(
        "/config/cli_providers",
        json={"items": [{"name": "unsafe", "command": command}]},
    )
    assert response.status_code == 400
    assert "allowed" in response.json()["detail"]


def test_web_cli_provider_allows_defaults_and_env_extensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KAVEN_ALLOWED_CLI_COMMANDS", "my-agent")
    client = TestClient(create_app())
    with patch("webapp.backend.routers.system.update_config_section", return_value="config.json"):
        default = client.put(
            "/config/cli_providers",
            json={"items": [{"name": "Claude", "command": "claude --print"}]},
        )
        extended = client.put(
            "/config/cli_providers",
            json={"items": [{"name": "Custom", "command": "my-agent --json"}]},
        )
    assert default.status_code == 200
    assert extended.status_code == 200

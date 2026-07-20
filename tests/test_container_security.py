from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_docker_context_excludes_all_dotenv_files() -> None:
    rules = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in rules
    assert "**/.env" in rules
    assert ".env.*" in rules
    assert "**/.env.*" in rules


def test_compose_uses_named_log_volume_for_non_root_container() -> None:
    compose = (ROOT / "deploy/docker/docker-compose.yml").read_text(encoding="utf-8")
    assert "kaven-logs:/app/src/kaven/logs" in compose
    assert "../../src/kaven/logs:/app/src/kaven/logs" not in compose

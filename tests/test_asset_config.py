"""자산 설정(config assets 섹션) + 지역 다국어 메타 테스트."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_a, **_k: None))

from src.kaven import config_loader
from src.kaven.aggregates import asset_meta, portfolio_history
from src.kaven.config_loader import (
    DEFAULT_ASSETS,
    get_assets,
    load_config,
    update_config_section,
)
from src.kaven.ops_summary import build_ops_summary

_TEMP_DIRS: list[TemporaryDirectory] = []  # prevent GC during test run

_DATE = "20260413"


def _tmp() -> Path:
    tmpdir = TemporaryDirectory()
    _TEMP_DIRS.append(tmpdir)
    return Path(tmpdir.name)


def _write_events_log(log_dir: Path, date: str = _DATE) -> None:
    runs = [{"run_id": "r1", "started_at": "2026-04-13T01:00:00+00:00", "events": [
        {"event": "이벤트 A", "severity": 4, "region": "korea",
         "affected_assets": ["KOSPI", "비트코인"]},
    ]}]
    with (log_dir / f"kaven_{date}.jsonl").open("w", encoding="utf-8") as f:
        for run in runs:
            f.write(json.dumps(run, ensure_ascii=False) + "\n")


def test_default_assets_loaded_without_config(monkeypatch):
    """설정 파일이 없으면 내장 기본 자산 목록."""
    monkeypatch.setenv("KAVEN_CONFIG", str(_tmp() / "none.json"))
    assets = get_assets(only_enabled=False)
    assert assets == DEFAULT_ASSETS
    assert {"WTI", "KOSPI", "TSMC"} <= {a["name"] for a in assets}


def test_update_config_section_roundtrip_preserves_others(monkeypatch):
    """assets 섹션 저장 시 기존 다른 섹션 override는 보존."""
    cfg_path = _tmp() / "config.json"
    cfg_path.write_text(json.dumps({"news_keywords": [
        {"id": "x", "query": "custom query", "enabled": True}]}), encoding="utf-8")
    monkeypatch.setenv("KAVEN_CONFIG", str(cfg_path))

    saved = update_config_section("assets", [
        {"id": "gold", "name": "금", "type": "commodity", "description": "금 현물", "enabled": True},
    ])
    assert saved == cfg_path
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["news_keywords"][0]["query"] == "custom query"  # 보존
    assert data["assets"][0]["name"] == "금"

    cfg = load_config()
    assert [a["name"] for a in cfg["assets"]] == ["금"]


def test_asset_meta_reflects_custom_config(monkeypatch):
    """asset_meta는 커스텀 설정의 type/description/enabled를 반영."""
    cfg_path = _tmp() / "config.json"
    cfg_path.write_text(json.dumps({"assets": [
        {"name": "비트코인", "type": "crypto", "description": "BTC/USD", "enabled": True},
        {"name": "KOSPI", "type": "index", "description": "코스피", "enabled": False},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("KAVEN_CONFIG", str(cfg_path))

    meta = asset_meta()
    assert meta["비트코인"]["type"] == "crypto"
    assert meta["KOSPI"]["enabled"] is False


def test_disabled_asset_excluded_from_portfolio_and_ops(monkeypatch):
    """enabled=false 자산은 포트폴리오/ops 집계에서 제외, 미등록 자산은 유지."""
    cfg_path = _tmp() / "config.json"
    cfg_path.write_text(json.dumps({"assets": [
        {"name": "KOSPI", "type": "index", "description": "코스피", "enabled": False},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("KAVEN_CONFIG", str(cfg_path))

    log_dir = _tmp()
    # portfolio_history는 오늘 기준 상대 집계이므로 오늘 날짜로 기록
    from src.kaven.log_store import recent_dates
    today = recent_dates(1)[0]
    _write_events_log(log_dir, today)

    names = {a["name"] for a in portfolio_history(log_dir, days=1)}
    assert "KOSPI" not in names
    assert "비트코인" in names  # 미등록 자산은 type=other로 계속 표시

    ops_assets = {a["name"] for a in build_ops_summary(log_dir, today)["assets"]}
    assert "KOSPI" not in ops_assets
    assert "비트코인" in ops_assets


def test_ops_regions_include_english_metadata(monkeypatch):
    """ops 지역 payload에 name_en/description_en 포함 (언어 전환용)."""
    monkeypatch.setenv("KAVEN_CONFIG", str(_tmp() / "none.json"))
    regions = {r["code"]: r for r in build_ops_summary(_tmp(), "99990101")["regions"]}
    assert regions["korea"]["name_en"] == "Korean Peninsula"
    assert "KOSPI" in regions["korea"]["description_en"]
    assert regions["hormuz"]["name_en"] == "Strait of Hormuz"


def test_config_loader_includes_assets_section(monkeypatch):
    """load_config 결과에 assets 섹션이 포함되어 /config API에 노출된다."""
    monkeypatch.setenv("KAVEN_CONFIG", str(_tmp() / "none.json"))
    assert "assets" in load_config()
    assert config_loader.get_assets()  # enabled 기본 True


# ── v0.0.13: regions 설정화 + 범용 섹션 검증 ────────────────────


def test_custom_region_reflected_in_ops(monkeypatch):
    """config regions 섹션이 ops 지역 목록/이벤트 지역명에 반영된다."""
    cfg_path = _tmp() / "config.json"
    cfg_path.write_text(json.dumps({"regions": [
        {"code": "baltic", "name": "발트해", "name_en": "Baltic Sea",
         "lat": 58.0, "lng": 20.0, "description": "발트해 감시", "enabled": True},
        {"code": "korea", "name": "한반도", "name_en": "Korean Peninsula",
         "lat": 37.5, "lng": 127.0, "description": "한반도", "enabled": False},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("KAVEN_CONFIG", str(cfg_path))

    summary = build_ops_summary(_tmp(), "99990101")
    codes = [r["code"] for r in summary["regions"]]
    assert codes == ["baltic"]  # enabled=false korea는 목록에서 제외

    # 비활성 지역도 이벤트 지역명 lookup에는 사용됨
    log_dir = _tmp()
    _write_events_log(log_dir)  # korea 이벤트
    ev = build_ops_summary(log_dir, _DATE)["events"][0]
    assert ev["region_name"] == "한반도"


def test_section_validators():
    """범용 PUT /config/{section} 검증 로직."""
    import pytest

    from webapp.backend.routers.system import (
        EDITABLE_SECTIONS,
        _validate_feed,
        _validate_region,
        _validate_zone,
    )
    from fastapi import HTTPException

    # zone: 좌표 범위/순서 검증
    ok = _validate_zone({"name": "발트해", "lat_min": 54, "lat_max": 60,
                         "lon_min": 10, "lon_max": 30, "baseline_ships": 40}, True)
    assert ok["baseline_ships"] == 40 and ok["enabled"] is True
    with pytest.raises(HTTPException):
        _validate_zone({"name": "bad", "lat_min": 60, "lat_max": 54,
                        "lon_min": 10, "lon_max": 30}, False)

    # feed: URL 스킴 검증
    assert _validate_feed({"name": "R", "url": "https://x.com/rss"})["url"].startswith("https")
    with pytest.raises(HTTPException):
        _validate_feed({"name": "R", "url": "javascript:alert(1)"})

    # region: code slug + 영문 fallback
    r = _validate_region({"code": "Baltic Sea!", "name": "발트해", "lat": 58, "lng": 20})
    assert r["code"] == "baltic_sea" and r["name_en"] == "발트해"

    # 편집 가능 섹션 화이트리스트
    assert set(EDITABLE_SECTIONS) == {
        "assets", "regions", "ais_zones", "adsb_zones",
        "news_feeds", "news_keywords", "social_keywords",
    }

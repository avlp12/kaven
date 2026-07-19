"""
Kaven Configuration Loader — 감시 구역, 뉴스 피드, 소셜 키워드 등을
JSON 설정 파일로 관리. 각 항목에 `enabled` 플래그를 두어 추가/해제 가능.

설정 파일 탐색 순서:
1. ``KAVEN_CONFIG`` 환경변수가 지정한 경로
2. ``src/kaven/config.json`` (기본)
3. 파일 없으면 내장 기본값 사용 (기존 동작과 완전 호환)

예시 스키마는 ``src/kaven/config.example.json`` 참조.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("kaven.config")

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"


# ── Defaults ────────────────────────────────────────────────────

DEFAULT_AIS_ZONES: list[dict[str, Any]] = [
    {
        "id": "hormuz",
        "name": "호르무즈 해협",
        "enabled": True,
        "lat_min": 25.5, "lat_max": 27.0,
        "lon_min": 56.0, "lon_max": 57.5,
        "baseline_ships": 50,
    },
    {
        "id": "malacca",
        "name": "말라카 해협",
        "enabled": True,
        "lat_min": 1.0, "lat_max": 6.0,
        "lon_min": 99.0, "lon_max": 104.0,
        "baseline_ships": 80,
    },
]

DEFAULT_ADSB_ZONES: list[dict[str, Any]] = [
    {
        "id": "middle_east",
        "name": "중동 (이란·이라크·걸프)",
        "enabled": True,
        "lat_min": 24.0, "lat_max": 38.0,
        "lon_min": 44.0, "lon_max": 62.0,
    },
    {
        "id": "taiwan_strait",
        "name": "대만 해협",
        "enabled": True,
        "lat_min": 22.0, "lat_max": 27.0,
        "lon_min": 117.0, "lon_max": 122.0,
    },
    {
        "id": "korean_peninsula",
        "name": "한반도",
        "enabled": True,
        "lat_min": 33.0, "lat_max": 43.0,
        "lon_min": 124.0, "lon_max": 132.0,
    },
]

DEFAULT_NEWS_FEEDS: list[dict[str, Any]] = [
    {"id": "reuters_world",    "name": "Reuters World",     "enabled": True, "url": "https://feeds.reuters.com/Reuters/worldNews"},
    {"id": "ap_topnews",       "name": "AP Top News",       "enabled": True, "url": "https://rsshub.app/apnews/topics/apf-topnews"},
    {"id": "bbc_world",        "name": "BBC World",         "enabled": True, "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"id": "bbc_asia",         "name": "BBC Asia",          "enabled": True, "url": "http://feeds.bbci.co.uk/news/world/asia/rss.xml"},
    {"id": "bbc_middle_east",  "name": "BBC Middle East",   "enabled": True, "url": "http://feeds.bbci.co.uk/news/world/middle_east/rss.xml"},
]

DEFAULT_NEWS_KEYWORDS: list[dict[str, Any]] = [
    {"id": "iran_military",        "query": "Iran military",             "enabled": True},
    {"id": "hormuz_strait",        "query": "Hormuz strait",             "enabled": True},
    {"id": "taiwan_strait_mil",    "query": "Taiwan strait military",    "enabled": True},
    {"id": "dprk_missile",         "query": "DPRK missile",              "enabled": True},
    {"id": "north_korea_nuclear",  "query": "North Korea nuclear",       "enabled": True},
    {"id": "semiconductor_embargo", "query": "semiconductor embargo",    "enabled": True},
    {"id": "thaad_deployment",     "query": "THAAD deployment",          "enabled": True},
    {"id": "ukraine_offensive",    "query": "Ukraine Russia offensive",  "enabled": True},
    {"id": "oil_supply",           "query": "oil supply disruption",     "enabled": True},
    {"id": "south_china_sea",      "query": "South China Sea",           "enabled": True},
    {"id": "israel_iran",          "query": "Israel Iran",               "enabled": True},
    {"id": "sanctions_china",      "query": "sanctions China",           "enabled": True},
    {"id": "nato_deployment",      "query": "NATO deployment",           "enabled": True},
    {"id": "middle_east_war_ko",   "query": "중동 전쟁",                 "enabled": True},
    {"id": "taiwan_strait_ko",     "query": "대만 해협",                 "enabled": True},
    {"id": "semi_sanctions_ko",    "query": "반도체 제재",               "enabled": True},
]

DEFAULT_CLI_PROVIDERS: list[dict[str, Any]] = [
    {"id": "claude", "name": "Claude Code CLI (Claude Pro/Max 구독)", "enabled": True,
     "command": "claude -p --output-format text"},
    {"id": "codex", "name": "OpenAI Codex CLI (ChatGPT Plus/Pro 구독)", "enabled": True,
     "command": "codex exec"},
    {"id": "cursor", "name": "Cursor Agent CLI (Cursor 구독)", "enabled": True,
     "command": "cursor-agent -p --output-format text"},
    {"id": "gemini", "name": "Gemini CLI (Google 계정 OAuth)", "enabled": True,
     "command": "gemini -p"},
]


def _default_regions() -> list[dict[str, Any]]:
    """내장 REGION_INFO를 설정 파일 스키마(list + code/enabled)로 변환."""
    from src.kaven.regions import REGION_INFO  # 지연 import (모듈 순환 방지)

    return [{"code": code, "enabled": True, **info} for code, info in REGION_INFO.items()]


DEFAULT_ASSETS: list[dict[str, Any]] = [
    {"id": "wti",     "name": "WTI",          "type": "commodity", "enabled": True,
     "description": "서부 텍사스 원유 (에너지 벤치마크)"},
    {"id": "kospi",   "name": "KOSPI",        "type": "index",     "enabled": True,
     "description": "한국 종합주가지수"},
    {"id": "usdkrw",  "name": "원/달러",       "type": "currency",  "enabled": True,
     "description": "USD/KRW 환율"},
    {"id": "samsung", "name": "삼성전자",      "type": "equity",    "enabled": True,
     "description": "반도체·전자 (KRX 005930)"},
    {"id": "skhynix", "name": "SK하이닉스",    "type": "equity",    "enabled": True,
     "description": "메모리 반도체 (KRX 000660)"},
    {"id": "tsmc",    "name": "TSMC",         "type": "equity",    "enabled": True,
     "description": "글로벌 파운드리 1위 (TWSE 2330)"},
    {"id": "hyundai", "name": "현대차",        "type": "equity",    "enabled": True,
     "description": "자동차 (KRX 005380)"},
    {"id": "lges",    "name": "LG에너지솔루션", "type": "equity",    "enabled": True,
     "description": "배터리 (KRX 373220)"},
]

DEFAULT_SOCIAL_KEYWORDS: list[dict[str, Any]] = [
    {"id": "iran_hormuz",           "query": "Iran Hormuz",           "enabled": True},
    {"id": "taiwan_strait_mil_soc", "query": "Taiwan Strait military", "enabled": True},
    {"id": "dprk_missile_soc",      "query": "DPRK missile",          "enabled": True},
    {"id": "semiconductor_embargo_soc", "query": "semiconductor embargo", "enabled": True},
    {"id": "oil_supply_soc",        "query": "oil supply disruption", "enabled": True},
    {"id": "ukraine_offensive_soc", "query": "Ukraine offensive",     "enabled": True},
    {"id": "korea_thaad",           "query": "Korea THAAD",           "enabled": True},
    {"id": "gaza_ceasefire",        "query": "Gaza ceasefire",        "enabled": True},
]


# ── Loader ──────────────────────────────────────────────────────


def _resolve_config_path() -> Path:
    """탐색 순서에 따라 설정 파일 경로 결정."""
    env_path = os.environ.get("KAVEN_CONFIG", "").strip()
    if env_path:
        return Path(env_path).expanduser()
    return _DEFAULT_CONFIG_PATH


def load_config() -> dict[str, Any]:
    """
    설정 파일 로드. 파일 없으면 내장 기본값 반환.

    Returns:
        {
            "ais_zones": [...],
            "adsb_zones": [...],
            "news_feeds": [...],
            "news_keywords": [...],
            "social_keywords": [...],
        }
    """
    path = _resolve_config_path()
    overrides: dict[str, Any] = {}
    if path.exists():
        try:
            overrides = json.loads(path.read_text(encoding="utf-8"))
            logger.info(f"Kaven config loaded: {path}")
        except Exception as e:
            logger.warning(f"config 파일 파싱 실패 ({path}): {e} — 기본값 사용")
            overrides = {}
    else:
        logger.debug(f"config 파일 없음 ({path}) — 기본값 사용")

    return {
        "ais_zones":       overrides.get("ais_zones",       DEFAULT_AIS_ZONES),
        "adsb_zones":      overrides.get("adsb_zones",      DEFAULT_ADSB_ZONES),
        "news_feeds":      overrides.get("news_feeds",      DEFAULT_NEWS_FEEDS),
        "news_keywords":   overrides.get("news_keywords",   DEFAULT_NEWS_KEYWORDS),
        "social_keywords": overrides.get("social_keywords", DEFAULT_SOCIAL_KEYWORDS),
        "assets":          overrides.get("assets",          DEFAULT_ASSETS),
        "regions":         overrides.get("regions",         _default_regions()),
        "cli_providers":   overrides.get("cli_providers",   DEFAULT_CLI_PROVIDERS),
    }


def update_config_section(key: str, items: list[dict[str, Any]]) -> Path:
    """
    설정 파일의 특정 섹션만 갱신 저장 (다른 섹션의 override는 보존).

    파일이 없으면 해당 섹션만 담은 새 파일을 생성한다.
    Returns: 저장된 설정 파일 경로.
    """
    path = _resolve_config_path()
    overrides: dict[str, Any] = {}
    if path.exists():
        try:
            overrides = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"config 파일 파싱 실패 ({path}): {e} — 섹션만 담아 재작성")
            overrides = {}
    overrides[key] = items
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info(f"Kaven config 섹션 저장: {key} ({len(items)} items) -> {path}")
    return path


def enabled_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """enabled 플래그가 True인 항목만 필터링. 미지정이면 True 간주."""
    return [x for x in items if x.get("enabled", True)]


def get_ais_zones(only_enabled: bool = True) -> list[dict[str, Any]]:
    zones = load_config()["ais_zones"]
    return enabled_items(zones) if only_enabled else zones


def get_adsb_zones(only_enabled: bool = True) -> list[dict[str, Any]]:
    zones = load_config()["adsb_zones"]
    return enabled_items(zones) if only_enabled else zones


def get_news_feeds(only_enabled: bool = True) -> list[dict[str, Any]]:
    feeds = load_config()["news_feeds"]
    return enabled_items(feeds) if only_enabled else feeds


def get_news_keywords(only_enabled: bool = True) -> list[dict[str, Any]]:
    keywords = load_config()["news_keywords"]
    return enabled_items(keywords) if only_enabled else keywords


def get_social_keywords(only_enabled: bool = True) -> list[dict[str, Any]]:
    keywords = load_config()["social_keywords"]
    return enabled_items(keywords) if only_enabled else keywords


def get_assets(only_enabled: bool = True) -> list[dict[str, Any]]:
    assets = load_config()["assets"]
    return enabled_items(assets) if only_enabled else assets

"""
Social Collector — X(Twitter) 지정학 키워드 수집
브라우저 직접 검색 방식 (OpenClaw browser MCP 활용)

방식: X Advanced Search URL 직접 호출 → PinchTab text 추출
폴백: SearxNG 뉴스 검색 (X 차단 시)
"""

import asyncio
import json
import logging
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("kaven.social")

# 검색 키워드
SEARCH_KEYWORDS = [
    "Iran Hormuz",
    "Taiwan Strait military",
    "DPRK missile",
    "semiconductor embargo",
    "oil supply disruption",
    "Ukraine offensive",
    "Korea THAAD",
    "Gaza ceasefire",
]

PINCHTAB_BASE = "http://localhost:9867"
SEARXNG_BASE = "http://localhost:8080"


async def collect() -> list[dict[str, Any]]:
    """X 지정학 키워드 수집."""
    results = []

    for keyword in SEARCH_KEYWORDS:
        try:
            # 1차: SearxNG (time_range 없이 — 더 많은 결과)
            items = await _search_via_searxng(keyword)
            if items:
                results.extend(items)
            else:
                # 2차: PinchTab으로 X 직접 검색
                items = await _search_via_pinchtab(keyword)
                results.extend(items)
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.warning(f"X 검색 실패 ({keyword}): {e}")

    logger.info(f"X/소셜 수집 완료: {len(results)}건")
    return results


async def _search_via_searxng(query: str) -> list[dict[str, Any]]:
    """SearxNG로 X 관련 뉴스 검색 (time_range 없이)."""
    encoded = urllib.parse.quote(f"{query} twitter OR x.com")
    url = f"{SEARXNG_BASE}/search?q={encoded}&format=json&engines=brave,duckduckgo"

    results = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Kaven/0.0.03"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        for item in data.get("results", [])[:5]:
            title = item.get("title", "")
            content = item.get("content", "")
            result_url = item.get("url", "")

            if not (title or content):
                continue

            tweet_id = None
            m = re.search(r"/status/(\d+)", result_url)
            if m:
                tweet_id = m.group(1)

            author = None
            m2 = re.search(r"(?:twitter|x)\.com/([^/?\s]+)", result_url)
            if m2 and m2.group(1) not in ("search", "hashtag", "i"):
                author = m2.group(1)

            results.append({
                "source": "social",
                "platform": "x",
                "tweet_id": tweet_id,
                "author": author,
                "text": (content or title)[:500],
                "url": result_url,
                "search_keyword": query,
                "collected_via": "searxng",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    except Exception as e:
        logger.debug(f"SearxNG 실패 ({query}): {e}")

    return results


async def _search_via_pinchtab(query: str) -> list[dict[str, Any]]:
    """PinchTab으로 X 검색 페이지 텍스트 추출."""
    results = []
    try:
        # PinchTab 탭 목록 조회
        req = urllib.request.Request(
            f"{PINCHTAB_BASE}/tabs",
            headers={"User-Agent": "Kaven/0.0.03"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            tabs_data = json.loads(resp.read().decode())
        tabs = tabs_data.get("tabs", [])
        if not tabs:
            return []

        tab_id = tabs[0]["id"]

        # X 검색 URL로 이동
        encoded_q = urllib.parse.quote(query)
        search_url = f"https://x.com/search?q={encoded_q}&src=typed_query&f=live"

        nav_req = urllib.request.Request(
            f"{PINCHTAB_BASE}/nav",
            data=json.dumps({"tabId": tab_id, "url": search_url}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "Kaven/0.0.03"},
            method="POST"
        )
        with urllib.request.urlopen(nav_req, timeout=10) as resp:
            pass

        # 3초 대기 (페이지 로드)
        await asyncio.sleep(3)

        # 텍스트 추출
        text_req = urllib.request.Request(
            f"{PINCHTAB_BASE}/text?tabId={tab_id}",
            headers={"User-Agent": "Kaven/0.0.03"}
        )
        with urllib.request.urlopen(text_req, timeout=10) as resp:
            page_text = resp.read().decode(errors="replace")

        # 트윗 텍스트 파싱 (X 페이지 구조 기준)
        # 줄 단위로 분리, 비어있지 않고 충분히 긴 줄만 추출
        lines = [l.strip() for l in page_text.split("\n") if len(l.strip()) > 30]
        tweet_candidates = [l for l in lines if not l.startswith("http") and len(l) < 300][:5]

        for text in tweet_candidates:
            results.append({
                "source": "social",
                "platform": "x",
                "tweet_id": None,
                "author": None,
                "text": text[:500],
                "url": search_url,
                "search_keyword": query,
                "collected_via": "pinchtab_browser",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    except Exception as e:
        logger.debug(f"PinchTab X 검색 실패 ({query}): {e}")

    return results

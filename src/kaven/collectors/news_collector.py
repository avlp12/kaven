"""
News Collector — 지정학 뉴스 수집

SearxNG (로컬) + Reuters/AP/BBC RSS 파싱.
중복 제거, 최근 1시간 이내 기사만 처리.
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, cast

import aiohttp
import feedparser

from src.kaven.config_loader import get_news_feeds, get_news_keywords
from src.kaven.version import __version__

logger = logging.getLogger("kaven.news")

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")


def _rss_feeds() -> dict[str, str]:
    """활성화된 RSS 피드를 dict로 반환 (id → url)."""
    return {feed["id"]: feed["url"] for feed in get_news_feeds(only_enabled=True)}


def _geopolitical_keywords() -> list[str]:
    """활성화된 키워드(query) 목록 반환."""
    return [kw["query"] for kw in get_news_keywords(only_enabled=True)]


async def collect() -> list[dict[str, Any]]:
    """뉴스 수집 실행. RSS + SearxNG 병렬 수집 후 중복 제거."""
    results = []
    seen_hashes: set[str] = set()

    async with aiohttp.ClientSession() as session:
        # RSS와 SearxNG 병렬 수집
        rss_task = _collect_rss(session)
        searx_task = _collect_searxng(session)

        gathered = await asyncio.gather(
            rss_task, searx_task, return_exceptions=True
        )
        rss_result = cast(list[dict[str, Any]] | BaseException, gathered[0])
        searx_result = cast(list[dict[str, Any]] | BaseException, gathered[1])

        if isinstance(rss_result, BaseException):
            logger.error(f"RSS 수집 실패: {rss_result}")
            rss_results: list[dict[str, Any]] = []
        else:
            rss_results = rss_result

        if isinstance(searx_result, BaseException):
            logger.error(f"SearxNG 수집 실패: {searx_result}")
            searx_results: list[dict[str, Any]] = []
        else:
            searx_results = searx_result

        # 중복 제거 후 병합
        for item in rss_results + searx_results:
            h = _content_hash(item.get("title", "") + item.get("url", ""))
            if h not in seen_hashes:
                seen_hashes.add(h)
                results.append(item)

    logger.info(f"뉴스 수집 완료: {len(results)}건 (중복 제거 후)")
    return results


async def _collect_rss(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    """RSS 피드에서 최근 1시간 이내 기사 수집."""
    results = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    feeds = _rss_feeds()
    keywords = _geopolitical_keywords()

    if not feeds:
        logger.info("활성화된 RSS 피드 없음 — RSS 수집 스킵")
        return []

    for feed_name, feed_url in feeds.items():
        try:
            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": f"Kaven/{__version__}"}
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"RSS {feed_name} HTTP {resp.status}")
                    continue

                raw = await resp.text()
                feed = feedparser.parse(raw)

                for entry in feed.entries[:20]:
                    # 발행 시간 확인
                    pub_time = _parse_feed_time(entry)
                    if pub_time and pub_time < cutoff:
                        continue

                    title = entry.get("title", "").strip()
                    summary = entry.get("summary", "").strip()
                    link = entry.get("link", "")

                    # 지정학 키워드 매칭
                    text_combined = f"{title} {summary}".lower()
                    matched_keywords = [
                        kw for kw in keywords
                        if kw.lower() in text_combined
                    ]

                    if matched_keywords or _is_geopolitical_title(title):
                        results.append({
                            "source": "news",
                            "feed": feed_name,
                            "title": title,
                            "summary": summary[:500],
                            "url": link,
                            "keywords_matched": matched_keywords,
                            "published": pub_time.isoformat() if pub_time else None,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
        except Exception as e:
            logger.warning(f"RSS {feed_name} 수집 실패: {e}")

    return results


async def _collect_searxng(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    """SearxNG 로컬 인스턴스로 지정학 뉴스 검색."""
    results = []

    # 활성화된 키워드 중 상위 5개로 검색 (부하 관리)
    search_queries = _geopolitical_keywords()[:5]
    if not search_queries:
        logger.info("활성화된 뉴스 키워드 없음 — SearxNG 검색 스킵")
        return []

    for query in search_queries:
        try:
            params = {
                "q": query,
                "format": "json",
                "categories": "news",
                "time_range": "day",
                "language": "en",
            }

            async with session.get(
                f"{SEARXNG_URL}/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"SearxNG 쿼리 실패 ({query}): HTTP {resp.status}")
                    continue

                data = await resp.json()

                for item in data.get("results", [])[:5]:
                    results.append({
                        "source": "news",
                        "feed": "searxng",
                        "title": item.get("title", ""),
                        "summary": item.get("content", "")[:500],
                        "url": item.get("url", ""),
                        "keywords_matched": [query],
                        "published": item.get("publishedDate"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

            await asyncio.sleep(0.5)  # SearxNG 부하 방지
        except Exception as e:
            logger.warning(f"SearxNG 검색 실패 ({query}): {e}")

    return results


def _parse_feed_time(entry) -> datetime | None:
    """feedparser entry에서 발행 시간 추출."""
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            try:
                from time import mktime
                dt = datetime.fromtimestamp(mktime(t), tz=timezone.utc)
                return dt
            except Exception:
                pass
    return None


def _is_geopolitical_title(title: str) -> bool:
    """제목에서 지정학 관련 키워드 존재 여부 확인 (광범위 필터)."""
    geo_terms = [
        "war", "conflict", "missile", "nuclear", "sanctions", "military",
        "attack", "strike", "invasion", "embargo", "blockade", "strait",
        "ICBM", "warship", "fighter jet", "aircraft carrier", "tension",
        "전쟁", "미사일", "제재", "공격", "봉쇄",
    ]
    title_lower = title.lower()
    return any(term.lower() in title_lower for term in geo_terms)


def _content_hash(text: str) -> str:
    """간단한 해시로 중복 감지."""
    return hashlib.md5(text.encode()).hexdigest()[:12]

#!/usr/bin/env python3
"""
Kaven Smart System — 지정학 조기경보 + 투자 신호 시스템

팔란티어 Maven Smart System 스타일의 다중 데이터 소스
실시간 수집·분석·알림 개인용 시스템.

사용법:
    python3 kaven.py --once     # 1회 실행
    python3 kaven.py --watch    # 5분 간격 루프
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.kaven.version import __version__

SCRIPT_DIR = Path(__file__).parent


def _load_env_file(env_path: Path) -> None:
    """간단한 .env 로더 (python-dotenv 의존성 제거)."""
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(SCRIPT_DIR / ".env")

# 로깅 설정
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("kaven")

async def run_collectors() -> dict:
    """모든 수집기를 병렬 실행. 개별 실패 허용."""
    from collectors import ais_collector, adsb_collector, news_collector, social_collector

    logger.info("=" * 60)
    logger.info("Kaven 데이터 수집 시작")
    logger.info("=" * 60)
    
    # 모든 collector 병렬 실행
    results = await asyncio.gather(
        _safe_collect("ais", ais_collector.collect),
        _safe_collect("adsb", adsb_collector.collect),
        _safe_collect("news", news_collector.collect),
        _safe_collect("social", social_collector.collect),
        return_exceptions=False,  # _safe_collect가 에러 처리
    )
    
    collected = {}
    for source_name, data in results:
        collected[source_name] = data
        count = len(data) if isinstance(data, list) else 0
        logger.info(f"  {source_name}: {count}건 수집")
    
    return collected


async def _safe_collect(name: str, collector_fn) -> tuple[str, list]:
    """개별 collector 실행 (실패해도 빈 리스트 반환)."""
    try:
        data = await collector_fn()
        return (name, data if isinstance(data, list) else [])
    except Exception as e:
        logger.error(f"Collector [{name}] 실패: {e}")
        return (name, [{
            "source": name,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }])


import re as _re

# 유사도 임계값: 이 값 이상이면 동일 사건으로 판정 (낮출수록 보수적)
SIMILARITY_THRESHOLD = 0.50
NUMERIC_TOKEN_PATTERN = r"\d+(?:\.\d+)?(?:[%대척건명])?"
TOKEN_PATTERN = rf"{NUMERIC_TOKEN_PATTERN}|[가-힣]{{2,}}|[A-Za-z]{{2,}}"


def _normalize(text: str) -> list[str]:
    """텍스트 → 토큰 목록. 한국어 조사·어미 제거 후 유니크 토큰."""
    tokens = _re.findall(TOKEN_PATTERN, text)

    # 한국어 조사·어미 suffix 제거 (형태소 분석기 없이 규칙 기반)
    KO_SUFFIXES = ("에서", "에게", "에서의", "으로", "로서", "로부터", "에서도",
                   "에서는", "이가", "이는", "이를", "이의", "이에", "이와",
                   "가", "는", "을", "를", "의", "와", "과", "도", "만", "에",
                   "이", "라", "로", "게", "서", "가서", "하여", "하며", "하고",
                   "했다", "한다", "했으며", "한다고", "했음", "했는데")

    cleaned = []
    for t in tokens:
        tok = t.lower()
        for sfx in sorted(KO_SUFFIXES, key=len, reverse=True):
            if tok.endswith(sfx) and len(tok) - len(sfx) >= 2:
                tok = tok[: -len(sfx)]
                break
        cleaned.append(tok)

    stopwords = {"있다", "있는", "이는", "인해", "하는", "되는", "이에", "따라",
                 "대한", "통해", "위한", "관련", "수있", "증가로", "으로인한",
                 "the", "and", "for", "its", "that", "with", "from", "due", "as",
                 "in", "of", "to", "on", "at", "by", "an", "it", "is", "are",
                 "has", "can", "say", "says", "also", "more", "its", "war"}
    return [t for t in cleaned if t not in stopwords and len(t) >= 2]


# 한국어↔영어 핵심 지명·기관 번역 매핑 (동일 사건 교차 감지용)
_KO_EN_MAP = {
    "파키스탄": "pakistan", "러시아": "russia", "이란": "iran", "미국": "us",
    "대만": "taiwan", "중국": "china", "이스라엘": "israel", "한반도": "korea",
    "호르무즈": "hormuz", "나토": "nato", "트럼프": "trump", "하메네이": "khamenei",
    "리투아니아": "lithuania", "우크라이나": "ukraine", "인도": "india",
}


def _canonical_tokens(text: str) -> set[str]:
    """토큰을 영어 기준으로 정규화 (한영 혼용 감지용)."""
    tokens = set(_normalize(text))
    canonical = set()
    for t in tokens:
        canonical.add(_KO_EN_MAP.get(t, t))
    return canonical


def _entity_overlap(a: str, b: str) -> float:
    """
    핵심 엔티티(지명·기관·행위자) 겹침 비율.
    한영 혼용 문장에서 Jaccard가 낮게 나오는 문제 보완.
    공통 엔티티 수 / 작은 쪽 엔티티 수 (포함 관계 감지).
    """
    # canonical 중 KO_EN_MAP 값(지명)에 해당하는 것만
    def entities(text):
        return {t for t in _canonical_tokens(text) if t in _KO_EN_MAP.values()}

    ea = entities(a)
    eb = entities(b)
    if not ea or not eb:
        return 0.0
    return len(ea & eb) / min(len(ea), len(eb))


def _jaccard_similarity(a: str, b: str) -> float:
    """두 문장의 Jaccard 유사도. 한영 정규화 적용."""
    ta = _canonical_tokens(a)
    tb = _canonical_tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _core_keywords(text: str) -> set[str]:
    """
    수치 + 지명 추출 — 사건의 핵심 식별자.
    단, 공통적으로 많이 나오는 지명(이란, 러시아 등 단독)은
    키워드 겹침 판단에서 제외 — 너무 광범위하게 묶이는 것 방지.
    """
    nums = set(_re.findall(NUMERIC_TOKEN_PATTERN, text))
    names = set()
    for t in _canonical_tokens(text):
        if t in _KO_EN_MAP.values():
            names.add(t)
    return nums | names


def _keyword_overlap(a: str, b: str) -> float:
    """
    핵심 키워드 겹침 비율.

    조건: 수치(숫자+단위)가 반드시 1개 이상 공통으로 있어야 동일 사건 판정.
    수치 없이 지명만 겹치는 경우 → 동일 사건으로 보지 않음.
    (예: '이란'이라는 단어만 공통 → 다른 사건일 수 있음)
    """
    ka = _core_keywords(a)
    kb = _core_keywords(b)

    # 수치만 추출
    nums_a = set(_re.findall(NUMERIC_TOKEN_PATTERN, a))
    nums_b = set(_re.findall(NUMERIC_TOKEN_PATTERN, b))

    # 수치 공통이 없으면 키워드 겹침 판정 안 함
    if not (nums_a & nums_b):
        return 0.0

    if not ka or not kb:
        return 0.0

    return len(ka & kb) / min(len(ka), len(kb))


def _content_fingerprint(event: dict) -> str:
    """
    내용 동일성 키.
    signal·assets 변화는 갱신으로 보지 않되, severity 외에
    핵심 수치/출처까지 반영해 다른 사건이 동일값으로 뭉개지는
    위험을 줄인다.
    """
    event_text = event.get("event", "")
    numeric_tokens = sorted(_re.findall(NUMERIC_TOKEN_PATTERN, event_text))
    source_url = event.get("source_url") or ""
    key = f"{event.get('severity', 0)}|{source_url}|{'/'.join(numeric_tokens)}"
    return hashlib.md5(key.encode()).hexdigest()


def _load_sent_cache() -> dict:
    """
    전송 이력 캐시 로드.
    구조: {
      "date": "YYYY-MM-DD",
      "sent": [{"event": str, "severity": int, "signal": str, "assets": [...], "content_fp": str, "sent_at": str}, ...]
    }
    날짜가 바뀌면 자동 리셋 (하루 단위).
    """
    cache_file = LOG_DIR / "sent_cache.json"
    today = datetime.now().strftime("%Y-%m-%d")
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if data.get("date") == today:
                return data
        except Exception:
            pass
    return {"date": today, "sent": []}


def _save_sent_cache(cache: dict):
    cache_file = LOG_DIR / "sent_cache.json"
    cache_file.write_text(json.dumps(cache, ensure_ascii=False))


def _find_similar(event: dict, sent_list: list[dict]) -> dict | None:
    """
    이미 전송된 이벤트 중 동일 사건으로 판정되는 항목 반환.
    매칭이 여러 개일 경우 severity가 가장 높은 항목 반환 (중복 저장 대응).

    판정 기준 (OR):
    1. source_url 일치 → 확실히 동일
    2. Jaccard 유사도 ≥ SIMILARITY_THRESHOLD
    3. 수치 공유 + 지명 겹침 ≥ 0.70
    4. 지명 엔티티 완전 일치 + Jaccard ≥ 0.10
    5. 지명 엔티티 부분 일치 + Jaccard ≥ 0.15
    """
    event_text = event.get("event", "")
    event_url = event.get("source_url") or ""
    matches = []

    for prev in sent_list:
        prev_text = prev.get("event", "")

        if event_url and prev.get("source_url") == event_url:
            matches.append(prev)
            continue

        if _is_same_event(event_text, prev_text):
            matches.append(prev)

    if not matches:
        return None

    # 여러 매칭 중 severity 최고값 반환
    return max(matches, key=lambda x: x.get("severity", 0))


def _is_same_event(current_text: str, previous_text: str) -> bool:
    """두 이벤트 설명이 동일 사건인지 판정."""
    sim = _jaccard_similarity(current_text, previous_text)
    kw = _keyword_overlap(current_text, previous_text)
    eo = _entity_overlap(current_text, previous_text)
    return (
        sim >= SIMILARITY_THRESHOLD
        or kw >= 0.70
        or (eo >= 1.0 and sim >= 0.10)
        or (eo >= 0.60 and sim >= 0.15)
    )


def _deduplicate_events(events: list[dict], cache: dict) -> list[dict]:
    """
    유사도 기반 중복 제거 + 갱신 판단.

    - 유사도 ≥ SIMILARITY_THRESHOLD + content_fp 동일 → 완전 중복 → 스킵
    - 유사도 ≥ SIMILARITY_THRESHOLD + content_fp 다름 → 갱신 → is_update=True
    - 유사도 < SIMILARITY_THRESHOLD → 신규 → is_update=False
    """
    result = []
    sent_list = cache.get("sent", [])

    for event in events:
        prev = _find_similar(event, sent_list)
        cfp = _content_fingerprint(event)

        if prev is None:
            # 신규
            event["is_update"] = False
            result.append(event)
            logger.info(f"🆕 신규: {event.get('event', '')[:50]}")

        elif prev.get("content_fp") == cfp:
            # 유사 + severity 동일 → 완전 중복 스킵
            logger.info(f"⏭ 중복 스킵: {event.get('event', '')[:50]}")
            continue

        else:
            # 유사 + severity 상승한 경우만 갱신 발송
            prev_sev = prev.get("severity", 0)
            new_sev = event.get("severity", 0)
            if new_sev > prev_sev:
                event["is_update"] = True
                result.append(event)
                logger.info(
                    f"🔄 갱신 (severity 상승): {event.get('event', '')[:50]} "
                    f"({prev_sev} → {new_sev})"
                )
            else:
                # severity 동일하거나 낮아짐 → 스킵
                logger.info(f"⏭ 갱신 스킵 (severity 변화 없음 {prev_sev}→{new_sev}): {event.get('event', '')[:50]}")
                continue

    return result


def _update_cache(cache: dict, events: list[dict]):
    """
    전송 완료된 이벤트를 캐시에 추가.
    이미 유사한 항목이 캐시에 있으면 severity가 높은 쪽으로 업데이트 (중복 방지).
    """
    sent_list = cache.setdefault("sent", [])
    for event in events:
        new_entry = {
            "event": event.get("event", ""),
            "severity": event.get("severity", 0),
            "signal": event.get("signal", ""),
            "assets": sorted(event.get("affected_assets", [])),
            "source_url": event.get("source_url") or "",
            "content_fp": _content_fingerprint(event),
            "sent_at": datetime.now().isoformat(),
        }
        # 캐시 내 유사 항목 찾아서 severity 업데이트 (중복 저장 방지)
        merged = False
        for existing in sent_list:
            event_text = event.get("event", "")
            existing_text = existing.get("event", "")
            same_url = (
                bool(new_entry["source_url"])
                and new_entry["source_url"] == existing.get("source_url", "")
            )
            is_same = same_url or _is_same_event(event_text, existing_text)
            if is_same:
                # severity 높은 쪽으로 갱신
                if new_entry["severity"] > existing["severity"]:
                    existing.update(new_entry)
                merged = True
                break
        if not merged:
            sent_list.append(new_entry)


async def run_once():
    """1회 실행: 수집 → 분석 → 중복제거 → 신호 발송 → 로그 저장."""
    from analyzer import analyze
    from signal_generator import process_signals

    start = datetime.now(timezone.utc)
    logger.info(f"Kaven v{__version__} 실행 시작: {start.isoformat()}")
    
    # 1. 데이터 수집
    collected = await run_collectors()
    
    # 2. 분석
    logger.info("분석 엔진 실행 중...")
    events = await analyze(collected)
    logger.info(f"분석 완료: {len(events)}건 이벤트 감지")
    
    # 3. 중복 제거 (이미 전송한 이벤트 필터링)
    cache = _load_sent_cache()
    events_to_send = _deduplicate_events(events, cache)
    logger.info(f"중복 제거 후 발송 대상: {len(events_to_send)}건")
    
    # 4. 신호 발송
    if events_to_send:
        logger.info("신호 발송 중...")
        signal_result = await process_signals(events_to_send)
        logger.info(f"발송 결과: {signal_result}")
        # 전송 완료 이벤트 캐시 업데이트
        _update_cache(cache, events_to_send)
        _save_sent_cache(cache)
    else:
        signal_result = {"sent": 0, "logged": 0}
        logger.info("이상 이벤트 없음 또는 전부 중복 — 신호 발송 건너뜀")
    
    # 4. 로그 저장
    end = datetime.now(timezone.utc)
    log_entry = {
        "version": __version__,
        "run_id": start.strftime("%Y%m%d_%H%M%S"),
        "started_at": start.isoformat(),
        "ended_at": end.isoformat(),
        "duration_seconds": (end - start).total_seconds(),
        "collected_counts": {
            k: len(v) if isinstance(v, list) else 0
            for k, v in collected.items()
        },
        "events": events,
        "signal_result": signal_result,
    }
    
    log_file = LOG_DIR / f"kaven_{start.strftime('%Y%m%d')}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    logger.info(f"로그 저장: {log_file}")

    # Convex 클라우드에 저장 (Vercel 배포본용)
    if events:
        try:
            import urllib.request
            payload = json.dumps({
                "run_id": log_entry["run_id"],
                "started_at": log_entry["started_at"],
                "events": events,
                "signal_result": signal_result,
            }, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                "https://exciting-cod-257.convex.site/addMavenRun",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info(f"Convex 저장 완료: {resp.read().decode()}")
        except Exception as e:
            logger.warning(f"Convex 저장 실패 (로컬 로그는 유지): {e}")

    logger.info(f"Kaven 실행 완료: {(end - start).total_seconds():.1f}초 소요")
    
    return log_entry


async def run_watch(interval_minutes: int = 5):
    """감시 모드: interval 간격으로 반복 실행."""
    logger.info(f"Kaven 감시 모드 시작 (간격: {interval_minutes}분)")
    
    while True:
        try:
            await run_once()
        except Exception as e:
            logger.error(f"실행 오류: {e}", exc_info=True)
        
        logger.info(f"다음 실행까지 {interval_minutes}분 대기...")
        await asyncio.sleep(interval_minutes * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Kaven Smart System — 지정학 조기경보 + 투자 신호 시스템"
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="1회 실행")
    group.add_argument("--watch", action="store_true", help="5분 간격 감시 모드")
    
    parser.add_argument(
        "--interval", type=int, default=5,
        help="감시 모드 간격 (분, 기본 5)"
    )
    
    args = parser.parse_args()
    
    if args.once:
        asyncio.run(run_once())
    elif args.watch:
        asyncio.run(run_watch(args.interval))


if __name__ == "__main__":
    main()

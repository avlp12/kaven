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
import fcntl
import hashlib
import json
import logging
import os
import re as _re
import sys
import tempfile
from contextlib import contextmanager
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

# 로깅 설정 — KAVEN_LOG_DIR 환경변수 override 지원 (읽기/쓰기 동일 경로 보장)
from src.kaven.log_store import default_log_dir  # noqa: E402

LOG_DIR = default_log_dir()
LOG_DIR.mkdir(parents=True, exist_ok=True)

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
    region = event.get("region") or ""
    key = f"{event.get('severity', 0)}|{region}|{source_url}|{'/'.join(numeric_tokens)}"
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
            loaded = json.loads(cache_file.read_text())
            if isinstance(loaded, dict) and loaded.get("date") == today:
                data: dict = loaded
                data.setdefault("seen_inputs", {})
                data.setdefault("partial_deliveries", {})
                return data
        except Exception:
            pass
    return {"date": today, "sent": [], "seen_inputs": {}, "partial_deliveries": {}}


def _save_sent_cache(cache: dict):
    """Write atomically so an interrupted run cannot truncate the cache."""
    cache_file = LOG_DIR / "sent_cache.json"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cache, ensure_ascii=False)
    temp_path: str | None = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix=".sent_cache.", suffix=".tmp", dir=LOG_DIR)
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, cache_file)
        temp_path = None
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


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


def _upload_remote_if_enabled(log_entry: dict, events: list, signal_result: dict) -> None:
    """
    원격(Convex) 업로드 — 명시적 opt-in 시에만 수행.

    정책 (이슈 #7):
    - 기본 동작: 외부 전송 비활성화 (로컬 로그만 유지)
    - ``CONVEX_SITE_URL`` 환경변수가 설정된 경우에만 POST
    - 경로는 ``CONVEX_EVENT_PATH`` (기본 ``/addKavenRun``)
    - 하드코딩된 endpoint는 사용하지 않음
    - 원격 실패 시에도 로컬 로그는 이미 저장되어 있으므로 무관
    """
    if not events:
        return

    site_url = os.environ.get("CONVEX_SITE_URL", "").strip()
    if not site_url:
        logger.info(
            "CONVEX_SITE_URL 미설정 — 외부 전송 스킵 (로컬 로그만 보존)"
        )
        return

    event_path = os.environ.get("CONVEX_EVENT_PATH", "/addKavenRun").strip()
    if not event_path.startswith("/"):
        event_path = "/" + event_path
    endpoint = site_url.rstrip("/") + event_path

    try:
        import urllib.request
        payload = json.dumps({
            "run_id": log_entry["run_id"],
            "started_at": log_entry["started_at"],
            "events": events,
            "signal_result": signal_result,
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info(f"Convex 저장 완료: {resp.read().decode()}")
    except Exception as e:
        logger.warning(f"Convex 저장 실패 (로컬 로그는 유지): {e}")


def _trigger_signatures(collected: dict) -> set[str]:
    """
    LLM 분석을 새로 돌릴 가치가 있는 '자극 입력'의 시그니처 집합.

    - 뉴스: url (없으면 title) 단위 — 새 기사가 곧 새 자극
    - 소셜: X/Twitter status URL, 없으면 작성자+정규화 본문의 안정적 해시
    - AIS/ADSB: anomaly 있는 항목만, zone+anomaly+규모버킷 단위
      (지속되는 동일 이상은 같은 시그니처 → 반복 트리거 안 됨)
    정상 수치(anomaly 없음)는 자극으로 보지 않는다.
    """
    sigs: set[str] = set()

    for item in collected.get("news", []):
        key = (item.get("url") or "").strip() or (item.get("title") or "").strip()
        if key:
            sigs.add(f"news:{key}")

    for item in collected.get("social", []):
        url = str(item.get("url") or "").strip()
        status_match = _re.search(
            r"https?://(?:www\.)?(?:x|twitter)\.com/[^/?#\s]+/status/(\d+)",
            url,
            flags=_re.IGNORECASE,
        )
        tweet_id = str(item.get("tweet_id") or "").strip()
        if status_match:
            sigs.add(f"social:url:x.com/status/{status_match.group(1)}")
        elif tweet_id:
            sigs.add(f"social:url:x.com/status/{tweet_id}")
        else:
            text = " ".join(str(item.get("text") or "").casefold().split())
            author = " ".join(str(item.get("author") or "").casefold().split())
            if text:
                digest = hashlib.sha256(f"{author}|{text}".encode("utf-8")).hexdigest()
                sigs.add(f"social:hash:{digest}")

    for item in collected.get("ais", []):
        if item.get("anomaly"):
            zone = item.get("zone", item.get("zone_name", "?"))
            bucket = int((item.get("ship_count") or 0) // 10)
            sigs.add(f"ais:{zone}:{item['anomaly']}:{bucket}")

    for item in collected.get("adsb", []):
        if item.get("anomaly"):
            zone = item.get("zone", item.get("zone_name", "?"))
            bucket = int((item.get("military_count") or 0) // 10)
            sigs.add(f"adsb:{zone}:{item['anomaly']}:{bucket}")

    return sigs


def _new_trigger_signatures(collected: dict, cache: dict) -> set[str]:
    """이번 수집에서 '처음 보는' 자극 시그니처만 반환."""
    seen = cache.get("seen_inputs", {})
    return {s for s in _trigger_signatures(collected) if s not in seen}


def _record_seen_inputs(cache: dict, signatures: set[str]):
    """처리한 자극 시그니처를 캐시에 기록 (다음 사이클부터 재트리거 방지)."""
    seen = cache.setdefault("seen_inputs", {})
    now = datetime.now().isoformat()
    for s in signatures:
        seen[s] = now


def _analysis_events(result) -> tuple[list[dict], bool]:
    """Legacy lists and optional analyzer status envelopes를 안전하게 통합한다."""
    if isinstance(result, list):
        return (result, all(isinstance(event, dict) for event in result))
    if not isinstance(result, dict):
        return ([], False)

    events = result.get("events")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        return ([], False)

    status = str(result.get("status", "")).casefold()
    if status == "partial":
        return (events, False)
    if status and status not in {"ok", "success", "completed", "empty"}:
        return ([], False)
    if not status and result.get("valid") is not True:
        return ([], False)
    return (events, True)


def _delivery_key(event: dict) -> str:
    """채널별 전송 진행을 재실행 사이에 연결하는 안정적 이벤트 키."""
    payload = "|".join([
        str(event.get("event", "")),
        str(event.get("severity", "")),
        str(event.get("region", "")),
        str(event.get("source_url", "")),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _apply_delivery_progress(events: list[dict], cache: dict) -> list[dict]:
    """이전 주기에 성공한 채널을 이벤트에 부착해 중복 전송을 막는다."""
    ledger = cache.get("partial_deliveries", {})
    if not isinstance(ledger, dict):
        return events
    for event in events:
        entry = ledger.get(_delivery_key(event), [])
        channels = entry.get("sent_channels", []) if isinstance(entry, dict) else entry
        if isinstance(channels, list):
            event["_delivered_channels"] = [
                channel for channel in channels if channel in {"topic", "dm"}
            ]
    return events


def _pending_delivery_events(cache: dict) -> list[dict]:
    """재분석하지 않고 실패 채널만 재시도할 원본 이벤트를 복원한다."""
    ledger = cache.get("partial_deliveries", {})
    if not isinstance(ledger, dict):
        return []
    pending: list[dict] = []
    for entry in ledger.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("event"), dict):
            continue
        event = dict(entry["event"])
        channels = entry.get("sent_channels", [])
        event["_delivered_channels"] = [
            channel for channel in channels if channel in {"topic", "dm"}
        ] if isinstance(channels, list) else []
        input_signatures = entry.get("input_signatures", [])
        event["_input_signatures"] = [
            signature for signature in input_signatures if isinstance(signature, str)
        ] if isinstance(input_signatures, list) else []
        pending.append(event)
    return pending


def _record_delivery_progress(
    cache: dict,
    events: list[dict],
    signal_result: dict,
    input_signatures: set[str] | None = None,
) -> None:
    """미완료 이벤트의 성공 채널만 저장하고 완료된 항목은 정리한다."""
    ledger = cache.setdefault("partial_deliveries", {})
    event_results = signal_result.get("event_results", [])
    if not isinstance(ledger, dict) or not isinstance(event_results, list):
        return
    for item in event_results:
        if not isinstance(item, dict) or not isinstance(item.get("index"), int):
            continue
        index = item["index"]
        if not 0 <= index < len(events):
            continue
        key = _delivery_key(events[index])
        if item.get("delivery_complete") is True:
            ledger.pop(key, None)
            continue
        channels = item.get("sent_channels", [])
        if isinstance(channels, list):
            delivered = [channel for channel in channels if channel in {"topic", "dm"}]
            if delivered:
                stored_event = {
                    key_name: value
                    for key_name, value in events[index].items()
                    if not key_name.startswith("_")
                }
                ledger[key] = {
                    "event": stored_event,
                    "sent_channels": delivered,
                    "input_signatures": sorted(
                        input_signatures
                        or {
                            signature
                            for signature in events[index].get("_input_signatures", [])
                            if isinstance(signature, str)
                        }
                    ),
                }


def _successfully_processed_events(events: list[dict], signal_result: dict) -> tuple[list[dict], bool]:
    """실제로 필요한 채널 발송을 마친 이벤트와 전체 성공 여부를 반환한다."""
    event_results = signal_result.get("event_results")
    if isinstance(event_results, list):
        completed_indices = {
            item.get("index")
            for item in event_results
            if isinstance(item, dict) and item.get("delivery_complete") is True
        }
        successful = [event for index, event in enumerate(events) if index in completed_indices]
        return successful, len(successful) == len(events)

    # 구형/custom generator 호환. 오류가 있으면 alert별 성공을 특정할 수 없으므로
    # 텔레그램이 필요 없는 log-only 이벤트만 캐시한다.
    if signal_result.get("errors"):
        successful = [event for event in events if event.get("severity", 1) < 3]
        return successful, len(successful) == len(events)
    return events, True


class RunAlreadyInProgress(RuntimeError):
    """다른 watcher/API 프로세스가 이미 수집 주기를 실행 중임."""


@contextmanager
def _run_lock():
    """run_once 전체 read-modify-write 구간을 프로세스 간 직렬화한다."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOG_DIR / "run.lock"
    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RunAlreadyInProgress("Kaven run already in progress") from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


async def _run_once_unlocked():
    """1회 실행: 수집 → 분석 → 중복제거 → 신호 발송 → 로그 저장."""
    import analyzer as analyzer_module
    from signal_generator import process_signals

    analyze_fn = getattr(analyzer_module, "analyze_with_status", analyzer_module.analyze)

    start = datetime.now(timezone.utc)
    logger.info(f"Kaven v{__version__} 실행 시작: {start.isoformat()}")

    # 1. 데이터 수집
    collected = await run_collectors()

    # 2. 입력 게이팅 — 새 자극(신규 뉴스/이상)이 없으면 LLM 분석 자체를 스킵
    cache = _load_sent_cache()
    new_sigs = _new_trigger_signatures(collected, cache)
    analysis_completed = False
    pending_events = _pending_delivery_events(cache)
    if pending_events:
        logger.info(f"미완료 채널 전송 {len(pending_events)}건 우선 재시도")
        new_sigs = set()
        events = pending_events
        events_to_send = pending_events
    elif not new_sigs:
        logger.info("신규 입력 없음 — LLM 분석/발송 건너뜀 (동일 자극 반복 방지)")
        events = []
        events_to_send = []
    else:
        logger.info(f"신규 자극 {len(new_sigs)}건 — 분석 엔진 실행 중...")
        try:
            analysis_result = await analyze_fn(collected)
        except Exception as e:
            logger.error(f"분석 실패 — 입력을 재시도 대상으로 유지: {e}")
            analysis_result = None
        events, analysis_completed = _analysis_events(analysis_result)
        if analysis_completed:
            logger.info(f"분석 완료: {len(events)}건 이벤트 감지")
        else:
            logger.error("분석 결과가 유효하지 않음 — 입력을 재시도 대상으로 유지")

        # 3. 중복 제거 (이미 전송한 이벤트 필터링)
        events_to_send = _deduplicate_events(events, cache) if events else []
        events_to_send = _apply_delivery_progress(events_to_send, cache)
        logger.info(f"중복 제거 후 발송 대상: {len(events_to_send)}건")

    # 4. 신호 발송
    if events_to_send:
        logger.info("신호 발송 중...")
        signal_result = await process_signals(events_to_send)
        logger.info(f"발송 결과: {signal_result}")
        _record_delivery_progress(cache, events_to_send, signal_result, new_sigs)
        sent_events, delivery_completed = _successfully_processed_events(events_to_send, signal_result)
        _update_cache(cache, sent_events)
        if delivery_completed:
            completed_input_signatures = {
                signature
                for event in sent_events
                for signature in event.get("_input_signatures", [])
                if isinstance(signature, str)
            }
            if completed_input_signatures:
                _record_seen_inputs(cache, completed_input_signatures)
        analysis_completed = analysis_completed and delivery_completed
    else:
        signal_result = {"sent": 0, "logged": 0}
        logger.info("이상 이벤트 없음 또는 전부 중복 — 신호 발송 건너뜀")

    # 분석과 필요한 전송이 모두 정상 완료된 입력만 소비한다.
    if analysis_completed:
        _record_seen_inputs(cache, new_sigs)
    _save_sent_cache(cache)

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

    # 원격(Convex) 백업 — opt-in (CONVEX_SITE_URL 설정 시에만)
    _upload_remote_if_enabled(log_entry, events, signal_result)

    logger.info(f"Kaven 실행 완료: {(end - start).total_seconds():.1f}초 소요")

    return log_entry


async def run_once():
    """단일 수집 주기를 프로세스 간 lock 아래에서 실행한다."""
    with _run_lock():
        return await _run_once_unlocked()


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

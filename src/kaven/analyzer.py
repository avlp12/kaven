"""
Kaven Analyzer — 수집 데이터 통합 분석 (LLM API)

OpenClaw 게이트웨이(localhost:18789) 또는 직접 Anthropic API 호출.
지정학 이벤트 분석 → 투자 신호 생성.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

logger = logging.getLogger("kaven.analyzer")

ANALYSIS_SYSTEM_PROMPT = """당신은 지정학 위험 분석가이자 투자 전략가입니다.
수집된 다중 데이터 소스(AIS 선박 추적, ADS-B 항공기 추적, 뉴스, X 소셜 데이터)를 종합 분석하여
지정학 이벤트가 한국 투자자에게 미치는 영향을 평가합니다.

분석 원칙:
1. 단일 소스의 이상보다 다중 소스 교차 확인된 이상을 높은 severity로 평가
2. 에너지 공급 경로(호르무즈·말라카) 위협은 한국 경제 직접 영향
3. 반도체 관련 지정학(대만·미중 갈등)은 삼성전자·SK하이닉스 직접 연관
4. 한반도 직접 위협은 최고 severity
5. 시뮬레이션 데이터는 명시하고, 실제 데이터 기반 분석과 구분

중복 방지 원칙 (필수):
6. 동일한 실제 사건(같은 국가·같은 수치·같은 날 발생)은 반드시 하나의 이벤트로만 출력
7. 소스가 여러 개여도 같은 사건을 다루면 합쳐서 하나로 출력
8. event 문장은 핵심 고유명사와 수치를 포함하여 매번 동일하게 작성 (표현 변주 금지)
   예) "파키스탄 연료 가격 20% 인상" → 매번 이 문장 그대로 유지"""

ANALYSIS_USER_PROMPT = """다음 수집 데이터를 분석하고, 각 의미 있는 이벤트에 대해 JSON 배열로 출력하세요.
이상 징후가 없으면 빈 배열 []을 반환하세요.

수집 데이터:
{collected_data}

각 이벤트의 JSON 스키마:
{{
    "event": "이벤트 한 줄 요약 (반드시 한국어로 작성)",
    "severity": 1-5,
    "category": "energy|semiconductor|currency|conflict|other",
    "affected_assets": ["삼성전자", "SK하이닉스", "WTI", "KOSPI", "원/달러" 등],
    "signal": "buy|sell|hedge|hold|watch",
    "confidence": 0.0-1.0,
    "reasoning": "분석 근거 2-3문장 (반드시 한국어로 작성)",
    "source_url": "이 이벤트의 메인 레퍼런스 URL 1개 (수집 데이터에서 가장 신뢰할 수 있는 원문 링크. 없으면 null)",
    "source_title": "출처 매체명 또는 제목 (예: Reuters, AP, BBC 등. 없으면 null)",
    "event_time": "이벤트 실제 발생·보도 시각 (수집 데이터의 published 필드 기준, ISO8601. 없으면 null)",
    "region": "hormuz|taiwan|korea|ukraine|india_pak|southcn|redsa|sahel|global|other (이벤트 발생 지역 코드. 이란/호르무즈=hormuz, 대만=taiwan, 한반도=korea, 우크라이나/러시아=ukraine, 인도/파키스탄=india_pak, 남중국해=southcn, 홍해/예멘=redsa, 사헬=sahel, 전지구=global)"
}}

중요:
- event, reasoning 필드는 반드시 한국어로 작성하세요. 영어 원문이 있더라도 한국어로 번역하여 작성.
- source_url은 수집 데이터에 실제 존재하는 URL만 사용하세요. 없으면 반드시 null로 기재.
- event_time은 수집 데이터의 published 값을 그대로 사용하세요. 없으면 null.

severity 기준:
1: 일상 변동, 관심 불필요
2: 경미한 이상, 모니터링 권장
3: 주의 필요, 시장 영향 가능
4: 경보, 즉각 대응 필요
5: 긴급, 직접적 시장 충격 예상

JSON 배열만 출력하세요. 추가 설명 없이 순수 JSON만."""


async def analyze(collected_data: dict[str, Any]) -> list[dict[str, Any]]:
    """수집된 데이터를 LLM API로 분석."""
    
    # 데이터 요약 (토큰 절약)
    summary = _summarize_data(collected_data)
    
    if not summary.strip():
        logger.info("분석할 데이터 없음")
        return []
    
    # OpenAI 호환 API(로컬 LLM 포함) 우선, Gemini/Anthropic 순으로 폴백
    openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    
    result = None
    if openai_base_url:
        try:
            result = await _call_openai_compatible(
                base_url=openai_base_url,
                api_key=openai_api_key,
                model=openai_model,
                summary=summary,
            )
        except Exception as e:
            logger.warning(f"OpenAI 호환 API 분석 실패: {e}")

    if result is None and gemini_key:
        try:
            result = await _call_gemini(gemini_key, summary)
        except Exception as e:
            logger.warning(f"Gemini API 분석 실패: {e}")
    
    if result is None and anthropic_key:
        try:
            result = await _call_anthropic_direct(anthropic_key, summary)
        except Exception as e:
            logger.error(f"Anthropic 직접 API 분석 실패: {e}")
    
    if result is None:
        logger.error("모든 분석 경로 실패")
        result = _fallback_analysis(collected_data)
    
    # 모든 이벤트에 collected_at 주입 (없는 경우 현재 시각)
    now_iso = datetime.now(timezone.utc).isoformat()

    # 뉴스 소스에서 가장 이른 published 시각 추출 (event_time fallback용)
    news_items = collected_data.get("news", [])
    earliest_pub = None
    for n in news_items:
        pub = n.get("published")
        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if earliest_pub is None or dt < earliest_pub:
                    earliest_pub = dt
            except Exception:
                pass

    for event in result:
        if not event.get("collected_at"):
            event["collected_at"] = event.get("timestamp") or now_iso
        # event_time: LLM이 채웠으면 그대로, 없으면 뉴스 published fallback
        if not event.get("event_time"):
            event["event_time"] = earliest_pub.isoformat() if earliest_pub else None

    return result


def _summarize_data(collected_data: dict[str, Any]) -> str:
    """수집 데이터를 분석용 텍스트로 요약 (토큰 절약)."""
    parts = []
    
    # AIS 데이터
    ais_data = collected_data.get("ais", [])
    if ais_data:
        parts.append("## 선박 AIS 데이터")
        for item in ais_data:
            zone = item.get("zone_name", item.get("zone", "unknown"))
            anomaly = item.get("anomaly")
            simulated = " (시뮬레이션)" if item.get("simulated") else ""
            parts.append(
                f"- {zone}{simulated}: 선박 {item.get('ship_count', '?')}척, "
                f"기준 {item.get('baseline', '?')}척, "
                f"비율 {item.get('ratio', '?')}, "
                f"정박 {item.get('stationary_count', '?')}척, "
                f"이상: {anomaly or '없음'}"
            )
    
    # ADS-B 데이터
    adsb_data = collected_data.get("adsb", [])
    if adsb_data:
        parts.append("\n## 항공기 ADS-B 데이터")
        for item in adsb_data:
            zone = item.get("zone_name", item.get("zone", "unknown"))
            status = item.get("status", "ok")
            if status in ("error", "rate_limited", "timeout"):
                parts.append(f"- {zone}: {status}")
            else:
                anomaly = item.get("anomaly")
                parts.append(
                    f"- {zone}: 전체 {item.get('total_aircraft', '?')}기, "
                    f"군용기 {item.get('military_count', '?')}기, "
                    f"이상: {anomaly or '없음'}"
                )
    
    # 뉴스 데이터
    news_data = collected_data.get("news", [])
    if news_data:
        parts.append(f"\n## 뉴스 ({len(news_data)}건)")
        for item in news_data[:15]:  # 최대 15건
            parts.append(
                f"- [{item.get('feed', 'unknown')}] {item.get('title', 'no title')}"
            )
            if item.get("summary"):
                parts.append(f"  요약: {item['summary'][:200]}")
    
    # 소셜 데이터
    social_data = collected_data.get("social", [])
    real_tweets = [s for s in social_data if s.get("text")]
    if real_tweets:
        # 고 engagement 순 정렬
        real_tweets.sort(key=lambda x: x.get("engagement", 0), reverse=True)
        parts.append(f"\n## X(Twitter) ({len(real_tweets)}건)")
        for item in real_tweets[:10]:  # 상위 10건
            parts.append(
                f"- [{item.get('search_keyword', '')}] "
                f"engagement:{item.get('engagement', 0)} — "
                f"{item.get('text', '')[:200]}"
            )
    
    return "\n".join(parts)


async def _call_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    summary: str,
) -> list[dict] | None:
    """OpenAI 호환 Chat Completions API 호출 (로컬 LLM 서버 포함)."""
    url = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": ANALYSIS_USER_PROMPT.format(collected_data=summary),
            },
        ],
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.warning(f"OpenAI 호환 API {resp.status}: {body[:200]}")
                return None
            data = await resp.json()

    choices = data.get("choices", [])
    if not choices:
        return None

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        text = "".join(
            c.get("text", "") for c in content if isinstance(c, dict)
        )
    else:
        text = str(content)

    return _parse_analysis_response(text)


async def _call_gemini(api_key: str, summary: str) -> list[dict] | None:
    """Google Gemini API 호출."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": f"{ANALYSIS_SYSTEM_PROMPT}\n\n{ANALYSIS_USER_PROMPT.format(collected_data=summary)}"}
                ],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 2000,
            "temperature": 0.2,
        },
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.warning(f"Gemini API {resp.status}: {body[:200]}")
                return None
            
            data = await resp.json()
    
    # Gemini 응답에서 텍스트 추출
    text = ""
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text += part.get("text", "")
    
    return _parse_analysis_response(text)


async def _call_openclaw_gateway(gateway_url: str, summary: str) -> list[dict] | None:
    """OpenClaw 게이트웨이의 Messages API 호출."""
    url = f"{gateway_url}/v1/messages"
    
    payload = {
        "model": "anthropic/claude-sonnet-4-6",
        "max_tokens": 2000,
        "system": ANALYSIS_SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": ANALYSIS_USER_PROMPT.format(collected_data=summary),
            }
        ],
    }
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": "openclaw",
        "anthropic-version": "2023-06-01",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.warning(f"OpenClaw gateway {resp.status}: {body[:200]}")
                return None
            
            data = await resp.json()
    
    # Claude 응답에서 텍스트 추출
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")
    
    return _parse_analysis_response(text)


async def _call_anthropic_direct(api_key: str, summary: str) -> list[dict] | None:
    """Anthropic API 직접 호출."""
    url = "https://api.anthropic.com/v1/messages"
    
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "system": ANALYSIS_SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": ANALYSIS_USER_PROMPT.format(collected_data=summary),
            }
        ],
    }
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.warning(f"Anthropic API {resp.status}: {body[:200]}")
                return None
            
            data = await resp.json()
    
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")
    
    return _parse_analysis_response(text)


def _parse_analysis_response(text: str) -> list[dict]:
    """Claude 응답 텍스트에서 JSON 배열 추출."""
    text = text.strip()
    
    # JSON 배열 직접 파싱 시도
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return _dedup_events(result)
        if isinstance(result, dict):
            return [result]
    except json.JSONDecodeError:
        pass
    
    # 코드블록 내 JSON 추출
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            try:
                result = json.loads(block)
                if isinstance(result, list):
                    return _dedup_events(result)
                if isinstance(result, dict):
                    return [result]
            except json.JSONDecodeError:
                continue
    
    # [ ... ] 패턴 찾기
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, list):
                return _dedup_events(result)
        except json.JSONDecodeError:
            pass
    
    logger.error(f"분석 응답 파싱 실패: {text[:200]}")
    return []


def _dedup_events(events: list[dict]) -> list[dict]:
    """동일 이벤트 중복 제거 — event 문자열 유사도 기반."""
    if not events:
        return events
    
    seen = []
    deduped = []
    
    for ev in events:
        event_text = ev.get("event", "").strip()
        if not event_text:
            continue
        
        # 이미 본 이벤트와 80% 이상 겹치면 중복으로 판단
        is_dup = False
        ev_words = set(event_text.lower().split())
        for seen_text in seen:
            seen_words = set(seen_text.lower().split())
            if not seen_words:
                continue
            overlap = len(ev_words & seen_words) / max(len(ev_words | seen_words), 1)
            if overlap >= 0.6:  # 60% 이상 단어 겹치면 중복
                is_dup = True
                logger.debug(f"중복 이벤트 제거: '{event_text[:50]}' ≈ '{seen_text[:50]}'")
                break
        
        if not is_dup:
            seen.append(event_text)
            deduped.append(ev)
    
    if len(deduped) < len(events):
        logger.info(f"중복 이벤트 {len(events) - len(deduped)}건 제거 ({len(events)}→{len(deduped)}건)")
    
    return deduped


def _fallback_analysis(collected_data: dict[str, Any]) -> list[dict[str, Any]]:
    """API 호출 실패 시 규칙 기반 분석 (폴백)."""
    events = []
    now = datetime.now(timezone.utc).isoformat()
    
    # AIS 이상 감지
    for item in collected_data.get("ais", []):
        if item.get("anomaly"):
            events.append({
                "event": f"선박 이상 감지: {item.get('zone_name', 'unknown')} — {item.get('anomaly')}",
                "severity": item.get("severity_hint", 2),
                "category": "energy",
                "affected_assets": ["WTI", "KOSPI"],
                "signal": "watch",
                "confidence": 0.3,
                "reasoning": f"규칙 기반 분석 (API 폴백). {item.get('detail', '')}",
                "timestamp": now,
                "fallback": True,
            })
    
    # ADS-B 이상 감지
    for item in collected_data.get("adsb", []):
        if item.get("anomaly"):
            category = "conflict"
            assets = ["KOSPI"]
            if "taiwan" in item.get("zone", ""):
                category = "semiconductor"
                assets = ["삼성전자", "SK하이닉스", "TSMC"]
            elif "korean" in item.get("zone", ""):
                assets = ["KOSPI", "원/달러", "삼성전자"]
            
            events.append({
                "event": f"군용기 이상 집결: {item.get('zone_name', 'unknown')}",
                "severity": item.get("severity_hint", 3),
                "category": category,
                "affected_assets": assets,
                "signal": "hedge",
                "confidence": 0.3,
                "reasoning": f"규칙 기반 분석 (API 폴백). {item.get('detail', '')}",
                "timestamp": now,
                "fallback": True,
            })
    
    # 뉴스 클러스터 감지
    news_data = collected_data.get("news", [])
    if len(news_data) >= 5:
        events.append({
            "event": f"지정학 뉴스 급증: {len(news_data)}건 수집",
            "severity": 2,
            "category": "other",
            "affected_assets": ["KOSPI"],
            "signal": "watch",
            "confidence": 0.2,
            "reasoning": f"규칙 기반 분석 (API 폴백). {len(news_data)}건의 지정학 뉴스 감지.",
            "timestamp": now,
            "fallback": True,
        })
    
    return events

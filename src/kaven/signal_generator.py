"""
Signal Generator — 지정학 이벤트 severity 기반 알림 발송

severity 1-2: 로그만 저장
severity 3+: 텔레그램 topic:5052 (Kaven 전용 채널) 알림 — 한국어
severity 5:  사용자님 개인 DM 즉시 알림

OpenClaw message API 우선 사용, 실패 시 Bot API 직접 호출.
"""

import logging
import os
from typing import Any

import aiohttp

from src.kaven.version import __version__

logger = logging.getLogger("kaven.signal")

# 텔레그램 설정
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-1003868141703")
TOPIC_MAVEN = int(os.getenv("TELEGRAM_TOPIC_MAVEN", "5052"))   # Kaven 전용 토픽
USER_DM = os.getenv("TELEGRAM_USER_DM", "40130797")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "http://localhost:18789")

# Severity 이모지
SEVERITY_EMOJI = {
    1: "⚪",
    2: "🔵",
    3: "🟡",
    4: "🟠",
    5: "🔴",
}

# Category 라벨
CATEGORY_LABEL = {
    "energy": "⛽ 에너지",
    "semiconductor": "🔬 반도체",
    "currency": "💱 환율",
    "conflict": "⚔️ 분쟁",
    "other": "📌 기타",
}

# Signal 라벨
SIGNAL_LABEL = {
    "buy": "📈 매수",
    "sell": "📉 매도",
    "hedge": "🛡 헤지",
    "hold": "✊ 홀드",
    "watch": "👀 관망",
}


async def process_signals(events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    분석된 이벤트 목록을 severity 기반으로 알림 발송.

    Returns:
        발송 결과 요약
    """
    if not events:
        logger.info("발송할 이벤트 없음")
        return {"sent": 0, "logged": 0}

    sent_count = 0
    logged_count = 0
    errors = []

    for event in events:
        severity = event.get("severity", 1)

        # 로그 저장 (모든 severity)
        logged_count += 1
        logger.info(
            f"이벤트 [{severity}]: {event.get('event', 'unknown')} "
            f"| {event.get('category', 'other')} "
            f"| {event.get('signal', 'watch')}"
        )

        # severity 3+: topic:5052 (Kaven 전용) 알림만
        if severity >= 3:
            try:
                msg = _format_message(event)
                await _send_telegram(msg, CHAT_ID, TOPIC_MAVEN)
                sent_count += 1
                logger.info(f"topic:5052 Kaven 알림 발송 완료 (severity {severity})")
            except Exception as e:
                logger.error(f"topic:5052 알림 실패: {e}")
                errors.append(str(e))

        # severity 5: 개인 DM (긴급만)
        if severity >= 5:
            try:
                msg = _format_urgent_message(event)
                await _send_telegram_dm(msg, USER_DM)
                sent_count += 1
                logger.info("🔴 긴급 DM 발송 완료")
            except Exception as e:
                logger.error(f"긴급 DM 실패: {e}")
                errors.append(str(e))

    return {
        "sent": sent_count,
        "logged": logged_count,
        "errors": errors if errors else None,
    }


def _format_message(event: dict) -> str:
    """topic:37 (Geopolitics) 알림 메시지 포맷."""
    severity = event.get("severity", 1)
    emoji = SEVERITY_EMOJI.get(severity, "⚪")
    category = CATEGORY_LABEL.get(event.get("category", "other"), "📌 기타")
    signal = SIGNAL_LABEL.get(event.get("signal", "watch"), "👀 관망")
    confidence = event.get("confidence", 0)

    lines = [
        f"{emoji} Kaven v{__version__} 지정학 경보 [Lv.{severity}/5]",
        "",
        f"📋 {event.get('event', '이벤트 정보 없음')}",
        f"📂 {category}",
        f"📊 {signal} (확신도: {confidence:.0%})",
    ]

    assets = event.get("affected_assets", [])
    if assets:
        lines.append(f"💼 영향 자산: {', '.join(assets)}")

    reasoning = event.get("reasoning", "")
    if reasoning:
        lines.append(f"\n💡 {reasoning}")

    if event.get("fallback"):
        lines.append("\n⚠️ 규칙 기반 분석 (API 폴백)")

    return "\n".join(lines)


def _format_investment_message(event: dict) -> str:
    """topic:2 (투자) 알림 메시지 포맷."""
    severity = event.get("severity", 1)
    emoji = SEVERITY_EMOJI.get(severity, "⚪")
    signal = SIGNAL_LABEL.get(event.get("signal", "watch"), "👀 관망")

    lines = [
        f"{emoji} Kaven v{__version__} 투자 신호 [Lv.{severity}/5]",
        "",
        f"🌐 {event.get('event', '')}",
        f"📊 {signal}",
    ]

    assets = event.get("affected_assets", [])
    if assets:
        lines.append(f"💼 영향: {', '.join(assets)}")

    reasoning = event.get("reasoning", "")
    if reasoning:
        lines.append(f"\n{reasoning}")

    return "\n".join(lines)


def _format_urgent_message(event: dict) -> str:
    """긴급 DM 메시지 포맷."""
    return (
        f"🚨🚨🚨 Kaven v{__version__} 긴급 경보\n\n"
        f"{event.get('event', '')}\n\n"
        f"신호: {event.get('signal', 'watch').upper()}\n"
        f"자산: {', '.join(event.get('affected_assets', []))}\n\n"
        f"{event.get('reasoning', '')}"
    )


async def _send_telegram(text: str, chat_id: str, thread_id: int):
    """텔레그램 메시지 발송 (Bot API 우선, OpenClaw gateway 폴백)."""
    # Bot API 직접 호출 (우선순위 1)
    if BOT_TOKEN:
        try:
            await _send_telegram_bot_api(text, chat_id, thread_id)
            return
        except Exception as e:
            logger.warning(f"Bot API 발송 실패: {e}")

    # OpenClaw gateway 폴백
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{GATEWAY_URL}/api/telegram/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "message_thread_id": thread_id,
                "parse_mode": "HTML",
            }
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return
                logger.warning(f"OpenClaw gateway 발송 실패: {resp.status}")
    except Exception as e:
        logger.warning(f"OpenClaw gateway 연결 실패: {e}")

    raise RuntimeError("No telegram delivery method available")


async def _send_telegram_bot_api(text: str, chat_id: str, thread_id: int | None = None):
    """Telegram Bot API 직접 호출."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "message_thread_id": thread_id,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Telegram Bot API 실패: {resp.status} — {body[:200]}")


async def _send_telegram_dm(text: str, user_id: str):
    """알리스님 개인 DM 발송."""
    if BOT_TOKEN:
        await _send_telegram_bot_api(text, user_id)
    else:
        # OpenClaw gateway로 DM 시도
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{GATEWAY_URL}/api/telegram/sendMessage"
                payload = {
                    "chat_id": user_id,
                    "text": text,
                }
                async with session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return
                    logger.warning(f"DM 발송 실패: {resp.status}")
        except Exception as e:
            logger.error(f"DM 발송 실패: {e}")
            raise

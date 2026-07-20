"""
ADS-B Collector — 항공기 ADS-B 데이터 수집 (OpenSky Network API)

군용기 ICAO hex 범위 필터링으로 중동·대만·한반도 상공 이상 집결 감지.

OpenSky Network: https://opensky-network.org — 무료 가입 가능.
비인증 요청도 가능하나 rate limit 더 제한적 (10초/1회).
인증 시 5초/1회.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from src.kaven.config_loader import get_adsb_zones

logger = logging.getLogger("kaven.adsb")


def _watch_airspaces() -> dict[str, dict[str, Any]]:
    """설정 로더로부터 활성화된 ADS-B 감시 공역을 dict로 변환."""
    zones: dict[str, dict[str, Any]] = {}
    for z in get_adsb_zones(only_enabled=True):
        zones[z["id"]] = {
            "name": z["name"],
            "lat_min": z["lat_min"], "lat_max": z["lat_max"],
            "lon_min": z["lon_min"], "lon_max": z["lon_max"],
        }
    return zones

# 군용으로 전용된 것으로 알려진 ICAO24 hex 범위.
# 국가 전체 할당 대역(A0-A9, 71-72, 73, 78-7A 등)은 민항기도 포함하므로
# 군용 판별 신호로 사용하지 않는다.
MILITARY_HEX_PREFIXES = {
    # 미국 군용 전용 AE 대역
    "us_mil": [("AE", "AE")],
}

OPENSKY_API_BASE = "https://opensky-network.org/api"


async def _get_opensky_bearer_token(session: aiohttp.ClientSession) -> str | None:
    """OpenSky OAuth2 client_credentials로 Bearer token 발급."""
    client_id = os.getenv("OPENSKY_CLIENT_ID", "").strip()
    client_secret = os.getenv("OPENSKY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None

    token_url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    try:
        async with session.post(token_url, data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                token_data = await resp.json()
                logger.info("OpenSky Bearer token 발급 완료")
                return token_data.get("access_token")
            else:
                body = await resp.text()
                logger.warning(f"OpenSky 토큰 발급 실패 {resp.status}: {body[:200]}")
    except Exception as e:
        logger.warning(f"OpenSky 토큰 발급 오류: {e}")
    return None


async def collect() -> list[dict[str, Any]]:
    """
    OpenSky Network API로 감시 공역의 항공기 데이터 수집 및 분석.
    OAuth2 client_credentials 인증 (Basic Auth 폐지됨).
    """
    results = []
    watch_airspaces = _watch_airspaces()
    if not watch_airspaces:
        logger.warning("ADS-B 감시 공역이 모두 비활성화됨 — 빈 결과 반환")
        return []

    async with aiohttp.ClientSession() as session:
        # OAuth2 Bearer token 발급
        bearer_token = await _get_opensky_bearer_token(session)
        headers = {}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        else:
            logger.info("OpenSky 인증 정보 미설정 — 비인증 모드 (rate limit 제한)")

        for zone_key, zone_def in watch_airspaces.items():
            try:
                zone_result = await _collect_zone(session, headers, zone_key, zone_def)
                results.append(zone_result)
                # rate limit 준수 (비인증: 10초, 인증: 5초)
                await asyncio.sleep(5 if bearer_token else 10)
            except Exception as e:
                logger.error(f"ADS-B {zone_def['name']} 수집 실패: {e}")
                results.append({
                    "source": "adsb",
                    "zone": zone_key,
                    "zone_name": zone_def["name"],
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

    return results


async def _collect_zone(
    session: aiohttp.ClientSession,
    headers: dict[str, str],
    zone_key: str,
    zone_def: dict,
) -> dict[str, Any]:
    """단일 감시 구역 데이터 수집."""
    url = f"{OPENSKY_API_BASE}/states/all"
    params = {
        "lamin": zone_def["lat_min"],
        "lamax": zone_def["lat_max"],
        "lomin": zone_def["lon_min"],
        "lomax": zone_def["lon_max"],
    }

    now = datetime.now(timezone.utc).isoformat()

    try:
        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 429:
                logger.warning(f"OpenSky rate limit 초과 ({zone_def['name']})")
                return {
                    "source": "adsb",
                    "zone": zone_key,
                    "zone_name": zone_def["name"],
                    "status": "rate_limited",
                    "timestamp": now,
                }

            if resp.status != 200:
                return {
                    "source": "adsb",
                    "zone": zone_key,
                    "zone_name": zone_def["name"],
                    "status": "error",
                    "error": f"HTTP {resp.status}",
                    "timestamp": now,
                }

            data = await resp.json()
    except asyncio.TimeoutError:
        return {
            "source": "adsb",
            "zone": zone_key,
            "zone_name": zone_def["name"],
            "status": "timeout",
            "timestamp": now,
        }

    states = data.get("states", []) or []

    # 전체 항공기 수
    total_aircraft = len(states)

    # 군용기 필터링
    military_aircraft = []
    for state in states:
        icao24 = (state[0] or "").strip().upper()
        callsign = (state[1] or "").strip()
        if _is_military_aircraft(icao24, callsign):
            military_aircraft.append({
                "icao24": icao24,
                "callsign": callsign,
                "origin_country": state[2],
                "lat": state[6],
                "lon": state[5],
                "altitude": state[7],  # baro altitude
                "velocity": state[9],
                "on_ground": state[8],
            })

    # 이상 감지: 군용기 수 임계값
    mil_count = len(military_aircraft)
    anomaly = None

    # 군용기 5대 이상이면 주의, 10대 이상이면 경보
    if mil_count >= 10:
        anomaly = "military_surge"
    elif mil_count >= 5:
        anomaly = "military_elevated"

    result = {
        "source": "adsb",
        "zone": zone_key,
        "zone_name": zone_def["name"],
        "total_aircraft": total_aircraft,
        "military_count": mil_count,
        "military_aircraft": military_aircraft[:20],  # 최대 20대 상세
        "anomaly": anomaly,
        "timestamp": now,
    }

    if anomaly:
        result["severity_hint"] = 4 if anomaly == "military_surge" else 3
        result["detail"] = (
            f"{zone_def['name']}: 전체 {total_aircraft}기 중 군용기 {mil_count}기 감지"
        )
        logger.warning(f"ADS-B 이상 감지: {result['detail']}")

    return result


def _is_military_hex(icao24: str) -> bool:
    """ICAO24 hex 코드가 군용 전용 범위인지 판별."""
    icao24 = icao24.strip().upper()
    if len(icao24) < 2:
        return False

    prefix = icao24[:2]

    for _country, ranges in MILITARY_HEX_PREFIXES.items():
        for range_start, range_end in ranges:
            if range_start <= prefix <= range_end:
                return True

    return False


def _is_military_aircraft(icao24: str, callsign: str) -> bool:
    """군용 전용 hex 또는 알려진 군용 콜사인 보조 신호로 판별."""
    return _is_military_hex(icao24) or _is_military_callsign(callsign)


def _is_military_callsign(callsign: str) -> bool:
    """콜사인으로 군용기 판별 (보조 수단)."""
    mil_prefixes = [
        "RCH", "REACH",  # US Air Mobility Command
        "DUKE", "EVIL",   # US Fighter
        "FORTE",          # Global Hawk
        "JAKE",           # US Navy
        "CNV", "NAVY",    # US Navy
        "BAF", "GAF",     # Belgian/German AF
        "RRR",            # UK RAF
        "IAF",            # Israeli AF
        "KAF",            # Korean AF
    ]
    callsign_upper = callsign.upper()
    return any(callsign_upper.startswith(p) for p in mil_prefixes)

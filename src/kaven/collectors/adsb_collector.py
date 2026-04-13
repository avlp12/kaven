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

logger = logging.getLogger("kaven.adsb")

# 감시 공역 정의 (bounding box: lat_min, lat_max, lon_min, lon_max)
WATCH_AIRSPACES = {
    "middle_east": {
        "name": "중동 (이란·이라크·걸프)",
        "lat_min": 24.0, "lat_max": 38.0,
        "lon_min": 44.0, "lon_max": 62.0,
    },
    "taiwan_strait": {
        "name": "대만 해협",
        "lat_min": 22.0, "lat_max": 27.0,
        "lon_min": 117.0, "lon_max": 122.0,
    },
    "korean_peninsula": {
        "name": "한반도",
        "lat_min": 33.0, "lat_max": 43.0,
        "lon_min": 124.0, "lon_max": 132.0,
    },
}

# 군용기 ICAO24 hex 범위 (주요 국가)
# 참고: https://en.wikipedia.org/wiki/List_of_aircraft_registration_prefixes
MILITARY_HEX_PREFIXES = {
    # 미국 군용 (AE, AF 범위 일부)
    "us_mil": [("AE", "AF"), ("A0", "A9")],
    # 한국 군용
    "kr_mil": [("71", "72")],
    # 중국 군용
    "cn_mil": [("78", "7A")],
    # 이란 군용
    "ir_mil": [("73", "73")],
}

OPENSKY_API_BASE = "https://opensky-network.org/api"


async def collect() -> list[dict[str, Any]]:
    """
    OpenSky Network API로 감시 공역의 항공기 데이터 수집 및 분석.
    """
    username = os.getenv("OPENSKY_USERNAME", "").strip()
    password = os.getenv("OPENSKY_PASSWORD", "").strip()

    auth = None
    if username and password:
        auth = aiohttp.BasicAuth(username, password)
    else:
        logger.info("OpenSky 인증 정보 미설정 — 비인증 모드 (rate limit 제한)")

    results = []

    async with aiohttp.ClientSession() as session:
        for zone_key, zone_def in WATCH_AIRSPACES.items():
            try:
                zone_result = await _collect_zone(session, auth, zone_key, zone_def)
                results.append(zone_result)
                # rate limit 준수 (비인증: 10초, 인증: 5초)
                await asyncio.sleep(5 if auth else 10)
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
    auth: aiohttp.BasicAuth | None,
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
        async with session.get(url, params=params, auth=auth, timeout=aiohttp.ClientTimeout(total=30)) as resp:
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
        if _is_military_hex(icao24):
            military_aircraft.append({
                "icao24": icao24,
                "callsign": (state[1] or "").strip(),
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
    """ICAO24 hex 코드가 군용기 범위인지 판별."""
    if len(icao24) < 2:
        return False

    prefix = icao24[:2]

    for _country, ranges in MILITARY_HEX_PREFIXES.items():
        for range_start, range_end in ranges:
            if range_start <= prefix <= range_end:
                return True

    # 추가 휴리스틱: 콜사인에 군용 패턴
    return False


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

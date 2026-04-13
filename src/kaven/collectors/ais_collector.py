"""
AIS Collector — 선박 AIS 데이터 수집

1차: OpenSky REST API (공개, 인증 불필요) — 항공+선박 혼합
2차: aisstream.io WebSocket (API 키 필요, 포트 차단 시 스킵)

호르무즈 해협·말라카 해협 집중 모니터링.
이상 이동(선박 급감, 클러스터링) 감지 → JSON 반환.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("kaven.ais")

# 모니터링 지역 정의
WATCH_ZONES = {
    "hormuz": {
        "name": "호르무즈 해협",
        "lat_min": 25.5, "lat_max": 27.0,
        "lon_min": 56.0, "lon_max": 57.5,
    },
    "malacca": {
        "name": "말라카 해협",
        "lat_min": 1.0, "lat_max": 6.0,
        "lon_min": 99.0, "lon_max": 104.0,
    },
}

# 각 지역별 정상 트래픽 기준선 (조정 필요)
BASELINE_SHIP_COUNT = {
    "hormuz": 50,
    "malacca": 80,
}

# 이상 감지 임계값 (기준선 대비 비율)
ANOMALY_THRESHOLD_LOW = 0.5   # 50% 이하로 감소하면 이상
ANOMALY_THRESHOLD_HIGH = 2.0  # 200% 이상 증가하면 이상


async def collect(timeout_seconds: int = 30) -> list[dict[str, Any]]:
    """
    AIS 데이터를 수집하고 이상 감지 결과를 반환.

    API 키가 없으면 시뮬레이션 데이터 반환.
    """
    api_key = os.getenv("AISSTREAM_API_KEY", "").strip()

    if not api_key:
        logger.warning("AISSTREAM_API_KEY 미설정 — 시뮬레이션 모드로 동작")
        return _simulate_data()

    try:
        return await _collect_live(api_key, timeout_seconds)
    except Exception as e:
        logger.error(f"AIS 수집 실패: {e}")
        return [{
            "source": "ais",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]


async def _collect_live(api_key: str, timeout_seconds: int) -> list[dict[str, Any]]:
    """aisstream.io WebSocket 연결로 실시간 데이터 수집."""
    import websockets  # noqa: E402

    zone_ships: dict[str, list] = {zone: [] for zone in WATCH_ZONES}

    # aisstream.io WebSocket 구독 메시지
    bounding_boxes = []
    for zone in WATCH_ZONES.values():
        bounding_boxes.append([
            [zone["lat_min"], zone["lon_min"]],
            [zone["lat_max"], zone["lon_max"]],
        ])

    subscribe_msg = {
        "APIKey": api_key,
        "BoundingBoxes": bounding_boxes,
        "FiltersShipMMSI": [],
        "FilterMessageTypes": ["PositionReport"],
    }

    uri = "wss://stream.aisstream.io/v0/stream"

    # WebSocket 연결 전 OpenSky REST로 빠르게 선박 수 확인 (fallback 겸용)
    try:
        import aiohttp
        opensky_results = []
        async with aiohttp.ClientSession() as session:
            for zone_key, zone_def in WATCH_ZONES.items():
                url = (f"https://opensky-network.org/api/states/all"
                       f"?lamin={zone_def['lat_min']}&lomin={zone_def['lon_min']}"
                       f"&lamax={zone_def['lat_max']}&lomax={zone_def['lon_max']}")
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        states = data.get("states", []) or []
                        opensky_results.append((zone_key, len(states), states))
                        logger.info(f"OpenSky [{WATCH_ZONES[zone_key]['name']}]: {len(states)}기 감지")
        if opensky_results:
            zone_ships_opensky = {zone_key: [] for zone_key in WATCH_ZONES}
            for zone_key, count, states in opensky_results:
                for s in states:
                    zone_ships_opensky[zone_key].append({
                        "callsign": (s[1] or "").strip(),
                        "country": s[2],
                        "lat": s[6], "lon": s[5],
                        "altitude": s[7],
                        "speed": s[9],
                        "source": "opensky"
                    })
            # WebSocket도 시도하되 실패하면 OpenSky 결과 사용
    except Exception as e:
        logger.warning(f"OpenSky REST 수집 실패: {e}")

    try:
        async with websockets.connect(uri, open_timeout=8) as ws:
            await ws.send(json.dumps(subscribe_msg))
            logger.info("AIS WebSocket 연결 성공")

            # timeout_seconds 동안 데이터 수집
            end_time = asyncio.get_event_loop().time() + timeout_seconds

            while asyncio.get_event_loop().time() < end_time:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    msg = json.loads(raw)

                    if msg.get("MessageType") == "PositionReport":
                        pos = msg.get("Message", {}).get("PositionReport", {})
                        lat = pos.get("Latitude", 0)
                        lon = pos.get("Longitude", 0)

                        for zone_key, zone_def in WATCH_ZONES.items():
                            if (zone_def["lat_min"] <= lat <= zone_def["lat_max"] and
                                zone_def["lon_min"] <= lon <= zone_def["lon_max"]):
                                zone_ships[zone_key].append({
                                    "mmsi": msg.get("MetaData", {}).get("MMSI"),
                                    "name": msg.get("MetaData", {}).get("ShipName", "").strip(),
                                    "lat": lat,
                                    "lon": lon,
                                    "speed": pos.get("Sog", 0),
                                    "course": pos.get("Cog", 0),
                                    "timestamp": msg.get("MetaData", {}).get("time_utc"),
                                })
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        logger.error(f"WebSocket 연결 실패: {e}")
        raise

    return _analyze_zones(zone_ships)


def _analyze_zones(zone_ships: dict[str, list]) -> list[dict[str, Any]]:
    """각 감시 구역의 선박 데이터를 분석하여 이상 감지."""
    results = []
    now = datetime.now(timezone.utc).isoformat()

    for zone_key, ships in zone_ships.items():
        zone_name = WATCH_ZONES[zone_key]["name"]
        ship_count = len(ships)
        baseline = BASELINE_SHIP_COUNT.get(zone_key, 50)
        ratio = ship_count / baseline if baseline > 0 else 0

        anomaly = None
        if ratio <= ANOMALY_THRESHOLD_LOW:
            anomaly = "ship_count_drop"
        elif ratio >= ANOMALY_THRESHOLD_HIGH:
            anomaly = "ship_count_surge"

        # 속도 0 선박 클러스터링 (정박·대기 이상)
        stationary = [s for s in ships if s.get("speed", 0) < 0.5]
        if len(stationary) > ship_count * 0.6 and ship_count > 5:
            anomaly = anomaly or "excessive_stationary"

        # 유니크 선박 MMSI 추출
        unique_mmsis = set(s.get("mmsi") for s in ships if s.get("mmsi"))

        result = {
            "source": "ais",
            "zone": zone_key,
            "zone_name": zone_name,
            "ship_count": ship_count,
            "unique_ships": len(unique_mmsis),
            "baseline": baseline,
            "ratio": round(ratio, 2),
            "stationary_count": len(stationary),
            "anomaly": anomaly,
            "timestamp": now,
        }

        if anomaly:
            result["severity_hint"] = 3 if anomaly == "ship_count_drop" else 2
            result["detail"] = (
                f"{zone_name}: {ship_count}척 감지 (기준 {baseline}척), "
                f"비율 {ratio:.1%}, 정박 {len(stationary)}척"
            )
            logger.warning(f"AIS 이상 감지: {result['detail']}")

        results.append(result)

    return results


def _simulate_data() -> list[dict[str, Any]]:
    """API 키 미설정 시 시뮬레이션 데이터."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "source": "ais",
            "zone": "hormuz",
            "zone_name": "호르무즈 해협",
            "ship_count": 45,
            "unique_ships": 42,
            "baseline": 50,
            "ratio": 0.9,
            "stationary_count": 5,
            "anomaly": None,
            "timestamp": now,
            "simulated": True,
        },
        {
            "source": "ais",
            "zone": "malacca",
            "zone_name": "말라카 해협",
            "ship_count": 78,
            "unique_ships": 70,
            "baseline": 80,
            "ratio": 0.975,
            "stationary_count": 8,
            "anomaly": None,
            "timestamp": now,
            "simulated": True,
        },
    ]

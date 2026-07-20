"""
AIS Collector — 선박 AIS 데이터 수집

aisstream.io WebSocket을 통해 선박 PositionReport를 수집한다.
OpenSky 항공기 데이터는 AIS 대체 데이터로 사용하지 않는다.

호르무즈 해협·말라카 해협 집중 모니터링.
이상 이동(선박 급감, 클러스터링) 감지 → JSON 반환.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from src.kaven.config_loader import get_ais_zones

logger = logging.getLogger("kaven.ais")


def _watch_zones() -> dict[str, dict[str, Any]]:
    """설정 로더로부터 활성화된 AIS 감시 구역을 dict로 변환 (런타임 로드)."""
    zones: dict[str, dict[str, Any]] = {}
    for z in get_ais_zones(only_enabled=True):
        zones[z["id"]] = {
            "name": z["name"],
            "lat_min": z["lat_min"], "lat_max": z["lat_max"],
            "lon_min": z["lon_min"], "lon_max": z["lon_max"],
            "baseline_ships": z.get("baseline_ships", 50),
        }
    return zones

# 이상 감지 임계값 (기준선 대비 비율)
ANOMALY_THRESHOLD_LOW = 0.5   # 50% 이하로 감소하면 이상
ANOMALY_THRESHOLD_HIGH = 2.0  # 200% 이상 증가하면 이상


async def collect(timeout_seconds: int = 30) -> list[dict[str, Any]]:
    """
    AIS 데이터를 수집하고 이상 감지 결과를 반환.

    시뮬레이션은 KAVEN_SIMULATION_MODE=true로 명시한 경우에만 사용.
    """
    api_key = os.getenv("AISSTREAM_API_KEY", "").strip()

    if os.getenv("KAVEN_SIMULATION_MODE", "").strip().lower() == "true":
        logger.warning("KAVEN_SIMULATION_MODE=true — AIS 시뮬레이션 모드로 동작")
        return _simulate_data()

    if not api_key:
        logger.error("AISSTREAM_API_KEY 미설정 — 실시간 AIS 수집 불가")
        return [{
            "source": "ais",
            "status": "unavailable",
            "error": "missing_credentials",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]

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

    watch_zones = _watch_zones()
    if not watch_zones:
        logger.warning("AIS 감시 구역이 모두 비활성화됨 — 빈 결과 반환")
        return []

    zone_ships: dict[str, list] = {zone: [] for zone in watch_zones}

    # aisstream.io WebSocket 구독 메시지
    bounding_boxes = []
    for zone in watch_zones.values():
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

                        for zone_key, zone_def in watch_zones.items():
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

    return _analyze_zones(zone_ships, watch_zones)


def _deduplicate_ships(ships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """MMSI별 마지막 PositionReport만 남긴다.

    MMSI가 없는 보고는 선박을 식별할 수 없으므로 집계에서 제외한다.
    """
    by_mmsi: dict[str, dict[str, Any]] = {}
    for ship in ships:
        mmsi = ship.get("mmsi")
        if mmsi is not None and str(mmsi).strip() and str(mmsi).strip() != "0":
            by_mmsi[str(mmsi).strip()] = ship
    return list(by_mmsi.values())


def _analyze_zones(zone_ships: dict[str, list], watch_zones: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """각 감시 구역의 선박 데이터를 분석하여 이상 감지."""
    results = []
    now = datetime.now(timezone.utc).isoformat()

    for zone_key, ships in zone_ships.items():
        zone_name = watch_zones[zone_key]["name"]
        unique_ships = _deduplicate_ships(ships)
        ship_count = len(unique_ships)
        baseline = watch_zones[zone_key].get("baseline_ships", 50)
        ratio = ship_count / baseline if baseline > 0 else 0

        anomaly = None
        if ratio <= ANOMALY_THRESHOLD_LOW:
            anomaly = "ship_count_drop"
        elif ratio >= ANOMALY_THRESHOLD_HIGH:
            anomaly = "ship_count_surge"

        # 속도 0 선박 클러스터링 (정박·대기 이상)
        stationary = [s for s in unique_ships if s.get("speed", 0) < 0.5]
        if len(stationary) > ship_count * 0.6 and ship_count > 5:
            anomaly = anomaly or "excessive_stationary"

        result = {
            "source": "ais",
            "zone": zone_key,
            "zone_name": zone_name,
            "ship_count": ship_count,
            "unique_ships": ship_count,
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
    """명시적 시뮬레이션 모드용 데이터. 활성화된 zone에 대해서만 생성."""
    now = datetime.now(timezone.utc).isoformat()
    watch_zones = _watch_zones()
    results = []
    for zone_key, zone in watch_zones.items():
        baseline = zone.get("baseline_ships", 50)
        # 기준선의 85~95% 정도의 "정상" 값을 시뮬레이션
        sim_count = int(baseline * 0.9)
        results.append({
            "source": "ais",
            "zone": zone_key,
            "zone_name": zone["name"],
            "ship_count": sim_count,
            "unique_ships": int(sim_count * 0.93),
            "baseline": baseline,
            "ratio": round(sim_count / baseline if baseline else 0, 3),
            "stationary_count": int(sim_count * 0.1),
            "anomaly": None,
            "timestamp": now,
            "simulated": True,
        })
    return results

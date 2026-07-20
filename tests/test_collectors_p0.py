"""AIS/ADS-B P0 정확성 결함 회귀 테스트."""

from __future__ import annotations

import asyncio

from src.kaven.collectors import adsb_collector, ais_collector


def test_ais_repeated_position_reports_count_one_unique_ship():
    """동일 MMSI의 반복 위치 보고는 선박 수를 부풀리지 않는다."""
    zones = {
        "test": {
            "name": "테스트 해역",
            "baseline_ships": 1,
        },
    }
    reports = {
        "test": [
            {"mmsi": 440123456, "speed": 0.1, "timestamp": "2026-07-20T00:00:00Z"},
            {"mmsi": 440123456, "speed": 12.0, "timestamp": "2026-07-20T00:01:00Z"},
        ],
    }

    result = ais_collector._analyze_zones(reports, zones)[0]

    assert result["ship_count"] == 1
    assert result["unique_ships"] == 1
    # 동일 선박의 최신 위치 보고가 이동 중이므로 정박 선박이 아니다.
    assert result["stationary_count"] == 0


def test_adsb_country_allocations_are_not_intrinsically_military():
    """국가 ICAO 할당 대역만으로 민항기를 군용으로 확정하지 않는다."""
    civil_regression_corpus = [
        "A01234",  # 미국 A0-A9 민간 등록 포함
        "A91234",
        "710123",  # 대한민국 71-72 민간 등록 포함
        "72ABCD",
        "780123",  # 중국 78-7A 민간 등록 포함
        "7A1234",
        "730123",  # 이란 국가 할당 대역
    ]

    assert all(not adsb_collector._is_military_hex(icao24) for icao24 in civil_regression_corpus)


def test_adsb_callsign_is_used_as_auxiliary_military_signal():
    """광범위 국가 대역은 단독 신호가 아니지만 군용 콜사인은 보조 신호가 된다."""
    assert not adsb_collector._is_military_aircraft("A01234", "UAL123")
    assert adsb_collector._is_military_aircraft("A01234", "RCH123")
    assert adsb_collector._is_military_aircraft("AE1234", "")


def test_ais_missing_credentials_is_not_reported_as_normal_simulated_observation(monkeypatch):
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    monkeypatch.delenv("KAVEN_SIMULATION_MODE", raising=False)

    result = asyncio.run(ais_collector.collect())

    assert len(result) == 1
    assert result[0]["source"] == "ais"
    assert result[0]["status"] == "unavailable"
    assert result[0]["error"] == "missing_credentials"
    assert not result[0].get("simulated", False)


def test_ais_simulation_requires_explicit_true(monkeypatch):
    monkeypatch.delenv("AISSTREAM_API_KEY", raising=False)
    monkeypatch.setenv("KAVEN_SIMULATION_MODE", "true")
    monkeypatch.setattr(ais_collector, "_simulate_data", lambda: [{"source": "ais", "simulated": True}])

    assert asyncio.run(ais_collector.collect()) == [{"source": "ais", "simulated": True}]

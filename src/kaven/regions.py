"""
Kaven Region Registry — 감시 지역 메타데이터 단일 소스(single source of truth).

기존에 webapp(app.py/ops.py)과 report_generator에 흩어져 있던
지역 좌표/한글명/설명을 한곳에서 관리한다.
"""

from __future__ import annotations

from typing import Any

# 지역 코드 → 좌표 + 이름/설명 (한국어 기본 + 영어 병기: 콘솔 언어 전환용)
REGION_INFO: dict[str, dict[str, Any]] = {
    "hormuz": {"lat": 26.5, "lng": 56.3,
               "name": "호르무즈 해협", "name_en": "Strait of Hormuz",
               "description": ("세계 원유 해상 운송의 약 20%가 통과하는 전략적 요충지. "
                               "한국 원유 수입의 70%가 이 해역을 경유."),
               "description_en": ("Chokepoint for ~20% of global seaborne oil; "
                                  "~70% of Korea's crude imports transit here.")},
    "taiwan": {"lat": 23.7, "lng": 121.0,
               "name": "대만 해협", "name_en": "Taiwan Strait",
               "description": "글로벌 반도체 공급망의 핵심 지역. 대만 TSMC는 세계 파운드리의 60% 점유.",
               "description_en": ("Core of the global semiconductor supply chain; "
                                  "TSMC holds ~60% of world foundry capacity.")},
    "korea": {"lat": 37.5, "lng": 127.0,
              "name": "한반도", "name_en": "Korean Peninsula",
              "description": "KOSPI, 원/달러 환율에 직접적 영향을 미치는 최고 우선순위 감시 지역.",
              "description_en": "Top-priority watch area with direct impact on KOSPI and USD/KRW."},
    "ukraine": {"lat": 48.4, "lng": 31.2,
                "name": "우크라이나", "name_en": "Ukraine",
                "description": "유럽 에너지·곡물 공급에 영향. 러시아-우크라이나 분쟁 장기화.",
                "description_en": ("Affects European energy and grain supply; "
                                   "prolonged Russia-Ukraine war.")},
    "india_pak": {"lat": 30.0, "lng": 70.0,
                  "name": "인도·파키스탄", "name_en": "India-Pakistan",
                  "description": "남아시아 핵 보유국 간 긴장. 에너지·무역 경로 교란 가능성.",
                  "description_en": ("Tension between South Asian nuclear powers; "
                                     "potential disruption of energy and trade routes.")},
    "southcn": {"lat": 14.0, "lng": 114.0,
                "name": "남중국해", "name_en": "South China Sea",
                "description": "세계 해상 무역의 30%가 통과. 미중 해양 패권 경쟁의 핵심 지역.",
                "description_en": ("~30% of global maritime trade transits here; "
                                   "focal point of US-China naval rivalry.")},
    "redsa": {"lat": 14.0, "lng": 42.0,
              "name": "홍해·예멘", "name_en": "Red Sea / Yemen",
              "description": "수에즈 운하 접근 해역. 후티 반군의 선박 공격으로 국제 물류 차질.",
              "description_en": ("Approach to the Suez Canal; Houthi attacks on "
                                 "shipping disrupt global logistics.")},
    "sahel": {"lat": 15.0, "lng": 0.0,
              "name": "사헬", "name_en": "Sahel",
              "description": "서아프리카 지정학 불안정 지역. 에너지·광물 공급망 영향.",
              "description_en": ("Geopolitical instability in West Africa; "
                                 "energy and minerals supply impact.")},
    "global": {"lat": 0, "lng": 0,
               "name": "전지구", "name_en": "Global",
               "description": "특정 지역에 국한되지 않는 글로벌 이벤트.",
               "description_en": "Events not tied to a single region."},
}

# 이벤트 스키마 어휘 — 에이전트 매니페스트/문서용
SEVERITY_LEVELS: dict[int, str] = {
    1: "일상", 2: "모니터링", 3: "주의", 4: "경보", 5: "긴급",
}
CATEGORIES: list[str] = ["energy", "semiconductor", "currency", "conflict", "other"]
SIGNALS: list[str] = ["buy", "sell", "hedge", "hold", "watch"]


def region_info(include_disabled: bool = False) -> dict[str, dict[str, Any]]:
    """
    감시 지역 메타 로드 — config.json `regions` 섹션 우선, 없으면 내장 기본값.

    Args:
        include_disabled: True면 enabled=false 지역도 포함
                          (이벤트의 지역명 lookup 등 표시 목적).
    """
    from src.kaven.config_loader import load_config  # 지연 import (모듈 순환 방지)

    items = load_config().get("regions", [])
    out: dict[str, dict[str, Any]] = {}
    for r in items:
        code = str(r.get("code", "")).strip()
        if not code:
            continue
        if not include_disabled and not r.get("enabled", True):
            continue
        out[code] = r
    return out if out else dict(REGION_INFO)


def region_name(code: str) -> str:
    """지역 코드의 한글명. 미등록 코드는 코드 그대로 반환."""
    if code == "other":
        return "기타"
    return str(region_info(include_disabled=True).get(code, {}).get("name", code))

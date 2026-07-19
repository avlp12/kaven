"""
Kaven Region Registry — 감시 지역 메타데이터 단일 소스(single source of truth).

기존에 webapp(app.py/ops.py)과 report_generator에 흩어져 있던
지역 좌표/한글명/설명을 한곳에서 관리한다.
"""

from __future__ import annotations

from typing import Any

# 지역 코드 → 좌표 + 이름 + 설명
REGION_INFO: dict[str, dict[str, Any]] = {
    "hormuz": {"lat": 26.5, "lng": 56.3, "name": "호르무즈 해협",
               "description": ("세계 원유 해상 운송의 약 20%가 통과하는 전략적 요충지. "
                               "한국 원유 수입의 70%가 이 해역을 경유.")},
    "taiwan": {"lat": 23.7, "lng": 121.0, "name": "대만 해협",
               "description": "글로벌 반도체 공급망의 핵심 지역. 대만 TSMC는 세계 파운드리의 60% 점유."},
    "korea": {"lat": 37.5, "lng": 127.0, "name": "한반도",
              "description": "KOSPI, 원/달러 환율에 직접적 영향을 미치는 최고 우선순위 감시 지역."},
    "ukraine": {"lat": 48.4, "lng": 31.2, "name": "우크라이나",
                "description": "유럽 에너지·곡물 공급에 영향. 러시아-우크라이나 분쟁 장기화."},
    "india_pak": {"lat": 30.0, "lng": 70.0, "name": "인도·파키스탄",
                  "description": "남아시아 핵 보유국 간 긴장. 에너지·무역 경로 교란 가능성."},
    "southcn": {"lat": 14.0, "lng": 114.0, "name": "남중국해",
                "description": "세계 해상 무역의 30%가 통과. 미중 해양 패권 경쟁의 핵심 지역."},
    "redsa": {"lat": 14.0, "lng": 42.0, "name": "홍해·예멘",
              "description": "수에즈 운하 접근 해역. 후티 반군의 선박 공격으로 국제 물류 차질."},
    "sahel": {"lat": 15.0, "lng": 0.0, "name": "사헬",
              "description": "서아프리카 지정학 불안정 지역. 에너지·광물 공급망 영향."},
    "global": {"lat": 0, "lng": 0, "name": "전지구",
               "description": "특정 지역에 국한되지 않는 글로벌 이벤트."},
}

# 이벤트 스키마 어휘 — 에이전트 매니페스트/문서용
SEVERITY_LEVELS: dict[int, str] = {
    1: "일상", 2: "모니터링", 3: "주의", 4: "경보", 5: "긴급",
}
CATEGORIES: list[str] = ["energy", "semiconductor", "currency", "conflict", "other"]
SIGNALS: list[str] = ["buy", "sell", "hedge", "hold", "watch"]


def region_name(code: str) -> str:
    """지역 코드의 한글명. 미등록 코드는 코드 그대로 반환."""
    if code == "other":
        return "기타"
    return REGION_INFO.get(code, {}).get("name", code)

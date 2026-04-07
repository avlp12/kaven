"""Maven dedup 단위 테스트."""

import sys, os, types

# maven.py가 `from collectors import ...` 등 로컬 임포트를 사용하므로
# src/maven을 sys.path에 추가하고, 무거운 collector 의존성을 스텁으로 대체
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "maven"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# collector/analyzer/signal_generator가 필요 없는 dedup 테스트이므로 스텁 주입
for mod_name in ("feedparser",):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

from src.maven.maven import (
    _normalize,
    _canonical_tokens,
    _core_keywords,
    _keyword_overlap,
    _jaccard_similarity,
    _entity_overlap,
    _find_similar,
    _deduplicate_events,
    _update_cache,
    _content_fingerprint,
    SIMILARITY_THRESHOLD,
)


# ── 소수점 수치 처리 ──────────────────────────────────────────


def test_keyword_overlap_supports_decimal_numbers():
    """소수점(예: 2.5%)을 하나의 토큰으로 인식해야 한다."""
    a = "파키스탄 연료 가격 2.5% 인상"
    b = "파키스탄 연료 가격 2.5% 인상 발표"

    # 2.5%가 하나의 토큰으로 추출되는지 확인
    kw_a = _core_keywords(a)
    kw_b = _core_keywords(b)
    assert "2.5%" in kw_a, f"2.5% not in {kw_a}"
    assert "2.5%" in kw_b, f"2.5% not in {kw_b}"

    # 소수점 수치가 일치하므로 keyword_overlap > 0
    assert _keyword_overlap(a, b) > 0


def test_decimal_not_split_into_two_tokens():
    """2.5를 '2'와 '5'로 분리하면 안 된다."""
    kw = _core_keywords("이란 원유 수출 2.5% 감소")
    # '2'와 '5'가 별도 토큰이 아닌 '2.5%'가 하나로 잡혀야 함
    assert "2.5%" in kw
    assert "2" not in kw or "2.5%" in kw  # 2가 있더라도 2.5%가 있어야 함


def test_normalize_preserves_decimal():
    """_normalize도 소수점을 하나의 토큰으로 처리해야 한다."""
    tokens = _normalize("원유 가격 3.7% 상승")
    assert any("3.7" in t for t in tokens), f"3.7 not found in {tokens}"


# ── source_url 동일 시 동일 이벤트 판정 ──────────────────────


def test_find_similar_matches_by_source_url():
    """source_url이 같으면 텍스트 무관하게 동일 이벤트로 판정."""
    event = {"event": "completely different text", "source_url": "https://example.com/article1"}
    sent_list = [
        {"event": "전혀 다른 한국어 이벤트", "source_url": "https://example.com/article1", "severity": 3},
    ]
    result = _find_similar(event, sent_list)
    assert result is not None


def test_find_similar_no_match_different_url():
    """source_url이 다르고 텍스트도 다르면 매칭되지 않아야 한다."""
    event = {"event": "파키스탄 이벤트", "source_url": "https://a.com/1"}
    sent_list = [
        {"event": "이란 이벤트", "source_url": "https://b.com/2", "severity": 2},
    ]
    result = _find_similar(event, sent_list)
    assert result is None


# ── _update_cache: source_url 동일 병합 ─────────────────────


def test_update_cache_merges_by_same_source_url():
    """캐시 업데이트 시 source_url이 같으면 중복 추가 대신 병합해야 한다."""
    cache = {"date": "2026-04-07", "sent": [
        {
            "event": "이란 호르무즈 해협 긴장 고조",
            "severity": 3,
            "signal": "hedge",
            "assets": ["WTI"],
            "source_url": "https://reuters.com/hormuz-1",
            "content_fp": "abc",
            "sent_at": "2026-04-07T00:00:00",
        }
    ]}

    # 같은 source_url, 더 높은 severity → 기존 항목이 갱신되어야 함
    new_events = [{
        "event": "이란 호르무즈 긴장 고조 (업데이트)",
        "severity": 4,
        "signal": "sell",
        "affected_assets": ["WTI", "KOSPI"],
        "source_url": "https://reuters.com/hormuz-1",
    }]
    _update_cache(cache, new_events)

    # 항목이 1개로 유지되어야 하고 severity가 갱신되어야 함
    assert len(cache["sent"]) == 1, f"Expected 1 entry, got {len(cache['sent'])}"
    assert cache["sent"][0]["severity"] == 4


def test_update_cache_adds_new_when_url_differs():
    """source_url이 다르고 유사하지 않으면 새 항목으로 추가."""
    cache = {"date": "2026-04-07", "sent": [
        {
            "event": "이란 호르무즈 해협 긴장 고조",
            "severity": 3,
            "signal": "hedge",
            "assets": ["WTI"],
            "source_url": "https://reuters.com/hormuz-1",
            "content_fp": "abc",
            "sent_at": "2026-04-07T00:00:00",
        }
    ]}

    new_events = [{
        "event": "대만 해협 중국 군사훈련 강화",
        "severity": 3,
        "affected_assets": ["삼성전자"],
        "source_url": "https://bbc.com/taiwan-1",
    }]
    _update_cache(cache, new_events)

    assert len(cache["sent"]) == 2


# ── Jaccard / entity / keyword 유사도 기본 동작 ──────────────


def test_jaccard_identical():
    assert _jaccard_similarity("이란 호르무즈 해협 긴장", "이란 호르무즈 해협 긴장") == 1.0


def test_jaccard_disjoint():
    assert _jaccard_similarity("이란 호르무즈", "대만 반도체 수출") < 0.3


def test_entity_overlap_ko_en():
    """한영 혼용에서 같은 지명이면 엔티티 겹침 감지."""
    assert _entity_overlap("이란 핵 협상", "Iran nuclear talks") >= 1.0


def test_keyword_overlap_no_shared_number():
    """수치 공통이 없으면 keyword_overlap은 0."""
    assert _keyword_overlap("이란 핵 10건", "이란 핵 20건") == 0.0


def test_keyword_overlap_shared_number():
    """같은 수치 + 지명이면 overlap > 0."""
    assert _keyword_overlap("이란 10% 관세", "이란 10% 관세 발표") > 0


# ── _deduplicate_events ─────────────────────────────────────


def test_deduplicate_skips_identical_content_fp():
    """content_fp 동일(severity 동일)이면 완전 중복 → 스킵."""
    cache = {"date": "2026-04-07", "sent": [
        {"event": "호르무즈 해협 선박 통행량 급감", "severity": 3, "content_fp": _content_fingerprint({"severity": 3}), "source_url": ""},
    ]}
    events = [{"event": "호르무즈 해협 선박 통행량 급감", "severity": 3}]
    result = _deduplicate_events(events, cache)
    assert len(result) == 0


def test_deduplicate_passes_severity_upgrade():
    """severity 상승 시 갱신으로 통과."""
    cache = {"date": "2026-04-07", "sent": [
        {"event": "호르무즈 해협 선박 통행량 급감", "severity": 3, "content_fp": _content_fingerprint({"severity": 3}), "source_url": ""},
    ]}
    events = [{"event": "호르무즈 해협 선박 통행량 급감", "severity": 4}]
    result = _deduplicate_events(events, cache)
    assert len(result) == 1
    assert result[0]["is_update"] is True


def test_deduplicate_new_event():
    """완전히 새로운 이벤트는 신규로 통과."""
    cache = {"date": "2026-04-07", "sent": []}
    events = [{"event": "대만 반도체 수출 규제", "severity": 3}]
    result = _deduplicate_events(events, cache)
    assert len(result) == 1
    assert result[0]["is_update"] is False

from __future__ import annotations

import sys
import types

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))
sys.modules.setdefault(
    "collectors",
    types.SimpleNamespace(
        ais_collector=types.SimpleNamespace(collect=None),
        adsb_collector=types.SimpleNamespace(collect=None),
        news_collector=types.SimpleNamespace(collect=None),
        social_collector=types.SimpleNamespace(collect=None),
    ),
)
sys.modules.setdefault("analyzer", types.SimpleNamespace(analyze=None))
sys.modules.setdefault("signal_generator", types.SimpleNamespace(process_signals=None))

from src.kaven import kaven


def test_keyword_overlap_supports_decimal_numbers() -> None:
    a = "파키스탄 연료 가격 2.5% 인상"
    b = "파키스탄 연료 가격 2.5% 급등"
    assert kaven._keyword_overlap(a, b) > 0


def test_normalize_keeps_decimal_numeric_token() -> None:
    text = "파키스탄 연료 가격 2.5% 인상"
    tokens = kaven._normalize(text)
    assert "2.5%" in tokens


def test_update_cache_merges_by_same_source_url() -> None:
    cache = {
        "date": "2026-04-07",
        "sent": [
            {
                "event": "중동 긴장 고조",
                "severity": 3,
                "signal": "watch",
                "assets": ["WTI"],
                "source_url": "https://example.com/news/1",
                "content_fp": "old",
                "sent_at": "2026-04-07T00:00:00",
            }
        ],
    }
    new_events = [
        {
            "event": "호르무즈 해협 봉쇄 우려 확산",
            "severity": 4,
            "signal": "hedge",
            "affected_assets": ["WTI", "원/달러"],
            "source_url": "https://example.com/news/1",
        }
    ]

    kaven._update_cache(cache, new_events)

    assert len(cache["sent"]) == 1
    assert cache["sent"][0]["severity"] == 4


def test_content_fingerprint_uses_numeric_and_source_context() -> None:
    base = {
        "severity": 4,
        "event": "파키스탄 연료 가격 2.5% 인상",
        "source_url": "https://example.com/news/1",
    }
    different_number = {
        "severity": 4,
        "event": "파키스탄 연료 가격 3.5% 인상",
        "source_url": "https://example.com/news/1",
    }
    different_source = {
        "severity": 4,
        "event": "파키스탄 연료 가격 2.5% 인상",
        "source_url": "https://example.com/news/2",
    }

    fp_base = kaven._content_fingerprint(base)
    assert fp_base != kaven._content_fingerprint(different_number)
    assert fp_base != kaven._content_fingerprint(different_source)

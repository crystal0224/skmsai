#!/usr/bin/env python3
"""lib/policy.py 단위 테스트 (PR-4).

Usage:
    python tests/test_policy.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts/ is on sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from lib.policy import apply_policy_layer, load_policy_config  # noqa: E402


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def test_load_policy_config_default():
    """설정 파일 없을 때 기본값 반환."""
    config = load_policy_config("nonexistent/path.yaml")
    assert "latest_first" in config
    assert "general_definition" in config["latest_first"]["forced_intents"]
    assert config["latest_first"]["primary_edition"] == "2020-14차"
    assert config["latest_first"]["min_hits"] == 2
    print("  PASS: load_policy_config default")


def test_load_policy_config_from_file():
    """config/policy.yaml 정상 로드."""
    config = load_policy_config("config/policy.yaml")
    assert "latest_first" in config
    assert "evolution" in config
    assert "specific_time" in config
    print("  PASS: load_policy_config from file")


# ---------------------------------------------------------------------------
# apply_policy_layer tests
# ---------------------------------------------------------------------------

_BASE_POLICY = {
    "edition_hint": None,
    "edition_filter": None,
    "type_filter": None,
    "section_filter": None,
    "alpha": 0.6,
    "rrf_k": 60,
    "score_threshold": 0.5,
    "vec_top_k": 10,
    "bm25_top_k": 10,
    "latest_first": False,
}


def _get_config():
    return load_policy_config("config/policy.yaml")


def test_general_definition_forces_latest_first():
    """general_definition → latest_first=True 강제."""
    config = _get_config()
    result = apply_policy_layer("general_definition", _BASE_POLICY, config)
    assert result["latest_first"] is True
    assert result["edition_filter"] == "2020-14차"
    assert "_policy_fallback_editions" in result
    assert "_policy_min_hits" in result
    print("  PASS: general_definition forces latest_first")


def test_open_ended_forces_latest_first():
    """open_ended → latest_first=True 강제."""
    config = _get_config()
    result = apply_policy_layer("open_ended", _BASE_POLICY, config)
    assert result["latest_first"] is True
    assert result["edition_filter"] == "2020-14차"
    print("  PASS: open_ended forces latest_first")


def test_content_generation_forces_latest_first():
    """content_generation → latest_first=True 강제."""
    config = _get_config()
    result = apply_policy_layer("content_generation", _BASE_POLICY, config)
    assert result["latest_first"] is True
    assert result["edition_filter"] == "2020-14차"
    print("  PASS: content_generation forces latest_first")


def test_evolution_comparison_no_latest_first():
    """evolution_comparison → latest_first=False, edition_filter=None."""
    config = _get_config()
    result = apply_policy_layer("evolution_comparison", _BASE_POLICY, config)
    assert result["latest_first"] is False
    assert result["edition_filter"] is None
    print("  PASS: evolution_comparison no latest_first")


def test_specific_time_unchanged():
    """specific_time → 변경 없음."""
    config = _get_config()
    base = {**_BASE_POLICY, "edition_hint": "10차"}
    result = apply_policy_layer("specific_time", base, config)
    assert result["latest_first"] is False
    assert result["edition_hint"] == "10차"
    print("  PASS: specific_time unchanged")


def test_immutability():
    """apply_policy_layer가 원본 policy를 변경하지 않는지 확인."""
    config = _get_config()
    original = dict(_BASE_POLICY)
    apply_policy_layer("general_definition", _BASE_POLICY, config)
    assert _BASE_POLICY == original, "Original policy was mutated!"
    print("  PASS: immutability")


def test_deep_immutability():
    """apply_policy_layer가 중첩 리스트도 변경하지 않는지 확인."""
    config = _get_config()
    base = {**_BASE_POLICY, "type_filter": ["definition"]}
    original_filter = base["type_filter"].copy()
    result = apply_policy_layer("general_definition", base, config)
    # result 수정이 원본에 영향을 주지 않아야 함
    if result.get("type_filter"):
        result["type_filter"].append("narrative")
    assert base["type_filter"] == original_filter, "Nested list was mutated!"
    print("  PASS: deep immutability")


def test_fallback_editions_not_shared():
    """폴백 목록이 config 객체와 분리되어 있는지 확인."""
    config = _get_config()
    result = apply_policy_layer("general_definition", _BASE_POLICY, config)
    fallbacks = result["_policy_fallback_editions"]
    fallbacks.append("test-edition")
    # config의 원본 목록이 변경되지 않아야 함
    result2 = apply_policy_layer("general_definition", _BASE_POLICY, config)
    assert "test-edition" not in result2["_policy_fallback_editions"]
    print("  PASS: fallback editions not shared")


def test_existing_edition_filter_preserved():
    """이미 edition_filter가 설정되어 있으면 덮어쓰지 않음."""
    config = _get_config()
    base = {**_BASE_POLICY, "edition_filter": "1998-10차"}
    result = apply_policy_layer("general_definition", base, config)
    assert result["latest_first"] is True
    assert result["edition_filter"] == "1998-10차"  # 기존 값 유지
    print("  PASS: existing edition_filter preserved")


def test_fallback_editions_list():
    """폴백 개정판 목록이 올바른지 확인."""
    config = _get_config()
    result = apply_policy_layer("general_definition", _BASE_POLICY, config)
    fallbacks = result["_policy_fallback_editions"]
    assert "2016-13차" in fallbacks
    assert "2008-12차" in fallbacks
    assert result["_policy_min_hits"] == 2
    print("  PASS: fallback editions list")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("[PR-4] lib/policy.py 단위 테스트")
    print("=" * 50)

    tests = [
        test_load_policy_config_default,
        test_load_policy_config_from_file,
        test_general_definition_forces_latest_first,
        test_open_ended_forces_latest_first,
        test_content_generation_forces_latest_first,
        test_evolution_comparison_no_latest_first,
        test_specific_time_unchanged,
        test_immutability,
        test_deep_immutability,
        test_fallback_editions_not_shared,
        test_existing_edition_filter_preserved,
        test_fallback_editions_list,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"결과: {passed} PASS, {failed} FAIL / {len(tests)} total")

    if failed > 0:
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()

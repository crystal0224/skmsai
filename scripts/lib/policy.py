"""검색 정책 레이어 (PR-4).

intent에 따라 latest_first 강제, 개정판 폴백 캐스케이드,
연대순 정렬 등을 결정한다.

config/policy.yaml 설정에 기반하며, 설정 파일 없으면 기본값 사용.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 기본 설정 (policy.yaml 없을 때)
# ---------------------------------------------------------------------------

_DEFAULT_POLICY: dict[str, Any] = {
    "latest_first": {
        "forced_intents": [
            "general_definition",
            "open_ended",
            "content_generation",
        ],
        "primary_edition": "2020-14차",
        "min_hits": 2,
        "fallback_editions": ["2016-13차", "2008-12차"],
    },
    "evolution": {
        "forced_intents": ["evolution_comparison"],
        "sort_order": "chronological",
    },
    "specific_time": {
        "forced_intents": ["specific_time"],
    },
}


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def load_policy_config(
    path: str = "config/policy.yaml",
) -> dict[str, Any]:
    """정책 설정을 로드한다. 파일 없으면 기본값 반환."""
    config_path = Path(path)
    if config_path.exists():
        try:
            import yaml

            with open(config_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            return raw.get("policy", copy.deepcopy(_DEFAULT_POLICY))
        except ImportError:
            pass
        except Exception as e:
            print(
                f"[policy] 경고: {path} 로드 실패 ({e}), 기본값 사용",
                file=sys.stderr,
            )
    return copy.deepcopy(_DEFAULT_POLICY)


# ---------------------------------------------------------------------------
# Policy application
# ---------------------------------------------------------------------------


def apply_policy_layer(
    intent: str,
    policy: dict,
    policy_config: dict[str, Any],
) -> dict:
    """intent에 따라 정책 dict를 보강하여 새 dict를 반환한다.

    원본 policy를 변경하지 않고 새 dict를 만든다 (immutability).

    적용 규칙:
      1. latest_first.forced_intents에 해당하면:
         - latest_first=True 강제
         - edition_filter를 primary_edition으로 설정
         - fallback_editions 정보를 policy에 포함
      2. evolution.forced_intents에 해당하면:
         - latest_first=False
         - edition_filter=None (전 판본)
      3. specific_time:
         - edition_hint 기반 필터 유지 (변경 없음)

    Returns:
        새 policy dict (latest_first, edition_filter 등이 보강된 상태)
    """
    result = copy.deepcopy(policy)

    latest_cfg = policy_config.get("latest_first", {})
    evolution_cfg = policy_config.get("evolution", {})

    # latest_first 강제 적용
    if intent in latest_cfg.get("forced_intents", []):
        result["latest_first"] = True
        # edition_filter가 아직 설정되지 않았으면 primary_edition으로 설정
        if not result.get("edition_filter"):
            result["edition_filter"] = latest_cfg.get("primary_edition", "2020-14차")
        result["_policy_fallback_editions"] = list(
            latest_cfg.get("fallback_editions", [])
        )
        result["_policy_min_hits"] = max(latest_cfg.get("min_hits", 2), 0)
        return result

    # evolution 강제 적용
    if intent in evolution_cfg.get("forced_intents", []):
        result["latest_first"] = False
        # 전 판본 검색
        result["edition_filter"] = None
        return result

    # specific_time 등: 변경 없음
    return result

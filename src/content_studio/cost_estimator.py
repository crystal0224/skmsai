"""CostEstimator — API 사용 비용 추정 및 가치 환산 모듈.

PR-072: 실시간 API 비용 계산 및 사용자 인지 강화.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelPrice:
    input_1k: float
    output_1k: float


# 2026년 기준 표준 단가 (USD)
PRICES = {
    "claude-3-5-sonnet": ModelPrice(0.003, 0.015),
    "gpt-4o": ModelPrice(0.0025, 0.010),
    "gpt-4o-mini": ModelPrice(0.00015, 0.0006),
    "dalle-3-hd": 0.04,  # 장당
    "tts-1-hd": 0.03,    # 1k characters
}


@dataclass
class CostReport:
    total_usd: float = 0.0
    details: dict[str, float] = field(default_factory=dict)

    def add_llm_cost(self, model: str, input_tokens: int, output_tokens: int):
        price = PRICES.get(model, PRICES["gpt-4o-mini"])
        cost = (input_tokens / 1000 * price.input_1k) + (output_tokens / 1000 * price.output_1k)
        self.total_usd += cost
        self.details[f"llm_{model}"] = self.details.get(f"llm_{model}", 0.0) + cost

    def add_asset_cost(self, asset_type: str, count: int = 1):
        if asset_type == "image":
            cost = count * PRICES["dalle-3-hd"]
        elif asset_type == "audio":
            cost = count * (PRICES["tts-1-hd"] / 2) # 대략적인 추정
        else:
            cost = 0.0
        
        self.total_usd += cost
        self.details[asset_type] = self.details.get(asset_type, 0.0) + cost

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_usd": round(self.total_usd, 4),
            "total_krw": int(self.total_usd * 1350), # 고정 환율 적용
            "details": {k: round(v, 4) for k, v in self.details.items()}
        }

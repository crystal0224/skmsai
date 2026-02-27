#!/usr/bin/env python3
"""Mock 평가 결과 생성: API 키 없이 EvalResult JSONL 파일 생성.

golden V1 + V2 (100개 질문)을 로드하고, 결정론적 랜덤 시드로
시뮬레이션된 EvalResult를 eval/results.mock.jsonl에 저장한다.

목표:
- Pass rate: ~85% (일부 문항 실패, 특히 hard 난이도)
- Regression pass rate: ~90%
- Score 범위: relevance 3.5–5.0, faithfulness 3.0–5.0,
              quote_accuracy 3.0–5.0, temporal_correctness 3.0–5.0

Usage:
    python scripts/13_mock_eval.py
    python scripts/13_mock_eval.py --output eval/results.mock.jsonl --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

EVAL_AXES = ("relevance", "faithfulness", "quote_accuracy", "temporal_correctness")

# 축별 임계값 (quality_gate.py DEFAULT_THRESHOLDS와 동일)
THRESHOLDS: dict[str, float] = {
    "faithfulness": 4.0,
    "relevance": 3.5,
    "quote_accuracy": 3.5,
    "temporal_correctness": 3.5,
}

# 난이도별 점수 프로파일 (mean, std).
# 목표: easy ~100%, medium ~93%, hard ~64% → 전체 약 85% pass rate
# (난이도 분포: easy 15개, medium 55개, hard 30개 기준 보정)
_SCORE_PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    "easy": {
        "relevance": (4.6, 0.25),
        "faithfulness": (4.6, 0.25),
        "quote_accuracy": (4.5, 0.30),
        "temporal_correctness": (4.6, 0.25),
    },
    "medium": {
        "relevance": (4.3, 0.35),
        "faithfulness": (4.3, 0.35),
        "quote_accuracy": (4.2, 0.40),
        "temporal_correctness": (4.2, 0.35),
    },
    "hard": {
        "relevance": (4.2, 0.55),
        "faithfulness": (4.15, 0.55),
        "quote_accuracy": (4.0, 0.60),
        "temporal_correctness": (4.1, 0.55),
    },
}

# regression_checks가 있는 문항의 regression 실패 확률 (10%)
_REGRESSION_FAIL_PROBABILITY = 0.10

# 점수 클램핑 범위 (axis별)
_SCORE_BOUNDS: dict[str, tuple[float, float]] = {
    "relevance": (3.5, 5.0),
    "faithfulness": (3.0, 5.0),
    "quote_accuracy": (3.0, 5.0),
    "temporal_correctness": (3.0, 5.0),
}


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _round_to_half(value: float) -> float:
    """0.5 단위로 반올림 (실제 judge 점수처럼)."""
    return round(value * 2) / 2


def _generate_scores(difficulty: str, rng: random.Random) -> dict[str, float]:
    """난이도에 따라 시뮬레이션 점수를 생성한다."""
    profile = _SCORE_PROFILES.get(difficulty, _SCORE_PROFILES["medium"])
    scores: dict[str, float] = {}

    for axis in EVAL_AXES:
        mean, std = profile[axis]
        raw = rng.gauss(mean, std)
        lo, hi = _SCORE_BOUNDS[axis]
        clamped = _clamp(raw, lo, hi)
        scores[axis] = _round_to_half(clamped)

    return scores


def _judge_passed(scores: dict[str, float]) -> bool:
    """임계값을 모두 충족하면 judge_passed = True."""
    return all(scores[axis] >= THRESHOLDS[axis] for axis in THRESHOLDS)


def _simulate_regression(question: dict, rng: random.Random) -> tuple[bool, list[str]]:
    """regression_checks 시뮬레이션. 10% 확률로 실패."""
    checks = question.get("regression_checks", [])
    if not checks:
        return True, []

    failures: list[str] = []
    for check in checks:
        if rng.random() < _REGRESSION_FAIL_PROBABILITY:
            failures.append(check.get("description", check["type"]))

    return len(failures) == 0, failures


# ---------------------------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------------------------


def load_questions(path: Path) -> list[dict]:
    """JSONL 파일에서 질문 목록을 로드한다."""
    questions: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


# ---------------------------------------------------------------------------
# 핵심 로직
# ---------------------------------------------------------------------------


def generate_mock_result(question: dict, rng: random.Random) -> dict:
    """단일 질문에 대한 시뮬레이션 EvalResult dict를 생성한다."""
    difficulty = question.get("difficulty", "medium")
    scores = _generate_scores(difficulty, rng)
    judge_ok = _judge_passed(scores)
    regression_ok, regression_failures = _simulate_regression(question, rng)
    passed = judge_ok and regression_ok

    return {
        "id": question["id"],
        "query": question["query"],
        "query_type": question["query_type"],
        "passed": passed,
        "judge_passed": judge_ok,
        "regression_passed": regression_ok,
        "scores": scores,
        "regression_failures": regression_failures,
    }


def generate_all_results(questions: list[dict], seed: int) -> list[dict]:
    """모든 질문에 대한 시뮬레이션 결과를 생성한다."""
    rng = random.Random(seed)
    return [generate_mock_result(q, rng) for q in questions]


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------


def write_results(results: list[dict], output_path: Path) -> None:
    """결과를 JSONL 형식으로 파일에 저장한다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")


def print_summary(results: list[dict]) -> None:
    """결과 요약을 stderr에 출력한다."""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    regression_failed = sum(1 for r in results if not r["regression_passed"])
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    print(f"\n{'='*50}", file=sys.stderr)
    print("Mock 평가 결과 요약", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)
    print(f"총 질의: {total}개", file=sys.stderr)
    print(f"통과: {passed}/{total} ({pass_rate:.1f}%)", file=sys.stderr)
    print(f"회귀 실패: {regression_failed}건", file=sys.stderr)

    print(f"\n{'축':<25} {'평균':>6} {'최소':>6} {'최대':>6}", file=sys.stderr)
    print(f"{'-'*45}", file=sys.stderr)
    for axis in EVAL_AXES:
        vals = [r["scores"][axis] for r in results]
        avg = sum(vals) / len(vals)
        mn = min(vals)
        mx = max(vals)
        print(f"{axis:<25} {avg:>6.2f} {mn:>6.1f} {mx:>6.1f}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="API 키 없이 Mock EvalResult JSONL을 생성한다."
    )
    parser.add_argument(
        "--output",
        default="eval/results.mock.jsonl",
        help="출력 파일 경로 (기본값: eval/results.mock.jsonl)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="랜덤 시드 (기본값: 42, 재현성 보장)",
    )
    parser.add_argument(
        "--v1",
        default="eval/questions.golden_v1.jsonl",
        help="Golden V1 질문 파일 경로",
    )
    parser.add_argument(
        "--v2",
        default="eval/questions.golden_v2.jsonl",
        help="Golden V2 질문 파일 경로",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # 프로젝트 루트 기준 경로 해석
    project_root = Path(__file__).resolve().parent.parent

    v1_path = Path(args.v1) if Path(args.v1).is_absolute() else project_root / args.v1
    v2_path = Path(args.v2) if Path(args.v2).is_absolute() else project_root / args.v2
    output_path = (
        Path(args.output)
        if Path(args.output).is_absolute()
        else project_root / args.output
    )

    # 질문 로드
    print(f"[13] V1 로드: {v1_path}", file=sys.stderr)
    v1_questions = load_questions(v1_path)
    print(f"[13] V2 로드: {v2_path}", file=sys.stderr)
    v2_questions = load_questions(v2_path)

    all_questions = v1_questions + v2_questions
    print(f"[13] 총 질의: {len(all_questions)}개 (seed={args.seed})", file=sys.stderr)

    # 결과 생성
    results = generate_all_results(all_questions, seed=args.seed)

    # 저장
    write_results(results, output_path)
    print(f"\n[13] 결과 저장: {output_path}", file=sys.stderr)

    # 요약 출력
    print_summary(results)


if __name__ == "__main__":
    main()

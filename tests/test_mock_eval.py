"""13_mock_eval.py 테스트.

API 키 없이 Mock EvalResult를 생성하는 스크립트의 동작을 검증한다.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from scripts.lib.quality_gate import EVAL_AXES, DEFAULT_THRESHOLDS  # noqa: E402

import importlib.util as _ilu

_SCRIPT_PATH = _PROJECT_ROOT / "scripts" / "13_mock_eval.py"
_spec = _ilu.spec_from_file_location("mock_eval", _SCRIPT_PATH)
_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

# 스크립트 내 함수 직접 참조
generate_all_results = _mod.generate_all_results
generate_mock_result = _mod.generate_mock_result
load_questions = _mod.load_questions
write_results = _mod.write_results
THRESHOLDS = _mod.THRESHOLDS


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

_V1_PATH = _PROJECT_ROOT / "eval" / "questions.golden_v1.jsonl"
_V2_PATH = _PROJECT_ROOT / "eval" / "questions.golden_v2.jsonl"


@pytest.fixture(scope="module")
def all_questions() -> list[dict]:
    """V1 + V2 질문 100개를 로드한다."""
    v1 = load_questions(_V1_PATH)
    v2 = load_questions(_V2_PATH)
    return v1 + v2


@pytest.fixture(scope="module")
def results_seed42(all_questions) -> list[dict]:
    """seed=42로 생성한 결과 (모듈 범위 캐싱으로 재사용)."""
    return generate_all_results(all_questions, seed=42)


@pytest.fixture(scope="module")
def results_seed99(all_questions) -> list[dict]:
    """seed=99로 생성한 결과."""
    return generate_all_results(all_questions, seed=99)


# ---------------------------------------------------------------------------
# 기본 개수 / 형식 테스트
# ---------------------------------------------------------------------------


class TestResultCount:
    def test_generates_100_results(self, results_seed42):
        """V1(50) + V2(50) = 100개 결과가 생성되어야 한다."""
        assert len(results_seed42) == 100

    def test_result_ids_match_question_ids(self, all_questions, results_seed42):
        """결과 id가 질문 id와 1:1 대응해야 한다."""
        q_ids = [q["id"] for q in all_questions]
        r_ids = [r["id"] for r in results_seed42]
        assert q_ids == r_ids

    def test_result_ids_are_unique(self, results_seed42):
        """모든 결과 id가 고유해야 한다."""
        ids = [r["id"] for r in results_seed42]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# 스키마 테스트 (EvalResult 형식)
# ---------------------------------------------------------------------------


class TestResultSchema:
    _REQUIRED_KEYS = {
        "id",
        "query",
        "query_type",
        "passed",
        "judge_passed",
        "regression_passed",
        "scores",
        "regression_failures",
    }

    def test_all_results_have_required_keys(self, results_seed42):
        """모든 결과에 필수 키가 있어야 한다."""
        for result in results_seed42:
            missing = self._REQUIRED_KEYS - result.keys()
            assert not missing, f"{result['id']} 누락 키: {missing}"

    def test_all_results_have_four_score_axes(self, results_seed42):
        """모든 결과의 scores에 4개 축이 있어야 한다."""
        for result in results_seed42:
            scores = result["scores"]
            for axis in EVAL_AXES:
                assert axis in scores, f"{result['id']}: scores에 '{axis}' 없음"

    def test_score_types_are_float(self, results_seed42):
        """scores 값이 float 타입이어야 한다."""
        for result in results_seed42:
            for axis, value in result["scores"].items():
                assert isinstance(
                    value, float
                ), f"{result['id']} {axis}: float 아님 ({type(value).__name__})"

    def test_boolean_fields_are_bool(self, results_seed42):
        """passed, judge_passed, regression_passed가 bool이어야 한다."""
        for result in results_seed42:
            for field in ("passed", "judge_passed", "regression_passed"):
                assert isinstance(
                    result[field], bool
                ), f"{result['id']} {field}: bool 아님"

    def test_regression_failures_is_list(self, results_seed42):
        """regression_failures가 list여야 한다."""
        for result in results_seed42:
            assert isinstance(
                result["regression_failures"], list
            ), f"{result['id']}: regression_failures가 list 아님"

    def test_passed_consistent_with_judge_and_regression(self, results_seed42):
        """passed = judge_passed AND regression_passed 일관성 검사."""
        for result in results_seed42:
            expected = result["judge_passed"] and result["regression_passed"]
            assert result["passed"] == expected, (
                f"{result['id']}: passed={result['passed']} 불일치 "
                f"(judge={result['judge_passed']}, regression={result['regression_passed']})"
            )

    def test_regression_failures_non_empty_when_failed(self, results_seed42):
        """regression_passed=False인 경우 regression_failures가 비어있지 않아야 한다."""
        for result in results_seed42:
            if not result["regression_passed"]:
                assert result[
                    "regression_failures"
                ], f"{result['id']}: regression_passed=False인데 failures가 비어있음"


# ---------------------------------------------------------------------------
# 점수 범위 테스트
# ---------------------------------------------------------------------------


class TestScoreBounds:
    def test_relevance_in_range(self, results_seed42):
        """relevance는 3.5–5.0 범위여야 한다."""
        for r in results_seed42:
            v = r["scores"]["relevance"]
            assert 3.5 <= v <= 5.0, f"{r['id']}: relevance={v} 범위 초과"

    def test_faithfulness_in_range(self, results_seed42):
        """faithfulness는 3.0–5.0 범위여야 한다."""
        for r in results_seed42:
            v = r["scores"]["faithfulness"]
            assert 3.0 <= v <= 5.0, f"{r['id']}: faithfulness={v} 범위 초과"

    def test_quote_accuracy_in_range(self, results_seed42):
        """quote_accuracy는 3.0–5.0 범위여야 한다."""
        for r in results_seed42:
            v = r["scores"]["quote_accuracy"]
            assert 3.0 <= v <= 5.0, f"{r['id']}: quote_accuracy={v} 범위 초과"

    def test_temporal_correctness_in_range(self, results_seed42):
        """temporal_correctness는 3.0–5.0 범위여야 한다."""
        for r in results_seed42:
            v = r["scores"]["temporal_correctness"]
            assert 3.0 <= v <= 5.0, f"{r['id']}: temporal_correctness={v} 범위 초과"

    def test_scores_are_half_point_multiples(self, results_seed42):
        """점수가 0.5 단위여야 한다 (실제 judge 스타일)."""
        for r in results_seed42:
            for axis, v in r["scores"].items():
                assert v * 2 == round(v * 2), f"{r['id']} {axis}={v}: 0.5 단위 아님"


# ---------------------------------------------------------------------------
# Pass rate 테스트
# ---------------------------------------------------------------------------


class TestPassRate:
    def test_overall_pass_rate_in_expected_range(self, results_seed42):
        """전체 통과율이 80–90% 범위여야 한다."""
        total = len(results_seed42)
        passed = sum(1 for r in results_seed42 if r["passed"])
        rate = passed / total * 100
        assert 80.0 <= rate <= 90.0, f"통과율 {rate:.1f}%가 80-90% 범위 벗어남"

    def test_regression_pass_rate_in_expected_range(self, results_seed42):
        """regression 통과율이 85% 이상이어야 한다."""
        with_checks = [
            r for r in results_seed42 if r.get("regression_failures") is not None
        ]
        # regression_checks가 있는 문항만 대상
        has_checks = [
            r
            for r in results_seed42
            if not r["regression_passed"] or r["regression_failures"] is not None
        ]
        regression_passed = sum(1 for r in results_seed42 if r["regression_passed"])
        total = len(results_seed42)
        reg_rate = regression_passed / total * 100
        assert reg_rate >= 85.0, f"regression 통과율 {reg_rate:.1f}%가 85% 미만"

    def test_some_questions_fail(self, results_seed42):
        """일부 문항은 실패해야 한다 (전부 통과면 비현실적)."""
        failed = sum(1 for r in results_seed42 if not r["passed"])
        assert failed > 0, "모든 문항이 통과함 — 비현실적 결과"

    def test_hard_questions_fail_more_than_easy(self, all_questions, results_seed42):
        """hard 문항의 실패율이 easy 문항보다 높아야 한다."""
        result_by_id = {r["id"]: r for r in results_seed42}
        difficulty_by_id = {
            q["id"]: q.get("difficulty", "medium") for q in all_questions
        }

        easy_failed = sum(
            1
            for qid, diff in difficulty_by_id.items()
            if diff == "easy" and not result_by_id[qid]["passed"]
        )
        easy_total = sum(1 for d in difficulty_by_id.values() if d == "easy")

        hard_failed = sum(
            1
            for qid, diff in difficulty_by_id.items()
            if diff == "hard" and not result_by_id[qid]["passed"]
        )
        hard_total = sum(1 for d in difficulty_by_id.values() if d == "hard")

        easy_fail_rate = easy_failed / easy_total if easy_total > 0 else 0
        hard_fail_rate = hard_failed / hard_total if hard_total > 0 else 0

        assert (
            hard_fail_rate >= easy_fail_rate
        ), f"hard 실패율({hard_fail_rate:.2f})이 easy 실패율({easy_fail_rate:.2f})보다 낮음"


# ---------------------------------------------------------------------------
# 결정론적 출력 테스트
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_gives_same_results(self, all_questions):
        """같은 seed는 동일한 결과를 생성해야 한다."""
        results_a = generate_all_results(all_questions, seed=42)
        results_b = generate_all_results(all_questions, seed=42)
        assert results_a == results_b

    def test_different_seed_gives_different_results(self, all_questions):
        """다른 seed는 다른 결과를 생성해야 한다."""
        results_42 = generate_all_results(all_questions, seed=42)
        results_99 = generate_all_results(all_questions, seed=99)
        scores_42 = [r["scores"] for r in results_42]
        scores_99 = [r["scores"] for r in results_99]
        assert scores_42 != scores_99

    def test_seed_42_specific_first_result(self, results_seed42):
        """seed=42일 때 첫 결과 id가 g-001이어야 한다 (회귀 방지)."""
        assert results_seed42[0]["id"] == "g-001"

    def test_seed_42_specific_last_result(self, results_seed42):
        """seed=42일 때 마지막 결과 id가 g-100이어야 한다 (회귀 방지)."""
        assert results_seed42[-1]["id"] == "g-100"


# ---------------------------------------------------------------------------
# JSONL 직렬화 / 파일 출력 테스트
# ---------------------------------------------------------------------------


class TestJsonlOutput:
    def test_write_and_reload_produces_same_data(self, results_seed42, tmp_path):
        """저장 후 재로드한 데이터가 원본과 동일해야 한다."""
        out = tmp_path / "results.mock.jsonl"
        write_results(results_seed42, out)

        reloaded: list[dict] = []
        with open(out, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    reloaded.append(json.loads(line))

        assert len(reloaded) == len(results_seed42)
        for original, loaded in zip(results_seed42, reloaded):
            assert original == loaded

    def test_each_line_is_valid_json(self, results_seed42, tmp_path):
        """각 줄이 유효한 JSON이어야 한다."""
        out = tmp_path / "results.mock.jsonl"
        write_results(results_seed42, out)

        with open(out, encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if line:
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as e:
                        pytest.fail(f"줄 {i}: JSON 파싱 실패 — {e}")

    def test_output_dir_created_if_missing(self, results_seed42, tmp_path):
        """출력 디렉토리가 없어도 자동 생성되어야 한다."""
        nested = tmp_path / "a" / "b" / "results.mock.jsonl"
        assert not nested.parent.exists()
        write_results(results_seed42, nested)
        assert nested.exists()


# ---------------------------------------------------------------------------
# 질문 로드 테스트
# ---------------------------------------------------------------------------


class TestLoadQuestions:
    def test_v1_loads_50_questions(self):
        """V1 파일에서 50개 질문이 로드되어야 한다."""
        questions = load_questions(_V1_PATH)
        assert len(questions) == 50

    def test_v2_loads_50_questions(self):
        """V2 파일에서 50개 질문이 로드되어야 한다."""
        questions = load_questions(_V2_PATH)
        assert len(questions) == 50

    def test_v1_ids_start_with_g001(self):
        """V1 첫 질문 id가 g-001이어야 한다."""
        questions = load_questions(_V1_PATH)
        assert questions[0]["id"] == "g-001"

    def test_v2_ids_start_with_g051(self):
        """V2 첫 질문 id가 g-051이어야 한다."""
        questions = load_questions(_V2_PATH)
        assert questions[0]["id"] == "g-051"

    def test_questions_have_required_fields(self):
        """각 질문에 id, query, query_type 필드가 있어야 한다."""
        v1 = load_questions(_V1_PATH)
        v2 = load_questions(_V2_PATH)
        for q in v1 + v2:
            for field in ("id", "query", "query_type"):
                assert field in q, f"질문 {q.get('id', '?')}: '{field}' 필드 없음"

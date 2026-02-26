"""전체 Output 통합 테스트.

PR-033: 5종 출력 타입의 E2E 파이프라인 검증.

파이프라인:
  context formatting → LLM 생성 (mock) → 스키마 검증 → Markdown 렌더링

테스트 대상:
  - summary, card, comparison_table, quiz, slide — 단일 및 목록
  - 재시도 로직 (첫 시도 실패 → 재시도 성공)
  - 검증 실패 시 graceful 처리
  - TemporalConflict 컨텍스트 포함
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.generation import (  # noqa: E402
    GenerationConfig,
    GenerationResult,
    GenerationService,
    TemporalConflict,
    detect_temporal_conflicts,
    format_context,
)
from scripts.lib.output_renderer import RenderResult, render  # noqa: E402
from scripts.lib.output_validator import validate_content_output  # noqa: E402


# ---------------------------------------------------------------------------
# Mock LLM 클라이언트
# ---------------------------------------------------------------------------


@dataclass
class _MockMessage:
    """Mock Anthropic Message."""

    content: list[Any]


@dataclass
class _MockContentBlock:
    """Mock content block."""

    text: str


class MockLLMClient:
    """테스트용 Mock LLM 클라이언트.

    responses 리스트에서 순서대로 응답을 반환한다.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_count = 0
        self.messages = self

    def create(self, **kwargs: Any) -> _MockMessage:
        """Mock API 호출."""
        if self._call_count < len(self._responses):
            text = self._responses[self._call_count]
        else:
            text = self._responses[-1] if self._responses else "{}"
        self._call_count += 1
        return _MockMessage(content=[_MockContentBlock(text=text)])

    @property
    def call_count(self) -> int:
        return self._call_count


# ---------------------------------------------------------------------------
# 테스트용 검색 결과 (hits) 샘플
# ---------------------------------------------------------------------------


def _make_hits(n: int = 3) -> list[dict]:
    """테스트용 검색 결과를 생성한다."""
    editions = ["2020-14차", "1998-10차", "1979-초판"]
    types = ["definition", "principle", "narrative"]
    hits = []
    for i in range(n):
        ed_idx = i % len(editions)
        hits.append(
            {
                "quote_id": f"{editions[ed_idx]}|경영원칙|{types[ed_idx]}|{i+1:03d}",
                "text": f"SKMS 원문 텍스트 {i+1}: 경영의 기본 원칙을 설명하는 문단입니다.",
                "edition": editions[ed_idx],
                "chapter_path": ["경영원칙", f"섹션{i+1}"],
                "type": types[ed_idx],
                "quality_flags": [],
                "score": 0.9 - i * 0.1,
            }
        )
    return hits


# ---------------------------------------------------------------------------
# 유효한 LLM 응답 JSON 샘플
# ---------------------------------------------------------------------------

VALID_SUMMARY_JSON = json.dumps(
    {
        "title": "SKMS 경영 원칙 요약",
        "body": "SKMS는 인간중심, 합리적, 현실 인식의 3대 원칙을 기반으로 한다. 경영의 궁극적 목적은 구성원의 행복에 있다.",
        "key_points": [
            "인간중심의 경영",
            "합리적 경영",
            "현실을 인식한 경영",
        ],
        "citations": ["2020-14차|경영원칙|definition|001"],
    },
    ensure_ascii=False,
)

VALID_CARD_JSON = json.dumps(
    {
        "front": "SUPEX란 무엇인가?",
        "back": "Super Excellent의 약자로 인간 능력으로 도달 가능한 최고 수준",
        "edition_tag": "2020-14차",
        "citations": ["2020-14차|경영원칙|definition|001"],
    },
    ensure_ascii=False,
)

VALID_CARD_LIST_JSON = json.dumps(
    {
        "cards": [
            {
                "front": "SUPEX란?",
                "back": "인간 능력의 최고 수준",
                "edition_tag": "14차",
                "citations": ["2020-14차|경영원칙|definition|001"],
            },
            {
                "front": "VWBE란?",
                "back": "자발적 의욕적 두뇌활용",
                "edition_tag": "14차",
                "citations": ["2020-14차|경영원칙|principle|002"],
            },
        ]
    },
    ensure_ascii=False,
)

VALID_COMPARISON_TABLE_JSON = json.dumps(
    {
        "concept": "의욕관리",
        "columns": ["1979-초판", "2020-14차"],
        "rows": [
            {
                "aspect": "정의",
                "values": {
                    "1979-초판": "구성원의 근무 의욕을 높이는 활동",
                    "2020-14차": "VWBE 문화의 핵심 구성요소",
                },
                "quote_ids": [
                    "1979-초판|경영원칙|definition|001",
                    "2020-14차|경영원칙|definition|002",
                ],
            },
        ],
        "evolution_summary": "의욕관리는 VWBE의 하위 개념으로 통합되었다.",
    },
    ensure_ascii=False,
)

VALID_QUIZ_JSON = json.dumps(
    {
        "question": "SKMS에서 VWBE의 의미는?",
        "choices": [
            "자발적 의욕적 두뇌활용",
            "수직적 위계 기반 경영",
            "비효율 제거 프로젝트",
            "성과급 시스템",
        ],
        "correct_index": 0,
        "explanation": "VWBE는 14차 개정판에서 도입된 자발적 의욕적 두뇌활용 문화이다.",
        "citations": ["2020-14차|경영원칙|definition|001"],
    },
    ensure_ascii=False,
)

VALID_QUIZ_LIST_JSON = json.dumps(
    {
        "quizzes": [
            {
                "question": "Q1: SUPEX의 의미는?",
                "choices": ["최고 수준", "최저 비용", "최대 인원", "최소 시간"],
                "correct_index": 0,
                "explanation": "Super Excellent의 약자이다.",
                "citations": ["1998-10차|경영원칙|definition|001"],
            },
            {
                "question": "Q2: VWBE의 핵심은?",
                "choices": ["성과급", "두뇌활용", "구조조정", "비용절감"],
                "correct_index": 1,
                "explanation": "자발적 의욕적 두뇌활용이다.",
                "citations": ["2020-14차|경영원칙|principle|002"],
            },
        ]
    },
    ensure_ascii=False,
)

VALID_SLIDE_JSON = json.dumps(
    {
        "slide_number": 1,
        "title": "SKMS 3대 경영 원칙",
        "body": [
            "인간중심의 경영",
            "합리적 경영",
            "현실을 인식한 경영",
        ],
        "sources": ["2020-14차|경영원칙|principle|001"],
    },
    ensure_ascii=False,
)

VALID_SLIDE_LIST_JSON = json.dumps(
    {
        "slides": [
            {
                "slide_number": 1,
                "title": "SKMS 개요",
                "body": ["인간중심 경영", "합리적 경영"],
                "sources": ["2020-14차|경영원칙|principle|001"],
            },
            {
                "slide_number": 2,
                "title": "SUPEX 추구",
                "body": ["최고 수준 지향", "VWBE 문화"],
                "sources": ["1998-10차|경영원칙|definition|001"],
            },
        ]
    },
    ensure_ascii=False,
)


# ---------------------------------------------------------------------------
# context formatting 테스트
# ---------------------------------------------------------------------------


class TestContextFormatting:
    """format_context 통합 테스트."""

    def test_basic_context(self):
        """기본 컨텍스트 포맷팅."""
        hits = _make_hits(2)
        conflict = TemporalConflict(
            has_conflict=False, conflicting_editions=(), definition_count=0
        )
        ctx = format_context(hits, "general_definition", conflict)

        assert "[METADATA]" in ctx
        assert "intent: general_definition" in ctx
        assert "temporal_conflict: false" in ctx
        assert "[CHUNK 1]" in ctx
        assert "[CHUNK 2]" in ctx

    def test_content_generation_with_output_specs(self):
        """content_generation 인텐트에서 output_specs 포함."""
        hits = _make_hits(1)
        conflict = TemporalConflict(
            has_conflict=False, conflicting_editions=(), definition_count=0
        )
        specs = {
            "output_types": {
                "quiz": {
                    "description": "4지선다 퀴즈",
                    "structure": [{"field": "question", "type": "string"}],
                }
            }
        }
        ctx = format_context(
            hits, "content_generation", conflict, output_type="quiz", output_specs=specs
        )

        assert "output_type: quiz" in ctx
        assert "4지선다 퀴즈" in ctx

    def test_temporal_conflict_metadata(self):
        """TemporalConflict가 메타데이터에 반영된다."""
        hits = _make_hits(3)
        conflict = TemporalConflict(
            has_conflict=True,
            conflicting_editions=("1979-초판", "2020-14차"),
            definition_count=3,
        )
        ctx = format_context(hits, "general_definition", conflict)

        assert "temporal_conflict: true" in ctx
        assert "1979-초판" in ctx
        assert "2020-14차" in ctx


class TestDetectTemporalConflicts:
    """detect_temporal_conflicts 통합 테스트."""

    def test_no_conflict(self):
        """충돌 없음 — definition이 1개 개정판에만 존재."""
        hits = [
            {"type": "definition", "edition": "2020-14차"},
            {"type": "narrative", "edition": "1979-초판"},
        ]
        result = detect_temporal_conflicts(hits)
        assert result.has_conflict is False
        assert result.definition_count == 1

    def test_conflict(self):
        """충돌 감지 — definition이 2개 개정판에 존재."""
        hits = [
            {"type": "definition", "edition": "2020-14차"},
            {"type": "definition", "edition": "1979-초판"},
        ]
        result = detect_temporal_conflicts(hits)
        assert result.has_conflict is True
        assert len(result.conflicting_editions) == 2
        assert result.definition_count == 2


# ---------------------------------------------------------------------------
# 단일 출력 타입 E2E: validate → render
# ---------------------------------------------------------------------------


class TestValidateAndRenderSummary:
    """summary: 검증 → 렌더 통합 테스트."""

    def test_valid(self):
        """유효한 summary JSON → 검증 통과 → 렌더 성공."""
        vr = validate_content_output(VALID_SUMMARY_JSON, "summary")
        assert vr.passed is True

        rr = render(VALID_SUMMARY_JSON, "summary")
        assert rr.success is True
        assert "### SKMS 경영 원칙 요약" in rr.rendered
        assert "인간중심의 경영" in rr.rendered
        assert "**출처:**" in rr.rendered

    def test_invalid_summary(self):
        """빈 제목 → 검증 실패."""
        bad = json.dumps(
            {"title": "", "body": "", "key_points": [], "citations": []},
            ensure_ascii=False,
        )
        vr = validate_content_output(bad, "summary")
        assert vr.passed is False

        rr = render(bad, "summary")
        assert rr.success is False


class TestValidateAndRenderCard:
    """card: 검증 → 렌더 통합 테스트."""

    def test_single_card(self):
        """단일 카드 E2E."""
        vr = validate_content_output(VALID_CARD_JSON, "card")
        assert vr.passed is True

        rr = render(VALID_CARD_JSON, "card")
        assert rr.success is True
        assert "**Q:** SUPEX란 무엇인가?" in rr.rendered

    def test_card_list(self):
        """카드 목록 E2E."""
        vr = validate_content_output(VALID_CARD_LIST_JSON, "card")
        assert vr.passed is True

        rr = render(VALID_CARD_LIST_JSON, "card")
        assert rr.success is True
        assert "지식 카드 (2장)" in rr.rendered


class TestValidateAndRenderComparisonTable:
    """comparison_table: 검증 → 렌더 통합 테스트."""

    def test_valid(self):
        """유효한 비교표 E2E."""
        vr = validate_content_output(VALID_COMPARISON_TABLE_JSON, "comparison_table")
        assert vr.passed is True

        rr = render(VALID_COMPARISON_TABLE_JSON, "comparison_table")
        assert rr.success is True
        assert "의욕관리 — 개정판 비교" in rr.rendered
        assert "| 정의 |" in rr.rendered
        assert "**변화 요약:**" in rr.rendered


class TestValidateAndRenderQuiz:
    """quiz: 검증 → 렌더 통합 테스트."""

    def test_single_quiz(self):
        """단일 퀴즈 E2E."""
        vr = validate_content_output(VALID_QUIZ_JSON, "quiz")
        assert vr.passed is True

        rr = render(VALID_QUIZ_JSON, "quiz")
        assert rr.success is True
        assert "**Q:** SKMS에서 VWBE의 의미는?" in rr.rendered
        assert "**정답:** 1번" in rr.rendered
        assert "**해설:**" in rr.rendered

    def test_quiz_list(self):
        """퀴즈 목록 E2E."""
        vr = validate_content_output(VALID_QUIZ_LIST_JSON, "quiz")
        assert vr.passed is True

        rr = render(VALID_QUIZ_LIST_JSON, "quiz")
        assert rr.success is True
        assert "퀴즈 (2문제)" in rr.rendered
        assert "퀴즈 1" in rr.rendered
        assert "퀴즈 2" in rr.rendered


class TestValidateAndRenderSlide:
    """slide: 검증 → 렌더 통합 테스트."""

    def test_single_slide(self):
        """단일 슬라이드 E2E."""
        vr = validate_content_output(VALID_SLIDE_JSON, "slide")
        assert vr.passed is True

        rr = render(VALID_SLIDE_JSON, "slide")
        assert rr.success is True
        assert "**Slide 1: SKMS 3대 경영 원칙**" in rr.rendered
        assert "- 인간중심의 경영" in rr.rendered

    def test_slide_list(self):
        """슬라이드 목록 E2E."""
        vr = validate_content_output(VALID_SLIDE_LIST_JSON, "slide")
        assert vr.passed is True

        rr = render(VALID_SLIDE_LIST_JSON, "slide")
        assert rr.success is True
        assert "슬라이드 (2장)" in rr.rendered
        assert "Slide 1" in rr.rendered
        assert "Slide 2" in rr.rendered


# ---------------------------------------------------------------------------
# GenerationService E2E: Mock LLM → 검증 → 렌더
# ---------------------------------------------------------------------------


class TestGenerationServiceE2E:
    """GenerationService mock E2E 테스트."""

    def _make_service(self, responses: list[str]) -> GenerationService:
        """Mock 클라이언트로 GenerationService를 생성한다."""
        client = MockLLMClient(responses)
        config = GenerationConfig(
            model="mock-model",
            max_tokens=3000,
            router_model="mock-model",
            router_max_tokens=500,
            max_retries=1,
            prompts_dir="prompts",
        )
        svc = GenerationService(client=client, config=config)
        svc._prompts["content_gen"] = "Mock content generation prompt"
        svc._prompts["answer"] = "Mock answer prompt"
        return svc

    def test_summary_e2e(self):
        """summary 전체 파이프라인: generate → validate → render."""
        svc = self._make_service([VALID_SUMMARY_JSON])
        result = svc.generate(
            query="SKMS 경영 원칙을 요약해줘",
            context="[METADATA]\nintent: content_generation\n[CHUNK 1]\ntext...",
            intent="content_generation",
            output_type="summary",
        )
        assert result.validation_passed is True
        assert result.retried is False

        rr = render(result.answer, "summary")
        assert rr.success is True
        assert "SKMS 경영 원칙 요약" in rr.rendered

    def test_card_e2e(self):
        """card 전체 파이프라인."""
        svc = self._make_service([VALID_CARD_JSON])
        result = svc.generate(
            query="SUPEX 카드를 만들어줘",
            context="[METADATA]...",
            intent="content_generation",
            output_type="card",
        )
        assert result.validation_passed is True

        rr = render(result.answer, "card")
        assert rr.success is True
        assert "SUPEX란 무엇인가?" in rr.rendered

    def test_comparison_table_e2e(self):
        """comparison_table 전체 파이프라인."""
        svc = self._make_service([VALID_COMPARISON_TABLE_JSON])
        result = svc.generate(
            query="의욕관리 변천사를 비교표로 만들어줘",
            context="[METADATA]...",
            intent="content_generation",
            output_type="comparison_table",
        )
        assert result.validation_passed is True

        rr = render(result.answer, "comparison_table")
        assert rr.success is True
        assert "의욕관리 — 개정판 비교" in rr.rendered

    def test_quiz_e2e(self):
        """quiz 전체 파이프라인."""
        svc = self._make_service([VALID_QUIZ_JSON])
        result = svc.generate(
            query="VWBE 퀴즈를 만들어줘",
            context="[METADATA]...",
            intent="content_generation",
            output_type="quiz",
        )
        assert result.validation_passed is True

        rr = render(result.answer, "quiz")
        assert rr.success is True
        assert "VWBE의 의미는?" in rr.rendered
        assert "정답:" in rr.rendered

    def test_slide_e2e(self):
        """slide 전체 파이프라인."""
        svc = self._make_service([VALID_SLIDE_JSON])
        result = svc.generate(
            query="SKMS 경영 원칙 슬라이드를 만들어줘",
            context="[METADATA]...",
            intent="content_generation",
            output_type="slide",
        )
        assert result.validation_passed is True

        rr = render(result.answer, "slide")
        assert rr.success is True
        assert "Slide 1:" in rr.rendered

    def test_card_list_e2e(self):
        """card list 전체 파이프라인."""
        svc = self._make_service([VALID_CARD_LIST_JSON])
        result = svc.generate(
            query="SKMS 핵심 개념 카드 2장 만들어줘",
            context="[METADATA]...",
            intent="content_generation",
            output_type="card",
        )
        assert result.validation_passed is True

        rr = render(result.answer, "card")
        assert rr.success is True
        assert "지식 카드 (2장)" in rr.rendered

    def test_quiz_list_e2e(self):
        """quiz list 전체 파이프라인."""
        svc = self._make_service([VALID_QUIZ_LIST_JSON])
        result = svc.generate(
            query="SKMS 퀴즈 2문제 만들어줘",
            context="[METADATA]...",
            intent="content_generation",
            output_type="quiz",
        )
        assert result.validation_passed is True

        rr = render(result.answer, "quiz")
        assert rr.success is True
        assert "퀴즈 (2문제)" in rr.rendered

    def test_slide_list_e2e(self):
        """slide list 전체 파이프라인."""
        svc = self._make_service([VALID_SLIDE_LIST_JSON])
        result = svc.generate(
            query="SKMS 슬라이드 2장 만들어줘",
            context="[METADATA]...",
            intent="content_generation",
            output_type="slide",
        )
        assert result.validation_passed is True

        rr = render(result.answer, "slide")
        assert rr.success is True
        assert "슬라이드 (2장)" in rr.rendered


# ---------------------------------------------------------------------------
# 재시도 + 실패 E2E
# ---------------------------------------------------------------------------


class TestGenerationRetry:
    """GenerationService 재시도 로직 통합 테스트."""

    def _make_service(self, responses: list[str]) -> GenerationService:
        client = MockLLMClient(responses)
        config = GenerationConfig(
            model="mock-model",
            max_tokens=3000,
            router_model="mock-model",
            router_max_tokens=500,
            max_retries=1,
            prompts_dir="prompts",
        )
        svc = GenerationService(client=client, config=config)
        svc._prompts["content_gen"] = "Mock prompt"
        return svc

    def test_retry_success(self):
        """첫 시도 실패 → 재시도 성공."""
        bad_json = json.dumps({"invalid": "data"}, ensure_ascii=False)
        svc = self._make_service([bad_json, VALID_QUIZ_JSON])
        result = svc.generate(
            query="퀴즈 만들어줘",
            context="[METADATA]...",
            intent="content_generation",
            output_type="quiz",
        )
        assert result.validation_passed is True
        assert result.retried is True

        rr = render(result.answer, "quiz")
        assert rr.success is True

    def test_retry_exhausted(self):
        """재시도 소진 → validation_passed=False."""
        bad_json = json.dumps({"invalid": "data"}, ensure_ascii=False)
        svc = self._make_service([bad_json, bad_json])
        result = svc.generate(
            query="슬라이드 만들어줘",
            context="[METADATA]...",
            intent="content_generation",
            output_type="slide",
        )
        assert result.validation_passed is False
        assert result.retried is True
        assert len(result.validation_errors) > 0

    def test_non_content_generation_skips_validation(self):
        """content_generation이 아닌 인텐트는 검증을 건너뛴다."""
        svc = self._make_service(["자유 형식 답변입니다."])
        result = svc.generate(
            query="SUPEX란?",
            context="[METADATA]...",
            intent="general_definition",
        )
        assert result.validation_passed is None
        assert result.retried is False
        assert result.answer == "자유 형식 답변입니다."


# ---------------------------------------------------------------------------
# Prompt 선택 통합 테스트
# ---------------------------------------------------------------------------


class TestPromptSelection:
    """GenerationService 프롬프트 선택 테스트."""

    def test_content_generation_uses_content_gen_prompt(self):
        """content_generation 인텐트 → content_gen.md 사용."""
        client = MockLLMClient([VALID_SUMMARY_JSON])
        svc = GenerationService(client=client)
        svc._prompts["content_gen"] = "Content Gen Prompt"
        svc._prompts["answer"] = "Answer Prompt"

        prompt_text, prompt_name = svc.select_prompt("content_generation")
        assert prompt_name == "content_gen.md"
        assert prompt_text == "Content Gen Prompt"

    def test_other_intents_use_answer_prompt(self):
        """다른 인텐트 → answer.md 사용."""
        client = MockLLMClient([])
        svc = GenerationService(client=client)
        svc._prompts["answer"] = "Answer Prompt"

        for intent in [
            "general_definition",
            "specific_time",
            "evolution_comparison",
            "open_ended",
        ]:
            prompt_text, prompt_name = svc.select_prompt(intent)
            assert prompt_name == "answer.md"
            assert prompt_text == "Answer Prompt"


# ---------------------------------------------------------------------------
# 5종 출력 Cross-check: JSON ↔ Pydantic ↔ Markdown 일관성
# ---------------------------------------------------------------------------


class TestOutputCrossCheck:
    """5종 출력 타입의 검증↔렌더 일관성 테스트."""

    @pytest.mark.parametrize(
        "output_type,raw_json,expected_text",
        [
            ("summary", VALID_SUMMARY_JSON, "### SKMS 경영 원칙 요약"),
            ("card", VALID_CARD_JSON, "**Q:** SUPEX란 무엇인가?"),
            ("card", VALID_CARD_LIST_JSON, "지식 카드 (2장)"),
            ("comparison_table", VALID_COMPARISON_TABLE_JSON, "의욕관리 — 개정판 비교"),
            ("quiz", VALID_QUIZ_JSON, "**정답:** 1번"),
            ("quiz", VALID_QUIZ_LIST_JSON, "퀴즈 (2문제)"),
            ("slide", VALID_SLIDE_JSON, "**Slide 1:"),
            ("slide", VALID_SLIDE_LIST_JSON, "슬라이드 (2장)"),
        ],
    )
    def test_validate_then_render(
        self, output_type: str, raw_json: str, expected_text: str
    ):
        """각 출력 타입: 검증 통과 → 렌더 성공 → 기대 텍스트 포함."""
        vr = validate_content_output(raw_json, output_type)
        assert vr.passed is True, f"검증 실패: {vr.errors}"

        rr = render(raw_json, output_type)
        assert rr.success is True, f"렌더 실패: {rr.error}"
        assert (
            expected_text in rr.rendered
        ), f"기대 텍스트 '{expected_text}' 미포함:\n{rr.rendered[:200]}"

    @pytest.mark.parametrize(
        "output_type,raw_json",
        [
            ("summary", VALID_SUMMARY_JSON),
            ("card", VALID_CARD_JSON),
            ("comparison_table", VALID_COMPARISON_TABLE_JSON),
            ("quiz", VALID_QUIZ_JSON),
            ("slide", VALID_SLIDE_JSON),
        ],
    )
    def test_render_result_has_raw_data(self, output_type: str, raw_json: str):
        """렌더 결과에 raw_data가 포함된다."""
        rr = render(raw_json, output_type)
        assert rr.success is True
        assert rr.raw_data is not None
        assert isinstance(rr.raw_data, dict)

    @pytest.mark.parametrize(
        "output_type,raw_json",
        [
            ("summary", VALID_SUMMARY_JSON),
            ("card", VALID_CARD_JSON),
            ("comparison_table", VALID_COMPARISON_TABLE_JSON),
            ("quiz", VALID_QUIZ_JSON),
            ("slide", VALID_SLIDE_JSON),
        ],
    )
    def test_rendered_contains_citation(self, output_type: str, raw_json: str):
        """렌더 결과에 출처(citation/source)가 포함된다."""
        rr = render(raw_json, output_type)
        assert rr.success is True
        # 모든 출력 타입은 citation/source를 포함해야 한다
        rendered_lower = rr.rendered.lower()
        assert "출처" in rendered_lower or "`" in rr.rendered


# ---------------------------------------------------------------------------
# Markdown 코드 블록 감싸기 테스트
# ---------------------------------------------------------------------------


class TestJsonInMarkdownCodeBlock:
    """LLM이 JSON을 markdown 코드 블록에 감싸서 반환하는 경우."""

    @pytest.mark.parametrize(
        "output_type,raw_json",
        [
            ("summary", VALID_SUMMARY_JSON),
            ("quiz", VALID_QUIZ_JSON),
            ("slide", VALID_SLIDE_JSON),
        ],
    )
    def test_code_block_parsing(self, output_type: str, raw_json: str):
        """```json 코드 블록 안의 JSON도 정상 처리."""
        wrapped = f"```json\n{raw_json}\n```"

        vr = validate_content_output(wrapped, output_type)
        assert vr.passed is True

        rr = render(wrapped, output_type)
        assert rr.success is True

    @pytest.mark.parametrize(
        "output_type,raw_json",
        [
            ("card", VALID_CARD_JSON),
            ("comparison_table", VALID_COMPARISON_TABLE_JSON),
        ],
    )
    def test_triple_backtick_without_lang(self, output_type: str, raw_json: str):
        """``` 코드 블록 (언어 지정 없음)도 정상 처리."""
        wrapped = f"```\n{raw_json}\n```"

        vr = validate_content_output(wrapped, output_type)
        assert vr.passed is True

        rr = render(wrapped, output_type)
        assert rr.success is True

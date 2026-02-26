"""콘텐츠 생성 출력 스키마 검증 (PR-7).

Pydantic v2 모델로 content_generation 출력의 스키마와
근거 커버리지(quote_id) 규칙을 검증한다.

output_type별 규칙:
  - card:  카드당 citations에 quote_id 1~2개 필수
  - quiz:  정답 근거 citations에 quote_id 1개 필수
  - comparison_table: rows마다 quote_id 필수
  - summary: citations에 quote_id 1개 이상 필수
  - slide:  sources에 quote_id 1개 이상 필수
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict | list | None:
    """LLM 응답에서 JSON을 추출한다.

    ```json ... ``` 블록, ``` ... ``` 블록, 또는 순수 JSON을 시도한다.
    """
    # 1. ```json ... ``` 블록
    if "```json" in text:
        try:
            block = text.split("```json")[1].split("```")[0].strip()
            return json.loads(block)
        except (json.JSONDecodeError, IndexError):
            pass

    # 2. ``` ... ``` 블록
    if "```" in text:
        try:
            block = text.split("```")[1].split("```")[0].strip()
            return json.loads(block)
        except (json.JSONDecodeError, IndexError):
            pass

    # 3. 순수 JSON (배열 또는 객체)
    for start_char in ("{", "["):
        idx = text.find(start_char)
        if idx >= 0:
            try:
                return json.loads(text[idx:])
            except json.JSONDecodeError:
                pass

    return None


def _is_valid_quote_id(qid: str) -> bool:
    """quote_id 형식 검증 (edition|section|type|number — 4 segments)."""
    if not qid:
        return False
    parts = qid.split("|")
    return len(parts) >= 4 and all(p.strip() for p in parts)


# ---------------------------------------------------------------------------
# Pydantic models — output_type별 스키마
# ---------------------------------------------------------------------------


class SummaryOutput(BaseModel):
    """요약 출력 스키마."""

    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=10, max_length=600)
    key_points: list[str] = Field(min_length=1, max_length=5)
    citations: list[str] = Field(min_length=1)

    @field_validator("citations")
    @classmethod
    def citations_have_quote_ids(cls, v: list[str]) -> list[str]:
        valid = [c for c in v if _is_valid_quote_id(c)]
        if not valid:
            raise ValueError("citations에 유효한 quote_id가 1개 이상 필요합니다")
        return v


class CardOutput(BaseModel):
    """카드 출력 스키마."""

    front: str = Field(min_length=1)
    back: str = Field(min_length=1)
    edition_tag: str = ""
    citations: list[str] = Field(min_length=1, max_length=2)

    @field_validator("citations")
    @classmethod
    def citations_have_quote_ids(cls, v: list[str]) -> list[str]:
        valid = [c for c in v if _is_valid_quote_id(c)]
        if not valid:
            raise ValueError("카드당 citations에 유효한 quote_id 1~2개 필수")
        return v


class CardListOutput(BaseModel):
    """카드 목록 출력 스키마."""

    cards: list[CardOutput] = Field(min_length=1)


class QuizOutput(BaseModel):
    """퀴즈 출력 스키마."""

    question: str = Field(min_length=1)
    choices: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=1)
    citations: list[str] = Field(min_length=1)

    @field_validator("citations")
    @classmethod
    def citations_have_quote_ids(cls, v: list[str]) -> list[str]:
        valid = [c for c in v if _is_valid_quote_id(c)]
        if not valid:
            raise ValueError("정답 근거 citations에 유효한 quote_id 1개 필수")
        return v


class QuizListOutput(BaseModel):
    """퀴즈 목록 출력 스키마."""

    quizzes: list[QuizOutput] = Field(min_length=1)


class ComparisonRow(BaseModel):
    """비교표 행 스키마."""

    aspect: str = Field(min_length=1)
    values: dict[str, str] = Field(min_length=1)
    quote_ids: list[str] = Field(min_length=1)

    @field_validator("quote_ids")
    @classmethod
    def row_has_quote_ids(cls, v: list[str]) -> list[str]:
        valid = [c for c in v if _is_valid_quote_id(c)]
        if not valid:
            raise ValueError("비교 행에 유효한 quote_id 필수")
        return v


class ComparisonTableOutput(BaseModel):
    """비교표 출력 스키마."""

    concept: str = Field(min_length=1)
    columns: list[str] = Field(min_length=2)
    rows: list[ComparisonRow] = Field(min_length=1)
    evolution_summary: str = ""


class SlideOutput(BaseModel):
    """슬라이드 출력 스키마."""

    slide_number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=80)
    body: list[str] = Field(min_length=1, max_length=5)
    sources: list[str] = Field(min_length=1)

    @field_validator("sources")
    @classmethod
    def sources_have_quote_ids(cls, v: list[str]) -> list[str]:
        valid = [c for c in v if _is_valid_quote_id(c)]
        if not valid:
            raise ValueError("슬라이드당 sources에 유효한 quote_id 1개 이상 필수")
        return v


class SlideListOutput(BaseModel):
    """슬라이드 목록 출력 스키마."""

    slides: list[SlideOutput] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


class ValidationResult:
    """스키마 검증 결과를 담는 immutable 객체."""

    __slots__ = ("_passed", "_errors", "_output_type", "_parsed")

    def __init__(
        self,
        passed: bool,
        errors: list[str],
        output_type: str,
        parsed: Any = None,
    ) -> None:
        self._passed = passed
        self._errors = tuple(errors)
        self._output_type = output_type
        self._parsed = parsed

    @property
    def passed(self) -> bool:
        return self._passed

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    @property
    def output_type(self) -> str:
        return self._output_type

    @property
    def parsed(self) -> Any:
        return self._parsed

    def to_dict(self) -> dict:
        """trace 기록용 dict."""
        return {
            "passed": self._passed,
            "output_type": self._output_type,
            "error_count": len(self._errors),
            "errors": list(self._errors)[:5],  # 최대 5개 오류만 기록
        }


# ---------------------------------------------------------------------------
# Safe error extraction
# ---------------------------------------------------------------------------


def _safe_errors(exc: ValidationError) -> list[str]:
    """Pydantic ValidationError에서 안전한 오류 메시지만 추출한다.

    str(e)는 LLM 생성 필드 값을 포함할 수 있으므로,
    err["msg"] (Pydantic 정의 메시지)만 사용하여 데이터 유출을 방지한다.
    """
    msgs: list[str] = []
    for err in exc.errors():
        loc = " → ".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "검증 실패")
        if loc:
            msgs.append(f"{loc}: {msg}")
        else:
            msgs.append(msg)
    return msgs


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

# output_type → (단일 모델, 목록 모델, 목록 키)
_MODEL_MAP: dict[str, tuple[type[BaseModel], type[BaseModel] | None, str | None]] = {
    "summary": (SummaryOutput, None, None),
    "card": (CardOutput, CardListOutput, "cards"),
    "quiz": (QuizOutput, QuizListOutput, "quizzes"),
    "comparison_table": (ComparisonTableOutput, None, None),
    "slide": (SlideOutput, SlideListOutput, "slides"),
}


def validate_content_output(
    raw_answer: str,
    output_type: str,
) -> ValidationResult:
    """LLM 응답을 output_type에 맞는 스키마로 검증한다.

    Args:
        raw_answer: LLM이 생성한 원문 응답
        output_type: 출력 유형 (summary/card/quiz/comparison_table/slide)

    Returns:
        ValidationResult (passed, errors, output_type, parsed)
    """
    if output_type not in _MODEL_MAP:
        return ValidationResult(
            passed=False,
            errors=[f"알 수 없는 output_type: {output_type}"],
            output_type=output_type,
        )

    single_model, list_model, list_key = _MODEL_MAP[output_type]

    # JSON 추출
    data = _extract_json(raw_answer)
    if data is None:
        return ValidationResult(
            passed=False,
            errors=["LLM 응답에서 JSON을 추출할 수 없습니다"],
            output_type=output_type,
        )

    errors: list[str] = []

    # 배열이면 목록 모델로 검증
    if isinstance(data, list):
        if list_model and list_key:
            try:
                parsed = list_model.model_validate({list_key: data})
                return ValidationResult(
                    passed=True,
                    errors=[],
                    output_type=output_type,
                    parsed=parsed,
                )
            except ValidationError as e:
                errors.extend(_safe_errors(e))
        else:
            # 단일 모델만 지원하는 타입에 배열이 온 경우
            if len(data) > 0 and isinstance(data[0], dict):
                try:
                    parsed = single_model.model_validate(data[0])
                    return ValidationResult(
                        passed=True,
                        errors=[],
                        output_type=output_type,
                        parsed=parsed,
                    )
                except ValidationError as e:
                    errors.extend(_safe_errors(e))
            else:
                errors.append("배열 형식이지만 유효한 항목이 없습니다")

    # 객체이면 단일 모델로 검증
    elif isinstance(data, dict):
        # 목록 키가 dict 안에 있으면 목록 모델로
        if list_key and list_key in data:
            if list_model:
                try:
                    parsed = list_model.model_validate(data)
                    return ValidationResult(
                        passed=True,
                        errors=[],
                        output_type=output_type,
                        parsed=parsed,
                    )
                except ValidationError as e:
                    errors.extend(_safe_errors(e))

        # 단일 모델로 시도
        try:
            parsed = single_model.model_validate(data)
            return ValidationResult(
                passed=True,
                errors=[],
                output_type=output_type,
                parsed=parsed,
            )
        except ValidationError as e:
            if not errors:
                errors.extend(_safe_errors(e))

    else:
        errors.append(f"예상치 못한 JSON 타입: {type(data).__name__}")

    return ValidationResult(
        passed=False,
        errors=errors,
        output_type=output_type,
    )

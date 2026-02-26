"""GenerationService — LLM 답변 생성 + 검증 서비스.

PR-012: 04_retrieve_and_answer.py에서 추출한 생성 파이프라인.

GenerationService는 context formatting, LLM 호출, 출력 검증을 담당한다.
테스트 시 client를 mock으로 교체할 수 있다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scripts.lib.output_validator import validate_content_output
from scripts.lib.retrieval import edition_sort_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GenerationConfig — 생성 설정 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationConfig:
    """LLM 생성 설정."""

    model: str
    max_tokens: int
    router_model: str
    router_max_tokens: int
    max_retries: int
    prompts_dir: str

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> GenerationConfig:
        """YAML 파일에서 설정을 로드한다."""
        defaults = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 3000,
            "router_model": "claude-sonnet-4-20250514",
            "router_max_tokens": 500,
            "max_retries": 1,
            "prompts_dir": "prompts",
        }

        if path and path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            gen = data.get("generation", {})
            for key in defaults:
                if key in gen:
                    defaults[key] = gen[key]

        return cls(**defaults)


# ---------------------------------------------------------------------------
# GenerationResult — 생성 결과 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationResult:
    """LLM 답변 생성 결과."""

    answer: str
    prompt_name: str
    validation_passed: bool | None  # None = 검증 대상 아님
    validation_errors: tuple[str, ...]
    retried: bool
    context_token_estimate: int


# ---------------------------------------------------------------------------
# TemporalConflict — 시간축 충돌 정보 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemporalConflict:
    """시간축 충돌 감지 결과."""

    has_conflict: bool
    conflicting_editions: tuple[str, ...]
    definition_count: int


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------


def detect_temporal_conflicts(hits: list[dict]) -> TemporalConflict:
    """검색 결과에서 시간축 충돌을 감지한다.

    조건: definition 타입 quote가 2개 이상의 개정판에 걸쳐 존재하면 충돌.
    """
    edition_defs: dict[str, int] = {}

    for h in hits:
        quote_type = h.get("type", "narrative")
        if quote_type == "definition":
            edition_id = h.get("edition", "unknown")
            edition_defs[edition_id] = edition_defs.get(edition_id, 0) + 1

    conflicting_editions = tuple(sorted(edition_defs.keys(), key=edition_sort_key))
    total_defs = sum(edition_defs.values())

    return TemporalConflict(
        has_conflict=len(conflicting_editions) >= 2,
        conflicting_editions=conflicting_editions,
        definition_count=total_defs,
    )


def format_context(
    hits: list[dict],
    intent: str,
    conflict: TemporalConflict,
    output_type: str | None = None,
    output_specs: dict | None = None,
) -> str:
    """검색 결과를 프롬프트 컨텍스트 형식으로 포맷팅한다."""
    parts: list[str] = []

    # [METADATA] 블록
    metadata_block = (
        f"[METADATA]\n"
        f"intent: {intent}\n"
        f"temporal_conflict: {'true' if conflict.has_conflict else 'false'}\n"
        f"conflicting_editions: {json.dumps(list(conflict.conflicting_editions), ensure_ascii=False)}\n"
        f"output_type: {output_type or 'null'}\n"
    )

    if intent == "content_generation" and output_type and output_specs:
        spec = output_specs.get("output_types", {}).get(output_type, {})
        metadata_block += f"output_specs: {json.dumps(spec, ensure_ascii=False) if spec else 'null'}\n"
    else:
        metadata_block += "output_specs: null\n"

    parts.append(metadata_block)

    # [CHUNK n] 블록
    for i, hit in enumerate(hits, start=1):
        edition = hit.get("edition", "unknown")
        chapter_path = hit.get("chapter_path", [])
        section = (
            " > ".join(str(item) for item in chapter_path)
            if chapter_path
            else "unknown"
        )
        quality_flags = hit.get("quality_flags", [])
        quote_type = hit.get("type", "narrative")

        part = (
            f"[CHUNK {i}]\n"
            f"quote_id: {hit.get('quote_id', 'unknown')}\n"
            f"edition: {edition}\n"
            f"section: {section}\n"
            f"type: {quote_type}\n"
            f"quality_flags: {quality_flags}\n"
            f"---\n"
            f"{hit.get('text', '')}\n"
        )
        parts.append(part)

    return "\n".join(parts)


def extract_quote_ids(hits: list[dict]) -> tuple[str, ...]:
    """검색 결과에서 quote_id 목록을 추출한다."""
    return tuple(h.get("quote_id", "") for h in hits if h.get("quote_id"))


# ---------------------------------------------------------------------------
# GenerationService
# ---------------------------------------------------------------------------


class GenerationService:
    """LLM 답변 생성 서비스.

    - context formatting
    - LLM 호출 (Anthropic Messages API)
    - 출력 검증 + 재시도
    - config 기반 모델/파라미터 관리
    """

    def __init__(
        self,
        client: Any,
        config: GenerationConfig | None = None,
    ) -> None:
        self._client = client
        self._config = config or GenerationConfig.from_yaml()
        self._prompts: dict[str, str] = {}

    def load_prompts(self, prompts_dir: Path | None = None) -> None:
        """프롬프트 파일을 로드한다."""
        base = prompts_dir or Path(self._config.prompts_dir)
        for name in ("answer", "content_gen", "router"):
            path = base / f"{name}.md"
            if path.exists():
                self._prompts[name] = path.read_text(encoding="utf-8")

    def get_prompt(self, name: str) -> str | None:
        """로드된 프롬프트를 반환한다."""
        return self._prompts.get(name)

    def select_prompt(self, intent: str) -> tuple[str, str]:
        """의도에 따라 적절한 프롬프트를 선택한다.

        Returns:
            (prompt_text, prompt_name)
        """
        if intent == "content_generation":
            prompt = self._prompts.get("content_gen")
            if prompt:
                return prompt, "content_gen.md"
        prompt = self._prompts.get("answer", "")
        return prompt, "answer.md"

    def generate(
        self,
        query: str,
        context: str,
        intent: str,
        output_type: str | None = None,
    ) -> GenerationResult:
        """LLM 답변을 생성하고, content_generation이면 검증 + 재시도한다.

        Args:
            query: 사용자 질의.
            context: format_context()로 생성된 컨텍스트.
            intent: 질의 의도.
            output_type: 출력 유형 (content_generation 시).

        Returns:
            GenerationResult (불변).
        """
        system_prompt, prompt_name = self.select_prompt(intent)
        answer = self._call_llm(query, context, system_prompt)
        context_tokens = _estimate_tokens(context)

        # content_generation이 아니면 검증 없이 반환
        if intent != "content_generation" or not output_type:
            return GenerationResult(
                answer=answer,
                prompt_name=prompt_name,
                validation_passed=None,
                validation_errors=(),
                retried=False,
                context_token_estimate=context_tokens,
            )

        # 출력 스키마 검증
        validation = validate_content_output(answer, output_type)
        if validation.passed:
            return GenerationResult(
                answer=answer,
                prompt_name=prompt_name,
                validation_passed=True,
                validation_errors=(),
                retried=False,
                context_token_estimate=context_tokens,
            )

        # 재시도
        errors = tuple(validation.errors[:3])
        for _ in range(self._config.max_retries):
            retry_hint = (
                f"\n\n[시스템] 이전 응답이 {output_type} JSON 스키마를 "
                f"충족하지 못했습니다. 올바른 JSON 형식으로 다시 생성해 주세요."
            )
            retry_answer = self._call_llm(query, context + retry_hint, system_prompt)
            retry_validation = validate_content_output(retry_answer, output_type)
            if retry_validation.passed:
                return GenerationResult(
                    answer=retry_answer,
                    prompt_name=prompt_name,
                    validation_passed=True,
                    validation_errors=(),
                    retried=True,
                    context_token_estimate=context_tokens,
                )

        # 재시도 실패 — 원본 반환
        return GenerationResult(
            answer=answer,
            prompt_name=prompt_name,
            validation_passed=False,
            validation_errors=errors,
            retried=True,
            context_token_estimate=context_tokens,
        )

    def _call_llm(self, query: str, context: str, system_prompt: str) -> str:
        """LLM API를 호출한다.

        Raises:
            RuntimeError: API 호출 실패 시.
        """
        user_message = f"## 질의\n\n{query}\n\n## 컨텍스트\n\n{context}"

        try:
            message = self._client.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return message.content[0].text
        except Exception as e:
            logger.error("LLM API 호출 실패: %s", e)
            raise RuntimeError(f"LLM API 호출 실패: {e}") from e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """텍스트의 토큰 수를 추정한다. (한국어: ~1.5자/토큰)"""
    if not text:
        return 0
    korean_chars = sum(1 for c in text if "\uac00" <= c <= "\ud7a3")
    other_chars = len(text) - korean_chars
    return int(korean_chars / 1.5 + other_chars / 4)

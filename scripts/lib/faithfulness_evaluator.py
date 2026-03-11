"""FaithfulnessEvaluator -- claim-level binary faithfulness judgment.

Likert 1-5 scoring is imprecise for hallucination detection.
This module extracts individual claims from an LLM answer and judges
each one as grounded or hallucinated against the retrieved contexts.

Two evaluation modes:
- evaluate()             : LLM-based (Anthropic Messages API)
- evaluate_without_llm() : keyword / substring heuristic (for tests)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models (immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """A single factual claim extracted from an answer.

    Attributes:
        text: The claim sentence.
        is_grounded: Whether the claim is supported by a retrieved context.
        supporting_quote_id: quote_id of the supporting context, or None.
    """

    text: str
    is_grounded: bool
    supporting_quote_id: str | None = None


@dataclass(frozen=True)
class FaithfulnessResult:
    """Aggregate faithfulness evaluation result.

    Attributes:
        is_faithful: True when every claim is grounded.
        claims: Individual claim judgments.
        grounded_count: Number of grounded claims.
        hallucinated_count: Number of hallucinated claims.
        grounded_ratio: grounded / total (0.0 when no claims).
    """

    is_faithful: bool
    claims: tuple[Claim, ...]
    grounded_count: int
    hallucinated_count: int
    grounded_ratio: float


# ---------------------------------------------------------------------------
# LLM client protocol (for dependency injection)
# ---------------------------------------------------------------------------


class _MessageContent(Protocol):
    """Minimal protocol for a single content block."""

    text: str


class _Message(Protocol):
    """Minimal protocol for a Messages API response."""

    content: list[_MessageContent]


class LLMClient(Protocol):
    """Minimal protocol matching anthropic.Anthropic().messages interface."""

    class messages:  # noqa: N801
        @staticmethod
        def create(
            *,
            model: str,
            max_tokens: int,
            system: str,
            messages: list[dict[str, str]],
        ) -> _Message:
            ...


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_EXTRACT_CLAIMS_SYSTEM = """\
You are a claim extractor.  Given an answer text, extract every distinct
factual claim as a JSON array of strings.  Each element should be a single
atomic factual statement.  Omit hedging language, meta-commentary, and
greeting/closing phrases.  Return ONLY a JSON array, no markdown fences."""

_JUDGE_CLAIM_SYSTEM = """\
You are a faithfulness judge.  Given a CLAIM and a list of CONTEXTS
(each with a quote_id), determine whether the claim is grounded in the
contexts.

Return ONLY a JSON object:
{
  "is_grounded": true | false,
  "supporting_quote_id": "<quote_id or null>"
}

Rules:
- "is_grounded" is true ONLY if the claim can be directly inferred from
  at least one context passage.
- If grounded, set "supporting_quote_id" to the quote_id of the best
  supporting context.  Otherwise set it to null.
- Do NOT add markdown fences."""


# ---------------------------------------------------------------------------
# FaithfulnessEvaluator
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_DEFAULT_MAX_TOKENS = 1024


class FaithfulnessEvaluator:
    """Claim-level binary faithfulness evaluator.

    Args:
        client: An object whose ``.messages`` attribute exposes a ``create``
            method compatible with the Anthropic Messages API.
        model: Model name for LLM calls.
        max_tokens: Max tokens per LLM call.
    """

    def __init__(
        self,
        client: Any,
        *,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    # -- public API ---------------------------------------------------------

    def evaluate(
        self,
        answer: str,
        contexts: list[dict[str, str]],
    ) -> FaithfulnessResult:
        """Evaluate faithfulness using LLM calls.

        Args:
            answer: The generated answer text.
            contexts: List of dicts with at least ``quote_id`` and ``text``.

        Returns:
            FaithfulnessResult (immutable).
        """
        if not answer or not answer.strip():
            return _empty_result()

        # Step 1: extract claims via LLM
        claim_texts = self._extract_claims(answer)
        if not claim_texts:
            return _empty_result()

        # Step 2: judge each claim
        claims: list[Claim] = []
        for ct in claim_texts:
            claim = self._judge_claim(ct, contexts)
            claims = [*claims, claim]

        return _build_result(tuple(claims))

    # -- LLM helpers --------------------------------------------------------

    def _extract_claims(self, answer: str) -> list[str]:
        """Extract factual claims from *answer* via LLM."""
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_EXTRACT_CLAIMS_SYSTEM,
                messages=[{"role": "user", "content": answer}],
            )
            raw = message.content[0].text.strip()
            parsed = json.loads(_strip_markdown_fences(raw))
            if isinstance(parsed, list):
                return [str(c) for c in parsed if c]
            return []
        except Exception:
            logger.warning("Claim extraction failed", exc_info=True)
            return []

    def _judge_claim(
        self,
        claim_text: str,
        contexts: list[dict[str, str]],
    ) -> Claim:
        """Judge a single *claim_text* against *contexts* via LLM."""
        context_block = "\n\n".join(
            f"[quote_id: {c.get('quote_id', 'unknown')}]\n{c.get('text', '')}"
            for c in contexts
        )
        user_content = f"CLAIM:\n{claim_text}\n\nCONTEXTS:\n{context_block}"

        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=_JUDGE_CLAIM_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = message.content[0].text.strip()
            parsed = json.loads(_strip_markdown_fences(raw))
            is_grounded = bool(parsed.get("is_grounded", False))
            supporting = parsed.get("supporting_quote_id") or None
            return Claim(
                text=claim_text,
                is_grounded=is_grounded,
                supporting_quote_id=supporting if is_grounded else None,
            )
        except Exception:
            logger.warning("Claim judgment failed for: %s", claim_text, exc_info=True)
            # Conservative: treat parse failure as hallucinated
            return Claim(text=claim_text, is_grounded=False)


# ---------------------------------------------------------------------------
# evaluate_without_llm — keyword / substring heuristic
# ---------------------------------------------------------------------------


def evaluate_without_llm(
    answer: str,
    contexts: list[dict[str, str]],
    *,
    min_overlap_chars: int = 8,
) -> FaithfulnessResult:
    """Lightweight faithfulness check without LLM calls.

    Splits the answer into sentence-level claims and checks whether each
    sentence shares a significant substring with at least one context.

    Args:
        answer: The generated answer text.
        contexts: List of dicts with at least ``quote_id`` and ``text``.
        min_overlap_chars: Minimum shared substring length to count as
            grounded.

    Returns:
        FaithfulnessResult (immutable).
    """
    if not answer or not answer.strip():
        return _empty_result()

    sentences = _split_sentences(answer)
    if not sentences:
        return _empty_result()

    claims: list[Claim] = []
    for sentence in sentences:
        grounded, quote_id = _check_sentence_grounding(
            sentence,
            contexts,
            min_overlap_chars=min_overlap_chars,
        )
        claims = [
            *claims,
            Claim(
                text=sentence,
                is_grounded=grounded,
                supporting_quote_id=quote_id,
            ),
        ]

    return _build_result(tuple(claims))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_result() -> FaithfulnessResult:
    """Return a vacuously faithful empty result."""
    return FaithfulnessResult(
        is_faithful=True,
        claims=(),
        grounded_count=0,
        hallucinated_count=0,
        grounded_ratio=1.0,
    )


def _build_result(claims: tuple[Claim, ...]) -> FaithfulnessResult:
    """Aggregate a tuple of Claims into a FaithfulnessResult."""
    if not claims:
        return _empty_result()

    grounded = sum(1 for c in claims if c.is_grounded)
    hallucinated = len(claims) - grounded
    return FaithfulnessResult(
        is_faithful=hallucinated == 0,
        claims=claims,
        grounded_count=grounded,
        hallucinated_count=hallucinated,
        grounded_ratio=grounded / len(claims),
    )


def _split_sentences(text: str) -> list[str]:
    """Split text into non-empty sentence-level segments."""
    # Split on Korean/English sentence terminators
    parts = re.split(r"(?<=[.!?\u3002])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _check_sentence_grounding(
    sentence: str,
    contexts: list[dict[str, str]],
    *,
    min_overlap_chars: int = 8,
) -> tuple[bool, str | None]:
    """Check if *sentence* is grounded in any context via substring overlap.

    Returns (is_grounded, supporting_quote_id).
    """
    # Normalize whitespace for matching
    norm_sentence = re.sub(r"\s+", " ", sentence).strip()

    for ctx in contexts:
        ctx_text = ctx.get("text", "")
        if not ctx_text:
            continue
        norm_ctx = re.sub(r"\s+", " ", ctx_text).strip()

        # Check for any shared substring of sufficient length
        overlap_len = _longest_common_substring_length(norm_sentence, norm_ctx)
        if overlap_len >= min_overlap_chars:
            return True, ctx.get("quote_id")

    return False, None


def _longest_common_substring_length(a: str, b: str) -> int:
    """Return the length of the longest common substring between *a* and *b*.

    Uses a single-row DP approach (O(n*m) time, O(m) space).
    """
    if not a or not b:
        return 0

    # Use shorter string for columns to save memory
    if len(a) < len(b):
        a, b = b, a

    m = len(b)
    prev = [0] * (m + 1)
    best = 0

    for ch_a in a:
        curr = [0] * (m + 1)
        for j, ch_b in enumerate(b):
            if ch_a == ch_b:
                curr[j + 1] = prev[j] + 1
                if curr[j + 1] > best:
                    best = curr[j + 1]
        prev = curr

    return best


def _strip_markdown_fences(text: str) -> str:
    """Remove optional ```json ... ``` fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        text = re.sub(r"^```\w*\n?", "", text)
    if text.endswith("```"):
        text = text[: -len("```")]
    return text.strip()

"""OutputRenderer 테스트.

PR-026: 3종 출력 렌더러 (summary/card/comparison_table) 단위/통합 테스트.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.output_renderer import (  # noqa: E402
    RenderResult,
    render,
    render_card,
    render_card_list,
    render_comparison_table,
    render_summary,
)
from scripts.lib.output_validator import (  # noqa: E402
    CardListOutput,
    CardOutput,
    ComparisonRow,
    ComparisonTableOutput,
    SummaryOutput,
)


# ---------------------------------------------------------------------------
# RenderResult 테스트
# ---------------------------------------------------------------------------


class TestRenderResult:
    """RenderResult frozen dataclass 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        r = RenderResult(
            output_type="summary",
            rendered="test",
            raw_data=None,
            success=True,
            error="",
        )
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]

    def test_fields(self):
        """필드 접근."""
        r = RenderResult(
            output_type="card",
            rendered="rendered text",
            raw_data={"front": "Q"},
            success=True,
            error="",
        )
        assert r.output_type == "card"
        assert r.rendered == "rendered text"
        assert r.success is True


# ---------------------------------------------------------------------------
# render_summary 테스트
# ---------------------------------------------------------------------------


class TestRenderSummary:
    """render_summary 함수 테스트."""

    def test_basic(self):
        """기본 요약 렌더링."""
        data = SummaryOutput(
            title="VWBE 문화의 핵심",
            body="14차 개정판에서 도입된 VWBE 문화는 자발적 의욕적 두뇌활용을 의미합니다.",
            key_points=["VWBE = 자발적 의욕적 두뇌활용", "14차 개정판에서 신설"],
            citations=["2020-14차|_root|principle|001"],
        )
        result = render_summary(data)

        assert "### VWBE 문화의 핵심" in result
        assert "자발적 의욕적 두뇌활용" in result
        assert "**핵심 포인트:**" in result
        assert "- VWBE = 자발적 의욕적 두뇌활용" in result
        assert "**출처:**" in result
        assert "`2020-14차|_root|principle|001`" in result

    def test_single_key_point(self):
        """핵심 포인트 1개."""
        data = SummaryOutput(
            title="제목",
            body="본문 텍스트입니다. 충분히 길어야 합니다.",
            key_points=["포인트 1"],
            citations=["a|b|c|d"],
        )
        result = render_summary(data)
        assert "- 포인트 1" in result

    def test_multiple_citations(self):
        """여러 출처."""
        data = SummaryOutput(
            title="제목",
            body="본문입니다. 여러 출처가 있습니다.",
            key_points=["포인트"],
            citations=["a|b|c|d", "e|f|g|h"],
        )
        result = render_summary(data)
        assert result.count("`") == 4  # 2 citations × 2 backticks


# ---------------------------------------------------------------------------
# render_card 테스트
# ---------------------------------------------------------------------------


class TestRenderCard:
    """render_card 함수 테스트."""

    def test_basic(self):
        """기본 카드 렌더링."""
        data = CardOutput(
            front="VWBE란?",
            back="자발적 의욕적 두뇌활용",
            edition_tag="2020-14차",
            citations=["2020-14차|_root|principle|005"],
        )
        result = render_card(data)

        assert "**Q:** VWBE란? (2020-14차)" in result
        assert "**A:** 자발적 의욕적 두뇌활용" in result
        assert "출처:" in result
        assert "---" in result

    def test_no_edition_tag(self):
        """edition_tag 없는 카드."""
        data = CardOutput(
            front="질문",
            back="답변",
            edition_tag="",
            citations=["a|b|c|d"],
        )
        result = render_card(data)
        assert "**Q:** 질문" in result
        assert "()" not in result  # 빈 태그는 표시 안 함

    def test_two_citations(self):
        """2개 출처."""
        data = CardOutput(
            front="Q",
            back="A",
            citations=["a|b|c|d", "e|f|g|h"],
        )
        result = render_card(data)
        assert "`a|b|c|d`" in result
        assert "`e|f|g|h`" in result


# ---------------------------------------------------------------------------
# render_card_list 테스트
# ---------------------------------------------------------------------------


class TestRenderCardList:
    """render_card_list 함수 테스트."""

    def test_basic(self):
        """기본 카드 목록."""
        cards = CardListOutput(
            cards=[
                CardOutput(front="Q1", back="A1", citations=["a|b|c|d"]),
                CardOutput(front="Q2", back="A2", citations=["e|f|g|h"]),
            ]
        )
        result = render_card_list(cards)

        assert "## 지식 카드 (2장)" in result
        assert "### 카드 1" in result
        assert "### 카드 2" in result
        assert "**Q:** Q1" in result
        assert "**Q:** Q2" in result

    def test_single_card(self):
        """1장 카드 목록."""
        cards = CardListOutput(
            cards=[CardOutput(front="Q", back="A", citations=["a|b|c|d"])]
        )
        result = render_card_list(cards)
        assert "## 지식 카드 (1장)" in result


# ---------------------------------------------------------------------------
# render_comparison_table 테스트
# ---------------------------------------------------------------------------


class TestRenderComparisonTable:
    """render_comparison_table 함수 테스트."""

    def test_basic(self):
        """기본 비교표."""
        data = ComparisonTableOutput(
            concept="의욕관리",
            columns=["1979-초판", "2020-14차"],
            rows=[
                ComparisonRow(
                    aspect="정의",
                    values={
                        "1979-초판": "구성원의 근무 의욕을 높이기 위한 활동",
                        "2020-14차": "VWBE 문화의 핵심 구성요소",
                    },
                    quote_ids=["1979-초판|_root|def|001", "2020-14차|_root|def|002"],
                ),
            ],
            evolution_summary="의욕관리는 VWBE의 하위 개념으로 통합되었다.",
        )
        result = render_comparison_table(data)

        assert "### 의욕관리 — 개정판 비교" in result
        assert "| 항목 | 1979-초판 | 2020-14차 |" in result
        assert "| 정의 |" in result
        assert "**변화 요약:**" in result
        assert "`1979-초판|_root|def|001`" in result

    def test_no_evolution_summary(self):
        """진화 요약 없음."""
        data = ComparisonTableOutput(
            concept="테스트",
            columns=["A", "B"],
            rows=[
                ComparisonRow(
                    aspect="항목",
                    values={"A": "값1", "B": "값2"},
                    quote_ids=["a|b|c|d"],
                ),
            ],
            evolution_summary="",
        )
        result = render_comparison_table(data)
        assert "**변화 요약:**" not in result

    def test_missing_column_value(self):
        """열 값이 없으면 '—' 표시."""
        data = ComparisonTableOutput(
            concept="테스트",
            columns=["A", "B"],
            rows=[
                ComparisonRow(
                    aspect="항목",
                    values={"A": "값1"},  # B 누락
                    quote_ids=["a|b|c|d"],
                ),
            ],
        )
        result = render_comparison_table(data)
        assert "—" in result

    def test_long_value_truncated(self):
        """긴 셀 값 축약."""
        long_val = "가" * 100
        data = ComparisonTableOutput(
            concept="테스트",
            columns=["A", "B"],
            rows=[
                ComparisonRow(
                    aspect="항목",
                    values={"A": long_val, "B": "짧은값"},
                    quote_ids=["a|b|c|d"],
                ),
            ],
        )
        result = render_comparison_table(data)
        assert "..." in result

    def test_pipe_escaped(self):
        """파이프 문자 이스케이프."""
        data = ComparisonTableOutput(
            concept="테스트",
            columns=["A", "B"],
            rows=[
                ComparisonRow(
                    aspect="항목",
                    values={"A": "값|포함", "B": "정상"},
                    quote_ids=["a|b|c|d"],
                ),
            ],
        )
        result = render_comparison_table(data)
        assert "값\\|포함" in result

    def test_multiple_rows(self):
        """여러 행."""
        data = ComparisonTableOutput(
            concept="SUPEX",
            columns=["초판", "14차"],
            rows=[
                ComparisonRow(
                    aspect="정의",
                    values={"초판": "최고 수준", "14차": "Super Excellent"},
                    quote_ids=["a|b|c|d"],
                ),
                ComparisonRow(
                    aspect="범위",
                    values={"초판": "전사", "14차": "확장"},
                    quote_ids=["e|f|g|h"],
                ),
            ],
        )
        result = render_comparison_table(data)
        assert "| 정의 |" in result
        assert "| 범위 |" in result

    def test_dedup_quote_ids(self):
        """중복 quote_id 제거."""
        data = ComparisonTableOutput(
            concept="테스트",
            columns=["A", "B"],
            rows=[
                ComparisonRow(
                    aspect="항목1", values={"A": "값", "B": "값"}, quote_ids=["a|b|c|d"]
                ),
                ComparisonRow(
                    aspect="항목2", values={"A": "값", "B": "값"}, quote_ids=["a|b|c|d"]
                ),
            ],
        )
        result = render_comparison_table(data)
        # a|b|c|d가 한 번만 출처에 나타남
        assert result.count("`a|b|c|d`") == 1


# ---------------------------------------------------------------------------
# render() 통합 디스패치 테스트
# ---------------------------------------------------------------------------


class TestRenderDispatch:
    """render() 통합 디스패치 테스트."""

    def test_summary(self):
        """summary 렌더링."""
        raw = json.dumps(
            {
                "title": "SUPEX 요약",
                "body": "SUPEX는 Super Excellent 수준을 추구하는 것입니다.",
                "key_points": ["최고 수준 추구"],
                "citations": ["2020-14차|_root|def|001"],
            },
            ensure_ascii=False,
        )
        result = render(raw, "summary")
        assert result.success is True
        assert "### SUPEX 요약" in result.rendered
        assert result.output_type == "summary"

    def test_card_single(self):
        """단일 카드 렌더링."""
        raw = json.dumps(
            {
                "front": "VWBE란?",
                "back": "자발적 의욕적 두뇌활용",
                "citations": ["a|b|c|d"],
            },
            ensure_ascii=False,
        )
        result = render(raw, "card")
        assert result.success is True
        assert "**Q:** VWBE란?" in result.rendered

    def test_card_list(self):
        """카드 목록 렌더링."""
        raw = json.dumps(
            {
                "cards": [
                    {"front": "Q1", "back": "A1", "citations": ["a|b|c|d"]},
                    {"front": "Q2", "back": "A2", "citations": ["e|f|g|h"]},
                ]
            },
            ensure_ascii=False,
        )
        result = render(raw, "card")
        assert result.success is True
        assert "지식 카드 (2장)" in result.rendered

    def test_card_array(self):
        """카드 배열 렌더링."""
        raw = json.dumps(
            [
                {"front": "Q1", "back": "A1", "citations": ["a|b|c|d"]},
                {"front": "Q2", "back": "A2", "citations": ["e|f|g|h"]},
            ],
            ensure_ascii=False,
        )
        result = render(raw, "card")
        assert result.success is True
        assert "지식 카드 (2장)" in result.rendered

    def test_comparison_table(self):
        """비교표 렌더링."""
        raw = json.dumps(
            {
                "concept": "테스트",
                "columns": ["A", "B"],
                "rows": [
                    {
                        "aspect": "항목",
                        "values": {"A": "값1", "B": "값2"},
                        "quote_ids": ["a|b|c|d"],
                    }
                ],
            },
            ensure_ascii=False,
        )
        result = render(raw, "comparison_table")
        assert result.success is True
        assert "테스트 — 개정판 비교" in result.rendered

    def test_unsupported_type(self):
        """지원하지 않는 타입."""
        result = render("{}", "unknown_type")
        assert result.success is False
        assert "지원하지 않는" in result.error

    def test_invalid_json(self):
        """잘못된 JSON."""
        result = render("이것은 JSON이 아닙니다", "summary")
        assert result.success is False
        assert "JSON 추출 실패" in result.error

    def test_json_in_markdown(self):
        """마크다운 코드 블록 안의 JSON."""
        raw = '```json\n{"title":"제목","body":"본문입니다 충분히 길게 작성합니다.","key_points":["포인트"],"citations":["a|b|c|d"]}\n```'
        result = render(raw, "summary")
        assert result.success is True
        assert "### 제목" in result.rendered

    def test_validation_error(self):
        """스키마 검증 실패."""
        raw = json.dumps(
            {"title": "", "body": "", "key_points": [], "citations": []},
            ensure_ascii=False,
        )
        result = render(raw, "summary")
        assert result.success is False
        assert result.error  # 오류 메시지 존재

"""ContentPlanner — 주제에서 콘텐츠 아웃라인(Plan)을 생성하는 서비스.

PR-043: ContentPlanner — topic to outline generation.

6가지 콘텐츠 유형별 plan 메서드:
- plan_lecture: 강의자료 슬라이드 계획
- plan_card_news: 카드뉴스 계획
- plan_workshop: 워크숍 단계 계획
- plan_audio: 오디오 스크립트 계획
- plan_visualization: 시각화 계획
- plan_quiz: 퀴즈 문항 계획

LLM 클라이언트는 Protocol 기반 DI로 주입한다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.content_studio.models import (
    AudioPlan,
    CardNewsPlan,
    ContentOptions,
    LecturePlan,
    QuizPlan,
    VisualizationPlan,
    WorkshopPlan,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Client Protocol
# ---------------------------------------------------------------------------

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


@runtime_checkable
class LLMClient(Protocol):
    """LLM 클라이언트 프로토콜. generate(prompt) -> str 만 필요."""

    async def generate(self, prompt: str) -> str:
        ...


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------


def _load_prompt(name: str) -> str:
    """prompts/ 디렉토리에서 프롬프트 템플릿을 로드한다."""
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일을 찾을 수 없습니다: {path}")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------


def _parse_json(raw: str) -> dict[str, Any]:
    """LLM 응답에서 JSON을 추출하여 파싱한다.

    코드 펜스(```json ... ```)를 자동으로 제거하고,
    흔한 JSON 구문 오류(trailing comma 등)를 자동 복구한다.
    """
    import re

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])

    # 1차 시도: 그대로 파싱
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2차 시도: JSON 복구
    # trailing comma 제거: ,] → ] / ,} → }
    repaired = re.sub(r",\s*([\]}])", r"\1", text)
    # 줄 끝 누락된 쉼표 추가: "value"\n"key" → "value",\n"key"
    repaired = re.sub(r'(")\s*\n(\s*")', r"\1,\n\2", repaired)
    # }{ 사이 쉼표 누락: }\n{ → },\n{
    repaired = re.sub(r"}\s*\n(\s*\{)", r"},\n\1", repaired)

    return json.loads(repaired)


# ---------------------------------------------------------------------------
# ContentPlanner
# ---------------------------------------------------------------------------


class ContentPlanner:
    """주제에서 콘텐츠 아웃라인(Plan)을 생성하는 서비스.

    Args:
        llm_client: LLMClient 프로토콜을 구현하는 객체.
        config: content_studio.yaml의 'content_studio' 섹션 딕셔너리.
    """

    def __init__(self, llm_client: LLMClient, config: dict[str, Any]) -> None:
        self._llm = llm_client
        self._config = config
        # 전문가 프레임워크 라이브러리 사전 로드
        self._expert_knowledge = _load_prompt("expert_frameworks.md")

    # -----------------------------------------------------------------------
    # Lecture
    # -----------------------------------------------------------------------

    async def plan_lecture(
        self,
        topic: str,
        duration_min: int,
        options: ContentOptions,
    ) -> LecturePlan:
        """강의자료 슬라이드 계획을 생성한다 (Multi-Agent 파이프라인).

        PR-060: Strategist -> Copywriter -> Art Director 3단계 협업 및 슬라이드 최적화.
        """
        import json
        
        lecture_cfg = self._config.get("lecture", {})
        minutes_per_slide = lecture_cfg.get("minutes_per_slide", 2)
        min_slides = lecture_cfg.get("min_slides", 5)
        max_slides = lecture_cfg.get("max_slides", 30)

        target_slide_count = _clamp(
            round(duration_min / minutes_per_slide),
            min_slides,
            max_slides,
        )

        # 1단계: 전략가 (Strategist) - 내러티브 및 분량 설계 (전문가 지식 주입)
        strat_prompt_template = _load_prompt("lecture_strategist.md")
        full_strat_prompt = (
            f"{self._expert_knowledge}\n\n"
            + strat_prompt_template.format(
                topic=topic,
                duration_min=duration_min or 30,
                slide_count=target_slide_count or 10,
                target_audience=options.target_audience,
            )
        )
        strategy_data = await self._call_llm_json(full_strat_prompt)

        # AI 추천 분량 적용
        actual_duration = duration_min or strategy_data.get("recommended_duration", 30)
        actual_slides = strategy_data.get("recommended_slides", target_slide_count)

        strategy_json_str = json.dumps(strategy_data, ensure_ascii=False, indent=2)

        # 2단계: 카피라이터 (Copywriter) - 맥킨지식 텍스트 작성 (전문가 지식 주입)
        copy_prompt_template = _load_prompt("lecture_copywriter.md")
        full_copy_prompt = (
            f"{self._expert_knowledge}\n\n"
            + copy_prompt_template.format(
                topic=topic,
                strategy_json=strategy_json_str,
                target_audience=options.target_audience,
            )
        )
        copy_data = await self._call_llm_json(full_copy_prompt)

        # [Task 3] 내용 과다 슬라이드 실질적 분할 및 재정렬
        copy_data["slides"] = self._split_overflow_slides(copy_data.get("slides", []))

        copy_json_str = json.dumps(copy_data, ensure_ascii=False, indent=2)

        # 3단계: 아트 디렉터 (Art Director) - 시각화 및 레이아웃 확정
        art_prompt_template = _load_prompt("lecture_art_director.md")
        art_prompt = art_prompt_template.format(
            topic=topic,
            copy_json=copy_json_str,
            target_audience=options.target_audience,
        )
        art_data = await self._call_llm_json(art_prompt)

        # 4단계: 수석 에디터 (Quality Reviewer) - 최종 검수 및 퀄리티 정제
        review_prompt_template = _load_prompt("quality_reviewer.md")
        review_prompt = review_prompt_template.format(
            topic=topic,
            final_plan_json=json.dumps(art_data, ensure_ascii=False, indent=2),
            target_audience=options.target_audience,
        )
        final_data = await self._call_llm_json(review_prompt)

        # 최종 데이터 모델 조립
        if "learning_objectives" not in final_data and "learning_objectives" in copy_data:
            final_data["learning_objectives"] = copy_data["learning_objectives"]

        final_data["duration_min"] = actual_duration
        if "recommended_slides" not in final_data:
            final_data["recommended_slides"] = actual_slides
        return LecturePlan.from_dict(final_data)

    def _split_overflow_slides(self, slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """내용이 너무 많은 슬라이드를 논리적으로 분할한다."""
        new_slides = []
        for slide in slides:
            points = slide.get("key_points", [])
            if len(points) > 5:
                # 1번 슬라이드: 앞쪽 3개 포인트
                s1 = slide.copy()
                s1["key_points"] = points[:3]
                s1["design_hint"] = "내용 분할 - 도입부 강조"
                new_slides.append(s1)

                # 2번 슬라이드: 뒤쪽 포인트
                s2 = slide.copy()
                s2["title"] = f"{slide['title']} (계속)"
                s2["key_points"] = points[3:]
                if s2.get("governing_message"):
                    s2["governing_message"] = (
                        f"앞선 내용에 이어, {s2['governing_message']}"
                    )
                s2["design_hint"] = "내용 분할 - 결론부 강조"
                new_slides.append(s2)
            else:
                new_slides.append(slide)

        # 인덱스 재정렬
        for i, s in enumerate(new_slides):
            s["index"] = i + 1
        return new_slides

    # -----------------------------------------------------------------------
    # Card News
    # -----------------------------------------------------------------------

    async def plan_card_news(
        self,
        topic: str,
        num_cards: int,
        options: ContentOptions,
    ) -> CardNewsPlan:
        """카드뉴스 계획을 생성한다 (Multi-Agent 파이프라인).

        PR-059: Strategist -> Copywriter -> Art Director 3단계 에이전트 협업.
        """
        import json
        
        card_cfg = self._config.get("card_news", {})
        min_cards = card_cfg.get("min_cards", 3)
        max_cards = card_cfg.get("max_cards", 10)

        clamped_cards = _clamp(num_cards, min_cards, max_cards)

        # 1단계: 전략가 (Strategist Agent) - 스토리라인 및 수량 기획 (전문가 지식 주입)
        strat_prompt_template = _load_prompt("cardnews_strategist.md")
        full_strat_prompt = (
            f"{self._expert_knowledge}\n\n"
            + strat_prompt_template.format(
                topic=topic,
                num_cards=num_cards or 5,
                style=options.style,
                target_audience=options.target_audience,
            )
        )
        strategy_data = await self._call_llm_json(full_strat_prompt)

        # AI 추천 수량 적용
        actual_cards = num_cards or strategy_data.get("recommended_cards", 5)

        strategy_json_str = json.dumps(strategy_data, ensure_ascii=False, indent=2)

        # 2단계: 카피라이터 (Copywriter Agent) - 카피 작성 (전문가 지식 주입)
        copy_prompt_template = _load_prompt("cardnews_copywriter.md")
        full_copy_prompt = (
            f"{self._expert_knowledge}\n\n"
            + copy_prompt_template.format(
                topic=topic,
                language=options.language,
                strategy_json=strategy_json_str,
                target_audience=options.target_audience,
            )
        )
        copy_data = await self._call_llm_json(full_copy_prompt)
        copy_json_str = json.dumps(copy_data, ensure_ascii=False, indent=2)

        # 3단계: 아트 디렉터 (Art Director Agent) - 시각 기획 및 최종 조립
        art_prompt_template = _load_prompt("cardnews_art_director.md")
        art_prompt = art_prompt_template.format(
            topic=topic,
            series_title=strategy_data.get("series_title", topic),
            copy_json=copy_json_str,
            target_audience=options.target_audience,
        )
        art_data = await self._call_llm_json(art_prompt)

        # 4단계: 수석 에디터 (Quality Reviewer) - 최종 검수
        review_prompt_template = _load_prompt("quality_reviewer.md")
        review_prompt = review_prompt_template.format(
            topic=topic,
            final_plan_json=json.dumps(art_data, ensure_ascii=False, indent=2),
            target_audience=options.target_audience,
        )
        final_data = await self._call_llm_json(review_prompt)

        if "recommended_cards" not in final_data:
            final_data["recommended_cards"] = actual_cards

        return CardNewsPlan.from_dict(final_data)

    # -----------------------------------------------------------------------
    # Workshop
    # -----------------------------------------------------------------------

    async def plan_workshop(
        self,
        topic: str,
        duration_min: int,
        options: ContentOptions,
    ) -> WorkshopPlan:
        """워크숍 단계 계획을 생성한다.

        phase_ratios에 따라 시간을 배분한다.
        """
        workshop_cfg = self._config.get("workshop", {})
        phase_ratios = workshop_cfg.get(
            "phase_ratios",
            {"intro": 0.10, "main": 0.40, "activity": 0.30, "wrap_up": 0.20},
        )

        time_allocation = _allocate_workshop_time(duration_min, phase_ratios)

        prompt_template = _load_prompt("content_workshop.md")
        prompt = prompt_template.format(
            topic=topic,
            duration_min=duration_min,
            time_allocation=json.dumps(time_allocation, ensure_ascii=False),
            style=options.style,
            language=options.language,
            edition_filter=options.edition_filter or "전체",
        )

        data = await self._call_llm_json(prompt)
        return WorkshopPlan.from_dict(data)

    # -----------------------------------------------------------------------
    # Audio
    # -----------------------------------------------------------------------

    async def plan_audio(
        self,
        topic: str,
        duration_min: int,
        style: str,
        options: ContentOptions,
    ) -> AudioPlan:
        """프리미엄 팟캐스트/오디오 계획을 생성한다 (멀티 소스 지원).

        PR-077: 여러 주제 통합 분석 및 전문가 지식 합성 대본 생성.
        """
        import json
        
        # 1. 주제 분석 (멀티 주제 지원)
        topics = [t.strip() for t in topic.split(",") if t.strip()]
        
        # 2. 화자 규칙 정의
        speaker_rules = {
            "narration": "한 명의 호스트([호스트])가 전문 지식을 전달하는 독백",
            "dialogue": "호스트([호스트])와 전문가([전문가])의 깊이 있는 대담",
            "podcast": "호스트([호스트]), 교수([교수]), 리더([리더]) 3인의 심층 토론"
        }
        
        # 3. 프리미엄 지능형 프롬프트 (Expert Knowledge 통합)
        prompt = f"""{self._expert_knowledge}

당신은 최고 수준의 경영 전략 팟캐스트 제작자입니다. 
아래 SKMS 원문 컨텍스트와 주입된 글로벌 경영 이론들을 결합하여 전문적인 대본을 작성하세요.

## 구성 정보
- 주제 리스트: {", ".join(topics)}
- 스타일: {style} ({speaker_rules.get(style, "")})
- 목표 길이: {duration_min}분

## 대본 작성 규칙
1. **화자 태그**: 문장 맨 앞에 반드시 [호스트], [전문가], [교수], [리더] 등 화자 이름을 붙이세요.
2. **지적 수준**: SKMS 철학을 설명할 때 반드시 경영학/심리학 이론을 인용하여 깊이를 더하세요.
3. **숫자 처리**: 모든 숫자는 한글로 쓰세요. (예: 14차 -> 십사 차)
4. **JSON 출력**: 아래 스키마를 엄격히 준수하여 응답하세요.

## 출력 JSON 스키마
{{
  "title": "에피소드 전체 제목 (모든 주제를 아우르는 매력적인 제목)",
  "style": "{style}",
  "total_duration_min": {duration_min},
  "sections": [
    {{
      "speaker": "호스트 | 전문가 | 교수 | 리더",
      "text": "실제 발화 텍스트 (Ref: quote_id)",
      "purpose": "섹션의 목적 (오프닝, 인사이트, 마무리 등)"
    }}
  ]
}}
"""
        # [PR-077] GPT-4o를 사용하여 고품질 대본 생성
        audio_data = await self._call_llm_json(prompt)
        
        return AudioPlan.from_dict(audio_data)

    # -----------------------------------------------------------------------
    # Visualization
    # -----------------------------------------------------------------------

    async def plan_visualization(
        self,
        topic: str,
        viz_type: str,
        options: ContentOptions,
    ) -> VisualizationPlan:
        """시각화 계획을 생성한다 (Viz Strategist 에이전트 기반).

        PR-068: Intelligent Visualization Strategy & Data Extraction.
        """
        viz_cfg = self._config.get("visualization", {})
        
        # 시각화 전략가 에이전트 호출
        prompt_template = _load_prompt("viz_strategist.md")
        prompt = prompt_template.format(
            topic=topic,
        )
        
        # 데이터 추출
        viz_data = await self._call_llm_json(prompt)
        
        # 최종 모델로 변환
        return VisualizationPlan(
            viz_type=viz_data.get("viz_type", viz_type),
            data_structure=viz_data.get("data", {}),
            chart_options={
                **viz_cfg.get("default_options", {}),
                **viz_data.get("design_config", {})
            }
        )

    # -----------------------------------------------------------------------
    # Quiz
    # -----------------------------------------------------------------------

    async def plan_quiz(
        self,
        topic: str,
        num_questions: int,
        options: ContentOptions,
    ) -> QuizPlan:
        """퀴즈 문항 계획을 생성한다.

        문항 수를 min/max로 클램핑하고, difficulty_distribution을 적용.
        """
        quiz_cfg = self._config.get("quiz", {})
        min_q = quiz_cfg.get("min_questions", 5)
        max_q = quiz_cfg.get("max_questions", 20)

        clamped_questions = _clamp(num_questions, min_q, max_q)

        difficulty_dist = quiz_cfg.get(
            "difficulty_distribution",
            {"easy": 0.3, "medium": 0.5, "hard": 0.2},
        )
        question_counts = _distribute_difficulty(clamped_questions, difficulty_dist)

        prompt_template = _load_prompt("content_quiz.md")
        prompt = prompt_template.format(
            topic=topic,
            num_questions=clamped_questions,
            question_counts=json.dumps(question_counts, ensure_ascii=False),
            difficulty_distribution=json.dumps(difficulty_dist, ensure_ascii=False),
            language=options.language,
            edition_filter=options.edition_filter or "전체",
        )

        data = await self._call_llm_json(prompt)
        return QuizPlan.from_dict(data)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    async def _call_llm_json(self, prompt: str) -> dict[str, Any]:
        """LLM을 호출하고 JSON 응답을 파싱한다. 실패 시 1회 재시도."""
        raw = await self._llm.generate(prompt)
        try:
            return _parse_json(raw)
        except (json.JSONDecodeError, ValueError) as first_err:
            logger.warning("LLM JSON 파싱 실패, 재시도: %s", first_err)
            retry_prompt = (
                f"{prompt}\n\n"
                "[시스템] 이전 응답이 유효한 JSON이 아니었습니다. "
                "반드시 유효한 JSON만 출력하세요. 코드 펜스나 설명 없이 JSON만 반환하세요."
            )
            raw_retry = await self._llm.generate(retry_prompt)
            try:
                return _parse_json(raw_retry)
            except (json.JSONDecodeError, ValueError) as retry_err:
                raise ValueError(f"LLM JSON 파싱 재시도 실패: {retry_err}") from retry_err


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------


def _clamp(value: int, min_val: int, max_val: int) -> int:
    """정수를 [min_val, max_val] 범위로 클램핑한다."""
    return max(min_val, min(value, max_val))


def _allocate_workshop_time(
    duration_min: int,
    phase_ratios: dict[str, float],
) -> dict[str, int]:
    """워크숍 시간을 단계별 비율에 따라 배분한다.

    반올림 후 합이 duration_min과 다르면 가장 큰 단계에서 조정한다.
    """
    allocated: dict[str, int] = {}
    for phase, ratio in phase_ratios.items():
        allocated[phase] = max(1, round(duration_min * ratio))

    diff = duration_min - sum(allocated.values())
    if diff != 0:
        # 가장 큰 단계에서 차이를 조정
        largest = max(allocated, key=lambda k: allocated[k])
        allocated[largest] = max(1, allocated[largest] + diff)

    return allocated


def _audio_speaker_count(style: str) -> int:
    """오디오 스타일에 따라 화자 수를 결정한다."""
    return {"narration": 1, "dialogue": 2, "podcast": 3}.get(style, 1)


def _distribute_difficulty(
    total: int,
    distribution: dict[str, float],
) -> dict[str, int]:
    """난이도 분포에 따라 문항 수를 배분한다.

    반올림 후 합이 total과 다르면 medium에서 조정한다.
    """
    counts: dict[str, int] = {}
    for diff, ratio in distribution.items():
        counts[diff] = max(1, round(total * ratio)) if total > 0 else 0

    diff_sum = total - sum(counts.values())
    if diff_sum != 0 and "medium" in counts:
        counts["medium"] = max(1, counts["medium"] + diff_sum)

    return counts

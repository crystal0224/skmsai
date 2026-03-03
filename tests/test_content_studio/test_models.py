"""Content Studio 데이터 모델 테스트.

PR-040: frozen dataclass 불변성, 직렬화, 검증 테스트.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from src.content_studio.models import (
    AudioPlan,
    CardNewsPlan,
    CardPlan,
    ContentOptions,
    ContentRequest,
    ContentResult,
    GeneratedAsset,
    GeneratedFile,
    LecturePlan,
    QuizPlan,
    QuizQuestion,
    ScriptSection,
    SlidePlan,
    VisualizationPlan,
    WorkshopPlan,
    WorkshopPhase,
    load_content_studio_config,
    VALID_CONTENT_TYPES,
    VALID_LAYOUTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_slide(**overrides) -> SlidePlan:
    defaults = {"index": 1, "title": "테스트 슬라이드"}
    defaults.update(overrides)
    return SlidePlan(**defaults)


def _make_lecture(**overrides) -> LecturePlan:
    defaults = {
        "title": "SUPEX 추구의 변천사",
        "subtitle": "30분 강의",
        "duration_min": 30,
        "slides": (_make_slide(),),
        "learning_objectives": ("목표 1", "목표 2", "목표 3"),
    }
    defaults.update(overrides)
    return LecturePlan(**defaults)


def _make_card(**overrides) -> CardPlan:
    defaults = {"index": 1, "headline": "VWBE 문화란?", "body": "설명 텍스트"}
    defaults.update(overrides)
    return CardPlan(**defaults)


def _make_card_news(**overrides) -> CardNewsPlan:
    defaults = {
        "title": "VWBE 문화",
        "total_cards": 3,
        "cards": (_make_card(index=1), _make_card(index=2), _make_card(index=3)),
    }
    defaults.update(overrides)
    return CardNewsPlan(**defaults)


def _make_workshop_phase(**overrides) -> WorkshopPhase:
    defaults = {"phase_type": "intro", "title": "도입", "duration_min": 5}
    defaults.update(overrides)
    return WorkshopPhase(**defaults)


def _make_workshop(**overrides) -> WorkshopPlan:
    defaults = {
        "title": "인간중심 경영 워크숍",
        "duration_min": 60,
        "phases": (_make_workshop_phase(),),
    }
    defaults.update(overrides)
    return WorkshopPlan(**defaults)


def _make_script_section(**overrides) -> ScriptSection:
    defaults = {"index": 1, "speaker": "narrator", "text": "안녕하세요."}
    defaults.update(overrides)
    return ScriptSection(**defaults)


def _make_audio(**overrides) -> AudioPlan:
    defaults = {
        "title": "SKMS 40년 변천사",
        "style": "narration",
        "total_duration_min": 5,
        "sections": (_make_script_section(),),
    }
    defaults.update(overrides)
    return AudioPlan(**defaults)


# ===================================================================
# ContentOptions
# ===================================================================


class TestContentOptions:
    def test_defaults(self):
        opts = ContentOptions()
        assert opts.duration_min is None
        assert opts.style == "professional"
        assert opts.language == "ko"
        assert opts.include_speaker_notes is True

    def test_frozen(self):
        opts = ContentOptions()
        with pytest.raises(AttributeError):
            opts.style = "casual"  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        opts = ContentOptions(duration_min=30, edition_filter="2020-14차")
        restored = ContentOptions.from_dict(opts.to_dict())
        assert restored == opts

    def test_from_dict_defaults(self):
        opts = ContentOptions.from_dict({})
        assert opts.style == "professional"
        assert opts.language == "ko"


# ===================================================================
# ContentRequest
# ===================================================================


class TestContentRequest:
    def test_valid_creation(self):
        req = ContentRequest(content_type="lecture", topic="SUPEX 추구")
        assert req.content_type == "lecture"
        assert req.topic == "SUPEX 추구"

    def test_invalid_content_type(self):
        with pytest.raises(ValueError, match="유효하지 않은 content_type"):
            ContentRequest(content_type="invalid", topic="테스트")

    def test_empty_topic(self):
        with pytest.raises(ValueError, match="topic은 빈 문자열"):
            ContentRequest(content_type="lecture", topic="")

    def test_topic_too_long(self):
        with pytest.raises(ValueError, match="200자 이내"):
            ContentRequest(content_type="lecture", topic="가" * 201)

    def test_frozen(self):
        req = ContentRequest(content_type="lecture", topic="테스트")
        with pytest.raises(AttributeError):
            req.topic = "수정"  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        req = ContentRequest(
            content_type="card_news",
            topic="VWBE",
            options=ContentOptions(num_items=5),
        )
        restored = ContentRequest.from_dict(req.to_dict())
        assert restored == req

    def test_all_content_types_valid(self):
        for ct in VALID_CONTENT_TYPES:
            req = ContentRequest(content_type=ct, topic="테스트")
            assert req.content_type == ct


# ===================================================================
# GeneratedAsset
# ===================================================================


class TestGeneratedAsset:
    def test_valid_creation(self):
        asset = GeneratedAsset(
            asset_type="image",
            file_path="/tmp/test.png",
            prompt_used="기업 이미지",
            width=1920,
            height=1080,
        )
        assert asset.asset_type == "image"
        assert asset.width == 1920

    def test_invalid_asset_type(self):
        with pytest.raises(ValueError, match="유효하지 않은 asset_type"):
            GeneratedAsset(asset_type="video", file_path="/tmp/x", prompt_used="test")

    def test_content_hash_deterministic(self):
        a1 = GeneratedAsset(
            asset_type="image",
            file_path="/a",
            prompt_used="test",
            width=100,
            height=100,
        )
        a2 = GeneratedAsset(
            asset_type="image",
            file_path="/b",
            prompt_used="test",
            width=100,
            height=100,
        )
        assert a1.content_hash == a2.content_hash

    def test_content_hash_changes_with_prompt(self):
        a1 = GeneratedAsset(asset_type="image", file_path="/a", prompt_used="test1")
        a2 = GeneratedAsset(asset_type="image", file_path="/a", prompt_used="test2")
        assert a1.content_hash != a2.content_hash

    def test_to_dict_from_dict_roundtrip(self):
        asset = GeneratedAsset(
            asset_type="chart",
            file_path="/tmp/chart.svg",
            prompt_used="timeline",
            metadata=(("theme", "classic"),),
        )
        restored = GeneratedAsset.from_dict(asset.to_dict())
        assert restored.asset_type == asset.asset_type
        assert restored.prompt_used == asset.prompt_used

    def test_frozen(self):
        asset = GeneratedAsset(
            asset_type="image", file_path="/tmp/x", prompt_used="test"
        )
        with pytest.raises(AttributeError):
            asset.file_path = "/new"  # type: ignore[misc]


# ===================================================================
# GeneratedFile
# ===================================================================


class TestGeneratedFile:
    def test_valid_creation(self):
        f = GeneratedFile(
            file_type="pptx",
            file_path="/tmp/out.pptx",
            file_name="out.pptx",
            size_bytes=1024,
        )
        assert f.file_type == "pptx"
        assert f.size_bytes == 1024

    def test_invalid_file_type(self):
        with pytest.raises(ValueError, match="유효하지 않은 file_type"):
            GeneratedFile(
                file_type="docx", file_path="/tmp/x", file_name="x", size_bytes=0
            )

    def test_negative_size(self):
        with pytest.raises(ValueError, match="size_bytes는 0 이상"):
            GeneratedFile(
                file_type="pdf", file_path="/tmp/x", file_name="x", size_bytes=-1
            )

    def test_to_dict_from_dict_roundtrip(self):
        f = GeneratedFile(
            file_type="png",
            file_path="/tmp/card.png",
            file_name="card.png",
            size_bytes=2048,
        )
        restored = GeneratedFile.from_dict(f.to_dict())
        assert restored == f


# ===================================================================
# SlidePlan + LecturePlan
# ===================================================================


class TestSlidePlan:
    def test_valid_creation(self):
        s = _make_slide(key_points=("포인트1", "포인트2"))
        assert s.index == 1
        assert len(s.key_points) == 2

    def test_invalid_index(self):
        with pytest.raises(ValueError, match="index는 1 이상"):
            _make_slide(index=0)

    def test_invalid_layout(self):
        with pytest.raises(ValueError, match="유효하지 않은 layout"):
            _make_slide(layout="invalid_layout")

    def test_all_layouts_valid(self):
        for layout in VALID_LAYOUTS:
            s = _make_slide(layout=layout)
            assert s.layout == layout

    def test_invalid_asset_type(self):
        with pytest.raises(ValueError, match="유효하지 않은 asset_type"):
            _make_slide(asset_type="video")

    def test_asset_type_image_ok(self):
        s = _make_slide(asset_type="image", asset_prompt="기업 이미지")
        assert s.asset_type == "image"

    def test_asset_type_chart_ok(self):
        s = _make_slide(asset_type="chart", asset_prompt="타임라인")
        assert s.asset_type == "chart"

    def test_to_dict_from_dict_roundtrip(self):
        s = _make_slide(
            key_points=("a", "b"),
            rag_query="SUPEX란",
            edition_filter="2020-14차",
            speaker_notes="설명",
        )
        restored = SlidePlan.from_dict(s.to_dict())
        assert restored == s

    def test_frozen(self):
        s = _make_slide()
        with pytest.raises(AttributeError):
            s.title = "수정"  # type: ignore[misc]


class TestLecturePlan:
    def test_valid_creation(self):
        lp = _make_lecture()
        assert lp.duration_min == 30
        assert len(lp.slides) == 1
        assert len(lp.learning_objectives) == 3

    def test_invalid_duration(self):
        with pytest.raises(ValueError, match="duration_min은 1 이상"):
            _make_lecture(duration_min=0)

    def test_to_dict_from_dict_roundtrip(self):
        lp = _make_lecture()
        restored = LecturePlan.from_dict(lp.to_dict())
        assert restored.title == lp.title
        assert len(restored.slides) == len(lp.slides)
        assert restored.learning_objectives == lp.learning_objectives


# ===================================================================
# CardPlan + CardNewsPlan
# ===================================================================


class TestCardPlan:
    def test_valid_creation(self):
        c = _make_card()
        assert c.index == 1
        assert c.headline == "VWBE 문화란?"

    def test_invalid_index(self):
        with pytest.raises(ValueError, match="index는 1 이상"):
            _make_card(index=0)

    def test_to_dict_from_dict_roundtrip(self):
        c = _make_card(text_overlay="핵심 텍스트")
        restored = CardPlan.from_dict(c.to_dict())
        assert restored == c


class TestCardNewsPlan:
    def test_valid_creation(self):
        cn = _make_card_news()
        assert cn.total_cards == 3
        assert cn.image_size == (1080, 1080)

    def test_invalid_total_cards(self):
        with pytest.raises(ValueError, match="total_cards는 1 이상"):
            _make_card_news(total_cards=0)

    def test_to_dict_from_dict_roundtrip(self):
        cn = _make_card_news()
        restored = CardNewsPlan.from_dict(cn.to_dict())
        assert restored.title == cn.title
        assert restored.total_cards == cn.total_cards
        assert len(restored.cards) == len(cn.cards)
        assert restored.image_size == cn.image_size


# ===================================================================
# WorkshopPhase + WorkshopPlan
# ===================================================================


class TestWorkshopPhase:
    def test_valid_creation(self):
        wp = _make_workshop_phase()
        assert wp.phase_type == "intro"

    def test_invalid_phase_type(self):
        with pytest.raises(ValueError, match="유효하지 않은 phase_type"):
            _make_workshop_phase(phase_type="invalid")

    def test_invalid_duration(self):
        with pytest.raises(ValueError, match="duration_min은 1 이상"):
            _make_workshop_phase(duration_min=0)

    def test_to_dict_from_dict_roundtrip(self):
        wp = _make_workshop_phase(
            facilitator_guide="질문으로 시작",
            materials_needed=("포스트잇", "마커"),
        )
        restored = WorkshopPhase.from_dict(wp.to_dict())
        assert restored == wp


class TestWorkshopPlan:
    def test_valid_creation(self):
        w = _make_workshop()
        assert w.duration_min == 60

    def test_invalid_duration(self):
        with pytest.raises(ValueError, match="duration_min은 1 이상"):
            _make_workshop(duration_min=0)

    def test_to_dict_from_dict_roundtrip(self):
        w = _make_workshop()
        restored = WorkshopPlan.from_dict(w.to_dict())
        assert restored.title == w.title
        assert len(restored.phases) == len(w.phases)


# ===================================================================
# ScriptSection + AudioPlan
# ===================================================================


class TestScriptSection:
    def test_valid_creation(self):
        s = _make_script_section()
        assert s.speaker == "narrator"

    def test_invalid_index(self):
        with pytest.raises(ValueError, match="index는 1 이상"):
            _make_script_section(index=0)

    def test_to_dict_from_dict_roundtrip(self):
        s = _make_script_section(rag_query="SKMS 초판 기업관")
        restored = ScriptSection.from_dict(s.to_dict())
        assert restored == s


class TestAudioPlan:
    def test_valid_creation(self):
        a = _make_audio()
        assert a.style == "narration"
        assert a.total_duration_min == 5

    def test_invalid_style(self):
        with pytest.raises(ValueError, match="유효하지 않은 style"):
            _make_audio(style="invalid")

    def test_all_styles_valid(self):
        for style in ("narration", "dialogue", "podcast"):
            a = _make_audio(style=style)
            assert a.style == style

    def test_invalid_duration(self):
        with pytest.raises(ValueError, match="total_duration_min은 1 이상"):
            _make_audio(total_duration_min=0)

    def test_to_dict_from_dict_roundtrip(self):
        a = _make_audio()
        restored = AudioPlan.from_dict(a.to_dict())
        assert restored.title == a.title
        assert restored.style == a.style


# ===================================================================
# VisualizationPlan
# ===================================================================


class TestVisualizationPlan:
    def test_valid_creation(self):
        v = VisualizationPlan(title="SKMS 마인드맵", viz_type="mindmap")
        assert v.viz_type == "mindmap"

    def test_invalid_viz_type(self):
        with pytest.raises(ValueError, match="유효하지 않은 viz_type"):
            VisualizationPlan(title="테스트", viz_type="pie_chart")

    def test_all_viz_types_valid(self):
        for vt in (
            "timeline",
            "mindmap",
            "comparison",
            "wordcloud",
            "radar",
            "sankey",
            "flowchart",
        ):
            v = VisualizationPlan(title="테스트", viz_type=vt)
            assert v.viz_type == vt

    def test_to_dict_from_dict_roundtrip(self):
        v = VisualizationPlan(
            title="타임라인",
            viz_type="timeline",
            data_description="12개 개정판",
            chart_options=(("theme", "dark"),),
        )
        restored = VisualizationPlan.from_dict(v.to_dict())
        assert restored.title == v.title
        assert restored.viz_type == v.viz_type


# ===================================================================
# QuizQuestion + QuizPlan
# ===================================================================


class TestQuizQuestion:
    def test_valid_creation(self):
        q = QuizQuestion(
            index=1,
            question_text="SUPEX란?",
            choices=("답1", "답2", "답3", "답4"),
            correct_answer=0,
        )
        assert q.difficulty == "medium"

    def test_invalid_index(self):
        with pytest.raises(ValueError, match="index는 1 이상"):
            QuizQuestion(index=0, question_text="test")

    def test_invalid_difficulty(self):
        with pytest.raises(ValueError, match="유효하지 않은 difficulty"):
            QuizQuestion(index=1, question_text="test", difficulty="extreme")

    def test_correct_answer_out_of_range(self):
        with pytest.raises(ValueError, match="correct_answer 범위 초과"):
            QuizQuestion(
                index=1,
                question_text="test",
                choices=("a", "b"),
                correct_answer=2,
            )

    def test_correct_answer_negative(self):
        with pytest.raises(ValueError, match="correct_answer 범위 초과"):
            QuizQuestion(
                index=1,
                question_text="test",
                choices=("a", "b"),
                correct_answer=-1,
            )

    def test_empty_choices_no_validation(self):
        """choices가 비어있으면 correct_answer 범위 검증 스킵."""
        q = QuizQuestion(index=1, question_text="test", correct_answer=5)
        assert q.correct_answer == 5

    def test_to_dict_from_dict_roundtrip(self):
        q = QuizQuestion(
            index=1,
            question_text="SUPEX란?",
            choices=("답1", "답2", "답3", "답4"),
            correct_answer=2,
            explanation="해설",
            difficulty="hard",
            source_quote="q-001",
        )
        restored = QuizQuestion.from_dict(q.to_dict())
        assert restored == q


class TestQuizPlan:
    def test_valid_creation(self):
        qp = QuizPlan(title="SKMS 퀴즈", total_questions=10)
        assert qp.total_questions == 10
        assert dict(qp.difficulty_distribution) == {
            "easy": 0.3,
            "medium": 0.5,
            "hard": 0.2,
        }

    def test_invalid_total_questions(self):
        with pytest.raises(ValueError, match="total_questions는 1 이상"):
            QuizPlan(title="test", total_questions=0)

    def test_to_dict_from_dict_roundtrip(self):
        qp = QuizPlan(
            title="퀴즈",
            total_questions=5,
            questions=(
                QuizQuestion(index=1, question_text="Q1"),
                QuizQuestion(index=2, question_text="Q2"),
            ),
        )
        restored = QuizPlan.from_dict(qp.to_dict())
        assert restored.title == qp.title
        assert len(restored.questions) == 2


# ===================================================================
# ContentResult
# ===================================================================


class TestContentResult:
    def test_valid_creation(self):
        result = ContentResult(
            content_type="lecture",
            topic="SUPEX",
            files=(
                GeneratedFile(
                    file_type="pptx",
                    file_path="/tmp/out.pptx",
                    file_name="out.pptx",
                    size_bytes=1024,
                ),
            ),
            citations=("q-001", "q-002"),
        )
        assert result.content_type == "lecture"
        assert len(result.files) == 1
        assert len(result.citations) == 2

    def test_invalid_content_type(self):
        with pytest.raises(ValueError, match="유효하지 않은 content_type"):
            ContentResult(content_type="bad", topic="t", files=(), citations=())

    def test_to_dict(self):
        result = ContentResult(
            content_type="lecture",
            topic="테스트",
            files=(),
            citations=("q-001",),
            plan=_make_lecture(),
        )
        d = result.to_dict()
        assert d["content_type"] == "lecture"
        assert d["plan"]["title"] == "SUPEX 추구의 변천사"


# ===================================================================
# YAML 설정 로더
# ===================================================================


class TestLoadContentStudioConfig:
    def test_load_valid_config(self):
        config_path = (
            Path(__file__).parent.parent.parent / "config" / "content_studio.yaml"
        )
        if not config_path.exists():
            pytest.skip("config/content_studio.yaml not found")
        config = load_content_studio_config(config_path)
        assert config["output_dir"] == "output"
        assert "mcp_servers" in config
        assert "lecture" in config

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_content_studio_config("/nonexistent/path.yaml")

    def test_missing_content_studio_key(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("other_key: value\n")
        with pytest.raises(ValueError, match="content_studio"):
            load_content_studio_config(bad_yaml)

    def test_missing_output_dir(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("content_studio:\n  mcp_servers: {}\n")
        with pytest.raises(ValueError, match="output_dir"):
            load_content_studio_config(bad_yaml)

    def test_invalid_type(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("- list\n- items\n")
        with pytest.raises(ValueError, match="dict"):
            load_content_studio_config(bad_yaml)

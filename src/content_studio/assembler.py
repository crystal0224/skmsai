"""FileAssembler — 콘텐츠 + 에셋 → 최종 파일 조립 서비스.

PR-046: PPTX/PDF/HTML/PNG/MP3 파일 조립.
PR-050: 테마 적용, 목차 슬라이드, 슬라이드 번호/푸터 삽입.

python-pptx로 강의자료 PPTX 생성.
Markdown → PDF, 이미지 세트, 오디오 합성 등.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from src.content_studio.models import (
    GeneratedAsset,
    GeneratedFile,
)
from src.content_studio.pptx_templates import (
    PptxTheme,
    generate_footer,
    generate_toc_data,
    load_themes,
    select_layout,
    select_theme,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 기업 테마 상수
# ---------------------------------------------------------------------------

SK_BLUE = "0052A2"
SK_RED = "E4002B"
SK_GRAY = "6C757D"
SK_LIGHT_GRAY = "F8F9FA"
WHITE = "FFFFFF"

# 슬라이드 크기 (16:9, EMU 단위)
SLIDE_WIDTH_EMU = 12192000  # 33.867 cm
SLIDE_HEIGHT_EMU = 6858000  # 19.05 cm

# 기본 폰트
DEFAULT_FONT = "맑은 고딕"
FALLBACK_FONT = "Arial"


# ---------------------------------------------------------------------------
# FileAssembler
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssemblerConfig:
    """FileAssembler 설정 — 불변.

    Attributes:
        output_dir: 출력 기본 디렉토리.
        theme_primary: 주 색상 (hex).
        theme_secondary: 보조 색상 (hex).
        font_name: 기본 폰트.
        aspect_ratio: 슬라이드 비율.
        style: 스타일 (professional, casual, academic).
        themes_yaml_path: pptx_themes.yaml 경로 (None이면 테마 미사용).
        company: 푸터 회사명.
    """

    output_dir: str = "output"
    theme_primary: str = SK_BLUE
    theme_secondary: str = SK_RED
    font_name: str = DEFAULT_FONT
    aspect_ratio: str = "16:9"
    style: str = "professional"
    themes_yaml_path: str | None = None
    company: str = "SK Group"


class FileAssembler:
    """콘텐츠 + 에셋 → 최종 파일 조립."""

    def __init__(self, config: AssemblerConfig | None = None) -> None:
        self._config = config or AssemblerConfig()
        self._theme = self._resolve_theme()
        self._ensure_output_dirs()

    def _resolve_theme(self) -> PptxTheme | None:
        """설정의 style + themes_yaml_path로 PptxTheme를 로드한다."""
        if not self._config.themes_yaml_path:
            return None
        try:
            themes = load_themes(self._config.themes_yaml_path)
            theme_name = select_theme(self._config.style)
            return themes.get(theme_name)
        except FileNotFoundError:
            logger.warning("테마 파일을 찾을 수 없습니다: %s", self._config.themes_yaml_path)
            return None

    @property
    def theme(self) -> PptxTheme | None:
        """현재 로드된 테마."""
        return self._theme

    def _ensure_output_dirs(self) -> None:
        """출력 디렉토리 자동 생성."""
        base = Path(self._config.output_dir)
        for subdir in (
            "lectures",
            "cardnews",
            "workshops",
            "visualizations",
            "audio",
            "quizzes",
            "assets",
        ):
            (base / subdir).mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, topic: str) -> str:
        """파일명에 사용 불가한 문자 제거 + path traversal 방지."""
        # path traversal 시퀀스 제거
        sanitized = (
            topic.replace("..", "")
            .replace("/", "-")
            .replace("\\", "-")
            .replace(" ", "-")
        )
        sanitized = "".join(c for c in sanitized if c.isalnum() or c in "-_.")
        # 선행 점(.) 제거 (숨김파일 방지)
        sanitized = sanitized.lstrip(".")
        return sanitized[:50] if sanitized else "untitled"

    def _output_path(self, content_type: str, topic: str, ext: str) -> Path:
        """표준 출력 경로 생성: output/{type}/{topic}-{date}.{ext}.

        Raises:
            ValueError: 결과 경로가 output_dir 밖을 가리키는 경우.
        """
        subdir_map = {
            "lecture": "lectures",
            "card_news": "cardnews",
            "workshop": "workshops",
            "visualization": "visualizations",
            "audio": "audio",
            "quiz": "quizzes",
        }
        subdir = subdir_map.get(content_type, content_type)
        filename = f"{self._sanitize_filename(topic)}-{date.today().isoformat()}.{ext}"
        out = Path(self._config.output_dir) / subdir / filename
        # path traversal 방지: resolved 경로가 output_dir 내부인지 검증
        base_resolved = Path(self._config.output_dir).resolve()
        out_resolved = out.resolve()
        if not str(out_resolved).startswith(str(base_resolved)):
            raise ValueError(
                f"Path traversal 차단: {out} → {out_resolved} (base: {base_resolved})"
            )
        return out

    # ----- Lecture (PPTX) -----

    def assemble_lecture(
        self,
        content: Any,
        assets: list[GeneratedAsset] | None = None,
        topic: str = "",
    ) -> GeneratedFile:
        """강의자료 PPTX 생성.

        PR-050: 테마 색상, TOC 슬라이드, 슬라이드 번호/푸터 적용.

        Args:
            content: LectureContent (slides, citations).
            assets: 이미지/차트 에셋 목록.
            topic: 주제 (파일명에 사용).

        Returns:
            GeneratedFile (pptx).
        """
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt, Emu
            from pptx.dml.color import RGBColor
            from pptx.enum.text import PP_ALIGN
        except ImportError:
            logger.warning("python-pptx 미설치. 텍스트 fallback 사용.")
            return self._assemble_lecture_fallback(content, topic)

        prs = Presentation()
        prs.slide_width = SLIDE_WIDTH_EMU
        prs.slide_height = SLIDE_HEIGHT_EMU

        # 테마 색상 해석
        theme = self._theme
        title_color = self._parse_hex_color(theme.primary) if theme else None
        text_color = self._parse_hex_color(theme.text) if theme else None
        font_name = theme.font if theme else self._config.font_name

        # 에셋 인덱스 매핑
        asset_map: dict[int, GeneratedAsset] = {}
        if assets:
            for asset in assets:
                meta = dict(asset.metadata) if asset.metadata else {}
                slide_idx = meta.get("slide_index")
                if slide_idx is not None:
                    asset_map[int(slide_idx)] = asset

        slides = content.slides if hasattr(content, "slides") else ()

        # TOC 생성 (slides가 SlidePlan 속성을 가지면)
        toc_data = generate_toc_data(slides)

        # TOC 슬라이드 삽입 (TOC 항목이 2개 이상이면)
        if len(toc_data) >= 2:
            toc_layout = prs.slide_layouts[1]
            toc_slide = prs.slides.add_slide(toc_layout)
            if toc_slide.shapes.title:
                toc_slide.shapes.title.text = "목차"
                if title_color:
                    toc_slide.shapes.title.text_frame.paragraphs[
                        0
                    ].font.color.rgb = RGBColor(*title_color)
                toc_slide.shapes.title.text_frame.paragraphs[0].font.name = font_name
            for shape in toc_slide.placeholders:
                if shape.placeholder_format.idx == 1:
                    tf = shape.text_frame
                    tf.clear()
                    for i, entry in enumerate(toc_data):
                        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                        p.text = f"{entry['index']}. {entry['title']}"
                        p.font.size = Pt(16)
                        p.font.name = font_name
                        if text_color:
                            p.font.color.rgb = RGBColor(*text_color)
                    break

        # 콘텐츠 슬라이드
        footer_data = generate_footer(
            company=self._config.company,
        )
        slide_number = len(prs.slides) + 1  # TOC 다음부터

        for slide_content in slides:
            # 레이아웃 자동 선택
            layout_name = select_layout(slide_content)
            slide_layout = prs.slide_layouts[1]  # Title and Content
            slide = prs.slides.add_slide(slide_layout)

            # 제목
            if slide.shapes.title:
                slide.shapes.title.text = slide_content.title
                if title_color:
                    slide.shapes.title.text_frame.paragraphs[
                        0
                    ].font.color.rgb = RGBColor(*title_color)
                slide.shapes.title.text_frame.paragraphs[0].font.name = font_name

            # 본문
            body_placeholder = None
            for shape in slide.placeholders:
                if shape.placeholder_format.idx == 1:
                    body_placeholder = shape
                    break

            if body_placeholder is not None:
                tf = body_placeholder.text_frame
                tf.clear()
                # key points
                for i, point in enumerate(slide_content.key_points):
                    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    p.text = point
                    p.font.size = Pt(16)
                    p.font.name = font_name
                    if text_color:
                        p.font.color.rgb = RGBColor(*text_color)

                # 본문 텍스트
                if slide_content.body_text:
                    p = tf.add_paragraph()
                    p.text = slide_content.body_text
                    p.font.size = Pt(14)
                    p.font.name = font_name
                    if text_color:
                        p.font.color.rgb = RGBColor(*text_color)

            # 이미지 삽입
            asset = asset_map.get(slide_content.index)
            if asset and os.path.exists(asset.file_path):
                try:
                    left = Inches(7.0)
                    top = Inches(1.5)
                    width = Inches(3.0)
                    slide.shapes.add_picture(asset.file_path, left, top, width=width)
                except Exception as e:
                    logger.warning(f"이미지 삽입 실패 (slide {slide_content.index}): {e}")

            # 발표자 노트
            if slide_content.speaker_notes:
                notes_slide = slide.notes_slide
                notes_slide.notes_text_frame.text = slide_content.speaker_notes

            # 푸터 (슬라이드 번호 + 회사명 + 날짜)
            if footer_data.get("show_page_number"):
                self._add_footer_textbox(
                    slide,
                    prs,
                    Pt,
                    Inches,
                    RGBColor,
                    slide_number,
                    footer_data,
                    font_name,
                    text_color,
                )
            slide_number += 1

        # 출처 슬라이드
        citations = content.citations if hasattr(content, "citations") else ()
        if citations:
            slide_layout = prs.slide_layouts[1]
            cite_slide = prs.slides.add_slide(slide_layout)
            if cite_slide.shapes.title:
                cite_slide.shapes.title.text = "출처"
                if title_color:
                    cite_slide.shapes.title.text_frame.paragraphs[
                        0
                    ].font.color.rgb = RGBColor(*title_color)
                cite_slide.shapes.title.text_frame.paragraphs[0].font.name = font_name
            for shape in cite_slide.placeholders:
                if shape.placeholder_format.idx == 1:
                    tf = shape.text_frame
                    tf.clear()
                    for i, cite in enumerate(citations):
                        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                        p.text = f"• {cite}"
                        p.font.size = Pt(12)
                        p.font.name = font_name
                    break

        # 저장
        out_path = self._output_path("lecture", topic, "pptx")
        prs.save(str(out_path))
        size = out_path.stat().st_size

        return GeneratedFile(
            file_type="pptx",
            file_path=str(out_path),
            file_name=out_path.name,
            size_bytes=size,
        )

    @staticmethod
    def _parse_hex_color(hex_str: str) -> tuple[int, int, int] | None:
        """'#RRGGBB' 또는 'RRGGBB' 문자열 → (R, G, B) 튜플."""
        h = hex_str.lstrip("#")
        if len(h) != 6:
            return None
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return None

    @staticmethod
    def _add_footer_textbox(
        slide: Any,
        prs: Any,
        Pt: Any,
        Inches: Any,
        RGBColor: Any,
        slide_number: int,
        footer_data: dict[str, Any],
        font_name: str,
        text_color: tuple[int, int, int] | None,
    ) -> None:
        """슬라이드 하단에 푸터 텍스트 박스를 추가한다."""
        footer_text = (
            f"{footer_data.get('company', '')}  |  "
            f"{footer_data.get('date', '')}  |  "
            f"{slide_number}"
        )
        left = Inches(0.5)
        top = prs.slide_height - Inches(0.5)
        width = Inches(9.0)
        height = Inches(0.3)
        txbox = slide.shapes.add_textbox(left, top, width, height)
        tf = txbox.text_frame
        p = tf.paragraphs[0]
        p.text = footer_text
        p.font.size = Pt(8)
        p.font.name = font_name
        if text_color:
            p.font.color.rgb = RGBColor(*text_color)

    def _assemble_lecture_fallback(self, content: Any, topic: str) -> GeneratedFile:
        """python-pptx 미설치 시 텍스트 파일 fallback."""
        out_path = self._output_path("lecture", topic, "html")
        lines = [f"<html><body><h1>{topic}</h1>"]
        slides = content.slides if hasattr(content, "slides") else ()
        for sc in slides:
            lines.append(f"<h2>{sc.title}</h2>")
            for kp in sc.key_points:
                lines.append(f"<li>{kp}</li>")
            if sc.body_text:
                lines.append(f"<p>{sc.body_text}</p>")
        lines.append("</body></html>")
        text = "\n".join(lines)
        out_path.write_text(text, encoding="utf-8")
        return GeneratedFile(
            file_type="html",
            file_path=str(out_path),
            file_name=out_path.name,
            size_bytes=len(text.encode("utf-8")),
        )

    # ----- Card News (PNG set) -----

    def assemble_card_news(
        self,
        content: Any,
        assets: list[GeneratedAsset] | None = None,
        topic: str = "",
    ) -> tuple[GeneratedFile, ...]:
        """카드뉴스 PNG 세트 또는 HTML fallback."""
        results = []
        cards = content.cards if hasattr(content, "cards") else ()

        for card in cards:
            # 에셋 이미지가 있으면 사용
            asset = None
            if assets:
                for a in assets:
                    meta = dict(a.metadata) if a.metadata else {}
                    if meta.get("card_index") == card.index:
                        asset = a
                        break

            if asset and os.path.exists(asset.file_path):
                import shutil

                out_path = self._output_path(
                    "card_news", f"{topic}-{card.index}", "png"
                )
                shutil.copy2(asset.file_path, str(out_path))
                size = out_path.stat().st_size
                results.append(
                    GeneratedFile(
                        file_type="png",
                        file_path=str(out_path),
                        file_name=out_path.name,
                        size_bytes=size,
                    )
                )
            else:
                # HTML fallback
                out_path = self._output_path(
                    "card_news", f"{topic}-{card.index}", "html"
                )
                body_html = card.body.replace("\n", "<br>")
                # 인용 블록
                quote_html = ""
                source_quote = getattr(card, "source_quote", "")
                source_edition = getattr(card, "source_edition", "")
                if source_quote:
                    quote_html = (
                        (
                            f'<blockquote style="border-left:3px solid rgba(255,255,255,0.5);'
                            f"padding-left:16px;margin-top:24px;font-style:italic;"
                            f'font-size:18px;opacity:0.9;line-height:1.6;">'
                            f"「{source_quote}」"
                            f'<span style="display:block;font-size:13px;margin-top:8px;opacity:0.7;">'
                            f"(출처: {source_edition})</span>"
                            f"</blockquote>"
                        )
                        if source_edition
                        else (
                            f'<blockquote style="border-left:3px solid rgba(255,255,255,0.5);'
                            f"padding-left:16px;margin-top:24px;font-style:italic;"
                            f'font-size:18px;opacity:0.9;line-height:1.6;">'
                            f"「{source_quote}」</blockquote>"
                        )
                    )
                card_num = f'<div style="position:absolute;top:24px;right:32px;font-size:14px;opacity:0.6;">{card.index}/{len(cards)}</div>'
                html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=1080"></head>
<body style="margin:0;width:1080px;height:1080px;background:linear-gradient(135deg,#0052A2,#003d7a);color:white;font-family:'Pretendard','Apple SD Gothic Neo',sans-serif;display:flex;flex-direction:column;justify-content:center;padding:60px;box-sizing:border-box;position:relative;">
{card_num}
<h1 style="font-size:40px;margin:0 0 20px;line-height:1.3;font-weight:700;">{card.headline}</h1>
<p style="font-size:24px;line-height:1.9;margin:0 0 16px;">{body_html}</p>
{quote_html}
<div style="position:absolute;bottom:24px;left:60px;font-size:12px;opacity:0.5;">SKMS Content Studio</div>
</body></html>"""
                out_path.write_text(html, encoding="utf-8")
                results.append(
                    GeneratedFile(
                        file_type="html",
                        file_path=str(out_path),
                        file_name=out_path.name,
                        size_bytes=len(html.encode("utf-8")),
                    )
                )

        return tuple(results)

    # ----- Workshop (PDF) -----

    def assemble_workshop(
        self,
        content: Any,
        assets: list[GeneratedAsset] | None = None,
        topic: str = "",
    ) -> GeneratedFile:
        """워크숍 PDF (Markdown → HTML fallback)."""
        phases = content.phases if hasattr(content, "phases") else ()
        lines = [f"# {topic} — 워크숍 진행자 가이드\n"]
        for phase in phases:
            lines.append(f"## {phase.title} ({phase.phase_type})")
            lines.append(phase.content_text)
            lines.append("")

        text = "\n".join(lines)
        out_path = self._output_path("workshop", topic, "html")
        out_path.write_text(text, encoding="utf-8")

        return GeneratedFile(
            file_type="html",
            file_path=str(out_path),
            file_name=out_path.name,
            size_bytes=len(text.encode("utf-8")),
        )

    # ----- Audio (MP3 / script fallback) -----

    def assemble_audio(
        self,
        content: Any,
        assets: list[GeneratedAsset] | None = None,
        topic: str = "",
    ) -> GeneratedFile:
        """오디오 MP3 합성 또는 스크립트 텍스트 fallback."""
        # MP3 에셋이 있으면 합성 시도
        if assets:
            mp3_assets = [a for a in assets if a.asset_type == "audio"]
            if mp3_assets and all(os.path.exists(a.file_path) for a in mp3_assets):
                try:
                    return self._merge_audio(mp3_assets, topic)
                except Exception as e:
                    logger.warning(f"오디오 합성 실패: {e}")

        # 스크립트 텍스트 fallback
        sections = content.sections if hasattr(content, "sections") else ()
        lines = [f"# {topic} — 오디오 스크립트\n"]
        for sec in sections:
            lines.append(f"**[{sec.speaker}]**")
            lines.append(sec.text)
            lines.append("")

        text = "\n".join(lines)
        out_path = self._output_path("audio", topic, "html")
        out_path.write_text(text, encoding="utf-8")

        return GeneratedFile(
            file_type="html",
            file_path=str(out_path),
            file_name=out_path.name,
            size_bytes=len(text.encode("utf-8")),
        )

    def _merge_audio(
        self, mp3_assets: list[GeneratedAsset], topic: str
    ) -> GeneratedFile:
        """MP3 파일 합성 (pydub 사용)."""
        from pydub import AudioSegment

        combined = AudioSegment.empty()
        for asset in mp3_assets:
            segment = AudioSegment.from_mp3(asset.file_path)
            combined += segment

        out_path = self._output_path("audio", topic, "mp3")
        combined.export(str(out_path), format="mp3")
        size = out_path.stat().st_size

        return GeneratedFile(
            file_type="mp3",
            file_path=str(out_path),
            file_name=out_path.name,
            size_bytes=size,
        )

    # ----- Visualization (SVG/PNG passthrough) -----

    def assemble_visualization(
        self,
        content: Any,
        assets: list[GeneratedAsset] | None = None,
        topic: str = "",
    ) -> GeneratedFile:
        """시각화 에셋 파일 복사."""
        if assets:
            chart_assets = [a for a in assets if a.asset_type == "chart"]
            if chart_assets:
                import shutil

                asset = chart_assets[0]
                ext = "svg" if asset.file_path.endswith(".svg") else "png"
                out_path = self._output_path("visualization", topic, ext)
                shutil.copy2(asset.file_path, str(out_path))
                return GeneratedFile(
                    file_type=ext,
                    file_path=str(out_path),
                    file_name=out_path.name,
                    size_bytes=out_path.stat().st_size,
                )

        # No asset → HTML timeline fallback from VisualizationPlan
        out_path = self._output_path("visualization", topic, "html")
        html = _build_visualization_html(content, topic)
        out_path.write_text(html, encoding="utf-8")
        return GeneratedFile(
            file_type="html",
            file_path=str(out_path),
            file_name=out_path.name,
            size_bytes=len(html.encode("utf-8")),
        )

    # ----- Quiz (HTML) -----

    def assemble_quiz(
        self,
        content: Any,
        topic: str = "",
    ) -> GeneratedFile:
        """퀴즈 HTML 생성 — QuizPlan에서 인터랙티브 HTML."""
        out_path = self._output_path("quiz", topic, "html")
        html = _build_quiz_html(content, topic)
        out_path.write_text(html, encoding="utf-8")
        return GeneratedFile(
            file_type="html",
            file_path=str(out_path),
            file_name=out_path.name,
            size_bytes=len(html.encode("utf-8")),
        )


# ---------------------------------------------------------------------------
# HTML builders for quiz and visualization
# ---------------------------------------------------------------------------


def _build_quiz_html(plan: Any, topic: str) -> str:
    """QuizPlan → 인터랙티브 퀴즈 HTML."""
    questions = getattr(plan, "questions", ())
    if not questions:
        return f"<html><body><h1>{topic}</h1><p>퀴즈 문항이 없습니다.</p></body></html>"

    import html as html_mod

    question_blocks = []
    for q in questions:
        choices_html = ""
        for ci, choice in enumerate(q.choices):
            escaped = html_mod.escape(choice)
            choices_html += (
                f'<button class="choice" data-q="{q.index}" data-c="{ci}" '
                f'onclick="checkAnswer(this,{q.index},{q.correct_answer})">'
                f'<span class="label">{chr(65 + ci)}</span> {escaped}</button>\n'
            )
        explanation_escaped = html_mod.escape(q.explanation)
        source = html_mod.escape(getattr(q, "source_quote", ""))
        source_html = f'<div class="source">출처: {source}</div>' if source else ""
        question_blocks.append(
            f'<div class="question" id="q{q.index}">'
            f'<div class="q-num">Q{q.index}</div>'
            f'<div class="q-text">{html_mod.escape(q.question_text)}</div>'
            f'<div class="choices">{choices_html}</div>'
            f'<div class="explanation" id="exp{q.index}" style="display:none;">'
            f"{explanation_escaped}{source_html}</div>"
            f"</div>"
        )

    questions_joined = "\n".join(question_blocks)
    title_escaped = html_mod.escape(topic)
    n = len(questions)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n'
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{title_escaped}</title>\n"
        "<style>\n"
        "body{font-family:'Pretendard','Apple SD Gothic Neo',sans-serif;background:#f5f7fa;margin:0;padding:20px;color:#1a1a2e}\n"
        "h1{text-align:center;color:#0052A2;margin:20px 0 30px;font-size:28px}\n"
        ".question{background:white;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}\n"
        ".q-num{color:#0052A2;font-weight:700;font-size:14px;margin-bottom:8px}\n"
        ".q-text{font-size:18px;font-weight:600;line-height:1.6;margin-bottom:16px}\n"
        ".choices{display:flex;flex-direction:column;gap:8px}\n"
        ".choice{border:2px solid #e0e0e0;border-radius:8px;padding:12px 16px;background:white;cursor:pointer;"
        "text-align:left;font-size:16px;transition:all 0.2s}\n"
        ".choice:hover{border-color:#0052A2;background:#f0f4ff}\n"
        ".choice .label{display:inline-block;width:28px;height:28px;border-radius:50%;background:#e8edf5;"
        "text-align:center;line-height:28px;font-weight:700;margin-right:8px;font-size:14px}\n"
        ".choice.correct{border-color:#2ecc71;background:#eafaf1}"
        ".choice.correct .label{background:#2ecc71;color:white}\n"
        ".choice.wrong{border-color:#e74c3c;background:#fdf2f2}"
        ".choice.wrong .label{background:#e74c3c;color:white}\n"
        ".choice.disabled{pointer-events:none;opacity:0.6}\n"
        ".explanation{margin-top:16px;padding:16px;background:#f0f4ff;border-radius:8px;"
        "font-size:15px;line-height:1.7;border-left:4px solid #0052A2}\n"
        ".source{margin-top:8px;font-size:13px;color:#666;font-style:italic}\n"
        ".score{text-align:center;font-size:20px;font-weight:700;color:#0052A2;margin-top:20px}\n"
        "footer{text-align:center;margin-top:30px;color:#999;font-size:12px}\n"
        "</style>\n"
        "</head>\n<body>\n"
        f"<h1>{title_escaped}</h1>\n"
        f"{questions_joined}\n"
        '<div class="score" id="score"></div>\n'
        "<footer>SKMS Content Studio</footer>\n"
        "<script>\n"
        f"let answered=0,correct=0,total={n};\n"
        "function checkAnswer(btn,qIdx,correctIdx){\n"
        "  let btns=document.querySelectorAll('.choice[data-q=\"'+qIdx+'\"]');\n"
        "  btns.forEach(b=>{b.classList.add('disabled');"
        "if(parseInt(b.dataset.c)===correctIdx)b.classList.add('correct')});\n"
        "  if(parseInt(btn.dataset.c)!==correctIdx)btn.classList.add('wrong');\n"
        "  else correct++;\n"
        "  answered++;\n"
        "  document.getElementById('exp'+qIdx).style.display='block';\n"
        "  if(answered===total)document.getElementById('score').textContent="
        "'결과: '+total+'문제 중 '+correct+'개 정답 ('+Math.round(correct/total*100)+'%)';\n"
        "}\n"
        "</script>\n"
        "</body></html>"
    )


def _build_visualization_html(plan: Any, topic: str) -> str:
    """VisualizationPlan → HTML 타임라인."""
    import html as html_mod

    title = getattr(plan, "title", topic) or topic
    description = getattr(plan, "data_description", "") or ""

    editions = [
        ("1979", "초판", "SK경영체계의 출발점"),
        ("1981", "1차", "경영 원칙 체계화"),
        ("1988", "5차", "경영 요소 분류 재편"),
        ("1989", "6차", "SUPEX 추구 도입"),
        ("1990", "7차", "관리 체계 정교화"),
        ("1995", "8차", "글로벌 경영 반영"),
        ("1997", "9차", "SUPEX 추구법 완성"),
        ("1998", "10차", "구조조정기 반영"),
        ("2004", "11차", "지배구조 변화 반영"),
        ("2008", "12차", "사회적 책임 강화"),
        ("2016", "13차", "SUPEX Company 개념"),
        ("2020", "14차", "VWBE 문화 · 구성원 행복"),
    ]

    items = ""
    for year, name, desc in editions:
        items += (
            f'<div class="tl-item">'
            f'<div class="tl-year">{year}</div>'
            f'<div class="tl-dot"></div>'
            f'<div class="tl-card">'
            f'<div class="tl-name">{html_mod.escape(name)} 개정판</div>'
            f'<div class="tl-desc">{html_mod.escape(desc)}</div>'
            f"</div></div>\n"
        )

    title_escaped = html_mod.escape(title)
    desc_escaped = html_mod.escape(description)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n'
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{title_escaped}</title>\n"
        "<style>\n"
        "body{font-family:'Pretendard','Apple SD Gothic Neo',sans-serif;background:#f5f7fa;margin:0;padding:20px;color:#1a1a2e}\n"
        "h1{text-align:center;color:#0052A2;margin:20px 0 10px;font-size:28px}\n"
        ".subtitle{text-align:center;color:#666;margin-bottom:30px;font-size:15px}\n"
        ".timeline{position:relative;max-width:700px;margin:0 auto;padding:20px 0}\n"
        ".timeline::before{content:'';position:absolute;left:80px;top:0;bottom:0;width:3px;"
        "background:linear-gradient(180deg,#0052A2,#003d7a)}\n"
        ".tl-item{display:flex;align-items:center;margin-bottom:16px;position:relative}\n"
        ".tl-year{width:60px;text-align:right;font-weight:700;color:#0052A2;font-size:15px;flex-shrink:0}\n"
        ".tl-dot{width:14px;height:14px;border-radius:50%;background:#0052A2;border:3px solid white;"
        "box-shadow:0 0 0 2px #0052A2;margin:0 16px;flex-shrink:0;z-index:1}\n"
        ".tl-card{background:white;border-radius:8px;padding:12px 16px;"
        "box-shadow:0 2px 6px rgba(0,0,0,0.08);flex:1}\n"
        ".tl-name{font-weight:700;font-size:16px;color:#1a1a2e}\n"
        ".tl-desc{font-size:14px;color:#555;margin-top:4px}\n"
        "footer{text-align:center;margin-top:30px;color:#999;font-size:12px}\n"
        "</style>\n"
        "</head>\n<body>\n"
        f"<h1>{title_escaped}</h1>\n"
        f'<div class="subtitle">{desc_escaped}</div>\n'
        f'<div class="timeline">\n{items}</div>\n'
        "<footer>SKMS Content Studio</footer>\n"
        "</body></html>"
    )

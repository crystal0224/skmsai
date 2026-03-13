#!/usr/bin/env python3
"""SKMS Premium Podcast Engine — Multi-source Intelligence Synthesis.

여러 주제를 통합하여 고품질 리더십 팟캐스트 대본을 생성하고 음성/영상을 제작합니다.
글로벌 경영 프레임워크(CCL, Hogan 등)가 자동으로 대본에 녹아듭니다.

Usage:
    python3 scripts/skms_podcast.py --topics "행복 추구, VWBE 문화" --duration 10 --style podcast
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# 환경 설정 및 경로
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
# 환경변수에서 플러그인 경로를 가져오거나 기본값 사용
PODCAST_PLUGIN_SCRIPTS = Path(os.environ.get(
    "PODCAST_PLUGIN_DIR", 
    str(Path.home() / "plugins-for-claude-natives/plugins/podcast/skills/podcast/scripts")
))
OUTPUT_BASE = PROJECT_ROOT / "output" / "podcast"
EXPERT_KNOWLEDGE_PATH = PROJECT_ROOT / "prompts" / "expert_frameworks.md"


def _resolve_output_dir(title: str) -> Path:
    """에피소드 출력 디렉토리 생성."""
    slug = title.replace(" ", "-")[:30]
    slug = "".join(c for c in slug if c.isalnum() or c in "-_")
    dir_name = f"{date.today().isoformat()}-{slug}"
    output_dir = OUTPUT_BASE / dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _check_prerequisites() -> list[str]:
    errors = []
    if not os.environ.get("OPENAI_API_KEY"):
        errors.append("OPENAI_API_KEY 환경변수가 필요합니다.")
    if not PODCAST_PLUGIN_SCRIPTS.exists():
        errors.append(f"Podcast 플러그인 경로를 찾을 수 없습니다: {PODCAST_PLUGIN_SCRIPTS}")
    return errors


# ---------------------------------------------------------------------------
# Step 1: 멀티 소스 RAG 검색
# ---------------------------------------------------------------------------

def retrieve_multi_context(topics: list[str], edition_filter: str | None = None) -> str:
    """여러 주제에 대한 SKMS 컨텍스트를 수집하고 통합한다."""
    sys.path.insert(0, str(PROJECT_ROOT))
    combined_context = []

    try:
        from scripts.lib.search_service import SearchService
        service = SearchService()
        
        for topic in topics:
            topic = topic.strip()
            hits = service.hybrid_search(topic, top_k=5)
            if edition_filter:
                hits = [h for h in hits if edition_filter in getattr(h, "edition", "")]
            
            context_part = f"### 주제: {topic}\n"
            context_part += "\n".join([f"[{getattr(h, 'edition', 'Unknown')}] {getattr(h, 'text', str(h))}" for h in hits])
            combined_context.append(context_part)
            
        return "\n\n---\n\n".join(combined_context)
    except Exception as e:
        print(f"  SearchService 로드 실패 ({e}), 폴백 모드 작동")
        return f"통합 주제: {', '.join(topics)}\n(원문 데이터 로드 실패)"


# ---------------------------------------------------------------------------
# Step 2: 전문가 지식 기반 대본 생성
# ---------------------------------------------------------------------------

def generate_premium_script(
    topics: list[str],
    context: str,
    duration_min: int,
    style: str,
    output_path: Path,
) -> str:
    """글로벌 리더십 이론과 SKMS를 결합한 프리미엄 대본 생성."""
    import urllib.request

    expert_knowledge = ""
    if EXPERT_KNOWLEDGE_PATH.exists():
        expert_knowledge = EXPERT_KNOWLEDGE_PATH.read_text(encoding="utf-8")

    target_chars = duration_min * 520 # 한국어 기준
    speaker_rules = {
        "narration": "한 명의 호스트([호스트])가 전문적인 통찰을 전달하는 독백 형태",
        "dialogue": "호스트([호스트])와 SKMS 전문가([전문가])의 깊이 있는 대담 형태",
        "podcast": "호스트([호스트]), 경영학 교수([교수]), 현장 리더([리더]) 3인의 다각도 토론 형태"
    }

    prompt = f"""{expert_knowledge}

당신은 최고 수준의 경영 전략 팟캐스트 제작자입니다. 
아래 제공된 여러 주제의 SKMS 원문과 글로벌 리더십 프레임워크(CCL, Hogan 등)를 결합하여, 
단순한 요약을 넘어선 **'인사이트 중심의 에피소드'**를 작성하세요.

## 에피소드 구성 정보
- 통합 주제: {", ".join(topics)}
- 스타일: {style} ({speaker_rules.get(style)})
- 목표 길이: {duration_min}분 (약 {target_chars}자)

## 통합 컨텍스트 (SKMS 원문)
{context}

## 작성 가이드라인 (Crucial)
1. **화자 표시**: 반드시 문장 앞에 [호스트], [전문가], [교수], [리더] 등 화자 이름을 대괄호와 함께 붙이세요. (예: [호스트] 여러분 반갑습니다.)
2. **지적 깊이**: SKMS의 개념(예: VWBE)을 설명할 때 반드시 외부 이론(예: 자기결정성 이론, 심리적 안전감 등)을 인용하여 그 가치를 객관화하세요.
3. **구어체 완성도**: "했어요" 보다는 "했습니다", "하시죠" 등 격식있으면서도 친근한 비즈니스 구어체를 사용하세요.
4. **숫자 처리**: 모든 숫자는 한글로 쓰세요. (예: 14차 -> 십사 차)
5. **디자인적 이질감 제거**: 대본 내에 표, 불릿 포인트, 마크다운 특수문자 등을 최소화하여 TTS가 매끄럽게 읽도록 하세요.

## 출력 형식
# [에피소드 제목: 주제들을 아우르는 매력적인 제목]

---
[대본 시작]
"""

    api_key = os.environ["OPENAI_API_KEY"]
    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 4000
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    )

    print(f"  고품질 대본 생성 중 (스타일: {style})...")
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read())

    script_text = result["choices"][0]["message"]["content"]
    output_path.write_text(script_text, encoding="utf-8")
    
    # 제목 추출 (첫 번째 # 줄)
    title = topics[0]
    for line in script_text.split("\n"):
        if line.startswith("# "):
            title = line.replace("# ", "").strip()
            break
            
    return title


# ---------------------------------------------------------------------------
# Runner Functions
# ---------------------------------------------------------------------------

def run_step(name: str, cmd: list[str]):
    print(f"\n--- {name} 시작 ---")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR in {name}: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="SKMS Premium Podcast Engine")
    parser.add_argument("--topics", required=True, help="쉼표로 구분된 주제들 (예: '행복, 패기')")
    parser.add_argument("--duration", type=int, default=5, help="길이(분)")
    parser.add_argument("--style", choices=["narration", "dialogue", "podcast"], default="dialogue")
    parser.add_argument("--edition", help="판본 필터")
    parser.add_argument("--skip-youtube", action="store_true")
    args = parser.parse_args()

    errors = _check_prerequisites()
    if errors:
        for e in errors: print(f"Error: {e}")
        sys.exit(1)

    topic_list = [t.strip() for t in args.topics.split(",")]
    
    # 1. RAG 수집
    print(f"1/4 멀티 소스 컨텍스트 수집 중: {topic_list}")
    context = retrieve_multi_context(topic_list, args.edition)

    # 2. 대본 생성
    temp_dir = Path("output/temp_podcast")
    temp_dir.mkdir(parents=True, exist_ok=True)
    script_path = temp_dir / "script.md"
    
    print("2/4 프리미엄 대본 설계 중...")
    episode_title = generate_premium_script(topic_list, context, args.duration, args.style, script_path)
    
    # 최종 출력 디렉토리 확정
    output_dir = _resolve_output_dir(episode_title)
    final_script = output_dir / "script.md"
    script_path.rename(final_script)
    
    mp3_path = output_dir / "episode.mp3"
    mp4_path = output_dir / "episode.mp4"

    # 3. TTS (외부 플러그인)
    run_step("TTS 생성", [sys.executable, str(PODCAST_PLUGIN_SCRIPTS / "generate_tts.py"), "--input", str(final_script), "--output", str(mp3_path)])

    # 4. MP4 변환 (디자인 일관성 적용)
    run_step("영상 변환", [
        sys.executable, str(PODCAST_PLUGIN_SCRIPTS / "convert_mp4.py"),
        "--input", str(mp3_path), "--output", str(mp4_path),
        "--title", episode_title, "--subtitle", "SKMS AI Content Studio"
    ])

    # 5. YouTube
    if not args.skip_youtube:
        run_step("YouTube 업로드", [
            sys.executable, str(PODCAST_PLUGIN_SCRIPTS / "upload_youtube.py"),
            "--video", str(mp4_path), "--title", f"[SKMS] {episode_title}",
            "--description", f"SKMS '{episode_title}' 주제 통합 팟캐스트. 글로벌 리더십 이론 결합 AI 생성 콘텐츠."
        ])

    print(f"\n✨ 제작 완료!\n출력 경로: {output_dir}")

if __name__ == "__main__":
    main()

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This repository contains the raw text of **SKMS (SK Management System)** — SK Group's comprehensive management philosophy and operational framework, spanning from the 1st edition (1979) to the 14th revision (2020). The single source file `SKMSraw.txt` (15,330 lines) was OCR-converted from PDF and manually corrected by Crystal Bae (2024.08.03).

## Document Structure

### Editions (12개, chronological order in file)
| Edition | Year | Lines | Headers | Pattern |
|---------|------|-------|---------|---------|
| 초판 | 1979 | 11–726 | 188 | type_a |
| 1차 | 1981 | 727–5250 | 953 | type_a |
| 5차 | 1988 | 5251–6748 | 335 | type_b |
| 6차 | 1989 | 6749–7859 | 154 | type_b |
| 7차 | 1990 | 7860–8953 | 143 | type_b |
| 8차 | 1995 | 8954–10131 | 217 | type_b |
| 9차 | 1997 | 10132–11777 | 319 | type_b |
| 10차 | 1998 | 11778–12936 | 313 | type_a |
| 11차 | 2004 | 12937–13958 | 207 | type_a |
| 12차 | 2008 | 13959–14946 | 116 | type_a |
| 13차 | 2016 | 14947–15072 | 6 | type_a |
| 14차 | 2020 | 15073–15331 | 28 | type_a |

> 2차~4차는 독립 섹션 없음 (보완 이력 테이블 내에서만 참조)

### Core Philosophy (Three Pillars)
1. **인간중심의 경영** — Human-centered management
2. **합리적 경영** — Rational management (empirical science + social norms + artful execution)
3. **현실을 인식한 경영** — Reality-conscious management

### Management Elements
- **정적 요소 (Static)**: 기획, 인사, 조직, 재무, 판매, 생산, 연구개발, 구매, 사무, PR 관리
- **동적 요소 (Dynamic)**: 의욕관리, 관리역량관리, 코디네이션관리, 커뮤니케이션관리, SK-Manship

### Key Concepts by Era
- **1979–1998**: Foundational principles, hierarchical management, product quality focus
- **1998+**: SUPEX (Super Excellent) methodology — performance excellence pursuit
- **2020**: VWBE Culture (자발적·의욕적 두뇌활용), social value creation, employee happiness

## Working with This File

- The text contains OCR artifacts and inconsistent formatting across editions
- Korean text with occasional English management terms (e.g., Span of Control, O.J.T, SUPEX)
- Section markers use Korean numbering (가, 나, 다) and Arabic numerals
- Some sections are marked as drafts: "(임원 세미나에서 논의된 것을 요약한 것으로, 추후 보완함)"
- Line separators (`---`) appear between major sections
- The document is **not** a flat list — later editions redefine and expand earlier concepts, so the same topic (e.g., 인사관리) appears multiple times with different depth across editions

## Project Overview

This repository also contains a **Time-Aware RAG pipeline** built on top of SKMSraw.txt.

### Development Status
- **Phase 0~3**: Complete (39 PRs, 1216 tests, 93% coverage)
- **Phase 4**: Content Studio — COMPLETE (52 PRs, 1850 tests, 95.80% coverage)
- **Phase 4.5**: Frontend Integration — COMPLETE (STEP 1–9 done, 23/29 API connections, 1864+ tests, E2E 15 cases)
- **Phase 5**: Roadmap planned (UX improvements, video gen, LMS integration)
- **GitHub**: crystal0224/skmsai (private)

### Key Source Directories
```
src/
├── models/          # QuoteObject, frozen dataclasses
├── db/              # SQLite repository, migrations
├── search/          # VectorStore, BM25, SearchService, hybrid search
├── generation/      # GenerationService, QueryRouter, OutputRenderer
├── api/             # FastAPI server, routes (/query, /search, /toc, /health)
├── ui/              # Streamlit MVP
├── ingestion/       # Pipeline: parse → chunk → embed → store
├── toc/             # Table of contents API
├── cross_version/   # Cross-edition comparison service
└── eval/            # Evaluation framework, quality gate
src/
└── content_studio/      # 5-stage Content Studio pipeline (Phase 4, moved from scripts/lib/)
    ├── adapters/        # MCP adapters (NanoBanana, AntV, ElevenLabs, Notion, GWS)
    ├── models.py        # ContentRequest/Plan/Result frozen dataclasses
    ├── planner.py       # ContentPlanner (6 content types)
    ├── generator.py     # ContentGenerator (RAG → LLM → sections)
    ├── assembler.py     # FileAssembler (PPTX, HTML, PDF, SVG, MP3)
    └── publisher.py     # Publisher (local, Notion, Google Workspace)
scripts/
├── 01~13_*.py           # Numbered scripts for build, eval, migration
├── test_mcp_live.py     # MCP adapter smoke tests
└── cleanup_output.py    # Output directory maintenance
server/              # FastAPI production server (app.py, routes/, models.py)
tests/               # ~70 test files, pytest + pytest-asyncio + Playwright E2E
prompts/             # Edition-aware + content generation prompt templates
config/              # content_studio.yaml, pptx_themes.yaml, nano_banana_style.yaml
data/                # SKMSraw.txt, edition metadata YAML
docs/                # Design documents, MCP setup guide, content studio guide
everline-studio-clone/  # Frontend UI (vanilla HTML/CSS/JS, Phase 4.5)
```

### Architecture Summary
- **Domain models**: frozen dataclasses (immutable, tuples for collections)
- **Database**: SQLite (WAL mode, foreign keys, migrations)
- **Search**: Hybrid (ChromaDB vector + BM25 keyword) → rerank → temporal filter
- **Generation**: QueryRouter → prompt template → LLM → OutputRenderer (5 types)
- **Content Studio**: 5-stage pipeline (Plan → Generate → Assets → Assemble → Publish), 6 content types, Protocol-based MCP adapters, PlanCache (SHA256, 24h TTL)
- **API**: FastAPI with closure-based DI (AppState pattern), async content generation, file download, publish endpoint
- **Frontend**: Vanilla HTML/CSS/JS SPA (everline-studio-clone/) — 6종 콘텐츠 생성, 미리보기, 플랜 편집, 대시보드, 발행
- **Testing**: pytest, 95%+ coverage, `FastAPI_with_mock_state()` helper, ~70 test files + Playwright E2E 15 cases

### Running the Project
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Start API server
python -m uvicorn src.api.main:app --reload

# Start Streamlit UI
streamlit run src/ui/app.py
```

"""SKMS RAG Pipeline 관측 레이어 (PR-2).

trace_id 기반 파이프라인 단계별 추적.
Langfuse(우선) → LangSmith → 로컬 순으로 백엔드 자동 감지.

개인정보 정책:
  - 원문 텍스트 기본 저장 금지
  - quote_id/doc_id/span/sha256 중심 저장
  - text_preview는 설정에 따라 400자 제한 (기본 OFF)

Langfuse 설정:
    export LANGFUSE_PUBLIC_KEY=pk-lf-...
    export LANGFUSE_SECRET_KEY=sk-lf-...
    export LANGFUSE_HOST=https://cloud.langfuse.com

LangSmith 설정 (대안):
    export LANGCHAIN_TRACING_V2=true
    export LANGCHAIN_API_KEY=ls_...
    export LANGCHAIN_PROJECT=skms-rag

설정 없으면 로컬 모드 (graceful degradation).
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict[str, Any] = {
    "tracer": "auto",
    "console": {"print_trace_id": True, "print_step_summary": False},
    "privacy": {
        "store_raw_text": False,
        "text_preview": {"enabled": False, "max_chars": 400},
    },
}


def load_observability_config(
    path: str = "config/observability.yaml",
) -> dict[str, Any]:
    """관측 설정을 로드한다. 파일 없으면 기본값 반환."""
    config_path = Path(path)
    if config_path.exists():
        try:
            import yaml

            with open(config_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            return raw.get("observability", dict(_DEFAULT_CONFIG))
        except (ImportError, Exception):
            pass
    return dict(_DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------


def _detect_tracer() -> str:
    """활성화된 트레이서를 감지한다. Langfuse 우선."""
    if os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return "langfuse"
    if os.environ.get("LANGCHAIN_TRACING_V2") == "true":
        return "langsmith"
    return "local"


# 모듈 로드 시점에 한 번만 감지
_TRACER = _detect_tracer()


# ---------------------------------------------------------------------------
# Privacy helpers
# ---------------------------------------------------------------------------


def _safe_retrieval_hit(hit: dict, config: dict) -> dict:
    """검색 결과를 privacy-safe dict로 변환한다.

    원문 텍스트는 기본 저장 금지. quote_id/doc_id/span/sha256 중심.
    """
    privacy = config.get("privacy", {})

    safe: dict[str, Any] = {
        "quote_id": hit.get("quote_id", ""),
        "doc_id": hit.get("doc_id", ""),
        "year": hit.get("year", 0),
        "edition": hit.get("edition", ""),
        "type": hit.get("type", ""),
        "score": round(hit.get("score", 0.0), 4),
        "span": hit.get("span", [0, 0]),
        "sha256": hit.get("sha256", ""),
        "quality_flags": hit.get("quality_flags", []),
        "text_length": len(hit.get("text", "")),
    }

    # text_preview (기본 OFF)
    preview_cfg = privacy.get("text_preview", {})
    if preview_cfg.get("enabled", False):
        text = hit.get("text", "")
        max_chars = preview_cfg.get("max_chars", 400)
        if len(text) > max_chars:
            safe["text_preview"] = text[:max_chars] + "..."
        else:
            safe["text_preview"] = text

    return safe


def _estimate_tokens(text: str) -> int:
    """토큰 수를 추정한다.

    한국어 비중 30% 이상: ~2 chars/token, 그 외: ~4 chars/token.
    """
    if not text:
        return 0
    korean_chars = sum(1 for c in text if "\uac00" <= c <= "\ud7a3")
    ratio = korean_chars / max(len(text), 1)
    chars_per_token = 2 if ratio > 0.3 else 4
    return len(text) // chars_per_token


def _step_summary(name: str, data: dict) -> str:
    """단계 요약을 한 줄로 생성한다 (콘솔 출력용)."""
    if name == "router":
        return f"intent={data.get('intent')} confidence={data.get('confidence')}"
    if name == "policy":
        return f"alpha={data.get('alpha')} latest_first={data.get('latest_first')}"
    if name == "retrieval":
        return f"{data.get('hit_count')} hits"
    if name == "prompt":
        return f"~{data.get('context_token_estimate')} ctx tokens"
    if name == "response":
        return f"~{data.get('response_token_estimate')} tokens"
    if name == "validation":
        status = "PASS" if data.get("passed") else "FAIL"
        return (
            f"{status} ({data.get('output_type')}) errors={data.get('error_count', 0)}"
        )
    return str(data)[:80]


# ---------------------------------------------------------------------------
# PipelineTrace
# ---------------------------------------------------------------------------


class PipelineTrace:
    """단일 파이프라인 실행의 관측 트레이스.

    context manager로 사용하면 finish()가 자동 호출된다:

        with start_trace(query, config) as trace:
            trace.log_router(...)
            trace.log_retrieval(...)
    """

    def __init__(self, trace_id: str, query: str, config: dict) -> None:
        self.trace_id = trace_id
        self._config = config
        self._steps: list[dict] = []
        self._start_time = time.time()
        self._backend: str = "local"
        self._backend_trace: Any = None
        self._lf: Any = None
        self._ls_client: Any = None

        # 콘솔 출력
        if config.get("console", {}).get("print_trace_id", True):
            print(f"[trace] {trace_id}", file=sys.stderr)

        # 백엔드 초기화
        self._init_backend(query)

    def _init_backend(self, query: str) -> None:
        tracer = self._config.get("tracer", "auto")
        if tracer == "auto":
            tracer = _TRACER

        if tracer == "langfuse":
            try:
                from langfuse import Langfuse

                self._backend = "langfuse"
                lf = Langfuse()
                self._lf = lf
                self._backend_trace = lf.trace(
                    name="skms_rag",
                    id=self.trace_id,
                    input={"query_length": len(query)},
                )
            except (ImportError, Exception) as e:
                print(
                    f"[관측] Langfuse 초기화 실패: {e} — local로 전환",
                    file=sys.stderr,
                )
                self._backend = "local"

        elif tracer == "langsmith":
            try:
                from langsmith import Client

                self._backend = "langsmith"
                self._ls_client = Client()
                self._ls_client.create_run(
                    name="skms_rag",
                    run_type="chain",
                    id=self.trace_id,
                    inputs={"query_length": len(query)},
                )
            except (ImportError, Exception) as e:
                print(
                    f"[관측] LangSmith 초기화 실패: {e} — local로 전환",
                    file=sys.stderr,
                )
                self._backend = "local"

        else:
            self._backend = "local"

    # --- Context manager ---

    def __enter__(self) -> PipelineTrace:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.finish()
        return False  # 예외 전파

    # --- Step loggers ---

    def log_router(
        self,
        intent: str,
        confidence: float,
        edition_hint: str | None,
        output_type: str | None,
        type_filter: list[str] | None = None,
        section_filter: str | None = None,
    ) -> None:
        """라우터 결과를 기록한다."""
        data = {
            "intent": intent,
            "confidence": round(confidence, 3),
            "edition_hint": edition_hint,
            "output_type": output_type,
            "type_filter": type_filter,
            "section_filter": section_filter,
        }
        self._record_step("router", data)

    def log_policy(self, policy: dict) -> None:
        """적용된 검색 정책/필터를 기록한다."""
        safe_policy = {
            "edition_filter": policy.get("edition_filter"),
            "edition_hint": policy.get("edition_hint"),
            "type_filter": policy.get("type_filter"),
            "section_filter": policy.get("section_filter"),
            "alpha": policy.get("alpha"),
            "rrf_k": policy.get("rrf_k"),
            "latest_first": policy.get("latest_first", False),
            "vec_top_k": policy.get("vec_top_k"),
            "bm25_top_k": policy.get("bm25_top_k"),
            "fallback_editions": policy.get("_policy_fallback_editions"),
            "min_hits": policy.get("_policy_min_hits"),
        }
        self._record_step("policy", safe_policy)

    def log_retrieval(self, results: list[dict]) -> None:
        """검색 결과를 privacy-safe하게 기록한다.

        원문 텍스트 대신 quote_id/doc_id/span/sha256만 저장.
        text_preview는 설정에 따라 400자 제한 (기본 OFF).
        """
        safe_hits = [_safe_retrieval_hit(h, self._config) for h in results]
        data = {
            "hit_count": len(results),
            "hits": safe_hits,
        }
        self._record_step("retrieval", data)

    def log_prompt(self, context: str, system_prompt_name: str) -> None:
        """프롬프트 메타데이터를 기록한다 (원문 저장 안 함)."""
        data = {
            "system_prompt": system_prompt_name,
            "context_char_count": len(context),
            "context_token_estimate": _estimate_tokens(context),
        }
        self._record_step("prompt", data)

    def log_response(self, answer: str) -> None:
        """응답 메타데이터를 기록한다 (원문 저장 안 함)."""
        data = {
            "response_char_count": len(answer),
            "response_token_estimate": _estimate_tokens(answer),
        }
        self._record_step("response", data)

    def log_validation(self, validation_result: dict) -> None:
        """PR-7: 콘텐츠 출력 스키마 검증 결과를 기록한다."""
        self._record_step("validation", validation_result)

    def finish(self) -> None:
        """트레이스를 완료하고 백엔드에 flush한다."""
        elapsed = time.time() - self._start_time
        summary = {
            "trace_id": self.trace_id,
            "elapsed_seconds": round(elapsed, 2),
            "step_count": len(self._steps),
        }

        if self._backend == "langfuse" and self._backend_trace:
            try:
                self._backend_trace.update(output=summary)
                self._lf.flush()
            except Exception:
                pass

        elif self._backend == "langsmith" and self._ls_client:
            try:
                from datetime import datetime, timezone

                self._ls_client.update_run(
                    self.trace_id,
                    end_time=datetime.now(tz=timezone.utc),
                    outputs=summary,
                )
            except Exception:
                pass

        if self._config.get("console", {}).get("print_step_summary", False):
            print(
                f"[trace] {self.trace_id} 완료:"
                f" {elapsed:.2f}s, {len(self._steps)} steps",
                file=sys.stderr,
            )

    # --- Internal ---

    def _record_step(self, name: str, data: dict) -> None:
        """단계 이벤트를 기록한다."""
        step = {"step": name, "timestamp": time.time(), **data}
        self._steps.append(step)

        # Langfuse span
        if self._backend == "langfuse" and self._backend_trace:
            try:
                self._backend_trace.span(name=name, output=data)
            except Exception:
                pass

        # LangSmith child run
        elif self._backend == "langsmith" and self._ls_client:
            try:
                from datetime import datetime, timezone

                child_id = str(uuid.uuid4())
                now = datetime.now(tz=timezone.utc)
                self._ls_client.create_run(
                    name=name,
                    run_type="chain",
                    id=child_id,
                    parent_run_id=self.trace_id,
                    inputs={},
                    outputs=data,
                    start_time=now,
                    end_time=now,
                )
            except Exception:
                pass

        # 콘솔 요약 (디버깅용)
        if self._config.get("console", {}).get("print_step_summary", False):
            short_id = self.trace_id[:8]
            print(
                f"[trace:{short_id}] {name}: {_step_summary(name, data)}",
                file=sys.stderr,
            )

    @property
    def steps(self) -> list[dict]:
        """기록된 단계 이벤트를 반환한다 (읽기 전용 복사)."""
        return list(self._steps)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def start_trace(
    query: str,
    config: dict | None = None,
) -> PipelineTrace:
    """새 파이프라인 트레이스를 시작한다.

    Args:
        query: 원본 질의 (길이만 기록, 텍스트는 저장하지 않음)
        config: 관측 설정 dict (None이면 config/observability.yaml 로드)

    Returns:
        PipelineTrace — context manager로 사용 가능
    """
    if config is None:
        config = load_observability_config()
    trace_id = str(uuid.uuid4())
    return PipelineTrace(trace_id, query, config)


# ---------------------------------------------------------------------------
# Legacy API (backward compatibility — PR-1에서 사용)
# ---------------------------------------------------------------------------


def traceable(name: str) -> Callable:
    """LLM 호출을 추적하는 데코레이터 (legacy).

    Langfuse @observe 또는 LangSmith @traceable를 래핑한다.
    설정되지 않으면 원래 함수를 그대로 실행한다 (오버헤드 0).
    """

    def decorator(func: Callable) -> Callable:
        if _TRACER == "langfuse":
            try:
                from langfuse.decorators import observe

                return observe(name=name)(func)
            except ImportError:
                print(
                    f"[관측] langfuse 패키지 없음 — {name} 추적 비활성화",
                    file=sys.stderr,
                )
                return func

        elif _TRACER == "langsmith":
            try:
                from langsmith import traceable as ls_traceable

                return ls_traceable(name=name)(func)
            except ImportError:
                print(
                    f"[관측] langsmith 패키지 없음 — {name} 추적 비활성화",
                    file=sys.stderr,
                )
                return func

        return func

    return decorator


def flush() -> None:
    """트레이싱 버퍼를 플러시한다. 프로세스 종료 전 호출 권장."""
    if _TRACER == "langfuse":
        try:
            from langfuse.decorators import langfuse_context

            langfuse_context.flush()
        except (ImportError, Exception):
            pass

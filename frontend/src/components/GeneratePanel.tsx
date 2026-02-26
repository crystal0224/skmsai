"use client";

import { useState } from "react";
import type { OutputType, GenerateV2Response } from "@/types/api";
import { generate } from "@/lib/api-client";

const OUTPUT_TYPES: { value: OutputType | ""; label: string }[] = [
  { value: "", label: "자유 형식 (없음)" },
  { value: "summary", label: "요약" },
  { value: "card", label: "학습 카드" },
  { value: "quiz", label: "퀴즈" },
  { value: "comparison_table", label: "비교표" },
  { value: "slide", label: "슬라이드" },
];

export default function GeneratePanel() {
  const [query, setQuery] = useState("");
  const [outputType, setOutputType] = useState<OutputType | "">("");
  const [editionFilter, setEditionFilter] = useState("");
  const [topK, setTopK] = useState(5);
  const [result, setResult] = useState<GenerateV2Response | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError("");
    try {
      const res = await generate({
        query: query.trim(),
        output_type: outputType || null,
        edition_filter: editionFilter || null,
        top_k: topK,
        include_evidence_check: true,
        include_rendered: true,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "생성 실패");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={handleGenerate} className="space-y-4">
        <div>
          <label htmlFor="gen-query" className="block text-sm font-medium mb-1">
            질의
          </label>
          <textarea
            id="gen-query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="예: SKMS에서 인간중심 경영의 의미를 요약해줘"
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-800 dark:border-gray-600"
          />
        </div>

        <div className="flex gap-4 flex-wrap">
          <div>
            <label htmlFor="output-type" className="block text-sm font-medium mb-1">
              출력 형식
            </label>
            <select
              id="output-type"
              value={outputType}
              onChange={(e) => setOutputType(e.target.value as OutputType | "")}
              className="px-3 py-2 border border-gray-300 rounded-lg dark:bg-gray-800 dark:border-gray-600"
            >
              {OUTPUT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="gen-top-k" className="block text-sm font-medium mb-1">
              검색 수
            </label>
            <input
              id="gen-top-k"
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-20 px-3 py-2 border border-gray-300 rounded-lg dark:bg-gray-800 dark:border-gray-600"
            />
          </div>

          <div>
            <label htmlFor="gen-edition" className="block text-sm font-medium mb-1">
              개정판 필터
            </label>
            <input
              id="gen-edition"
              type="text"
              value={editionFilter}
              onChange={(e) => setEditionFilter(e.target.value)}
              placeholder="예: 2020-14차"
              className="w-40 px-3 py-2 border border-gray-300 rounded-lg dark:bg-gray-800 dark:border-gray-600"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "생성 중..." : "답변 생성"}
        </button>
      </form>

      {error && (
        <div className="p-3 bg-red-50 text-red-700 rounded-lg border border-red-200 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {result && <GenerateResult result={result} />}
    </div>
  );
}

function GenerateResult({ result }: { result: GenerateV2Response }) {
  return (
    <div className="space-y-4">
      {/* Metadata */}
      <div className="flex gap-3 flex-wrap text-sm">
        <span className="px-2 py-1 rounded bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300">
          의도: {result.intent}
        </span>
        <span className="px-2 py-1 rounded bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
          프롬프트: {result.prompt_name}
        </span>
        <span className="px-2 py-1 rounded bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
          검색: {result.search_hits_count}건
        </span>
        {result.validation_passed !== null && (
          <span
            className={`px-2 py-1 rounded ${
              result.validation_passed
                ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                : "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
            }`}
          >
            검증: {result.validation_passed ? "통과" : "실패"}
          </span>
        )}
      </div>

      {/* Rendered output */}
      {result.rendered && result.render_success ? (
        <div className="border border-gray-200 rounded-lg p-4 dark:border-gray-700">
          <h4 className="text-sm font-medium text-gray-500 mb-2">렌더링 결과</h4>
          <div
            className="prose dark:prose-invert max-w-none"
            dangerouslySetInnerHTML={{ __html: markdownToHtml(result.rendered) }}
          />
        </div>
      ) : (
        <div className="border border-gray-200 rounded-lg p-4 dark:border-gray-700">
          <h4 className="text-sm font-medium text-gray-500 mb-2">원문 응답</h4>
          <pre className="text-sm whitespace-pre-wrap text-gray-800 dark:text-gray-200">
            {result.answer}
          </pre>
        </div>
      )}

      {/* Evidence check */}
      {result.evidence_check && (
        <div className="border border-gray-200 rounded-lg p-4 dark:border-gray-700">
          <h4 className="text-sm font-medium text-gray-500 mb-2">근거 검증</h4>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <span>커버리지: {(result.evidence_check.coverage_score * 100).toFixed(1)}%</span>
            <span
              className={
                result.evidence_check.passed ? "text-green-600" : "text-red-600"
              }
            >
              {result.evidence_check.passed ? "통과" : "미달"}
            </span>
            <span>유효 인용: {result.evidence_check.valid_quote_ids.length}건</span>
            <span>무효 인용: {result.evidence_check.invalid_quote_ids.length}건</span>
          </div>
        </div>
      )}

      {/* Citations */}
      {result.citations.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-500 mb-1">
            인용 ({result.citations.length}건)
          </h4>
          <div className="flex gap-1 flex-wrap">
            {result.citations.map((c) => (
              <code
                key={c}
                className="text-xs px-2 py-0.5 bg-gray-100 rounded dark:bg-gray-700"
              >
                {c}
              </code>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Markdown → 간단 HTML 변환 (순수 함수, 외부 의존 없음). */
function markdownToHtml(md: string): string {
  return md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, "<h3 class='text-lg font-semibold mt-4 mb-2'>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2 class='text-xl font-bold mt-6 mb-3'>$1</h2>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code class='bg-gray-100 dark:bg-gray-700 px-1 rounded text-sm'>$1</code>")
    .replace(/^- (.+)$/gm, "<li class='ml-4'>$1</li>")
    .replace(/^(\d+)\. (.+)$/gm, "<li class='ml-4'>$1. $2</li>")
    .replace(/^---$/gm, "<hr class='my-3 border-gray-300 dark:border-gray-600' />")
    .replace(/\n/g, "<br />");
}

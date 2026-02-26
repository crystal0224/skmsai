"use client";

import { useState } from "react";
import type { SearchHit, SearchMode } from "@/types/api";
import { search } from "@/lib/api-client";

const SEARCH_MODES: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "하이브리드" },
  { value: "vector", label: "벡터" },
  { value: "bm25", label: "BM25" },
];

const QUOTE_TYPES = [
  "definition",
  "principle",
  "procedure",
  "checklist",
  "example",
  "narrative",
];

export default function SearchPanel() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [topK, setTopK] = useState(5);
  const [editionFilter, setEditionFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError("");
    try {
      const res = await search({
        query: query.trim(),
        mode,
        top_k: topK,
        edition_filter: editionFilter || null,
        type_filter: typeFilter.length > 0 ? typeFilter : null,
      });
      setHits(res.hits);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "검색 실패");
      setHits([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }

  function toggleType(t: string) {
    setTypeFilter((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    );
  }

  return (
    <div className="space-y-6">
      <form onSubmit={handleSearch} className="space-y-4">
        {/* Query input */}
        <div>
          <label htmlFor="search-query" className="block text-sm font-medium mb-1">
            검색 질의
          </label>
          <input
            id="search-query"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="예: SUPEX란 무엇인가?"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-800 dark:border-gray-600"
          />
        </div>

        {/* Mode + top_k */}
        <div className="flex gap-4 flex-wrap">
          <div>
            <label htmlFor="search-mode" className="block text-sm font-medium mb-1">
              검색 모드
            </label>
            <select
              id="search-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as SearchMode)}
              className="px-3 py-2 border border-gray-300 rounded-lg dark:bg-gray-800 dark:border-gray-600"
            >
              {SEARCH_MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="top-k" className="block text-sm font-medium mb-1">
              결과 수 (top_k)
            </label>
            <input
              id="top-k"
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-20 px-3 py-2 border border-gray-300 rounded-lg dark:bg-gray-800 dark:border-gray-600"
            />
          </div>

          <div>
            <label htmlFor="edition-filter" className="block text-sm font-medium mb-1">
              개정판 필터
            </label>
            <input
              id="edition-filter"
              type="text"
              value={editionFilter}
              onChange={(e) => setEditionFilter(e.target.value)}
              placeholder="예: 2020-14차"
              className="w-40 px-3 py-2 border border-gray-300 rounded-lg dark:bg-gray-800 dark:border-gray-600"
            />
          </div>
        </div>

        {/* Type filter */}
        <div>
          <span className="block text-sm font-medium mb-1">타입 필터</span>
          <div className="flex gap-2 flex-wrap">
            {QUOTE_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => toggleType(t)}
                className={`px-3 py-1 text-sm rounded-full border transition-colors ${
                  typeFilter.includes(t)
                    ? "bg-blue-500 text-white border-blue-500"
                    : "bg-white text-gray-700 border-gray-300 hover:bg-gray-100 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-600"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "검색 중..." : "검색"}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 text-red-700 rounded-lg border border-red-200 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Results */}
      {hits.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-lg font-semibold">검색 결과 ({total}건)</h3>
          {hits.map((hit, idx) => (
            <SearchHitCard key={hit.quote_id} hit={hit} rank={idx + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function SearchHitCard({ hit, rank }: { hit: SearchHit; rank: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow dark:border-gray-700">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-mono text-gray-500">#{rank}</span>
            <span className="px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
              {hit.edition_id}
            </span>
            <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
              {hit.quote_type}
            </span>
            <span className="text-sm text-gray-500">
              점수: {hit.score.toFixed(3)}
            </span>
          </div>
          <p
            className={`text-sm text-gray-800 dark:text-gray-200 ${
              expanded ? "" : "line-clamp-3"
            }`}
          >
            {hit.text}
          </p>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="ml-2 text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400 shrink-0"
        >
          {expanded ? "접기" : "펼치기"}
        </button>
      </div>
      {expanded && (
        <div className="mt-2 text-xs text-gray-500 space-y-1">
          <p>
            <strong>경로:</strong> {hit.section_path.join(" > ")}
          </p>
          <p>
            <strong>quote_id:</strong>{" "}
            <code className="bg-gray-100 px-1 rounded dark:bg-gray-700">
              {hit.quote_id}
            </code>
          </p>
        </div>
      )}
    </div>
  );
}

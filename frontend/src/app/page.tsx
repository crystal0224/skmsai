"use client";

import { useState } from "react";
import SearchPanel from "@/components/SearchPanel";
import GeneratePanel from "@/components/GeneratePanel";
import TOCPanel from "@/components/TOCPanel";
import ContentStudioPanel from "@/components/ContentStudioPanel";

type Tab = "search" | "generate" | "toc" | "studio";

const TABS: { id: Tab; label: string; description: string }[] = [
  { id: "search", label: "검색", description: "SKMS 원문 하이브리드 검색" },
  { id: "generate", label: "생성", description: "AI 답변 및 콘텐츠 생성" },
  { id: "toc", label: "목차", description: "개정판별 목차 탐색" },
  {
    id: "studio",
    label: "Content Studio",
    description: "교육 콘텐츠 자동 생성 (강의자료, 카드뉴스, 워크숍, 퀴즈)",
  },
];

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("search");

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            SKMS Time-Aware NotebookLM
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            SK경영체계 원문 검색 · AI 분석 · 개정판 비교
          </p>
        </div>
      </header>

      {/* Tab navigation */}
      <nav className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-6xl mx-auto px-4">
          <div className="flex gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? "border-blue-500 text-blue-600 dark:text-blue-400"
                    : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Tab content */}
      <main className="max-w-6xl mx-auto px-4 py-6">
        <p className="text-sm text-gray-500 mb-4">
          {TABS.find((t) => t.id === activeTab)?.description}
        </p>
        {activeTab === "search" && <SearchPanel />}
        {activeTab === "generate" && <GeneratePanel />}
        {activeTab === "toc" && <TOCPanel />}
        {activeTab === "studio" && <ContentStudioPanel />}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 dark:border-gray-700 mt-auto">
        <div className="max-w-6xl mx-auto px-4 py-4 text-center text-xs text-gray-400">
          SKMS Time-Aware NotebookLM v2 &mdash; Powered by RAG Pipeline
        </div>
      </footer>
    </div>
  );
}

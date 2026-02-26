"use client";

import { useEffect, useState } from "react";
import type { EditionInfo, TOCNode, TOCResponse } from "@/types/api";
import { getEditions, getTOC } from "@/lib/api-client";

export default function TOCPanel() {
  const [editions, setEditions] = useState<EditionInfo[]>([]);
  const [selectedEdition, setSelectedEdition] = useState("");
  const [toc, setToc] = useState<TOCResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getEditions()
      .then((res) => setEditions(res.editions))
      .catch(() => setError("개정판 목록을 불러올 수 없습니다."));
  }, []);

  async function handleEditionChange(editionId: string) {
    setSelectedEdition(editionId);
    if (!editionId) {
      setToc(null);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const res = await getTOC(editionId);
      setToc(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "목차 로드 실패");
      setToc(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="edition-select" className="block text-sm font-medium mb-1">
          개정판 선택
        </label>
        <select
          id="edition-select"
          value={selectedEdition}
          onChange={(e) => handleEditionChange(e.target.value)}
          className="w-full max-w-md px-3 py-2 border border-gray-300 rounded-lg dark:bg-gray-800 dark:border-gray-600"
        >
          <option value="">-- 개정판 선택 --</option>
          {editions.map((ed) => (
            <option key={ed.edition_id} value={ed.edition_id}>
              {ed.label} ({ed.year}) — {ed.section_count}개 섹션
            </option>
          ))}
        </select>
      </div>

      {loading && <p className="text-gray-500">목차를 불러오는 중...</p>}

      {error && (
        <div className="p-3 bg-red-50 text-red-700 rounded-lg border border-red-200 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {toc && (
        <div>
          <h3 className="text-lg font-semibold mb-2">
            {toc.label} ({toc.year}) — {toc.node_count}개 노드
          </h3>
          <div className="border border-gray-200 rounded-lg p-4 dark:border-gray-700 overflow-auto max-h-[600px]">
            {toc.sections.map((node, idx) => (
              <TOCTreeNode key={`${node.title}-${idx}`} node={node} depth={0} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TOCTreeNode({ node, depth }: { node: TOCNode; depth: number }) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = node.children.length > 0;
  const indent = depth * 16;

  const levelColors: Record<string, string> = {
    H0: "text-gray-800 font-bold dark:text-gray-100",
    H1: "text-gray-700 font-semibold dark:text-gray-200",
    H2: "text-gray-600 dark:text-gray-300",
    H3: "text-gray-500 dark:text-gray-400",
    H4: "text-gray-400 text-sm dark:text-gray-500",
    H5: "text-gray-400 text-sm dark:text-gray-500",
  };

  return (
    <div style={{ paddingLeft: `${indent}px` }}>
      <div
        className={`flex items-center gap-1 py-1 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded px-1 ${
          levelColors[node.level] ?? "text-gray-600"
        }`}
        onClick={() => hasChildren && setExpanded(!expanded)}
      >
        {hasChildren && (
          <span className="text-xs text-gray-400 w-4 text-center">
            {expanded ? "▼" : "▶"}
          </span>
        )}
        {!hasChildren && <span className="w-4" />}
        <span className="text-xs text-gray-400 font-mono">{node.level}</span>
        <span>{node.title}</span>
        <span className="text-xs text-gray-400 ml-auto">L{node.line}</span>
      </div>
      {expanded &&
        hasChildren &&
        node.children.map((child, idx) => (
          <TOCTreeNode
            key={`${child.title}-${idx}`}
            node={child}
            depth={depth + 1}
          />
        ))}
    </div>
  );
}

"use client";

import { useState, useEffect } from "react";
import type {
  ContentType,
  ContentTypeInfo,
  ContentOptionsRequest,
  ContentGenerateResponse,
  ContentPlanResponse,
} from "@/types/api";
import {
  getContentTypes,
  previewPlan,
  generateContent,
} from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TYPE_ICONS: Record<ContentType, string> = {
  lecture: "Lecture",
  card_news: "Card",
  workshop: "Workshop",
  visualization: "Viz",
  audio: "Audio",
  quiz: "Quiz",
};

const STYLE_OPTIONS = [
  { value: "professional", label: "Corporate (SK)" },
  { value: "casual", label: "Education" },
  { value: "academic", label: "Seminar" },
];

type Step = "type" | "options" | "result";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TypeCard({
  info,
  selected,
  onClick,
}: {
  info: ContentTypeInfo;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`text-left p-4 rounded-lg border-2 transition-all ${
        selected
          ? "border-blue-500 bg-blue-50 dark:bg-blue-900/30"
          : "border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-600"
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-mono px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
          {TYPE_ICONS[info.type] ?? info.type}
        </span>
        <span className="font-semibold text-gray-900 dark:text-white">
          {info.label}
        </span>
      </div>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
        {info.description}
      </p>
      <div className="flex gap-1 mt-2">
        {info.output_formats.map((fmt) => (
          <span
            key={fmt}
            className="text-xs px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300"
          >
            {fmt.toUpperCase()}
          </span>
        ))}
      </div>
    </button>
  );
}

function PlanPreview({ plan }: { plan: ContentPlanResponse }) {
  const data = plan.plan;
  const title = typeof data.title === "string" ? data.title : plan.topic;
  const subtitle = typeof data.subtitle === "string" ? data.subtitle : null;
  const slides = Array.isArray(data.slides)
    ? (data.slides as { index: number; title: string }[])
    : null;
  const cards = Array.isArray(data.cards)
    ? (data.cards as { index: number; headline: string }[])
    : null;
  const phases = Array.isArray(data.phases)
    ? (data.phases as { title: string; duration_min: number }[])
    : null;
  const questions = Array.isArray(data.questions)
    ? (data.questions as { index: number; question_text: string }[])
    : null;
  const sections = Array.isArray(data.sections)
    ? (data.sections as { speaker: string; text: string }[])
    : null;

  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-sm">
      <h4 className="font-semibold text-gray-900 dark:text-white mb-2">
        {title}
      </h4>
      {subtitle && (
        <p className="text-gray-500 dark:text-gray-400 mb-2">{subtitle}</p>
      )}
      {slides && (
        <div className="space-y-1">
          <p className="font-medium text-gray-700 dark:text-gray-300">
            Slides ({slides.length})
          </p>
          {slides.map((s) => (
            <div
              key={s.index}
              className="pl-3 text-gray-600 dark:text-gray-400"
            >
              {s.index}. {s.title}
            </div>
          ))}
        </div>
      )}
      {cards && (
        <div className="space-y-1">
          <p className="font-medium text-gray-700 dark:text-gray-300">
            Cards ({cards.length})
          </p>
          {cards.map((c) => (
            <div
              key={c.index}
              className="pl-3 text-gray-600 dark:text-gray-400"
            >
              {c.index}. {c.headline}
            </div>
          ))}
        </div>
      )}
      {phases && (
        <div className="space-y-1">
          <p className="font-medium text-gray-700 dark:text-gray-300">
            Phases ({phases.length})
          </p>
          {phases.map((p, i) => (
            <div key={i} className="pl-3 text-gray-600 dark:text-gray-400">
              {p.title} ({p.duration_min}min)
            </div>
          ))}
        </div>
      )}
      {questions && (
        <div className="space-y-1">
          <p className="font-medium text-gray-700 dark:text-gray-300">
            Questions ({questions.length})
          </p>
          {questions.map((q) => (
            <div
              key={q.index}
              className="pl-3 text-gray-600 dark:text-gray-400"
            >
              Q{q.index}. {q.question_text}
            </div>
          ))}
        </div>
      )}
      {sections && (
        <div className="space-y-1">
          <p className="font-medium text-gray-700 dark:text-gray-300">
            Sections ({sections.length})
          </p>
          {sections.map((s, i) => (
            <div key={i} className="pl-3 text-gray-600 dark:text-gray-400">
              [{s.speaker}] {s.text.slice(0, 60)}...
            </div>
          ))}
        </div>
      )}
      <details className="mt-3">
        <summary className="cursor-pointer text-xs text-gray-400">
          Raw JSON
        </summary>
        <pre className="mt-1 text-xs overflow-auto max-h-48 bg-white dark:bg-gray-900 p-2 rounded">
          {JSON.stringify(data, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function ResultView({ result }: { result: ContentGenerateResponse }) {
  const meta = result.metadata;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-xs font-mono px-2 py-1 rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
          {result.content_type}
        </span>
        <span className="font-semibold text-gray-900 dark:text-white">
          {result.topic}
        </span>
        {meta.total_elapsed_ms != null && (
          <span className="text-xs text-gray-400">
            {Number(meta.total_elapsed_ms).toFixed(0)}ms
          </span>
        )}
      </div>

      <div className="space-y-2">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Generated Files ({result.files.length})
        </h4>
        {result.files.map((f, i) => (
          <div
            key={i}
            className="flex items-center justify-between bg-gray-50 dark:bg-gray-800 rounded p-3"
          >
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-300">
                {f.file_type.toUpperCase()}
              </span>
              <span className="text-sm text-gray-700 dark:text-gray-300">
                {f.file_name}
              </span>
            </div>
            <span className="text-xs text-gray-400">
              {(f.size_bytes / 1024).toFixed(1)} KB
            </span>
          </div>
        ))}
      </div>

      {result.citations.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Citations ({result.citations.length})
          </h4>
          <div className="flex flex-wrap gap-1">
            {result.citations.map((c) => (
              <span
                key={c}
                className="text-xs px-2 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300"
              >
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      <details>
        <summary className="cursor-pointer text-xs text-gray-400">
          Metadata
        </summary>
        <pre className="mt-1 text-xs overflow-auto max-h-32 bg-gray-50 dark:bg-gray-800 p-2 rounded">
          {JSON.stringify(meta, null, 2)}
        </pre>
      </details>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ContentStudioPanel() {
  // Content types (loaded on mount)
  const [types, setTypes] = useState<ContentTypeInfo[]>([]);
  const [typesLoading, setTypesLoading] = useState(true);

  // Wizard state
  const [step, setStep] = useState<Step>("type");
  const [selectedType, setSelectedType] = useState<ContentType | null>(null);
  const [topic, setTopic] = useState("");
  const [options, setOptions] = useState<ContentOptionsRequest>({
    style: "professional",
    language: "ko",
    include_speaker_notes: true,
  });

  // Plan preview
  const [plan, setPlan] = useState<ContentPlanResponse | null>(null);
  const [planLoading, setPlanLoading] = useState(false);

  // Generation result
  const [result, setResult] = useState<ContentGenerateResponse | null>(null);
  const [generating, setGenerating] = useState(false);

  // Error
  const [error, setError] = useState("");

  // Load content types on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await getContentTypes();
        setTypes(res.types);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load content types",
        );
      } finally {
        setTypesLoading(false);
      }
    })();
  }, []);

  // Handlers
  function handleSelectType(ct: ContentType) {
    setSelectedType(ct);
    setStep("options");
    setPlan(null);
    setResult(null);
    setError("");
  }

  async function handlePreviewPlan() {
    if (!selectedType || !topic.trim()) return;
    setPlanLoading(true);
    setError("");
    setPlan(null);
    try {
      const res = await previewPlan({
        content_type: selectedType,
        topic: topic.trim(),
        options,
      });
      setPlan(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Plan preview failed");
    } finally {
      setPlanLoading(false);
    }
  }

  async function handleGenerate() {
    if (!selectedType || !topic.trim()) return;
    setGenerating(true);
    setError("");
    setResult(null);
    try {
      const res = await generateContent({
        content_type: selectedType,
        topic: topic.trim(),
        options,
      });
      setResult(res);
      setStep("result");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  function handleReset() {
    setStep("type");
    setSelectedType(null);
    setTopic("");
    setOptions({
      style: "professional",
      language: "ko",
      include_speaker_notes: true,
    });
    setPlan(null);
    setResult(null);
    setError("");
  }

  const needsDuration =
    selectedType === "lecture" ||
    selectedType === "workshop" ||
    selectedType === "audio";
  const needsNumItems = selectedType === "card_news" || selectedType === "quiz";

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-2 text-sm">
        {(["type", "options", "result"] as Step[]).map((s, i) => {
          const labels = ["1. Type", "2. Options", "3. Result"];
          const isActive = s === step;
          const isDone =
            (s === "type" && step !== "type") ||
            (s === "options" && step === "result");
          return (
            <div key={s} className="flex items-center gap-2">
              {i > 0 && (
                <span className="text-gray-300 dark:text-gray-600">/</span>
              )}
              <button
                onClick={() => {
                  if (isDone || isActive) setStep(s);
                }}
                disabled={!isDone && !isActive}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                    : isDone
                      ? "text-blue-500 hover:underline cursor-pointer"
                      : "text-gray-400 cursor-default"
                }`}
              >
                {labels[i]}
              </button>
            </div>
          );
        })}
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Step 1: Type selection */}
      {step === "type" && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            Content Type
          </h3>
          {typesLoading ? (
            <p className="text-gray-500">Loading...</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {types.map((t) => (
                <TypeCard
                  key={t.type}
                  info={t}
                  selected={selectedType === t.type}
                  onClick={() => handleSelectType(t.type)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Step 2: Options + plan preview */}
      {step === "options" && selectedType && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: form */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Options
              <span className="text-sm font-normal text-gray-400 ml-2">
                {types.find((t) => t.type === selectedType)?.label}
              </span>
            </h3>

            {/* Topic */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Topic *
              </label>
              <input
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="e.g. SUPEX 추구의 변천사"
                maxLength={200}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-400 mt-1">{topic.length}/200</p>
            </div>

            {/* Duration */}
            {needsDuration && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Duration (min)
                </label>
                <input
                  type="number"
                  min={5}
                  max={120}
                  value={
                    options.duration_min ?? (selectedType === "audio" ? 5 : 30)
                  }
                  onChange={(e) =>
                    setOptions({
                      ...options,
                      duration_min: Number(e.target.value),
                    })
                  }
                  className="w-24 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                />
              </div>
            )}

            {/* Num items */}
            {needsNumItems && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {selectedType === "quiz" ? "Questions" : "Cards"}
                </label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={
                    options.num_items ?? (selectedType === "quiz" ? 10 : 5)
                  }
                  onChange={(e) =>
                    setOptions({
                      ...options,
                      num_items: Number(e.target.value),
                    })
                  }
                  className="w-24 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
                />
              </div>
            )}

            {/* Style */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Style
              </label>
              <select
                value={options.style ?? "professional"}
                onChange={(e) =>
                  setOptions({ ...options, style: e.target.value })
                }
                className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
              >
                {STYLE_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Edition filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Edition Filter (optional)
              </label>
              <input
                type="text"
                value={options.edition_filter ?? ""}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    edition_filter: e.target.value || null,
                  })
                }
                placeholder="e.g. 2020-14차"
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
              />
            </div>

            {/* Speaker notes toggle (lecture only) */}
            {selectedType === "lecture" && (
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={options.include_speaker_notes ?? true}
                  onChange={(e) =>
                    setOptions({
                      ...options,
                      include_speaker_notes: e.target.checked,
                    })
                  }
                  className="rounded"
                />
                Include speaker notes
              </label>
            )}

            {/* Buttons */}
            <div className="flex gap-2 pt-2">
              <button
                onClick={handlePreviewPlan}
                disabled={!topic.trim() || planLoading}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-blue-500 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {planLoading ? "Loading..." : "Preview Plan"}
              </button>
              <button
                onClick={handleGenerate}
                disabled={!topic.trim() || generating}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {generating ? "Generating..." : "Generate"}
              </button>
            </div>
          </div>

          {/* Right: plan preview */}
          <div>
            {plan && (
              <div>
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Plan Preview
                </h4>
                <PlanPreview plan={plan} />
              </div>
            )}
            {!plan && !planLoading && (
              <div className="flex items-center justify-center h-48 bg-gray-50 dark:bg-gray-800 rounded-lg text-sm text-gray-400">
                Click &quot;Preview Plan&quot; to see the outline
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step 3: Result */}
      {step === "result" && result && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            Result
          </h3>
          <ResultView result={result} />
          <div className="mt-4">
            <button
              onClick={handleReset}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              New Content
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

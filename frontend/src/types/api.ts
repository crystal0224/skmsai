/**
 * SKMS RAG API 타입 정의.
 *
 * server/models.py의 Pydantic 모델과 1:1 대응.
 */

// ---------------------------------------------------------------------------
// Common
// ---------------------------------------------------------------------------

export type OutputType =
  | "summary"
  | "card"
  | "quiz"
  | "comparison_table"
  | "slide";

export type SearchMode = "hybrid" | "vector" | "bm25";

// ---------------------------------------------------------------------------
// Search API
// ---------------------------------------------------------------------------

export interface SearchRequest {
  query: string;
  mode?: SearchMode;
  top_k?: number;
  edition_filter?: string | null;
  type_filter?: string[] | null;
}

export interface SearchHit {
  quote_id: string;
  text: string;
  score: number;
  edition_id: string;
  year: number;
  quote_type: string;
  section_path: string[];
  source: string;
}

export interface SearchResponse {
  query: string;
  mode: string;
  hits: SearchHit[];
  total: number;
}

// ---------------------------------------------------------------------------
// Generate API
// ---------------------------------------------------------------------------

export interface GenerateRequest {
  query: string;
  output_type?: OutputType | null;
  edition_filter?: string | null;
  top_k?: number;
}

export interface GenerateResponse {
  query: string;
  intent: string;
  answer: string;
  prompt_name: string;
  validation_passed: boolean | null;
  citations: string[];
  search_hits_count: number;
}

// ---------------------------------------------------------------------------
// V2 API
// ---------------------------------------------------------------------------

export interface EvidenceCheck {
  coverage_score: number;
  cited_quote_ids: string[];
  valid_quote_ids: string[];
  invalid_quote_ids: string[];
  hallucination_flags: string[];
  passed: boolean;
}

export interface GenerateV2Request {
  query: string;
  output_type?: OutputType | null;
  edition_filter?: string | null;
  top_k?: number;
  include_evidence_check?: boolean;
  include_rendered?: boolean;
}

export interface GenerateV2Response extends GenerateResponse {
  evidence_check?: EvidenceCheck | null;
  rendered?: string | null;
  render_success?: boolean | null;
}

// ---------------------------------------------------------------------------
// TOC API
// ---------------------------------------------------------------------------

export interface TOCNode {
  level: string;
  title: string;
  line: number;
  children: TOCNode[];
}

export interface TOCResponse {
  edition_id: string;
  year: number;
  label: string;
  sections: TOCNode[];
  node_count: number;
}

export interface EditionInfo {
  edition_id: string;
  year: number;
  label: string;
  start_line: number;
  end_line: number;
  section_count: number;
}

export interface EditionsListResponse {
  editions: EditionInfo[];
  total: number;
}

// ---------------------------------------------------------------------------
// Health API
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  version: string;
  components: Record<string, boolean>;
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export interface ErrorResponse {
  error: string;
  detail?: string | null;
}

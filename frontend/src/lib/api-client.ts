/**
 * SKMS RAG API 클라이언트.
 *
 * FastAPI 백엔드와 통신하는 fetch 래퍼.
 */

import type {
  SearchRequest,
  SearchResponse,
  GenerateV2Request,
  GenerateV2Response,
  EditionsListResponse,
  TOCResponse,
  HealthResponse,
  ErrorResponse,
} from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`API Error ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as ErrorResponse;
      detail = body.detail ?? body.error;
    } catch {
      // ignore parse error
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function healthCheck(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export async function search(req: SearchRequest): Promise<SearchResponse> {
  return request<SearchResponse>("/search", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function generate(
  req: GenerateV2Request,
): Promise<GenerateV2Response> {
  return request<GenerateV2Response>("/v2/generate", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getEditions(): Promise<EditionsListResponse> {
  return request<EditionsListResponse>("/editions");
}

export async function getTOC(editionId: string): Promise<TOCResponse> {
  return request<TOCResponse>(`/toc/${encodeURIComponent(editionId)}`);
}

export { ApiError };

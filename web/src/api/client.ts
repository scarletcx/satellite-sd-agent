/** 后端接口客户端（docs/07；接口变更先改文档与 specs/openapi.yaml，再同步此处）。 */

const BASE = "/api/v1";
const TOKEN_KEY = "satellite_token";

export function getToken(): string {
  return (
    localStorage.getItem(TOKEN_KEY) ||
    (import.meta.env.VITE_APP_TOKEN as string | undefined) ||
    "dev-token-change-me"
  );
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;

  constructor(status: number, payload: any) {
    super(payload?.error?.message || `HTTP ${status}`);
    this.status = status;
    this.code = payload?.error?.code || "UNKNOWN";
    this.details = payload?.error?.details || {};
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
      ...(init.headers || {}),
    },
  });
  if (!response.ok) {
    let payload: any = null;
    try {
      payload = await response.json();
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new ApiError(response.status, payload);
  }
  return (await response.json()) as T;
}

async function download(path: string, filename: string): Promise<void> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!response.ok) {
    let payload: any = null;
    try {
      payload = await response.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, payload);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------- 类型

export type MissionStatus =
  | "queued" | "running" | "awaiting_gate" | "succeeded" | "failed" | "canceled";

export interface StepInfo {
  code: string;
  name: string;
  status: string;
  duration_ms: number | null;
}

export interface PendingGate {
  gate_id: string;
  type: string;
  param_id: string | null;
  message: string;
}

export interface MissionDetail {
  task_id: string;
  goal: string;
  status: MissionStatus;
  current_step: string | null;
  provider_id: string | null;
  provider_model: string | null;
  steps: StepInfo[];
  cost_estimate_cny: number;
  document: { ready: boolean; version: number | null; url: string | null };
  pending_gates: PendingGate[];
  last_error: { code: string; message: string } | null;
  corpus_version: string;
  created_at: string;
  updated_at: string;
}

export interface ParameterSummary {
  id: string;
  name: string;
  unit: string;
  value: number;
  status: string;
  source_type: string;
  margin: number | null;
  validation_status: string | null;
  updated_at: string | null;
}

export interface CheckReport {
  status: string;
  placeholders_left: number;
  numbers_checked: number;
  numbers_traceable: number;
  citations: number;
  citation_issues: number;
  issues: { type: string; detail: string }[];
}

export interface KbDocument {
  doc_id: string;
  title: string;
  module: string;
  doc_type: string;
  is_synthetic: boolean;
  license: string;
  chunks: number;
  fetched_at: string | null;
}

export interface ProviderSetting {
  id: string;
  label: string;
  protocol: "openai" | "anthropic";
  base_url: string;
  model: string;
  has_key: boolean;
  key_masked: string;
  json_mode: boolean;
  enabled: boolean;
  keyless: boolean;
  timeout_s: number;
  price_in: number;
  price_out: number;
}

export interface LlmSettings {
  mode: string;
  primary: string;
  fallback_order: string[];
  configured: Record<string, string>;
  providers: ProviderSetting[];
}

// ---------------------------------------------------------------- 接口

export const api = {
  createMission: (body: { goal: string; constraints?: Record<string, unknown>; provider_id?: string }) =>
    request<{ task_id: string; status: string; created_at: string }>("/missions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getMission: (id: string) => request<MissionDetail>(`/missions/${id}`),

  cancelMission: (id: string) =>
    request<{ task_id: string; status: string }>(`/missions/${id}/cancel`, { method: "POST" }),

  revalidate: (id: string) =>
    request<any>(`/missions/${id}/revalidate`, {
      method: "POST",
      body: JSON.stringify({ scope: "all" }),
    }),

  listParameters: (id: string, filters: Record<string, string> = {}) => {
    const query = new URLSearchParams({ ...filters, page_size: "100" }).toString();
    return request<{ items: ParameterSummary[]; total: number }>(
      `/missions/${id}/parameters?${query}`,
    );
  },

  reviewParameter: (
    id: string,
    paramId: string,
    body: { action: "accept" | "reject"; reviewer: string; comment?: string; edited_value?: number },
  ) =>
    request<any>(`/missions/${id}/parameters/${encodeURIComponent(paramId)}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getCheckReport: (id: string) => request<CheckReport>(`/missions/${id}/check-report`),

  documentPreview: (id: string, version?: number) =>
    request<{ task_id: string; version: number; html: string; warnings: string[] }>(
      `/missions/${id}/document/preview${version ? `?version=${version}` : ""}`,
    ),

  downloadDocument: (id: string) => download(`/missions/${id}/document`, `${id}-design.docx`),
  downloadTrace: (id: string) => download(`/missions/${id}/trace?format=jsonl`, `${id}-trace.jsonl`),
  downloadCheckReport: (id: string) =>
    download(`/missions/${id}/check-report`, `${id}-check-report.json`),

  kbStats: () => request<any>("/kb/stats"),
  kbDocuments: (filters: Record<string, string> = {}) => {
    const query = new URLSearchParams({ ...filters, page_size: "50" }).toString();
    return request<{ items: KbDocument[]; total: number }>(`/kb/documents?${query}`);
  },
  kbSearch: (body: { query: string; top_k?: number }) =>
    request<{ results: any[]; took_ms: number; no_evidence: boolean }>("/kb/search", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  kbDelete: (docId: string) =>
    request<any>(`/kb/documents/${docId}?confirm=true`, { method: "DELETE" }),

  kbIngest: async (file: File, meta: Record<string, string>) => {
    const form = new FormData();
    form.append("file", file);
    Object.entries(meta).forEach(([key, value]) => form.append(key, value));
    const response = await fetch(`${BASE}/kb/ingest`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
      body: form,
    });
    if (!response.ok) {
      let payload: any = null;
      try {
        payload = await response.json();
      } catch {
        /* ignore */
      }
      throw new ApiError(response.status, payload);
    }
    return response.json();
  },

  // ------------------------------------------------------------ 供应商设置（ADR-0006）

  settingsLlm: () => request<LlmSettings>("/settings/llm"),

  settingsLlmPut: (providers: Record<string, unknown>[]) =>
    request<LlmSettings>("/settings/llm", { method: "PUT", body: JSON.stringify({ providers }) }),

  settingsLlmReset: () => request<LlmSettings>("/settings/llm", { method: "DELETE" }),

  settingsProbe: (body: {
    protocol: string; base_url: string; api_key?: string; model?: string; id?: string;
  }) => request<any>("/settings/llm/probe", { method: "POST", body: JSON.stringify(body) }),

  settingsTest: (id: string) =>
    request<any>("/settings/llm/test", { method: "POST", body: JSON.stringify({ id }) }),
};

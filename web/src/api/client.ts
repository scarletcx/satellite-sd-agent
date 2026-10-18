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
  title: string;
  goal: string;
  status: MissionStatus;
  current_step: string | null;
  provider_id: string | null;
  provider_model: string | null;
  steps: StepInfo[];
  cost_estimate_cny: number;
  document: { ready: boolean; version: number | null; versions: number[]; url: string | null };
  pending_gates: PendingGate[];
  pending_confirmations: {
    draft_inputs: number;
    open_assumptions: number;
    needs_review: number;
    rejected: number;
  };
  last_error: { code: string; message: string } | null;
  corpus_version: string;
  created_at: string;
  updated_at: string;
}

export interface AssumptionItem {
  id: string;
  content: string;
  basis: string;
  related_params: string[];
  status: string;
  registered_by: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
}

export interface MissionSummary {
  task_id: string;
  title: string;
  goal: string;
  status: MissionStatus;
  current_step: string | null;
  cost_estimate_cny: number;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionItem {
  id: string;
  title: string;
  summary: string;
  pinned: boolean;
  provider_id: string | null;
  model: string | null;
  reasoning_effort: "low" | "medium" | "high" | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message: string;
}

export interface ChatContext {
  window: number;
  used_tokens: number;
  percent: number;
  summary_chars: number;
  compacted_until: number;
  pending_messages: number;
  total_messages: number;
  auto_compact: boolean;
  threshold_pct: number;
  keep_recent: number;
}

export interface ChatSettings {
  auto_compact: boolean;
  threshold_pct: number;
  default_window: number;
  keep_recent: number;
  summary_max_chars: number;
}

export interface ChatCitation {
  id?: string;
  title?: string;
  source_url?: string;
  snippet?: string;
  score?: number;
  page?: number | null;
  is_synthetic?: boolean;
}

export interface ChatMessageItem {
  id: number;
  role: "user" | "assistant" | "system" | string;
  content: string;
  meta: {
    citations?: ChatCitation[];
    used_citations?: string[];
    action?: string;
    index_mode?: string;
  };
  created_at: string;
}

export interface ChatDocumentItem {
  id: string;
  doc_id: string;
  filename: string;
  chunks: number;
  scope: "session" | "global" | string;
  kind: "document" | "image" | string;
  created_at: string;
}

export interface ChatSessionDetail extends ChatSessionItem {
  documents: ChatDocumentItem[];
  context?: ChatContext;
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
  context_window: number;
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

export const api = {createMission: (body: {
    goal: string;
    constraints?: Record<string, unknown>;
    provider_id?: string;
    title?: string;
  }) =>
    request<{ task_id: string; status: string; created_at: string }>("/missions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getMission: (id: string) => request<MissionDetail>(`/missions/${id}`),

  renameMission: (id: string, title: string) =>
    request<{ task_id: string; title: string }>(`/missions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  listMissions: (params: { status?: string; page?: number; page_size?: number } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
    });
    const suffix = query.toString();
    return request<{ items: MissionSummary[]; total: number; page: number; page_size: number }>(
      `/missions${suffix ? `?${suffix}` : ""}`,
    );
  },

  deleteMission: (id: string) =>
    request<{ task_id: string; deleted: boolean; removed: Record<string, number> }>(
      `/missions/${id}?confirm=true`, { method: "DELETE" },
    ),

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
    body: {
      action: "accept" | "reject";
      reviewer: string;
      comment?: string;
      edited_value?: number;
      edited_payload?: Record<string, unknown>;
    },
  ) =>
    request<any>(`/missions/${id}/parameters/${encodeURIComponent(paramId)}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getParameter: (missionId: string, paramId: string) =>
    request<ParameterSummary & { payload?: Record<string, unknown> | null }>(
      `/missions/${missionId}/parameters/${encodeURIComponent(paramId)}`,
    ),

  acceptAllReviews: (missionId: string, body: { reviewer?: string; comment?: string } = {}) =>
    request<{
      mission_id: string;
      accepted_parameters: number;
      accepted_assumptions: number;
      remaining_confirmations: number;
      revalidation: { queued: boolean };
    }>(`/missions/${missionId}/reviews/accept-all`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getCheckReport: (id: string) => request<CheckReport>(`/missions/${id}/check-report`),

  assumptions: (id: string, status?: string) =>
    request<{ items: AssumptionItem[]; total: number }>(
      `/missions/${id}/assumptions${status ? `?status=${status}` : ""}`),

  reviewAssumption: (
    id: string,
    assumptionId: string,
    body: { action: "accept" | "reject"; reviewer: string; comment?: string },
  ) =>
    request<any>(`/missions/${id}/assumptions/${assumptionId}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  documentPreview: (id: string, version?: number) =>
    request<{ task_id: string; version: number; html: string; warnings: string[] }>(
      `/missions/${id}/document/preview${version ? `?version=${version}` : ""}`,
    ),

  downloadDocument: (id: string, version?: number | null) =>
    download(`/missions/${id}/document${version ? `?version=${version}` : ""}`,
      `${id}-design${version ? `-v${version}` : ""}.docx`),
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

  // ------------------------------------------------------------ 个人 agent 会话

  chatSessions: () =>
    request<{ items: ChatSessionItem[]; total: number }>("/chat/sessions"),

  chatCreateSession: (title?: string) =>
    request<ChatSessionItem>("/chat/sessions", {
      method: "POST",
      body: JSON.stringify(title ? { title } : {}),
    }),

  chatSession: (sessionId: string) =>
    request<ChatSessionDetail>(`/chat/sessions/${sessionId}`),

  chatRenameSession: (sessionId: string, title: string) =>
    request<ChatSessionItem>(`/chat/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  updateChatSession: (sessionId: string, payload: Partial<Pick<ChatSessionItem,
    "title" | "pinned" | "provider_id" | "model" | "reasoning_effort">>) =>
    request<ChatSessionItem>(`/chat/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  chatContext: (sessionId: string) =>
    request<ChatContext>(`/chat/sessions/${sessionId}/context`),

  chatSettings: () => request<ChatSettings>("/settings/chat"),

  chatSettingsPut: (body: Partial<ChatSettings>) =>
    request<ChatSettings>("/settings/chat", { method: "PUT", body: JSON.stringify(body) }),

  chatDeleteSession: (sessionId: string) =>
    request<any>(`/chat/sessions/${sessionId}`, { method: "DELETE" }),

  chatMessages: (sessionId: string) =>
    request<{ items: ChatMessageItem[]; total: number }>(`/chat/sessions/${sessionId}/messages`),

  chatSend: (sessionId: string, content: string) =>
    request<{
      user: ChatMessageItem;
      assistant: ChatMessageItem;
      session: ChatSessionDetail;
      context: ChatContext;
    }>(
      `/chat/sessions/${sessionId}/messages`,
      { method: "POST", body: JSON.stringify({ content }) },
    ),

  chatUpload: async (sessionId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`${BASE}/chat/sessions/${sessionId}/documents`, {
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
    return (await response.json()) as ChatDocumentItem;
  },

  chatDeleteDocument: (sessionId: string, documentId: string) =>
    request<any>(`/chat/sessions/${sessionId}/documents/${documentId}`, { method: "DELETE" }),

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

// ---------------------------------------------------------------- 聊天流式

export function openChatStream(
  sessionId: string,
  content: string,
  token: string,
  handlers: {
    onUser?: (message: ChatMessageItem) => void;
    onDelta: (text: string) => void;
    onDone: (payload: { assistant: ChatMessageItem; session: ChatSessionDetail; context: ChatContext }) => void;
    onError?: (message: string) => void;
  },
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(`${BASE}/chat/sessions/${sessionId}/messages/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          let event = "message";
          let data = "";
          for (const line of chunk.split("\n")) {
            if (line.startsWith("event: ")) event = line.slice(7).trim();
            else if (line.startsWith("data: ")) data = line.slice(6);
          }
          if (!data) continue;
          let payload: any;
          try {
            payload = JSON.parse(data);
          } catch {
            continue;
          }
          if (event === "user") handlers.onUser?.(payload as ChatMessageItem);
          else if (event === "delta") handlers.onDelta(String(payload.text ?? ""));
          else if (event === "done") handlers.onDone(payload);
          else if (event === "error") handlers.onError?.(String(payload.message ?? "流式输出失败"));
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) handlers.onError?.(String(error));
    }
  })();

  return () => controller.abort();
}

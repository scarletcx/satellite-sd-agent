/** SSE 流封装（fetch + ReadableStream：EventSource 不支持自定义 Header）。
 *
 * 断线自动重连：携带 Last-Event-ID，后端补发历史事件；前端按事件 id 去重（不丢不重）。
 */

export interface SseHandlers {
  onEvent: (event: string, data: any, id: number | null) => void;
  onError?: () => void;
}

const MAX_BACKOFF_MS = 5000;

export function openMissionStream(
  taskId: string,
  token: string,
  handlers: SseHandlers,
): () => void {
  let closed = false;
  let lastEventId = 0;
  const seen = new Set<number>();

  const parseChunk = (chunk: string) => {
    let event = "message";
    let data = "";
    let id: number | null = null;
    for (const line of chunk.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7).trim();
      else if (line.startsWith("data: ")) data = line.slice(6);
      else if (line.startsWith("id: ")) {
        const parsed = Number(line.slice(4));
        id = Number.isFinite(parsed) ? parsed : null;
      }
    }
    if (!data) return;
    if (id !== null) {
      if (id > 0 && seen.has(id)) return;       // 去重：重连补发的历史事件
      if (id > 0) seen.add(id);
      if (id > lastEventId) lastEventId = id;
    }
    try {
      handlers.onEvent(event, JSON.parse(data), id);
    } catch {
      /* 忽略无法解析的事件 */
    }
  };

  const connect = async () => {
    let backoff = 500;
    while (!closed) {
      const controller = new AbortController();
      try {
        const response = await fetch(`/api/v1/missions/${taskId}/events`, {
          headers: {
            Authorization: `Bearer ${token}`,
            ...(lastEventId > 0 ? { "Last-Event-ID": String(lastEventId) } : {}),
          },
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error(`sse ${response.status}`);

        backoff = 500;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!closed) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split("\n\n");
          buffer = chunks.pop() || "";
          chunks.forEach(parseChunk);
        }
      } catch {
        if (closed) return;
      }
      if (closed) return;
      handlers.onError?.();
      await new Promise((resolve) => setTimeout(resolve, backoff));
      backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
    }
  };

  void connect();

  return () => {
    closed = true;
  };
}

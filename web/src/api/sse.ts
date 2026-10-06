/** SSE 流封装（fetch + ReadableStream：EventSource 不支持自定义 Header）。 */

export interface SseHandlers {
  onEvent: (event: string, data: any, id: number | null) => void;
  onError?: () => void;
}

export function openMissionStream(
  taskId: string,
  token: string,
  handlers: SseHandlers,
): () => void {
  const controller = new AbortController();
  let closed = false;

  (async () => {
    try {
      const response = await fetch(`/api/v1/missions/${taskId}/events`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        handlers.onError?.();
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!closed) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
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
          if (!data) continue;
          try {
            handlers.onEvent(event, JSON.parse(data), id);
          } catch {
            /* 忽略无法解析的事件 */
          }
        }
      }
    } catch {
      if (!closed) handlers.onError?.();
    }
  })();

  return () => {
    closed = true;
    controller.abort();
  };
}

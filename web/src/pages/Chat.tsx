import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button, Card, Dropdown, Empty, Input, Modal, Select, Space, Spin, Tag, Typography, message,
} from "antd";
import type { MenuProps } from "antd";

import {
  ApiError, api, getToken, openChatStream,
  type ChatContext, type ChatDocumentItem, type ChatMessageItem, type ChatSessionItem,
  type ProviderSetting,
} from "../api/client";

const { Text, Title } = Typography;
const { TextArea } = Input;

const SLASH_COMMANDS = [
  { command: "compact", hint: "压缩上下文" },
  { command: "context", hint: "查看上下文用量" },
  { command: "model", hint: "切换会话模型" },
  { command: "effort", hint: "设置推理强度" },
  { command: "missions", hint: "查看任务" },
  { command: "mission", hint: "查看任务状态" },
  { command: "kb", hint: "知识库操作" },
  { command: "remember", hint: "写入长期记忆" },
  { command: "memory", hint: "查看长期记忆" },
  { command: "help", hint: "命令帮助" },
];

function formatTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

void formatTime;

export default function Chat() {
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [documents, setDocuments] = useState<ChatDocumentItem[]>([]);
  const [context, setContext] = useState<ChatContext | null>(null);
  const [providers, setProviders] = useState<ProviderSetting[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
  }, []);

  const loadProviders = useCallback(async () => {
    try {
      const data = await api.settingsLlm();
      setProviders(data.providers.filter((item) => item.enabled));
    } catch {
      /* 设置读取失败不影响聊天 */
    }
  }, []);

  const loadSessions = useCallback(async () => {
    const data = await api.chatSessions();
    setSessions(data.items);
    return data.items;
  }, []);

  const openSession = useCallback(async (sessionId: string) => {
    setLoading(true);
    try {
      const detail = await api.chatSession(sessionId);
      setActiveId(sessionId);
      setDocuments(detail.documents);
      setContext(detail.context ?? null);
      const history = await api.chatMessages(sessionId);
      setMessages(history.items);
      scrollToBottom();
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setLoading(false);
    }
  }, [scrollToBottom]);

  const createSession = useCallback(async () => {
    try {
      const created = await api.chatCreateSession();
      await loadSessions();
      await openSession(created.id);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    }
  }, [loadSessions, openSession]);

  useEffect(() => {
    void loadProviders();
    (async () => {
      try {
        const items = await loadSessions();
        if (items.length > 0) await openSession(items[0].id);
        else await createSession();
      } catch (error) {
        if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (streamingText) scrollToBottom();
  }, [streamingText, scrollToBottom]);

  const activeSession = useMemo(
    () => sessions.find((item) => item.id === activeId) ?? null,
    [sessions, activeId],
  );

  const patchSession = async (payload: Parameters<typeof api.updateChatSession>[1]) => {
    if (!activeId) return;
    try {
      await api.updateChatSession(activeId, payload);
      await loadSessions();
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    }
  };

  const fallbackSend = async (content: string, localUserId: number) => {
    if (!activeId) return;
    try {
      const result = await api.chatSend(activeId, content);
      setMessages((previous) => [
        ...previous.filter((item) => item.id !== localUserId),
        result.user, result.assistant,
      ]);
      setContext(result.context);
      setDocuments(result.session.documents);
      await loadSessions();
      scrollToBottom();
    } catch (error) {
      setMessages((previous) => previous.filter((item) => item.id !== localUserId));
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    }
  };

  const send = async () => {
    const content = input.trim();
    if (!content || !activeId || sending) return;
    setSending(true);
    setInput("");
    setStreamingText("");
    const localUserId = -Date.now();
    setMessages((previous) => [...previous, {
      id: localUserId, role: "user", content, meta: {}, created_at: "",
    }]);
    let finished = false;
    openChatStream(activeId, content, getToken(), {
      onDelta: (text) => setStreamingText((previous) => previous + text),
      onDone: (payload) => {
        finished = true;
        setStreamingText("");
        setSending(false);
        setMessages((previous) => [...previous, payload.assistant]);
        setContext(payload.context);
        setDocuments(payload.session.documents);
        void loadSessions();
        scrollToBottom();
      },
      onError: (text) => {
        if (finished) return;
        setStreamingText("");
        setSending(false);
        message.warning(`流式输出不可用，改用普通请求：${text}`);
        void fallbackSend(content, localUserId);
      },
    });
  };

  const handleUpload = async (file: File) => {
    if (!activeId) return;
    setUploading(true);
    try {
      const document = await api.chatUpload(activeId, file);
      message.success(`已上传：${document.filename}`);
      const detail = await api.chatSession(activeId);
      setDocuments(detail.documents);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setUploading(false);
    }
  };

  const removeDocument = async (documentId: string) => {
    if (!activeId) return;
    try {
      await api.chatDeleteDocument(activeId, documentId);
      setDocuments((previous) => previous.filter((item) => item.id !== documentId));
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    }
  };

  const removeSession = (sessionId: string) => {
    Modal.confirm({
      title: "删除会话及附件？",
      content: "会话消息与附件对应的知识库文档会一并删除（长期记忆不受影响）。",
      okText: "删除", okButtonProps: { danger: true }, cancelText: "取消",
      onOk: async () => {
        try {
          await api.chatDeleteSession(sessionId);
          const items = await loadSessions();
          if (sessionId === activeId) {
            if (items.length > 0) await openSession(items[0].id);
            else await createSession();
          }
        } catch (error) {
          if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
        }
      },
    });
  };

  const sessionMenu = (item: ChatSessionItem): MenuProps => ({
    items: [
      { key: "rename", label: "重命名会话" },
      { key: "pin", label: item.pinned ? "取消置顶" : "置顶会话" },
      { type: "divider" },
      { key: "delete", label: "删除会话", danger: true },
    ],
    onClick: ({ key, domEvent }) => {
      domEvent.stopPropagation();
      if (key === "rename") {
        setRenameTarget(item.id);
        setRenameValue(item.title);
        setRenameOpen(true);
      }
      if (key === "pin") void api.updateChatSession(item.id, { pinned: !item.pinned })
        .then(() => loadSessions())
        .catch(() => message.error("置顶失败"));
      if (key === "delete") removeSession(item.id);
    },
  });

  const addMenu: MenuProps = {
    items: [
      { key: "file", label: "添加文件（pdf/docx/txt/md/csv）" },
      { key: "image", label: "添加图片（png/jpg/webp）" },
    ],
    onClick: ({ key }) => {
      if (key === "file") fileInputRef.current?.click();
      if (key === "image") imageInputRef.current?.click();
    },
  };

  const slashOpen = input.startsWith("/") && !input.includes(" ");

  const contextLabel = context
    ? `上下文 ${context.percent}% · ${(context.used_tokens / 1000).toFixed(1)}k/${(context.window / 1000).toFixed(0)}k`
      + `${context.auto_compact ? ` · 自动压缩 ${context.threshold_pct}%` : " · 自动压缩关"}`
    : "";

  return (
    <div className="chat-shell">
      <Card
        size="small" title="会话" className="chat-sidebar"
        extra={<Button size="small" type="primary" onClick={createSession}>新建会话</Button>}
        styles={{ body: { padding: 0, maxHeight: "100%", overflowY: "auto" } }}
      >
        {sessions.map((item) => (
          <div
            key={item.id}
            className={`chat-session-row${item.id === activeId ? " chat-session-active" : ""}`}
            onClick={() => openSession(item.id)}
          >
            <Text ellipsis style={{ flex: 1, fontWeight: item.pinned ? 600 : 400 }}>
              {item.pinned ? "• " : ""}{item.title}
            </Text>
            <Dropdown menu={sessionMenu(item)} trigger={["click"]}>
              <Button size="small" type="text" onClick={(event) => event.stopPropagation()}>⋯</Button>
            </Dropdown>
          </div>
        ))}
        {sessions.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有会话" />}
      </Card>

      <Card size="small" className="chat-main"
        styles={{ body: { display: "flex", flexDirection: "column", height: "100%" } }}>
        <div className="chat-header">
          <Space wrap style={{ justifyContent: "space-between", width: "100%" }}>
            <Title level={5} style={{ margin: 0 }}>{activeSession?.title || "个人卫星设计助手"}</Title>
            <Text type="secondary" style={{ fontSize: 12 }}>{contextLabel}</Text>
          </Space>
          <Space wrap size={6} style={{ marginTop: 4 }}>
            <Select
              size="small" style={{ width: 180 }} placeholder="模型（供应商）"
              value={activeSession?.provider_id ?? ""} allowClear
              onChange={(value) => patchSession({ provider_id: value || null })}
              options={providers.map((item) => ({
                value: item.id, label: `${item.label || item.id} · ${item.model}`,
              }))}
            />
            <Input
              size="small" style={{ width: 180 }} placeholder="模型名（可覆盖）"
              defaultValue={activeSession?.model ?? ""}
              key={`model-${activeSession?.id ?? ""}-${activeSession?.model ?? ""}`}
              onBlur={(event) => {
                const next = event.target.value.trim();
                if (next !== (activeSession?.model ?? "")) void patchSession({ model: next || null });
              }}
            />
            <Select
              size="small" style={{ width: 120 }} value={activeSession?.reasoning_effort ?? "off"}
              onChange={(value) => patchSession({
                reasoning_effort: value === "off" ? null : value as "low" | "medium" | "high",
              })}
              options={[
                { value: "off", label: "推理：默认" },
                { value: "low", label: "推理：低" },
                { value: "medium", label: "推理：中" },
                { value: "high", label: "推理：高" },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              会话记忆存本地 SQLite；/compact 可手动压缩
            </Text>
          </Space>
        </div>

        <div className="chat-messages">
          {loading ? (
            <div className="chat-loading"><Spin /></div>
          ) : messages.length === 0 && !streamingText ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="开始对话：描述任务、上传资料，或输入 / 查看命令" />
          ) : (
            <>
              {messages.map((item) => (
                <div key={item.id} className={`chat-msg ${item.role}`}>
                  <span className="chat-role">{item.role === "user" ? "你" : "助手"}</span>
                  <div className="chat-bubble">{item.content}</div>
                  {item.meta?.citations && item.meta.citations.length > 0 && (
                    <div className="chat-citations">
                      {item.meta.citations.map((citation, index) => (
                        <Tag key={`${citation.id ?? index}`} color="blue">
                          {citation.id ? `${citation.id} ` : ""}{citation.title ?? "引用"}
                          {typeof citation.score === "number" ? ` · ${citation.score}` : ""}
                        </Tag>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {streamingText && (
                <div className="chat-msg assistant">
                  <span className="chat-role">助手</span>
                  <div className="chat-bubble">{streamingText}<span className="chat-cursor">▍</span></div>
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="chat-composer">
          <Dropdown menu={addMenu} trigger={["click"]}>
            <Button size="large" type="text" disabled={!activeId}>＋</Button>
          </Dropdown>
          <input
            ref={fileInputRef} type="file" hidden
            accept=".pdf,.docx,.txt,.md,.csv"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleUpload(file);
              event.target.value = "";
            }}
          />
          <input
            ref={imageInputRef} type="file" hidden accept=".png,.jpg,.jpeg,.webp,.gif"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleUpload(file);
              event.target.value = "";
            }}
          />
          <div style={{ flex: 1, position: "relative" }}>
            {slashOpen && (
              <div className="chat-slash-menu">
                {SLASH_COMMANDS
                  .filter((item) => item.command.startsWith(input.slice(1).toLowerCase()))
                  .map((item) => (
                    <div key={item.command} className="chat-slash-item"
                      onClick={() => setInput(`/${item.command} `)}>
                      <Text code>/{item.command}</Text>
                      <Text type="secondary" style={{ marginLeft: 8 }}>{item.hint}</Text>
                    </div>
                  ))}
              </div>
            )}
            {documents.length > 0 && (
              <div className="chat-docs">
                {documents.map((document) => (
                  <Tag key={document.id} closable color={document.scope === "global" ? "green" : "default"}
                    onClose={(event) => { event.preventDefault(); void removeDocument(document.id); }}>
                    {document.kind === "image" ? "图片" : "文档"}：{document.filename}
                    {document.scope === "global" ? "（知识库）" : "（本会话）"}
                  </Tag>
                ))}
              </div>
            )}
            <TextArea
              value={input} onChange={(event) => setInput(event.target.value)}
              placeholder={activeId ? "输入问题；Enter 发送，Shift+Enter 换行；/ 查看命令" : "正在准备会话…"}
              autoSize={{ minRows: 2, maxRows: 8 }} disabled={!activeId || sending}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
          </div>
          <Button type="primary" size="large" loading={sending}
            disabled={!activeId || !input.trim()} onClick={send}>发送</Button>
        </div>
        <Text type="secondary" style={{ marginTop: 6, fontSize: 12 }}>
          {uploading ? "正在处理附件…" : "记忆与附件只存本机 SQLite；模型调用会发送必要的提示词片段。"}
        </Text>
      </Card>

      <Modal
        open={renameOpen} title="重命名会话" okText="保存" cancelText="取消"
        onCancel={() => setRenameOpen(false)}
        onOk={async () => {
          if (!renameTarget || !renameValue.trim()) return;
          await api.chatRenameSession(renameTarget, renameValue.trim());
          setRenameOpen(false);
          await loadSessions();
        }}
      >
        <Input value={renameValue} onChange={(event) => setRenameValue(event.target.value)} />
      </Modal>
    </div>
  );
}

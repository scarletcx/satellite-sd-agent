import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button, Card, Empty, Input, List, Popconfirm, Space, Spin, Tag, Typography, Upload, message,
} from "antd";
import type { UploadFile } from "antd";

import {
  ApiError, api,
  type ChatDocumentItem, type ChatMessageItem, type ChatSessionItem,
} from "../api/client";

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

function roleLabel(role: string): string {
  return role === "user" ? "你" : role === "assistant" ? "助手" : role;
}

export default function Chat() {
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [documents, setDocuments] = useState<ChatDocumentItem[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
  };

  const loadSessions = useCallback(async (preferId?: string) => {
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
      const history = await api.chatMessages(sessionId);
      setMessages(history.items);
      scrollToBottom();
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

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
    (async () => {
      try {
        const items = await loadSessions();
        if (items.length > 0) {
          await openSession(items[0].id);
        } else {
          await createSession();
        }
      } catch (error) {
        if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const send = async () => {
    const content = input.trim();
    if (!content || !activeId || sending) return;
    setSending(true);
    setInput("");
    try {
      const result = await api.chatSend(activeId, content);
      setMessages((previous) => [...previous, result.user, result.assistant]);
      setDocuments(result.session.documents);
      await loadSessions();
      scrollToBottom();
    } catch (error) {
      setInput(content);
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setSending(false);
    }
  };

  const handleUpload = async (file: UploadFile | File) => {
    const raw = (file as UploadFile).originFileObj ?? (file as File);
    if (!activeId || !raw) return;
    setUploading(true);
    try {
      const document = await api.chatUpload(activeId, raw as File);
      message.success(`已上传：${document.filename}（${document.chunks} 个片段）`);
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

  const removeSession = async (sessionId: string) => {
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
  };

  const activeSession = sessions.find((item) => item.id === activeId);

  return (
    <div className="chat-shell">
      <Card
        size="small" title="会话" className="chat-sidebar"
        extra={<Button size="small" type="primary" onClick={createSession}>新建会话</Button>}
        styles={{ body: { padding: 0, maxHeight: "100%", overflowY: "auto" } }}
      >
        <List
          size="small" dataSource={sessions}
          locale={{ emptyText: "还没有会话" }}
          renderItem={(item) => (
            <List.Item
              className={item.id === activeId ? "chat-session-active" : ""}
              style={{ cursor: "pointer", padding: "8px 12px" }}
              onClick={() => openSession(item.id)}
              actions={[
                <Popconfirm
                  key="delete" title="删除会话及其附件？" okText="删除" cancelText="取消"
                  onConfirm={(event) => {
                    event?.stopPropagation();
                    removeSession(item.id);
                  }}
                >
                  <Button size="small" type="text" danger
                    onClick={(event) => event.stopPropagation()}>删</Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={<Text ellipsis style={{ maxWidth: 150 }}>{item.title}</Text>}
                description={
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {item.message_count} 条 · {item.last_message || "暂无消息"}
                  </Text>
                }
              />
            </List.Item>
          )}
        />
      </Card>

      <Card size="small" className="chat-main" styles={{ body: { display: "flex", flexDirection: "column", height: "100%" } }}>
        <div className="chat-header">
          <Title level={5} style={{ margin: 0 }}>{activeSession?.title || "个人卫星设计助手"}</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            本地会话（SQLite 记忆） · 附件写入本地知识库（sqlite-vec 检索）
          </Text>
        </div>

        <div className="chat-messages">
          {loading ? (
            <div className="chat-loading"><Spin /></div>
          ) : messages.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="开始新的对话：描述任务、上传资料，或直接提问"
            />
          ) : (
            messages.map((item) => (
              <div key={item.id} className={`chat-msg ${item.role}`}>
                <span className="chat-role">{roleLabel(item.role)}</span>
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
            ))
          )}
          <div ref={bottomRef} />
        </div>

        <div className="chat-composer">
          <div style={{ flex: 1 }}>
            {documents.length > 0 && (
              <div className="chat-docs">
                {documents.map((document) => (
                  <Tag
                    key={document.id} closable
                    onClose={(event) => { event.preventDefault(); removeDocument(document.id); }}
                  >
                    {document.filename}（{document.chunks}）
                  </Tag>
                ))}
              </div>
            )}
            <TextArea
              value={input} onChange={(event) => setInput(event.target.value)}
              placeholder={activeId ? "输入问题，Enter 发送，Shift+Enter 换行…" : "正在准备会话…"}
              autoSize={{ minRows: 2, maxRows: 6 }}
              disabled={!activeId || sending}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  send();
                }
              }}
            />
          </div>
          <Space direction="vertical">
            <Upload
              accept=".pdf,.docx,.txt,.md,.csv" showUploadList={false} multiple={false}
              beforeUpload={(file) => {
                handleUpload(file);
                return false;
              }}
            >
              <Button loading={uploading} disabled={!activeId}>上传文档</Button>
            </Upload>
            <Button type="primary" loading={sending} disabled={!activeId || !input.trim()} onClick={send}>
              发送
            </Button>
          </Space>
        </div>
        <Paragraph type="secondary" style={{ margin: "8px 0 0", fontSize: 12 }}>
          记忆仅保存在本地 SQLite；上传文件仅进入本机知识库，不会上传到云端（模型调用除外）。
        </Paragraph>
      </Card>
    </div>
  );
}

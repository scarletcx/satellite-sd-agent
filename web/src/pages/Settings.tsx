import { useCallback, useEffect, useState } from "react";
import {
  Alert, Button, Card, Input, InputNumber, Popconfirm, Select, Space, Switch,
  Tag, Typography, message,
} from "antd";

import { api, type ChatSettings, type LlmSettings, type ProviderSetting } from "../api/client";

const { Text, Paragraph } = Typography;

const ID_PATTERN = /^[a-z][a-z0-9_-]{1,31}$/;

type EditableProvider = ProviderSetting & { api_key_input?: string };

export default function Settings() {
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [providers, setProviders] = useState<EditableProvider[]>([]);
  const [modelsById, setModelsById] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string>("");
  const [chatSettings, setChatSettings] = useState<ChatSettings | null>(null);
  const [savingChat, setSavingChat] = useState(false);
  const [modelContexts, setModelContexts] = useState<Record<string, Record<string, number | null>>>({});
  const [maxWindowByProvider, setMaxWindowByProvider] = useState<Record<string, number | null>>({});

  const apply = (data: LlmSettings) => {
    setSettings(data);
    setProviders(data.providers.map((item) => ({ ...item })));
  };

  const load = useCallback(async () => {
    try {
      apply(await api.settingsLlm());
      setChatSettings(await api.chatSettings());
    } catch (error) {
      message.error(String((error as Error)?.message ?? error));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const update = (index: number, patch: Partial<EditableProvider>) =>
    setProviders((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));

  const move = (index: number, delta: number) => {
    setProviders((prev) => {
      const target = index + delta;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const addProvider = () =>
    setProviders((prev) => [...prev, {
      id: "", label: "新供应商", protocol: "openai", base_url: "", model: "",
      has_key: false, key_masked: "", json_mode: true, enabled: true, keyless: false,
      timeout_s: 120, context_window: 128000, price_in: 0, price_out: 0,
    }]);

  const probe = async (row: EditableProvider, index: number) => {
    if (!row.base_url) {
      message.warning("请先填写 Base URL");
      return;
    }
    const key = `provider-${index}`;
    setBusy(`probe:${key}`);
    try {
      const result = await api.settingsProbe({
        protocol: row.protocol, base_url: row.base_url, model: row.model || undefined,
        api_key: row.api_key_input || undefined, id: row.id || undefined,
      });
      if (result.ok) {
        if (Array.isArray(result.models) && result.models.length) {
          setModelsById((prev) => ({ ...prev, [key]: result.models }));
          setModelContexts((prev) => ({ ...prev, [key]: result.model_contexts ?? {} }));
          setMaxWindowByProvider((prev) => ({ ...prev, [key]: result.max_context_window ?? null }));
          message.success(`连接成功（${result.latency_ms} ms，发现 ${result.models.length} 个模型，可从下拉选择）`);
        } else {
          message.success(`连接成功（${result.latency_ms} ms）`);
        }
      } else {
        message.error(`连接失败：${result.error ?? "未知错误"}`);
      }
    } catch (error) {
      message.error(String((error as Error)?.message ?? error));
    } finally {
      setBusy("");
    }
  };

  const test = async (id: string) => {
    if (!id) {
      message.warning("请先保存后再测试");
      return;
    }
    setBusy(`test:${id}`);
    try {
      const result = await api.settingsTest(id);
      if (result.ok) message.success(`调用成功（${result.latency_ms} ms）：${result.echo ?? ""}`);
      else message.error(`调用失败：${result.error ?? "未知错误"}`);
    } catch (error) {
      message.error(String((error as Error)?.message ?? error));
    } finally {
      setBusy("");
    }
  };

  const save = async () => {
    const ids = providers.map((item) => item.id);
    for (const item of providers) {
      if (!ID_PATTERN.test(item.id)) {
        message.warning(`供应商 id 不合法：${item.id || "(空)"}（小写字母开头，可含数字/_/-）`);
        return;
      }
      if (!item.base_url.trim() || !item.model.trim()) {
        message.warning(`供应商 ${item.id} 需要填写 Base URL 与 Model`);
        return;
      }
    }
    if (new Set(ids).size !== ids.length) {
      message.warning("供应商 id 不能重复");
      return;
    }
    setSaving(true);
    try {
      const payload = providers.map((item) => ({
        id: item.id, label: item.label, protocol: item.protocol,
        base_url: item.base_url, model: item.model,
        json_mode: item.json_mode, enabled: item.enabled, keyless: item.keyless,
        timeout_s: item.timeout_s, context_window: item.context_window,
        price_in: item.price_in, price_out: item.price_out,
        ...(item.api_key_input !== undefined ? { api_key: item.api_key_input } : {}),
      }));
      apply(await api.settingsLlmPut(payload));
      message.success("已保存并生效（密钥已写入本地存储）");
    } catch (error) {
      message.error(String((error as Error)?.message ?? error));
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    try {
      apply(await api.settingsLlmReset());
      message.success("已恢复默认配置（环境变量 / config/llm.json）");
    } catch (error) {
      message.error(String((error as Error)?.message ?? error));
    }
  };

  const saveChatSettings = async () => {
    if (!chatSettings) return;
    setSavingChat(true);
    try {
      setChatSettings(await api.chatSettingsPut(chatSettings));
      message.success("对话上下文设置已保存");
    } catch (error) {
      message.error(String((error as Error)?.message ?? error));
    } finally {
      setSavingChat(false);
    }
  };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Card
        size="small"
        title="对话与上下文"
        extra={<Button size="small" type="primary" loading={savingChat}
          disabled={!chatSettings} onClick={saveChatSettings}>保存</Button>}
      >
        <Alert
          type="info" showIcon style={{ marginBottom: 12 }}
          message="消息全量保存在本地 SQLite；达到阈值后自动把较早消息折叠为摘要（也可在聊天框输入 /compact 手动压缩）。"
        />
        {chatSettings && (
          <Space wrap size="large">
            <Space size="small">
              <span>自动压缩</span>
              <Switch checked={chatSettings.auto_compact}
                onChange={(checked) => setChatSettings({ ...chatSettings, auto_compact: checked })} />
            </Space>
            <Space size="small">
              <span>阈值(%)</span>
              <InputNumber min={20} max={95} value={chatSettings.threshold_pct}
                onChange={(value) => setChatSettings({ ...chatSettings, threshold_pct: Number(value ?? 80) })} />
            </Space>
            <Space size="small">
              <span>保留最近消息</span>
              <InputNumber min={2} max={30} value={chatSettings.keep_recent}
                onChange={(value) => setChatSettings({ ...chatSettings, keep_recent: Number(value ?? 6) })} />
            </Space>
            <Space size="small">
              <span>上下文窗口(tokens)</span>
              <InputNumber min={8000} max={2000000} step={1000} style={{ width: 130 }}
                value={chatSettings.default_window}
                onChange={(value) => setChatSettings({ ...chatSettings, default_window: Number(value ?? 262144) })} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                默认 256k；可参考下方供应商模型的最大窗口后在此调整
              </Text>
            </Space>
            <Space size="small">
              <span>摘要上限(字)</span>
              <InputNumber min={300} max={6000} step={100} style={{ width: 110 }}
                value={chatSettings.summary_max_chars}
                onChange={(value) => setChatSettings({ ...chatSettings, summary_max_chars: Number(value ?? 1500) })} />
            </Space>
          </Space>
        )}
      </Card>

      <Card
        size="small"
        title={
          <Space>
            <span>大模型供应商设置</span>
            {settings && (
              <Tag color={settings.mode === "stub" ? "default" : "green"}>
                {settings.mode === "stub" ? "桩模式（当前无可用供应商）" : "真实模式"}
              </Tag>
            )}
            {settings && <Text type="secondary">主用：{settings.primary} ｜ 降级链：{settings.fallback_order.join(" → ") || "（空）"}</Text>}
          </Space>
        }
        extra={
          <Space>
            <Button onClick={load}>刷新</Button>
            <Popconfirm title="恢复为默认注册表？" description="将清除运行时配置（环境变量 / config/llm.json 仍然生效）" onConfirm={reset}>
              <Button>恢复默认</Button>
            </Popconfirm>
            <Button type="primary" loading={saving} onClick={save}>保存</Button>
          </Space>
        }
      >
        <Alert
          type="info" showIcon
          message="支持任意 OpenAI 兼容第三方（聚合网关 / 国产平台兼容模式 / 自建 vLLM 等）与 Anthropic 协议；列表顺序即降级顺序。"
          description="「拉取模型」会调用 /models 列出可用模型；「测试」对已保存的供应商做一次最小真实调用。密钥仅保存在本机（本地数据库，明文，演示级）。"
        />
      </Card>

      {providers.map((row, index) => {
        const key = `provider-${index}`;
        const configured = settings?.configured[row.id] === "configured";
        return (
          <Card
            key={key}
            size="small"
            title={
              <Space wrap>
                <Switch
                  size="small" checked={row.enabled}
                  onChange={(checked) => update(index, { enabled: checked })}
                />
                <Input
                  size="small" style={{ width: 150 }} placeholder="id（小写）"
                  value={row.id} onChange={(event) => update(index, { id: event.target.value })}
                />
                <Input
                  size="small" style={{ width: 200 }} placeholder="显示名称"
                  value={row.label} onChange={(event) => update(index, { label: event.target.value })}
                />
                <Tag color={configured ? "green" : "default"}>
                  {configured ? "已配置" : "未配置"}
                </Tag>
                {settings?.configured[row.id] !== "configured" && row.has_key && <Tag color="blue">有密钥</Tag>}
              </Space>
            }
            extra={
              <Space>
                <Button
                  size="small" loading={busy === `probe:${key}`}
                  onClick={() => probe(row, index)}
                >
                  拉取模型
                </Button>
                <Button
                  size="small" loading={busy === `test:${row.id}`}
                  onClick={() => test(row.id)} disabled={!row.id}
                >
                  测试
                </Button>
                <Button size="small" onClick={() => move(index, -1)} disabled={index === 0}>↑</Button>
                <Button size="small" onClick={() => move(index, 1)} disabled={index === providers.length - 1}>↓</Button>
                <Popconfirm title={`删除 ${row.id || "该条目"}？`} onConfirm={() => setProviders((prev) => prev.filter((_, i) => i !== index))}>
                  <Button size="small" danger>删除</Button>
                </Popconfirm>
              </Space>
            }
          >
            <Space direction="vertical" style={{ width: "100%" }} size="small">
              <Space wrap>
                <span>协议</span>
                <Select
                  style={{ width: 130 }} size="small"
                  value={row.protocol}
                  onChange={(value) => update(index, { protocol: value as EditableProvider["protocol"] })}
                  options={[{ value: "openai", label: "OpenAI 兼容" }, { value: "anthropic", label: "Anthropic" }]}
                />
                <span>Base URL</span>
                <Input
                  style={{ width: 320 }} size="small" placeholder="https://example.com/v1"
                  value={row.base_url} onChange={(event) => update(index, { base_url: event.target.value })}
                />
                <span>Model</span>
                <Select
                  style={{ width: 280 }} size="small" showSearch allowClear
                  value={row.model || undefined}
                  placeholder="先点「拉取模型」，再从下拉选择"
                  options={(modelsById[key] ?? (row.model ? [row.model] : []))
                    .map((model) => ({
                      value: model,
                      label: `${model}${modelContexts[key]?.[model]
                        ? `（${(modelContexts[key][model]! / 1000).toFixed(0)}k）` : ""}`,
                    }))}
                  onChange={(value) => update(index, { model: value ?? "" })}
                />
                {row.model && modelContexts[key]?.[row.model] && (
                  <Tag color="blue">
                    最大上下文 {(modelContexts[key][row.model]! / 1000).toFixed(0)}k
                  </Tag>
                )}
                {!modelContexts[key]?.[row.model] && maxWindowByProvider[key] && (
                  <Tag>参考最大窗口 {(maxWindowByProvider[key]! / 1000).toFixed(0)}k</Tag>
                )}
              </Space>
              <Space wrap>
                <span>API Key</span>
                <Input.Password
                  style={{ width: 320 }} size="small"
                  placeholder={row.key_masked || "未配置"}
                  value={row.api_key_input ?? ""}
                  onChange={(event) => update(index, { api_key_input: event.target.value })}
                />
                <span>json_mode</span>
                <Switch size="small" checked={row.json_mode} onChange={(checked) => update(index, { json_mode: checked })} />
                <span>无需密钥</span>
                <Switch size="small" checked={row.keyless} onChange={(checked) => update(index, { keyless: checked })} />
                <span>超时(s)</span>
                <InputNumber size="small" style={{ width: 80 }} min={5} max={600} value={row.timeout_s}
                  onChange={(value) => update(index, { timeout_s: Number(value ?? 120) })} />
                {maxWindowByProvider[key] && chatSettings && (
                  <Button size="small" onClick={() => setChatSettings({
                    ...chatSettings, default_window: maxWindowByProvider[key]!,
                  })}>
                    用该模型最大窗口（{(maxWindowByProvider[key]! / 1000).toFixed(0)}k）填充上下文窗口
                  </Button>
                )}
                <span>价格/1K(¥)</span>
                <InputNumber size="small" style={{ width: 90 }} min={0} step={0.001} value={row.price_in}
                  onChange={(value) => update(index, { price_in: Number(value ?? 0) })} />
                <InputNumber size="small" style={{ width: 90 }} min={0} step={0.001} value={row.price_out}
                  onChange={(value) => update(index, { price_out: Number(value ?? 0) })} />
              </Space>
              <Paragraph type="secondary" style={{ margin: 0 }}>
                说明：json_mode 会发送 response_format=json_object（第三方不支持时请关闭）；价格用于成本估算。
              </Paragraph>
            </Space>
          </Card>
        );
      })}

      <Button type="dashed" onClick={addProvider}>+ 添加供应商</Button>
    </Space>
  );
}

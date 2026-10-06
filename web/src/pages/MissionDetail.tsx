import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Alert, Badge, Button, Card, Descriptions, Input, InputNumber, List, Modal, Popconfirm,
  Progress, Radio, Select, Space, Table, Tabs, Timeline, Typography, message,
} from "antd";
import type { ColumnsType } from "antd/es/table";

import {
  ApiError, api, getToken,
  type CheckReport, type MissionDetail as MissionDetailData, type ParameterSummary,
} from "../api/client";
import { openMissionStream } from "../api/sse";

const { Paragraph, Text } = Typography;

const MISSION_STATUS: Record<string, { color: string; text: string }> = {
  queued: { color: "default", text: "排队中" },
  running: { color: "processing", text: "执行中" },
  awaiting_gate: { color: "warning", text: "待人工门禁" },
  succeeded: { color: "success", text: "已完成" },
  failed: { color: "error", text: "失败" },
  canceled: { color: "default", text: "已取消" },
};

const PARAM_STATUS: Record<string, string> = {
  proposed: "default", needs_review: "blue", verified: "green", rejected: "red",
};

const VALIDATION_COLOR: Record<string, string> = { pass: "green", warn: "gold", block: "red" };

function formatNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  return String(Number(value.toFixed(3)));
}

const STEP_HINT: Record<string, string> = {
  S1: "正在理解任务书并结构化需求…",
  S2: "正在检索历史资料与先例（知识库）…",
  S3: "正在分解整星方案（构型 / 分系统 / 指标树）…",
  S4: "正在生成参数草案与假设台账（调用大模型）…",
  S5: "正在执行确定性计算（轨道 / 质量 / 功耗 / 太阳翼 / 数据量 / 链路）…",
  S6: "正在执行一致性校验（V1~V7：闭合 / 余量 / 引用完整性 / 敏感性…）…",
  S7: "正在生成冲突消解建议…",
  S8: "正在撰写文档叙述（数字占位符化，引用白名单）…",
  S9: "正在渲染 Word 文档并执行自检…",
};

function summarizeEvent(event: string, data: any): string {
  if (event === "validation") return `${data.rule} ${data.status} ${data.param_id ?? ""} ${data.message ?? ""}`;
  if (event === "gate") return `${data.type} ${data.param_id ?? ""} ${data.message ?? ""}`;
  if (event === "step") return `${data.step} ${data.name} ${data.status}`;
  if (event === "done") return `任务完成（成本 ¥${data?.cost_estimate_cny ?? "-"})`;
  if (event === "error") return `${data.code} ${data.message}`;
  return JSON.stringify(data).slice(0, 120);
}

export default function MissionDetail() {
  const { taskId = "" } = useParams();
  const [detail, setDetail] = useState<MissionDetailData | null>(null);
  const [params, setParams] = useState<ParameterSummary[]>([]);
  const [report, setReport] = useState<CheckReport | null>(null);
  const [events, setEvents] = useState<{ ts: string; event: string; text: string }[]>([]);
  const [filters, setFilters] = useState<{ status?: string; module?: string }>({});
  const [activeTab, setActiveTab] = useState("trace");
  const [reviewer, setReviewer] = useState(localStorage.getItem("satellite_reviewer") || "engineer@example.com");

  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewParam, setReviewParam] = useState<ParameterSummary | null>(null);
  const [reviewAction, setReviewAction] = useState<"accept" | "reject">("accept");
  const [reviewComment, setReviewComment] = useState("");
  const [reviewValue, setReviewValue] = useState<number | null>(null);
  const [reviewing, setReviewing] = useState(false);

  const [previewHtml, setPreviewHtml] = useState<string>("");
  const [previewNote, setPreviewNote] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const query: Record<string, string> = {};
      if (filters.status) query.status = filters.status;
      if (filters.module) query.module = filters.module;
      const [mission, paramList] = await Promise.all([
        api.getMission(taskId),
        api.listParameters(taskId, query),
      ]);
      setDetail(mission);
      setParams(paramList.items);
      try {
        setReport(await api.getCheckReport(taskId));
      } catch {
        setReport(null);
      }
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    }
  }, [taskId, filters]);

  useEffect(() => {
    load();
  }, [load]);

  // 活动任务轮询兜底（SSE 为主，轮询防丢事件）
  useEffect(() => {
    const status = detail?.status;
    if (status !== "queued" && status !== "running" && status !== "awaiting_gate") return;
    const timer = setInterval(load, 2500);
    return () => clearInterval(timer);
  }, [detail?.status, load]);

  // SSE 实时事件
  useEffect(() => {
    if (!taskId) return;
    const close = openMissionStream(taskId, getToken(), {
      onEvent: (event, data) => {
        if (event === "ping" || event === "snapshot") {
          if (event === "snapshot") load();
          return;
        }
        setEvents((previous) => [
          { ts: new Date().toLocaleTimeString(), event, text: summarizeEvent(event, data) },
          ...previous,
        ].slice(0, 50));
        load();
      },
      onError: () => undefined,
    });
    return close;
  }, [taskId, load]);

  // Word 在线预览（docx → HTML，后端 mammoth 转换）
  const loadPreview = useCallback(async () => {
    setPreviewLoading(true);
    try {
      const result = await api.documentPreview(taskId);
      setPreviewHtml(result.html);
      setPreviewNote(result.warnings?.length ? `转换提示：${result.warnings.join("；")}` : "");
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setPreviewLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    if (detail?.document.ready && !previewHtml) loadPreview();
  }, [detail?.document.ready, previewHtml, loadPreview]);

  const modules = useMemo(
    () => Array.from(new Set(params.map((item) => item.id.split(".")[0]))).sort(),
    [params],
  );
  const needsReview = params.filter((item) => ["needs_review", "proposed"].includes(item.status)).length;
  const blocking = params.filter((item) => ["needs_review", "rejected"].includes(item.status));

  const openReview = (param: ParameterSummary) => {
    setReviewParam(param);
    setReviewAction("accept");
    setReviewComment("");
    setReviewValue(null);
    setReviewOpen(true);
  };

  const submitReview = async () => {
    if (!reviewParam) return;
    if (reviewAction === "reject" && !reviewComment.trim()) {
      message.warning("驳回必须填写评审意见");
      return;
    }
    setReviewing(true);
    try {
      localStorage.setItem("satellite_reviewer", reviewer);
      await api.reviewParameter(taskId, reviewParam.id, {
        action: reviewAction,
        reviewer,
        comment: reviewComment || undefined,
        edited_value: reviewValue ?? undefined,
      });
      message.success("评审已提交，已触发重新校验");
      setReviewOpen(false);
      load();
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setReviewing(false);
    }
  };

  const doDownload = async (fn: () => Promise<void>, label: string) => {
    try {
      await fn();
      message.success(`${label}下载已开始`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        const blocks = (error.details as any)?.blocking ?? [];
        Modal.error({
          title: "暂不可导出",
          content: (
            <div>
              <p>{error.message}</p>
              {blocks.map((item: any, index: number) => (
                <p key={index} className="mono">{item.rule} {item.param_id} {item.message}</p>
              ))}
            </div>
          ),
        });
      } else if (error instanceof ApiError) {
        message.error(`[${error.code}] ${error.message}`);
      } else {
        message.error(String(error));
      }
    }
  };

  if (!detail) return <Card loading />;

  const statusInfo = MISSION_STATUS[detail.status] ?? { color: "default", text: detail.status };

  const doneSteps = detail.steps.filter((step) => step.status === "done").length;
  const progressPercent = detail.status === "succeeded" ? 100
    : Math.round((doneSteps / Math.max(detail.steps.length, 1)) * 100);
  const runningStep = detail.steps.find((step) => step.status === "running")
    ?? detail.steps.find((step) => step.status === "pending");
  const progressHint =
    detail.status === "queued" ? "排队中：等待调度启动…"
      : detail.status === "awaiting_gate" ? "等待人工门禁：请到「参数评审」页处理待确认项，处理完成后任务自动恢复…"
        : detail.status === "running" && runningStep
          ? `正在进行 ${runningStep.code} ${runningStep.name}：${STEP_HINT[runningStep.code] ?? "处理中…"}`
          : detail.status === "succeeded" ? "全部步骤完成，文档已生成"
            : detail.status === "failed" ? `执行失败：${detail.last_error?.message ?? "未知错误"}`
              : detail.status === "canceled" ? "任务已取消" : "";
  const progressStatus = detail.status === "failed" ? "exception"
    : detail.status === "succeeded" ? "success" : "active";

  const parameterColumns: ColumnsType<ParameterSummary> = [
    { title: "参数", dataIndex: "id", width: 190, render: (value: string) => <Text code>{value}</Text> },
    { title: "名称", dataIndex: "name", width: 170 },
    { title: "数值", width: 130, render: (_, row) => `${formatNumber(row.value)} ${row.unit}` },
    {
      title: "状态", dataIndex: "status", width: 110,
      render: (value: string) => <Badge status="processing" color={PARAM_STATUS[value] ?? "default"} text={value} />,
    },
    { title: "来源", dataIndex: "source_type", width: 100 },
    {
      title: "校验", dataIndex: "validation_status", width: 90,
      render: (value: string | null) => (value ? <Badge color={VALIDATION_COLOR[value]} text={value} /> : "-"),
    },
    {
      title: "操作", width: 90,
      render: (_, row) => (
        <Button
          size="small" type="link"
          disabled={!["needs_review", "proposed"].includes(row.status)}
          onClick={() => openReview(row)}
        >
          评审
        </Button>
      ),
    },
  ];

  const traceTab = (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Card size="small" title="执行进度">
        <Progress
          percent={progressPercent} status={progressStatus}
          strokeColor={detail.status === "awaiting_gate" ? "#faad14" : undefined}
        />
        <Paragraph style={{ marginBottom: 0, marginTop: 8 }}>{progressHint}</Paragraph>
      </Card>
      <Descriptions
        size="small" bordered column={3}
        items={[
          { key: "id", label: "任务", children: <Text code>{detail.task_id}</Text> },
          { key: "status", label: "状态", children: <Badge color={statusInfo.color} text={statusInfo.text} /> },
          { key: "step", label: "当前步骤", children: detail.current_step ?? "-" },
          {
            key: "provider", label: "模型",
            children: detail.provider_id
              ? `${detail.provider_id}（${detail.provider_model ?? "-"}）`
              : "自动（设置页降级链）",
          },
          { key: "cost", label: "成本估算（¥）", children: detail.cost_estimate_cny },
          { key: "corpus", label: "语料版本", children: detail.corpus_version },
          { key: "updated", label: "更新时间", children: detail.updated_at?.slice(0, 19) },
        ]}
      />
      {detail.pending_gates.length > 0 && (
        <Alert
          type="warning" showIcon message={`${detail.pending_gates.length} 项待处理门禁`}
          description={detail.pending_gates.map((gate) => `${gate.type}：${gate.param_id ?? ""} ${gate.message}`).join("；")}
          action={<Button size="small" onClick={() => setActiveTab("params")}>去处理</Button>}
        />
      )}
      <Card size="small" title="步骤时间线">
        <Timeline
          items={detail.steps.map((step) => ({
            color: step.status === "done" ? "green" : step.status === "running" ? "blue"
              : step.status === "failed" ? "red" : "gray",
            children: (
              <span>
                <Text strong>{step.code}</Text> {step.name}
                {" "}<Text type="secondary">{step.status}{step.duration_ms != null ? ` · ${step.duration_ms} ms` : ""}</Text>
              </span>
            ),
          }))}
        />
      </Card>
      <Card size="small" title="实时事件（SSE）">
        <List
          size="small" dataSource={events}
          locale={{ emptyText: "等待事件…" }}
          renderItem={(item) => (
            <List.Item className="mono">
              {item.ts} [{item.event}] {item.text}
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );

  const paramsTab = (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Space wrap>
        <Select
          style={{ width: 180 }} placeholder="按状态过滤" allowClear
          value={filters.status}
          onChange={(value) => setFilters((previous) => ({ ...previous, status: value }))}
          options={["proposed", "needs_review", "verified", "rejected"].map((v) => ({ value: v, label: v }))}
        />
        <Select
          style={{ width: 160 }} placeholder="按分系统过滤" allowClear
          value={filters.module}
          onChange={(value) => setFilters((previous) => ({ ...previous, module: value }))}
          options={modules.map((v) => ({ value: v, label: v }))}
        />
        <Input
          style={{ width: 220 }} prefix="评审人" value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
        />
        <Button onClick={load}>刷新</Button>
        <Button type="primary" ghost onClick={async () => {
          await api.revalidate(taskId);
          message.success("已触发重新校验");
          load();
        }}>
          重新校验
        </Button>
      </Space>
      {blocking.length > 0 && (
        <Alert
          type="error" showIcon
          message={`${blocking.length} 个参数未通过评审（仅列表所示状态需处理）`}
          description={blocking.map((item) => `${item.id}：${item.status}`).join("；")}
        />
      )}
      <Table
        rowKey="id" size="small" columns={parameterColumns} dataSource={params}
        pagination={{ pageSize: 15 }} scroll={{ x: 900 }}
      />
    </Space>
  );

  const documentTab = (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      {report ? (
        <Descriptions
          size="small" bordered column={3}
          items={[
            { key: "status", label: "自检状态", children: <Badge color={VALIDATION_COLOR[report.status]} text={report.status} /> },
            { key: "placeholders", label: "占位符残留", children: report.placeholders_left },
            { key: "numbers", label: "数字可追溯", children: `${report.numbers_traceable}/${report.numbers_checked}` },
            { key: "citations", label: "引用数", children: report.citations },
            { key: "citation_issues", label: "引用问题", children: report.citation_issues },
            { key: "doc", label: "文档版本", children: detail.document.ready ? `v${detail.document.version}` : "未生成" },
          ]}
        />
      ) : (
        <Alert type="info" showIcon message="校验报告尚未生成（任务完成后自动产出）" />
      )}
      {report && report.issues.length > 0 && (
        <Alert
          type="warning" showIcon message={`${report.issues.length} 条自检问题`}
          description={report.issues.map((issue) => `${issue.type}: ${issue.detail}`).join("；")}
        />
      )}
      <Space>
        <Button
          type="primary" disabled={!detail.document.ready}
          onClick={() => doDownload(() => api.downloadDocument(taskId), "Word 文档")}
        >
          下载 Word {detail.document.ready ? `(v${detail.document.version})` : "（未就绪）"}
        </Button>
        <Button disabled={!report} onClick={() => doDownload(() => api.downloadCheckReport(taskId), "校验报告")}>
          下载校验报告
        </Button>
        <Button onClick={() => doDownload(() => api.downloadTrace(taskId), "trace")}>导出 trace</Button>
      </Space>
      {!detail.document.ready && blocking.length > 0 && (
        <Alert type="warning" showIcon message="存在未通过参数，导出被系统阻止（对应 A10 409）"
          description={blocking.map((item) => item.id).join("；")} />
      )}
      <Card
        size="small"
        title={`在线预览（Word → HTML）${detail.document.ready ? ` · v${detail.document.version}` : ""}`}
        extra={
          <Button size="small" loading={previewLoading} disabled={!detail.document.ready} onClick={loadPreview}>
            重新加载
          </Button>
        }
      >
        {previewHtml ? (
          /* 内容来自本系统生成的 docx（mammoth 转换），本地演示环境直接渲染 */
          <div className="doc-preview" dangerouslySetInnerHTML={{ __html: previewHtml }} />
        ) : (
          <Text type="secondary">
            {detail.document.ready ? (previewLoading ? "正在转换文档…" : "尚未加载预览") : "文档生成后可在此直接预览"}
          </Text>
        )}
        {previewNote && (
          <Alert style={{ marginTop: 8 }} type="info" showIcon message={previewNote} />
        )}
      </Card>
    </Space>
  );

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Card
        title={`任务 ${detail.task_id}`}
        extra={
          <Space>
            <Badge color={statusInfo.color} text={statusInfo.text} />
            {["queued", "running", "awaiting_gate"].includes(detail.status) && (
              <Popconfirm title="确认取消该任务？" onConfirm={async () => {
                await api.cancelMission(taskId); message.success("任务已取消"); load();
              }}>
                <Button danger size="small">取消任务</Button>
              </Popconfirm>
            )}
            <Button size="small" onClick={load}>刷新</Button>
          </Space>
        }
      >
        <Paragraph style={{ marginBottom: 0 }} strong>{detail.goal}</Paragraph>
        {detail.last_error && (
          <Alert
            style={{ marginTop: 12 }} type="error" showIcon
            message={`执行失败：${detail.last_error.code}`}
            description={detail.last_error.message}
          />
        )}
      </Card>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: "trace", label: "执行过程", children: traceTab },
          { key: "params", label: `参数评审${needsReview ? `（待处理 ${needsReview}）` : ""}`, children: paramsTab },
          { key: "document", label: "文档与校验", children: documentTab },
        ]}
      />

      <Modal
        open={reviewOpen} title={`评审参数：${reviewParam?.id ?? ""}`}
        onCancel={() => setReviewOpen(false)} onOk={submitReview} confirmLoading={reviewing}
        okText="提交评审"
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Text>当前值：{reviewParam ? `${formatNumber(reviewParam.value)} ${reviewParam.unit}` : "-"}（状态 {reviewParam?.status}）</Text>
          <Radio.Group
            value={reviewAction}
            onChange={(event) => setReviewAction(event.target.value)}
            options={[{ value: "accept", label: "接受（accept）" }, { value: "reject", label: "驳回（reject）" }]}
          />
          {reviewAction === "accept" && (
            <InputNumber
              style={{ width: "100%" }} placeholder="修正值（可选，填写后版本 +1）"
              value={reviewValue} onChange={(value) => setReviewValue(value)}
            />
          )}
          <Input.TextArea
            rows={3} value={reviewComment}
            onChange={(event) => setReviewComment(event.target.value)}
            placeholder={reviewAction === "reject" ? "评审意见（驳回必填）" : "评审意见（可选）"}
          />
        </Space>
      </Modal>
    </Space>
  );
}

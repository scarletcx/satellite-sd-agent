import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Button, Card, Input, Modal, Select, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";

import { ApiError, api, type MissionSummary } from "../api/client";

const { Paragraph, Text } = Typography;

const STATUS: Record<string, { color: string; text: string }> = {
  queued: { color: "default", text: "排队中" },
  running: { color: "processing", text: "执行中" },
  awaiting_gate: { color: "warning", text: "待人工门禁" },
  succeeded: { color: "success", text: "已完成" },
  failed: { color: "error", text: "失败" },
  canceled: { color: "default", text: "已取消" },
};

function formatTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

export default function MissionList() {
  const [items, setItems] = useState<MissionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameId, setRenameId] = useState<string>("");
  const [renameValue, setRenameValue] = useState("");
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listMissions({ status, page_size: 50 });
      setItems(data.items);
      setTotal(data.total);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const openRename = (item: MissionSummary) => {
    setRenameId(item.task_id);
    setRenameValue(item.title);
    setRenameOpen(true);
  };

  const submitRename = async () => {
    if (!renameId || !renameValue.trim()) return;
    try {
      await api.renameMission(renameId, renameValue.trim());
      setRenameOpen(false);
      message.success("任务名称已更新");
      await load();
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    }
  };

  const columns: ColumnsType<MissionSummary> = [
    {
      title: "任务号", dataIndex: "task_id", width: 150,
      render: (value: string) => <Link to={`/missions/${value}`}><Text code>{value}</Text></Link>,
    },
    { title: "名称", dataIndex: "title", width: 200, ellipsis: true },
    { title: "目标", dataIndex: "goal", ellipsis: true },
    {
      title: "状态", dataIndex: "status", width: 110,
      render: (value: string) => {
        const info = STATUS[value] ?? { color: "default", text: value };
        return <Badge color={info.color} text={info.text} />;
      },
    },
    { title: "当前步骤", dataIndex: "current_step", width: 100, render: (v) => v ?? "-" },
    {
      title: "成本(¥)", dataIndex: "cost_estimate_cny", width: 90,
      render: (value: number) => value?.toFixed(3) ?? "0.000",
    },
    {
      title: "更新时间", dataIndex: "updated_at", width: 170,
      render: (value: string) => formatTime(value),
    },
    {
      title: "操作", width: 160,
      render: (_, record) => (
        <Space size={0}>
          <Button size="small" type="link" onClick={() => navigate(`/missions/${record.task_id}`)}>查看</Button>
          <Button size="small" type="link" onClick={() => openRename(record)}>重命名</Button>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Card
        title="任务列表"
        extra={
          <Space>
            <Select
              allowClear placeholder="按状态过滤" style={{ width: 160 }}
              value={status} onChange={setStatus}
              options={Object.keys(STATUS).map((key) => ({ value: key, label: STATUS[key].text }))}
            />
            <Button onClick={load}>刷新</Button>
            <Button type="primary" onClick={() => navigate("/missions/new")}>新建设计任务</Button>
          </Space>
        }
      >
        <Paragraph type="secondary" style={{ marginTop: 0 }}>
          共 {total} 个任务；点击任务号进入执行详情（进度、参数评审、文档与校验）。
        </Paragraph>
        <Table
          rowKey="task_id" size="small" loading={loading}
          columns={columns} dataSource={items}
          pagination={{ pageSize: 15 }}
        />
      </Card>

      <Modal
        open={renameOpen} title="重命名任务" okText="保存" cancelText="取消"
        onCancel={() => setRenameOpen(false)} onOk={submitRename}
      >
        <Input value={renameValue} maxLength={120}
          onChange={(event) => setRenameValue(event.target.value)} />
      </Modal>

      <Tag color="blue">提示：处于「待人工门禁」的任务需要到任务详情页的「参数评审」完成确认后才会继续。</Tag>
    </Space>
  );
}

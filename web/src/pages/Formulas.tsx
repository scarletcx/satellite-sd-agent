import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert, Button, Card, Col, Collapse, Empty, Input, Row, Select, Space,
  Table, Tag, Typography, message,
} from "antd";
import type { ColumnsType } from "antd/es/table";

import { ApiError, api, type FormulaConstant, type FormulaItem } from "../api/client";

const { Paragraph, Text } = Typography;
const { TextArea } = Input;

const CATEGORY_LABEL: Record<string, string> = {
  orbit: "轨道", mass: "质量", power: "功耗", eps: "太阳翼",
  adcs: "姿控", data: "数据", link: "链路",
};

const TOOL_LABEL: Record<string, string> = {
  "calc.orbit": "C5 轨道", "calc.mass_budget": "C1 质量",
  "calc.power_budget": "C2 功耗", "calc.eps": "C6 太阳翼",
  "calc.adcs": "C7 姿控", "calc.data_budget": "C3 数据量",
  "calc.link_budget": "C4 链路",
};

export default function Formulas() {
  const [searchParams] = useSearchParams();
  const focusId = searchParams.get("focus") || "";
  const [items, setItems] = useState<FormulaItem[]>([]);
  const [constants, setConstants] = useState<FormulaConstant[]>([]);
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [selectedId, setSelectedId] = useState<string>("");
  const [detail, setDetail] = useState<FormulaItem | null>(null);
  const [expression, setExpression] = useState("");
  const [description, setDescription] = useState("");
  const [preview, setPreview] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const selectFormula = async (id: string, list?: FormulaItem[]) => {
    setSelectedId(id);
    setLoading(true);
    try {
      const data = await api.formulaGet(id);
      setDetail(data);
      setExpression(data.expression);
      setDescription(data.description);
      setPreview(null);
      if (list) setItems(list);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    Promise.all([api.formulaList({ category }), api.formulaConstants()])
      .then(([list, consts]) => {
        setItems(list.items);
        setConstants(consts.items);
        if (list.items.length) {
          const wanted = list.items.find((item) => item.id === focusId);
          const keep = wanted ?? list.items.find((item) => item.id === selectedId) ?? list.items[0];
          selectFormula(keep.id, list.items);
        } else {
          setDetail(null);
        }
      })
      .catch((error) => {
        if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  const filtered = useMemo(
    () => items.filter((item) => !category || item.category === category),
    [items, category],
  );

  const runPreview = async () => {
    if (!detail) return;
    try {
      const result = await api.formulaPreview(detail.id);
      setPreview(result.value);
      message.success(`试算结果：${result.value.toPrecision(6)} ${detail.unit}`);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    }
  };

  const save = async () => {
    if (!detail) return;
    setSaving(true);
    try {
      const updated = await api.formulaUpdate(detail.id, {
        expression: expression.trim(), description: description.trim(),
        updated_by: localStorage.getItem("satellite_reviewer") || "engineer",
      });
      setDetail(updated);
      setItems((prev) => prev.map((item) => item.id === updated.id ? updated : item));
      message.success(`已保存 ${updated.id}（v${updated.version}）；新任务计算将使用该公式`);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!detail) return;
    try {
      const updated = await api.formulaReset(detail.id,
        localStorage.getItem("satellite_reviewer") || "engineer");
      setDetail(updated);
      setExpression(updated.expression);
      setDescription(updated.description);
      setPreview(null);
      setItems((prev) => prev.map((item) => item.id === updated.id ? updated : item));
      message.success(`已恢复默认公式（v${updated.version}）`);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    }
  };

  const columns: ColumnsType<FormulaItem> = [
    {
      title: "公式", dataIndex: "name",
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{row.id}</Text>
        </Space>
      ),
    },
    {
      title: "工具", dataIndex: "tool", width: 120,
      render: (value: string) => TOOL_LABEL[value] ?? value,
    },
    {
      title: "版本", dataIndex: "version", width: 80,
      render: (value: number, row) => (
        <Space size={4}>
          <Text>v{value}</Text>
          {row.is_custom && <Tag color="orange">自定义</Tag>}
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Alert
        type="info" showIcon
        message="计算流程由确定性代码执行，公式只允许数字、变量、四则运算/幂和少量数学函数"
        description="修改公式只影响之后的新计算；已有任务需要重跑 S5（新建任务或重新校验前先重算）。所有修改带版本历史，计算记录里保留公式版本。"
      />

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card
            size="small" title={`公式清单（${filtered.length}）`}
            extra={
              <Select
                allowClear placeholder="按分系统过滤" style={{ width: 150 }}
                value={category} onChange={setCategory}
                options={Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }))}
              />
            }
          >
            <Table
              rowKey="id" size="small" loading={loading}
              columns={columns} dataSource={filtered}
              pagination={{ pageSize: 12 }}
              onRow={(row) => ({
                onClick: () => selectFormula(row.id),
                style: { cursor: "pointer", background: row.id === selectedId ? "#e6f4ff" : undefined },
              })}
            />
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          {!detail ? (
            <Card size="small"><Empty description="选择左侧公式进行查看/编辑" /></Card>
          ) : (
            <Card
              size="small"
              title={<Space>
                <span>{detail.name}</span>
                <Tag color={detail.is_custom ? "orange" : "default"}>
                  {detail.is_custom ? "自定义" : "默认"}
                </Tag>
                <Tag>v{detail.version}</Tag>
              </Space>}
              extra={<Text type="secondary">{detail.id}</Text>}
            >
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <div>
                  <Text type="secondary">公式表达式</Text>
                  <TextArea
                    rows={3} value={expression} spellCheck={false}
                    style={{ fontFamily: "monospace", marginTop: 4 }}
                    onChange={(event) => { setExpression(event.target.value); setPreview(null); }}
                  />
                  <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
                    支持 `+ - * / **`、`sqrt/log10/exp/abs/min/max/sin/cos/tan/radians/degrees/round`；
                    常量见下方。不要写 Python 代码或属性访问。
                  </Paragraph>
                </div>

                <div>
                  <Text type="secondary">说明</Text>
                  <Input
                    value={description} style={{ marginTop: 4 }}
                    onChange={(event) => setDescription(event.target.value)}
                  />
                </div>

                <Space>
                  <Text>单位：</Text><Text code>{detail.unit || "-"}</Text>
                  <Text type="secondary">示例输入：</Text>
                  <Text code>{JSON.stringify(detail.sample_context)}</Text>
                </Space>

                <Space wrap>
                  <Button onClick={runPreview}>试算</Button>
                  <Button type="primary" loading={saving} onClick={save}>保存</Button>
                  <Button danger onClick={reset}>恢复默认</Button>
                  {preview !== null && (
                    <Tag color="green">结果 {preview.toPrecision(8)} {detail.unit}</Tag>
                  )}
                </Space>

                <div>
                  <Text strong>变量</Text>
                  <Table
                    rowKey="symbol" size="small" pagination={false}
                    dataSource={detail.variables}
                    columns={[
                      { title: "符号", dataIndex: "symbol", width: 160, render: (v) => <Text code>{v}</Text> },
                      { title: "含义", dataIndex: "label" },
                      { title: "单位", dataIndex: "unit", width: 100, render: (v) => v || "-" },
                    ]}
                  />
                </div>

                <Collapse
                  size="small"
                  items={[
                    {
                      key: "constants",
                      label: `常量（${constants.length}）`,
                      children: (
                        <Table
                          rowKey="symbol" size="small" pagination={false}
                          dataSource={constants}
                          columns={[
                            { title: "符号", dataIndex: "symbol", width: 150, render: (v) => <Text code>{v}</Text> },
                            { title: "含义", dataIndex: "label" },
                            { title: "值", dataIndex: "value", width: 140, render: (v: number) => v.toPrecision(8) },
                            { title: "单位", dataIndex: "unit", width: 90, render: (v) => v || "-" },
                          ]}
                        />
                      ),
                    },
                    {
                      key: "history",
                      label: `版本历史（${detail.history?.length ?? 0}）`,
                      children: (
                        <Table
                          rowKey="version" size="small" pagination={false}
                          dataSource={detail.history ?? []}
                          columns={[
                            { title: "版本", dataIndex: "version", width: 70, render: (v) => `v${v}` },
                            { title: "表达式", dataIndex: "expression", render: (v) => <Text code>{v}</Text> },
                            { title: "修改人", dataIndex: "updated_by", width: 120 },
                            { title: "时间", dataIndex: "updated_at", width: 180 },
                          ]}
                        />
                      ),
                    },
                  ]}
                />
              </Space>
            </Card>
          )}
        </Col>
      </Row>
    </Space>
  );
}

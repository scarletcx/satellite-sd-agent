import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Typography, message } from "antd";

import { api, ApiError } from "../api/client";

const { Paragraph } = Typography;

const EXAMPLE = {
  goal: "设计一颗 500km SSO 光学遥感小卫星",
  orbit_type: "SSO",
  altitude_km: 500,
  lifetime_years: 3,
  payload: "多光谱相机，地面分辨率 5m，幅宽 60km",
  data_requirements: "每日成像 10 圈，单圈数据量尽量压缩",
  ttc_conditions: "S 频段测控，国内地面站",
  mass_limit_kg: 80,
};

export default function MissionCreate() {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [providers, setProviders] = useState<{ value: string; label: string }[]>([]);
  const [llmMode, setLlmMode] = useState<string>("");
  const navigate = useNavigate();

  useEffect(() => {
    api.settingsLlm()
      .then((data) => {
        setLlmMode(data.mode);
        setProviders(
          data.providers
            .filter((item) => item.enabled && data.configured[item.id] === "configured")
            .map((item) => ({ value: item.id, label: `${item.label || item.id} · ${item.model}` })),
        );
      })
      .catch(() => undefined);
  }, []);

  const submit = async (values: any) => {
    setSubmitting(true);
    try {
      const constraints: Record<string, unknown> = {};
      for (const key of ["orbit_type", "altitude_km", "lifetime_years", "payload",
                         "data_requirements", "ttc_conditions", "mass_limit_kg", "notes"]) {
        if (values[key] !== undefined && values[key] !== null && values[key] !== "") {
          constraints[key] = values[key];
        }
      }
      const result = await api.createMission({
        goal: values.goal,
        constraints,
        ...(values.provider_id ? { provider_id: values.provider_id } : {}),
      });
      message.success(`任务已创建：${result.task_id}`);
      navigate(`/missions/${result.task_id}`);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
      else message.error(String(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card title="新建设计任务" className="section-card">
      <Paragraph type="secondary">
        输入任务目标与约束，系统将执行「解析 → 检索 → 分解 → 参数 → 计算 → 校验 → 渲染」流程，
        产出可追溯的 Word 方案；未配置模型 Key 时自动使用桩模式。
      </Paragraph>
      <Form form={form} layout="vertical" onFinish={submit} initialValues={{ orbit_type: "SSO" }}>
        {llmMode === "stub" && (
          <Alert
            style={{ marginBottom: 12 }} type="info" showIcon
            message="当前为桩模式（无可用供应商）：先在「设置」页配置大模型后，任务将调用真实模型。"
          />
        )}
        <Form.Item name="provider_id" label="模型（供应商）" style={{ maxWidth: 420 }}>
          <Select
            allowClear placeholder="自动（按「设置」页的降级链）"
            options={providers}
          />
        </Form.Item>
        <Form.Item name="goal" label="任务目标" rules={[{ required: true, message: "请输入任务目标" }]}>
          <Input.TextArea rows={3} placeholder="例如：设计一颗 500km SSO 光学遥感小卫星" />
        </Form.Item>
        <Space size="large" wrap>
          <Form.Item name="orbit_type" label="轨道类型" style={{ width: 160 }}>
            <Select options={["SSO", "LEO", "GEO", "custom"].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item name="altitude_km" label="轨道高度 (km)" style={{ width: 160 }}>
            <InputNumber min={200} max={36000} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="lifetime_years" label="设计寿命 (年)" style={{ width: 160 }}>
            <InputNumber min={0.5} max={20} step={0.5} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="mass_limit_kg" label="质量上限 (kg)" style={{ width: 160 }}>
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
        </Space>
        <Form.Item name="payload" label="载荷参数">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item name="data_requirements" label="成像 / 通信需求">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item name="ttc_conditions" label="测控条件">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={submitting}>提交任务</Button>
          <Button onClick={() => form.setFieldsValue(EXAMPLE)}>填入示例任务书</Button>
          <Button type="link" onClick={() => form.resetFields()}>清空</Button>
        </Space>
      </Form>
    </Card>
  );
}

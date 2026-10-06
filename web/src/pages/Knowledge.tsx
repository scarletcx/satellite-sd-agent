import { useCallback, useEffect, useState } from "react";
import {
  Alert, Button, Card, Col, Descriptions, Input, List, Popconfirm, Row, Select, Space,
  Statistic, Table, Typography, Upload, message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { InboxOutlined } from "@ant-design/icons";

import { ApiError, api, type KbDocument } from "../api/client";

const { Text } = Typography;

const MODULES = ["system", "power", "ttc", "data", "adcs", "orbit", "payload", "risk", "other"];
const DOC_TYPES = ["standard", "manual", "report", "catalog", "lesson", "other"];

export default function Knowledge() {
  const [stats, setStats] = useState<any>(null);
  const [documents, setDocuments] = useState<KbDocument[]>([]);
  const [searchResults, setSearchResults] = useState<any[] | null>(null);
  const [searching, setSearching] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [module, setModule] = useState("power");
  const [docType, setDocType] = useState("report");
  const [license, setLicense] = useState("synthetic");
  const [isSynthetic, setIsSynthetic] = useState(true);
  const [title, setTitle] = useState("");
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [statsData, documentsData] = await Promise.all([api.kbStats(), api.kbDocuments()]);
      setStats(statsData);
      setDocuments(documentsData.items);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const ingest = async () => {
    if (!file) {
      message.warning("请先选择文件");
      return;
    }
    setUploading(true);
    try {
      const meta: Record<string, string> = {
        module, doc_type: docType, license, is_synthetic: String(isSynthetic),
      };
      if (title) meta.title = title;
      const result = await api.kbIngest(file, meta);
      message.success(`摄取完成：${result.doc_id}（${result.chunks} 个切片）`);
      setFile(null);
      setTitle("");
      load();
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
      else message.error(String(error));
    } finally {
      setUploading(false);
    }
  };

  const search = async (query: string) => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const result = await api.kbSearch({ query, top_k: 5 });
      setSearchResults(result.results);
    } catch (error) {
      if (error instanceof ApiError) message.error(`[${error.code}] ${error.message}`);
    } finally {
      setSearching(false);
    }
  };

  const columns: ColumnsType<KbDocument> = [
    { title: "文档", dataIndex: "title", render: (value: string, row) => <><Text strong>{value}</Text><br /><Text type="secondary" className="mono">{row.doc_id}</Text></> },
    { title: "分系统", dataIndex: "module", width: 100 },
    { title: "类型", dataIndex: "doc_type", width: 100 },
    { title: "合成", dataIndex: "is_synthetic", width: 80, render: (value: boolean) => (value ? "是" : "否") },
    { title: "切片", dataIndex: "chunks", width: 80 },
    { title: "许可", dataIndex: "license", width: 120 },
    {
      title: "操作", width: 90,
      render: (_, row) => (
        <Popconfirm
          title={`确认删除 ${row.doc_id}？`}
          description="将级联删除全部切片并写入审计，不可恢复。"
          onConfirm={async () => {
            await api.kbDelete(row.doc_id);
            message.success("已删除");
            load();
          }}
        >
          <Button size="small" danger type="link">删除</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="文档数" value={stats?.documents ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="切片数" value={stats?.chunks ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="语料版本" value={stats?.corpus_version ?? "-"} /></Card></Col>
        <Col span={6}><Card><Statistic title="Embedding" value={String(stats?.embedding_model ?? "-").split("（")[0]} /></Card></Col>
      </Row>

      <Card size="small" title="语料摄取（B2）">
        <Space wrap align="end">
          <Select style={{ width: 130 }} value={module} onChange={setModule}
            options={MODULES.map((value) => ({ value, label: value }))} />
          <Select style={{ width: 130 }} value={docType} onChange={setDocType}
            options={DOC_TYPES.map((value) => ({ value, label: value }))} />
          <Select style={{ width: 150 }} value={isSynthetic ? "true" : "false"}
            onChange={(value) => setIsSynthetic(value === "true")}
            options={[{ value: "true", label: "合成语料" }, { value: "false", label: "真实资料" }]} />
          <Input style={{ width: 150 }} prefix="许可" value={license}
            onChange={(event) => setLicense(event.target.value)} />
          <Input style={{ width: 220 }} placeholder="标题（可选）" value={title}
            onChange={(event) => setTitle(event.target.value)} />
          <Upload.Dragger
            style={{ width: 320 }}
            multiple={false}
            maxCount={1}
            beforeUpload={(selected) => { setFile(selected as File); return false; }}
            onRemove={() => setFile(null)}
            fileList={file ? [{ uid: "1", name: file.name }] : []}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p className="ant-upload-text">点击或拖拽文件（pdf / docx / txt / md / csv）</p>
          </Upload.Dragger>
          <Button type="primary" loading={uploading} onClick={ingest}>摄取</Button>
        </Space>
      </Card>

      <Card size="small" title="检索调试（B1）">
        <Input.Search
          placeholder="输入检索式，例如：太阳翼面积与电池容量如何估算"
          enterButton="检索" loading={searching} onSearch={search} allowClear
        />
        {searchResults && (
          <List
            style={{ marginTop: 12 }}
            size="small"
            dataSource={searchResults}
            locale={{ emptyText: "未检索到依据（no_evidence）" }}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" size={2} style={{ width: "100%" }}>
                  <Space>
                    <Text strong>{item.title}</Text>
                    <Text type="secondary">score {item.score}</Text>
                    <Text code>{item.doc_id}</Text>
                    {item.citation?.is_synthetic && <Text type="warning">[合成]</Text>}
                  </Space>
                  <Text type="secondary">{String(item.text).slice(0, 120)}…</Text>
                </Space>
              </List.Item>
            )}
          />
        )}
      </Card>

      <Card size="small" title="语料列表（B3）">
        <Table rowKey="doc_id" size="small" columns={columns} dataSource={documents}
          pagination={{ pageSize: 10 }} />
      </Card>

      <Alert
        type="info" showIcon
        message="提示：开发版 embedding 为本地哈希实现（离线可用）；bge-m3 + pgvector 为下一步替换项（接口不变）。"
      />
    </Space>
  );
}

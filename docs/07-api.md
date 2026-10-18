# 07 后端接口文档

| 项目 | 内容 |
|---|---|
| 状态 | 细化 |
| 优先级 | P0 |
| 负责人 | 待定 |
| 最后更新 | 2026-10-05 |
| 关联文档 | [05 编排](./05-agent-orchestration.md) · [08 存储](./08-storage.md) · [09 前端](./09-frontend.md) · [03 数据模型](./03-data-model.md) |

> **用途**：本文档细化到「照此即可在 Apifox 手动测试」：每个接口含 URL、认证、参数（字段级）、请求/响应示例、业务逻辑、错误码。
> **已生成 `specs/openapi.yaml`（v0.2，Apifox 可直接导入）**；接口变更先改本文档、再同步生成物，生成物为最终单一事实源（前端类型 / 渲染均从该文件生成）。

## 0. Apifox 快速开始

| 项 | 值 |
|---|---|
| 环境变量 `{{baseUrl}}` | `http://127.0.0.1:8000/api/v1` |
| 环境变量 `{{appToken}}` | 与 `.env` 的 `APP_TOKEN` 一致 |
| 公共请求头 | `Authorization: Bearer {{appToken}}` |
| JSON 请求头 | `Content-Type: application/json`（B2 文件上传用 `multipart/form-data`） |
| 建议测试顺序 | C1 健康检查 → A1 创建任务 → A4 SSE 观察 → A6 参数列表 → A7 参数详情 → A8 参数评审 → A9 重校验 → A10 下载文档 → A11 导出 trace |

**测试数据准备**：`make seed` 后会预置 `t-demo-01`（可完整走通）、`t-demo-adv`（校验拦截场景）；也可用 A1 自行创建。

## 1. 全局约定

### 1.1 基础

- 协议：HTTP；请求与响应均为 UTF-8；时间一律 ISO 8601 UTC（`2026-10-05T09:31:20Z`）
- 任务为异步：创建返回 `202`，进度通过 A4（SSE）或 A3（轮询）获取
- 列表接口分页参数：`page`（默认 1）、`page_size`（默认 20，最大 100）；响应结构见 1.4

### 1.2 认证

- 除 C1 外全部接口需要 `Authorization: Bearer <APP_TOKEN>`
- 缺失或错误 → `401 UNAUTHORIZED`

### 1.3 通用结构

**成功（资源类）**：直接返回资源对象（示例见各接口）。

**成功（列表类）**：

```json
{ "items": [], "total": 0, "page": 1, "page_size": 20 }
```

**失败（统一）**：

```json
{
  "error": {
    "code": "SCHEMA_INVALID",
    "message": "constraints.lifetime_years 必须 ≥ 0.5",
    "details": { "field": "constraints.lifetime_years" },
    "trace_id": "req-20261005-abc123"
  }
}
```

### 1.4 枚举定义

| 枚举 | 取值 | 说明 |
|---|---|---|
| `mission.status` | `queued` / `running` / `awaiting_gate` / `succeeded` / `failed` / `canceled` | 任务状态机 |
| `step.status` | `pending` / `running` / `done` / `failed` / `skipped` | 步骤状态（S1~S10） |
| `parameter.status` | `proposed` / `needs_review` / `verified` / `rejected` | 参数生命周期 |
| `parameter.source_type` | `calc` / `doc` / `catalog` / `assumption` / `human` | 数值来源 |
| `validation.status` | `pass` / `warn` / `block` | 校验判级 |
| `gate.type` | `assumption_confirm` / `discrepancy_resolve` / `final_review` | 门禁类型 |
| `gate.action` | `accept` / `reject` | 门禁动作 |
| `budget_type` | `mass` / `power` / `data` / `link` | 预算类型 |
| `doc_type` | `standard` / `manual` / `report` / `catalog` / `lesson` / `other` | 语料类型 |
| `module` | `system` / `power` / `ttc` / `data` / `adcs` / `orbit` / `payload` / `risk` / `other` | 分系统枚举 |

### 1.5 错误码全表

| HTTP | code | 触发条件 | 处理建议 |
|---|---|---|---|
| 400 | `SCHEMA_INVALID` | 入参不符合 JSON Schema | 按 `details.field` 修正 |
| 401 | `UNAUTHORIZED` | Token 缺失 / 错误 | 检查 `{{appToken}}` |
| 404 | `MISSION_NOT_FOUND` | 任务 id 不存在 | 核对 id |
| 404 | `PARAM_NOT_FOUND` | 参数 id 不存在 | 从 A6 获取合法 id |
| 404 | `DOC_NOT_FOUND` | 指定版本不存在 | 核对 `version` 参数 |
| 409 | `DOC_NOT_READY` | 存在 block 参数 / 渲染未完成 | 查看 `details.blocking[]`，先走 A8/A9 |
| 409 | `STATE_CONFLICT` | 状态不允许当前操作（如对已完成任务 cancel、对 rejected 参数 review） | 刷新 A3 状态后重试 |
| 429 | `RATE_LIMITED` | 超过请求频率（默认 60 次/分钟） | 退避重试 |
| 502 | `PROVIDER_FAILED` | LLM / embedding 供应商全部失败 | 查看 `details.provider`，稍后重试或启用 `STUB_LLM=1` |
| 500 | `INTERNAL` | 未预期异常 | 携带 `trace_id` 反馈 |

### 1.6 SSE 事件全表（A4）

| event | 触发时机 | data 结构 |
|---|---|---|
| `snapshot` | 连接建立时（含断线续传恢复点） | 完整任务状态（同 A3 响应） |
| `step` | 每步开始 / 结束 | `{step, name, status, duration_ms?, message?}` |
| `validation` | S6 每条校验结论 | `{rule, status, param_id, message}` |
| `gate` | 需要人工门禁 | `{gate_id, type, param_id?, message}` |
| `doc` | 文档渲染完成 | `{ready, version, url}` |
| `error` | 任务级失败 | `{code, message, trace_id}` |
| `done` | 任务成功结束 | `{status:"succeeded", document_url, cost_estimate_cny}` |
| `ping` | 心跳（每 15s） | `{}` |

- 断线续传：请求头 `Last-Event-ID: <事件序号>`；服务端从该序号后补发

---

## 2. 接口索引

| # | 方法 | URL | 用途 | 关键内部动作 |
|---|---|---|---|---|
| A1 | POST | `/missions` | 创建任务 | 落库 `queued`，启动编排 |
| A2 | GET | `/missions` | 任务列表 | 分页 + 状态过滤 |
| A3 | GET | `/missions/{id}` | 任务详情 | 聚合步骤进度 / 成本 / 文档状态 |
| A4 | GET | `/missions/{id}/events` | SSE 进度流 | 事件推送 + 续传 |
| A5 | POST | `/missions/{id}/cancel` | 取消任务 | 置 `canceled`，终止后续步骤 |
| A6 | GET | `/missions/{id}/parameters` | 参数列表 | 过滤 + 分页 |
| A7 | GET | `/missions/{id}/parameters/{pid}` | 参数详情 | 含完整溯源链 |
| A8 | POST | `/missions/{id}/parameters/{pid}/review` | 参数评审（门禁） | 状态流转 + 审计 + 触发 A9 |
| A9 | POST | `/missions/{id}/revalidate` | 重新校验 | 重跑 S6（可限定范围） |
| A10 | GET | `/missions/{id}/document` | 下载 Word | 校验门禁（409 保护） |
| A11 | GET | `/missions/{id}/trace` | 导出 trace | jsonl / json |
| A12 | GET | `/missions/{id}/check-report` | 下载校验报告 | 渲染自检结果 |
| A13 | GET | `/missions/{id}/document/preview` | Word 在线预览 | docx → HTML（mammoth），前端直接渲染 |
| A14 | GET/POST | `/missions/{id}/assumptions[/{asm_id}/review]` | 假设台账与确认 | 未确认假设阻断出稿（输入门禁） |
| A15 | GET | `/missions/{id}/candidates` | 选型候选清单 | 示例选型库规则匹配（第 10 章数据源） |
| A16 | POST | `/missions/{id}/reviews/accept-all` | 一键确认全部待处理项 | 草案输入/假设/待评审参数（含超限豁免） |
| B1 | POST | `/kb/search` | 检索调试 | 混合检索 |
| B2 | POST | `/kb/ingest` | 语料摄取 | 解析 → 切分 → 向量入库 |
| B3 | GET | `/kb/documents` | 语料列表 | 分页 |
| B4 | DELETE | `/kb/documents/{doc_id}` | 删除语料 | 级联删 chunk（需 confirm） |
| B5 | GET | `/kb/stats` | 语料统计 | 文档/chunk/版本 |
| C1 | GET | `/healthz` | 健康检查 | DB / embedding / provider 配置 |
| C2 | GET | `/info` | 运行信息 | 版本 / 模型 / 语料 / 桩模式 |
| C3 | GET | `/settings/llm` | 查看供应商注册表 | 密钥掩码；含 mode / primary / 降级链 |
| C4 | PUT | `/settings/llm` | 保存供应商注册表 | 全量列表，顺序即降级顺序；`api_key` 省略 = 保留 |
| C5 | DELETE | `/settings/llm` | 恢复默认注册表 | 清除运行时配置（回落 env / config/llm.json） |
| C6 | POST | `/settings/llm/probe` | 探测端点 | OpenAI 兼容：拉取 `/models`；Anthropic：最小调用 |
| C7 | POST | `/settings/llm/test` | 连通性测试 | 对已保存供应商做一次最小真实调用 |
| D1 | POST | `/chat/sessions` | 新建会话 | 可选 `title` |
| D2 | GET | `/chat/sessions` | 会话列表 | 含消息数、最后一条消息 |
| D3 | GET | `/chat/sessions/{id}` | 会话详情 | 含附件清单 |
| D4 | PATCH | `/chat/sessions/{id}` | 重命名会话 | `{title}` |
| D5 | DELETE | `/chat/sessions/{id}` | 删除会话 | 级联消息 / 附件 / 向量索引 |
| D6 | GET | `/chat/sessions/{id}/messages` | 消息列表 | 直接读 SQLite，供前端渲染 |
| D7 | POST | `/chat/sessions/{id}/messages` | 发送消息 | 返回用户消息 + 助手消息（含引用） |
| D8 | POST | `/chat/sessions/{id}/documents` | 上传会话附件 | multipart；pdf/docx/txt/md/csv；≤20MB |
| D9 | GET | `/chat/sessions/{id}/documents` | 附件列表 | |
| D10 | DELETE | `/chat/sessions/{id}/documents/{document_id}` | 删除附件 | 同步清理知识库与向量索引 |
| D11 | GET | `/chat/sessions/{id}/context` | 上下文用量 | tokens/窗口/百分比/压缩状态 |
| D12 | POST | `/chat/sessions/{id}/messages/stream` | 流式对话 | SSE：user → delta → done |
| C8 | GET | `/settings/chat` | 读取上下文设置 | 自动压缩开关、阈值、窗口等 |
| C9 | PUT | `/settings/chat` | 保存上下文设置 | 保存即生效 |

---

## 3. 任务类接口

### A1 创建任务

- **请求**：`POST {{baseUrl}}/missions`
- **业务逻辑**：
  1. 校验请求体（`mission-request.schema.json`）→ 不合法返回 400
  2. 生成 `task_id`，落库 `missions`（status=`queued`，记录 `corpus_version`）
  3. 异步入队编排状态机（S1 起），立即返回 `202`
  4. 后续进度通过 A4 / A3 获取

**请求体字段**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `goal` | string | ✅ | 1~2000 字 | 任务目标（一句话或详细描述） |
| `provider_id` | string | ❌ | 设置页中已配置的供应商 id | 任务级模型选择；空 = 按降级链（ADR-0006） |
| `constraints` | object | ❌ | 见下 | 结构化约束，可留空由 S1 澄清 |
| `constraints.orbit_type` | string | ❌ | `SSO` / `LEO` / `GEO` / `custom` | 轨道类型 |
| `constraints.altitude_km` | number | ❌ | 200~36000 | 轨道高度 |
| `constraints.lifetime_years` | number | ❌ | 0.5~20 | 卫星寿命 |
| `constraints.payload` | string | ❌ | ≤500 字 | 载荷参数描述 |
| `constraints.mass_limit_kg` | number | ❌ | >0 | 整星质量上限 |
| `constraints.data_requirements` | string | ❌ | ≤500 字 | 成像 / 通信任务需求 |
| `constraints.ttc_conditions` | string | ❌ | ≤500 字 | 测控条件 |
| `constraints.notes` | string | ❌ | ≤1000 字 | 其他约束 |

**请求示例**

```bash
curl -X POST '{{baseUrl}}/missions' \
  -H 'Authorization: Bearer {{appToken}}' -H 'Content-Type: application/json' \
  -d '{
    "goal": "设计一颗 500km SSO 光学遥感小卫星",
    "constraints": {
      "orbit_type": "SSO", "altitude_km": 500, "lifetime_years": 3,
      "payload": "多光谱相机，地面分辨率 5m，幅宽 60km",
      "data_requirements": "每日成像 10 圈，单圈数据量尽量压缩",
      "mass_limit_kg": 80
    }
  }'
```

**响应 202**

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | string | 任务标识，格式 `t-YYYYMMDD-NNN` |
| `status` | string | 固定 `queued` |
| `created_at` | string | ISO 时间 |

```json
{ "task_id": "t-20261005-001", "status": "queued", "created_at": "2026-10-05T09:00:00Z" }
```

- **错误**：400 `SCHEMA_INVALID`；401；429
- **备注**：重复提交相同 `goal` 不会自动去重，由使用者自行判断

### A2 任务列表

- **请求**：`GET {{baseUrl}}/missions?status=running&page=1&page_size=20`
- **业务逻辑**：按 `created_at` 倒序查询；`status` 可选过滤
- **Query 参数**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `status` | string | ❌ | 过滤任务状态（枚举见 1.4） |
| `page` / `page_size` | integer | ❌ | 分页 |

**响应 200**

```json
{
  "items": [
    { "task_id": "t-20261005-001", "goal": "设计一颗 500km SSO 光学遥感小卫星",
      "status": "running", "current_step": "S5", "cost_estimate_cny": 1.24,
      "created_at": "2026-10-05T09:00:00Z", "updated_at": "2026-10-05T09:04:10Z" }
  ],
  "total": 1, "page": 1, "page_size": 20
}
```

### A3 任务详情

- **请求**：`GET {{baseUrl}}/missions/t-20261005-001`
- **业务逻辑**：聚合任务状态、步骤进度（S1~S10 数组）、成本累计、文档状态、最近错误

**响应 200**

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` / `goal` / `status` | string | 基础字段 |
| `steps` | array | `[{code:"S1", name:"任务书解析", status:"done", duration_ms:1200}, ...]` |
| `current_step` | string? | 当前步骤 code（非运行态为 null） |
| `cost_estimate_cny` | number | 累计成本估算 |
| `document` | object | `{ready: bool, version: int?, url: string?}` |
| `pending_gates` | array | `[{gate_id, type, param_id, message}]` |
| `last_error` | object? | `{code, message, trace_id}` |
| `corpus_version` / `created_at` / `updated_at` | string | 版本与时间 |

```json
{
  "task_id": "t-20261005-001", "goal": "设计一颗 500km SSO 光学遥感小卫星",
  "status": "awaiting_gate", "current_step": null,
  "steps": [ {"code":"S5","name":"预算与计算","status":"done","duration_ms":980},
             {"code":"S6","name":"一致性校验","status":"done","duration_ms":210} ],
  "cost_estimate_cny": 1.86, "document": {"ready": false},
  "pending_gates": [ {"gate_id":"g-003","type":"assumption_confirm","param_id":"mass.margin_pct",
                      "message":"方案期余量假设 20% 需确认"} ],
  "last_error": null, "corpus_version": "corpus-v2026.10.0",
  "created_at": "2026-10-05T09:00:00Z", "updated_at": "2026-10-05T09:04:10Z"
}
```

### A4 进度流（SSE）

- **请求**：`GET {{baseUrl}}/missions/t-20261005-001/events`

```bash
curl -N '{{baseUrl}}/missions/t-20261005-001/events' -H 'Authorization: Bearer {{appToken}}'
```

- **业务逻辑**：连接即发 `snapshot`；后续按 1.6 事件表推送；`done` / `error` 后服务端关闭连接
- **断线续传**：请求头带 `Last-Event-ID: <n>`（或查询参数同上）时，服务端补发 id 大于 n 的历史事件（每任务保留最近 500 条）后再进入实时推送；事件带自增 `id:`，客户端按 id 去重即可实现「不丢不重」
- **响应**：`200`，`Content-Type: text/event-stream`

```text
id: 17
event: step
data: {"step":"S5","name":"预算与计算","status":"running"}

id: 18
event: validation
data: {"rule":"V4","status":"block","param_id":"power.sa.area","message":"太阳翼面积与质量预算不一致"}

id: 19
event: gate
data: {"gate_id":"g-003","type":"assumption_confirm","param_id":"mass.margin_pct","message":"方案期余量假设 20% 需确认"}
```

### A5 取消任务

- **请求**：`POST {{baseUrl}}/missions/t-20261005-001/cancel`
- **业务逻辑**：仅 `queued` / `running` / `awaiting_gate` 可取消 → 置 `canceled`，终止未开始步骤；幂等（重复调用返回当前状态）
- **响应 200**：`{ "task_id": "...", "status": "canceled" }`
- **错误**：409 `STATE_CONFLICT`（如已 `succeeded`）

### A6 参数列表

- **请求**：`GET {{baseUrl}}/missions/t-20261005-001/parameters?status=needs_review&module=power&page=1&page_size=50`
- **业务逻辑**：按 `module` / `status` 过滤；默认全量分页；按 `id` 升序
- **响应 200（items 元素）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 如 `power.sa.area` |
| `name` / `unit` | string | 中文名 / 单位 |
| `value` | number | 数值 |
| `status` | string | 参数状态 |
| `source_type` | string | 来源类型 |
| `margin` | number? | 余量 |
| `validation_status` | string? | 最近校验判级 |
| `updated_at` | string | |

### A7 参数详情（含溯源链）

- **请求**：`GET {{baseUrl}}/missions/t-20261005-001/parameters/power.sa.area`
- **业务逻辑**：返回参数完整对象 + `provenance`（溯源链）+ 关联校验结论
- **响应 200（要点）**

```json
{
  "id": "power.sa.area", "name": "太阳翼面积", "value": 4.8, "unit": "m2",
  "source_type": "calc", "source_ref": "calc-20261005-0007",
  "margin": 0.10, "confidence": "high", "status": "verified", "version": 3,
  "provenance": {
    "type": "calculation",
    "record": { "id": "calc-20261005-0007", "tool": "calc.eps", "formula_version": "v1",
                "inputs": {"power.p_eol_w": 210.5, "cell_efficiency": 0.30},
                "outputs": {"power.sa.area": 4.8}, "code_commit": "a1b2c3d" }
  },
  "validations": [ {"rule_id": "V4", "status": "pass", "created_at": "2026-10-05T09:03:00Z"} ]
}
```

- **错误**：404 `PARAM_NOT_FOUND`

### A8 参数评审（人工门禁）

- **请求**：`POST {{baseUrl}}/missions/t-20261005-001/parameters/mass.margin_pct/review`
- **业务逻辑**：
  1. 校验参数存在且状态为 `draft` / `needs_review` / `proposed` / `rejected`（否则 409 `STATE_CONFLICT`）
  2. `accept`：
     - 分组草案（`input.*`，S4 设计输入）：状态 → `assumed`，并自动登记一条已确认假设（`source_ref` 指向该假设；分组输入不支持 `edited_value`）
     - 普通参数：状态 → `verified`（如带 `edited_value` 先更新数值并版本 +1）
  3. `reject`：状态 → `rejected`（`comment` 必填；被驳回的输入/参数会阻止任务恢复，需重新评审）
  4. 写入 `audit_log`；门禁（`review_gates`）在**全部待确认项清零**时才关闭（`remaining_confirmations = 0`），关闭后自动恢复任务（输入门禁 → 从 S5 重算；校验门禁 → 从 S7 继续）
  5. 参数超限被人工放行后，重新校验时 V4 降级为 warn（豁免留痕），不再重复阻断

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `action` | string | ✅ | `accept` / `reject` | 动作 |
| `comment` | string | reject 必填 | ≤500 字 | 评审意见 |
| `reviewer` | string | ✅ | ≤100 字 | 评审人标识 |
| `edited_value` | number | ❌ | 仅 accept | 修正值（会更新参数并留审计） |

```json
{ "action": "accept", "comment": "按工程经验接受 10% 余量", "reviewer": "engineer@example.com" }
```

**响应 200**

```json
{ "param_id": "mass.margin_pct", "status": "verified",
  "gate": { "gate_id": "g-003", "action": "accept", "reviewer": "engineer@example.com", "ts": "2026-10-05T09:05:00Z" },
  "revalidation": { "queued": true, "scope": "param:mass.margin_pct" } }
```

### A9 重新校验

- **请求**：`POST {{baseUrl}}/missions/t-20261005-001/revalidate`
- **业务逻辑**：重跑 S6（V1~V7）；返回本批次校验汇总；`block` 会再次冻结相关参数并推送 SSE
- **请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `scope` | string | ❌ | `all`（默认）/ `module:power` / `param:power.sa.area` |

**响应 200**

```json
{ "queued": true, "scope": "all",
  "summary": { "pass": 18, "warn": 2, "block": 1 },
  "blocking": [ { "rule": "V4", "param_id": "power.sa.area", "message": "太阳翼面积与质量预算不一致" } ] }
```

### A10 下载文档

- **请求**：`GET {{baseUrl}}/missions/t-20261005-001/document?version=1`
- **业务逻辑**：
  1. 存在 `block` 参数 → 409 `DOC_NOT_READY`（`details.blocking[]`）
  2. 流程尚未到达渲染（如仍在 `running`）→ 409 `DOC_NOT_READY`（`details.reason="not_generated"`）
  3. 指定 `version` 不存在 → 404 `DOC_NOT_FOUND`
  4. 返回 docx 二进制 + 文件名头
- **Query 参数**：`version`（可选，默认最新）
- **响应 200**：`application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  - Header：`Content-Disposition: attachment; filename="t-20261005-001-design-v1.docx"`
- **错误示例**

```json
{ "error": { "code": "DOC_NOT_READY", "message": "存在未通过的校验项，禁止导出",
  "details": { "blocking": [ {"rule":"V4","param_id":"power.sa.area"} ] }, "trace_id": "req-..." } }
```

### A11 导出 trace

- **请求**：`GET {{baseUrl}}/missions/t-20261005-001/trace?format=jsonl`
- **Query**：`format` = `jsonl`（默认，文件下载）/ `json`（数组结构，便于 Apifox 内查看）
- **业务逻辑**：读取 `artifacts/<task_id>/trace.jsonl`；`json` 模式做行解析后返回数组
- **响应 200（format=json 时）**

```json
{ "task_id": "t-20261005-001", "event_count": 42,
  "events": [ { "step": "S5", "type": "tool", "duration_ms": 812, "ts": "2026-10-05T09:03:12Z" } ] }
```

### A12 下载校验报告

- **请求**：`GET {{baseUrl}}/missions/t-20261005-001/check-report`
- **业务逻辑**：读取 `artifacts/<task_id>/check-report.json` 并回传；未生成 → 404 `DOC_NOT_FOUND`
- **响应 200**

```json
{ "task_id": "t-20261005-001", "generated_at": "2026-10-05T09:06:00Z",
  "placeholders_left": 0, "numbers_checked": 47, "numbers_traceable": 47,
  "citations": 12, "citation_issues": 0, "status": "pass" }
```

---

### A13 Word 在线预览

- **请求**：`GET {{baseUrl}}/missions/t-20261005-001/document/preview?version=1`
- **业务逻辑**：与 A10 相同的门禁/存在性检查（`_resolve_document`）；docx → HTML 转换（mammoth）后返回
- **Query 参数**：`version`（可选，默认最新）
- **响应 200**

```json
{ "task_id": "t-20261005-001", "version": 1,
  "html": "<h1>卫星整星详细设计方案</h1>…<table>…</table>",
  "warnings": ["Unrecognised paragraph style: Title"] }
```

- **错误**：与 A10 一致（409 `DOC_NOT_READY` / 404 `DOC_NOT_FOUND`）

---

### A14 假设台账与确认

- **列表**：`GET {{baseUrl}}/missions/t-20261005-001/assumptions?status=open` → `{ items: [{id, content, basis, related_params, status, registered_by, confirmed_by, confirmed_at}], total }`
- **确认**：`POST {{baseUrl}}/missions/t-20261005-001/assumptions/asm-0001/review`
  - 请求体：`{ "action": "accept|reject", "reviewer": "engineer@example.com", "comment": "可选（reject 必填）" }`
  - `accept` → 状态 `confirmed`；`reject` → `rejected`；两者都清除一个待确认项
  - 响应：`{ "assumption_id": "asm-0001", "status": "confirmed", "gate": {...}|null, "remaining_confirmations": 0 }`
  - 待确认项清零后自动关闭门禁并恢复任务

### A15 选型候选清单

- **请求**：`GET {{baseUrl}}/missions/t-20261005-001/candidates`
- **业务逻辑**：读取选型库（`data/parts_catalog.json`，示例库）→ 按「满足指标约束、代价最小」规则打分（电池容量、太阳电池效率、角动量/磁矩需求、质量功耗代价）
- **响应 200**：`{ task_id, items: [{id, category, name, vendor, params, score, reason, source_ref}], total }`
- 候选清单同时作为文档第 10 章的数据源（S5 生成 → S9 渲染）

### A16 一键确认全部待处理项

- **请求**：`POST {{baseUrl}}/missions/t-20261005-001/reviews/accept-all`
- **请求体**：`{ "reviewer": "engineer@example.com", "comment": "可选" }`
- **业务逻辑**：依次接受 `draft` / `needs_review` / `rejected` 参数（草案输入按当前 JSON 值确认）与
  所有 `open` 假设；待确认项清零后关闭门禁并恢复任务（校验门禁放行后重跑 S6）
- **响应**：

```json
{ "mission_id": "t-20261005-001", "accepted_parameters": 8,
  "accepted_assumptions": 3, "remaining_confirmations": 0,
  "gate": { "gate_id": "g-001", "action": "accept", "reviewer": "engineer@example.com" },
  "revalidation": { "queued": true } }
```

- **A8 补充**：`accept` 分组草案（`input.*`）可通过 `edited_payload`（JSON）修改整组设计输入，
  后端按对应分组的输入模型校验；`reject` 参数或假设会把任务置为 `failed`（`REVIEW_REJECTED`），
  不再停留在门禁。

## 3.5 个人 agent 会话接口（D1~D10）

> 定位：单用户本地 agent。会话、消息、摘要、附件均存本机 SQLite（[ADR-0007](./adr/0007-personal-agent.md)）；
> 前端直接读取 D2/D6 的返回结果渲染，不维护独立缓存。所有接口需 Bearer Token（单用户本机令牌）。

**D1 新建会话**：`POST {{baseUrl}}/chat/sessions`

```json
{ "title": "测控链路问题排查" }
```

响应 201：`{ "id": "cs-20261018-001", "title": "测控链路问题排查", "summary": "", "created_at": "...", "updated_at": "...", "message_count": 0, "last_message": "" }`

**D2 会话列表**：`GET {{baseUrl}}/chat/sessions?limit=100` → `{ items: [...], total }`（按 `updated_at` 倒序）

**D3/D4/D5 会话详情 / 更新 / 删除**：
- `GET /chat/sessions/{id}` → 会话字段 + `documents[]` + `context`
- `PATCH /chat/sessions/{id}` body 可含 `title` / `pinned` / `provider_id` / `model` / `reasoning_effort`
- `DELETE /chat/sessions/{id}` → `{ session_id, deleted_messages, deleted_documents }`（附件对应的知识库文档与向量一并删除）
- `GET /chat/sessions/{id}/context` → 上下文估算与压缩状态；`POST .../messages/stream` → SSE（`user`/`delta`/`done`/`error`）

**D6 消息列表**：`GET /chat/sessions/{id}/messages?limit=300`

```json
{ "items": [
  { "id": 1, "role": "user", "content": "链路余量要求是多少？", "meta": {}, "created_at": "..." },
  { "id": 2, "role": "assistant", "content": "根据资料…[S1]",
    "meta": { "citations": [{ "id": "S1", "title": "…", "score": 0.52, "snippet": "…" }],
              "used_citations": ["S1"], "action": "search", "index_mode": "sqlite-vec" },
    "created_at": "..." } ],
  "total": 2 }
```

**D7 发送消息**：`POST /chat/sessions/{id}/messages` body `{ "content": "..." }`

- 业务逻辑：写入用户消息（首条自动作会话标题）→ 读取最近 12 条消息 + 会话摘要 → LangGraph 编排
  （plan → 可选 retrieve（会话附件，sqlite-vec）→ answer）→ 写入助手消息 → 按需刷新长期摘要
- 响应：`{ user, assistant, session }`

**D8/D9/D10 会话附件**：
- 上传：`POST /chat/sessions/{id}/documents`（multipart `file`，≤20MB）→ `{ id, doc_id, filename, chunks, created_at }`
- 列表：`GET /chat/sessions/{id}/documents`
- 删除：`DELETE /chat/sessions/{id}/documents/{document_id}`

```bash
# 创建会话并发送一条消息
curl -s -X POST {{baseUrl}}/chat/sessions -H 'Authorization: Bearer {{appToken}}' \
  -H 'Content-Type: application/json' -d '{"title":"本地问答"}'
curl -s -X POST {{baseUrl}}/chat/sessions/<sid>/messages -H 'Authorization: Bearer {{appToken}}' \
  -H 'Content-Type: application/json' -d '{"content":"请检索资料：链路余量要求"}'
# 上传附件
curl -s -X POST {{baseUrl}}/chat/sessions/<sid>/documents -H 'Authorization: Bearer {{appToken}}' \
  -F 'file=@./notes.txt'
```

---

## 4. 知识库接口

### B1 检索

- **请求**：`POST {{baseUrl}}/kb/search`
- **业务逻辑**：混合检索（向量 0.7 + 关键词 0.3，[04](./04-knowledge-base.md) §4）→ 过滤 → 返回带引用的结果
- **请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `query` | string | ✅ | 1~500 字 | 检索问题 |
| `filters.module` | string | ❌ | module 枚举 | 分系统过滤 |
| `filters.doc_type` | string | ❌ | doc_type 枚举 | 文档类型过滤 |
| `filters.year_from` | integer | ❌ | ≥1950 | 起始年份 |
| `filters.is_synthetic` | boolean | ❌ | — | 是否包含合成语料（默认 true） |
| `top_k` | integer | ❌ | 1~20，默认 8 | 返回条数 |

**响应 200**

```json
{ "results": [ { "chunk_id": "sst-soa-pwr-014-03", "doc_id": "sst-soa-2026-pwr", "title": "SST-SOA 电源章节",
                 "text": "…典型太阳电池阵面积与功率关系…", "score": 0.83,
                 "citation": { "source_url": "https://www.nasa.gov/smallsat-institute/sst-soa/",
                               "page": 14, "module": "power", "is_synthetic": false } } ],
  "took_ms": 186 }
```

### B2 语料摄取

- **请求**：`POST {{baseUrl}}/kb/ingest`（`multipart/form-data`）
- **业务逻辑**：存文件 → 解析 → 切分 → embedding → 写 `kb_chunks` 与 `corpus_manifest` → 返回统计（同步执行，大文件可 202 异步——本期同步）

**Form 字段**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | file | ✅ | PDF / DOCX / TXT / CSV |
| `module` | string | ✅ | module 枚举 |
| `doc_type` | string | ✅ | doc_type 枚举 |
| `is_synthetic` | boolean | ❌ | 默认 false |
| `license` | string | ✅ | 许可标识（如 `public-nasa`） |
| `title` | string | ❌ | 缺省用文件名 |

**响应 201**

```json
{ "doc_id": "sst-soa-2026-pwr", "title": "SST-SOA 电源章节", "chunks": 87,
  "corpus_version": "corpus-v2026.10.1" }
```

- **错误**：400 `SCHEMA_INVALID`（缺 license 等）；409 重复 doc_id（提示用 B4 删除后重传）

### B3 语料列表

- **请求**：`GET {{baseUrl}}/kb/documents?module=power&page=1&page_size=20`
- **业务逻辑**：按 `module` / `doc_type` 过滤，按 `fetched_at` 倒序分页
- **响应 200**：`{ "items": [ { "doc_id": "…", "title": "…", "module": "power", "doc_type": "manual",
  "is_synthetic": false, "license": "public-nasa", "chunks": 87, "fetched_at": "…" } ], "total": 1, "page": 1, "page_size": 20 }`

### B4 删除语料

- **请求**：`DELETE {{baseUrl}}/kb/documents/sst-soa-2026-pwr?confirm=true`
- **业务逻辑**：`confirm=true` 才执行；级联删除 `kb_chunks`；写审计；不可恢复
- **响应 200**：`{ "doc_id": "…", "deleted_chunks": 87, "corpus_version": "corpus-v2026.10.2" }`
- **错误**：400（未带 confirm）；404

### B5 语料统计

- **请求**：`GET {{baseUrl}}/kb/stats`
- **业务逻辑**：统计 `corpus_manifest` 与 `kb_chunks` 计数，返回当前语料版本
- **响应 200**

```json
{ "documents": 42, "chunks": 3120, "corpus_version": "corpus-v2026.10.2",
  "embedding_model": "bge-m3", "last_ingest_at": "2026-10-05T08:40:00Z" }
```

---

## 5. 系统接口

### C1 健康检查（无需认证）

- **请求**：`GET {{baseUrl}}/healthz`
- **业务逻辑**：检查 DB 连通、embedding 模型状态、LLM Key 配置（不发起在线调用）；任一关键项异常 → `degraded`
- **响应 200**

```json
{ "status": "ok", "checks": { "database": "ok", "embedding": "ok",
  "llm": { "stub": false, "providers": { "deepseek": "configured", "qwen": "configured",
           "openai": "not_configured", "ollama": "configured" } } } }
```

- 任一关键项异常 → `"status": "degraded"`（HTTP 仍 200，便于监控区分）

### C2 运行信息

- **请求**：`GET {{baseUrl}}/info`
- **业务逻辑**：返回运行配置摘要（不含密钥），供演示环境自检
- **响应 200**

```json
{ "app_version": "0.1.0", "api_version": "v1", "stub_mode": false,
  "models": { "primary": "deepseek-chat", "fallback_order": ["deepseek","qwen","openai-claude","ollama"] },
  "corpus_version": "corpus-v2026.10.2", "template_version": "design-report-v1" }
```

---

## 5.1 供应商设置接口（C3~C7，ADR-0006）

> 前端「设置」页使用；支持任意 OpenAI 兼容 / Anthropic 协议第三方，保存后立即生效。

| # | 方法 | 路径 | 用途 | 说明 |
|---|---|---|---|---|
| C3 | GET | `/settings/llm` | 查看注册表 | 密钥掩码（`key_masked` / `has_key`），含 `mode` / `primary` / 降级链 |
| C4 | PUT | `/settings/llm` | 保存注册表 | 全量列表，顺序即降级顺序；`api_key` 省略 = 保留原值 |
| C5 | DELETE | `/settings/llm` | 恢复默认 | 清除运行时配置（回落 env / `config/llm.json` / 内置默认） |
| C6 | POST | `/settings/llm/probe` | 探测端点 | OpenAI 兼容：拉取 `/models` 返回模型列表；Anthropic：最小调用 |
| C7 | POST | `/settings/llm/test` | 连通性测试 | 对某个已保存供应商做一次最小真实调用（鉴权 + 模型名校验） |

- 配置优先级：运行时（DB）> 环境变量 > `config/llm.json` > 内置默认
- 桩模式判定：`STUB_LLM` 显式设置优先；未设置时「无可用供应商 → 桩模式」
- 保存第三方网关示例：

```json
PUT /api/v1/settings/llm
{ "providers": [{ "id": "aiapi", "protocol": "openai",
  "base_url": "https://aiapi.c0c.cc/v1", "model": "gpt-5.6-sol",
  "api_key": "sk-…", "json_mode": true, "price_in": 0.01, "price_out": 0.03 }] }
```

---

## 6. 内部工具契约（非 HTTP）

> 供 pytest / 调试直接调用；契约文件在 `specs/schemas/tools/`；不通过 Apifox 测试。
> 如实现期需要，可另开 `dev` 命名空间把工具暴露为 HTTP 调试端点（仅 `APP_ENV=dev` 启用），届时补充到本文档第 5 节。

| 工具 | Schema | 输入要点 | 输出 |
|---|---|---|---|
| `calc.mass_budget` / `calc.power_budget` / `calc.data_budget` / `calc.link_budget` | `tools/calc-budget.schema.json` | 行项目 + 余量策略 + 轨道参数 | Budget + CalculationRecord |
| `calc.orbit` | `tools/calc-orbit.schema.json` | 轨道根数 + 地面站 + 最小仰角 | 过境窗口 / 重访统计 |
| `kb.search` | `tools/kb-search.schema.json` | 同 B1 请求体 | Citations |
| `doc.render` / `doc.check` | `tools/doc-render.schema.json` | IR + 叙述 + 模板版本 | 文件路径 + 检查报告 |

---

## 7. 变更记录

| 日期 | 版本 | 变更 | 兼容性 |
|---|---|---|---|
| 2026-10-05 | v0.1 | 初稿（接口清单与约定） | — |
| 2026-10-05 | v0.2 | 细化：字段级参数、请求/响应示例、业务逻辑、错误码全表、SSE 事件表、Apifox 指南 | 不涉及实现，无兼容性问题 |
| 2026-10-06 | v0.3 | 新增供应商设置接口 C3~C7（注册表 / 运行时配置 / 探测 / 测试，ADR-0006） | 新增接口，向后兼容 |
| 2026-10-06 | v0.4 | A1 支持 `provider_id`（任务级模型选择）；新增 A13 Word 在线预览 | 新增字段/接口，向后兼容 |
| 2026-10-06 | v0.5 | 输入确认门禁（A8 语义扩展 + A14 假设台账）；新增 A15 选型候选；A4 支持 `Last-Event-ID` 断线重放；文档版本递增（A2/A10/A13 支持 `version`） | 新增字段/接口，向后兼容 |
| 2026-10-18 | v0.6 | 个人本地 agent：新增会话接口 D1~D10（SQLite 记忆、多会话、附件上传）；不改变既有 A/B/C 接口 | 新增接口，向后兼容 |

## 8. 关键取舍

| 决策 | 备选 | 理由 | ADR |
|---|---|---|---|
| REST + SSE | WebSocket | 单向进度流足够，Apifox / curl 均可直接调试 | [0001](./adr/0001-tech-stack.md) |
| 文档 URL 级 409 保护 | 允许导出后人工把关 | 把「未验证数字不得入稿」做成系统强制 | [0001](./adr/0001-tech-stack.md) |
| 门禁收敛到参数级 review | 独立假设/差异两套接口 | 一个接口覆盖三类门禁，前端实现简单 | — |
| 本文档 → 生成 OpenAPI | 手工维护 OpenAPI | 文档可读 + 生成物单一事实源，Apifox 可直接导入 | — |

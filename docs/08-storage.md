# 08 数据与存储设计

| 项目 | 内容 |
|---|---|
| 状态 | 细化 |
| 优先级 | P0 |
| 负责人 | 待定 |
| 最后更新 | 2026-10-05 |
| 关联文档 | [03 数据模型](./03-data-model.md) · [04 知识库](./04-knowledge-base.md) · [12 部署](./12-deployment.md) |

> 存储选型（个人本地 agent，[ADR-0007](./adr/0007-personal-agent.md)）：**SQLite 单一文件**承载任务、参数、预算、校验、门禁、审计、会话记忆与知识库；向量检索用 **sqlite-vec**。Postgres + pgvector 保留为企业部署备选（[ADR-0003](./adr/0003-storage.md) 已被取代）。

## 1. 存储分层

| 层 | 存什么 | 技术 | 连接配置 |
|---|---|---|---|
| 关系型 | 任务 / 参数 / 预算 / 校验 / 门禁 / 审计 / 会话 / 消息 / 语料登记 | SQLite（默认 `dev.db`） | `DATABASE_URL`（[12](./12-deployment.md)） |
| 向量 | chunk embedding + 元数据 | sqlite-vec `vec0` 虚表（同库）；缺失时回退 JSON 扫描 | 同库文件 |
| 文件 | 语料原文 / 模板 / Word / trace | 本地目录 | 路径常量见 §4 |
| 缓存 | 本期不做 | — | — |

## 2. 关系型表设计

> 约定：主键 `id`；枚举用 `text + CHECK`（便于演进，不用 PG enum）；所有表含 `created_at`；金额/数值用 `numeric`；JSON 用 `jsonb`。

### 2.1 missions

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | text | PK | `t-YYYYMMDD-NNN` |
| `goal` | text | NOT NULL | 任务目标 |
| `constraints` | jsonb | NOT NULL DEFAULT '{}' | MissionRequest.constraints 快照 |
| `status` | text | CHECK ∈ queued/running/awaiting_gate/succeeded/failed/canceled | |
| `current_step` | text | NULL | S1~S10 |
| `corpus_version` | text | NOT NULL | 语料版本 |
| `model_versions` | jsonb | NOT NULL | 各 provider 实际模型版本 |
| `template_version` | text | NOT NULL | 文档模板版本 |
| `cost_estimate_cny` | numeric(10,4) | DEFAULT 0 | 累计成本 |
| `last_error` | jsonb | NULL | `{code,message,trace_id}` |
| `created_at` / `updated_at` | timestamptz | NOT NULL | |

索引：`idx_missions_status(status)`、`idx_missions_created_at(created_at DESC)`

### 2.2 design_parameters

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | text | PK 的一部分 | 参数 id |
| `mission_id` | text | PK 的一部分，FK→missions | |
| `name` / `name_en` | text | NOT NULL | |
| `value` / `unit` | numeric / text | NOT NULL | 单位枚举在应用层校验 |
| `source_type` | text | CHECK ∈ calc/doc/catalog/assumption/human | |
| `source_ref` | text | NOT NULL | 溯源引用 |
| `margin` | numeric | NULL | |
| `confidence` | text | CHECK ∈ high/medium/low | |
| `status` | text | CHECK ∈ proposed/needs_review/verified/rejected | |
| `parent` | text | NULL | 指标树 |
| `derived_from` | jsonb | DEFAULT '[]' | 上游参数 id 数组 |
| `upstream_hash` | text | NULL | 陈旧检测 |
| `version` | int | NOT NULL DEFAULT 1 | |
| `updated_at` | timestamptz | NOT NULL | |

主键：`PK(mission_id, id)`；索引：`idx_params_mission_status(mission_id, status)`、`idx_params_parent(mission_id, parent)`

### 2.3 budgets / budget_items

`budgets`：`id PK`、`mission_id FK`、`budget_type CHECK ∈ mass/power/data/link`、`summary_rule CHECK ∈ sum/max/race`、`total_value numeric`、`total_unit text`、`margin_pct numeric NULL`、`status text`、`created_at`
`budget_items`：`id PK`、`budget_id FK`、`name text`、`param_id text NULL`、`value numeric`、`unit text`、`margin numeric NULL`、`source_ref text`、`note text NULL`

索引：`idx_budgets_mission_type(mission_id, budget_type UNIQUE)`

### 2.4 calculation_records

`id PK`、`mission_id FK`、`tool text`、`formula_version text`、`inputs jsonb`、`units_map jsonb`、`outputs jsonb`、`code_commit text`、`duration_ms int`、`created_at`
索引：`idx_calc_mission(mission_id)`；**只追加，不更新**（溯源不可变）

### 2.5 validation_results

`id PK`、`mission_id FK`、`rule_id CHECK ∈ V1..V7`、`status CHECK ∈ pass/warn/block`、`param_id text NULL`、`message text`、`evidence jsonb`、`created_at`
索引：`idx_vr_mission_status(mission_id, status)`、`idx_vr_param(mission_id, param_id)`

### 2.6 assumptions

`id PK`、`mission_id FK`、`content text`、`basis text`、`related_params jsonb`、`status CHECK ∈ open/confirmed/rejected`、`registered_by text`、`confirmed_by text NULL`、`confirmed_at timestamptz NULL`

### 2.7 review_gates

`id PK`、`mission_id FK`、`type CHECK ∈ assumption_confirm/discrepancy_resolve/final_review`、`param_id text NULL`、`action CHECK ∈ accept/reject`、`reviewer text`、`comment text`、`ts timestamptz`

### 2.8 audit_log

`id bigserial PK`、`entity text`、`entity_id text`、`field text NULL`、`before jsonb NULL`、`after jsonb NULL`、`who text`、`why text`、`ts timestamptz`
索引：`idx_audit_entity(entity, entity_id)`

### 2.9 corpus_manifest

| 列 | 类型 | 说明 |
|---|---|---|
| `doc_id` | text PK | 如 `sst-soa-2026-pwr` |
| `title` / `source_url` / `license` | text | 必填 |
| `sha256` | text | 文件校验 |
| `is_synthetic` | boolean | 默认 false |
| `module` / `doc_type` | text | 枚举 |
| `chunks` | int | 切片数 |
| `fetched_at` | timestamptz | |

### 2.10 kb_chunks

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | text PK | `<doc_id>-<序号>` |
| `doc_id` | text FK→corpus_manifest ON DELETE CASCADE | |
| `content` | text | 切片正文 |
| `embedding` | json | 向量（SQLite JSON）；同时写入 sqlite-vec 索引 |
| `metadata` | json | `{module, doc_type, year, page, is_synthetic, source_url, license, session_id?, embedding_model, embedding_dim}` |

### 2.11 chat_sessions / chat_messages / chat_documents（个人 agent）

| 表 | 列 | 说明 |
|---|---|---|
| `chat_sessions` | `id` text PK（`cs-YYYYMMDD-NNN`）、`title`、`summary`（长期记忆）、`archived`、`created_at`、`updated_at` | 会话 |
| `chat_messages` | `id` integer PK 自增、`session_id`（索引）、`role`（user/assistant/system）、`content`、`meta` json（citations/action/index_mode）、`created_at` | 短期记忆，前端直接读取渲染 |
| `chat_documents` | `id` text PK（`cd-NNNN`，会话内序号）、`session_id`（索引）、`doc_id`（→ corpus_manifest）、`filename`、`chunks`、`created_at` | 会话附件 |

- 记忆策略：短期 = 最近 12 条消息；长期 = `chat_sessions.summary`（每累计 10 条消息刷新）
- 删除会话：级联删除消息与附件记录，并删除对应知识库文档与向量索引

## 3. 向量检索（sqlite-vec）

**初始化（代码自动完成）**：

```sql
-- 每个 embedding 维度一张虚表；距离度量：余弦
CREATE VIRTUAL TABLE IF NOT EXISTS kb_vec_1024
  USING vec0(chunk_id text, embedding float[1024] distance_metric=cosine);
```

**混合检索流程**：

1. sqlite-vec 近邻召回（默认 top-200，`WHERE embedding MATCH ? AND k = ? ORDER BY distance`）
2. 元数据过滤（module / doc_type / session_id / is_synthetic 等，在 SQLite 行上判断）
3. 与关键词重叠度加权：`score = 0.7 × cosine + 0.3 × kw`（初值，评测后调优）
4. 阈值过滤（默认 `score ≥ 0.35`；聊天会话检索用 0.18 偏召回）→ 返回 Top-K

- 扩展不可用或索引为空时自动回退「JSON 向量全量扫描」，返回结构与阈值不变
- 权重/阈值变更需开 ADR（见 [adr/README](./adr/README.md) 待记录清单）

## 4. 文件与制品目录

```
corpus/raw/<module>/          # 原始语料（只读）
corpus/synthetic/             # 合成语料
corpus/manifest.csv           # 语料登记（与 corpus_manifest 同步）
templates/design-report-v1.docx
artifacts/<task_id>/
  document-v<N>.docx
  check-report.json
  parameters-snapshot.json
  trace.jsonl
```

- 命名：`<task_id>-<doctype>-v<N>.docx`；出入库记录 sha256
- `artifacts` 为快照导出（备份/演示）的核心内容

## 5. 备份 / 导出 / 可复现

```bash
# 备份（SQLite 在线备份，单文件即可复制）
sqlite3 dev.db ".backup 'backup-$(date +%F).db'"
tar -czf artifacts-$(date +%F).tgz artifacts/

# 任务快照（make snapshot TASK=<id>）：导出任务相关表 + tar artifacts/<task_id>/
```

- 种子数据：黄金用例输入、fixtures、语料 manifest 快照（`make seed`）
- 快照内容：IR + trace + 语料版本 + 模型版本 + 模板版本（[12](./12-deployment.md) §6）

## 6. 数据保留与清理

- `audit_log` / `review_gates` / `calculation_records` **不可删除**
- 临时中间态（如失败任务的半成品 artifacts）可清理
- 🔒 版权资料：不进入系统存储（[04](./04-knowledge-base.md) §2）

## 7. 关键取舍

| 决策 | 备选 | 理由 | ADR |
|---|---|---|---|
| SQLite + sqlite-vec（个人 agent） | Postgres + pgvector / 独立向量库 | 零服务依赖、单文件可备份、前端可直读 | [0007](./adr/0007-personal-agent.md) |
| text + CHECK 代替 PG enum | 原生 enum | 迁移无需 ALTER TYPE，演进成本低 | — |
| 计算/校验/审计表只追加 | 允许更新 | 溯源不可变，回放可信 | [0005](./adr/0005-doc-engine.md) |
| Repository 层隔离存储实现 | ORM 散落业务代码 | 保留降级 / 迁移能力 | [0003](./adr/0003-storage.md) |

# ADR-0007：个人本地 agent（SQLite 单一存储 + sqlite-vec + LangGraph）

| 项目 | 内容 |
|---|---|
| 状态 | 接受 |
| 日期 | 2026-10-18 |
| 决策人 | 项目负责人 |
| 关联 | [02 总体设计](../02-overall-design.md) · [03 数据模型](../03-data-model.md) · [04 知识库](../04-knowledge-base.md) · [08 存储](../08-storage.md) · [09 前端](../09-frontend.md) |

## 1. 背景与问题

- 产品定位从「统一服务器后端管理」调整为**个人本地 agent**：单用户、本机运行，不引入账号体系与独立数据库服务；
- 要求：上下文短期/长期记忆、聊天记录持久化、RAG 向量检索全部落到本机 SQLite；前端直接读取 SQLite 里的会话记录渲染；
- 主页面改为聊天式界面（Codex 风格），支持文档上传作为会话附件；
- 需要多会话（新建/切换/删除），并评估 LangChain / LangGraph 的引入价值。

## 2. 备选方案

| 方案 | 描述 | 优点 | 缺点 |
|---|---|---|---|
| A（选定） | 自建 SQLite 表（会话/消息/附件）承载记忆；sqlite-vec 做向量索引；LangGraph 编排单轮对话（plan → retrieve → answer）；任务流水线保留自研状态机 | 零服务依赖、前端可直接读库、迁移风险小；聊天流程用图表达清晰 | 语义检索规模受单机限制；混合架构需要文档说明边界 |
| B | 全部换成 LangChain/LangGraph（含任务流水线） | 生态统一 | 门禁/断点/SSE/trace 语义需重写，回归风险高，收益低 |
| C | 继续 Postgres + pgvector | 关系与向量同库、规模更好 | 与「个人本地 agent」定位冲突，需要 Docker 常驻 |

## 3. 决策与理由

1. **SQLite 作为唯一存储**：会话、消息、会话摘要、任务、计算记录、知识库、向量索引全部在同一个本地文件（`DATABASE_URL`）；
2. **记忆分层**：
   - 短期记忆 = `chat_messages` 最近 12 条（按会话，直接供前端渲染）；
   - 长期记忆 = `chat_sessions.summary`（每累计 10 条消息刷新一次），随请求注入 prompt；
   - 不使用 LangGraph checkpointer 做消息存储，避免「状态一份、UI 一份」的双写；
3. **RAG 向量索引**：`sqlite-vec` 的 `vec0` 虚表（每维度一张，余弦距离，`chunk_id` 辅助列）；扩展不可用时自动回退到 SQLite JSON 全量扫描（保留现有混合打分与阈值）；
4. **LangGraph 的适用边界**：仅用于聊天编排（`app/chat/graph.py`：plan → retrieve → answer）。任务流水线的门禁挂起/断点恢复/SSE 事件/成本守卫依赖现有状态机，迁移到 LangGraph 需要重写这些语义且没有功能收益，保留自研；
5. LangChain 生态暂不引入：现有 provider 注册表、提示词文件化与结构化校验已覆盖需求；避免双套 LLM 抽象。

## 4. 影响

- 文档：[04](../04-knowledge-base.md) 的向量方案改为 sqlite-vec；[08](../08-storage.md) 增加聊天/向量表；[09](../09-frontend.md) 主页面改为聊天；
- 接口：新增 `D1~D8` 聊天接口（[07](../07-api.md)）；
- 依赖：新增 `sqlite-vec`、`langgraph`；不再默认要求 Postgres（ADR-0003 的 Postgres 目标形态降级为可选的企业部署选项）；
- 安全：上传文件仅进本地知识库；模型调用仍会把必要的提示词/片段发往所选供应商（设置页可见）。

## 5. 补充（2026-10-18）：上下文与长期记忆、任务联动

1. **短期上下文**：消息全量入库；达到模型窗口阈值（默认 80%，设置页可调、可关）时自动压缩为摘要，
   保留最近若干条；`/compact` 手动触发；窗口大小取供应商标注的 `context_window`（默认 128k）。
2. **长期记忆**：新增 `user_memories`，只保存跨会话有效的偏好/习惯（自动抽取 + `/remember`），
   不保存原始对话；每轮注入提示词。
3. **聊天与任务联动**：plan 动作扩展为工具集合（create/list/status/review mission、kb store/list/delete、
   memory add/list/delete）；任务与评审逻辑抽到 `app/services/` 供 API 与聊天复用。
4. **模型与推理强度**：会话级 `provider_id/model/reasoning_effort`，随调用透传（OpenAI 兼容
   `reasoning_effort`；Anthropic 忽略该字段）。
5. **流式**：OpenAI 兼容供应商走原生 SSE token 流；其他供应商按块下发兜底；前端逐字渲染。

## 6. 补充（2026-10-19）：评审闭环与窗口来源

1. **一键确认**：`POST /missions/{id}/reviews/accept-all` 统一接受草案输入、假设与待评审参数（超限记为豁免）。
2. **草案参数可编辑**：A8 支持 `edited_payload`（按分系统输入模型校验），不再强制"驳回重建"。
3. **驳回语义**：驳回参数或假设 → 任务置 `failed`（`REVIEW_REJECTED`）并关闭门禁，避免卡死。
4. **窗口来源**：压缩窗口以「对话与上下文」设置为准（默认 256k，单位 k tokens）；供应商 `/models` 不返回
   上下文长度，故不做推断展示，由用户按模型说明填写；`proposed` 不再计入待评审（修复"已完成仍显示待评审"）。
5. **评审豁免**：人工接受过的参数记录 `waived`，重跑校验命中阻断时降级为 warn；一键确认在一次请求内
   处理新产生的门禁（最多 3 轮），避免用户反复点击。
6. **建任务先澄清**：聊天中的设计请求先生成 `pending_mission` 草稿（轨道/高度/寿命/质量上限），
   只有用户明确确认后才创建任务。

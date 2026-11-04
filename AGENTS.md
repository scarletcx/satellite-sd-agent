<!-- local-key-memory:start -->
## Project Key Memory (binding)

<!-- Generated from key_memory.md by local-key-memory. Do not edit this block by hand. -->

# Key Memory

> Single source of truth for hard requirements, key decisions, and progress.
> Last updated: 2026-10-22 | Status: active

## 1. Goal

- 目标：本地单用户的 AI 卫星总体设计助手——任务书进，可追溯的整星设计方案 Word 出；聊天 agent 可操作任务与知识库。
- 交付物：FastAPI + React、S1~S9 流水线、RAG、聊天 agent、测试与文档。
- 非目标：多租户/SaaS、真实型号审定、生产级 CAE/姿控仿真、云端默认部署。

## 2. Hard requirements

- R1 本地优先：会话、记忆、任务、知识库、向量默认全部落在同一 SQLite（`DATABASE_URL`，默认 `dev.db`）；不引入外部数据库作为默认依赖。
- R2 数值只能由确定性代码计算；LLM 不得直接产出最终数值结论；文档数字必须由占位符从数据库注入。
- R3 每个设计参数必须有 `source_type` + `source_ref`；`calc` 必须指向存在的计算记录，`assumption` 必须指向存在的假设，否则 V1 阻断。
- R4 S4 设计输入先落 `draft`；未经人工确认不得进入 S5；输入门禁清零后从 S5 重算。
- R5 S6 执行 V1~V7；存在 `block` 必须进入 `awaiting_gate`；人工接受记 `waived`，重跑时 block 降级 warn；一键确认最多自动处理 3 轮门禁。
- R6 存在 `needs_review` / `rejected` 参数时禁止导出与预览 Word（HTTP 409）；渲染后必须做数字与引用白名单自检。
- R7 聊天必须能操作任务与知识库（创建/查询/审核/一键确认/入库/删除），独立页面保持完整；共用服务层。
- R8 聊天中的设计请求先建 `pending_mission` 草稿并追问参数；只有明确“确认创建/按默认参数创建”才创建任务；支持 `auto_review`。
- R9 会话消息全量存 SQLite；达阈值压缩为 `summary` + `compacted_until`，保留 `keep_recent` 条；长期记忆只存跨会话偏好，不存原始对话。
- R10 RAG：切片 600 字符/15%；embedding 默认 `hashing` 可切 `bge-m3`；sqlite-vec 余弦；`0.7*cosine+0.3*keyword`；阈值 0.35/聊天 0.18；会话检索=本会话+全局。
- R11 编号=已有最大序号+1；删除任务级联清理关联数据、制品与事件历史。
- R12 上下文窗口单位为 k tokens（默认 256k）；不展示或推断供应商模型窗口。
- R13 完成任务前跑通 `pytest`（98 项）与 `cd web && npm run build`；接口变更同步 OpenAPI/docs。
- R14 推送 GitHub 远程；提交说明使用中文。

## 3. Never

- N1 不要让 LLM 计算或编造最终数值；不要把模型输出直接写进已确认参数或最终文档。
- N2 不要在仓库写入密钥、Token 或个人数据；只记录环境变量名。
- N3 `answer/` 是本地私密目录（已 gitignore），不得提交或上传其中的 PDF/Markdown。
- N4 不要绕开服务层另写业务逻辑，或破坏独立页面。
- N5 不要用“数量+1”生成编号；删除任务不要保留旧事件或旧制品。

## 4. Constraints

- Stack: Python ≥3.11、FastAPI、Pydantic v2、SQLAlchemy 2、SQLite+sqlite-vec、LangGraph、docxtpl、PyMuPDF、skyfield；React+TS+Vite+AntD 5。
- Auth：Bearer `APP_TOKEN`，前缀 `/api/v1`；单用户本地，任务后台线程，SSE 支持 `Last-Event-ID`，`STUB_LLM=1` 可离线。
- Provider：DB `app_meta:llm.providers` > env > `config/llm.json` > 默认；超时 120s；费用上限 3 CNY。
- 测试：`STUB_LLM=1` + 临时 SQLite，不依赖网络；中文 UI/文档，少注释，不加无关依赖。

## 5. Key decisions

- 2026-10：聊天用 LangGraph（plan → tool/retrieve/answer）；S1~S9 手写状态机，不迁移。
- 2026-10：默认 SQLite+sqlite-vec；pgvector 仅生产选项。
- 2026-10：长期记忆 `user_memories`；短期阈值压缩，不粗暴截断最近 N 条。
- 2026-10：评审 `waived` 豁免 + 多轮一键确认；驳回置 `failed(REVIEW_REJECTED)`。
- 2026-10：建任务先澄清 `pending_mission`；`auto_review` 后台轮询门禁。
- 2026-10：运行时契约 Pydantic；JSON Schema 文件仅文档；7 工具 C1~C7，公式版本化，计算记录存完整输入输出。

## 6. Key facts

- 入口：`app/main.py`、`app/orchestrator/engine.py`、`app/chat/graph.py`、`app/tools/kb/store.py`、`app/validation/rules.py`、`app/tools/doc/render.py`。
- 命令：`make test/run/seed/corpus-fetch`；`cd web && npm run build|dev`。
- 数据：`dev.db`；`artifacts/<task_id>/`（trace.jsonl、citations.json、system-design.json、document-vN.docx、check-report.json）。
- 接口：A1~A17、B1~B5、D1~D12、C1~C9、F1~F5；OpenAPI 0.8.0。
- 测试 98 项；重点 `test_review_flow.py`、`test_chat_agent.py`、`test_kb_scope.py`、`test_ids.py`、`test_formulas.py`。
- 公式：`formula_definitions` / `formula_versions`；安全表达式求值，S5 读自定义覆盖，记录版本带 `+uiN`。
- 文档：README、docs/03/04/07/08/09、ADR-0007。

## 7. Progress

- Current focus：项目稳定，等待下一步需求（可选：RAG 评测/rerank、图片清理）。
- Done:
  - [x] 评审：草案 JSON 编辑、驳回终止、`waived` 豁免、一键确认多轮、`proposed` 不计待处理。
  - [x] RAG：会话+全局范围、召回自适应扩大、切片/检索文档对齐。
  - [x] 编号 max+1；任务删除 A17（级联+制品+事件清理）。
  - [x] 聊天：建任务先澄清、`auto_review`、SSE 流式、记忆/压缩、任务与知识库工具。
  - [x] 聊天可实时查询任务进度/结果（步骤、门禁、参数、校验、文档）。
  - [x] 公式管理：安全表达式编辑、试算、版本历史、恢复默认；S5 支持自定义覆盖。
  - [x] 上下文窗口按 k tokens；S3/S5 空值兜底；重新校验可从 S5 重跑；本地材料（`answer/`）。
- Next:
  - [ ] 如需要：RAG 评测集、rerank/MMR、图片清理。
- Blockers：公式/阈值未经领域审定；`bge-m3` / pgvector 需外部依赖。

## 8. Open questions

- rerank/pgvector/多用户是否引入取决于部署需求；真实公式与阈值需专家审定。
<!-- local-key-memory:end -->

# ADR-0003：存储选型（关系型 + 向量）

| 项目 | 内容 |
|---|---|
| 状态 | 接受 |
| 日期 | 2026-10-05 |
| 决策人 | 项目负责人 |
| 关联 | [04 知识库](../04-knowledge-base.md) · [08 存储](../08-storage.md) |

## 1. 背景与问题

- 需要同时承载：业务数据（任务 / 参数 IR / 校验 / 门禁 / 审计）、语料向量检索、文件制品
- 要求：结构可演进、可回滚、单机可跑、演示可复现

## 2. 备选方案

| 方案 | 描述 | 优点 | 缺点 |
|---|---|---|---|
| A（选定） | Postgres 16 + pgvector（docker compose） | 单组件覆盖关系 + 向量；SQL 过滤与检索同库；迁移路径零成本 | 依赖 Docker |
| B | SQLite + ChromaDB | pip 零依赖、最快跑通 | 双存储一致性差；后期迁移 |
| C | SQLite + sqlite-vec | 单文件最轻 | 生态新、资料少、功能受限 |
| D | 独立向量库（Milvus / Qdrant） | 专业向量能力 | 本量级过重，多一个服务 |

## 3. 决策与理由

- 选择：**Postgres 16 + pgvector**（docker compose 起服务）；SQLAlchemy 2 + Alembic 管 schema；业务表与 `kb_chunks` 同库；artifacts 与 trace 用本地目录
- 理由：
  1. 向量与结构化数据同库，可用 SQL 过滤（分系统 / 年份 / 是否合成）后再检索
  2. pgvector 的 HNSW 索引在本项目量级（万级 chunk）绰绰有余
  3. 避免双存储的一致性维护；备份 / 快照一次完成（`pg_dump` + artifacts 打包）
- 明确放弃：多数据库组件、云托管数据库（演示单机优先）

## 4. 影响

- 开发与演示环境需要 Docker；CI 需要 PG service 容器
- 万级以上 chunk 或高并发时，重新评估索引参数或独立向量库
- 若最终无法使用 Docker，可降级 SQLite + Chroma（接口层已按 Repository 模式隔离，迁移成本可控）

## 5. 参考

- [08 数据与存储设计](../08-storage.md) · [collection-checklist.md](../collection-checklist.md)

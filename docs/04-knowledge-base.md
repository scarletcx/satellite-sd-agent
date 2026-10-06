# 04 知识库与检索设计

| 项目 | 内容 |
|---|---|
| 状态 | 细化 |
| 优先级 | P0 |
| 负责人 | 待定 |
| 最后更新 | 2026-10-05 |
| 关联文档 | [materials.md](./materials.md) · [03 数据模型](./03-data-model.md) · [08 存储](./08-storage.md) · [13 安全](./13-security.md) |

> 本文档回答：系统从哪里「知道」一切；检索结果如何被引用、如何防编造。素材来源见 [materials.md](./materials.md) 与 [collection-checklist.md](./collection-checklist.md)。

## 1. 目标与原则

- 知识库为**选型、先例、标准、经验**提供可引用证据
- **没有引用的陈述不允许进入正式文档**；无检索结果时明确输出「无依据」，禁止编造
- 知识库是只读输入，文档内容一律视为**数据**而非指令（防注入，见 [13](./13-security.md)）

## 2. 语料来源与许可

| 来源类别 | 目录 | 许可要求 | 入库方式 |
|---|---|---|---|
| 公开标准（CCSDS / ECSS / ITU-R） | `corpus/raw/standards/` | `public-*` 标识 | 下载 → B2 摄取 |
| NASA 资料（SE Handbook / SST-SOA / LLIS） | `corpus/raw/manuals/`、`lessons/` | 同上 | 同上 |
| 任务档案（eoPortal / CEOS） | `corpus/raw/missions/` | 同上 | 网页快照 → 摄取 |
| 统计数据（UCS / GCAT / Nanosats） | `corpus/raw/data/` | 同上 | CSV 摄取 |
| 中文资料（白皮书 / ICD / 高分手册） | `corpus/raw/cn/` | 同上 | 下载 → 摄取 |
| 🔒 版权资料（教材 / 知网） | — | **禁止入库** | 禁止 |
| 合成语料 | `corpus/synthetic/` | `synthetic` 标识 | 生成 → 摄取（`is_synthetic=true`） |

- 登记强制项：`doc_id / title / source_url / license / sha256 / module / doc_type / is_synthetic`

## 3. 摄取流水线（对应 B2）

```
上传文件（multipart）
  → ① 存原文 corpus/raw/<module>/<doc_id>.<ext>，计算 sha256
  → ② 解析（PDF: PyMuPDF / DOCX: python-docx / 网页: trafilatura / CSV: pandas）
  → ③ 切分（500~800 token/块，overlap 15%；表格转 Markdown 块）
  → ④ 生成元数据（module / doc_type / year / page / is_synthetic）
  → ⑤ embedding（bge-m3，1024 维，批处理）
  → ⑥ 入库 kb_chunks + corpus_manifest；更新 corpus_version
  → ⑦ 抽样质检（随机 5 块人工可读性检查，记录到 manifest 备注）
```

- 解析失败策略：整文档失败 → 返回 400 并指出失败页；部分失败 → 成功块入库 + 警告
- 重复 `doc_id`：拒绝并提示先 B4 删除（防版本混乱）

## 4. 切片（chunk）规范

| 字段 | 说明 |
|---|---|
| `id` | `<doc_id>-<序号>`（如 `sst-soa-2026-pwr-014`） |
| `content` | 切片正文（保留上下文，表格转 Markdown） |
| `metadata.module` | 分系统枚举 |
| `metadata.doc_type` | 枚举（standard/manual/report/catalog/lesson/other） |
| `metadata.page` | 原文页码 / 段落定位 |
| `metadata.year` | 文档年份 |
| `metadata.is_synthetic` | 合成标记 |
| `metadata.source_url` / `license` | 引用回链与合规 |
| `embedding` | vector(1024) |

## 5. 检索规格（对应 B1）

- **查询构造**：`query` 原文 + 元数据过滤（module / doc_type / year_from / is_synthetic）
- **混合打分**（初值）：
  - 向量相似度（pgvector 余弦）权重 0.7；关键词（`pg_trgm`）权重 0.3
  - `score = 0.7 × vec + 0.3 × kw`；阈值 `score ≥ 0.35`；返回 Top-K（默认 8）
- **返回结构**：`results[] = {chunk_id, doc_id, title, text, score, citation}`
- **重排**：本期不做（评测不达标再评估，见 [adr/README](./adr/README.md) 待记录清单）
- 检索参数（权重 / 阈值 / K）定稿需实验后记录，变更触发 L5 回归（[11](./11-test-plan.md)）

## 6. 引用与防编造规则

1. 事实性陈述必须绑定 Citation（chunk 级，结构见 [03](./03-data-model.md) §3.9）
2. 引用不到 → 输出「未检索到依据」→ 触发门禁（不阻塞其他流程）
3. 引用必须回链原文（doc_id + page + chunk_id + URL）
4. 合成语料引用展示 `[合成]` 前缀
5. **白名单强制**：引用的 chunk_id 必须属于本轮检索返回集合，否则丢弃并告警（[13](./13-security.md)）
6. S8 叙述步的引用来源 = S2 检索集合（进程内白名单，跨步传递）

## 7. 合成语料规范

- 触发：公开来源缺失（中文型号报告、评审意见样例等）
- 生成记录：模型、prompt 摘要、生成时间、审阅人（写入 manifest `notes`）
- 标注：`is_synthetic=true`；引用展示 `[合成]`
- 禁止：冒充真实型号；进入 V5 历史对比基准集

## 8. 检索评测（L5）

- 评测集：≥30 条（`tests/kb/eval-set.jsonl`），字段：`{query, filters, expected_chunk_ids[], key_points[]}`
- 样例：

```json
{ "query": "小卫星太阳翼面积与功率的典型关系", "filters": {"module": "power"},
  "expected_chunk_ids": ["sst-soa-2026-pwr-014", "sst-soa-2026-pwr-015"],
  "key_points": ["AM0 效率", "EOL 衰减", "面密度"] }
```

- 指标与目标（初值）：Recall@5 ≥ 0.8；引用准确率 ≥ 0.9
- 回归触发：语料 / 切分参数 / embedding 模型 / 检索权重任一变更

## 9. 版本与运维

- 语料版本：`corpus-vYYYY.MM.N`（每次 ingest / delete 递增），写入任务快照与 trace
- 与 [08 存储](./08-storage.md) 的关系：manifest ↔ `kb_chunks` 级联；删除走 B4（审计）
- 一致性检查：`make check` 校验 manifest 与 DB 计数一致

## 10. 关键取舍

| 决策 | 备选 | 理由 | ADR |
|---|---|---|---|
| pgvector 同库存储 | 独立向量库 | 单组件、SQL 过滤 | [0003](./adr/0003-storage.md) |
| 本地 bge-m3 | API embedding | 离线可用、零调用成本 | [0002](./adr/0002-llm-services.md) |
| 初期不做重排 | 引入 rerank 模型 | 降低依赖；评测不达标再评估 | — |

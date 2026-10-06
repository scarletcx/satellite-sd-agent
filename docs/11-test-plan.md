# 11 验证与测试计划

| 项目 | 内容 |
|---|---|
| 状态 | 细化 |
| 优先级 | P0 |
| 负责人 | 待定 |
| 最后更新 | 2026-10-05 |
| 关联文档 | [06 校验](./06-calculation-verification.md) · [01 范围](./01-scope-requirements.md) · [05 编排](./05-agent-orchestration.md) |

> 双重目的：工程质量保障 + 评审现场演示（黄金 / 对抗用例可当场跑）。本文档细化到「用例步骤 + 断言 + 桩管理」。

## 1. 测试分层与运行入口

| 层 | 对象 | 方式 | 通过标准 | 入口 |
|---|---|---|---|---|
| L1 单元 | C1~C7 计算、V1~V7 规则、单位换算 | pytest + 黄金数据 | 全绿 | `make test-unit` |
| L2 契约 | 工具 JSON Schema、OpenAPI 一致性 | schema 校验 | 全绿 | `make test-contract` |
| L3 集成 | S1~S10（LLM 桩回放） | 固定输入 → trace 快照比对 | 快照一致 | `make test-int` |
| L4 端到端 | 任务书 → Word | E2E-01~05 | 文档自检全过 | `make test-e2e` |
| L5 检索 | `kb.search` | 评测集（≥30 条） | Recall@5 ≥0.8、引用准确率 ≥0.9 | `make test-kb` |
| L6 LLM 契约 | 各 LLM 步 | 解析成功率统计 | 修复后失败率 <5% | CI 统计 |

## 2. LLM 桩管理（可复现的关键）

- 目录：`tests/fixtures/llm/<step>/<input_hash>.json`（`input_hash` = 规范化输入的 sha256）
- 录制：`make record-llm CASE=E2E-01`（真实调用一次并落桩，人工检查后入库）
- 回放：`STUB_LLM=1`（CI 默认）；未命中桩 → 明确失败（不允许静默真调）
- 桩变更 = 测试数据变更，需评审；桩内记录 `provider/model/prompt_version`（防换模型不换桩）

## 3. 黄金用例集

> 用例文件：`tests/e2e/cases/E2E-0x.json`（输入任务书）+ `expects.json`（断言与期望区间）。
> **期望数值区间由独立手算 / 公开资料得出后填入**（禁止用系统自身输出当期望）。

### E2E-01 500km SSO 光学遥感小卫星

| 断言项 | 方法 | 期望 |
|---|---|---|
| 流程完成 | A3 状态 | `succeeded`（含 1 次门禁通过） |
| 文档产出 | A10 | 200 + docx；`check-report.status=pass` |
| 占位符 | check-report | `placeholders_left = 0` |
| 可追溯率 | check-report | `numbers_checked = numbers_traceable` |
| 质量闭合 | V3 evidence | 汇总 − 分项和 ≤ 0.5% |
| 覆盖输出 | `orbit.windows_per_day` | 落入手算区间（待填） |
| 链路余量 | C4 | ≥ 3 dB（待填实际区间） |
| 全文数字 | doc.check | 0 个不可反查数字 |

### E2E-02 GEO 通信卫星（简版）

关键断言：链路余量达标、寿命相关退化（deg^life）参与 EPS 计算、文档含简化模型声明。

### E2E-03 载荷升级冲突

步骤：以 E2E-01 输入为基线，修订分辨率 / 口径 → 期望：V4 触发 warn/block → 门禁处置后重校验 → 状态恢复并重新出稿。

### E2E-04 严格质量包络

步骤：`mass_limit_kg` 压到紧张值 → 期望：明确 warn/block（禁止静默通过）；block 时 A10 返回 409。

### E2E-05 全中文任务书

断言：解析无信息丢失（clarifications 记录完整）；输出文档术语与 [14](./14-glossary.md) 一致（抽样 10 个术语）。

## 4. 对抗用例集

> 注入方式：桩内篡改 / 直接构造 IR（`tests/adversarial/`）；每个用例给出「期望 trace 标记」。

| # | 注入 | 期望行为 | trace 断言 |
|---|---|---|---|
| ADV-01 | S4 桩输出「太阳翼 5.2 m²」且无计算请求 | 拦截 → 走计算 → V2/V3 不一致 → block；A10 409 | `validation{rule=V2/V3,status=block}` |
| ADV-02 | 参数 `unit` 改为 `kW` | V1 block | `validation{rule=V1}` |
| ADV-03 | 预算汇总篡改（≠ 分项和） | V3 block | `evidence.expected≠actual` |
| ADV-04 | S8 引用不在白名单 | 引用被丢弃 + 告警；无依据标记 | `warning= citation_dropped` |
| ADV-05 | S2 返回空 + S8 给具体结论 | 输出「无依据」转门禁；不阻塞其他章节 | `gate{type=assumption_confirm}` |
| ADV-06 | 修改 `cell_efficiency` 后不重算 | 相关参数 `needs_review`（hash 不一致） | `param status=needs_review` |
| ADV-07 | 语料埋入「忽略以上指令…」 | 行为不变 + 注入告警 | `warning=injection_suspected` |

## 5. 验收矩阵

| 验收项（[01](./01-scope-requirements.md) §6） | 用例 | 通过标准 |
|---|---|---|
| A1 完整 Word | E2E-01 | 章节齐全、0 残留、可下载 |
| A2 拦截能力 | ADV-01~07 | 7/7 按期望处理 |
| A3 可追溯 | L4 + trace 抽查 20 个数字 | 100% 可追到来源 |
| A4 演示 | 彩排（[15](./15-demo-script.md)） | 10 分钟内完成，含拦截演示 |
| A5 性能与成本 | E2E-01 计时 / trace 汇总 | ≤10 分钟、≤ ¥3 |

## 6. 回归触发矩阵

| 变更 | 必跑 |
|---|---|
| 公式 / 容差 / 阈值 | L1 + L4（E2E-01/02） |
| 提示词 / 模型版本 | L3 + L4（全部） |
| 语料 / 切分 / 检索参数 | L5 + ADV-04/05 |
| 校验规则 | L1 + ADV 全量 |
| Word 模板 | L4 文档回归（[10](./10-doc-generation.md) §5） |
| 存储 / Schema 迁移 | L1~L5 全量 |

## 7. 关键取舍

| 决策 | 备选 | 理由 | ADR |
|---|---|---|---|
| LLM 桩回放（未命中即失败） | 允许真实调用兜底 | CI 确定性与成本控制 | — |
| 期望值独立手算 | 用系统自身输出 | 防「自证循环」 | [0004](./adr/0004-orbit-computation.md) |
| 对抗用例进入常规回归 | 仅演示时跑 | 拦截能力是本系统核心卖点 | — |

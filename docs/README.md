# 项目文档索引

> 本目录是「AI 卫星总体设计助手」的开发文档集。文档是**开发的输入**，不是完工后的总结。
> 最近更新：2026-10-05 —— P0 文档已细化到「可据此实现」级别（API 细化到 Apifox 可直接手动测试）。

## 文档地图

| 编号 | 文档 | 优先级 | 状态 | 说明 |
|---|---|---|---|---|
| 01 | [需求与范围定义](./01-scope-requirements.md) | P0 | 初稿（稳定） | 做什么、不做什么、验收标准 |
| 02 | [总体设计](./02-overall-design.md) | P0 | 初稿（稳定） | 架构、模块边界、数据流 |
| 03 | [设计参数数据模型（IR）](./03-data-model.md) | P0 | **细化** | 实体字段级定义 + 示例 + 状态机 |
| 04 | [知识库与检索设计](./04-knowledge-base.md) | P0 | **细化** | 摄取流水线、切片、检索规格、评测集 |
| 05 | [Agent 编排与 Prompt 设计](./05-agent-orchestration.md) | P0 | **细化** | S1~S10 逐步契约、工具协议、trace |
| 06 | [计算与校验引擎设计](./06-calculation-verification.md) | P0 | **细化** | C1~C7 公式级、V1~V7 规则级、对抗用例 |
| 07 | [后端接口文档](./07-api.md) | P0 | **细化（Apifox 可用）** | 字段级参数、示例、业务逻辑、错误码、SSE |
| 08 | [数据与存储设计](./08-storage.md) | P0 | **细化** | 列级表设计、索引、pgvector、备份 |
| 09 | [前端开发文档](./09-frontend.md) | P1 | **细化** | 页面级规格、SSE 模块、验收点 |
| 10 | [Word 生成与模板规范](./10-doc-generation.md) | P1 | **细化** | 章节级占位符、自检清单、回归 |
| 11 | [验证与测试计划](./11-test-plan.md) | P0 | **细化** | 用例级步骤与断言、桩管理、回归矩阵 |
| 12 | [部署与运行环境](./12-deployment.md) | P1 | **细化** | .env 全表、模型配置、make 脚本 |
| 13 | [安全与提示注入防护](./13-security.md) | P1 | **细化** | 防护实现、注入样本、审计示例 |
| 14 | [术语表](./14-glossary.md) | P2 | **细化** | 38 条，约束 Prompt 与数据模型 |
| 15 | [演示脚本](./15-demo-script.md) | P1 | **细化** | 分钟级时间轴、回退链、彩排清单 |
| ADR | [决策记录](./adr/README.md) | — | 持续 | 0001~0005 已记录 |

参考资料（外部素材）：[materials.md](./materials.md) · [collection-checklist.md](./collection-checklist.md)

## 写作规范

1. **固定结构**：元信息表 → 正文 → 「关键取舍」段；重大取舍另开 ADR。
2. **单一事实源**：接口 → `specs/openapi.yaml`（由 [07](./07-api.md) 生成）；数据结构 → `specs/schemas/*.json`；公式 → 文档与代码互相引用。
3. **图表**：统一 mermaid。
4. **状态流转**：初稿 → 细化 → 评审中 → 冻结；冻结后变更走 ADR。

## 文档与关键问题的对应

| 文档 | 支撑的问题 |
|---|---|
| 01 | 第一阶段目标（做什么 / 不做什么） |
| 02 | 任务拆解（哪些给模型、哪些给程序） |
| 05 | 系统内部流程 |
| 06 + 11 | 如何证明系统输出是对的 |
| 03 + 06 + 07 | 无出处数字的处理逻辑 |

## 下一步（按依赖排序）

1. ✅ `specs/openapi.yaml` + `specs/schemas/*.json` 已生成（openapi.yaml 可直接导入 Apifox）
2. ✅ `app/` 骨架：编排 S1~S9 + C1~C3 计算 + V1/V3/V4 校验 + 桩模式
3. ✅ docx 渲染（docxtpl）与 A10 下载已接入；模板可用 `make template` 重新生成
4. ✅ 知识库模块：摄取 / 混合检索 / 引用（S2 → Word 附录）；开发版 embedding 与存储，pgvector + bge-m3 为下一步
5. ✅ LLM 适配层：DeepSeek → Qwen → OpenAI → Claude → Ollama 降级链 + 提示词文件化 + 修复重试 + 用量/成本记账
6. ✅ 前端（React + AntD）：任务 / Trace（SSE）/ 评审门禁 / 文档 / 知识库，浏览器端到端验收通过
7. ✅ 计算与校验补全：C4 链路 / C5 轨道覆盖 / C6 太阳翼；**V1~V7 校验全部实现**（V2 独立重算 / V5 UCS 参考分布 / V6 敏感性）
8. ✅ 运维脚本：`make seed` / `make demo-adv`（拦截演示）/ `make reference` / `make snapshot` / `make cost-report`；成本上限守卫
9. ✅ 供应商注册表 + 前端「设置」页（任意第三方，保存即生效，ADR-0006）；**真实 Key 联调完成**（第三方网关：4 次调用 / ¥0.43 / 91-91 可追溯）
10. ✅ 任务级模型选择（A1 `provider_id`）、执行进度与过程提示（含门禁暂停态）、Word 在线预览（A13 docx→HTML）
11. 下一步：bge-m3 + pgvector；语料采集按 [collection-checklist.md](./collection-checklist.md) 执行

## 待确认事项

- [ ] 黄金用例期望数值区间（独立手算后填入 [11](./11-test-plan.md)）
- [ ] 交叉验证库三选一（brahe / tudatpy / skyfield，[ADR-0004](./adr/0004-orbit-computation.md)）
- [ ] 切分与检索参数定稿（[04](./04-knowledge-base.md) §5，实验后开 ADR）
- [ ] 模型名与配额核对（[12](./12-deployment.md) §3）

# ADR-0002：LLM 服务与嵌入模型

| 项目 | 内容 |
|---|---|
| 状态 | 接受 |
| 日期 | 2026-10-05 |
| 决策人 | 项目负责人 |
| 关联 | [05 编排](../05-agent-orchestration.md) · [12 部署](../12-deployment.md) |

## 1. 背景与问题

- 需求：中文能力强、支持结构化输出（JSON）、成本可控、可离线演示、多供应商可切换
- 风险：单一供应商限流 / 涨价 / 断供会直接中断演示

## 2. 备选方案

| 方案 | 描述 | 优点 | 缺点 |
|---|---|---|---|
| A（选定） | 自研薄适配层 + 多供应商降级 | 可控、无重依赖、离线兜底 | 需维护少量 provider 差异 |
| B | 仅 DeepSeek 直连 | 最简单 | 无降级、离线不可用 |
| C | LiteLLM 等统一网关 | 多供应商开箱即用 | 重依赖、抽象泄漏、额外调试成本 |
| D | 嵌入用 API（如 Qwen text-embedding-v3） | 免本地部署 | 离线不可用、按量计费 |

## 3. 决策与理由

- 适配层统一接口：`chat()` / `chat_json()` / `stream()`，provider 由配置驱动
- 降级顺序：**DeepSeek → 通义千问 Qwen → OpenAI / Claude → 本地 Ollama（离线）**
- 结构化输出策略：优先进 provider 原生 JSON 模式（DeepSeek / Qwen 支持）；不支持的走「提示约束 + 解析 + 修复重试」
- Embedding：**本地 BGE（bge-m3，1024 维）**，经 sentence-transformers；保留 API 嵌入适配口
- 温度策略：参数 / 结构化步 ≤ 0.2；叙述步 ≤ 0.6（按步骤记录于 [05](../05-agent-orchestration.md)）
- 具体模型名与版本以账号开通为准，登记到 [12](../12-deployment.md)；**模型版本必须写入 trace 与任务快照**

## 4. 影响

- 需维护各 provider 差异点：JSON 模式支持度、限流语义、超时、计费口径
- 离线演示依赖 Ollama 与本地模型可用性（演示前必须实测性能）
- 后续 provider 超过 5 家时，重新评估是否引入统一网关

## 5. 参考

- [materials.md](../materials.md) · [12 部署与运行环境](../12-deployment.md)

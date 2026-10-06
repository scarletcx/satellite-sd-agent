# ADR-0006：LLM 供应商注册表与运行时设置

| 项目 | 内容 |
|---|---|
| 状态 | 接受 |
| 日期 | 2026-10-06 |
| 决策人 | 项目负责人 |
| 关联 | [ADR-0002](./0002-llm-services.md) · [07 接口](../07-api.md) · [12 部署](../12-deployment.md) |

## 1. 背景与问题

- 原实现只有 5 个固定槽位（DeepSeek/Qwen/OpenAI/Claude/Ollama），第三方 OpenAI 兼容服务（聚合网关、国产平台兼容模式、自建 vLLM）只能"借槽位"，且 `json_mode` 按槽位写死、数量不可扩展；
- 需要在前端设置页直接修改 `base_url / api_key / model`，保存后立即生效，无需改环境变量与重启。

## 2. 备选方案

| 方案 | 描述 | 优点 | 缺点 |
|---|---|---|---|
| A（选定） | 供应商注册表 + 运行时覆盖（存本地 DB，前端可编辑） | 任意数量、第三方一等公民、保存即生效 | 密钥落本地库（演示级）；多一层配置合并逻辑 |
| B | 仅扩展环境变量（每加一家改 .env 重启） | 简单 | 不满足"前端可改"，运维体验差 |
| C | 前端保存配置并在每次请求携带 | 后端无状态 | 密钥暴露在浏览器；接口复杂化；无法用于后台任务 |

## 3. 决策与理由

- 注册表模型 `ProviderSpec`：`id / label / protocol(openai|anthropic) / base_url / model / api_key / json_mode / enabled / keyless / timeout_s / price_in / price_out`，数量不限，列表顺序即降级顺序；
- 配置优先级：**运行时（DB，前端可改，立即生效）> 环境变量 > `config/llm.json` > 内置默认**（向后兼容纯 env 部署）；
- 新增设置接口：`GET/PUT/DELETE /settings/llm`、`POST /settings/llm/probe`（拉取 `/models` 列表）、`POST /settings/llm/test`（最小真实调用）；
- 密钥处理：GET 一律掩码返回；PUT 省略 `api_key` 表示保留原值；密钥仅存本机（本地 SQLite，明文，演示级——生产应替换为密钥管理服务）；
- 桩模式判定改为动态：`STUB_LLM` 显式设置优先，否则「无可用供应商 → 桩模式」。

## 4. 影响

- 前端新增「设置」页：可视化增删/排序供应商、"拉取模型"下拉选型、"测试"连通性；
- 实测：第三方网关（`aiapi.c0c.cc`，`gpt-5.6-sol`）完成真实全链路任务——4 次 LLM 调用、成本 ≈¥0.43、`check-report` 91/91 数字可追溯；
- 遗留：多用户与权限（当前单用户演示级）、密钥加密存储、按步骤绑定不同模型（当前每供应商一个模型）。

## 5. 参考

- [ADR-0002 LLM 服务与嵌入模型](./0002-llm-services.md) · [docs/12 §3](../12-deployment.md)

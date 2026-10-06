# 12 部署与运行环境

| 项目 | 内容 |
|---|---|
| 状态 | 细化 |
| 优先级 | P1 |
| 负责人 | 待定 |
| 最后更新 | 2026-10-05 |
| 关联文档 | [08 存储](./08-storage.md) · [07 接口](./07-api.md) · [adr/0002](./adr/0002-llm-services.md) |

> 目标：一条命令起服务 + 可复现演示。形态：本地单机（应用本地运行，Postgres 走 docker compose）。

## 1. 环境与组件版本

| 组件 | 版本 / 形态 | 说明 |
|---|---|---|
| Python | 3.11+（uv 管理） | `uv sync` 安装依赖 |
| Node.js | 20+（pnpm） | 前端构建 / dev |
| Postgres | 16 + pgvector（镜像 `pgvector/pgvector:pg16`） | docker compose |
| 后端 | FastAPI（uvicorn，本地运行） | `make up` 启动 |
| 前端 | Vite dev / 静态构建 | `pnpm dev` |
| Embedding | bge-m3（sentence-transformers 本地） | 首启加载，约需显存/内存 1~2GB |

## 2. 配置与密钥（`.env` 全表）

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `APP_ENV` | ❌ | `dev` | `dev` / `prod`；`dev` 才启用调试工具入口 |
| `APP_TOKEN` | ✅ | — | API 鉴权 Token（[07](./07-api.md) §1.2） |
| `DATABASE_URL` | ✅ | — | `postgresql+psycopg://app:app@localhost:5432/satellite` |
| `DEEPSEEK_API_KEY` | ✅* | — | 主力模型（*`STUB_LLM=1` 时可不填） |
| `DASHSCOPE_API_KEY` | ❌ | — | Qwen（第一备选） |
| `OPENAI_API_KEY` | ❌ | — | 第二备选 |
| `ANTHROPIC_API_KEY` | ❌ | — | 第二备选 |
| `OLLAMA_HOST` | ❌ | `http://localhost:11434` | 离线兜底 |
| `EMBEDDING_MODEL` | ❌ | `bge-m3` | 本地 embedding |
| `STUB_LLM` | ❌ | `0` | `1` = 桩回放（CI / 离线演示） |
| `COST_LIMIT_CNY` | ❌ | `3` | 单任务成本上限 |
| `LOG_LEVEL` | ❌ | `INFO` | 应用日志级别 |

- 密钥只经环境变量注入；`.env` 在 `.gitignore`；提供 `.env.example`
- 启动时校验：`APP_TOKEN` / `DATABASE_URL` 必填；`STUB_LLM=0` 时至少一个 LLM Key 必填

## 3. 模型与降级配置（注册表，ADR-0006）

- 供应商注册表：`config/llm.json`（随仓库，无密钥）+ 环境变量覆盖 + **运行时设置（DB，前端「设置」页可改，保存即生效）**
- 配置优先级：**运行时 > 环境变量 > `config/llm.json` > 内置默认**；列表顺序即降级顺序
- 供应商字段：`id / label / protocol(openai|anthropic) / base_url / model / api_key / json_mode / enabled / keyless / timeout_s / price_in / price_out`
- 第三方接入：任意 OpenAI 兼容端点（聚合网关 / 国产平台兼容模式 / 自建 vLLM）直接添加；端点不支持 `response_format` 时关闭 `json_mode` 即可
- 环境变量（可选，无 UI 部署方式）：`LLM_ORDER`（按 id 过滤/重排）、`LLM_TIMEOUT_S`、`PRICE_<ID>_IN/OUT`，以及 `*_API_KEY / *_BASE_URL / *_MODEL`
- 密钥：运行时密钥存于本地数据库（演示级明文；生产应接密钥管理服务）；接口返回一律掩码
- **实际模型版本写入 trace 与任务快照**（ADR-0002）；降级触发：超时 / 限流 / 5xx → 顺位切换

> 实测记录（2026-10-06）：第三方网关 `aiapi.c0c.cc` 以 `gpt-5.6-sol` 完成整条任务
> （S1/S3/S4/S8 四次真实调用、成本 ≈¥0.43、`check-report` 91/91 数字可追溯；同网关其他模型当时存在 429/502，降级链可按需配置多家）。

## 4. 成本与配额

- 记账公式：`cost = tokens_in × price_in + tokens_out × price_out`（单价表 `config/pricing.yaml`，以官方价目更新）
- 单任务上限 `COST_LIMIT_CNY`（默认 ¥3）：80% 告警、100% 挂起重试需人工放行
- 汇总入口：`artifacts/<task_id>/trace.jsonl` → `make cost-report`（可选脚本）

## 5. 日志与可观测性

| 输出 | 位置 | 内容 |
|---|---|---|
| trace | `artifacts/<task_id>/trace.jsonl` | 每步记录（[05](./05-agent-orchestration.md) §7） |
| 应用日志 | `logs/app.log`（按天轮转，保留 7 天） | 结构化 JSON：ts / level / module / msg / trace_id |
| 审计 | Postgres `audit_log` | 写操作（who/what/why） |

- 演示面板：前端 P2（Trace 页）现场回放；`make demo-adv` 跑拦截演示

## 6. 可复现性清单

| 项 | 记录位置 |
|---|---|
| Python / Node 版本 | `uv.lock` / `pnpm-lock.yaml` + `.python-version` |
| 语料版本 | `corpus-vYYYY.MM.N`（missions 表 + trace） |
| 模型版本 | `missions.model_versions` + trace |
| 提示词版本 | trace `prompt_version` |
| 模板版本 | `missions.template_version` |
| 随机性 | 温度固定（[05](./05-agent-orchestration.md) §2）；支持处固定 seed |

- 任务快照（`make snapshot TASK=<id>`）：IR + trace + 语料版本 + 模型版本 + 模板版本 + docx

## 7. Make 脚本（运维入口）

| 目标 | 动作 |
|---|---|
| `make up` | compose 起 DB → `alembic upgrade head` → 启动后端（前台） |
| `make down` | 停止后端与 DB |
| `make seed` | 建表检查 + 导入语料 manifest + 黄金用例 + 录制桩 |
| `make check` | 健康检查（DB / embedding / provider 配置）+ manifest 与 DB 计数一致 |
| `make test*` | L1~L5 分层测试（[11](./11-test-plan.md) §1） |
| `make record-llm CASE=E2E-01` | 录制 LLM 桩 |
| `make demo-adv` | 运行对抗用例 ADV-01（拦截演示） |
| `make snapshot TASK=<id>` | 导出任务全量快照 |
| `make cost-report` | 汇总指定任务的成本 |

## 8. 启动 / 停止 / 排障

```bash
cp .env.example .env        # 填 APP_TOKEN 与 API Key
make up                     # 起服务
make check                  # 确认各依赖连通

# 常见问题
# - embedding 加载慢：首次下载模型，预热后再演示
# - DB 端口占用：compose 端口映射改为 5433 并同步 DATABASE_URL
# - 全 provider 失败：STUB_LLM=1 切桩模式（演示回退，[15](./15-demo-script.md) §5）
```

## 9. 关键取舍

| 决策 | 备选 | 理由 | ADR |
|---|---|---|---|
| 应用本地 + DB compose | 全 compose / 云 | 演示优先、调试快 | [0001](./adr/0001-tech-stack.md) |
| 桩模式一等公民 | 仅真实调用 | 演示回退与 CI 确定性 | [0002](./adr/0002-llm-services.md) |
| 供应商运行时注册表（前端可改） | 固定 5 槽位 / 仅环境变量 | 第三方接入无需改配置与重启 | [0006](./adr/0006-llm-provider-registry.md) |

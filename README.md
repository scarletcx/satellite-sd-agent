# AI 卫星总体设计助手（satellite-sd-agent）

> 输入任务书 → 输出可复核的整星设计方案：**数字全部来自确定性计算，全链路可追溯、可回放**。
> 当前状态：**全链路可运行原型（v0.4）**。S1~S9 编排链路完整贯通；C1~C6 确定性计算（质量、功耗、数据量、轨道覆盖、测控链路、太阳翼面积）、V1~V7 校验规则全部真实实现；基于 docxtpl 的 Word 文档自动渲染、下载与在线预览；知识库（解析、切片、向量摄取、混合检索、引用溯源）；LLM 适配层支持任意第三方 OpenAI / Anthropic 兼容网关与本地 Ollama，前端设置页支持热修改 URL、Key 与模型并实时生效；React + Ant Design 前端支持任务级模型选择、执行过程进度与提示、参数评审门禁及文档在线预览。已基于真实第三方网关完成全链路联调与验证。

## 快速开始

```bash
# 1) 安装（无 uv 环境，使用 venv + pip）
make install

# 2) 运行（默认 SQLite；「设置」页配置 Key 后即接入真实模型，未配置时自动进入桩模式）
cp .env.example .env        # 可选：修改 APP_TOKEN
make run                    # http://127.0.0.1:8000 ，接口文档 /docs

# 3) 测试
make test                   # 单元 + 流水线 + API 冒烟（41 个用例全部通过）

# 4) 常用脚本
make seed                   # 导入种子语料（幂等）
make demo-adv               # ADV-01 拦截演示：无计算依据的数字被校验层拦下（导出返回 409）
make reference              # 生成 V5 历史对比参考分布（基于 UCS 公开卫星数据）
make snapshot TASK=<task_id>    # 导出任务全量快照（zip）
make cost-report TASK=<task_id> # 任务成本与 Token 用量报告

# 5) 前端（/api 已代理到 8000）
cd web && npm install && npm run dev    # http://localhost:5173
```

## 冒烟演示（全链路运行）

```bash
TOKEN=dev-token-change-me
BASE=http://127.0.0.1:8000/api/v1

curl -s $BASE/healthz | python3 -m json.tool

# 创建任务（支持通过 provider_id 指定供应商，留空则走设置页降级链）
curl -s -X POST $BASE/missions \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"goal":"设计一颗 500km SSO 光学遥感小卫星",
       "constraints":{"orbit_type":"SSO","altitude_km":500,"lifetime_years":3,"mass_limit_kg":80}}'

# 用返回的 task_id 查看进度 / 参数 / 校验报告 / trace / 在线预览
curl -s $BASE/missions/<task_id> -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s $BASE/missions/<task_id>/parameters -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s $BASE/missions/<task_id>/check-report -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s $BASE/missions/<task_id>/document/preview -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 门禁演示：当 mass_limit_kg 设为 70 时，质量超限触发 V4 阻断，任务停在 awaiting_gate，
# 工程师在参数列表评审 mass.total_with_margin，通过接口签批后任务自动恢复并完成出稿：
curl -s -X POST $BASE/missions/<task_id>/parameters/mass.total_with_margin/review \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"action":"accept","reviewer":"engineer@example.com","comment":"接受超限，转入结构轻量化设计"}'
```

## 知识库（摄取 / 检索）

```bash
# 摄取（multipart；支持 pdf / docx / txt / md / csv）
curl -s -X POST $BASE/kb/ingest -H "Authorization: Bearer $TOKEN" \
  -F "file=@tests/fixtures/kb/power.txt" \
  -F "module=power" -F "doc_type=report" -F "license=synthetic" \
  -F "is_synthetic=true" -F "title=电源分系统样例（合成）"

# 检索（混合：向量 + 关键词）
curl -s -X POST $BASE/kb/search -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"太阳翼面积与电池容量如何估算","top_k":5}'

# 统计 / 列表 / 删除
curl -s $BASE/kb/stats -H "Authorization: Bearer $TOKEN"
curl -s "$BASE/kb/documents?module=power" -H "Authorization: Bearer $TOKEN"
curl -s -X DELETE "$BASE/kb/documents/<doc_id>?confirm=true" -H "Authorization: Bearer $TOKEN"
```

## 目录结构

```
app/
  api/            # 对外接口层（FastAPI 路由：任务、参数评审、文档导出/预览、知识库、模型设置）
  orchestrator/   # 状态机 S1~S9 编排引擎与 SSE 实时事件总线
  steps/          # 各步骤业务逻辑（S1~S9 全链路串联）
  tools/calc/     # 确定性计算核心：C1 质量、C2 功耗、C3 数据量、C4 链路、C5 轨道覆盖、C6 太阳翼
  tools/kb/       # 知识库工具链：文档解析、文本分块、Embedding 向量化、混合检索
  tools/doc/      # Word 渲染与报告自检：docxtpl 动态注入与数字反向溯源查证
  validation/     # 一致性校验引擎：V1 溯源、V2 独立复算、V3 闭合、V4 约束、V5 历史分布、V6 敏感性、V7 假设
  providers/      # LLM 适配层：动态供应商注册表、降级链路由、提示词加载、用量与成本记账
  models.py       # 数据库实体定义（SQLAlchemy ORM）
prompts/          # 版本化提示词文件（S1/S3/S4/S8 及安全护栏）
templates/        # 12 章 Word 技术规范模板（通过 make template 自动化生成）
specs/            # 契约中心：OpenAPI 3.0 接口规范与 17 个 JSON Schema
docs/             # 系统工程开发文档集（01~15 架构文档与 ADR 决策记录）
tests/            # 自动化测试集（单元测试、流水线测试、API 冒烟、攻击拦截与设置管理）
artifacts/        # 任务运行产物存档（Word 方案文档、反向校验报告、全量执行 trace.jsonl）
```

## 当前实现与后续生产演进

| 模块 | 当前实现（工程原型 demo） | 生产落地演进目标 |
|---|---|---|
| 数据库存储 | 本地 SQLite（支持通过环境变量无缝切换 PostgreSQL） | PostgreSQL 16 + pgvector 原生扩展（docs/08） |
| 文本向量检索 | 开发级轻量向量计算与余量检索存储 | 本地部署 bge-m3 深度语义模型 + pgvector 混合检索（docs/04） |
| 大语言模型 | 支持任意第三方网关与本地模型接入，前端设置页热修改，具备自动降级链、用量审计与任务级指定模型功能，已调通真实 API | 生产环境私有化高可用模型集群与专网网关路由（ADR-0002 / ADR-0006） |
| 确定性计算 | C1~C6 全部实现，包含质量、功耗、数据量、链路余量、轨道覆盖及太阳翼推导 | 引入高精度轨道力学开源库（如 brahe）实现双路交叉数值复核（ADR-0004） |
| 一致性校验 | V1~V7 规则集全部落地，包含双算法独立复算、UCS 历史基线比对、硬约束阻断与敏感性分析 | 扩展更多分系统（姿控、热控）的详细物理闭合约束与经验数据库 |
| 文档与自检 | 自动化生成 12 章 Word 技术方案，支持网页端在线富文本预览与下载，自检脚本校验 92 处数值 100% 可追溯 | 针对型号编制规范增加复杂图表公式与排版样式定制 |
| 人机交互界面 | 基于 React 18 + AntD 5 构建，支持模型选择、实时进度与过程提示、参数评审门禁及文档在线预览 | 完善多任务协同看板与企业级权限审计体系（docs/09） |

## 工程约定

- 接口与实体以 `specs/` 为单一事实源；调整接口需先同步 `docs/07-api.md`
- 所有任务的运行产物（trace、Word、自检报告）严格持久化于 `artifacts/<task_id>/`，支持全过程回放
- 自动化校验期望值独立制定，禁止使用大模型自身生成的数值作为测试真值（docs/11 §7）

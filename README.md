# AI 卫星总体设计助手（satellite-sd-agent）

> 输入任务书 → 输出可复核的整星设计方案：**数字全部来自确定性计算，全链路可追溯、可回放**。
> 当前状态：**骨架阶段（v0.1）**——S1~S9 编排链路已可运行；C1~C6 计算（质量/功耗/数据量/轨道覆盖/链路/太阳翼）、V1/V3/V4/V7 校验、docx 渲染与下载、知识库（摄取/检索/引用）、LLM 适配层（降级链/提示词/修复重试/成本记账）、前端（React + AntD）为真实实现；未配置 API Key 时自动进入桩模式。真实 Key 联调与 bge-m3/pgvector 为下一步。

## 快速开始

```bash
# 1) 安装（无 uv 环境，使用 venv + pip）
make install

# 2) 运行（默认 SQLite；未配置 LLM Key 时自动进入桩模式）
cp .env.example .env        # 可选：修改 APP_TOKEN
make run                    # http://127.0.0.1:8000 ，接口文档 /docs

# 3) 测试
make test                   # 单元 + 流水线 + API 冒烟（33 个用例）

# 4) 常用脚本
make seed                   # 导入种子语料（幂等）
make demo-adv               # ADV-01 拦截演示：无计算依据的数字被校验层拦下
make reference              # 生成 V5 历史对比参考分布（UCS 公开数据）
make snapshot TASK=<task_id>    # 导出任务全量快照（zip）
make cost-report TASK=<task_id> # 任务成本报告

# 5) 前端（可选；/api 已代理到 8000）
cd web && npm install && npm run dev    # http://localhost:5173（「设置」页可配置第三方大模型）
```

## 冒烟演示（骨架版全链路）

```bash
TOKEN=dev-token-change-me
BASE=http://127.0.0.1:8000/api/v1

curl -s $BASE/healthz | python3 -m json.tool

curl -s -X POST $BASE/missions \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"goal":"设计一颗 500km SSO 光学遥感小卫星",
       "constraints":{"orbit_type":"SSO","altitude_km":500,"lifetime_years":3,"mass_limit_kg":80}}'

# 用返回的 task_id 查看进度 / 参数 / 校验报告 / trace
curl -s $BASE/missions/<task_id> -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s $BASE/missions/<task_id>/parameters -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s $BASE/missions/<task_id>/check-report -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 门禁演示：把 mass_limit_kg 改为 70 → 任务停在 awaiting_gate，
# 在参数列表找到 mass.total_with_margin，执行 A8 评审后自动恢复：
curl -s -X POST $BASE/missions/<task_id>/parameters/mass.total_with_margin/review \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"action":"accept","reviewer":"you@example.com","comment":"接受超限，后续减重"}'
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
  api/            # 对外接口（docs/07）
  orchestrator/   # 状态机 S1~S9 + 事件总线
  steps/          # 每步实现（S5/S6/S9 为真实实现，其余为桩）
  tools/calc/     # 确定性计算 C1~C3
  tools/kb/       # 知识库：解析 / 切片 / embedding / 检索
  tools/doc/      # docx 渲染与自检
  validation/     # 校验规则 V1/V3/V4（骨架）
  providers/      # LLM 适配层（降级链 / 提示词 / 用量记账）
  models.py       # ORM（docs/03 / docs/08）
prompts/          # 提示词（版本化：S1/S3/S4/S8 + safety）
templates/        # Word 模板（make template 再生成）
specs/            # OpenAPI + JSON Schema（单一事实源）
docs/             # 开发文档集（01~15 + ADR）
tests/            # 单元 / 流水线 / API / 知识库 / 适配层
artifacts/        # 运行产物：document / check-report / trace.jsonl
```

## 与文档的差异（骨架阶段已知项）

| 项 | 现状 | 目标（文档） |
|---|---|---|
| 数据库 | 默认 SQLite（`DATABASE_URL` 可切 Postgres） | Postgres 16 + pgvector（docs/08） |
| docx | ✅ 已实现：docxtpl 渲染 `document-v1.docx` + A10 下载（模板经 `make template` 再生成） | docxtpl 渲染 docx（docs/10） |
| LLM | ✅ 适配层 + **供应商注册表**（ADR-0006）：任意 OpenAI 兼容 / Anthropic 第三方；前端「设置」页可改 URL/Key/模型，保存即生效；降级链、提示词文件化、修复重试、用量与成本记账；**已用第三方网关完成真实全链路**（4 次调用、¥0.43/任务、91/91 数字可追溯） | ADR-0002 / ADR-0006 |
| 知识库 | ✅ 已接入：摄取 / 混合检索 / 引用（S2 → 附录引用表）；开发版 embedding（hashing）与 SQLite 向量存储 | pgvector + bge-m3（docs/04） |
| 前端 | ✅ React 18 + Ant Design 5：任务创建（**任务级模型选择**）/ Trace（SSE + **进度条与过程提示**）/ 参数评审门禁 / 文档与校验（**Word 在线预览**）/ 知识库 / 设置；浏览器端到端验收通过 | docs/09 |
| 校验 | ✅ V1~V7 全部实现：V1 单位/溯源/引用完整性、V2 独立重算（六类计算记录 0.5% 容差）、V3 闭合/余量、V4 约束、V5 历史对比（UCS P10~P90，`make reference` 生成）、V6 敏感性、V7 假设台账（warn 级） | docs/06 |

## 开发约定

- 接口/数据结构以 `specs/` 为单一事实源；改接口先改 `docs/07-api.md` 再同步生成物
- 运行产物（trace、文档、校验报告）落在 `artifacts/<task_id>/`，可回放
- 测试期望值必须独立手算（禁止用系统自身输出当期望，docs/11 §7）

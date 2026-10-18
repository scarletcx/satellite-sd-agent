# AI 卫星总体设计助手（个人本地 agent）

> **定位**：单用户、本机运行的个人 agent。会话记忆、聊天记录、知识库与向量索引全部存本地 SQLite；
> 主界面是聊天（Codex 风格），可上传文档做资料问答；复杂设计任务走可审计的任务流水线。
> 工程底线不变：**数字来自确定性计算，可追溯、可回放**。

## 当前能力（v0.7）

- **个人 agent 对话**：多会话（新建 / 切换 / 重命名 / 删除 / 置顶）；
  消息**全量**保存在 SQLite，达到上下文阈值（默认 80%，可在设置页调整/关闭）自动把较早消息折叠为摘要；
  聊天界面实时显示上下文使用率，`/compact` 可手动压缩
- **长期记忆**：跨会话保存用户偏好/习惯（自动抽取 + `/remember`、`/memory`、`/forget`），
  每次对话注入提示词；不保存原始对话
- **聊天内切换模型与推理强度**：会话级供应商 / 模型覆盖 + `low|medium|high` 推理强度（模型支持时透传）
- **逐字输出**：SSE 流式回答（OpenAI 兼容供应商原生 token 流；其他供应商按块下发兜底）
- **文档上传**：pdf / docx / txt / md / csv（≤20MB）+ 图片；`+` 菜单在输入框内；
  附件默认仅本会话可见，聊天里说「存入知识库」或 `/kb store` 提升为全局知识库
- **聊天与任务联动**：对话中可新建任务、查看任务列表/状态、审核参数（接受/驳回/改值），
  也可查询/删除/入库知识库文档；设计任务页面功能完整保留
- **RAG**：`sqlite-vec` 向量索引 + 关键词混合打分；扩展缺失自动回退
- **设计任务流水线**：S1~S9、C1~C7、V1~V7（含 skyfield/SGP4 交叉验证）、输入确认门禁、
  参数评审（接受 / 驳回 / 编辑，**一键确认全部**）、Word 自动渲染（版本递增）与在线预览
- **评审增强**：草案输入可直接改 JSON 后确认；驳回会明确终止任务（不再卡在门禁）；
  修复「任务已完成仍显示待评审」——`proposed` 不再计入待处理，门禁放行后会重跑校验
- **模型与窗口**：聊天内供应商/模型为下拉选择；设置页「拉取模型」会给出各模型的最大上下文窗口参考，
  并可一键填入「上下文窗口」（默认 256k）
- **任务命名**：创建时可命名，列表页可重命名；任务编号使用本地日期
- 测试：**85 个用例全部通过**

## 快速开始

```bash
# 1) 安装（venv + pip；默认 SQLite，无需 Docker）
make install

# 2) 运行（未配置模型时自动进入桩模式）
cp .env.example .env        # 可选：修改 APP_TOKEN
make run                    # http://127.0.0.1:8000 ，接口文档 /docs

# 3) 前端（/api 已代理到 8000）
cd web && npm install && npm run dev    # http://localhost:5173（主页即对话）

# 4) 测试与常用脚本
make test                   # 单元 + 流水线 + API 冒烟（85 个用例）
make seed                   # 导入种子语料（幂等）
make corpus-fetch           # 抓取开放许可语料（NASA 公开文档；产物在 corpus/raw/，不入库）
make demo-adv               # 拦截演示：无计算依据的数字被校验层拦下（导出 409）
make reference              # 生成 V5 历史对比参考分布（UCS 公开数据）
make snapshot TASK=<id>     # 导出任务全量快照（zip）
make cost-report TASK=<id>  # 任务成本与 Token 用量报告
```

## 个人 agent 冒烟（会话 / 上传 / 问答）

```bash
TOKEN=dev-token-change-me
BASE=http://127.0.0.1:8000/api/v1

# 新建会话
SID=$(curl -s -X POST $BASE/chat/sessions -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"title":"资料问答"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 上传会话附件（进入本地知识库，按会话隔离检索）
curl -s -X POST "$BASE/chat/sessions/$SID/documents" -H "Authorization: Bearer $TOKEN" \
  -F "file=@./notes.txt"

# 发消息（返回用户消息 + 助手消息，assistant.meta.citations 为引用）
curl -s -X POST "$BASE/chat/sessions/$SID/messages" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"content":"请检索资料：链路余量要求是多少？"}'

# 斜杠命令：压缩上下文 / 记住偏好 / 任务联动
curl -s -X POST "$BASE/chat/sessions/$SID/messages" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"content":"/compact"}'
curl -s -X POST "$BASE/chat/sessions/$SID/messages" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"content":"/remember 回答先给结论，再给依据"}'
curl -s -X POST "$BASE/chat/sessions/$SID/messages" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"content":"新建任务：设计一颗 500km SSO 光学遥感小卫星"}'

# 流式对话（SSE：user → delta… → done）
curl -N -X POST "$BASE/chat/sessions/$SID/messages/stream" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"content":"你好"}'

# 会话列表 / 消息历史 / 删除会话
curl -s "$BASE/chat/sessions" -H "Authorization: Bearer $TOKEN"
curl -s "$BASE/chat/sessions/$SID/messages" -H "Authorization: Bearer $TOKEN"
curl -s -X DELETE "$BASE/chat/sessions/$SID" -H "Authorization: Bearer $TOKEN"
```

## 设计任务冒烟（全链路）

```bash
# 创建任务（支持 provider_id 指定供应商，留空走设置页降级链）
curl -s -X POST $BASE/missions \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"goal":"设计一颗 500km SSO 光学遥感小卫星",
       "constraints":{"orbit_type":"SSO","altitude_km":500,"lifetime_years":3,"mass_limit_kg":80}}'

# 进度 / 参数 / 校验报告 / trace / 在线预览
curl -s $BASE/missions/<task_id> -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s $BASE/missions/<task_id>/parameters -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s $BASE/missions/<task_id>/check-report -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s $BASE/missions/<task_id>/document/preview -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 门禁：mass_limit_kg=70 时质量超限 → awaiting_gate；签批后自动恢复出稿
curl -s -X POST $BASE/missions/<task_id>/parameters/mass.total_with_margin/review \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"action":"accept","reviewer":"engineer@example.com","comment":"接受超限，转入结构轻量化设计"}'
```

## 知识库（摄取 / 检索）

```bash
curl -s -X POST $BASE/kb/ingest -H "Authorization: Bearer $TOKEN" \
  -F "file=@tests/fixtures/kb/power.txt" \
  -F "module=power" -F "doc_type=report" -F "license=synthetic" \
  -F "is_synthetic=true" -F "title=电源分系统样例（合成）"

curl -s -X POST $BASE/kb/search -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"太阳翼面积与电池容量如何估算","top_k":5}'

curl -s $BASE/kb/stats -H "Authorization: Bearer $TOKEN"   # 含 vector_index / vector_indexed_chunks
```

## 目录结构

```
app/
  chat/           # 个人 agent：LangGraph 编排（graph.py）与会话服务（service.py）
  api/            # 对外接口层（FastAPI：会话、任务、参数评审、文档、知识库、模型设置）
  orchestrator/   # 任务状态机 S1~S9 与 SSE 实时事件总线
  steps/          # 各步骤业务逻辑（S1~S9 全链路串联）
  tools/calc/     # 确定性计算核心：C1 质量、C2 功耗、C3 数据量、C4 链路、C5 轨道覆盖、C6 太阳翼、C7 姿控粗算
  tools/catalog/  # 选型候选规则匹配（示例选型库 data/parts_catalog.json）
  tools/kb/       # 知识库：解析、分块、embedding、sqlite-vec 索引（vec_index.py）、混合检索
  tools/doc/      # Word 渲染与报告自检（docxtpl + 数字反向溯源）
  validation/     # V1~V7 校验 + 轨道交叉验证（orbit_crosscheck.py）
  providers/      # LLM 适配层：供应商注册表、降级链、提示词加载、用量成本记账
  models.py       # ORM：任务 / 参数 / 计算 / 校验 / 门禁 / 会话 / 消息 / 附件 / 知识库
prompts/          # 版本化提示词（S1/S3/S4/S7/S8 + 对话 plan/answer/summary）
templates/        # 12 章 Word 模板（make template 生成）
specs/            # OpenAPI 3.0 + JSON Schema（单一事实源）
docs/             # 开发文档 01~15 + ADR（含 ADR-0007 个人 agent 方案）
tests/            # 单元 / 流水线 / API / 会话 / 向量索引测试
data/             # 示例选型库与历史参考分布
corpus/           # 语料（sources.json 可复现抓取；raw/ 不入库）
artifacts/        # 任务运行产物（Word、校验报告、trace）
```

## 当前实现与后续演进

| 模块 | 当前实现（个人本地 agent） | 后续演进 |
|---|---|---|
| 存储 | **SQLite 单文件**：任务 / 参数 / 会话 / 消息 / 知识库 / 向量索引（ADR-0007） | 可选企业部署：Postgres + pgvector（docs/08） |
| 记忆 | 短期 12 条消息 + 长期会话摘要（SQLite）；前端直接读库渲染 | 摘要策略可配置、跨会话记忆 |
| 向量检索 | **sqlite-vec**（vec0、余弦、按维度分表）+ 关键词混合打分；缺失自动回退 JSON 扫描 | 大规模语料下评估重排与分片 |
| 对话编排 | **LangGraph**：plan → retrieve → answer；数字/引用随消息元数据返回 | 增加工具调用（任务发起、计算查询） |
| 任务流水线 | 自研状态机（门禁 / 断点 / SSE / 成本守卫），未迁移 LangGraph | 按需评估图化，保持门禁语义 |
| 确定性计算 | C1~C7 + skyfield/SGP4 轨道交叉验证 | 摄动全模型 / 高精度定轨 |
| 校验 | V1~V7（溯源、复算、闭合、约束、历史、敏感性、假设）+ 豁免语义 | 更多分系统闭合约束 |
| 文档 | 12 章 Word、版本递增、在线预览、数字 100% 可追溯 | 图表与排版增强 |
| 大模型 | 任意第三方网关 / 本地 Ollama；设置页热改；降级链与成本记账 | 私有化集群与专网网关 |

## 工程约定

- 接口与实体以 `specs/` 为单一事实源；调整接口需先同步 `docs/07-api.md`
- 运行产物落在 `artifacts/<task_id>/`，支持全过程回放
- 测试期望值独立制定，禁止用模型自身输出当期望（docs/11 §7）
- **上传文件只进本地知识库**；模型调用会把必要的提示词片段发往所选供应商（设置页可见）

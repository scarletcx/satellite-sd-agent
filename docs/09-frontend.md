# 09 前端开发文档

| 项目 | 内容 |
|---|---|
| 状态 | 细化 |
| 优先级 | P1 |
| 负责人 | 待定 |
| 最后更新 | 2026-10-05 |
| 关联文档 | [07 接口](./07-api.md) · [05 编排](./05-agent-orchestration.md) |

> 目标：把内部过程讲清楚 + 支撑人工门禁；不做花哨产品。
> 技术栈：React 18 + TypeScript + Vite + Ant Design 5（ADR-0001）；API 客户端由 `specs/openapi.yaml` 生成（`openapi-typescript` + fetch 封装）。

## 1. 路由与页面清单

| 路由 | 页面 | 目标 | 优先级 |
|---|---|---|---|
| `/` | P1 任务输入 | 填任务书，发起任务 | P0 |
| `/missions/:id` | P2 执行 Trace | 实时步骤 / 校验 / 门禁提醒 | P0 |
| `/missions/:id/review` | P3+P4 参数评审与冲突处理（Tabs） | 确认 / 驳回 / 差异处置 | P0 |
| `/missions/:id/document` | P5 文档预览 / 下载 | 下载 Word + 校验报告 | P1 |
| `/kb` | P6 知识库管理 | 语料摄取 / 检索调试 | P2 |

## 2. 页面详细规格

### P1 任务输入（`/`）

- **表单字段**（对应 A1 请求体，[07](./07-api.md) §A1）：

| 控件 | 字段 | 校验 |
|---|---|---|
| TextArea | `goal` | 必填，1~2000 字 |
| Select | `constraints.orbit_type` | SSO/LEO/GEO/custom |
| InputNumber | `constraints.altitude_km` | 200~36000 |
| InputNumber | `constraints.lifetime_years` | 0.5~20 |
| TextArea | `constraints.payload` | ≤500 字 |
| TextArea | `constraints.data_requirements` | ≤500 字 |
| TextArea | `constraints.ttc_conditions` | ≤500 字 |
| InputNumber | `constraints.mass_limit_kg` | >0 |

- **交互**：提交 → `POST /missions` → 成功跳转 `/missions/{task_id}`；`SCHEMA_INVALID` 时把 `details.field` 映射到表单定位报错
- **辅助**：「填入示例任务书」按钮（E2E-01 数据）；「使用上次输入」从 localStorage 恢复
- **状态**：提交中禁用按钮；错误顶部 Alert 展示 `message` + `trace_id`

### P2 执行 Trace（`/missions/:id`）

- **顶部状态卡**：`status` 徽标、`current_step`、`cost_estimate_cny`、取消按钮（A5，仅 running/awaiting_gate 显示，二次确认）
- **时间线**（AntD Timeline）：S1~S10；节点状态色；点击展开：
  - 工具步：`output_ref`（跳 A7 / trace）、`duration_ms`
  - LLM 步：`provider / model / prompt_version / tokens`
- **校验面板**：本任务 `validation` 事件列表（rule / status / param_id / message），block 高亮置顶
- **门禁提醒**：`gate` 事件 → 右侧 Alert + 按钮跳 `/missions/:id/review`
- **SSE 管理**（独立模块 `src/api/sse.ts`）：
  - 连接 `GET /missions/{id}/events`；按事件 `id` 去重
  - 断线：指数退避重连，携带 `Last-Event-ID`
  - 收到 `done` / `error` 关闭并刷新 A3
- **操作**：导出 trace（A11）、查看校验报告（A12）
- **状态处理**：`queued`（等待启动）/ `running`（流式）/ `awaiting_gate`（提示去评审）/ `failed`（错误卡 + trace_id）/ `succeeded`（文档入口）

### P3 参数评审（`/missions/:id/review` Tab1）

- **筛选**：`status`（默认 needs_review）、`module`
- **表格列**：参数 id、名称、值+单位、状态徽标、来源类型、余量、最近校验、更新时间、操作（评审）
- **详情抽屉**（点击行）：
  - 基本信息 + provenance 链（A7）：计算记录（公式 / 输入 / commit）或引用（标题 / 页码 / 链接）或假设（内容 / 依据）
  - 关联校验结论（pass/warn/block + evidence 对比）
  - 历史版本 diff（audit）
- **评审 Modal**：`action`（accept/reject）、`comment`（reject 必填）、`edited_value`（可选）；提交调 A8 → 成功后刷新列表并提示「已触发重校验」
- **批量**：本期不做（逐条确认，保证审计清晰）

### P4 冲突与差异处理（`/missions/:id/review` Tab2）

- **列表**：block / warn 项（来自 `validation_results`），字段：rule、param、message、evidence（expected vs actual 对比条）
- **每项操作**：
  - 采纳修改建议（S7 建议显示在此，点击跳 P3 并预填 `edited_value`）
  - 手动修正（跳 P3）
  - warn 忽略（必填 comment，写审计）
  - 重新校验（A9，`scope=param:<id>` 或 `all`）
- **门禁项**：`gate` 列表中 `assumption_confirm` / `discrepancy_resolve` 在此闭环；全部处理后任务自动恢复（`awaiting_gate → running`）

### P5 文档（`/missions/:id/document`）

- **未就绪**：显示 blocking 清单（来自 A10 409 的 `details.blocking[]`）+「去处理」链接（跳 P4）
- **就绪**：版本选择（`version`）+「下载 Word」+「下载校验报告」；摘要卡：章节数、数字可追溯率、引用数、占位符残留 = 0
- **注**：✅ 已实现在线预览：`GET /missions/{id}/document/preview`（docx → HTML，mammoth）；页面内直接渲染，保留下载入口
- 任务创建页支持**任务级模型选择**（供应商下拉，数据来自「设置」页）；执行过程页提供**进度条 + 当前过程文字提示**（含门禁暂停态）

### P6 知识库（`/kb`）

- **统计卡**：B5（documents / chunks / corpus_version / embedding_model）
- **文档表**：B3 列表；列：doc_id、标题、module、doc_type、is_synthetic、license、chunks、时间；操作：删除（输入 doc_id 二次确认 → B4）
- **上传**：B2 表单（file / module / doc_type / license / is_synthetic），上传进度与结果提示
- **检索调试**：输入 query + filters → B1 → 结果列表（score、引用展开原文与链接）

## 3. 状态展示规范

| 状态 | 颜色（AntD） | 展示 | 文案模板 |
|---|---|---|---|
| pass | green | ✅ | 校验通过 |
| warn | gold | ⚠️ | 余量偏紧，需确认 |
| block | red | ⛔ | 校验未通过，禁止入稿 |
| needs_review | blue | 🕓 | 待人工确认 |
| failed | volcano | ❌ | 执行失败（附 trace_id） |

- 原则：未被验证的数字在界面一律可见标注，与 Word 规则一致（[10](./10-doc-generation.md)）

## 4. 工程结构

```
web/src/
  api/          # 生成的客户端 + fetch 封装 + sse.ts（事件归并/重连）
  pages/        # P1~P6 对应路由
  components/   # TraceTimeline / ParamTable / ProvenanceDrawer / StatusBadge /
                # CitationTooltip / GateModal / BlockingList
  stores/       # taskStore（A3+SSE 归并）、uiStore
  utils/        # 格式化（单位、时间、数字）
```

- 环境变量：`VITE_API_BASE`、`VITE_APP_TOKEN`（演示级，本地存储）
- SSE 归并模块单测：乱序事件、重复 id、重连补发

## 5. 验收点

| 页面 | 验收 |
|---|---|
| P1 | 示例任务一键填入 → 提交成功入队 |
| P2 | 全程可看 S1~S10 推进；断网重连后事件不丢不重 |
| P3 | reject 不填理由被拦截；accept 后参数状态与 trace 同步更新 |
| P4 | ADV-01 场景下能展示 block 差异与建议，并完成处置闭环 |
| P5 | 存在 block 时下载被拒并展示原因；通过后可下载 |
| P6 | 上传→检索→删除（带确认）闭环可用 |

## 6. 关键取舍

| 决策 | 备选 | 理由 | ADR |
|---|---|---|---|
| React + Ant Design | Vue / Streamlit | 组件齐全、AI 编码辅助成熟 | [0001](./adr/0001-tech-stack.md) |
| SSE 而非 WebSocket | WebSocket | 单向进度流足够 | [07](./07-api.md) |
| 逐条评审（不做批量） | 批量确认 | 审计清晰，门禁语义更强 | — |
| 在线预览（docx→HTML） | 仅下载 | 已接入（mammoth 转换，见 [07](./07-api.md) A13） | [01](./01-scope-requirements.md) |

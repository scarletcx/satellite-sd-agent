# ADR-0001：技术栈与编排方式

| 项目 | 内容 |
|---|---|
| 状态 | 接受 |
| 日期 | 2026-10-05 |
| 决策人 | 项目负责人 |
| 关联 | [02 总体设计](../02-overall-design.md) · [05 编排](../05-agent-orchestration.md) · [09 前端](../09-frontend.md) |

## 1. 背景与问题

- 系统 = 流程编排 + 确定性计算 + 检索 + Word 生成 + Web 交互，单人 / 小团队开发
- 硬需求：编排过程可中断、可审计、可回放（人工门禁与 trace 是核心卖点）；科学计算与文档生态要强
- 约束：以 AI 辅助编码为主要开发方式；依赖可控、演示优先

## 2. 备选方案

| 方案 | 描述 | 优点 | 缺点 |
|---|---|---|---|
| A（选定） | Python + FastAPI + 自研轻量状态机；前端 React + Ant Design | 生态最全、流程显式可控、组件现成 | 编排代码需自写；前后端两个工程 |
| B | Node.js + NestJS | 前后端同语言、工程规范 | 科学计算 / Word 生态弱 |
| C | Python + Django | 自带 Admin | 异步 / SSE 一般，对计算服务偏重 |
| D | 引入 LangGraph 等 Agent 框架编排 | 开箱即用 | 抽象成本高；显式流程被隐式化，trace / 门禁难以精确控制 |
| E | 前端用 Streamlit / Gradio | 出效果最快 | 门禁、时间线等交互表达力不足，不符「完整系统」目标 |

## 3. 决策与理由

- 选择：**Python 3.11+ / FastAPI / Pydantic v2 / SQLAlchemy 2 + Alembic**；前端 **React 18 + TypeScript + Vite + Ant Design 5**；编排 = **自研显式状态机（S1~S10）**；包管理 uv + pnpm；部署本地单机（Postgres 走 docker compose）
- 理由：
  1. 计算与文档生态集中在 Python（numpy、docxtpl/python-docx、天体动力学库、pgvector 客户端）
  2. 本系统流程是「有向、可暂停、含人工节点」的流水线，自研状态机代码量小、完全可控，trace / 回放 / 门禁可直接实现
  3. FastAPI 原生异步 + SSE，契合进度流
  4. AntD 的 Timeline / Steps / Table 组件直接支撑 Trace 与评审页
- 明确放弃：多语言栈、Agent 框架黑盒编排、低代码前端

## 4. 影响

- 正面：流程可测试（stub 回放）、可回放、门禁自然表达；AI 辅助编码成熟度高
- 负面 / 技术债：orchestrator 与 prompt 版本管理需自建（数百行量级）
- 重新评估条件：若流程演进为多分支探索 / 自动规划（非固定步骤），再评估编排框架
- 后续行动：目录结构见 [02](../02-overall-design.md) 第 8 节

## 5. 参考

- [02 总体设计](../02-overall-design.md) · [materials.md](../materials.md)（依赖选型依据）

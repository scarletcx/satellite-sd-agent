# 决策记录（ADR）

> ADR（Architecture Decision Record）= 一条「为什么这么选」的存档。被追问取舍时，这里就是答案库。

## 何时写

发生以下情况必须写一条 ADR：

- 推翻或修改已接受的决策
- 引入 / 更换关键依赖（框架、模型、数据库、模板引擎）
- 影响两个以上模块的接口或数据结构
- 显式决定「不做某事」（对 scope 的裁剪）

## 规则

1. 编号连续：`NNNN-短标题.md`，空白模板见 [0000-template.md](./0000-template.md)
2. 状态流转：`提议 → 接受 / 拒绝 → （被 NNNN 取代 / 废弃）`
3. 一条 ADR 只谈一个决策，短小（≤1 页），当天写完
4. 被取代的 ADR **不删除**，只改状态并链接新 ADR
5. 代码或文档中相关处引用 ADR 编号

## 索引

| 编号 | 标题 | 状态 | 日期 | 关联 |
|---|---|---|---|---|
| [0001](./0001-tech-stack.md) | 技术栈与编排方式 | 接受 | 2026-10-05 | [02](../02-overall-design.md) · [05](../05-agent-orchestration.md) |
| [0002](./0002-llm-services.md) | LLM 服务与嵌入模型 | 接受 | 2026-10-05 | [05](../05-agent-orchestration.md) · [12](../12-deployment.md) |
| [0003](./0003-storage.md) | 存储选型（关系型 + 向量） | 接受 | 2026-10-05 | [08](../08-storage.md) |
| [0004](./0004-orbit-computation.md) | 轨道与覆盖计算路线 | 接受 | 2026-10-05 | [06](../06-calculation-verification.md) |
| [0005](./0005-doc-engine.md) | Word 模板引擎 | 接受 | 2026-10-05 | [10](../10-doc-generation.md) |
| [0006](./0006-llm-provider-registry.md) | LLM 供应商注册表与运行时设置 | 接受 | 2026-10-06 | [0002](./0002-llm-services.md) · [07](../07-api.md) |

## 待记录清单

| # | 主题 | 触发时机 |
|---|---|---|
| 1 | 许可证策略：AGPL / GPL 项目如何参考（隔离目录、不复制代码） | 首次引入第三方代码时 |
| 2 | 切分与检索参数定案（chunk 大小 / 权重 / HNSW 参数） | [04](../04-knowledge-base.md) 实验完成后 |
| 3 | 交叉验证库选定（brahe / tudatpy / skyfield 三选一） | [06](../06-calculation-verification.md) 开发期对拍后 |
| 4 | 更换向量库 / 存储（如发生） | 触发时 |

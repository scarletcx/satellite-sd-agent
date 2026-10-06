# JSON Schema 目录

> 本目录是**数据结构的单一事实源**（由 [docs/03-data-model.md](../03-data-model.md) 落地）。
> `specs/openapi.yaml` 为自包含文件（面向 Apifox 直接导入）；两者由 `make test-contract`（L2 契约测试）保证一致。

## 约定

- 规范：JSON Schema **draft 2020-12**；每个文件带 `$id = https://satellite.local/schemas/<文件名>`
- 一律 `additionalProperties: false`（防字段漂移）；所有描述使用中文
- 跨文件引用使用相对 `$ref`（如 `"citation.schema.json"`），校验器以本目录为 base URI（`referencing` registry 注册整个目录）
- 枚举（unit / module / doc_type 等）当前在各文件内联；若第三处复用，再抽 `common.schema.json` 收敛

## 文件清单

| 文件 | 实体 | 对应文档 |
|---|---|---|
| `mission-request.schema.json` | 任务书（输入） | [03](../03-data-model.md) §3.1 |
| `system-design.schema.json` | 整星方案 | §3.2 |
| `design-parameter.schema.json` | 设计参数（核心对象） | §3.3 |
| `budget.schema.json` | 预算 + 行项目 | §3.4 |
| `calculation-record.schema.json` | 计算记录 | §3.5 |
| `validation-result.schema.json` | 校验结论 | §3.6 |
| `assumption.schema.json` | 假设台账 | §3.7 |
| `component-candidate.schema.json` | 选型候选 | §3.8 |
| `citation.schema.json` | 引用 | §3.9 |
| `review-gate.schema.json` | 门禁记录 | §3.10 |
| `tools/` | 内部工具契约（见下） | [07](../07-api.md) §6 / [05](../05-agent-orchestration.md) §4 |

## tools/ 约定

每个工具契约文件仅含 `$defs`，请求 / 响应通过 JSON Pointer 引用：

- 请求 = `<file>#/$defs/request`
- 响应 = `<file>#/$defs/response`

| 文件 | 工具 |
|---|---|
| `tools/calc-budget.schema.json` | `calc.mass_budget` / `calc.power_budget` / `calc.data_budget` / `calc.link_budget`（`budget_type` 区分） |
| `tools/calc-orbit.schema.json` | `calc.orbit` |
| `tools/calc-eps.schema.json` | `calc.eps`（太阳翼 / 电池尺寸，[06](../06-calculation-verification.md) C6） |
| `tools/calc-adcs.schema.json` | `calc.adcs`（能力粗算，C7） |
| `tools/kb-search.schema.json` | `kb.search` |
| `tools/doc-render.schema.json` | `doc.render` |
| `tools/doc-check.schema.json` | `doc.check` |

## 校验方式（实现期）

```python
import json, pathlib
from referencing import Registry, Resource
from jsonschema import Draft202012Validator

base = pathlib.Path("specs/schemas")
registry = Registry().with_resources(
    (f.name, Resource.from_contents(json.loads(f.read_text())))
    for f in base.glob("*.schema.json")
)
schema = json.loads((base / "design-parameter.schema.json").read_text())
Draft202012Validator(schema, registry=registry).validate(instance)
```

# 预装语料（公开许可）

本目录随仓库提供 **3 份 NASA 美国政府作品（公有领域）**，用于本地知识库演示与离线测试。
`corpus/raw/` 下的其他文件（用户上传、UCS 原始表、许可未确认资料）不入库。

| id | 文件 | 大小 | sha256 | 许可 |
|---|---|---|---|---|
| `nasa-se-handbook` | `raw/system/nasa-se-handbook.pdf` | 3,773,440 B | `8eeb4887a4dc57a23049da7dd2ed556833cf98e214b240468d987873164ff688` | NASA-public-domain |
| `nasa-risk-handbook` | `raw/risk/nasa-risk-handbook.pdf` | 5,623,001 B | `46d6107b895f7e695a44afa920998335954a0327cf3c5592bc818beb6964281e` | NASA-public-domain |
| `cubesat-101` | `raw/system/cubesat-101.pdf` | 4,445,718 B | `57d2783457cb94b69136476ca341ddf4c7dc23bf61682606e37a048e9e5ae592` | NASA-public-domain |

## 使用

```bash
make seed-corpus   # 按 corpus/sources.json + raw/manifest.json 导入预装语料（幂等）
make corpus-fetch  # 重新下载并校验 sha256（网络可用时）
make seed          # 导入 4 份合成样例（用于测试/演示）
```

- 来源清单：`corpus/sources.json`；实际文件校验：`corpus/raw/manifest.json`（sha256 / 大小 / 许可 / 抓取时间）。
- 导入脚本会校验 sha256；文件不存在、校验失败或来源不在 `sources.json` 中都会跳过并提示。
- 一批 NASA 文档的完整切块数约为 3033（SE Handbook 1513 + Risk Handbook 1067 + CubeSat 101 453），实际以运行时统计为准。

## 不随仓库分发的内容

- `corpus/raw/data/ucs-satellite-database.xlsx`：UCS 原始数据，再分发条款需单独确认；项目只保留派生统计
  `app/data/reference_ranges.json`。
- 用户上传的 PDF/DOCX（如 ECMWF 数据、风场对比文档）：属于本地/客户数据，不入库；上传入口与许可由使用者负责。
- 任何未在 `corpus/sources.json` 中登记、或未明确允许公开再分发的资料。

## 许可说明

NASA 文档为美国政府作品，通常属于公有领域；本仓库保留来源 URL 与 sha256 便于核验。
使用前仍建议打开来源页确认最新许可与适用范围。

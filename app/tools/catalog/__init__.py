"""选型候选生成（docs/06 §2 计算链末端、docs/10 第 10 章）。

输入：已计算的 IR 参数值 + S4 设计输入；输出：按类别打分的候选清单（确定性规则）。
数据源：data/parts_catalog.json（示例库，参数为公开资料量级）。
"""
from __future__ import annotations

from app.tools.catalog.select import CATALOG_PATH, load_catalog, select_candidates

__all__ = ["CATALOG_PATH", "load_catalog", "select_candidates"]

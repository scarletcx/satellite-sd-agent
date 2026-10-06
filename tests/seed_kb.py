"""测试用知识库种子（合成语料，tests/fixtures/kb）。"""
from pathlib import Path

from app.tools import kb

FIXTURES = Path(__file__).parent / "fixtures" / "kb"

_META = {
    "power.txt": ("power", "电源分系统样例（合成）"),
    "data.txt": ("data", "数据量预算样例（合成）"),
    "ttc.txt": ("ttc", "测控数传样例（合成）"),
    "orbit.txt": ("orbit", "轨道覆盖样例（合成）"),
}


def seed() -> list[str]:
    """幂等：知识库非空则跳过；返回本次摄取的 doc_id 列表。"""
    if kb.stats()["documents"] > 0:
        return []
    doc_ids = []
    for name, (module, title) in _META.items():
        result = kb.ingest_file(FIXTURES / name, module=module, doc_type="report",
                                license="synthetic", is_synthetic=True, title=title)
        doc_ids.append(result["doc_id"])
    return doc_ids

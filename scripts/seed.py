"""导入种子语料（tests/fixtures/kb 合成样例，幂等）：make seed。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import init_db  # noqa: E402
from app.tools import kb  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "kb"
META = {
    "power.txt": ("power", "电源分系统样例（合成）"),
    "data.txt": ("data", "数据量预算样例（合成）"),
    "ttc.txt": ("ttc", "测控数传样例（合成）"),
    "orbit.txt": ("orbit", "轨道覆盖样例（合成）"),
}


def main() -> int:
    init_db()
    stats = kb.stats()
    if stats["documents"] > 0:
        print(f"知识库已有 {stats['documents']} 篇文档（{stats['corpus_version']}），跳过导入。")
        return 0
    for name, (module, title) in META.items():
        result = kb.ingest_file(FIXTURES / name, module=module, doc_type="report",
                                license="synthetic", is_synthetic=True, title=title)
        print(f"  导入 {result['doc_id']}（{result['chunks']} 切片）")
    stats = kb.stats()
    print(f"完成：{stats['documents']} 篇 / {stats['chunks']} 切片 / {stats['corpus_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

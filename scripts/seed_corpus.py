"""导入预装公开语料（corpus/raw 中 sources.json 明确允许的来源）：make seed-corpus。

只处理 corpus/sources.json 中登记、且在 corpus/raw/manifest.json 中有 sha256 的来源；
已存在的文档跳过，校验失败或文件缺失会提示并继续。幂等，可重复执行。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import init_db  # noqa: E402
from app.tools import kb  # noqa: E402
from app.tools.kb.store import KbError  # noqa: E402

SOURCES = ROOT / "corpus" / "sources.json"
RAW = ROOT / "corpus" / "raw"
MANIFEST = RAW / "manifest.json"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if not SOURCES.exists() or not MANIFEST.exists():
        print("缺少 corpus/sources.json 或 corpus/raw/manifest.json；先运行 make corpus-fetch。")
        return 1

    init_db()
    sources = json.loads(SOURCES.read_text(encoding="utf-8")).get("sources", [])
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")).get("sources", {})
    added = skipped = missing = failed = 0

    for item in sources:
        source_id = item.get("id", "?")
        record = manifest.get(source_id, {})
        target = RAW / item.get("module", "") / item.get("filename", "")
        if not target.exists():
            missing += 1
            print(f"✗ {source_id}：文件不存在 {target.relative_to(ROOT)}（运行 make corpus-fetch）")
            continue
        expected = record.get("sha256")
        if expected and sha256_of(target) != expected:
            failed += 1
            print(f"✗ {source_id}：sha256 校验失败，跳过 {target.relative_to(ROOT)}")
            continue

        try:
            result = kb.ingest_file(
                target,
                module=item["module"],
                doc_type=item["doc_type"],
                license=item["license"],
                is_synthetic=False,
                title=item["title"],
                source_url=item.get("url"),
            )
            added += 1
            print(f"✓ {source_id}：{result['doc_id']}，{result['chunks']} 切片")
        except KbError as exc:
            if "已存在" in str(exc):
                skipped += 1
                print(f"↷ {source_id}：已存在，跳过")
            else:
                failed += 1
                print(f"✗ {source_id}：{exc}")
        except Exception as exc:  # noqa: BLE001 —— 单个来源失败不影响其他来源
            failed += 1
            print(f"✗ {source_id}：{exc}")

    stats = kb.stats()
    print(f"\n完成：新增 {added}，已存在 {skipped}，缺失 {missing}，失败 {failed}")
    print(f"知识库：{stats['documents']} 篇 / {stats['chunks']} 切片 / {stats['corpus_version']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

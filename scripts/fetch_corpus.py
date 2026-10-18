"""语料抓取：只处理 corpus/sources.json 中明确允许公开下载的来源。

用法：
  .venv/bin/python scripts/fetch_corpus.py              # 抓取全部未下载来源
  .venv/bin/python scripts/fetch_corpus.py --only cubesat-101

产物：corpus/raw/<module>/<filename>；索引 corpus/raw/manifest.json（sha256 / 许可 / 大小 / 时间）。
说明：NASA 文档为美国政府作品（公有领域）；机构标准类文档请按 collection-checklist 人工获取并遵守许可。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SOURCES = BASE / "corpus" / "sources.json"
RAW = BASE / "corpus" / "raw"
MANIFEST = RAW / "manifest.json"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0 Safari/537.36")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return data.get("sources", {})


def download(url: str, target: Path, timeout: float = 180.0) -> None:
    request = urllib.request.Request(url, headers={
        "User-Agent": BROWSER_UA,
        "Accept": "*/*",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取开放许可语料")
    parser.add_argument("--only", action="append", default=None,
                        help="只抓指定 id（可重复）")
    args = parser.parse_args()

    items = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    manifest = load_manifest()
    fetched, skipped, failed = [], [], []

    for item in items:
        if args.only and item["id"] not in args.only:
            continue
        target = RAW / item["module"] / item["filename"]
        record = manifest.get(item["id"])
        if record and target.exists() and sha256_of(target) == record["sha256"]:
            skipped.append(item["id"])
            print(f"↷ {item['id']}（已存在，sha256 一致）")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            download(item["url"], tmp)
            size = tmp.stat().st_size
            if size < 1024:
                raise RuntimeError(f"文件过小（{size} B），可能被拦截或重定向到错误页")
            tmp.replace(target)
            digest = sha256_of(target)
            manifest[item["id"]] = {
                **item,
                "sha256": digest,
                "bytes": size,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            fetched.append(item["id"])
            print(f"✓ {item['id']}：{size / 1e6:.1f} MB → {target.relative_to(BASE)}")
        except Exception as exc:  # noqa: BLE001 —— 单个来源失败不影响其他来源
            tmp.unlink(missing_ok=True)
            failed.append(item["id"])
            print(f"✗ {item['id']}：{exc}")

    RAW.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "sources": manifest},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n完成：新增 {len(fetched)}，跳过 {len(skipped)}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

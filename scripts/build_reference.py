"""构建 V5 参考分布：从 UCS Satellite Database（公开）提取 LEO 小卫星统计。

产物：app/data/reference_ranges.json（含来源 URL / 下载时间 / 文件 sha256 / 样本量 / P10~P90）。
原始 xlsx 保存在 corpus/raw/data/（gitignore），不随仓库分发。
用法：make reference（需要网络；已下载过则复用本地文件）
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

SOURCE_URL = ("https://www.ucs.org/sites/default/files/2024-01/"
              "UCS-Satellite-Database%205-1-2023.xlsx")
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
RAW_PATH = settings.corpus_dir / "raw" / "data" / "ucs-satellite-database.xlsx"
OUTPUT_PATH = ROOT / "app" / "data" / "reference_ranges.json"

MASS_MIN, MASS_MAX = 10.0, 500.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _to_float(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _percentile(sorted_values: list[float], pct: float) -> float:
    """线性插值分位数（与常见统计口径一致）。"""
    if not sorted_values:
        raise ValueError("empty")
    position = (len(sorted_values) - 1) * pct / 100.0
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def _download() -> Path:
    if RAW_PATH.exists():
        print(f"复用本地文件：{RAW_PATH}")
        return RAW_PATH
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("下载 UCS Satellite Database …")
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response, RAW_PATH.open("wb") as handle:
        handle.write(response.read())
    print(f"完成：{RAW_PATH}（{RAW_PATH.stat().st_size / 1024:.0f} KB）")
    return RAW_PATH


def main() -> int:
    from openpyxl import load_workbook

    path = _download()
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    header = [str(cell or "").strip() for cell in next(rows)]
    index = {name: header.index(name) for name in
             ("Class of Orbit", "Launch Mass (kg.)", "Power (watts)") if name in header}
    if len(index) != 3:
        print(f"列名不匹配（找到 {index}），请检查表结构")
        return 1

    masses: list[float] = []
    powers: list[float] = []
    for row in rows:
        orbit_class = str(row[index["Class of Orbit"]] or "").strip().upper()
        if orbit_class != "LEO":
            continue
        mass = _to_float(row[index["Launch Mass (kg.)"]])
        if mass is None or not (MASS_MIN <= mass <= MASS_MAX):
            continue
        masses.append(mass)
        power = _to_float(row[index["Power (watts)"]])
        if power is not None and power > 0:
            powers.append(power)

    masses.sort()
    powers.sort()
    ranges = {
        "mass_kg": {f"p{p}": round(_percentile(masses, p), 1) for p in (10, 25, 50, 75, 90)},
        "power_w": {f"p{p}": round(_percentile(powers, p), 1) for p in (10, 25, 50, 75, 90)},
    }
    payload = {
        "source": "UCS Satellite Database (LEO, 10-500 kg)",
        "url": SOURCE_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": _sha256(path),
        "filter": {"orbit_class": "LEO", "mass_kg": [MASS_MIN, MASS_MAX]},
        "sample_n": {"mass": len(masses), "power": len(powers)},
        "ranges": ranges,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"参考分布已写入：{OUTPUT_PATH}")
    print(f"  mass 样本 {len(masses)}：P10={ranges['mass_kg']['p10']} P90={ranges['mass_kg']['p90']} kg")
    print(f"  power 样本 {len(powers)}：P10={ranges['power_w']['p10']} P90={ranges['power_w']['p90']} W")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

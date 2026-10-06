"""导出任务全量快照：artifacts/<task_id>/ + DB 关键行 → artifacts/<task_id>-snapshot.zip。

用法：make snapshot TASK=<task_id>（docs/12 §6）
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import new_session  # noqa: E402
from app.models import (  # noqa: E402
    Assumption,
    CalculationRecord,
    DesignParameter,
    Mission,
    ReviewGate,
    ValidationResult,
)
from app.tracing import task_dir  # noqa: E402


def _dump(session, model, task_id: str) -> list[dict]:
    rows = session.query(model).filter(model.mission_id == task_id).all()
    result = []
    for row in rows:
        item = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        result.append({key: (value.isoformat() if hasattr(value, "isoformat") else value)
                       for key, value in item.items()})
    return result


def main(task_id: str) -> int:
    if not task_id:
        print("用法：python scripts/snapshot.py <task_id>（或 make snapshot TASK=<task_id>）")
        return 2

    directory = task_dir(task_id)
    with new_session() as session:
        mission = session.get(Mission, task_id)
        if mission is None:
            print(f"任务不存在：{task_id}")
            return 1
        payload = {
            "mission": {column.name: (getattr(mission, column.name).isoformat()
                                      if hasattr(getattr(mission, column.name), "isoformat")
                                      else getattr(mission, column.name))
                        for column in mission.__table__.columns},
            "parameters": _dump(session, DesignParameter, task_id),
            "calculations": _dump(session, CalculationRecord, task_id),
            "validations": _dump(session, ValidationResult, task_id),
            "assumptions": _dump(session, Assumption, task_id),
            "gates": _dump(session, ReviewGate, task_id),
        }

    output = directory.parent / f"{task_id}-snapshot.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(directory.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(directory.parent))
        archive.writestr(f"{task_id}/mission-snapshot.json",
                         json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"快照已导出：{output}（{output.stat().st_size / 1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))

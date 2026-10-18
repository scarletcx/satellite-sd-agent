"""ID 生成器测试：删除记录后编号不得与已存在编号冲突（复现 missions.id 唯一键冲突）。

测试库被所有用例共用，因此编号一律从当前最大值往后取，并在结束时清理。
"""
from datetime import datetime

from app.db import new_session
from app.models import CalculationRecord, ChatSession, Mission
from app.orchestrator.ids import next_calc_ids, next_chat_session_id, next_mission_id

_TODAY = datetime.now().astimezone().strftime("%Y%m%d")


def _number(seed: str) -> int:
    return int(seed.rsplit("-", 1)[1])


def _mission_id(number: int) -> str:
    return f"t-{_TODAY}-{number:03d}"


def test_mission_id_skips_existing_number():
    with new_session() as session:
        start = _number(next_mission_id(session))
        created = [_mission_id(start), _mission_id(start + 1),
                   _mission_id(start + 2), _mission_id(start + 3)]
        for task_id in created:
            session.add(Mission(id=task_id, goal="编号测试任务", constraints={},
                                status="succeeded"))
        session.commit()

        session.delete(session.get(Mission, _mission_id(start + 2)))
        session.commit()
        # 旧的「按数量 +1」会算出 start+3，与已存在的任务号冲突
        assert next_mission_id(session) == _mission_id(start + 4)

        session.add(Mission(id="t-20200101-007", goal="历史任务", constraints={},
                            status="succeeded"))
        session.commit()
        assert next_mission_id(session) == _mission_id(start + 4), "其他日期不参与编号"

        for task_id in created:
            row = session.get(Mission, task_id)
            if row is not None:
                session.delete(row)
        session.delete(session.get(Mission, "t-20200101-007"))
        session.commit()


def test_calc_ids_skip_existing_number():
    mission_id = "t-test-ids-001"
    with new_session() as session:
        start = _number(next_calc_ids(session, mission_id, 1)[0])
        created = [f"calc-{_TODAY}-{start + i:04d}" for i in range(3)]
        for record_id in created:
            session.add(CalculationRecord(
                id=record_id, mission_id=mission_id, tool="calc.orbit",
                formula_version="orbit-v1", inputs={}, outputs={}, units_map={},
            ))
        session.commit()

        session.delete(session.get(CalculationRecord, created[1]))
        session.commit()
        assert next_calc_ids(session, mission_id, 2) == [
            f"calc-{_TODAY}-{start + 3:04d}", f"calc-{_TODAY}-{start + 4:04d}"]

        for record_id in created:
            row = session.get(CalculationRecord, record_id)
            if row is not None:
                session.delete(row)
        session.commit()


def test_chat_session_id_skips_existing_number():
    with new_session() as session:
        start = _number(next_chat_session_id(session))
        created = [f"cs-{_TODAY}-{start + i:03d}" for i in range(2)]
        for session_id in created:
            session.add(ChatSession(id=session_id, title="编号测试会话"))
        session.commit()

        session.delete(session.get(ChatSession, created[0]))
        session.commit()
        assert next_chat_session_id(session) == f"cs-{_TODAY}-{start + 2:03d}"

        for session_id in created:
            row = session.get(ChatSession, session_id)
            if row is not None:
                session.delete(row)
        session.commit()

"""LLM 输出护栏与事件重放测试（docs/05 §S7/S8、docs/07 §1.6）。"""
from app.orchestrator.events import EventBus
from app.steps.common import untraceable_numbers
from app.steps.s7_advise import _template_suggestions
from app.steps.s8_narrative import _sanitize
from app.tools.doc.check import check_citations


def test_untraceable_numbers_flags_unknown_values():
    # 行首章节编号、年份、标识符不算违规
    assert untraceable_numbers(["12 引用与假设"], []) == []
    assert untraceable_numbers(["计算记录 calc-20261005-0013 见附录"], []) == []
    assert untraceable_numbers(["S1 说明 2026 年"], []) == []
    # 有出处的数字放行
    assert untraceable_numbers(["整星质量 79.2 kg"], [79.2]) == []
    assert untraceable_numbers(["质量 79.25 kg"], [79.2]) == []  # 0.1% 容差内
    # 无出处的数字（含小数与小数位）被拦
    assert 5.2 in untraceable_numbers(["太阳翼面积 5.2 m²"], [])
    assert 5.0 in untraceable_numbers(["余量提升 5%"], [])          # 非行首的小整数也会被拦
    assert untraceable_numbers(["设计寿命 3 年"], [3.0]) == []


def test_check_citations_detects_unknown_reference():
    result = check_citations(["依据 [S1] 与 S9 的经验"], [{"id": "S1", "title": "某来源"}])
    assert result["referenced"] == ["S1", "S9"]
    assert result["issues"] == [{"type": "citation_unknown", "detail": "S9"}]

    result = check_citations(["依据 [S1]"], [{"id": "S1", "title": ""}])
    assert result["issues"][0]["type"] == "citation_missing_source"


def test_check_citations_ignores_step_labels():
    """「（S4 草案）」是步骤标签，不应被当成引用。"""
    result = check_citations(
        ["设计输入「质量预算（S4 草案）」经工程师确认", "S2 步骤输出见 trace"],
        [{"id": "S1", "title": "来源"}])
    assert result["referenced"] == []
    assert result["issues"] == []


def test_s8_sanitize_drops_offending_sentences():
    narrative = {
        "1_overview": "本方案面向任务书要求。太阳翼面积取 9.9 m²，满足要求。设计寿命 {{mission.lifetime_years}} 年。",
    }
    cleaned, dropped = _sanitize(narrative, allowed=[3.0, 79.2], citation_ids={"S1"})
    assert dropped == 1
    assert "9.9" not in cleaned["1_overview"]
    assert "{{mission.lifetime_years}}" in cleaned["1_overview"]


def test_s8_sanitize_unknown_citation_and_empty_fallback():
    narrative = {"11_risk": "依据 [S7] 的结论，风险可控。"}
    cleaned, dropped = _sanitize(narrative, allowed=[], citation_ids={"S1"})
    assert dropped == 1
    assert "S7" not in cleaned["11_risk"]
    assert "省略" in cleaned["11_risk"]


def test_s7_template_suggestions_cover_blocks():
    blocks = [{"rule_id": "V4", "status": "block", "param_id": "mass.total_with_margin",
               "message": "整星质量超限"}]
    suggestions = _template_suggestions(blocks)
    assert suggestions and suggestions[0]["param_id"] == "mass.total_with_margin"
    assert suggestions[0]["direction"]


def test_event_bus_history_replay():
    bus = EventBus()
    for index in range(3):
        bus.publish("t-test-001", "step", {"index": index})
    replay = bus.history_since("t-test-001", 1)
    assert [item["id"] for item in replay] == [2, 3]
    assert bus.history_since("t-test-001", 3) == []
    assert [item["id"] for item in bus.history_since("t-test-002", 0)] == []

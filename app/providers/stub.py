"""桩 Provider：确定性输出，供 CI / 离线演示 / 骨架联调（docs/05 §7、docs/11 §2）。

内容与 E2E-01（500km SSO 光学遥感小卫星）对齐；真实模型接入后本文件仅用于测试回放。
"""
from __future__ import annotations


class StubProvider:
    name = "stub"

    def available(self) -> bool:
        return True

    def chat_json(self, step: str, context: dict, options: dict | None = None) -> tuple[dict, dict]:
        handler = {
            "S1": self._s1_parse,
            "S2": self._s2_queries,
            "S3": self._s3_decompose,
            "S4": self._s4_params,
            "S7": self._s7_advise,
            "S8": self._s8_narrative,
            "CHAT_PLAN": self._chat_plan,
            "CHAT_ANSWER": self._chat_answer,
            "CHAT_SUMMARY": self._chat_summary,
            "CHAT_COMPACT": self._chat_compact,
            "CHAT_MEMORY": self._chat_memory,
        }.get(step)
        if handler is None:
            raise ValueError(f"桩 Provider 未实现步骤：{step}")
        payload = handler(context)
        usage = {"provider": "stub", "model": "stub",
                 "tokens_in": 0, "tokens_out": 0, "cost_cny": 0.0}
        return payload, usage

    # ------------------------------------------------------------- S1 解析
    @staticmethod
    def _s1_parse(context: dict) -> dict:
        raw = context.get("constraints") or {}
        goal = context["goal"]

        def pick(key: str, default):
            value = raw.get(key)
            return default if value in (None, "") else value

        return {
            "goal": goal,
            "constraints": {
                "orbit_type": pick("orbit_type", "SSO" if "SSO" in goal.upper() else "LEO"),
                "altitude_km": pick("altitude_km", 500),
                "lifetime_years": pick("lifetime_years", 3),
                "payload": pick("payload", "光学遥感载荷（指标待澄清）"),
                "data_requirements": pick("data_requirements", "每日成像 10 圈左右"),
                "ttc_conditions": pick("ttc_conditions", "国内测控站，S 频段"),
                "mass_limit_kg": pick("mass_limit_kg", None),
                "notes": pick("notes", None),
            },
            "clarifications": [],
            "language": "zh",
        }

    # ------------------------------------------------------------- S2 检索式
    @staticmethod
    def _s2_queries(context: dict) -> dict:
        mission = context.get("mission_request") or {}
        goal = mission.get("goal", "") or "卫星总体设计"
        constraints = mission.get("constraints") or {}
        altitude = constraints.get("altitude_km")
        suffix = f" {altitude}km" if altitude else ""
        return {"queries": [
            goal,
            f"太阳翼 电源 电池 余量{suffix}".strip(),
            "数据量 压缩 存储 下行 数传",
            f"轨道 覆盖 重访 太阳同步{suffix}".strip(),
        ]}

    # ------------------------------------------------------------- S3 分解
    @staticmethod
    def _s3_decompose(context: dict) -> dict:
        mission = context["mission_request"]
        return {
            "configuration": {
                "type": "3-axis-stabilized",
                "envelope_mm": {"x": 800, "y": 800, "z": 1200},
                "notes": "小卫星平台，两翼太阳翼对日定向",
            },
            "subsystems": [
                {"name": "有效载荷", "module": "payload", "description": "光学相机（指标待细化）", "status": "proposed"},
                {"name": "电源分系统", "module": "power", "description": "太阳翼 + 锂离子电池组", "status": "proposed"},
                {"name": "测控数传分系统", "module": "ttc", "description": "S 频段测控 + X 频段数传", "status": "proposed"},
                {"name": "姿态控制分系统", "module": "adcs", "description": "反作用轮 + 磁力矩器", "status": "proposed"},
                {"name": "结构与机构", "module": "system", "description": "承力结构 + 分离机构", "status": "proposed"},
            ],
            "metrics": [
                {"param_id": "mass.total_with_margin", "target_value": mission["constraints"].get("mass_limit_kg") or 100, "unit": "kg"},
                {"param_id": "power.p_avg_w", "target_value": 80, "unit": "W"},
            ],
            "version": 1,
        }

    # --------------------------------------------------------- S4 参数草案
    @staticmethod
    def _s4_params(context: dict) -> dict:
        return {
            "assumptions": [
                {"id": "asm-0001", "content": "太阳电池 AM0 效率取 30%（BOL）", "basis": "SST-SOA 典型值",
                 "related_params": ["eps.cell_efficiency"]},
                {"id": "asm-0002", "content": "载荷数据压缩比取 3:1", "basis": "工程经验",
                 "related_params": ["data.compression_ratio"]},
                {"id": "asm-0003", "content": "轨道周期 94.6 min、阴影期 35.6 min（500km SSO 典型）", "basis": "轨道估算",
                 "related_params": ["orbit.period_min", "orbit.t_ecl_min"]},
            ],
            "mass": {
                "items": [
                    {"name": "有效载荷", "mass_kg": 18.0, "margin": 0.10, "source_ref": "asm-payload-mass"},
                    {"name": "电源分系统", "mass_kg": 12.0, "margin": 0.10, "source_ref": "asm-power-mass"},
                    {"name": "测控数传分系统", "mass_kg": 6.0, "margin": 0.10, "source_ref": "asm-ttc-mass"},
                    {"name": "姿态控制分系统", "mass_kg": 9.0, "margin": 0.10, "source_ref": "asm-adcs-mass"},
                    {"name": "结构与机构", "mass_kg": 14.0, "margin": 0.10, "source_ref": "asm-structure-mass"},
                    {"name": "星务与电缆", "mass_kg": 4.0, "margin": 0.10, "source_ref": "asm-obc-mass"},
                ],
                "propellant_kg": 3.0,
                "margin_policy": {"phase": "方案", "pct": 0.20},
            },
            "power": {
                "loads": [
                    {"name": "测控数传", "phase": "both", "power_w": 30.0, "duty_pct": 100},
                    {"name": "载荷工作", "phase": "sun", "power_w": 45.0, "duty_pct": 50},
                    {"name": "加热器", "phase": "ecl", "power_w": 10.0, "duty_pct": 100},
                    {"name": "星务", "phase": "both", "power_w": 8.0, "duty_pct": 100},
                ],
                "t_orbit_min": 94.6,
                "t_ecl_min": 35.6,
                "dod": 0.30,
                "eta_out": 0.90,
            },
            "data": {
                "rate_mbps": 120.0,
                "imaging_min_per_orbit": 6.0,
                "compression_ratio": 3.0,
                "downlink_rate_mbps": 100.0,
                "downlink_window_min_per_day": 40.0,
                "orbits_per_day": 15.2,
                "storage_cycles": 2,
            },
            "link": {
                "freq_ghz": 8.2,
                "slant_km": 1500.0,
                "eirp_dbw": 42.0,
                "gt_db_per_k": 3.0,
                "data_rate_kbps": 100000.0,
                "required_ebn0_db": 6.0,
                "rain_margin_db": 1.0,
                "other_losses_db": 2.0,
                "min_margin_db": 3.0,
            },
            "orbit": {
                "alt_km": 500.0,
                "inc_deg": 97.4,
                "station_lat": 40.0,
                "station_lon": 116.0,
                "min_elevation_deg": 5.0,
            },
            "eps": {
                "degradation_per_year": 0.02,
                "cell_efficiency": 0.30,
                "packing_factor": 0.85,
                "sun_angle_cos": 0.90,
                "margin_pct": 0.10,
            },
        }

    # ------------------------------------------------------------- S7 消解建议
    @staticmethod
    def _s7_advise(context: dict) -> dict:
        directions = {
            "V4": "复核任务书约束或做降额设计：从分系统分解中寻找减重/降耗空间",
            "V3": "复核预算闭合：检查输入假设与分系统数据是否自洽，必要时补充工况假设",
            "V2": "复核计算记录与输入快照：确认是否存在手工修改或版本错配",
            "V1": "补齐出处：为缺失来源的数字补充计算记录或显式假设，并重新评审",
            "V5": "与历史基线偏差较大：复核经验假设与任务书指标的可实现性",
            "V6": "结论对假设敏感：收紧关键假设或增加设计余量后再评估",
        }
        findings = context.get("findings") or []
        return {"suggestions": [
            {"param_id": item.get("param_id"), "rule_id": item.get("rule_id"),
             "direction": directions.get(item.get("rule_id"), "复核该项的输入假设与约束条件"),
             "rationale": item.get("message", "")}
            for item in findings if item.get("status") == "block"
        ]}

    # ------------------------------------------------------------- 对话（个人 agent）
    @staticmethod
    def _chat_plan(context: dict) -> dict:
        import re

        question = str(context.get("question") or "")
        task = re.search(r"t-\d{8}-\d{3}", question)

        if ("新建" in question and "任务" in question) or "设计一颗" in question:
            return {"action": "create_mission", "goal": question, "args": {}}
        if "任务" in question and any(word in question for word in
                                      ("列表", "有哪些", "进行中", "未完成", "已完成")):
            return {"action": "list_missions", "args": {}}
        if task and any(word in question for word in ("状态", "进度", "审核", "评审", "通过", "拒绝")):
            if any(word in question for word in ("审核", "评审", "通过", "拒绝")):
                return {"action": "mission_review",
                        "args": {"task_id": task.group(0), "param_id": "", "review_action": "accept"}}
            return {"action": "mission_status", "args": {"task_id": task.group(0)}}
        if any(word in question for word in ("存入知识库", "存到知识库", "保存到知识库", "入库")):
            return {"action": "kb_store", "args": {}}
        if any(word in question for word in ("知识库有哪些", "列出知识库", "知识库列表", "知识库文档")):
            return {"action": "kb_list"}
        if "删除" in question and "知识库" in question:
            return {"action": "kb_delete", "args": {}}
        if any(word in question for word in ("你记得", "长期记忆", "我的偏好")):
            return {"action": "memory_list"}
        if any(word in question for word in ("记住", "以后都", "我的习惯")):
            return {"action": "memory_add", "args": {"content": question, "category": "preference"}}
        if any(word in question for word in ("检索", "资料", "文档", "手册", "引用", "标准")):
            return {"action": "search", "query": question}
        return {"action": "answer",
                "answer": f"（桩模式）收到：{question}。在设置页配置真实模型后，我会给出完整回答。"}

    @staticmethod
    def _chat_answer(context: dict) -> dict:
        evidence = context.get("evidence") or []
        question = str(context.get("question") or "")
        if not evidence:
            return {"answer": f"资料里没有找到与「{question}」相关的内容。可以换一种问法，或上传相关文档后再试。",
                    "used_citations": []}
        titles = "；".join(str(item.get("title")) for item in evidence[:3])
        ids = [str(item.get("id")) for item in evidence[:3]]
        return {"answer": f"根据检索到的资料（{titles}），与「{question}」相关的内容如下："
                          f"{evidence[0].get('snippet', '')[:200]}",
                "used_citations": ids}

    @staticmethod
    def _chat_summary(context: dict) -> dict:
        history = context.get("history") or []
        parts = [f"{item.get('role')}: {str(item.get('content'))[:80]}" for item in history[-6:]]
        summary = (str(context.get("summary") or "") + " " + " / ".join(parts)).strip()
        return {"summary": summary[:200]}

    @staticmethod
    def _chat_compact(context: dict) -> dict:
        """桩模式压缩：保留早期摘要 + 折叠消息的首段，作为新摘要。"""
        history = context.get("history") or []
        lines = [f"{item.get('role')}: {str(item.get('content'))[:80]}" for item in history]
        merged = (str(context.get("summary") or "") + " " + " / ".join(lines)).strip()
        return {"summary": merged[:600]}

    @staticmethod
    def _chat_memory(context: dict) -> dict:
        """桩模式不做自动记忆抽取（可用 /remember 手动写入）。"""
        return {"memories": []}

    def text_stream(self, step: str, context: dict):
        """桩模式的流式回答：确定性文本分块下发。"""
        question = str(context.get("question") or "")
        evidence = context.get("evidence") or []
        if evidence:
            titles = "；".join(str(item.get("title")) for item in evidence[:3])
            text = (f"根据检索到的资料（{titles}），与「{question}」相关的内容如下："
                    f"{str(evidence[0].get('snippet') or '')[:200]}")
        else:
            text = f"（桩模式）收到：{question}。在设置页配置真实模型后，我会给出完整回答。"
        for index in range(0, len(text), 6):
            yield text[index:index + 6]

    # ------------------------------------------------------------- S8 叙述
    @staticmethod
    def _s8_narrative(context: dict) -> dict:
        mission = context["mission_request"]
        return {
            "1_overview": "本方案面向「" + mission["goal"] + "」，输出了总体构型、分系统配置与各项预算。"
                          "轨道设计高度 {{mission.altitude_km}} km，设计寿命 {{mission.lifetime_years}} 年。",
            "4_mass": "质量预算按分系统分解并预留方案期余量，详见下表。整星质量（含余量）为 {{mass.total_with_margin}} kg。",
            "5_power": "功耗预算覆盖光照与阴影两种工况，轨道平均功耗 {{power.p_avg_w}} W，电池容量需求 {{power.battery_capacity_wh}} Wh。",
            "6_data": "数据量预算按载荷数据率与压缩比估算，单圈数据量 {{data.per_orbit_gb}} GB，每日 {{data.per_day_gb}} GB。",
            "11_risk": "风险分析基于公开经验教训库（LLIS）与历史型号统计，详见风险表（骨架阶段为占位内容）。",
        }

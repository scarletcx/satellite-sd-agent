"""桩 Provider：确定性输出，供 CI / 离线演示 / 骨架联调（docs/05 §7、docs/11 §2）。

内容与 E2E-01（500km SSO 光学遥感小卫星）对齐；真实模型接入后本文件仅用于测试回放。
"""
from __future__ import annotations


class StubProvider:
    name = "stub"

    def available(self) -> bool:
        return True

    def chat_json(self, step: str, context: dict) -> tuple[dict, dict]:
        handler = {
            "S1": self._s1_parse,
            "S3": self._s3_decompose,
            "S4": self._s4_params,
            "S8": self._s8_narrative,
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

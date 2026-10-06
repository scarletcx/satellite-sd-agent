# 06 计算与校验引擎设计

| 项目 | 内容 |
|---|---|
| 状态 | 细化 |
| 优先级 | P0 |
| 负责人 | 待定 |
| 最后更新 | 2026-10-05 |
| 关联文档 | [03 数据模型](./03-data-model.md) · [05 编排](./05-agent-orchestration.md) · [11 测试计划](./11-test-plan.md) |

> 本文档是计算与校验的实现规格。
> 常量统一放 `app/tools/calc/constants.py`：`μ=398600.4418`、`Re=6378.137 km`、`J2=1.08263e-3`、`c=299792458 m/s`、`k=1.380649e-23 J/K（-228.6 dB）`、`E0=1361 W/m²`

## 1. 原则

1. LLM 不得直接输出数值结论，只能提出**计算请求**（参数 + 假设）。
2. 每个公式有文献 / 标准出处，可被第三方复算。
3. 校验路径与生成路径**相互独立**（不能自己证明自己）。
4. 校验结论分三级：`pass` / `warn`（带余量提示）/ `block`（禁止进文档）。

## 2. 计算模块详细规格

> 各模块统一要求：输入经 JSON Schema 校验（缺项即拒绝）；输出写入 IR 并附 `units_map`；错误返回结构化缺失清单。

### C1 质量预算（`calc.mass_budget`）

- **输入**：`items[{name, mass_kg>0, margin, source_ref}]`、`propellant_kg≥0`、`margin_policy{phase: 方案|初样, pct}`
- **公式**：`dry = Σ item.mass_kg`；`total = dry + propellant`；`margin_mass = total × pct`；`total_with_margin = total + margin_mass`
- **输出**：`mass.dry / mass.propellant / mass.total / mass.margin_pct / mass.total_with_margin`（kg）
- **余量**：方案期 ≥20%，初样期 ≥10%（低于 → V3 warn/block）
- **边界**：空清单、负值、`margin_policy` 缺失 → 拒绝

### C2 功耗与能量平衡（`calc.power_budget`）

- **输入**：`loads[{name, phase: sun|ecl|both, power_w≥0, duty_pct 0~100}]`、`orbit{T_orbit_min>0, T_ecl_min≥0}`、`battery{dod 0~1, eta_out 0~1}`
- **公式**：
  - `P_phase = Σ power_w × duty_pct/100`（按 phase 归类）
  - `P_avg = (P_sun × T_sun + P_ecl × T_ecl) / T_orbit`，`T_sun = T_orbit − T_ecl`
  - `E_ecl_wh = P_ecl × T_ecl / 60`
  - `C_batt_wh = E_ecl_wh / (dod × eta_out)`
- **输出**：`power.p_sun_w / p_ecl_w / p_avg_w / e_ecl_wh / battery.capacity_wh`；能量平衡标志（充电功率是否覆盖 E_ecl + 充电损耗）
- **边界**：`T_ecl ≥ T_orbit`、`duty>100`、负功率 → 拒绝

### C3 数据量预算（`calc.data_budget`）

- **输入**：`payload{rate_mbps>0, imaging_min_per_orbit≥0, compression_ratio≥1}`、`downlink{rate_mbps, window_min_per_day}`、`storage_cycles`（默认 2）
- **公式**（十进制单位：1 GB = 8000 Mb）：
  - `D_orbit_gb = rate_mbps × imaging_s / (8×1000 × compression_ratio)`
  - `D_day_gb = D_orbit_gb × orbits_per_day`
  - `D_down_gb = downlink_rate × window_s / 8000`
  - `storage_required_gb = max(storage_cycles × D_orbit_gb, D_day_gb − D_down_gb)`
- **输出**：`data.per_orbit_gb / per_day_gb / downlink_capacity_gb / storage_required_gb`
- **余量**：存储 ≥ 计算需求 ×1.2（不足 → V3 block）

### C4 链路预算（`calc.link_budget`）

- **输入**：`freq_ghz>0`、`slant_km>0`、`eirp_dbw`、`gt_db_per_k`、`data_rate_kbps>0`、`required_ebn0_db`（调制编码门限）、`rain_margin_db`、`other_losses_db`、`min_margin_db`（默认 3）
- **公式**：
  - `λ = c / (f×1e9)`；`L_fs_db = 20 lg(4π × d_m / λ)`
  - `Eb/N0 = EIRP + G/T − L_fs − L_atm(rain) − L_other − 10 lg(R_b) − 10 lg(k)`（即 `+228.6`）
  - `margin_db = Eb/N0 − required_ebn0_db`
- **输出**：`link.l_fs_db / ebn0_db / margin_db`
- **判定**：`margin_db ≥ min_margin_db` 为 pass；`0 ≤ margin < min` → warn；`<0` → block
- **边界**：缺 `required_ebn0_db` → 拒绝（不得默认放行）

### C5 轨道与覆盖（`calc.orbit`）

- **输入**：`orbit{alt_km, inc_deg, e≈0}`、`station{lat, lon, min_elevation_deg(默认5)}`
- **公式要点**：
  - `a = Re + alt`；`n = √(μ/a³)`；`T = 2π/n`
  - J2 交点退行：`Ω̇ = −1.5 × J2 × n × (Re/a)² × cos(i)`（SSO 校验：`Ω̇ ≈ +0.9856°/day`）
  - 可见性：时间步进（步长 ≤30s）计算站星仰角 `el(t) ≥ ε`，合并成窗口
- **输出**：`orbit.period_min / sso_ok / windows_per_day / revisit_avg_h / max_gap_h`
- **交叉验证（V2）**：与开源库（brahe / tudatpy / skyfield，开发期对拍选定）比较：周期 ±0.1%、窗口数 ±10%
- **声明**：简化模型（二体 + J2 长期项），不适用高精度任务；误差范围写入输出文档（ADR-0004）

### C6 太阳翼与电池尺寸（`calc.eps`）

- **输入**：`power.p_eol_w`（或由 C2 提供 `p_avg + 充电功率`）、`life_years`、`degradation_per_year`、`cell_efficiency`、`packing_factor`、`sun_angle_cos`（默认 0.9）、`margin_pct`
- **公式**：`P_bol = P_eol / (1−deg)^life`；`A_m2 = P_bol / (E0 × η_cell × packing × cosθ) × (1+margin)`
- **输出**：`power.sa.area`（m²）、`power.p_bol_w`
- **边界**：`deg≤0` 或 `≥1`、`η≤0` → 拒绝

### C7 ADCS 能力粗算（`calc.adcs`）

- **输入**：`inertia_kgm2`、`alt_km`、`cross_area_m2`、`residual_dipole_am2`、`slew_angle_deg`、`slew_time_s`
- **公式（简化）**：扰动力矩 `T_dist = T_gg + T_aero + T_mag`，其中 `T_gg = 1.5 × μ × |I_diff| / a³`；`T_aero = 0.5 × ρ(h) × v² × Cd × A × l`（指数大气 ρ）；`T_mag = m_res × B`（B ≈ 3e-5 T 低轨近似）
- **输出**：`adcs.torque_required_nm`、`adcs.momentum_nms = T × t_hold × 设计裕度2`
- **边界**：缺任一输入 → 拒绝；结论仅为「能力级核对」，非详细设计

### C8 预留

热 / 结构仅做**约束检查**（包络、温度区间），本期不实现计算。

## 3. 单位与数值规范

- 单位 SI 为主，枚举化管理（[03](./03-data-model.md) §4）；换算集中 `app/tools/calc/units.py`
- 有效数字：内部全精度；输出保留 3 位有效数字（表格可定制）
- 容差 / 阈值（初值，标定后更新）：

| 项 | 阈值 |
|---|---|
| 数值一致性（汇总 = 分项和） | ±0.5% |
| 跨模块一致性 | ±5% |
| 链路余量 | ≥ 3 dB |
| 质量 / 功耗余量 | ≥ 10%（方案期质量 ≥20%） |
| 数据存储余量 | ≥ 20% |
| 轨道交叉验证 | 周期 ±0.1%，窗口 ±10% |

## 4. 校验规则详细规格

### V1 Schema / 单位 / 量纲

- **输入**：待入库对象
- **判定**：① JSON Schema 校验；② `unit` ∈ 枚举；③ 公式输入输出量纲与签名一致（按 `units_map`）
- **输出 evidence**：`{field, expected, got}`；失败消息模板：`字段 {field} 应为 {expected}，实际 {got}`

### V2 独立重算

- **输入**：预算对象 / 轨道结果
- **判定**：
  1. 预算：独立求和分项与汇总对比（±0.5%）
  2. 轨道：自研模型 vs 交叉验证库（周期 ±0.1%、窗口 ±10%）
- **输出**：`{a, b, diff_pct, tolerance_pct}`

### V3 预算闭合与余量

- **判定**：汇总 = 分项和（±0.5%）；各项余量 ≥ §3 阈值；出现负余量 → block
- **输出**：`{expected, actual, tolerance_pct, margin_pct, threshold}`

### V4 跨模块一致性（规则清单）

| # | 检查 | 容差 |
|---|---|---|
| 1 | `power.sa.area` ↔ `power.p_bol_w` ↔ `power.sa.mass` | ±5% |
| 2 | `data.per_day_gb` ↔ `data.storage_required_gb` ↔ 下行能力 | ±5% |
| 3 | `mass.total_with_margin` ≤ `constraints.mass_limit_kg` | 超出即 block |
| 4 | `power.p_avg_w` ≤ `constraints.power_limit_w`（如有） | 超出即 warn → block 需门禁 |
| 5 | 包络：`system-design.envelope_mm` ↔ 各分系统几何声明 | 超包络 block |

### V5 历史型号对比（P1）

- **判定**：将 `mass.total / power.p_avg_w / data.per_day_gb / orbit.revisit_avg_h` 与 UCS / GCAT 同类任务分布对比；落在 P10~P90 之外 → warn
- **输出**：`{param, value, p10, p90, percentile}`

### V6 敏感性分析（P1）

- **判定**：对关键假设（电池效率、占空比、压缩比、余量口径）±10% 重跑受影响计算；结论翻转（越阈值）→ warn
- **输出**：`{assumption, delta_pct, flipped: bool, impacted_params[]}`

### V7 假设台账核对

- **判定**：所有 `verified` 参数引用的 assumption 必须 `confirmed`；否则 → block 该参数入稿
- **输出**：`{param_id, assumption_id, status}`

## 5. 判级与处置

| 结论 | 触发条件 | 流程动作 |
|---|---|---|
| pass | 全部规则通过 | 参数置 `verified`（仍需人工门禁确认） |
| warn | 余量偏小 / 离群但可解释 | 文档中标注 + 人工确认后放行 |
| block | 规则硬性失败 | 冻结参数、差异报告、禁止渲染进 Word、转门禁 |

## 6. 对抗用例库

| # | 用例 | 注入方式（fixture） | 期望行为 |
|---|---|---|---|
| ADV-01 | 「太阳翼面积 5.2 m²，无计算过程」 | S4 桩输出直给数值 | 拦截：要求计算请求 → V2/V3 复算不一致 → block |
| ADV-02 | 单位混用（W vs kW） | 参数 `unit` 篡改 | V1 block |
| ADV-03 | 预算不闭合（汇总 ≠ 分项和） | 篡改汇总 | V3 block |
| ADV-04 | 编造引用 | 引用不在检索集合 | 引用白名单丢弃 → 判定无依据 |
| ADV-05 | 检索为空仍给结论 | S2 返回空 + S8 给出具体参数 | 输出「无依据」，转门禁 |
| ADV-06 | 上游变更后旧数据被引用 | 修改 `cell_efficiency` 后不重算 | `upstream_hash` 不一致 → `needs_review` |
| ADV-07 | 语料注入（「忽略以上指令」） | 语料文件埋入指令 | 行为不变 + 告警（[13](./13-security.md)） |

## 7. 实现与代码映射

| 模块 | 代码位置 | 状态 |
|---|---|---|
| C1~C3 预算 | `app/tools/calc/budgets.py` | ✅ 已实现 |
| C4 链路 | `app/tools/calc/link.py` | ✅ 已实现 |
| C5 轨道覆盖 | `app/tools/calc/orbit.py` | ✅ 已实现（简化模型；库交叉验证待接） |
| C6 太阳翼 | `app/tools/calc/eps.py` | ✅ 已实现 |
| C7 ADCS 粗算 | `app/tools/calc/adcs.py` | 待开发（P1） |
| 常量与换算 | `app/tools/calc/constants.py` · `units.py` | ✅ 已实现 |
| V1 / V3 / V4 / V7 | `app/validation/rules.py` | ✅ V1 含引用完整性；V7 为 warn 级（确认门禁流程待接） |
| V2 独立重算 | `app/validation/recompute.py` | ✅ 六类计算记录全部重算比对（容差 0.5%） |
| V5 历史对比 | `app/validation/history.py` + `make reference` | ✅ 基于 UCS 公开统计（LEO 10-500kg，P10~P90） |
| V6 敏感性 | `app/validation/sensitivity.py` | ✅ 质量 +10% / 链路 +2 dB 两类扰动 |

> S5 实际执行顺序：**C5 轨道 → C1 质量 → C2 功耗 → C6 太阳翼 → C3 数据量 → C4 链路**（依赖驱动；C3 的 `orbits_per_day` 采用 C5 输出）。

## 8. 关键取舍

| 决策 | 备选 | 理由 | ADR |
|---|---|---|---|
| 自研简化模型 + 库交叉验证 | 高保真库为主 | 校验独立、依赖轻 | [0004](./adr/0004-orbit-computation.md) |
| 阈值 / 容差用初值起步 | 精确定标 | 先跑通闭环，标定后更新本文档 | — |
| 拒绝「默认放行」 | 缺失时用经验值 | 缺输入即拒绝，防止静默错误 | — |

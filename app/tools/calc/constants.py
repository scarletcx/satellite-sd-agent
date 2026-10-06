"""物理常量（docs/06 §1 统一出处）。"""
from __future__ import annotations

MU_EARTH_KM3_S2 = 398600.4418  # 地球引力常数 μ
RE_KM = 6378.137               # 地球赤道半径
J2 = 1.08263e-3                # 地球扁率摄动项
C_M_S = 299792458.0            # 光速
K_BOLTZMANN = 1.380649e-23     # 玻尔兹曼常数
K_DBW = -228.6                 # 10·lg(k)，dBW/K/Hz
E0_W_M2 = 1361.0               # 太阳常数

# 公式版本（写入 CalculationRecord，保证可复现）
FORMULA_VERSIONS = {
    "calc.mass_budget": "mass-v1",
    "calc.power_budget": "power-v1",
    "calc.data_budget": "data-v1",
    "calc.orbit": "orbit-v1",
    "calc.link_budget": "link-v1",
    "calc.eps": "eps-v1",
}

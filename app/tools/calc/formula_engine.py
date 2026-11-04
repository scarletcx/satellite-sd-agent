"""安全公式求值器：只允许数字、变量、四则运算、幂和少量数学函数。

不执行任意 Python：禁止属性访问、下标、推导式、lambda、比较、导入等。
公式保存前用示例上下文试算；计算时用真实上下文求值。
"""
from __future__ import annotations

import ast
import math
from typing import Any

from app.tools.calc.adcs import MIN_MAGNETIC_FIELD_T, RADIATION_PRESSURE_N_M2
from app.tools.calc.constants import (
    C_M_S,
    E0_W_M2,
    J2,
    K_DBW,
    MU_EARTH_KM3_S2,
    RE_KM,
)


class FormulaError(ValueError):
    """公式语法/变量/计算错误。"""


FUNCTIONS = {
    "sqrt": math.sqrt,
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "min": min,
    "max": max,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "radians": math.radians,
    "degrees": math.degrees,
    "round": round,
}

CONSTANTS = {
    "pi": math.pi,
    "RE_KM": RE_KM,
    "MU_EARTH_KM3_S2": MU_EARTH_KM3_S2,
    "J2": J2,
    "C_M_S": C_M_S,
    "K_DBW": K_DBW,
    "E0_W_M2": E0_W_M2,
    "P0": RADIATION_PRESSURE_N_M2,
    "B_MIN": MIN_MAGNETIC_FIELD_T,
}

CONSTANT_META = {
    "pi": ("圆周率", ""),
    "RE_KM": ("地球赤道半径", "km"),
    "MU_EARTH_KM3_S2": ("地球引力常数", "km³/s²"),
    "J2": ("地球扁率摄动项", ""),
    "C_M_S": ("光速", "m/s"),
    "K_DBW": ("10·lg(k)", "dBW/K/Hz"),
    "E0_W_M2": ("太阳常数", "W/m²"),
    "P0": ("1 AU 太阳辐射压", "N/m²"),
    "B_MIN": ("低轨磁感应强度低值", "T"),
}

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
    ast.Mod: lambda a, b: a % b,
}
_UNARY_OPS = {ast.UAdd: lambda a: a, ast.USub: lambda a: -a}


def _eval(node: ast.AST, context: dict[str, Any]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, context)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FormulaError("公式只允许数字常量")
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in context:
            value = context[node.id]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise FormulaError(f"变量 {node.id} 不是数值")
            return float(value)
        if node.id in CONSTANTS:
            return float(CONSTANTS[node.id])
        raise FormulaError(f"未知变量：{node.id}")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise FormulaError("不支持的运算符")
        try:
            return op(_eval(node.left, context), _eval(node.right, context))
        except ZeroDivisionError as exc:
            raise FormulaError("公式出现除以零") from exc
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise FormulaError("不支持的一元运算符")
        return op(_eval(node.operand, context))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise FormulaError("只允许 sqrt/log10/exp/abs/min/max/sin/cos/tan/radians/degrees/round")
        if node.keywords:
            raise FormulaError("函数不支持关键字参数")
        args = [_eval(arg, context) for arg in node.args]
        try:
            return float(FUNCTIONS[node.func.id](*args))
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise FormulaError(f"函数 {node.func.id} 计算失败：{exc}") from exc
    raise FormulaError(f"不支持的表达式结构：{type(node).__name__}")


def evaluate(expression: str, context: dict[str, Any] | None = None) -> float:
    expression = (expression or "").strip()
    if not expression:
        raise FormulaError("公式不能为空")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"公式语法错误：{exc.msg}") from exc
    result = _eval(tree, dict(context or {}))
    if not math.isfinite(result):
        raise FormulaError("公式结果不是有限数值")
    return result


def sample_context(spec: dict) -> dict:
    return {**CONSTANTS, **dict(spec.get("sample_context") or {})}

"""
Safe Calculator Tool.

Evaluates mathematical expressions WITHOUT using eval() or exec().
Uses Python's ast module to parse and evaluate only safe numeric expressions.
"""

import ast
import math
import operator
from typing import Any, Dict

from tools.base import BaseTool, ToolResult, ToolParameter, PermissionLevel


# Allowed operators for safe evaluation
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Allowed math functions
_SAFE_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "ceil": math.ceil,
    "floor": math.floor,
    "pi": math.pi,
    "e": math.e,
    "pow": math.pow,
    "factorial": math.factorial,
}


def _safe_eval_node(node: ast.AST) -> Any:
    """Recursively evaluate an AST node using only safe operations."""
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        # Safety: prevent extreme exponentiation
        if op_type == ast.Pow and isinstance(right, (int, float)) and abs(right) > 1000:
            raise ValueError(f"Exponent too large: {right}. Max allowed: 1000")
        return _SAFE_OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return _SAFE_OPERATORS[op_type](_safe_eval_node(node.operand))

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in _SAFE_FUNCTIONS:
                raise ValueError(f"Function '{func_name}' is not allowed. Allowed: {list(_SAFE_FUNCTIONS.keys())}")
            func = _SAFE_FUNCTIONS[func_name]
            args = [_safe_eval_node(arg) for arg in node.args]
            return func(*args)
        raise ValueError("Only named function calls are supported (e.g., sqrt(16))")

    if isinstance(node, ast.Name):
        name = node.id
        if name in _SAFE_FUNCTIONS and not callable(_SAFE_FUNCTIONS[name]):
            return _SAFE_FUNCTIONS[name]  # Constants like pi, e
        raise ValueError(f"Unknown variable: '{name}'. Use numbers or allowed functions.")

    raise ValueError(f"Unsupported expression type: {type(node).__name__}")


def safe_calculate(expression: str) -> Any:
    """Parse and evaluate a math expression safely."""
    expression = expression.strip()
    if not expression:
        raise ValueError("Empty expression")
    if len(expression) > 500:
        raise ValueError("Expression too long (max 500 characters)")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid mathematical expression: {e}")

    return _safe_eval_node(tree)


class CalculatorTool(BaseTool):
    """Safe mathematical calculator.

    Evaluates arithmetic expressions, trigonometry, logarithms, and
    basic math functions WITHOUT using eval() or exec().
    """

    name = "calculator"
    description = (
        "Evaluates mathematical expressions safely. Supports: "
        "+, -, *, /, //, %, ** (power), sqrt, sin, cos, tan, log, log2, log10, "
        "ceil, floor, abs, round, min, max, factorial, pi, e."
    )
    category = "math"
    permission = PermissionLevel.SAFE
    parameters = [
        ToolParameter(
            name="expression",
            type="string",
            description="Mathematical expression to evaluate, e.g. 'sqrt(144) + 3 * pi'",
            required=True,
        ),
    ]

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        expression = str(params.get("expression", ""))
        try:
            result = safe_calculate(expression)
            return ToolResult(
                success=True,
                output={
                    "expression": expression,
                    "result": result,
                    "type": type(result).__name__,
                },
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except ZeroDivisionError:
            return ToolResult(success=False, error="Division by zero")
        except OverflowError:
            return ToolResult(success=False, error="Result too large (overflow)")

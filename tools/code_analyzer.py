"""
Code Analyzer Tool.

Analyzes Python source code structure without executing it.
Read-only static analysis: functions, classes, imports, complexity metrics.
"""

import ast
from pathlib import Path
from typing import Any, Dict, List

from tools.base import BaseTool, ToolResult, ToolParameter, PermissionLevel

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BLOCKED_NAMES = {".env", ".git", "__pycache__", ".venv"}


class CodeAnalyzerTool(BaseTool):
    """Static Python code analyzer.

    Parses Python files using the ast module to extract structure
    (functions, classes, imports, docstrings) and compute basic
    complexity metrics — without ever executing the code.
    """

    name = "code_analyzer"
    description = (
        "Analyzes Python source files for structure (functions, classes, imports), "
        "docstrings, line counts, and basic complexity. Read-only, no code execution."
    )
    category = "code"
    permission = PermissionLevel.READ_ONLY
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Relative path to a Python file within the project (e.g., 'server.py')",
            required=False,
        ),
        ToolParameter(
            name="code",
            type="string",
            description="Raw Python source code to analyze (alternative to path)",
            required=False,
        ),
        ToolParameter(
            name="action",
            type="string",
            description="'structure' (default): full analysis. 'syntax': check syntax only.",
            required=False,
            default="structure",
        ),
    ]

    def validate_params(self, params: Dict[str, Any]) -> str | None:
        if not params.get("path") and not params.get("code"):
            return "Either 'path' or 'code' parameter is required."
        return None

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        action = str(params.get("action", "structure")).lower()
        source_code = None
        source_path = None

        # Get source code from path or direct input
        if params.get("path"):
            rel_path = str(params["path"])
            target = (_PROJECT_ROOT / rel_path).resolve()

            # Security check
            try:
                target.relative_to(_PROJECT_ROOT)
            except ValueError:
                return ToolResult(success=False, error="Access denied: outside project directory.")

            for part in target.parts:
                if part.lower() in _BLOCKED_NAMES:
                    return ToolResult(success=False, error=f"Access denied: '{part}' is restricted.")

            if not target.exists():
                return ToolResult(success=False, error=f"File not found: {rel_path}")
            if not target.suffix == ".py":
                return ToolResult(success=False, error="Only .py files can be analyzed.")

            try:
                source_code = target.read_text(encoding="utf-8")
                source_path = str(target.relative_to(_PROJECT_ROOT))
            except Exception as e:
                return ToolResult(success=False, error=f"Error reading file: {str(e)}")
        else:
            source_code = str(params.get("code", ""))
            source_path = "<inline>"

        if action == "syntax":
            return self._check_syntax(source_code, source_path)
        return self._analyze_structure(source_code, source_path)

    def _check_syntax(self, code: str, path: str) -> ToolResult:
        """Check if the code has valid Python syntax."""
        try:
            ast.parse(code)
            return ToolResult(
                success=True,
                output={"path": path, "syntax_valid": True, "errors": []},
            )
        except SyntaxError as e:
            return ToolResult(
                success=True,
                output={
                    "path": path,
                    "syntax_valid": False,
                    "errors": [{"line": e.lineno, "col": e.offset, "message": e.msg}],
                },
            )

    def _analyze_structure(self, code: str, path: str) -> ToolResult:
        """Full structural analysis of Python code."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return ToolResult(
                success=False,
                error=f"Syntax error at line {e.lineno}: {e.msg}",
            )

        functions: List[Dict] = []
        classes: List[Dict] = []
        imports: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                func_info = {
                    "name": node.name,
                    "line": node.lineno,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "args": [arg.arg for arg in node.args.args],
                    "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
                    "docstring": ast.get_docstring(node) or None,
                }
                functions.append(func_info)

            elif isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(item.name)
                classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "bases": [self._get_name(b) for b in node.bases],
                    "methods": methods,
                    "docstring": ast.get_docstring(node) or None,
                })

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")

        lines = code.splitlines()
        return ToolResult(
            success=True,
            output={
                "path": path,
                "total_lines": len(lines),
                "blank_lines": sum(1 for ln in lines if not ln.strip()),
                "comment_lines": sum(1 for ln in lines if ln.strip().startswith("#")),
                "functions": functions,
                "function_count": len(functions),
                "classes": classes,
                "class_count": len(classes),
                "imports": sorted(set(imports)),
                "import_count": len(set(imports)),
            },
        )

    @staticmethod
    def _get_decorator_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{CodeAnalyzerTool._get_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Call):
            return CodeAnalyzerTool._get_decorator_name(node.func)
        return "?"

    @staticmethod
    def _get_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{CodeAnalyzerTool._get_name(node.value)}.{node.attr}"
        return "?"

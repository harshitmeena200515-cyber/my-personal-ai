"""
Tests for Sandboxed Tool System.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.base import ToolRegistry, ToolResult, PermissionLevel
from tools.calculator import CalculatorTool, safe_calculate
from tools.file_reader import FileReaderTool
from tools.code_analyzer import CodeAnalyzerTool
from tools.system_info import SystemInfoTool
from tools.datetime_tool import DateTimeTool
from tools import tool_registry


def test_calculator_basic_and_advanced():
    """Verify safe mathematical evaluation."""
    calc = CalculatorTool()
    
    # Basic math
    res = asyncio.run(calc.execute({"expression": "2 + 2 * 3"}))
    assert res.success is True
    assert res.output["result"] == 8

    # Functions and constants
    res = asyncio.run(calc.execute({"expression": "sqrt(144) + log10(100) + abs(-5)"}))
    assert res.success is True
    assert res.output["result"] == 19.0

    # Division by zero
    res = asyncio.run(calc.execute({"expression": "10 / 0"}))
    assert res.success is False
    assert "zero" in res.error.lower()

    # Disallowed function
    res = asyncio.run(calc.execute({"expression": "open('test.txt')"}))
    assert res.success is False
    assert "not allowed" in res.error.lower()
    print("✅ test_calculator_basic_and_advanced PASSED")


def test_file_reader_security_and_reading():
    """Verify file reader operates inside sandbox and blocks sensitive paths."""
    reader = FileReaderTool()

    # Safe read
    res = asyncio.run(reader.execute({"path": "requirements.txt", "action": "read"}))
    assert res.success is True
    assert "fastapi" in res.output["content"]

    # Safe directory list
    res = asyncio.run(reader.execute({"path": "core", "action": "list"}))
    assert res.success is True
    assert res.output["count"] >= 3

    # BLOCKED: .env
    res = asyncio.run(reader.execute({"path": ".env", "action": "read"}))
    assert res.success is False
    assert "restricted" in res.error.lower() or "denied" in res.error.lower()

    # BLOCKED: .git
    res = asyncio.run(reader.execute({"path": ".git/config", "action": "read"}))
    assert res.success is False
    assert "restricted" in res.error.lower() or "denied" in res.error.lower()

    # BLOCKED: Path traversal outside project
    res = asyncio.run(reader.execute({"path": "../../Windows/System32", "action": "read"}))
    assert res.success is False
    assert "outside" in res.error.lower() or "denied" in res.error.lower()
    print("✅ test_file_reader_security_and_reading PASSED")


def test_code_analyzer():
    """Verify static Python code analysis without execution."""
    analyzer = CodeAnalyzerTool()

    # Analyze server.py
    res = asyncio.run(analyzer.execute({"path": "server.py", "action": "structure"}))
    assert res.success is True
    assert res.output["function_count"] >= 4
    assert "fastapi" in str(res.output["imports"])

    # Check syntax validation
    res = asyncio.run(analyzer.execute({"code": "def foo():\n    return 42", "action": "syntax"}))
    assert res.success is True
    assert res.output["syntax_valid"] is True

    # Check syntax error detection
    res = asyncio.run(analyzer.execute({"code": "def foo(:\n    return 42", "action": "syntax"}))
    assert res.success is True
    assert res.output["syntax_valid"] is False
    print("✅ test_code_analyzer PASSED")


def test_system_info():
    """Verify system info metrics collection."""
    sys_tool = SystemInfoTool()
    res = asyncio.run(sys_tool.execute({"category": "all"}))
    assert res.success is True
    assert "hardware" in res.output
    assert "software" in res.output
    assert "RTX 3050" in res.output["hardware"]["gpu"]
    assert res.output["hardware"]["cpu_count"] > 0
    print("✅ test_system_info PASSED")


def test_datetime_tool():
    """Verify date/time calculations."""
    dt_tool = DateTimeTool()

    # Now
    res = asyncio.run(dt_tool.execute({"action": "now"}))
    assert res.success is True
    assert "date" in res.output
    assert "time" in res.output

    # Add duration
    res = asyncio.run(dt_tool.execute({"action": "add", "days": 7, "hours": 2}))
    assert res.success is True
    assert "result" in res.output

    # Difference
    res = asyncio.run(dt_tool.execute({
        "action": "diff",
        "date_str": "2026-01-01T00:00:00",
        "date_str_2": "2026-01-11T00:00:00"
    }))
    assert res.success is True
    assert res.output["difference_days"] == 10
    print("✅ test_datetime_tool PASSED")


def test_tool_registry():
    """Verify tool registry lookup, validation, and execution."""
    assert tool_registry.has_tool("calculator")
    assert tool_registry.has_tool("file_reader")
    assert tool_registry.has_tool("code_analyzer")
    assert tool_registry.has_tool("system_info")
    assert tool_registry.has_tool("datetime")
    assert len(tool_registry.list_tools()) == 5

    # Safe execute unknown tool
    res = asyncio.run(tool_registry.execute("unknown_tool", {}))
    assert res.success is False
    assert "not found" in res.error.lower()
    print("✅ test_tool_registry PASSED")


if __name__ == "__main__":
    test_calculator_basic_and_advanced()
    test_file_reader_security_and_reading()
    test_code_analyzer()
    test_system_info()
    test_datetime_tool()
    test_tool_registry()
    print("ALL TOOL TESTS PASSED!")

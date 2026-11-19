"""
Tool System Package Initialization.

Registers all available sandboxed tools and exposes the global registry.
"""

from tools.base import ToolRegistry, ToolResult, ToolInfo, BaseTool, PermissionLevel
from tools.calculator import CalculatorTool
from tools.file_reader import FileReaderTool
from tools.code_analyzer import CodeAnalyzerTool
from tools.system_info import SystemInfoTool
from tools.datetime_tool import DateTimeTool


def create_tool_registry() -> ToolRegistry:
    """Create and populate the global tool registry with all Phase 3 tools."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(FileReaderTool())
    registry.register(CodeAnalyzerTool())
    registry.register(SystemInfoTool())
    registry.register(DateTimeTool())
    return registry


# Global singleton registry
tool_registry = create_tool_registry()

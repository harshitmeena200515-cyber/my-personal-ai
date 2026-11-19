"""
Tool System Foundation for MY PERSONAL AI.

Provides BaseTool, ToolResult, ToolInfo, and ToolRegistry — the core abstractions
for the sandboxed tool execution layer.

Security Model:
  - All tools are explicitly registered.
  - Each tool declares its own parameter schema and permission level.
  - The registry validates inputs before execution.
  - No arbitrary code execution.
"""

import time
import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from core.logging import logger


class PermissionLevel(str, Enum):
    """Permission tiers for tool execution."""
    SAFE = "safe"                   # No side effects, always allowed
    READ_ONLY = "read_only"        # Reads data, no modifications
    RESTRICTED = "restricted"       # Requires user approval before execution


class ToolResult(BaseModel):
    """Standardized result returned by every tool execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    tool_name: str = ""


class ToolParameter(BaseModel):
    """Schema for a single tool parameter."""
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None


class ToolInfo(BaseModel):
    """Public metadata about a tool for display and planning."""
    name: str
    description: str
    category: str = "general"
    permission: PermissionLevel = PermissionLevel.SAFE
    parameters: List[ToolParameter] = Field(default_factory=list)


class BaseTool(ABC):
    """Abstract base class all tools must inherit."""

    name: str = "unnamed_tool"
    description: str = "No description."
    category: str = "general"
    permission: PermissionLevel = PermissionLevel.SAFE
    parameters: List[ToolParameter] = []

    def get_info(self) -> ToolInfo:
        """Return public metadata about this tool."""
        return ToolInfo(
            name=self.name,
            description=self.description,
            category=self.category,
            permission=self.permission,
            parameters=self.parameters,
        )

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute the tool with the given parameters. Must be overridden."""
        ...

    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        """Validate incoming parameters against the declared schema.
        Returns an error message string if invalid, or None if valid.
        """
        for p in self.parameters:
            if p.required and p.name not in params:
                return f"Missing required parameter: '{p.name}'"
        return None

    async def safe_execute(self, params: Dict[str, Any], timeout: float = 30.0) -> ToolResult:
        """Execute with validation, timeout enforcement, and error capture."""
        # 1. Validate parameters
        validation_error = self.validate_params(params)
        if validation_error:
            return ToolResult(
                success=False,
                error=validation_error,
                tool_name=self.name,
            )

        # 2. Execute with timeout
        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(self.execute(params), timeout=timeout)
            result.execution_time_ms = round((time.perf_counter() - start) * 1000, 2)
            result.tool_name = self.name
            return result
        except asyncio.TimeoutError:
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            logger.warning("tool_timeout", tool=self.name, timeout_sec=timeout)
            return ToolResult(
                success=False,
                error=f"Tool '{self.name}' timed out after {timeout}s",
                execution_time_ms=elapsed,
                tool_name=self.name,
            )
        except Exception as e:
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            logger.error("tool_execution_error", tool=self.name, error=str(e))
            return ToolResult(
                success=False,
                error=f"Tool '{self.name}' error: {str(e)}",
                execution_time_ms=elapsed,
                tool_name=self.name,
            )


class ToolRegistry:
    """Central registry for all available tools.

    Tools must be explicitly registered. The registry handles:
      - Registration and lookup.
      - Input validation before execution.
      - Permission checking.
      - Execution with timeout and error capture.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance by its name."""
        if tool.name in self._tools:
            logger.warning("tool_already_registered", tool=tool.name)
        self._tools[tool.name] = tool
        logger.info("tool_registered", tool=tool.name, permission=tool.permission.value)

    def get(self, name: str) -> Optional[BaseTool]:
        """Look up a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolInfo]:
        """Return metadata for all registered tools."""
        return [t.get_info() for t in self._tools.values()]

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    async def execute(
        self,
        name: str,
        params: Dict[str, Any],
        timeout: float = 30.0,
    ) -> ToolResult:
        """Look up and execute a tool by name with safety wrappers."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' not found in registry. Available: {list(self._tools.keys())}",
                tool_name=name,
            )
        return await tool.safe_execute(params, timeout=timeout)

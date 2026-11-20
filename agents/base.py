"""
Base Agent Interface and Data Contracts for MY PERSONAL AI (Milestone E).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from agents.context import SharedContext


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED_AWAITING_APPROVAL = "BLOCKED_AWAITING_APPROVAL"


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class AgentTask:
    task_id: str
    description: str
    assigned_to: str
    status: AgentStatus = AgentStatus.IDLE
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    agent_name: str
    task_id: str
    status: AgentStatus
    output: str
    risk_level: RiskLevel = RiskLevel.SAFE
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class BaseAgent(ABC):
    """Abstract Base Class for all specialized autonomous agents."""

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        allowed_tools: Optional[List[str]] = None,
        max_iterations: int = 5,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools or []
        self.max_iterations = max_iterations

    def can_use_tool(self, tool_name: str) -> bool:
        """Verify whether this agent is permitted to execute the named tool."""
        return tool_name in self.allowed_tools

    @abstractmethod
    async def execute(self, task: str, context: SharedContext) -> AgentResult:
        """Execute the assigned task within the shared blackboard context."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize agent specification for API and UI rendering."""
        return {
            "name": self.name,
            "role": self.role,
            "allowed_tools": self.allowed_tools,
            "max_iterations": self.max_iterations,
        }

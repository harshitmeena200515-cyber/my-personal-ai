"""
Agent Registry and Routing Engine for MY PERSONAL AI (Milestone E).
"""

import threading
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from core.logging import logger


class AgentRegistry:
    """Singleton registry for autonomous agents with intelligent intent-based routing."""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._lock = threading.RLock()

    def register(self, agent: BaseAgent) -> None:
        """Register an agent in the system."""
        with self._lock:
            self._agents[agent.name] = agent
            logger.info("agent_registered", name=agent.name, role=agent.role)

    def get(self, name: str) -> Optional[BaseAgent]:
        """Retrieve an agent by its unique name."""
        with self._lock:
            return self._agents.get(name)

    def list_agents(self) -> List[Dict[str, Any]]:
        """Return metadata for all registered agents."""
        with self._lock:
            return [agent.to_dict() for agent in self._agents.values()]

    def route_task(self, intent: str, task_text: str) -> BaseAgent:
        """Route an incoming task to the most appropriate specialized agent."""
        with self._lock:
            text_lower = task_text.lower()
            intent_lower = intent.lower()

            # 1. Cybersecurity Agent
            cyber_keywords = ["security", "audit", "vulnerability", "cve", "auth", "permission", "sandbox", "token", "hash"]
            if any(k in text_lower for k in cyber_keywords) or "security" in intent_lower:
                if "cybersec_agent" in self._agents:
                    return self._agents["cybersec_agent"]

            # 2. Coding Agent
            code_keywords = ["code", "function", "script", "refactor", "bug", "python", "fastapi", "class", "def ", "import "]
            if any(k in text_lower for k in code_keywords) or intent_lower in ("code_generation", "code_analysis"):
                if "coding_agent" in self._agents:
                    return self._agents["coding_agent"]

            # 3. Research Agent (default for system info, datetime, general math/queries)
            if "research_agent" in self._agents:
                return self._agents["research_agent"]

            # Fallback to any registered agent
            if self._agents:
                return next(iter(self._agents.values()))

            raise RuntimeError("No agents are currently registered in the AgentRegistry.")


# Singleton registry instance
agent_registry = AgentRegistry()

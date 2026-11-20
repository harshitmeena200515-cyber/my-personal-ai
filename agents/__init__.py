"""
Autonomous Agents Package for MY PERSONAL AI (Milestone E).
"""

from agents.base import AgentResult, AgentStatus, AgentTask, BaseAgent, RiskLevel
from agents.coding import CodingAgent
from agents.context import SharedContext
from agents.cybersec import CybersecurityAgent
from agents.registry import AgentRegistry, agent_registry
from agents.research import ResearchAgent

# Initialize and register core specialized agents
coding_agent = CodingAgent()
research_agent = ResearchAgent()
cybersec_agent = CybersecurityAgent()

agent_registry.register(coding_agent)
agent_registry.register(research_agent)
agent_registry.register(cybersec_agent)

__all__ = [
    "AgentResult",
    "AgentStatus",
    "AgentTask",
    "BaseAgent",
    "RiskLevel",
    "SharedContext",
    "AgentRegistry",
    "agent_registry",
    "CodingAgent",
    "ResearchAgent",
    "CybersecurityAgent",
    "coding_agent",
    "research_agent",
    "cybersec_agent",
]

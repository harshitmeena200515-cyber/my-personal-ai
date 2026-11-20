"""
Autonomous Research and Inspection Agent for MY PERSONAL AI (Milestone E).
"""

from typing import Any, Dict

from agents.base import AgentResult, AgentStatus, BaseAgent, RiskLevel
from agents.context import SharedContext
from core.logging import logger
from models.router import model_router
from tools import tool_registry


class ResearchAgent(BaseAgent):
    """Specialized agent for data inspection, information synthesis, system telemetry, and mathematical analysis."""

    def __init__(self):
        super().__init__(
            name="research_agent",
            role="Autonomous Researcher & System Analyst",
            system_prompt=(
                "You are an autonomous research analyst. You inspect system states, summarize data accurately, "
                "and perform step-by-step analytical reasoning without hallucinations."
            ),
            allowed_tools=["file_reader", "system_info", "datetime", "calculator"],
            max_iterations=5,
        )

    async def execute(self, task: str, context: SharedContext) -> AgentResult:
        """Execute research task, optionally querying tools and writing findings to blackboard."""
        context.add_event(self.name, "task_started", {"task": task})
        logger.info("research_agent_executing", task=task[:60])

        task_lower = task.lower()
        tool_findings = {}

        # Heuristic tool execution when relevant
        if any(w in task_lower for w in ("hardware", "gpu", "system", "vram", "ram", "os")):
            sys_tool = tool_registry.get_tool("system_info")
            if sys_tool and self.can_use_tool("system_info"):
                res = sys_tool.execute()
                tool_findings["system_info"] = res.output

        if any(w in task_lower for w in ("date", "time", "today", "clock")):
            dt_tool = tool_registry.get_tool("datetime")
            if dt_tool and self.can_use_tool("datetime"):
                res = dt_tool.execute()
                tool_findings["datetime"] = res.output

        context_prompt = f"Task: {task}\n"
        if tool_findings:
            context_prompt += f"Observed Tool Outputs: {tool_findings}\n"

        try:
            response = await model_router.chat(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": context_prompt},
                ],
                model="qwen2.5-coder:3b",
                stream=False,
                temperature=0.2,
            )
            output = response.get("content", "")

            # Store in blackboard
            context.set("research_findings", tool_findings)
            context.set("research_summary", output)
            context.add_event(self.name, "task_completed", {"findings_count": len(tool_findings)})

            return AgentResult(
                agent_name=self.name,
                task_id=context.task_id,
                status=AgentStatus.SUCCESS,
                output=output,
                risk_level=RiskLevel.SAFE,
                metadata={"tool_findings": tool_findings},
            )
        except Exception as e:
            logger.error("research_agent_failed", error=str(e))
            context.add_event(self.name, "task_failed", {"error": str(e)})
            return AgentResult(
                agent_name=self.name,
                task_id=context.task_id,
                status=AgentStatus.FAILED,
                output="",
                risk_level=RiskLevel.SAFE,
                error=str(e),
            )

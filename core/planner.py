"""
Task Planning Engine for MY PERSONAL AI.

Converts complex goals into ordered, executable task plans.
Manages task states, dependencies, and progress tracking.

Security: The planner CANNOT generate steps involving:
  - Shell/PowerShell command execution
  - File writes or deletions
  - External network requests
  - System configuration changes
"""

import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from core.logging import logger
from core.reasoning import ReasoningResult


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskStep(BaseModel):
    """A single executable step within a task plan."""
    id: str
    action: str                    # "calculate", "read_file", "analyze_code", "think", "respond"
    description: str = ""
    tool: Optional[str] = None     # Tool name from registry, or None for LLM-only steps
    inputs: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class PlanStatus(str, Enum):
    PLANNED = "planned"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPlan(BaseModel):
    """An ordered plan of steps to achieve a goal."""
    goal: str
    steps: List[TaskStep] = Field(default_factory=list)
    status: PlanStatus = PlanStatus.PLANNED
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    final_answer: Optional[str] = None

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def progress_pct(self) -> float:
        if not self.steps:
            return 0.0
        return round(self.completed_steps / self.total_steps * 100, 1)

    def get_next_step(self) -> Optional[TaskStep]:
        """Return the next pending step whose dependencies are met."""
        completed_ids = {s.id for s in self.steps if s.status == StepStatus.COMPLETED}
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                if all(dep in completed_ids for dep in step.depends_on):
                    return step
        return None


# Allowed actions (blocklist enforcement)
_ALLOWED_ACTIONS = {
    "calculate", "read_file", "analyze_code", "get_system_info",
    "get_datetime", "think", "respond", "summarize", "verify",
}

# Allowed tools
_ALLOWED_TOOLS = {
    "calculator", "file_reader", "code_analyzer", "system_info", "datetime",
    None,  # LLM-only steps have no tool
}

# System prompt for plan generation
PLANNER_SYSTEM_PROMPT = """You are the Task Planner of an autonomous Personal AI.

Your job is to decompose a user's goal into a sequence of concrete, executable steps.

You MUST respond with ONLY a valid JSON object (no markdown, no explanation, no code fences).

Available tools: calculator, file_reader, code_analyzer, system_info, datetime
Available actions: calculate, read_file, analyze_code, get_system_info, get_datetime, think, respond, summarize, verify

JSON schema:
{
  "steps": [
    {
      "id": "step_1",
      "action": "one of the allowed actions",
      "description": "what this step does",
      "tool": "tool name or null for LLM-only steps",
      "inputs": {"param1": "value1"},
      "depends_on": ["step_ids this depends on"]
    }
  ]
}

Rules:
- Maximum 8 steps per plan.
- Each step must use only allowed actions and tools.
- The final step should be "respond" (synthesize answer for user).
- "think" steps use the LLM to reason (tool=null).
- "verify" steps check previous step outputs.
- For calculator: inputs must include "expression" (a math string).
- For file_reader: inputs must include "path" and optionally "action" (read/list/info).
- For code_analyzer: inputs must include "path" and optionally "action" (structure/syntax).
- For system_info: inputs may include "category" (all/hardware/software/disk/project).
- For datetime: inputs may include "action" (now/add/diff/format).
- NEVER include shell commands, file writes, network calls, or system changes.
- If the task cannot be done with available tools, use "think" to reason about it and "respond" to explain limitations."""


class TaskPlanner:
    """Converts complex goals into executable task plans.

    Uses the local model for plan generation with heuristic fallback.
    Validates plans against security constraints before returning.
    """

    def __init__(self, model_router):
        self.router = model_router

    async def create_plan(
        self,
        goal: str,
        reasoning: ReasoningResult,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> TaskPlan:
        """Generate a task plan for the given goal."""

        # 1. Try model-based planning
        try:
            plan = await self._model_plan(goal, reasoning)
            if plan and plan.steps:
                # Validate the plan
                plan = self._validate_and_sanitize(plan)
                logger.info(
                    "plan_created",
                    goal=goal[:80],
                    steps=len(plan.steps),
                )
                return plan
        except Exception as e:
            logger.warning("model_planning_failed", error=str(e))

        # 2. Fallback to heuristic planning
        plan = self._heuristic_plan(goal, reasoning)
        logger.info("plan_heuristic_fallback", steps=len(plan.steps))
        return plan

    async def _model_plan(self, goal: str, reasoning: ReasoningResult) -> Optional[TaskPlan]:
        """Use the local model to generate a plan."""
        from models.router import ChatRequest, ChatMessage

        context = (
            f"User's goal: {goal}\n"
            f"Intent: {reasoning.intent}\n"
            f"Complexity: {reasoning.complexity}/5\n"
            f"Suggested tools: {reasoning.suggested_tools}\n"
        )

        messages = [
            ChatMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
            ChatMessage(role="user", content=context),
        ]

        request = ChatRequest(messages=messages, temperature=0.1, stream=False)
        response = await self.router.route_chat(request)
        raw = response.content.strip()

        parsed = self._extract_json(raw)
        if not parsed or "steps" not in parsed:
            return None

        steps = []
        for i, step_data in enumerate(parsed["steps"][:8]):  # Max 8 steps
            step = TaskStep(
                id=step_data.get("id", f"step_{i + 1}"),
                action=str(step_data.get("action", "think")),
                description=str(step_data.get("description", "")),
                tool=step_data.get("tool"),
                inputs=dict(step_data.get("inputs", {})),
                depends_on=list(step_data.get("depends_on", [])),
            )
            steps.append(step)

        return TaskPlan(goal=goal, steps=steps)

    def _validate_and_sanitize(self, plan: TaskPlan) -> TaskPlan:
        """Validate plan steps against security constraints. Remove unsafe steps."""
        safe_steps = []
        for step in plan.steps:
            # Validate action
            if step.action not in _ALLOWED_ACTIONS:
                logger.warning("plan_blocked_action", action=step.action, step=step.id)
                step.action = "think"
                step.tool = None
                step.description = f"[SANITIZED] Original action '{step.action}' was blocked. Thinking instead."

            # Validate tool
            if step.tool not in _ALLOWED_TOOLS:
                logger.warning("plan_blocked_tool", tool=step.tool, step=step.id)
                step.tool = None

            # Block any inputs that look like shell commands
            for key, value in list(step.inputs.items()):
                if isinstance(value, str):
                    danger_patterns = ["exec(", "eval(", "os.system", "subprocess", "powershell", "cmd /c", "rm -rf", "del /f"]
                    if any(d in value.lower() for d in danger_patterns):
                        step.inputs[key] = "[BLOCKED]"
                        logger.warning("plan_blocked_input", key=key, step=step.id)

            safe_steps.append(step)

        plan.steps = safe_steps

        # Ensure there's a final respond step
        if not any(s.action == "respond" for s in plan.steps):
            plan.steps.append(TaskStep(
                id=f"step_{len(plan.steps) + 1}",
                action="respond",
                description="Synthesize final answer from previous steps.",
                tool=None,
                depends_on=[s.id for s in plan.steps],
            ))

        return plan

    def _heuristic_plan(self, goal: str, reasoning: ReasoningResult) -> TaskPlan:
        """Generate a simple plan based on reasoning results."""
        steps: List[TaskStep] = []

        # Step 1: Use suggested tools
        for i, tool in enumerate(reasoning.suggested_tools):
            tool_action_map = {
                "calculator": "calculate",
                "file_reader": "read_file",
                "code_analyzer": "analyze_code",
                "system_info": "get_system_info",
                "datetime": "get_datetime",
            }
            action = tool_action_map.get(tool, "think")
            steps.append(TaskStep(
                id=f"step_{i + 1}",
                action=action,
                description=f"Use {tool} to gather information.",
                tool=tool,
                inputs=self._guess_inputs(tool, goal),
                depends_on=[f"step_{i}" for i in range(1, i + 1)] if i > 0 else [],
            ))

        # If no tools suggested, add a think step
        if not steps:
            steps.append(TaskStep(
                id="step_1",
                action="think",
                description="Reason about the user's request.",
                tool=None,
            ))

        # Final respond step
        steps.append(TaskStep(
            id=f"step_{len(steps) + 1}",
            action="respond",
            description="Provide the final answer to the user.",
            tool=None,
            depends_on=[s.id for s in steps],
        ))

        return TaskPlan(goal=goal, steps=steps)

    def _guess_inputs(self, tool: str, goal: str) -> Dict[str, Any]:
        """Heuristic: guess tool inputs from the goal text."""
        if tool == "calculator":
            # Try to extract a math expression
            expr_match = re.search(r'[\d\.\+\-\*/\(\)\^]+', goal)
            return {"expression": expr_match.group(0) if expr_match else goal}
        elif tool == "file_reader":
            # Try to find a filename
            file_match = re.search(r'[\w/\\]+\.[\w]+', goal)
            return {"path": file_match.group(0) if file_match else ".", "action": "read"}
        elif tool == "code_analyzer":
            file_match = re.search(r'[\w/\\]+\.py', goal)
            return {"path": file_match.group(0) if file_match else "server.py"}
        elif tool == "system_info":
            return {"category": "all"}
        elif tool == "datetime":
            return {"action": "now"}
        return {}

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from model output."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        brace_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

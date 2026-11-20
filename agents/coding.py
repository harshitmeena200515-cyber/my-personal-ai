"""
Autonomous Coding Agent for MY PERSONAL AI (Milestone E).
"""

import ast
from typing import Any, Dict, Optional

from agents.base import AgentResult, AgentStatus, BaseAgent, RiskLevel
from agents.context import SharedContext
from core.logging import logger
from models.router import model_router


class CodingAgent(BaseAgent):
    """Specialized agent for software engineering, code generation, refactoring, and static syntax validation."""

    def __init__(self):
        super().__init__(
            name="coding_agent",
            role="Senior Software Engineer & Code Synthesizer",
            system_prompt=(
                "You are an expert software engineer specialized in clean, secure, PEP 8 Python and modern web code. "
                "Always generate robust, tested, and self-contained code. "
                "Never write code that accesses files outside sandboxes or imports dangerous primitives."
            ),
            allowed_tools=["code_analyzer", "file_reader", "calculator"],
            max_iterations=5,
        )

    def validate_python_syntax(self, code_str: str) -> Dict[str, Any]:
        """Perform static Python AST validation on generated code."""
        try:
            tree = ast.parse(code_str)
            return {
                "valid": True,
                "node_count": len(list(ast.walk(tree))),
                "error": None,
            }
        except SyntaxError as e:
            return {
                "valid": False,
                "node_count": 0,
                "error": f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}",
            }

    async def execute(self, task: str, context: SharedContext) -> AgentResult:
        """Synthesize code for the task, validate AST, and record results in the blackboard."""
        context.add_event(self.name, "task_started", {"task": task})
        logger.info("coding_agent_executing", task=task[:60])

        prompt = (
            f"Role: {self.role}\n"
            f"Task: {task}\n"
            "Provide clean, well-commented Python code satisfying the task. Return code enclosed in ```python ``` blocks."
        )

        try:
            response = await model_router.chat(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                model="qwen2.5-coder:3b",
                stream=False,
                temperature=0.2,
            )
            raw_content = response.get("content", "")

            # Extract python code if present
            code_blocks = []
            if "```python" in raw_content:
                parts = raw_content.split("```python")
                for p in parts[1:]:
                    code = p.split("```")[0].strip()
                    code_blocks.append(code)

            syntax_results = []
            for idx, c in enumerate(code_blocks):
                v = self.validate_python_syntax(c)
                syntax_results.append(v)
                if not v["valid"]:
                    logger.warning("coding_agent_ast_error", error=v["error"])

            # Store in blackboard
            context.set("last_generated_code", code_blocks[0] if code_blocks else raw_content)
            context.set("ast_validation", syntax_results)
            context.add_event(self.name, "task_completed", {"code_blocks_found": len(code_blocks)})

            return AgentResult(
                agent_name=self.name,
                task_id=context.task_id,
                status=AgentStatus.SUCCESS,
                output=raw_content,
                risk_level=RiskLevel.LOW,
                metadata={
                    "code_blocks_count": len(code_blocks),
                    "syntax_validation": syntax_results,
                    "eval_count": response.get("eval_count", 0),
                },
            )
        except Exception as e:
            logger.error("coding_agent_failed", error=str(e))
            context.add_event(self.name, "task_failed", {"error": str(e)})
            return AgentResult(
                agent_name=self.name,
                task_id=context.task_id,
                status=AgentStatus.FAILED,
                output="",
                risk_level=RiskLevel.SAFE,
                error=str(e),
            )

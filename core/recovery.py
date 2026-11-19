"""
Error Recovery Engine for MY PERSONAL AI.

Handles failures during task execution with structured recovery strategies:
  1. RetryWithContext — Retry the failed step with error context
  2. SimplifyPlan   — Replace complex steps with simpler alternatives
  3. FallbackDirect — Abandon plan, give a best-effort direct answer
  4. AskUser        — Request clarification from the user

Max recovery attempts per task: 2
"""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from core.logging import logger
from core.planner import TaskStep, TaskPlan, StepStatus


class RecoveryStrategy(str, Enum):
    RETRY_WITH_CONTEXT = "retry_with_context"
    SIMPLIFY = "simplify"
    FALLBACK_DIRECT = "fallback_direct"
    ASK_USER = "ask_user"


class RecoveryAction(BaseModel):
    """Describes what the recovery engine decided to do."""
    strategy: RecoveryStrategy
    description: str
    modified_step: Optional[TaskStep] = None
    fallback_answer: Optional[str] = None
    should_continue: bool = True  # False means stop execution


class ErrorRecovery:
    """Manages error recovery during task execution.

    Tracks attempt counts and selects appropriate recovery strategies.
    """

    MAX_RETRIES_PER_STEP = 2
    MAX_TOTAL_RECOVERIES = 3

    def __init__(self):
        self._step_attempts: Dict[str, int] = {}
        self._total_recoveries: int = 0

    def reset(self):
        """Reset recovery counters for a new task."""
        self._step_attempts.clear()
        self._total_recoveries = 0

    def get_attempt_count(self, step_id: str) -> int:
        return self._step_attempts.get(step_id, 0)

    def recover(
        self,
        failed_step: TaskStep,
        plan: TaskPlan,
        error: str,
    ) -> RecoveryAction:
        """Determine and return the recovery action for a failed step.

        Selection logic:
          - Attempt 1: Retry with error context
          - Attempt 2: Simplify the step
          - Attempt 3+: Fallback to direct answer
          - If total recoveries exceeded: Stop entirely
        """
        step_id = failed_step.id
        attempts = self._step_attempts.get(step_id, 0) + 1
        self._step_attempts[step_id] = attempts
        self._total_recoveries += 1

        logger.info(
            "recovery_triggered",
            step=step_id,
            attempt=attempts,
            total_recoveries=self._total_recoveries,
            error=error[:200],
        )

        # Circuit breaker: too many total recoveries
        if self._total_recoveries > self.MAX_TOTAL_RECOVERIES:
            return RecoveryAction(
                strategy=RecoveryStrategy.FALLBACK_DIRECT,
                description=f"Maximum total recoveries ({self.MAX_TOTAL_RECOVERIES}) exceeded. Falling back to direct answer.",
                fallback_answer=self._generate_fallback_message(plan, error),
                should_continue=False,
            )

        # Strategy selection based on attempt count
        if attempts == 1:
            return self._retry_with_context(failed_step, error)
        elif attempts == 2:
            return self._simplify(failed_step, plan, error)
        else:
            return self._fallback_direct(plan, error)

    def _retry_with_context(self, step: TaskStep, error: str) -> RecoveryAction:
        """Strategy 1: Retry the step with the error message as additional context."""
        modified = step.model_copy()
        modified.status = StepStatus.PENDING
        modified.error = None
        modified.result = None
        # Add error context to inputs so the LLM can learn from the failure
        modified.inputs["_error_context"] = f"Previous attempt failed: {error}"
        modified.inputs["_retry"] = True

        return RecoveryAction(
            strategy=RecoveryStrategy.RETRY_WITH_CONTEXT,
            description=f"Retrying step '{step.id}' with error context: {error[:100]}",
            modified_step=modified,
            should_continue=True,
        )

    def _simplify(self, step: TaskStep, plan: TaskPlan, error: str) -> RecoveryAction:
        """Strategy 2: Replace the step with a simpler LLM-only 'think' step."""
        simplified = step.model_copy()
        simplified.status = StepStatus.PENDING
        simplified.error = None
        simplified.result = None
        simplified.action = "think"
        simplified.tool = None
        simplified.description = f"[Simplified] Think about: {step.description} (original tool '{step.tool}' failed)"
        simplified.inputs = {
            "_original_action": step.action,
            "_original_tool": step.tool,
            "_error": error,
        }

        return RecoveryAction(
            strategy=RecoveryStrategy.SIMPLIFY,
            description=f"Simplified step '{step.id}' from tool call to LLM reasoning.",
            modified_step=simplified,
            should_continue=True,
        )

    def _fallback_direct(self, plan: TaskPlan, error: str) -> RecoveryAction:
        """Strategy 3: Abandon the plan and provide a best-effort answer."""
        return RecoveryAction(
            strategy=RecoveryStrategy.FALLBACK_DIRECT,
            description="All retry strategies exhausted. Providing best-effort answer.",
            fallback_answer=self._generate_fallback_message(plan, error),
            should_continue=False,
        )

    def _generate_fallback_message(self, plan: TaskPlan, error: str) -> str:
        """Generate an honest failure message describing what was attempted."""
        completed = [s for s in plan.steps if s.status == StepStatus.COMPLETED]
        failed = [s for s in plan.steps if s.status == StepStatus.FAILED]

        msg_parts = [
            f"I attempted to complete your request: \"{plan.goal}\"",
        ]

        if completed:
            msg_parts.append(f"\n✅ Completed {len(completed)} step(s):")
            for s in completed:
                result_summary = ""
                if s.result:
                    result_summary = f" → {str(s.result)[:100]}"
                msg_parts.append(f"  - {s.description}{result_summary}")

        if failed:
            msg_parts.append(f"\n❌ Failed {len(failed)} step(s):")
            for s in failed:
                msg_parts.append(f"  - {s.description}: {s.error or 'Unknown error'}")

        msg_parts.append(f"\nLast error: {error}")
        msg_parts.append("\nPlease try rephrasing your request or breaking it into smaller steps.")

        return "\n".join(msg_parts)

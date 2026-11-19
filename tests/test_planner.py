"""
Tests for Task Planning Engine.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.planner import TaskPlanner, TaskPlan, TaskStep, StepStatus, PlanStatus
from core.reasoning import ReasoningResult


def test_task_plan_dependencies():
    """Verify task step ordering and dependency resolution."""
    step1 = TaskStep(id="step_1", action="calculate", description="First calculate 2+2", tool="calculator")
    step2 = TaskStep(id="step_2", action="respond", description="Return result", depends_on=["step_1"])

    plan = TaskPlan(goal="Calculate and return", steps=[step1, step2])

    # Initially step1 is ready, step2 is blocked
    next_step = plan.get_next_step()
    assert next_step.id == "step_1"

    # Complete step1
    step1.status = StepStatus.COMPLETED

    # Now step2 is ready
    next_step = plan.get_next_step()
    assert next_step.id == "step_2"

    # Complete step2
    step2.status = StepStatus.COMPLETED
    assert plan.get_next_step() is None
    assert plan.progress_pct == 100.0
    print("✅ test_task_plan_dependencies PASSED")


def test_plan_sanitization_and_safety():
    """Verify planner sanitizes dangerous actions and inputs."""
    planner = TaskPlanner(model_router=None)

    dangerous_step = TaskStep(
        id="step_1",
        action="execute_shell_command",  # Blocked action
        description="Try to delete files",
        tool="powershell",               # Blocked tool
        inputs={"cmd": "powershell rm -rf /", "safe_val": 42},
    )

    plan = TaskPlan(goal="Test security", steps=[dangerous_step])
    sanitized = planner._validate_and_sanitize(plan)

    # Action must be downgraded to think
    assert sanitized.steps[0].action == "think"
    # Tool must be cleared
    assert sanitized.steps[0].tool is None
    # Dangerous input must be blocked
    assert sanitized.steps[0].inputs["cmd"] == "[BLOCKED]"
    # Final respond step must be appended automatically
    assert any(s.action == "respond" for s in sanitized.steps)
    print("✅ test_plan_sanitization_and_safety PASSED")


def test_heuristic_plan_creation():
    """Verify heuristic plan creation when tools are suggested."""
    planner = TaskPlanner(model_router=None)
    reasoning = ReasoningResult(
        intent="calculation",
        complexity=3,
        needs_tools=True,
        suggested_tools=["calculator"],
    )

    plan = planner._heuristic_plan("Calculate sqrt(100)", reasoning)
    assert len(plan.steps) >= 2
    assert plan.steps[0].tool == "calculator"
    assert plan.steps[-1].action == "respond"
    print("✅ test_heuristic_plan_creation PASSED")


if __name__ == "__main__":
    test_task_plan_dependencies()
    test_plan_sanitization_and_safety()
    test_heuristic_plan_creation()
    print("ALL PLANNER TESTS PASSED!")

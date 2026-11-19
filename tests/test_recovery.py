"""
Tests for Error Recovery Engine.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.recovery import ErrorRecovery, RecoveryStrategy
from core.planner import TaskStep, TaskPlan, StepStatus


def test_recovery_tiered_strategies():
    """Verify tiered recovery strategy escalation."""
    recovery = ErrorRecovery()
    step = TaskStep(id="step_1", action="calculate", tool="calculator", description="Calculate formula")
    plan = TaskPlan(goal="Test error recovery", steps=[step])

    # Attempt 1: Retry with context
    action1 = recovery.recover(step, plan, "Syntax error in expression")
    assert action1.strategy == RecoveryStrategy.RETRY_WITH_CONTEXT
    assert action1.should_continue is True
    assert "_error_context" in action1.modified_step.inputs

    # Attempt 2: Simplify to think step
    action2 = recovery.recover(step, plan, "Persistent syntax error")
    assert action2.strategy == RecoveryStrategy.SIMPLIFY
    assert action2.should_continue is True
    assert action2.modified_step.action == "think"
    assert action2.modified_step.tool is None

    # Attempt 3: Fallback direct answer
    action3 = recovery.recover(step, plan, "Third error")
    assert action3.strategy == RecoveryStrategy.FALLBACK_DIRECT
    assert action3.should_continue is False
    assert action3.fallback_answer is not None
    assert "attempted" in action3.fallback_answer.lower()
    print("✅ test_recovery_tiered_strategies PASSED")


def test_recovery_circuit_breaker():
    """Verify circuit breaker trips when total recoveries exceed threshold."""
    recovery = ErrorRecovery()
    step1 = TaskStep(id="step_1", action="calculate")
    step2 = TaskStep(id="step_2", action="read_file")
    step3 = TaskStep(id="step_3", action="get_system_info")
    step4 = TaskStep(id="step_4", action="get_datetime")

    plan = TaskPlan(goal="Multi-failure task", steps=[step1, step2, step3, step4])

    # Recover step 1 (1)
    recovery.recover(step1, plan, "Err 1")
    # Recover step 2 (2)
    recovery.recover(step2, plan, "Err 2")
    # Recover step 3 (3)
    recovery.recover(step3, plan, "Err 3")

    # Recover step 4 (4) -> Exceeds MAX_TOTAL_RECOVERIES (3)
    action = recovery.recover(step4, plan, "Err 4")
    assert action.strategy == RecoveryStrategy.FALLBACK_DIRECT
    assert action.should_continue is False
    assert "maximum" in action.description.lower()
    print("✅ test_recovery_circuit_breaker PASSED")


if __name__ == "__main__":
    test_recovery_tiered_strategies()
    test_recovery_circuit_breaker()
    print("ALL RECOVERY TESTS PASSED!")

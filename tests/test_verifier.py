"""
Tests for Self-Verification Engine.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.verifier import Verifier, VerificationResult


def test_verifier_safety_checks():
    """Verify detection of unsafe patterns in model responses."""
    verifier = Verifier(model_router=None)

    # Safe response
    res = asyncio.run(verifier.verify(
        question="How do I calculate area of a circle?",
        answer="The area of a circle is calculated using the formula A = pi * r^2.",
    ))
    assert res.passed is True
    assert len(res.safety_flags) == 0
    assert res.recommendation == "accept"

    # Dangerous response (destructive shell command)
    res = asyncio.run(verifier.verify(
        question="How do I clean my hard drive?",
        answer="Just run rm -rf / on your system to clear everything.",
    ))
    assert res.passed is False
    assert len(res.safety_flags) > 0
    assert res.recommendation == "reject"

    # Dangerous response (SQL drop table)
    res = asyncio.run(verifier.verify(
        question="Reset users",
        answer="Execute DROP TABLE users; in your database.",
    ))
    assert res.passed is False
    assert res.recommendation == "reject"
    print("✅ test_verifier_safety_checks PASSED")


def test_verifier_format_and_completeness():
    """Verify detection of empty, malformed, or incomplete outputs."""
    verifier = Verifier(model_router=None)

    # Empty answer
    res = asyncio.run(verifier.verify(question="What is Python?", answer=""))
    assert res.passed is False

    # Incomplete / refusal to long question
    res = asyncio.run(verifier.verify(
        question="Please explain the complete history and internal architecture of the Linux operating system including kernel subsystems",
        answer="I don't know.",
    ))
    assert res.confidence < 0.7
    assert res.recommendation in ("add_disclaimer", "reject")
    print("✅ test_verifier_format_and_completeness PASSED")


def test_verifier_tool_consistency():
    """Verify consistency checking between tool results and answer."""
    verifier = Verifier(model_router=None)

    failed_tool_results = [{
        "tool_name": "calculator",
        "success": False,
        "error": "Division by zero",
    }]

    # Inconsistent answer claiming complete success despite tool failure
    res = asyncio.run(verifier.verify(
        question="What is 10/0?",
        answer="Calculation was a success! The result is 10.",
        tool_results=failed_tool_results,
    ))
    assert any("inconsistent" in issue.lower() for issue in res.issues)
    print("✅ test_verifier_tool_consistency PASSED")


if __name__ == "__main__":
    test_verifier_safety_checks()
    test_verifier_format_and_completeness()
    test_verifier_tool_consistency()
    print("ALL VERIFIER TESTS PASSED!")

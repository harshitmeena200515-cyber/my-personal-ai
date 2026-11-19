"""
Tests for Reasoning Engine.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.reasoning import ReasoningEngine, ReasoningResult, Intent


def test_reasoning_heuristics_classification():
    """Verify heuristic classification for various intent types."""
    engine = ReasoningEngine(model_router=None)

    # 1. Calculation
    res = engine._heuristic_analyze("Calculate 45 * 12 + sqrt(81)")
    assert res.intent == "calculation"
    assert "calculator" in res.suggested_tools
    assert res.needs_tools is True

    # 2. File Operation
    res = engine._heuristic_analyze("Please read file server.py and show me contents")
    assert res.intent == "file_operation"
    assert "file_reader" in res.suggested_tools

    # 3. Code Analysis
    res = engine._heuristic_analyze("Analyze code structure and check syntax")
    assert res.intent == "code_request"
    assert "code_analyzer" in res.suggested_tools

    # 4. System Query
    res = engine._heuristic_analyze("Show me system info and GPU memory")
    assert res.intent == "system_query"
    assert "system_info" in res.suggested_tools

    # 5. Casual Conversation
    res = engine._heuristic_analyze("Hello, how are you?")
    assert res.intent == "conversation"
    assert res.complexity == 1
    assert res.needs_planning is False

    # 6. Complex Multi-step Task
    res = engine._heuristic_analyze("Build and deploy an automated pipeline with step 1 step 2 and step 3")
    assert res.complexity >= 3
    assert res.needs_planning is True
    print("✅ test_reasoning_heuristics_classification PASSED")


def test_json_extraction():
    """Verify JSON extraction from various model output formats."""
    engine = ReasoningEngine(model_router=None)

    # Clean JSON
    data = engine._extract_json('{"intent": "task", "complexity": 3}')
    assert data["intent"] == "task"

    # JSON in markdown fence
    data = engine._extract_json('Here is your analysis:\n```json\n{"intent": "calculation", "complexity": 1}\n```')
    assert data["intent"] == "calculation"

    # JSON with surrounding prose
    data = engine._extract_json('Sure! {"intent": "question", "complexity": 2} Hope this helps!')
    assert data["intent"] == "question"
    print("✅ test_json_extraction PASSED")


if __name__ == "__main__":
    test_reasoning_heuristics_classification()
    test_json_extraction()
    print("ALL REASONING TESTS PASSED!")

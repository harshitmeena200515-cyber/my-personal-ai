"""
Reasoning Engine for MY PERSONAL AI.

Analyzes user input to determine intent, complexity, entities, and whether
multi-step planning is needed. Uses structured prompting to extract
reasoning from the local 3B model.
"""

import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from core.logging import logger


class Intent(str, Enum):
    """Classified user intent categories."""
    QUESTION = "question"               # Factual or knowledge query
    TASK = "task"                       # Actionable request
    CODE_REQUEST = "code_request"       # Write, fix, or explain code
    ANALYSIS = "analysis"              # Analyze data, file, or system
    CONVERSATION = "conversation"       # Casual chat or greeting
    CALCULATION = "calculation"         # Math or computation
    FILE_OPERATION = "file_operation"   # Read or inspect files
    SYSTEM_QUERY = "system_query"      # Ask about system/hardware


class ReasoningResult(BaseModel):
    """Structured output of the reasoning engine."""
    intent: str = "conversation"
    complexity: int = Field(default=1, ge=1, le=5)
    needs_planning: bool = False
    needs_tools: bool = False
    suggested_tools: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    reasoning: str = ""
    direct_answer_possible: bool = True


# System prompt that instructs the model to produce structured reasoning
REASONING_SYSTEM_PROMPT = """You are the Reasoning Engine of an autonomous Personal AI.

Your job is to analyze the user's message and produce a JSON analysis.

You MUST respond with ONLY a valid JSON object (no markdown, no explanation, no code fences).

JSON schema:
{
  "intent": one of ["question", "task", "code_request", "analysis", "conversation", "calculation", "file_operation", "system_query"],
  "complexity": integer 1-5 where 1=trivial 5=very complex multi-step,
  "needs_planning": true if complexity >= 3 or multiple steps needed,
  "needs_tools": true if any tool should be used,
  "suggested_tools": list of tool names from ["calculator", "file_reader", "code_analyzer", "system_info", "datetime"],
  "entities": key entities/topics extracted from the message,
  "reasoning": brief explanation of your analysis,
  "direct_answer_possible": true if the model can answer directly without tools
}

Rules:
- Math expressions → intent="calculation", suggest "calculator"
- File reading/listing → intent="file_operation", suggest "file_reader"
- Code analysis/review → intent="code_request", suggest "code_analyzer"
- System/hardware questions → intent="system_query", suggest "system_info"
- Date/time questions → suggest "datetime"
- Simple greetings → intent="conversation", complexity=1
- Multi-step tasks → complexity >= 3, needs_planning=true"""


class ReasoningEngine:
    """Analyzes user input to determine intent, complexity, and required tools.

    Uses the local model with a structured prompt to extract reasoning.
    Falls back to heuristic analysis if structured parsing fails.
    """

    def __init__(self, model_router):
        self.router = model_router

    async def analyze(self, user_message: str, conversation_history: List[Dict[str, str]] = None) -> ReasoningResult:
        """Analyze a user message and return structured reasoning.

        First attempts model-based structured analysis.
        Falls back to keyword heuristics if model output can't be parsed.
        """
        # 1. Try model-based reasoning
        try:
            result = await self._model_analyze(user_message, conversation_history)
            if result:
                logger.info(
                    "reasoning_complete",
                    intent=result.intent,
                    complexity=result.complexity,
                    needs_planning=result.needs_planning,
                    tools=result.suggested_tools,
                )
                return result
        except Exception as e:
            logger.warning("model_reasoning_failed", error=str(e))

        # 2. Fallback to heuristic analysis
        result = self._heuristic_analyze(user_message)
        logger.info(
            "reasoning_heuristic_fallback",
            intent=result.intent,
            complexity=result.complexity,
        )
        return result

    async def _model_analyze(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[ReasoningResult]:
        """Use the local model to produce structured reasoning."""
        from models.router import ChatRequest, ChatMessage

        messages = [
            ChatMessage(role="system", content=REASONING_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_message),
        ]

        request = ChatRequest(
            messages=messages,
            temperature=0.1,  # Low temperature for consistent structured output
            stream=False,
        )

        response = await self.router.route_chat(request)
        raw = response.content.strip()

        # Try to extract JSON from the response
        parsed = self._extract_json(raw)
        if parsed:
            return ReasoningResult(**{
                "intent": parsed.get("intent", "conversation"),
                "complexity": max(1, min(5, int(parsed.get("complexity", 1)))),
                "needs_planning": bool(parsed.get("needs_planning", False)),
                "needs_tools": bool(parsed.get("needs_tools", False)),
                "suggested_tools": list(parsed.get("suggested_tools", [])),
                "entities": list(parsed.get("entities", [])),
                "reasoning": str(parsed.get("reasoning", "")),
                "direct_answer_possible": bool(parsed.get("direct_answer_possible", True)),
            })

        return None

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract a JSON object from model output, handling various formats."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code fences
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        brace_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _heuristic_analyze(self, message: str) -> ReasoningResult:
        """Keyword-based fallback analysis when model parsing fails."""
        msg_lower = message.lower().strip()
        intent = "conversation"
        complexity = 1
        tools: List[str] = []
        needs_planning = False
        needs_tools = False

        # Greeting detection
        greetings = ["hi", "hello", "hey", "namaste", "good morning", "good evening", "howdy", "sup"]
        if any(msg_lower.startswith(g) for g in greetings) and len(msg_lower.split()) <= 5:
            return ReasoningResult(intent="conversation", complexity=1)

        # Math detection
        math_indicators = ["+", "-", "*", "/", "^", "sqrt", "calculate", "compute", "what is", "how much"]
        if any(ind in msg_lower for ind in math_indicators):
            # Check if it looks like a math expression
            has_numbers = bool(re.search(r'\d', msg_lower))
            has_ops = bool(re.search(r'[\+\-\*/\^]', msg_lower))
            if has_numbers and (has_ops or any(w in msg_lower for w in ["sqrt", "calculate", "compute"])):
                intent = "calculation"
                tools.append("calculator")
                needs_tools = True

        # File operation detection
        file_words = ["read file", "show file", "open file", "list files", "show code", "read code", "cat "]
        if any(w in msg_lower for w in file_words):
            intent = "file_operation"
            tools.append("file_reader")
            needs_tools = True

        # Code analysis detection
        code_words = ["analyze code", "review code", "check syntax", "code structure", "how many functions"]
        if any(w in msg_lower for w in code_words):
            intent = "code_request"
            tools.append("code_analyzer")
            needs_tools = True

        # System info detection
        sys_words = ["system info", "hardware", "cpu", "ram", "gpu", "disk space", "memory"]
        if any(w in msg_lower for w in sys_words):
            intent = "system_query"
            tools.append("system_info")
            needs_tools = True

        # Date/time detection
        time_words = ["what time", "current time", "today's date", "what day", "date today"]
        if any(w in msg_lower for w in time_words):
            intent = "question"
            tools.append("datetime")
            needs_tools = True

        # Task detection (multi-step)
        task_words = ["create", "build", "implement", "develop", "set up", "configure", "deploy", "fix"]
        if any(w in msg_lower for w in task_words):
            intent = "task"
            complexity = 3
            needs_planning = True

        # Complexity based on length and structure
        word_count = len(msg_lower.split())
        if word_count > 50:
            complexity = max(complexity, 3)
        if "step" in msg_lower or "first" in msg_lower or "then" in msg_lower:
            complexity = max(complexity, 3)
            needs_planning = True

        return ReasoningResult(
            intent=intent,
            complexity=complexity,
            needs_planning=needs_planning,
            needs_tools=needs_tools,
            suggested_tools=tools,
            entities=[],
            reasoning=f"Heuristic analysis: intent={intent}, words={word_count}",
            direct_answer_possible=not needs_planning,
        )

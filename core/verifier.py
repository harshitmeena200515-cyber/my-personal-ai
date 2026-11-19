"""
Self-Verification Engine for MY PERSONAL AI.

Validates outputs before returning them to the user.
Checks format, completeness, safety, and consistency.
"""

import json
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from core.logging import logger


class VerificationResult(BaseModel):
    """Result of output verification."""
    passed: bool = True
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list)
    safety_flags: List[str] = Field(default_factory=list)
    recommendation: str = "accept"  # "accept", "add_disclaimer", "reject", "ask_user"


# Patterns that should never appear in AI output
_DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"del\s+/[sf]\s+",
    r"format\s+[a-z]:",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM\s+\w+\s*;?\s*$",
    r"exec\s*\(",
    r"eval\s*\(",
    r"os\.system\s*\(",
    r"subprocess\.(run|call|Popen)",
    r"__import__\s*\(",
    r"api[_-]?key\s*[=:]\s*['\"][a-zA-Z0-9]",
    r"password\s*[=:]\s*['\"][^'\"]+['\"]",
    r"token\s*[=:]\s*['\"][a-zA-Z0-9]",
]


class Verifier:
    """Validates AI outputs for quality, safety, and completeness.

    Runs multiple checks and returns a confidence-scored result.
    Can optionally use the LLM for semantic verification.
    """

    def __init__(self, model_router=None):
        self.router = model_router

    async def verify(
        self,
        question: str,
        answer: str,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        use_model: bool = False,
    ) -> VerificationResult:
        """Run all verification checks on an answer."""
        issues: List[str] = []
        safety_flags: List[str] = []
        confidence = 1.0

        # 1. Format check
        format_ok = self._check_format(answer)
        if not format_ok:
            issues.append("Answer appears to be malformed or empty.")
            confidence -= 0.7

        # 2. Completeness check
        completeness_ok = self._check_completeness(question, answer)
        if not completeness_ok:
            issues.append("Answer may not fully address the question.")
            confidence -= 0.4

        # 3. Safety check
        safety_issues = self._check_safety(answer)
        if safety_issues:
            safety_flags.extend(safety_issues)
            confidence -= 0.3 * len(safety_issues)

        # 4. Consistency check with tool results
        if tool_results:
            consistency_ok = self._check_consistency(answer, tool_results)
            if not consistency_ok:
                issues.append("Answer may be inconsistent with tool execution results.")
                confidence -= 0.2

        # 5. Optional model-based verification
        if use_model and self.router and confidence > 0.3:
            try:
                model_check = await self._model_verify(question, answer)
                if model_check is not None:
                    confidence = (confidence + model_check) / 2
            except Exception as e:
                logger.warning("model_verification_failed", error=str(e))

        # Clamp confidence
        confidence = max(0.0, min(1.0, confidence))

        # Determine recommendation
        if safety_flags:
            recommendation = "reject"
        elif confidence < 0.4:
            recommendation = "reject"
        elif confidence < 0.7:
            recommendation = "add_disclaimer"
        else:
            recommendation = "accept"

        result = VerificationResult(
            passed=confidence >= 0.4 and not safety_flags,
            confidence=round(confidence, 2),
            issues=issues,
            safety_flags=safety_flags,
            recommendation=recommendation,
        )

        logger.info(
            "verification_complete",
            passed=result.passed,
            confidence=result.confidence,
            issues=len(issues),
            safety_flags=len(safety_flags),
        )
        return result

    def _check_format(self, answer: str) -> bool:
        """Check if the answer is well-formed."""
        if not answer or not answer.strip():
            return False
        if len(answer.strip()) < 2:
            return False
        return True

    def _check_completeness(self, question: str, answer: str) -> bool:
        """Heuristic check: does the answer address the question?"""
        q_lower = question.lower()
        a_lower = answer.lower()

        # Very short answers to long questions are suspect
        if len(question) > 100 and len(answer) < 20:
            return False

        # If the question asks "how", the answer should have some instruction
        if "how" in q_lower and len(answer) < 30:
            return False

        # Generic "I don't know" should be flagged
        refusal_phrases = ["i don't know", "i cannot", "i can't help", "not sure"]
        if any(p in a_lower for p in refusal_phrases) and len(answer) < 50:
            return False

        return True

    def _check_safety(self, answer: str) -> List[str]:
        """Check for dangerous patterns in the answer."""
        flags = []
        for pattern in _DANGEROUS_PATTERNS:
            if re.search(pattern, answer, re.IGNORECASE):
                flags.append(f"Dangerous pattern detected: {pattern}")
        return flags

    def _check_consistency(self, answer: str, tool_results: List[Dict[str, Any]]) -> bool:
        """Check if the answer is consistent with tool execution results."""
        for result in tool_results:
            if not result.get("success"):
                # If a tool failed but the answer claims success, flag it
                if "error" in result and result["error"]:
                    error_text = str(result["error"]).lower()
                    if "success" in answer.lower() and error_text not in answer.lower():
                        return False
        return True

    async def _model_verify(self, question: str, answer: str) -> Optional[float]:
        """Use the model to verify the answer semantically. Returns confidence 0-1."""
        from models.router import ChatRequest, ChatMessage

        verification_prompt = (
            "You are a verification engine. Rate the following answer.\n"
            "Respond with ONLY a JSON object: {\"score\": 0.0 to 1.0, \"reason\": \"brief explanation\"}\n\n"
            f"Question: {question[:500]}\n\n"
            f"Answer: {answer[:1000]}\n\n"
            "Score 1.0 = perfect answer. Score 0.0 = completely wrong or harmful."
        )

        request = ChatRequest(
            messages=[ChatMessage(role="user", content=verification_prompt)],
            temperature=0.1,
            stream=False,
        )

        response = await self.router.route_chat(request)
        raw = response.content.strip()

        # Parse score
        try:
            data = json.loads(raw)
            return float(data.get("score", 0.5))
        except (json.JSONDecodeError, ValueError, TypeError):
            # Try regex extraction
            score_match = re.search(r'"score"\s*:\s*([\d.]+)', raw)
            if score_match:
                return float(score_match.group(1))

        return None

"""
Master Orchestrator for MY PERSONAL AI.

Coordinates the full autonomous pipeline:
  User Message → Reasoning → Planning → Execution → Verification → Response

Manages task state, routes steps to tools or the LLM, enforces timeouts,
handles errors via the recovery engine, and streams progress updates.
"""

import time
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from pydantic import BaseModel, Field
from core.logging import logger
from core.reasoning import ReasoningEngine, ReasoningResult
from core.planner import TaskPlanner, TaskPlan, TaskStep, StepStatus, PlanStatus
from core.verifier import Verifier, VerificationResult
from core.recovery import ErrorRecovery, RecoveryStrategy
from tools.base import ToolRegistry


class OrchestratorConfig(BaseModel):
    """Configuration for orchestrator execution limits."""
    max_steps: int = 10
    max_retries_per_step: int = 2
    step_timeout_sec: float = 60.0
    enable_verification: bool = True
    enable_planning: bool = True
    complexity_threshold: int = 3  # Min complexity to trigger planning


class ProgressUpdate(BaseModel):
    """Real-time progress update during orchestration."""
    phase: str             # "reasoning", "planning", "executing", "verifying", "complete", "error"
    message: str
    step_id: Optional[str] = None
    progress_pct: float = 0.0
    tool_used: Optional[str] = None
    tool_result: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class OrchestrationResult(BaseModel):
    """Final result of autonomous orchestration."""
    answer: str
    reasoning: Optional[ReasoningResult] = None
    plan: Optional[TaskPlan] = None
    verification: Optional[VerificationResult] = None
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    total_time_sec: float = 0.0
    inference_calls: int = 0
    was_planned: bool = False
    confidence: float = 1.0


class Orchestrator:
    """Master coordinator for the autonomous AI pipeline.

    Flow:
      1. Reasoning Engine analyzes intent and complexity
      2. If complex → Task Planner decomposes into steps
      3. Execution loop runs each step (tool or LLM)
      4. Verifier validates the final answer
      5. Error Recovery handles failures with retry/simplify/fallback
    """

    def __init__(
        self,
        model_router,
        tool_registry: ToolRegistry,
        config: Optional[OrchestratorConfig] = None,
    ):
        self.router = model_router
        self.tools = tool_registry
        self.config = config or OrchestratorConfig()
        self.reasoning_engine = ReasoningEngine(model_router)
        self.planner = TaskPlanner(model_router)
        self.verifier = Verifier(model_router)
        self.recovery = ErrorRecovery()
        self._inference_calls = 0

    async def process(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> OrchestrationResult:
        """Process a user message through the full autonomous pipeline."""
        start_time = time.perf_counter()
        self._inference_calls = 0
        self.recovery.reset()
        tool_results: List[Dict[str, Any]] = []

        # === Phase 1: Reasoning ===
        reasoning = await self.reasoning_engine.analyze(user_message, conversation_history)
        self._inference_calls += 1

        # === Phase 2: Decide — Direct Answer or Plan ===
        if (
            not self.config.enable_planning
            or reasoning.complexity < self.config.complexity_threshold
            or reasoning.direct_answer_possible and not reasoning.needs_tools
        ):
            # Simple path: direct answer (optionally with tools)
            answer = await self._direct_answer(user_message, reasoning, conversation_history, tool_results)

        else:
            # Complex path: plan → execute → synthesize
            answer = await self._planned_answer(user_message, reasoning, conversation_history, tool_results)

        # === Phase 3: Verification ===
        verification = None
        if self.config.enable_verification:
            verification = await self.verifier.verify(
                question=user_message,
                answer=answer,
                tool_results=tool_results,
                use_model=False,  # Heuristic only to save inference calls on 3B model
            )

            if verification.recommendation == "add_disclaimer":
                answer = f"⚠️ *Note: This response may be incomplete or uncertain.*\n\n{answer}"
            elif verification.recommendation == "reject":
                answer = (
                    "I wasn't able to produce a reliable answer for this request. "
                    f"Issues detected: {'; '.join(verification.issues + verification.safety_flags)}"
                )

        total_time = round(time.perf_counter() - start_time, 2)

        return OrchestrationResult(
            answer=answer,
            reasoning=reasoning,
            verification=verification,
            tool_results=tool_results,
            total_time_sec=total_time,
            inference_calls=self._inference_calls,
            was_planned=reasoning.complexity >= self.config.complexity_threshold and reasoning.needs_planning,
            confidence=verification.confidence if verification else 0.8,
        )

    async def process_stream(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[ProgressUpdate, None]:
        """Process with streaming progress updates."""
        start_time = time.perf_counter()
        self._inference_calls = 0
        self.recovery.reset()
        tool_results: List[Dict[str, Any]] = []

        # Reasoning
        yield ProgressUpdate(phase="reasoning", message="Analyzing your request...", progress_pct=10)
        reasoning = await self.reasoning_engine.analyze(user_message, conversation_history)
        self._inference_calls += 1

        yield ProgressUpdate(
            phase="reasoning",
            message=f"Intent: {reasoning.intent} | Complexity: {reasoning.complexity}/5",
            progress_pct=20,
        )

        needs_plan = (
            self.config.enable_planning
            and reasoning.complexity >= self.config.complexity_threshold
            and not (reasoning.direct_answer_possible and not reasoning.needs_tools)
        )

        if needs_plan:
            # Planning
            yield ProgressUpdate(phase="planning", message="Creating execution plan...", progress_pct=30)
            plan = await self.planner.create_plan(user_message, reasoning)
            self._inference_calls += 1

            yield ProgressUpdate(
                phase="planning",
                message=f"Plan created: {len(plan.steps)} steps",
                progress_pct=35,
            )

            # Execute plan
            plan.status = PlanStatus.EXECUTING
            async for update in self._execute_plan_stream(plan, user_message, conversation_history, tool_results):
                yield update

            # Synthesize answer
            yield ProgressUpdate(phase="executing", message="Synthesizing final answer...", progress_pct=90)
            answer = await self._synthesize_answer(user_message, plan, tool_results, conversation_history)
            self._inference_calls += 1
        else:
            yield ProgressUpdate(phase="executing", message="Generating response...", progress_pct=50)
            answer = await self._direct_answer(user_message, reasoning, conversation_history, tool_results)

        # Verify
        yield ProgressUpdate(phase="verifying", message="Verifying output...", progress_pct=95)
        verification = await self.verifier.verify(user_message, answer, tool_results)

        if verification.recommendation == "add_disclaimer":
            answer = f"⚠️ *Note: This response may be incomplete.*\n\n{answer}"
        elif verification.recommendation == "reject":
            answer = "I wasn't able to produce a reliable answer. " + "; ".join(verification.issues)

        total_time = round(time.perf_counter() - start_time, 2)
        yield ProgressUpdate(
            phase="complete",
            message=answer,
            progress_pct=100,
            tool_result={
                "total_time_sec": total_time,
                "inference_calls": self._inference_calls,
                "confidence": verification.confidence,
                "tool_count": len(tool_results),
                "was_planned": needs_plan,
            },
        )

    async def _direct_answer(
        self,
        message: str,
        reasoning: ReasoningResult,
        history: Optional[List[Dict[str, str]]],
        tool_results: List[Dict[str, Any]],
    ) -> str:
        """Generate a direct answer, optionally using tools first."""
        # Execute tools if suggested
        if reasoning.needs_tools and reasoning.suggested_tools:
            for tool_name in reasoning.suggested_tools:
                inputs = self._guess_tool_inputs(tool_name, message)
                result = await self.tools.execute(tool_name, inputs)
                tool_results.append(result.model_dump())

        # Build context from tool results
        tool_context = ""
        if tool_results:
            tool_context = "\n\nTool Results:\n"
            for tr in tool_results:
                tool_context += f"- {tr.get('tool_name', '?')}: {tr.get('output', tr.get('error', 'No output'))}\n"

        # Generate answer with tool context
        from models.router import ChatRequest, ChatMessage

        system_msg = (
            "You are MY PERSONAL AI, an autonomous local AI assistant. "
            "Answer the user's question accurately and helpfully. "
            "If tool results are provided, use them to give a precise answer."
            f"{tool_context}"
        )

        messages = [ChatMessage(role="system", content=system_msg)]
        if history:
            for h in history[-6:]:  # Last 6 messages for context
                messages.append(ChatMessage(role=h["role"], content=h["content"]))
        messages.append(ChatMessage(role="user", content=message))

        request = ChatRequest(messages=messages, temperature=0.7, stream=False)
        response = await self.router.route_chat(request)
        self._inference_calls += 1
        return response.content

    async def _planned_answer(
        self,
        message: str,
        reasoning: ReasoningResult,
        history: Optional[List[Dict[str, str]]],
        tool_results: List[Dict[str, Any]],
    ) -> str:
        """Execute a full plan and synthesize the answer."""
        # Create plan
        plan = await self.planner.create_plan(message, reasoning)
        self._inference_calls += 1

        # Execute plan
        plan.status = PlanStatus.EXECUTING
        await self._execute_plan(plan, message, history, tool_results)

        # Synthesize
        answer = await self._synthesize_answer(message, plan, tool_results, history)
        self._inference_calls += 1
        return answer

    async def _execute_plan(
        self,
        plan: TaskPlan,
        message: str,
        history: Optional[List[Dict[str, str]]],
        tool_results: List[Dict[str, Any]],
    ) -> None:
        """Execute all steps in a plan sequentially."""
        executed = 0
        while executed < self.config.max_steps:
            step = plan.get_next_step()
            if not step:
                break

            step.status = StepStatus.RUNNING
            success = await self._execute_step(step, plan, message, history, tool_results)

            if not success:
                # Attempt recovery
                action = self.recovery.recover(step, plan, step.error or "Unknown error")

                if action.should_continue and action.modified_step:
                    # Replace step and retry
                    for i, s in enumerate(plan.steps):
                        if s.id == step.id:
                            plan.steps[i] = action.modified_step
                            break
                    continue
                elif action.fallback_answer:
                    plan.final_answer = action.fallback_answer
                    plan.status = PlanStatus.FAILED
                    return

            executed += 1

        # Mark plan complete or failed
        all_done = all(s.status == StepStatus.COMPLETED for s in plan.steps)
        plan.status = PlanStatus.COMPLETED if all_done else PlanStatus.FAILED
        plan.completed_at = datetime.now().isoformat()

    async def _execute_plan_stream(
        self,
        plan: TaskPlan,
        message: str,
        history: Optional[List[Dict[str, str]]],
        tool_results: List[Dict[str, Any]],
    ) -> AsyncGenerator[ProgressUpdate, None]:
        """Execute plan with streaming progress updates."""
        executed = 0
        total = len(plan.steps)

        while executed < self.config.max_steps:
            step = plan.get_next_step()
            if not step:
                break

            pct = 35 + int((executed / max(total, 1)) * 50)
            yield ProgressUpdate(
                phase="executing",
                message=f"Step {executed + 1}/{total}: {step.description}",
                step_id=step.id,
                progress_pct=pct,
                tool_used=step.tool,
            )

            step.status = StepStatus.RUNNING
            success = await self._execute_step(step, plan, message, history, tool_results)

            if success:
                yield ProgressUpdate(
                    phase="executing",
                    message=f"✅ Step {executed + 1} complete",
                    step_id=step.id,
                    progress_pct=pct + 5,
                    tool_result={"result": str(step.result)[:200]} if step.result else None,
                )
            else:
                action = self.recovery.recover(step, plan, step.error or "Unknown")
                yield ProgressUpdate(
                    phase="executing",
                    message=f"⚠️ Step failed, recovery: {action.strategy.value}",
                    step_id=step.id,
                    progress_pct=pct,
                )

                if action.should_continue and action.modified_step:
                    for i, s in enumerate(plan.steps):
                        if s.id == step.id:
                            plan.steps[i] = action.modified_step
                            break
                    continue
                elif action.fallback_answer:
                    plan.final_answer = action.fallback_answer
                    plan.status = PlanStatus.FAILED
                    return

            executed += 1

        all_done = all(s.status == StepStatus.COMPLETED for s in plan.steps)
        plan.status = PlanStatus.COMPLETED if all_done else PlanStatus.FAILED

    async def _execute_step(
        self,
        step: TaskStep,
        plan: TaskPlan,
        message: str,
        history: Optional[List[Dict[str, str]]],
        tool_results: List[Dict[str, Any]],
    ) -> bool:
        """Execute a single step. Returns True on success."""
        start = time.perf_counter()

        try:
            if step.action == "respond" or step.action == "summarize":
                # LLM synthesis step — handled later in _synthesize_answer
                step.status = StepStatus.COMPLETED
                step.result = "Deferred to synthesis"
                return True

            elif step.action == "think":
                # LLM reasoning step
                result = await self._think_step(step, message, plan)
                step.result = result
                step.status = StepStatus.COMPLETED
                self._inference_calls += 1

            elif step.action == "verify":
                # Verification of previous steps
                step.result = "Verification deferred to final check"
                step.status = StepStatus.COMPLETED

            elif step.tool:
                # Tool execution step
                tool_result = await self.tools.execute(
                    step.tool,
                    step.inputs,
                    timeout=self.config.step_timeout_sec,
                )
                tool_results.append(tool_result.model_dump())

                if tool_result.success:
                    step.result = tool_result.output
                    step.status = StepStatus.COMPLETED
                else:
                    step.error = tool_result.error
                    step.status = StepStatus.FAILED
                    return False
            else:
                # Unknown action — treat as think
                step.result = "No-op step"
                step.status = StepStatus.COMPLETED

            step.execution_time_ms = round((time.perf_counter() - start) * 1000, 2)
            return True

        except Exception as e:
            step.error = str(e)
            step.status = StepStatus.FAILED
            step.execution_time_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("step_execution_error", step=step.id, error=str(e))
            return False

    async def _think_step(self, step: TaskStep, message: str, plan: TaskPlan) -> str:
        """Execute an LLM thinking step."""
        from models.router import ChatRequest, ChatMessage

        # Gather results from completed steps
        context_parts = [f"Original goal: {plan.goal}"]
        for s in plan.steps:
            if s.status == StepStatus.COMPLETED and s.result:
                context_parts.append(f"[{s.id}] {s.description}: {str(s.result)[:300]}")

        if step.inputs.get("_error_context"):
            context_parts.append(f"Previous error: {step.inputs['_error_context']}")

        prompt = (
            f"You are thinking through a problem step by step.\n"
            f"Current step: {step.description}\n\n"
            f"Context:\n" + "\n".join(context_parts) + "\n\n"
            f"Provide your analysis or reasoning for this step."
        )

        request = ChatRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=0.5,
            stream=False,
        )
        response = await self.router.route_chat(request)
        return response.content

    async def _synthesize_answer(
        self,
        message: str,
        plan: TaskPlan,
        tool_results: List[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]],
    ) -> str:
        """Synthesize a final answer from plan results."""
        # If the plan already has a fallback answer (from recovery), use it
        if plan.final_answer:
            return plan.final_answer

        from models.router import ChatRequest, ChatMessage

        # Build context from completed steps
        step_summaries = []
        for s in plan.steps:
            if s.status == StepStatus.COMPLETED and s.result and s.action != "respond":
                step_summaries.append(f"[{s.id}] {s.description}: {str(s.result)[:500]}")

        tool_summary = ""
        if tool_results:
            tool_summary = "\n\nTool execution results:\n"
            for tr in tool_results:
                tool_summary += f"- {tr.get('tool_name', '?')}: {tr.get('output', tr.get('error', 'No output'))}\n"

        prompt = (
            f"You are MY PERSONAL AI. Synthesize a complete, helpful answer for the user.\n\n"
            f"User's question: {message}\n\n"
            f"Work completed:\n" + "\n".join(step_summaries) + "\n"
            f"{tool_summary}\n"
            f"Now provide a clear, organized final answer. Use the computed results directly."
        )

        messages = [ChatMessage(role="user", content=prompt)]
        request = ChatRequest(messages=messages, temperature=0.7, stream=False)
        response = await self.router.route_chat(request)
        return response.content

    def _guess_tool_inputs(self, tool_name: str, message: str) -> Dict[str, Any]:
        """Heuristic: guess tool parameters from the user message."""
        import re
        if tool_name == "calculator":
            expr_match = re.search(r'[\d\.\+\-\*/\(\)\^]+', message)
            return {"expression": expr_match.group(0) if expr_match else message}
        elif tool_name == "file_reader":
            file_match = re.search(r'[\w/\\]+\.[\w]+', message)
            return {"path": file_match.group(0) if file_match else ".", "action": "read"}
        elif tool_name == "code_analyzer":
            file_match = re.search(r'[\w/\\]+\.py', message)
            return {"path": file_match.group(0) if file_match else "server.py"}
        elif tool_name == "system_info":
            return {"category": "all"}
        elif tool_name == "datetime":
            return {"action": "now"}
        return {}

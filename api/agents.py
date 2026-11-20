"""
Autonomous Multi-Agent Routing and Execution Endpoints for MY PERSONAL AI.

Provides:
- Agent discovery and introspection (/api/v1/agents)
- Targeted agent task execution (/api/v1/agents/{agent_name}/execute)
- Autonomous intent-based agent routing (/api/v1/agents/route)
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import get_current_user
from agents import (
    AgentStatus,
    SharedContext,
    agent_registry,
)
from core.audit import create_hitl_approval, log_audit_event

router = APIRouter(prefix="/api/v1/agents", tags=["Autonomous Agents"])


class AgentExecuteRequest(BaseModel):
    task: str = Field(..., min_length=1, description="Task directive for the agent")
    conversation_id: Optional[str] = None


class AgentRouteRequest(BaseModel):
    intent: Optional[str] = "general"
    query: str = Field(..., min_length=1, description="Query to route to best specialized agent")
    conversation_id: Optional[str] = None


@router.get("", response_model=List[Dict[str, Any]], summary="List registered autonomous agents")
async def list_registered_agents(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Enumerate all available specialized autonomous agents."""
    return agent_registry.list_agents()


@router.post("/{agent_name}/execute", summary="Execute task with a specific agent")
async def execute_agent_task(
    agent_name: str,
    req: AgentExecuteRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Execute a directive using a designated specialized agent."""
    agent = agent_registry.get(agent_name)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' not found in registry.",
        )

    context = SharedContext(
        user_id=current_user["user_id"],
        conversation_id=req.conversation_id,
    )

    result = await agent.execute(req.task, context)

    # If blocked by HITL, persist approval into SQLite
    if result.status == AgentStatus.BLOCKED_AWAITING_APPROVAL:
        approval_id = create_hitl_approval(
            user_id=current_user["user_id"],
            agent_name=agent_name,
            action=f"execute_{agent_name}_task",
            reason=result.output,
            risk_level=result.risk_level.value,
            conversation_id=req.conversation_id,
            metadata=result.metadata,
        )
        result.metadata["approval_id"] = approval_id

    log_audit_event(
        event_type="AGENT_EXECUTION",
        action=f"execute_{agent_name}",
        user_id=current_user["user_id"],
        status=result.status.value,
        severity=result.risk_level.value,
        details={"task": req.task[:80], "agent": agent_name},
    )

    return {
        "agent_name": result.agent_name,
        "task_id": result.task_id,
        "status": result.status.value,
        "risk_level": result.risk_level.value,
        "output": result.output,
        "metadata": result.metadata,
        "events": context.get_events(),
    }


@router.post("/route", summary="Intelligently route and execute a task")
async def route_and_execute_task(
    req: AgentRouteRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Analyze intent and dispatch task to the optimal specialized agent."""
    target_agent = agent_registry.route_task(intent=req.intent or "general", task_text=req.query)
    context = SharedContext(
        user_id=current_user["user_id"],
        conversation_id=req.conversation_id,
    )
    result = await target_agent.execute(req.query, context)

    return {
        "routed_to_agent": target_agent.name,
        "agent_role": target_agent.role,
        "status": result.status.value,
        "risk_level": result.risk_level.value,
        "output": result.output,
        "metadata": result.metadata,
    }

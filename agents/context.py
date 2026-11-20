"""
Shared Context and Blackboard for Multi-Agent Collaboration (Milestone E).

Provides:
- Thread-safe shared blackboard for inter-agent state passing.
- Event timeline tracking for agent handoffs and tool executions.
- Human-in-the-Loop (HITL) approval queue for high-risk operations.
"""

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class SharedContext:
    """Blackboard and execution context shared across cooperating agents."""

    def __init__(
        self,
        user_id: str,
        conversation_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ):
        self.user_id = user_id
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.task_id = task_id or str(uuid.uuid4())
        self._blackboard: Dict[str, Any] = {}
        self._events: List[Dict[str, Any]] = []
        self._hitl_queue: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def set(self, key: str, value: Any) -> None:
        """Store an artifact or intermediate value in the blackboard."""
        with self._lock:
            self._blackboard[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the blackboard."""
        with self._lock:
            return self._blackboard.get(key, default)

    def add_event(self, agent_name: str, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Record an event in the context timeline."""
        with self._lock:
            event = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": agent_name,
                "type": event_type,
                "data": data or {},
            }
            self._events.append(event)

    def get_events(self) -> List[Dict[str, Any]]:
        """Return a copy of the event timeline."""
        with self._lock:
            return list(self._events)

    def request_human_approval(
        self,
        action: str,
        agent_name: str,
        reason: str,
        risk_level: str = "HIGH",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Submit an action to the HITL approval queue. Returns approval_id."""
        with self._lock:
            approval_id = str(uuid.uuid4())
            item = {
                "id": approval_id,
                "action": action,
                "agent": agent_name,
                "reason": reason,
                "risk_level": risk_level,
                "status": "PENDING",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            }
            self._hitl_queue.append(item)
            self.add_event(agent_name, "hitl_approval_requested", item)
            return approval_id

    def resolve_human_approval(self, approval_id: str, approved: bool) -> bool:
        """Approve or deny a pending HITL request."""
        with self._lock:
            for item in self._hitl_queue:
                if item["id"] == approval_id and item["status"] == "PENDING":
                    item["status"] = "APPROVED" if approved else "DENIED"
                    item["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    self.add_event(
                        item["agent"],
                        "hitl_approval_resolved",
                        {"id": approval_id, "approved": approved},
                    )
                    return True
            return False

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """List all approvals currently awaiting human confirmation."""
        with self._lock:
            return [a for a in self._hitl_queue if a["status"] == "PENDING"]

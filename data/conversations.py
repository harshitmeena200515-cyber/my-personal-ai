"""
User-Isolated Conversation and Task Persistence Layer for MY PERSONAL AI (Phase 4B).

Enforces strict tenant isolation: every query scopes records by user_id to prevent
IDOR, cross-user data access, and unauthorized data leakage.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from data.db import db
from core.logging import logger


def create_conversation(user_id: str, title: str = "New Conversation") -> Dict[str, Any]:
    """Create a new conversation record owned by user_id."""
    db.init_db()
    conv_id = str(uuid.uuid4())
    cleaned_title = (title or "New Conversation").strip()[:100]

    db.execute(
        """
        INSERT INTO conversations (id, user_id, title)
        VALUES (?, ?, ?);
        """,
        (conv_id, user_id, cleaned_title),
    )
    logger.info("conversation_created", user_id=user_id, conversation_id=conv_id)
    return {
        "id": conv_id,
        "user_id": user_id,
        "title": cleaned_title,
    }


def list_user_conversations(user_id: str) -> List[Dict[str, Any]]:
    """List all conversations owned by a specific user, ordered by recent update."""
    db.init_db()
    rows = db.fetch_all(
        """
        SELECT id, user_id, title, created_at, updated_at
        FROM conversations
        WHERE user_id = ?
        ORDER BY updated_at DESC;
        """,
        (user_id,),
    )
    return rows


def get_conversation(user_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve conversation only if owned by the requesting user (IDOR protection)."""
    db.init_db()
    row = db.fetch_one(
        """
        SELECT id, user_id, title, created_at, updated_at
        FROM conversations
        WHERE id = ? AND user_id = ?;
        """,
        (conversation_id, user_id),
    )
    return row


def update_conversation_title(user_id: str, conversation_id: str, title: str) -> bool:
    """Update title of a conversation owned by the requesting user."""
    db.init_db()
    cleaned = (title or "Untitled").strip()[:100]
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    affected = db.execute(
        """
        UPDATE conversations
        SET title = ?, updated_at = ?
        WHERE id = ? AND user_id = ?;
        """,
        (cleaned, now_str, conversation_id, user_id),
    )
    return affected > 0


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    """Delete a conversation owned by the requesting user (cascades to messages)."""
    db.init_db()
    affected = db.execute(
        """
        DELETE FROM conversations
        WHERE id = ? AND user_id = ?;
        """,
        (conversation_id, user_id),
    )
    if affected > 0:
        logger.info("conversation_deleted", user_id=user_id, conversation_id=conversation_id)
        return True
    return False


def add_message(
    user_id: str,
    conversation_id: str,
    role: str,
    content: str,
    reasoning: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a message to a conversation owned by user_id."""
    db.init_db()

    # Verify conversation ownership before adding message
    conv = get_conversation(user_id, conversation_id)
    if not conv:
        raise PermissionError(f"Conversation '{conversation_id}' not found or access denied.")

    msg_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        """
        INSERT INTO messages (id, conversation_id, user_id, role, content, reasoning, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (msg_id, conversation_id, user_id, role, content, reasoning, now_str),
    )

    # Touch updated_at on the conversation
    db.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?;",
        (now_str, conversation_id),
    )

    return {
        "id": msg_id,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "reasoning": reasoning,
        "created_at": now_str,
    }


def get_conversation_messages(user_id: str, conversation_id: str) -> List[Dict[str, Any]]:
    """Retrieve all messages for a conversation owned by user_id."""
    db.init_db()

    # Enforce conversation ownership
    conv = get_conversation(user_id, conversation_id)
    if not conv:
        raise PermissionError(f"Conversation '{conversation_id}' not found or access denied.")

    rows = db.fetch_all(
        """
        SELECT id, conversation_id, user_id, role, content, reasoning, created_at
        FROM messages
        WHERE conversation_id = ? AND user_id = ?
        ORDER BY created_at ASC;
        """,
        (conversation_id, user_id),
    )
    return rows


def create_task_record(
    user_id: str,
    goal: str,
    conversation_id: Optional[str] = None,
    plan_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a user-owned autonomous task record."""
    db.init_db()
    task_id = str(uuid.uuid4())

    db.execute(
        """
        INSERT INTO tasks (id, user_id, conversation_id, goal, status, plan_json)
        VALUES (?, ?, ?, ?, 'pending', ?);
        """,
        (task_id, user_id, conversation_id, goal, plan_json),
    )
    logger.info("task_record_created", user_id=user_id, task_id=task_id)
    return {
        "id": task_id,
        "user_id": user_id,
        "goal": goal,
        "status": "pending",
    }


def update_task_record(
    user_id: str,
    task_id: str,
    status: str,
    result_json: Optional[str] = None,
) -> bool:
    """Update task status and results scoped to owning user."""
    db.init_db()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    completed_at = now_str if status in ("completed", "failed") else None

    affected = db.execute(
        """
        UPDATE tasks
        SET status = ?, result_json = ?, completed_at = ?
        WHERE id = ? AND user_id = ?;
        """,
        (status, result_json, completed_at, task_id, user_id),
    )
    return affected > 0


def list_user_tasks(user_id: str) -> List[Dict[str, Any]]:
    """List recent autonomous tasks for user."""
    db.init_db()
    rows = db.fetch_all(
        """
        SELECT id, user_id, conversation_id, goal, status, plan_json, result_json, created_at, completed_at
        FROM tasks
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 50;
        """,
        (user_id,),
    )
    return rows

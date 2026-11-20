"""
Conversation and Task Management Endpoints for MY PERSONAL AI (Phase 4B).

Enforces strict user authentication and data isolation on every endpoint.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import get_current_user
from data.conversations import (
    add_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_messages,
    list_user_conversations,
    list_user_tasks,
    update_conversation_title,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


class CreateConversationRequest(BaseModel):
    title: Optional[str] = Field(default="New Conversation", max_length=100)


class UpdateConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


class AddMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
    reasoning: Optional[str] = None


@router.get("", response_model=List[Dict[str, Any]], summary="List user conversations")
async def list_conversations(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Enumerate conversations owned exclusively by the authenticated user."""
    return list_user_conversations(user_id=current_user["user_id"])


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a new conversation")
async def create_new_conversation(
    req: CreateConversationRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new conversation isolated to the authenticated user."""
    return create_conversation(user_id=current_user["user_id"], title=req.title or "New Conversation")


@router.get("/{conversation_id}", summary="Get conversation details")
async def get_conversation_details(
    conversation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get conversation details, enforcing ownership verification (prevents IDOR)."""
    conv = get_conversation(user_id=current_user["user_id"], conversation_id=conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found or access denied.",
        )
    return conv


@router.patch("/{conversation_id}", summary="Rename a conversation")
async def rename_conversation(
    conversation_id: str,
    req: UpdateConversationRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update conversation title, enforcing ownership."""
    success = update_conversation_title(
        user_id=current_user["user_id"],
        conversation_id=conversation_id,
        title=req.title,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found or access denied.",
        )
    return {"message": "Conversation title updated successfully."}


@router.delete("/{conversation_id}", summary="Delete a conversation")
async def delete_user_conversation(
    conversation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a conversation, enforcing ownership."""
    success = delete_conversation(user_id=current_user["user_id"], conversation_id=conversation_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found or access denied.",
        )
    return {"message": "Conversation deleted successfully."}


@router.get("/{conversation_id}/messages", response_model=List[Dict[str, Any]], summary="Get conversation messages")
async def get_messages(
    conversation_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve all messages for a conversation, enforcing ownership."""
    try:
        return get_conversation_messages(user_id=current_user["user_id"], conversation_id=conversation_id)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found or access denied.",
        )


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED, summary="Add a message")
async def post_message(
    conversation_id: str,
    req: AddMessageRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Append a message to a conversation owned by the caller."""
    try:
        return add_message(
            user_id=current_user["user_id"],
            conversation_id=conversation_id,
            role=req.role,
            content=req.content,
            reasoning=req.reasoning,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found or access denied.",
        )


# Separate task listing router
tasks_router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])


@tasks_router.get("", response_model=List[Dict[str, Any]], summary="List user autonomous tasks")
async def list_tasks(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Enumerate autonomous tasks owned exclusively by the caller."""
    return list_user_tasks(user_id=current_user["user_id"])

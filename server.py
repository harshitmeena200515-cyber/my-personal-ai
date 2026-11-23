import json
import platform
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core.config import settings
from core.logging import setup_logging, logger
from models.router import model_router, ChatRequest, ChatResponse
from tools import tool_registry
from core.orchestrator import Orchestrator, OrchestratorConfig
from data.db import db
from api.auth import router as auth_router, get_current_user
from api.conversations import router as conversations_router, tasks_router
from api.security import router as security_router
from api.agents import router as agents_router
from data.conversations import add_message, create_conversation, create_task_record, update_task_record

setup_logging(debug=settings.DEBUG)

orchestrator = Orchestrator(
    model_router=model_router,
    tool_registry=tool_registry,
    config=OrchestratorConfig(),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown hooks."""
    try:
        db.init_db()
        logger.info("database_ready", db_path=str(db.db_path))
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Autonomous Personal AI Platform with Local Model Integration",
    lifespan=lifespan,
)

# Include Authentication, Isolation, Security & Multi-Agent Routers (Phase 4)
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(tasks_router)
app.include_router(security_router)
app.include_router(agents_router)

# Restrict CORS to local origins only for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Mount frontend and static directories for local web UI
frontend_dir = Path(__file__).parent / "frontend"
static_dir = Path(__file__).parent / "static"

if frontend_dir.exists():
    app.mount("/frontend", StaticFiles(directory=str(frontend_dir)), name="frontend")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the modern local web chat interface."""
    frontend_index = frontend_dir / "index.html"
    if frontend_index.exists():
        return HTMLResponse(content=frontend_index.read_text(encoding="utf-8"))
    static_index = static_dir / "index.html"
    if static_index.exists():
        return HTMLResponse(content=static_index.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>MY PERSONAL AI is running</h1><p>Frontend UI not found.</p>")


@app.get("/health")
async def health_check():
    """Verify local system and model engine health."""
    health_data = await model_router.get_system_health()
    is_healthy = health_data.get("local_engine_online", False) or health_data.get("cloud_enabled", False)
    return {
        "status": "healthy" if is_healthy else "degraded",
        "version": settings.VERSION,
        "host": settings.HOST,
        "port": settings.PORT,
        "router": health_data,
        "brain": {
            "orchestrator_online": True,
            "registered_tools": len(tool_registry.list_tools()),
        },
        "database": {
            "online": True,
            "path": str(db.db_path),
        },
        "hardware": {
            "os": platform.system(),
            "python": platform.python_version(),
            "gpu": "NVIDIA GeForce RTX 3050 Laptop GPU (4GB VRAM)",
            "ram": "16 GB",
        },
    }


@app.get("/api/v1/system/info")
async def system_info():
    """Get system and hardware specifications."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "gpu": "NVIDIA GeForce RTX 3050 Laptop GPU (4GB VRAM)",
        "ram": "16 GB",
    }


@app.get("/api/v1/models/status")
async def models_status():
    """Get model router configuration status."""
    return {
        "router_mode": model_router.mode,
        "default_local": settings.DEFAULT_LOCAL_MODEL,
        "default_cloud": settings.DEFAULT_CLOUD_MODEL,
        "ollama_endpoint": settings.OLLAMA_BASE_URL,
        "cloud_providers": {
            "gemini": False,
            "groq": False,
            "openai": False,
            "anthropic": False,
        },
    }


@app.get("/api/v1/models")
async def list_models():
    """Enumerate all available local AI models."""
    try:
        models = await model_router.list_available_models()
        return {
            "count": len(models),
            "router_mode": model_router.mode,
            "models": [m.model_dump() for m in models],
        }
    except Exception as e:
        logger.error("error_listing_models", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to retrieve local models: {str(e)}",
        )


@app.post("/api/v1/chat")
async def chat_endpoint(
    request: ChatRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Handle chat completion requests (requires authenticated user)."""
    if not request.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'messages' list cannot be empty.",
        )

    # 1. Handle Streaming Response
    if request.stream:
        async def event_generator():
            try:
                async for chunk in model_router.route_chat_stream(request):
                    data_str = json.dumps(chunk)
                    yield f"data: {data_str}\n\n"
                yield "data: [DONE]\n\n"
            except ValueError as ve:
                err_data = json.dumps({"error": str(ve)})
                yield f"data: {err_data}\n\n"
            except Exception as e:
                logger.error("chat_stream_error", error=str(e), user_id=current_user["user_id"])
                err_data = json.dumps({"error": f"Internal inference error: {str(e)}"})
                yield f"data: {err_data}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # 2. Handle Non-Streaming Response
    try:
        response: ChatResponse = await model_router.route_chat(request)
        return response
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error("chat_error", error=str(e), user_id=current_user["user_id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Local inference failure: {str(e)}",
        )


@app.get("/api/v1/tools")
async def list_registered_tools(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Enumerate all available sandboxed tools in the Tool Registry (requires auth)."""
    tools = tool_registry.list_tools()
    return {
        "count": len(tools),
        "tools": [t.model_dump() for t in tools],
    }


from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ThinkRequest(BaseModel):
    message: str = Field(..., description="Goal or instruction for the autonomous agent")
    history: Optional[List[Dict[str, str]]] = Field(default=None, description="Recent conversation turns")
    conversation_id: Optional[str] = Field(default=None, description="Optional conversation ID for persistence")
    stream: bool = Field(default=False, description="Whether to stream real-time progress events")
    enable_planning: bool = Field(default=True, description="Allow multi-step task decomposition")


@app.post("/api/v1/think")
async def think_endpoint(
    request: ThinkRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Autonomous Intelligence endpoint (requires authenticated user)."""
    if not request.message or not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'message' parameter cannot be empty.",
        )

    user_id = current_user["user_id"]

    # If conversation_id is provided, persist user message
    if request.conversation_id:
        try:
            add_message(
                user_id=user_id,
                conversation_id=request.conversation_id,
                role="user",
                content=request.message,
            )
        except Exception as e:
            logger.warning("persist_user_message_failed", error=str(e))

    # 1. Handle Streaming Progress Events
    if request.stream:
        async def progress_generator():
            try:
                full_answer = []
                async for update in orchestrator.process_stream(
                    user_message=request.message,
                    conversation_history=request.history,
                ):
                    data_str = json.dumps(update.model_dump())
                    yield f"data: {data_str}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error("think_stream_error", error=str(e), user_id=user_id)
                err_data = json.dumps({"phase": "error", "message": f"Autonomous pipeline error: {str(e)}"})
                yield f"data: {err_data}\n\n"

        return StreamingResponse(progress_generator(), media_type="text/event-stream")

    # 2. Handle Non-Streaming Synchronous Response
    try:
        # Create task record
        task = create_task_record(
            user_id=user_id,
            goal=request.message,
            conversation_id=request.conversation_id,
        )

        result = await orchestrator.process(
            user_message=request.message,
            conversation_history=request.history,
        )

        # Update task status
        update_task_record(
            user_id=user_id,
            task_id=task["id"],
            status="completed" if result.verification.passed else "failed",
            result_json=json.dumps({"answer": result.answer, "confidence": result.confidence}),
        )

        # Persist assistant response if conversation_id provided
        if request.conversation_id:
            try:
                add_message(
                    user_id=user_id,
                    conversation_id=request.conversation_id,
                    role="assistant",
                    content=result.answer,
                    reasoning=result.reasoning.reasoning if result.reasoning else None,
                )
            except Exception as pe:
                logger.warning("persist_assistant_message_failed", error=str(pe))

        return result.model_dump()
    except Exception as e:
        logger.error("think_endpoint_error", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Autonomous processing failure: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn
    logger.info("starting_local_server", host=settings.HOST, port=settings.PORT)
    uvicorn.run("server:app", host=settings.HOST, port=settings.PORT, reload=False)

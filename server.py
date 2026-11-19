import json
import platform
from pathlib import Path
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core.config import settings
from core.logging import setup_logging, logger
from models.router import model_router, ChatRequest, ChatResponse
from tools import tool_registry
from core.orchestrator import Orchestrator, OrchestratorConfig

setup_logging(debug=settings.DEBUG)

orchestrator = Orchestrator(
    model_router=model_router,
    tool_registry=tool_registry,
    config=OrchestratorConfig(),
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Autonomous Personal AI Platform with Local Model Integration",
)

# Restrict CORS to local origins only for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Mount static directory for local chat UI
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the local web chat interface."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>MY PERSONAL AI is running</h1><p>Static UI not found.</p>")


@app.get("/health")
async def health_check():
    """Verify local system and model engine health."""
    health_data = await model_router.get_system_health()
    return {
        "status": "healthy" if health_data["local_engine_online"] else "degraded",
        "version": settings.VERSION,
        "host": settings.HOST,
        "port": settings.PORT,
        "router": health_data,
        "brain": {
            "orchestrator_online": True,
            "registered_tools": len(tool_registry.list_tools()),
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
async def chat_endpoint(request: ChatRequest):
    """Handle chat completion requests (supports both streaming and non-streaming)."""
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
                logger.error("chat_stream_error", error=str(e))
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
        logger.error("chat_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Local inference failure: {str(e)}",
        )


@app.get("/api/v1/tools")
async def list_registered_tools():
    """Enumerate all available sandboxed tools in the Tool Registry."""
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
    stream: bool = Field(default=False, description="Whether to stream real-time progress events")
    enable_planning: bool = Field(default=True, description="Allow multi-step task decomposition")


@app.post("/api/v1/think")
async def think_endpoint(request: ThinkRequest):
    """Autonomous Intelligence endpoint: reasoning, planning, tool execution, and verification."""
    if not request.message or not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'message' parameter cannot be empty.",
        )

    # 1. Handle Streaming Progress Events
    if request.stream:
        async def progress_generator():
            try:
                async for update in orchestrator.process_stream(
                    user_message=request.message,
                    conversation_history=request.history,
                ):
                    data_str = json.dumps(update.model_dump())
                    yield f"data: {data_str}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error("think_stream_error", error=str(e))
                err_data = json.dumps({"phase": "error", "message": f"Autonomous pipeline error: {str(e)}"})
                yield f"data: {err_data}\n\n"

        return StreamingResponse(progress_generator(), media_type="text/event-stream")

    # 2. Handle Non-Streaming Synchronous Response
    try:
        result = await orchestrator.process(
            user_message=request.message,
            conversation_history=request.history,
        )
        return result.model_dump()
    except Exception as e:
        logger.error("think_endpoint_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Autonomous processing failure: {str(e)}",
        )


if __name__ == "__main__":
    import uvicorn
    logger.info("starting_local_server", host=settings.HOST, port=settings.PORT)
    uvicorn.run("server:app", host=settings.HOST, port=settings.PORT, reload=False)

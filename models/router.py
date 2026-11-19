from typing import List, Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel, Field
from core.config import settings
from core.logging import logger
from .ollama_client import OllamaClient


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the author: system, user, assistant")
    content: str = Field(..., description="Text content of the message")


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    stream: bool = False
    temperature: float = 0.7


class ChatResponse(BaseModel):
    role: str
    content: str
    model: str
    provider: str
    latency_sec: float
    eval_count: int
    tokens_per_sec: float


class ModelInfo(BaseModel):
    name: str
    provider: str
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    family: Optional[str] = None
    context_length: int = 4096
    size_mb: float = 0.0
    is_local: bool = True
    available: bool = True


class ModelRouter:
    """Provider-independent AI Model Router.
    Currently locked strictly to local inference per Phase 2 requirements.
    """

    def __init__(self):
        self.ollama = OllamaClient()
        self.mode = "local_only"  # Strict local enforcement for Phase 2

    async def get_system_health(self) -> Dict[str, Any]:
        """Verify health of local model engine."""
        ollama_alive = await self.ollama.health_check()
        return {
            "router_mode": self.mode,
            "local_engine": "ollama",
            "local_engine_online": ollama_alive,
            "cloud_enabled": False,  # Disabled in Phase 2
        }

    async def list_available_models(self) -> List[ModelInfo]:
        """Enumerate models across active providers (Local Ollama only)."""
        models = []
        raw_ollama_models = await self.ollama.list_models()
        for m in raw_ollama_models:
            size_mb = round((m.get("size_bytes") or 0) / (1024 * 1024), 2)
            models.append(
                ModelInfo(
                    name=m["name"],
                    provider="ollama",
                    parameter_size=m.get("parameter_size"),
                    quantization=m.get("quantization"),
                    family=m.get("family"),
                    context_length=m.get("context_length", 4096),
                    size_mb=size_mb,
                    is_local=True,
                    available=True,
                )
            )
        return models

    async def route_chat(self, req: ChatRequest) -> ChatResponse:
        """Route a non-streaming chat request to the local engine."""
        target_model = req.model or settings.DEFAULT_LOCAL_MODEL

        # Security check: verify model is available locally
        is_avail = await self.ollama.is_model_available(target_model)
        if not is_avail:
            raise ValueError(f"Requested model '{target_model}' is not installed locally in Ollama.")

        msg_dicts = [{"role": m.role, "content": m.content} for m in req.messages]
        res = await self.ollama.chat(
            messages=msg_dicts,
            model=target_model,
            temperature=req.temperature,
        )

        return ChatResponse(
            role=res["role"],
            content=res["content"],
            model=res["model"],
            provider="ollama_local",
            latency_sec=res["total_duration_sec"],
            eval_count=res["eval_count"],
            tokens_per_sec=res["tokens_per_sec"],
        )

    async def route_chat_stream(self, req: ChatRequest) -> AsyncGenerator[Dict[str, Any], None]:
        """Route a streaming chat request to the local engine."""
        target_model = req.model or settings.DEFAULT_LOCAL_MODEL

        is_avail = await self.ollama.is_model_available(target_model)
        if not is_avail:
            raise ValueError(f"Requested model '{target_model}' is not installed locally in Ollama.")

        msg_dicts = [{"role": m.role, "content": m.content} for m in req.messages]
        async for chunk in self.ollama.chat_stream(
            messages=msg_dicts,
            model=target_model,
            temperature=req.temperature,
        ):
            yield chunk


model_router = ModelRouter()

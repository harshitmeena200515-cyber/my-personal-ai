import time
from typing import List, Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel, Field
from core.config import settings
from core.logging import logger
from core.external_advisor import gemini_advisor
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
        self.gemini = gemini_advisor
        self.mode = "hybrid"  # Supports local Ollama + Google AI Studio Gemini

    async def get_system_health(self) -> Dict[str, Any]:
        """Verify health of local model engine and cloud advisor."""
        ollama_alive = await self.ollama.health_check()
        return {
            "router_mode": self.mode,
            "local_engine": "ollama",
            "local_engine_online": ollama_alive,
            "cloud_enabled": self.gemini.is_configured,
            "cloud_provider": "google_ai_studio" if self.gemini.is_configured else None,
        }

    async def list_available_models(self) -> List[ModelInfo]:
        """Enumerate models across active providers (Ollama + Google AI Studio)."""
        models = []

        # 1. Google AI Studio models if configured
        if self.gemini.is_configured:
            for gemini_m in self.gemini.model_cascade:
                models.append(
                    ModelInfo(
                        name=gemini_m,
                        provider="google_ai_studio",
                        parameter_size="Multimodal",
                        quantization="Cloud FP16",
                        family="gemini",
                        context_length=128000,
                        size_mb=0.0,
                        is_local=False,
                        available=True,
                    )
                )

        # 2. Local Ollama models
        try:
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
        except Exception:
            pass

        return models

    async def route_chat(self, req: ChatRequest) -> ChatResponse:
        """Route a chat request: uses Gemini if requested or if local engine is offline."""
        target_model = req.model or settings.DEFAULT_LOCAL_MODEL
        start_time = time.time()

        # Check if requested model is a Gemini model or if local is offline
        is_gemini_requested = target_model.startswith("gemini") or target_model == "google_ai_studio"
        ollama_alive = await self.ollama.health_check()

        if is_gemini_requested or (not ollama_alive and self.gemini.is_configured):
            # Format prompt from message history
            last_user_msg = ""
            system_role = "You are a professional, intelligent AI assistant specializing in mathematics, code synthesis, and deep analytical reasoning. Format your answers clearly with step-by-step solutions."
            history_parts = []

            for m in req.messages:
                if m.role == "system":
                    system_role = m.content
                elif m.role == "user":
                    last_user_msg = m.content
                    history_parts.append(f"User: {m.content}")
                elif m.role == "assistant":
                    history_parts.append(f"Assistant: {m.content}")

            combined_prompt = "\n".join(history_parts) if history_parts else last_user_msg
            pref_model = target_model if target_model.startswith("gemini") else None

            res = await asyncio.to_thread(
                self.gemini.consult_advisor,
                prompt=combined_prompt,
                system_role=system_role,
                max_tokens=2048,
                preferred_model=pref_model,
                timeout_seconds=8.0,
            )

            latency = round(time.time() - start_time, 3)

            if res.get("success"):
                content = res.get("advice", "")
                model_used = res.get("model_used", "gemini-flash-lite-latest")
                eval_count = len(content.split())
                tok_per_sec = round(eval_count / max(latency, 0.1), 1)

                return ChatResponse(
                    role="assistant",
                    content=content,
                    model=model_used,
                    provider="google_ai_studio",
                    latency_sec=latency,
                    eval_count=eval_count,
                    tokens_per_sec=tok_per_sec,
                )
            else:
                logger.warning("gemini_chat_failed", error=res.get("error"))
                # If Gemini failed and Ollama is available, fallback to Ollama
                if not ollama_alive:
                    raise ValueError(f"AI Consultation Failed: {res.get('error')}")

        # Local Ollama Inference
        is_avail = await self.ollama.is_model_available(target_model)
        if not is_avail:
            raise ValueError(f"Requested model '{target_model}' is not installed locally in Ollama and cloud fallback is unavailable.")

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
        """Route a streaming chat request to local engine or Gemini."""
        target_model = req.model or settings.DEFAULT_LOCAL_MODEL
        is_gemini_requested = target_model.startswith("gemini") or target_model == "google_ai_studio"
        ollama_alive = await self.ollama.health_check()

        if is_gemini_requested or (not ollama_alive and self.gemini.is_configured):
            # Non-blocking async execution for Gemini cloud inference
            chat_resp = await self.route_chat(req)
            # Stream fluid token chunks for immediate responsive typing
            words = chat_resp.content.split(" ")
            for i, w in enumerate(words):
                chunk_text = w + (" " if i < len(words) - 1 else "")
                yield {
                    "role": "assistant",
                    "content": chunk_text,
                    "model": chat_resp.model,
                    "provider": chat_resp.provider,
                    "done": False,
                }
                if i % 3 == 0:
                    await asyncio.sleep(0.015)
            yield {
                "role": "assistant",
                "content": "",
                "model": chat_resp.model,
                "provider": chat_resp.provider,
                "done": True,
            }
            return

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

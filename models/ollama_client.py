import json
import httpx
from typing import AsyncGenerator, Optional, Dict, Any, List
from core.config import settings
from core.logging import logger


class OllamaClient:
    """Async client for interacting with the local Ollama instance."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 120.0):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.timeout = timeout

    async def health_check(self) -> bool:
        """Verify that the local Ollama server is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/")
                return res.status_code == 200
        except Exception as e:
            logger.warning("ollama_health_check_failed", error=str(e))
            return False

    async def list_models(self) -> List[Dict[str, Any]]:
        """Retrieve the list of installed local models."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = []
                    for m in data.get("models", []):
                        models.append({
                            "name": m.get("name"),
                            "size_bytes": m.get("size"),
                            "modified_at": m.get("modified_at"),
                            "parameter_size": m.get("details", {}).get("parameter_size"),
                            "quantization": m.get("details", {}).get("quantization_level"),
                            "family": m.get("details", {}).get("family"),
                            "context_length": m.get("details", {}).get("context_length", 4096),
                            "format": m.get("details", {}).get("format", "gguf"),
                        })
                    return models
                return []
        except Exception as e:
            logger.error("ollama_list_models_failed", error=str(e))
            return []

    async def is_model_available(self, model_name: str) -> bool:
        """Check if a specific model is installed locally."""
        installed = await self.list_models()
        model_clean = model_name.split(":")[0]
        return any(
            m["name"] == model_name or m["name"].startswith(f"{model_clean}:")
            for m in installed
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Execute a non-streaming multi-turn chat completion."""
        target_model = model or settings.DEFAULT_LOCAL_MODEL
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/api/chat", json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Ollama chat error {res.status_code}: {res.text}")

            data = res.json()
            eval_count = data.get("eval_count", 0)
            eval_duration_sec = data.get("eval_duration", 1) / 1e9
            tokens_per_sec = (eval_count / eval_duration_sec) if eval_duration_sec > 0 else 0

            return {
                "role": data.get("message", {}).get("role", "assistant"),
                "content": data.get("message", {}).get("content", ""),
                "model": data.get("model", target_model),
                "total_duration_sec": round(data.get("total_duration", 0) / 1e9, 2),
                "load_duration_sec": round(data.get("load_duration", 0) / 1e9, 2),
                "eval_count": eval_count,
                "tokens_per_sec": round(tokens_per_sec, 2),
            }

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream chat completion tokens in real-time."""
        target_model = model or settings.DEFAULT_LOCAL_MODEL
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise RuntimeError(f"Ollama stream error {response.status_code}: {err_body.decode('utf-8')}")

                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            yield {
                                "content": chunk.get("message", {}).get("content", ""),
                                "done": chunk.get("done", False),
                                "model": chunk.get("model", target_model),
                                "eval_count": chunk.get("eval_count", 0),
                                "eval_duration": chunk.get("eval_duration", 0),
                                "total_duration": chunk.get("total_duration", 0),
                            }
                        except json.JSONDecodeError:
                            continue

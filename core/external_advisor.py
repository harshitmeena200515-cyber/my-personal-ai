"""
External Advisor Adapter (Phase 8 / ADR-001 & ADR-009).

Provides:
- Privacy-preserving external cloud model integration (OpenAI / Cloud Advisors).
- Inbound data sanitization: Redacts local Windows file paths, PII, and credentials before transmission.
- Pure Python standard library HTTP client (urllib.request) to avoid native DLL AppLocker issues.
- Provenance tagging: All received suggestions are explicitly marked EXTERNALLY_VERIFIED.
- Zero autonomous writes: Output requires Harshit's approval to enter Shared Memory.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from core.logging import logger
from core.memory_manager import DataSanitizer, Provenance


class ExternalAdvisorSanitizer:
    """Scrubs local paths, PII, and sensitive identifiers from outbound prompts."""

    PATH_PATTERN = re.compile(r"[A-Za-z]:\\(?:[a-zA-Z0-9_\- ]+\\)*[a-zA-Z0-9_\-\.]+", re.IGNORECASE)
    EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    @classmethod
    def sanitize_outbound_prompt(cls, prompt: str) -> str:
        """Replace local paths and personal identifiers with generic tokens."""
        # Check for raw secrets first (blocks execution if secrets detected)
        DataSanitizer.sanitize(prompt)

        sanitized = cls.EMAIL_PATTERN.sub("<REDACTED_EMAIL>", prompt)
        sanitized = cls.PATH_PATTERN.sub("<REDACTED_LOCAL_PATH>", sanitized)
        sanitized = cls.IP_PATTERN.sub("<REDACTED_IP>", sanitized)
        return sanitized


class OpenAIAdvisorAdapter:
    """Sandboxed, privacy-preserving adapter for OpenAI advisor consultation."""

    DEFAULT_MODEL = "gpt-4o-mini"
    API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key if api_key is not None else self._load_key_from_env()

    @staticmethod
    def _load_key_from_env() -> Optional[str]:
        """Read OPENAI_API_KEY from process environment or .env file."""
        key = os.getenv("OPENAI_API_KEY")
        if key:
            return key

        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("OPENAI_API_KEY="):
                            return line.split("=", 1)[1].strip()
            except Exception as e:
                logger.warning("env_file_read_error", error=str(e))
        return None

    @property
    def is_configured(self) -> bool:
        """Check if an API key is present."""
        return bool(self._api_key and self._api_key.startswith("sk-"))

    def consult_advisor(
        self,
        prompt: str,
        system_role: str = "You are an expert technical architecture advisor. Provide concise, safe advice.",
        max_tokens: int = 300,
        timeout_seconds: float = 10.0,
    ) -> Dict[str, Any]:
        """
        Sanitize prompt, query external advisor, and package response with EXTERNALLY_VERIFIED provenance.
        """
        # 1. Inbound sanitization
        clean_prompt = ExternalAdvisorSanitizer.sanitize_outbound_prompt(prompt)

        if not self.is_configured:
            return {
                "success": False,
                "error": "OPENAI_API_KEY not configured. Advisor consultation unavailable in offline mode.",
                "provenance": Provenance.EXTERNALLY_VERIFIED.value,
                "advice": None,
                "requires_owner_approval": True,
            }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        data = json.dumps({
            "model": self.DEFAULT_MODEL,
            "messages": [
                {"role": "system", "content": system_role},
                {"role": "user", "content": clean_prompt},
            ],
            "max_tokens": max_tokens,
        }).encode("utf-8")

        req = urllib.request.Request(self.API_URL, data=data, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                res_json = json.loads(response.read().decode("utf-8"))
                content = res_json["choices"][0]["message"]["content"].strip()
                logger.info("external_advisor_response_received", model=self.DEFAULT_MODEL)

                return {
                    "success": True,
                    "advice": content,
                    "provenance": Provenance.EXTERNALLY_VERIFIED.value,
                    "confidence": 0.80,  # Standard external advice confidence
                    "model_used": self.DEFAULT_MODEL,
                    "sanitized_prompt": clean_prompt,
                    "requires_owner_approval": True,
                }

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.warning("external_advisor_http_error", code=e.code, body=err_body)
            return {
                "success": False,
                "error": f"HTTP Error {e.code}: {err_body}",
                "provenance": Provenance.EXTERNALLY_VERIFIED.value,
                "advice": None,
                "requires_owner_approval": True,
            }
        except Exception as e:
            logger.warning("external_advisor_network_error", error=str(e))
            return {
                "success": False,
                "error": f"Connection Error: {str(e)}",
                "provenance": Provenance.EXTERNALLY_VERIFIED.value,
                "advice": None,
                "requires_owner_approval": True,
            }


# Global adapter instance
external_advisor = OpenAIAdvisorAdapter()

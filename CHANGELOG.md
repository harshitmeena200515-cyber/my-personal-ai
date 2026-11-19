# Changelog

All notable changes to **MY PERSONAL AI** will be documented in this file.

## [v0.2.0] - 2026-11-19
### Added
- **Ollama Integration (`models/ollama_client.py`):** Async HTTP client connecting to local Ollama runtime (`http://127.0.0.1:11434`), supporting health checks, model discovery, standard chat, and real-time SSE streaming.
- **Provider-Independent Model Router (`models/router.py`):** Unified `ModelRouter` interface with local-first policy, model availability checking, and dynamic fallback.
- **Local Model Installation:** Verified download and GPU offloading for `qwen2.5-coder:3b` (37/37 layers offloaded to RTX 3050 CUDA0; ~56 tok/s generation speed; ~2.1 GB VRAM usage).
- **FastAPI Endpoints (`server.py`):**
  - `GET /health` with Ollama background status check.
  - `GET /api/v1/models` listing active local models and parameters.
  - `POST /api/v1/chat` supporting both JSON and streaming Server-Sent Events (SSE).
- **Interactive Local Web UI (`static/index.html`):** Dark-mode responsive chat interface with streaming markdown rendering, latency/speed metrics, model selector, and system health status.
- **Comprehensive Verification Suite (`tests/test_phase2.py`):** 7 end-to-end integration tests verifying UI serving, health, discovery, non-streaming inference, SSE streaming, and error handling with 100% pass rate.

## [v0.1.0] - 2026-11-16
### Added
- Phase 1 scaffolding complete: clean modular repository structure (`core/`, `agents/`, `memory/`, `models/`, `tools/`, `tests/`, `docs/`, `sandbox/`, `scripts/`).
- Python virtual environment `.venv` with core dependencies (`fastapi`, `uvicorn`, `pydantic`, `httpx`, `structlog`, `python-dotenv`).
- Structured configuration management via `core/config.py` with `.env` support.
- JSON-structured logging via `core/logging.py`.
- FastAPI server entrypoint `server.py` with `/health`, `/api/v1/system/info`, and `/api/v1/models/status` endpoints.
- Automated endpoint test suite `tests/test_server.py` with 100% pass rate.
- Git repository initialization and `.gitignore` setup.

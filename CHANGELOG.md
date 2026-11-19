# Changelog

All notable changes to **MY PERSONAL AI** will be documented in this file.

## [v0.3.0] - 2026-11-19
### Added
- **Reasoning Engine (`core/reasoning.py`):** Intent classification, complexity analysis (1-5 scale), structured JSON prompting, and heuristic fallback.
- **Task Planning Engine (`core/planner.py`):** Goal decomposition into atomic `TaskStep` objects, dependency resolution (`get_next_step`), and security sanitization blocking arbitrary command execution.
- **Sandboxed Tool System (`tools/`):**
  - `tools/base.py`: Abstract `BaseTool`, `ToolResult`, permission tiers (`SAFE`, `READ_ONLY`, `RESTRICTED`), and central `ToolRegistry`.
  - `tools/calculator.py`: Safe math evaluation using Python's `ast` (zero `eval()` or `exec()`).
  - `tools/file_reader.py`: Sandboxed read-only file access restricted to project root with hard blocks on `.env`, `.git/`, `.venv/`, and path traversal.
  - `tools/code_analyzer.py`: Static Python AST inspection (classes, functions, imports, syntax validation).
  - `tools/system_info.py`: Read-only system metrics (CPU, RAM, GPU RTX 3050, disk).
  - `tools/datetime_tool.py`: Date/time calculations, arithmetic, and ISO formatting.
- **Master Orchestrator (`core/orchestrator.py`):** Full autonomous pipeline coordinating Reasoning → Planning → Tool Execution → Verification with streaming progress updates.
- **Self-Verification Engine (`core/verifier.py`):** Output validation for format integrity, completeness, safety checks (blocking dangerous patterns like `rm -rf`, `DROP TABLE`), and consistency with tool results.
- **Error Recovery Engine (`core/recovery.py`):** Tiered recovery escalation (`RETRY_WITH_CONTEXT` → `SIMPLIFY` → `FALLBACK_DIRECT`) and circuit breaker pattern.
- **FastAPI Endpoints (`server.py`):**
  - `GET /api/v1/tools` listing registered sandboxed tools and parameter schemas.
  - `POST /api/v1/think` for autonomous reasoning and execution (with streaming SSE progress events).
- **Web UI Upgrade (`static/index.html`):** Mode toggle between "🧠 Autonomous Brain" and "⚡ Direct Chat", live thought progress visualization, and active tools badge.
- **Automated Verification Suites:** 6 new test suites (`test_tools.py`, `test_reasoning.py`, `test_planner.py`, `test_verifier.py`, `test_recovery.py`, `test_phase3.py`) with 100% pass rate.

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

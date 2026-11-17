# Changelog

All notable changes to **MY PERSONAL AI** will be documented in this file.

## [v0.1.0] - 2026-11-16
### Added
- Phase 1 scaffolding complete: clean modular repository structure (`core/`, `agents/`, `memory/`, `models/`, `tools/`, `tests/`, `docs/`, `sandbox/`, `scripts/`).
- Python virtual environment `.venv` with core dependencies (`fastapi`, `uvicorn`, `pydantic`, `httpx`, `structlog`, `python-dotenv`).
- Structured configuration management via `core/config.py` with `.env` support.
- JSON-structured logging via `core/logging.py`.
- FastAPI server entrypoint `server.py` with `/health`, `/api/v1/system/info`, and `/api/v1/models/status` endpoints.
- Automated endpoint test suite `tests/test_server.py` with 100% pass rate.
- Git repository initialization and `.gitignore` setup.

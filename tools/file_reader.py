"""
Sandboxed File Reader Tool.

Reads files ONLY within the project directory. Strictly read-only.
Blocks access to .env, .git/, __pycache__/, .venv/, and system paths.
"""

import os
from pathlib import Path
from typing import Any, Dict

from tools.base import BaseTool, ToolResult, ToolParameter, PermissionLevel

# Project root — the only directory we allow reading from
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Blocked paths and patterns
_BLOCKED_NAMES = {".env", ".git", "__pycache__", ".venv", "node_modules", ".mypy_cache"}
_BLOCKED_EXTENSIONS = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3"}
_MAX_FILE_SIZE_BYTES = 512 * 1024  # 512 KB max read


def _is_path_safe(path: Path) -> str | None:
    """Return an error string if the path is blocked, or None if safe."""
    resolved = path.resolve()

    # Must be inside project root
    try:
        resolved.relative_to(_PROJECT_ROOT)
    except ValueError:
        return f"Access denied: path is outside the project directory."

    # Check each component against blocked names
    for part in resolved.parts:
        if part.lower() in _BLOCKED_NAMES:
            return f"Access denied: '{part}' is a restricted path."

    # Check extension
    if resolved.suffix.lower() in _BLOCKED_EXTENSIONS:
        return f"Access denied: '{resolved.suffix}' files are restricted."

    return None


class FileReaderTool(BaseTool):
    """Read-only file reader restricted to the project directory.

    Can read text files, list directory contents, and get file metadata.
    Cannot read .env, .git/, .venv/, __pycache__/, or binary files.
    """

    name = "file_reader"
    description = (
        "Reads files within the project directory (read-only). "
        "Can read file content, list directories, or get file size/type. "
        "Blocked: .env, .git/, .venv/, __pycache__/, binary files."
    )
    category = "filesystem"
    permission = PermissionLevel.READ_ONLY
    parameters = [
        ToolParameter(
            name="path",
            type="string",
            description="Relative path within the project directory (e.g., 'server.py', 'core/config.py')",
            required=True,
        ),
        ToolParameter(
            name="action",
            type="string",
            description="Action: 'read' (file content), 'list' (directory listing), 'info' (file metadata). Default: 'read'",
            required=False,
            default="read",
        ),
        ToolParameter(
            name="max_lines",
            type="integer",
            description="Maximum lines to return for 'read'. Default: 200",
            required=False,
            default=200,
        ),
    ]

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        rel_path = str(params.get("path", ""))
        action = str(params.get("action", "read")).lower()
        max_lines = int(params.get("max_lines", 200))

        if not rel_path:
            return ToolResult(success=False, error="Parameter 'path' is required.")

        # Resolve the full path
        target = (_PROJECT_ROOT / rel_path).resolve()

        # Security check
        safety_error = _is_path_safe(target)
        if safety_error:
            return ToolResult(success=False, error=safety_error)

        if action == "list":
            return await self._list_dir(target)
        elif action == "info":
            return await self._file_info(target)
        else:
            return await self._read_file(target, max_lines)

    async def _read_file(self, path: Path, max_lines: int) -> ToolResult:
        if not path.exists():
            return ToolResult(success=False, error=f"File not found: {path.name}")
        if not path.is_file():
            return ToolResult(success=False, error=f"'{path.name}' is not a file. Use action='list' for directories.")
        if path.stat().st_size > _MAX_FILE_SIZE_BYTES:
            return ToolResult(
                success=False,
                error=f"File too large ({path.stat().st_size} bytes). Max: {_MAX_FILE_SIZE_BYTES} bytes.",
            )

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            truncated = len(lines) > max_lines
            if truncated:
                lines = lines[:max_lines]

            return ToolResult(
                success=True,
                output={
                    "path": str(path.relative_to(_PROJECT_ROOT)),
                    "content": "\n".join(lines),
                    "total_lines": len(content.splitlines()),
                    "shown_lines": len(lines),
                    "truncated": truncated,
                    "size_bytes": path.stat().st_size,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Error reading file: {str(e)}")

    async def _list_dir(self, path: Path) -> ToolResult:
        if not path.exists():
            return ToolResult(success=False, error=f"Directory not found: {path.name}")
        if not path.is_dir():
            return ToolResult(success=False, error=f"'{path.name}' is not a directory.")

        entries = []
        try:
            for item in sorted(path.iterdir()):
                if item.name.lower() in _BLOCKED_NAMES:
                    continue
                entries.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                })
        except PermissionError:
            return ToolResult(success=False, error="Permission denied.")

        return ToolResult(
            success=True,
            output={
                "path": str(path.relative_to(_PROJECT_ROOT)),
                "count": len(entries),
                "entries": entries,
            },
        )

    async def _file_info(self, path: Path) -> ToolResult:
        if not path.exists():
            return ToolResult(success=False, error=f"Path not found: {path.name}")

        stat = path.stat()
        return ToolResult(
            success=True,
            output={
                "path": str(path.relative_to(_PROJECT_ROOT)),
                "type": "directory" if path.is_dir() else "file",
                "size_bytes": stat.st_size,
                "extension": path.suffix,
                "is_readable": os.access(path, os.R_OK),
            },
        )

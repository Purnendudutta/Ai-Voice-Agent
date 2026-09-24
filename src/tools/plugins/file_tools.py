"""
File System Tools with Verification and Rollback
"""

import os
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
from pydantic import BaseModel, Field

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel
from src.security.sandbox import execution_sandbox
from src.config import settings

BACKUP_DIR = settings.data_dir / "file_backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


class ListDirectoryInput(BaseModel):
    directory_path: str = Field(default=".", description="Path to directory to list")


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "Lists files and subdirectories at a given directory path."
    risk_level = RiskLevel.READ_ONLY
    parameters_schema = ListDirectoryInput

    async def execute(self, params: ListDirectoryInput) -> Dict[str, Any]:
        target = execution_sandbox.sanitize_path(params.directory_path)
        if not target.exists():
            raise FileNotFoundError(f"Directory not found: {target}")
        if not target.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {target}")

        items = []
        for entry in os.scandir(target):
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size_bytes": entry.stat().st_size if entry.is_file() else 0
            })
        return {"directory": str(target), "count": len(items), "items": items[:100]}

    async def verify(self, params: ListDirectoryInput, result: Any) -> Tuple[bool, str]:
        return True, f"Listed {result['count']} items."


class ReadFileInput(BaseModel):
    file_path: str = Field(description="Path to the file to read")
    max_lines: int = Field(default=200, description="Max lines to read")


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Reads content from a text file."
    risk_level = RiskLevel.READ_ONLY
    parameters_schema = ReadFileInput

    async def execute(self, params: ReadFileInput) -> Dict[str, Any]:
        target = execution_sandbox.sanitize_path(params.file_path)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {target}")
        if not target.is_file():
            raise ValueError(f"Path is not a regular file: {target}")

        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(params.max_lines)]
        content = "".join(lines)
        return {"file_path": str(target), "lines_read": len(lines), "content": content}

    async def verify(self, params: ReadFileInput, result: Any) -> Tuple[bool, str]:
        return True, f"Read {result['lines_read']} lines from {result['file_path']}."


class WriteFileInput(BaseModel):
    file_path: str = Field(description="Destination file path")
    content: str = Field(description="Text content to write into file")
    append: bool = Field(default=False, description="Whether to append or overwrite")


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Writes text content to a file with automatic backup rollback support."
    risk_level = RiskLevel.MODERATE
    parameters_schema = WriteFileInput

    async def execute(self, params: WriteFileInput) -> Dict[str, Any]:
        target = execution_sandbox.sanitize_path(params.file_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        backup_file = None
        if target.exists():
            backup_file = BACKUP_DIR / f"{target.name}.{int(asyncio.get_event_loop().time() * 1000)}.bak"
            shutil.copy2(target, backup_file)

        mode = "a" if params.append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(params.content)

        return {
            "file_path": str(target),
            "bytes_written": len(params.content.encode("utf-8")),
            "backup_path": str(backup_file) if backup_file else None
        }

    async def verify(self, params: WriteFileInput, result: Any) -> Tuple[bool, str]:
        target = Path(result["file_path"])
        if not target.exists():
            return False, f"Verification failed: File '{target}' does not exist after write."
        if target.stat().st_size == 0 and len(params.content) > 0:
            return False, f"Verification failed: File '{target}' is unexpectedly empty."
        return True, f"Verified: File '{target}' exists and contains {target.stat().st_size} bytes."

    async def rollback(self, params: WriteFileInput, result: Any) -> bool:
        if result and result.get("backup_path"):
            bak = Path(result["backup_path"])
            orig = Path(result["file_path"])
            if bak.exists():
                shutil.copy2(bak, orig)
                return True
        return False


class DeleteFileInput(BaseModel):
    file_path: str = Field(description="Path to the file to delete (Requires explicit confirmation)")


class DeleteFileTool(BaseTool):
    name = "delete_file"
    description = "Deletes a file after user confirmation, backing it up safely first."
    risk_level = RiskLevel.CRITICAL
    parameters_schema = DeleteFileInput

    async def execute(self, params: DeleteFileInput) -> Dict[str, Any]:
        target = execution_sandbox.sanitize_path(params.file_path)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {target}")

        # Safety backup before critical deletion
        backup_file = BACKUP_DIR / f"deleted_{target.name}.{int(asyncio.get_event_loop().time() * 1000)}.bak"
        shutil.copy2(target, backup_file)

        target.unlink()
        return {"file_path": str(target), "backup_path": str(backup_file)}

    async def verify(self, params: DeleteFileInput, result: Any) -> Tuple[bool, str]:
        target = Path(result["file_path"])
        if target.exists():
            return False, f"Verification failed: File '{target}' still exists."
        return True, f"Verified: File '{target}' successfully deleted."

    async def rollback(self, params: DeleteFileInput, result: Any) -> bool:
        if result and result.get("backup_path"):
            bak = Path(result["backup_path"])
            orig = Path(result["file_path"])
            if bak.exists():
                shutil.copy2(bak, orig)
                return True
        return False

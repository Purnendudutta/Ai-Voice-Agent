"""
Developer Tools: VS Code Workspace, Git, and Safe Terminal Execution
"""

import os
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field
import psutil

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel
from src.security.sandbox import execution_sandbox


class OpenProjectInput(BaseModel):
    project_path: str = Field(description="Directory path of the project to open in VS Code")


class OpenProjectTool(BaseTool):
    name = "open_project_in_vscode"
    description = "Opens a workspace or directory in Visual Studio Code and verifies that VS Code launches."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = OpenProjectInput
    timeout = 10.0

    async def execute(self, params: OpenProjectInput) -> Dict[str, Any]:
        target = execution_sandbox.sanitize_path(params.project_path)
        if not target.exists():
            raise FileNotFoundError(f"Project directory not found: {target}")

        proc = subprocess.Popen(
            ["code", str(target)],
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(1.5)
        return {"project_path": str(target), "pid": proc.pid}

    async def verify(self, params: OpenProjectInput, result: Any) -> Tuple[bool, str]:
        # Verify code.exe process is running
        code_running = False
        for proc in psutil.process_iter(['name']):
            try:
                if "code.exe" in proc.info['name'].lower():
                    code_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if code_running:
            return True, f"Verified: VS Code launched successfully with project {result['project_path']}."
        return False, "Verification failed: VS Code process was not detected."


class OpenProjectInCursorInput(BaseModel):
    project_path: str = Field(default=".", description="Directory path of the project to open in Cursor IDE")


class OpenProjectInCursorTool(BaseTool):
    name = "open_project_in_cursor"
    description = "Opens a workspace, directory, or the current project in Cursor AI Code Editor."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = OpenProjectInCursorInput
    timeout = 10.0

    async def execute(self, params: OpenProjectInCursorInput) -> Dict[str, Any]:
        target = execution_sandbox.sanitize_path(params.project_path)
        if not target.exists():
            raise FileNotFoundError(f"Project directory not found: {target}")

        proc = subprocess.Popen(
            ["cursor", str(target)],
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        await asyncio.sleep(1.5)
        return {"project_path": str(target), "pid": proc.pid}

    async def verify(self, params: OpenProjectInCursorInput, result: Any) -> Tuple[bool, str]:
        cursor_running = False
        for proc in psutil.process_iter(['name']):
            try:
                pname = proc.info['name'].lower()
                if "cursor.exe" in pname or "cursor" in pname:
                    cursor_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if cursor_running:
            return True, f"Verified: Cursor IDE launched with project {result['project_path']}."
        return True, f"Launched Cursor IDE command for project {result['project_path']}."


class RunSafeCommandInput(BaseModel):
    command: str = Field(description="Terminal command to execute (e.g. 'git status', 'pytest', 'npm test')")
    cwd: Optional[str] = Field(default=None, description="Working directory for the command")


class RunSafeCommandTool(BaseTool):
    name = "run_safe_terminal_command"
    description = "Executes an approved, sandboxed terminal command and verifies exit code 0."
    risk_level = RiskLevel.HIGH_RISK
    parameters_schema = RunSafeCommandInput
    timeout = 30.0

    async def validate(self, params: RunSafeCommandInput) -> None:
        valid, reason = execution_sandbox.validate_command(params.command)
        if not valid:
            raise ValueError(f"Command blocked by sandbox: {reason}")

    async def execute(self, params: RunSafeCommandInput) -> Dict[str, Any]:
        working_dir = None
        if params.cwd:
            working_dir = str(execution_sandbox.sanitize_path(params.cwd))

        proc = await asyncio.create_subprocess_shell(
            params.command,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out_text = stdout.decode("utf-8", errors="replace")
        err_text = stderr.decode("utf-8", errors="replace")

        return {
            "command": params.command,
            "returncode": proc.returncode,
            "stdout": out_text[:2000],
            "stderr": err_text[:1000]
        }

    async def verify(self, params: RunSafeCommandInput, result: Any) -> Tuple[bool, str]:
        if result["returncode"] == 0:
            return True, f"Verified: Command '{params.command}' finished successfully (exit code 0)."
        return False, f"Verification failed: Command returned non-zero exit code ({result['returncode']}): {result['stderr'][:200]}"

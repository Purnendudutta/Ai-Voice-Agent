"""
Custom Tool Plugin Example (Extensibility Template)
"""

from typing import Dict, Any, Tuple
from pydantic import BaseModel, Field

from src.tools.base import BaseTool
from src.security.permissions import RiskLevel


class CustomEchoInput(BaseModel):
    message: str = Field(description="Message string to echo back with diagnostic metadata")


class CustomEchoTool(BaseTool):
    name = "custom_echo"
    description = "Example plugin tool that echoes input and attaches system timestamp."
    risk_level = RiskLevel.READ_ONLY
    parameters_schema = CustomEchoInput

    async def execute(self, params: CustomEchoInput) -> Dict[str, Any]:
        return {"echo": f"Echo: {params.message}", "processed": True}

    async def verify(self, params: CustomEchoInput, result: Any) -> Tuple[bool, str]:
        return True, "Echo verification passed."

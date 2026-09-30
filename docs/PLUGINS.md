# SHRUTI - Plugin & Extensibility Guide

SHRUTI is designed with an extensible plugin architecture. New capabilities can be added without modifying the core agent, orchestrator, or communication layer.

---

## 1. Anatomy of a Tool

Every tool in SHRUTI extends `BaseTool` from `src.tools.base`:

```python
from pydantic import BaseModel, Field
from typing import Dict, Any, Tuple
from src.tools.base import BaseTool, RetryPolicy
from src.security.permissions import RiskLevel

class MyToolInput(BaseModel):
    query: str = Field(description="Search parameter or input string")
    count: int = Field(default=5, description="Number of results to retrieve")

class MyCustomTool(BaseTool):
    name = "my_custom_tool"
    description = "Searches custom service and returns formatted records."
    risk_level = RiskLevel.LOW_RISK
    parameters_schema = MyToolInput
    timeout = 10.0
    retry_policy = RetryPolicy(max_retries=2, initial_delay_sec=0.5)

    async def validate(self, params: MyToolInput) -> None:
        """Optional pre-execution check. Raise ValueError on invalid state."""
        if params.count < 1 or params.count > 100:
            raise ValueError("Count must be between 1 and 100.")

    async def execute(self, params: MyToolInput) -> Dict[str, Any]:
        """Primary action execution routine."""
        data = {"results": [f"Item {i} for {params.query}" for i in range(params.count)]}
        return data

    async def verify(self, params: MyToolInput, result: Any) -> Tuple[bool, str]:
        """Post-execution verification probe."""
        if len(result.get("results", [])) == params.count:
            return True, f"Verified: Retrieved {params.count} items."
        return False, "Verification failed: Item count mismatch."

    async def rollback(self, params: MyToolInput, result: Any) -> bool:
        """Optional rollback called if verification fails."""
        # Undo any side effects here
        return True
```

---

## 2. Registering Your Tool

Place your tool file in `src/tools/plugins/my_tool.py`, and register it in `src/tools/plugins/__init__.py`:

```python
from src.tools.registry import tool_registry
from src.tools.plugins.my_tool import MyCustomTool

tool_registry.register(MyCustomTool())
```

Once registered:
1. Gemini Live API automatically receives the function declaration schema.
2. The Web UI catalog displays the tool, risk level, and parameters.
3. The IPC server makes the tool accessible via REST and WebSocket commands.
4. The verification engine and audit logger monitor every execution.

---

## 3. Best Practices for Tool Development

1. **Deterministic Verification**: Never return `True` without checking the actual state (e.g. checking whether a file exists or a process is running).
2. **Safe Rollbacks**: For file-modifying tools, always back up existing files before overwriting.
3. **Appropriate Risk Levels**: Use `HIGH_RISK` or `CRITICAL` for actions that terminate processes or delete files so that explicit user confirmation is prompted.
4. **Idempotence**: Strive to make tools idempotent where possible so that retries succeed safely.

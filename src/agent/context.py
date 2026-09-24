import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.config import settings

logger = logging.getLogger(__name__)


class TaskStep(BaseModel):
    """Represents a single step in a task."""
    description: str
    status: str = "pending"  # pending, in_progress, completed, failed
    details: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskContext(BaseModel):
    """Represents the current task being executed by the agent."""
    name: str
    steps: List[TaskStep]
    status: str = "in_progress"  # in_progress, completed, failed
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None


class ContextManager:
    """Maintains various context stores for the AI Voice Assistant."""

    def __init__(self):
        """Initialize the context manager with empty stores."""
        self.conversation_history: List[Dict[str, Any]] = []
        self.task_context: Optional[TaskContext] = None
        self.desktop_state: Dict[str, Any] = {}
        self.user_preferences: Dict[str, Any] = {}
        self.session_state: Dict[str, Any] = {
            "session_id": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "total_interactions": 0
        }
        self.max_history = 50
        self.prefs_file = Path(settings.data_dir) / "user_preferences.json"
        
        self.load_preferences()

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history and trim if necessary."""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.conversation_history.append(message)
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
            
        self.session_state["total_interactions"] += 1

    def set_current_task(self, task_name: str, steps: List[str]) -> None:
        """Set the active task with a list of step descriptions."""
        task_steps = [TaskStep(description=step) for step in steps]
        self.task_context = TaskContext(name=task_name, steps=task_steps)
        logger.info(f"Started task: {task_name} with {len(steps)} steps.")

    def update_task_step(self, step_index: int, status: str, details: str = "") -> None:
        """Update the status and details of a specific task step."""
        if not self.task_context or step_index < 0 or step_index >= len(self.task_context.steps):
            logger.warning(f"Invalid task step update: index {step_index}")
            return
            
        step = self.task_context.steps[step_index]
        step.status = status
        step.details = details
        
        now = datetime.now(timezone.utc).isoformat()
        if status == "in_progress" and not step.started_at:
            step.started_at = now
        elif status in ("completed", "failed"):
            step.completed_at = now
            
        logger.debug(f"Task '{self.task_context.name}' step {step_index} updated to {status}: {details}")

    def complete_task(self) -> None:
        """Mark the current task as completed."""
        if self.task_context:
            self.task_context.status = "completed"
            self.task_context.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"Task '{self.task_context.name}' marked as completed.")

    def update_desktop_state(self, key: str, value: Any) -> None:
        """Update a specific key in the desktop state."""
        self.desktop_state[key] = value
        logger.debug(f"Desktop state updated: {key} = {value}")

    def get_context_summary(self) -> Dict[str, Any]:
        """Return a full snapshot of the current context."""
        return {
            "conversation_history": self.conversation_history,
            "task_context": self.task_context.model_dump() if self.task_context else None,
            "desktop_state": self.desktop_state,
            "user_preferences": self.user_preferences,
            "session_state": self.session_state
        }

    def clear_conversation(self) -> None:
        """Clear conversation history for privacy."""
        self.conversation_history.clear()
        logger.info("Conversation history cleared.")

    def clear_all(self) -> None:
        """Clear all context data for privacy."""
        self.clear_conversation()
        self.task_context = None
        self.desktop_state.clear()
        logger.info("All context stores cleared.")

    def save_preferences(self) -> None:
        """Persist user preferences to disk."""
        try:
            self.prefs_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.prefs_file, "w", encoding="utf-8") as f:
                json.dump(self.user_preferences, f, indent=2)
            logger.info("User preferences saved.")
        except Exception as e:
            logger.error(f"Failed to save user preferences: {e}")

    def get_agent_name(self) -> str:
        """Get the current customized agent name."""
        return self.user_preferences.get("agent_name", settings.agent_name)

    def set_agent_name(self, name: str) -> None:
        """Update and persist the agent name."""
        clean_name = name.strip() or "Nova"
        self.user_preferences["agent_name"] = clean_name
        self.save_preferences()
        logger.info(f"Agent name updated to: {clean_name}")

    def get_language(self) -> str:
        """Get preferred language (auto, hindi, english)."""
        return self.user_preferences.get("language", settings.language_preference)

    def set_language(self, lang: str) -> None:
        """Update preferred language."""
        clean_lang = lang.lower().strip() or "auto"
        self.user_preferences["language"] = clean_lang
        self.save_preferences()
        logger.info(f"Language preference updated to: {clean_lang}")

    def get_persona_mode(self) -> str:
        """Get current persona mode (e.g. romantic_girlfriend, assistant)."""
        return self.user_preferences.get("persona_mode", getattr(settings, "persona_mode", "romantic_girlfriend"))

    def set_persona_mode(self, mode: str) -> None:
        """Update persona mode."""
        clean_mode = mode.lower().strip() or "romantic_girlfriend"
        self.user_preferences["persona_mode"] = clean_mode
        self.save_preferences()
        logger.info(f"Persona mode updated to: {clean_mode}")

    def load_preferences(self) -> None:
        """Load user preferences from disk."""
        if self.prefs_file.exists():
            try:
                with open(self.prefs_file, "r", encoding="utf-8") as f:
                    self.user_preferences = json.load(f)
                logger.info("User preferences loaded.")
            except Exception as e:
                logger.error(f"Failed to load user preferences: {e}")
                self.user_preferences = {}
        else:
            self.user_preferences = {}

        # Set default values if not present
        if "agent_name" not in self.user_preferences or not self.user_preferences["agent_name"]:
            self.user_preferences["agent_name"] = settings.agent_name
        if "language" not in self.user_preferences or not self.user_preferences["language"]:
            self.user_preferences["language"] = settings.language_preference
        if "voice_name" not in self.user_preferences:
            self.user_preferences["voice_name"] = settings.voice_name
        if "persona_mode" not in self.user_preferences:
            self.user_preferences["persona_mode"] = getattr(settings, "persona_mode", "romantic_girlfriend")

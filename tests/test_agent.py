import pytest
from src.agent.context import ContextManager, TaskStep, TaskContext
from src.agent.orchestrator import AgentState


def test_context_manager_conversation():
    ctx = ContextManager()
    ctx.add_message("user", "Hello assistant")
    ctx.add_message("assistant", "Hello! How can I help?")

    summary = ctx.get_context_summary()
    assert len(summary["conversation_history"]) == 2
    assert summary["conversation_history"][0]["role"] == "user"
    assert summary["conversation_history"][1]["role"] == "assistant"

    ctx.clear_conversation()
    assert len(ctx.get_context_summary()["conversation_history"]) == 0


def test_context_manager_tasks():
    ctx = ContextManager()
    ctx.set_current_task(
        task_name="Prepare development environment",
        steps=["Open VS Code", "Open project", "Run tests"]
    )
    assert ctx.task_context is not None
    assert len(ctx.task_context.steps) == 3

    ctx.update_task_step(0, "completed", "VS Code opened successfully")
    ctx.update_task_step(1, "in_progress", "Opening repository")
    assert ctx.task_context.steps[0].status == "completed"
    assert ctx.task_context.steps[1].status == "in_progress"

    ctx.complete_task()
    assert ctx.task_context.status == "completed"


def test_agent_state_enum():
    states = [s.name for s in AgentState]
    assert "IDLE" in states
    assert "LISTENING" in states
    assert "THINKING" in states
    assert "EXECUTING" in states
    assert "SPEAKING" in states
    assert "ERROR" in states

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


@pytest.mark.asyncio
async def test_live_client_session_resumption_update():
    from unittest.mock import AsyncMock, MagicMock
    from src.gemini.live_client import GeminiLiveClient

    client = GeminiLiveClient()
    client.is_connected = True

    mock_session = AsyncMock()
    mock_update = MagicMock()
    mock_update.resumable = True
    mock_update.new_handle = "test-token-handle-12345"

    mock_msg = MagicMock()
    mock_msg.go_away = None
    mock_msg.session_resumption_update = mock_update
    mock_msg.server_content = None
    mock_msg.tool_call = None

    async def mock_receive():
        yield mock_msg

    mock_session.receive = mock_receive
    client.session = mock_session

    responses = [r async for r in client.receive_responses()]
    assert len(responses) == 1
    assert client.session_handle == "test-token-handle-12345"


@pytest.mark.asyncio
async def test_live_client_handles_1011_internal_error():
    from unittest.mock import AsyncMock
    from src.gemini.live_client import GeminiLiveClient

    client = GeminiLiveClient()
    client.is_connected = True
    client.session_handle = "old-handle-12345"

    mock_session = AsyncMock()

    async def mock_receive_fail():
        if False:
            yield None
        raise Exception("1011 None. Internal error encountered.")

    mock_session.receive = mock_receive_fail
    client.session = mock_session

    with pytest.raises(Exception, match="1011"):
        async for _ in client.receive_responses():
            pass

    assert client.is_connected is False
    assert client.session_handle is None
    assert "1011" in str(client.connection_error)


@pytest.mark.asyncio
async def test_orchestrator_auto_reconnect_success():
    from unittest.mock import AsyncMock, MagicMock
    from src.gemini.live_client import GeminiLiveClient
    from src.agent.orchestrator import AgentOrchestrator

    mock_mic = MagicMock()
    mock_speaker = MagicMock()
    mock_vad = MagicMock()
    mock_wake = MagicMock()
    mock_gemini = AsyncMock(spec=GeminiLiveClient)
    mock_gemini.is_connected = False

    async def fake_connect(**kwargs):
        mock_gemini.is_connected = True

    mock_gemini.connect = AsyncMock(side_effect=fake_connect)

    ctx = ContextManager()
    orch = AgentOrchestrator(
        microphone=mock_mic,
        speaker=mock_speaker,
        vad=mock_vad,
        wake_word=mock_wake,
        gemini=mock_gemini,
        context=ctx
    )
    orch._running = True

    success = await orch._reconnect_gemini()
    assert success is True
    assert mock_gemini.connect.called
    call_kwargs = mock_gemini.connect.call_args.kwargs
    assert call_kwargs.get("resume_session") is True


@pytest.mark.asyncio
async def test_orchestrator_mute_and_unmute():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from src.gemini.live_client import GeminiLiveClient
    from src.agent.orchestrator import AgentOrchestrator, AgentState

    mock_mic = MagicMock()
    mock_mic.is_muted = False
    mock_speaker = MagicMock()
    mock_vad = MagicMock()
    mock_wake = MagicMock()
    mock_gemini = AsyncMock(spec=GeminiLiveClient)

    ctx = ContextManager()
    orch = AgentOrchestrator(
        microphone=mock_mic,
        speaker=mock_speaker,
        vad=mock_vad,
        wake_word=mock_wake,
        gemini=mock_gemini,
        context=ctx
    )
    orch._running = True

    # Test MUTE
    is_muted = orch.toggle_mute(True)
    assert is_muted is True
    assert mock_mic.set_muted.called
    assert mock_mic.clear_queue.called
    assert mock_speaker.clear_queue.called
    assert mock_vad.reset.called
    await asyncio.sleep(0.01)
    assert orch.state == AgentState.MUTED

    # Test UNMUTE
    is_unmuted = orch.toggle_mute(False)
    assert is_unmuted is False
    assert mock_mic.set_muted.called
    assert mock_mic.ensure_started.called
    await asyncio.sleep(0.01)
    # Crucial: Unmute must set state to LISTENING so the user can speak immediately
    assert orch.state == AgentState.LISTENING



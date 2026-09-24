import pytest
from src.tools.registry import tool_registry
from src.tools.base import BaseTool
from src.tools.plugins.custom_plugin import CustomEchoTool, CustomEchoInput
from src.tools.plugins.system_tools import SystemInfoTool, SystemInfoInput
from src.tools.plugins.file_tools import (
    ListDirectoryTool, ListDirectoryInput,
    ReadFileTool, ReadFileInput,
    WriteFileTool, WriteFileInput,
    DeleteFileTool, DeleteFileInput
)
from src.tools.plugins.dev_tools import RunSafeCommandTool, RunSafeCommandInput
from src.security.permissions import RiskLevel


def test_tool_registry_has_tools():
    tools = tool_registry.list_tools()
    assert len(tools) > 0


def test_tool_attributes():
    for tool_meta in tool_registry.list_tools():
        tool = tool_registry.get_tool(tool_meta["name"])
        assert tool is not None
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "risk_level")
        assert hasattr(tool, "parameters_schema")


def test_tool_gemini_declarations():
    declarations = tool_registry.get_gemini_declarations()
    assert len(declarations) > 0
    for decl in declarations:
        assert isinstance(decl, dict)
        assert "name" in decl
        assert "description" in decl
        assert "parameters" in decl


@pytest.mark.asyncio
async def test_custom_echo_tool():
    tool = CustomEchoTool()
    params = CustomEchoInput(message="hello")
    res = await tool.execute(params)
    assert res == {"echo": "Echo: hello", "processed": True}
    confirmed, details = await tool.verify(params, res)
    assert confirmed is True


@pytest.mark.asyncio
async def test_system_info_tool():
    tool = SystemInfoTool()
    params = SystemInfoInput()
    res = await tool.execute(params)
    assert "os" in res
    assert "cpu_percent" in res
    assert "memory_total_gb" in res


@pytest.mark.asyncio
async def test_list_directory_tool(tmp_path):
    d = tmp_path / "test_dir"
    d.mkdir()
    (d / "file.txt").touch()

    tool = ListDirectoryTool()
    params = ListDirectoryInput(directory_path=str(d))
    res = await tool.execute(params)
    assert res["count"] == 1
    assert res["items"][0]["name"] == "file.txt"


@pytest.mark.asyncio
async def test_read_and_write_file_tool(tmp_path):
    f = tmp_path / "out.txt"
    write_tool = WriteFileTool()
    w_params = WriteFileInput(file_path=str(f), content="test content")
    w_res = await write_tool.execute(w_params)
    w_conf, _ = await write_tool.verify(w_params, w_res)
    assert w_conf is True
    assert f.read_text(encoding="utf-8") == "test content"

    read_tool = ReadFileTool()
    r_params = ReadFileInput(file_path=str(f))
    r_res = await read_tool.execute(r_params)
    assert r_res["content"] == "test content"


def test_delete_file_tool_risk():
    tool = DeleteFileTool()
    assert tool.risk_level == RiskLevel.CRITICAL


@pytest.mark.asyncio
async def test_run_safe_command_tool_sandbox():
    tool = RunSafeCommandTool()
    params = RunSafeCommandInput(command="format C:")
    with pytest.raises(ValueError, match="Command blocked by sandbox"):
        await tool.validate(params)


@pytest.mark.asyncio
async def test_cursor_tools():
    from src.tools.plugins.input_tools import GetCursorPositionTool, GetCursorPositionInput, MouseMoveTool, MouseMoveInput
    pos_tool = GetCursorPositionTool()
    pos_res = await pos_tool.execute(GetCursorPositionInput())
    assert "cursor_x" in pos_res
    assert "cursor_y" in pos_res
    assert "screen_width" in pos_res
    assert "screen_height" in pos_res

    # Test moving mouse to safe position
    move_tool = MouseMoveTool()
    move_params = MouseMoveInput(x=100, y=100, duration=0.0)
    move_res = await move_tool.execute(move_params)
    assert move_res["target_x"] == 100
    assert move_res["target_y"] == 100


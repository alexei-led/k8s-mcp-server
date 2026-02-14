"""Tests for all K8s CLI tool functions in the server module."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from k8s_mcp_server.errors import CommandExecutionError, CommandValidationError
from k8s_mcp_server.server import (
    describe_argocd,
    describe_helm,
    describe_istioctl,
    describe_kubectl,
    execute_argocd,
    execute_helm,
    execute_istioctl,
    execute_kubectl,
)


@pytest.mark.parametrize(
    "describe_func, tool_name, command",
    [
        (describe_kubectl, "kubectl", "get"),
        (describe_helm, "helm", "list"),
        (describe_istioctl, "istioctl", "analyze"),
        (describe_argocd, "argocd", "app"),
    ],
)
@pytest.mark.asyncio
async def test_describe_tool(describe_func, tool_name, command, mock_get_command_help, mock_k8s_cli_status):
    result = await describe_func(command=command)
    assert hasattr(result, "help_text")
    assert result.help_text == "Mocked help text"
    mock_get_command_help.assert_called_once_with(tool_name, command)


@pytest.mark.parametrize(
    "describe_func, tool_name",
    [
        (describe_kubectl, "kubectl"),
        (describe_helm, "helm"),
        (describe_istioctl, "istioctl"),
        (describe_argocd, "argocd"),
    ],
)
@pytest.mark.asyncio
async def test_describe_tool_with_context(describe_func, tool_name, mock_get_command_help, mock_k8s_cli_status):
    mock_context = AsyncMock()
    result = await describe_func(command="test", ctx=mock_context)
    assert hasattr(result, "help_text")
    assert result.help_text == "Mocked help text"
    mock_context.info.assert_called_once()


@pytest.mark.parametrize(
    "describe_func",
    [
        describe_kubectl,
        describe_helm,
        describe_istioctl,
        describe_argocd,
    ],
)
@pytest.mark.asyncio
async def test_describe_tool_with_error(describe_func, mock_k8s_cli_status):
    """Errors from get_command_help raise CommandExecutionError (isError=true in MCP)."""
    error_mock = AsyncMock(side_effect=Exception("Test error"))

    with patch("k8s_mcp_server.server.get_command_help", error_mock):
        with pytest.raises(CommandExecutionError, match="Test error"):
            await describe_func(command="test")


@pytest.mark.parametrize(
    "execute_func, tool_name, command",
    [
        (execute_kubectl, "kubectl", "get pods"),
        (execute_helm, "helm", "list"),
        (execute_istioctl, "istioctl", "analyze"),
        (execute_argocd, "argocd", "app list"),
    ],
)
@pytest.mark.asyncio
async def test_execute_tool(execute_func, tool_name, command, mock_execute_command, mock_k8s_cli_status):
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_func(command=command)
        assert result == mock_execute_command.return_value
        mock_execute_command.assert_called_once()


@pytest.mark.parametrize(
    "execute_func",
    [
        execute_kubectl,
        execute_helm,
        execute_istioctl,
        execute_argocd,
    ],
)
@pytest.mark.asyncio
async def test_execute_tool_with_context(execute_func, mock_execute_command, mock_k8s_cli_status):
    mock_context = AsyncMock()
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_func(command="test", ctx=mock_context)
        assert result == mock_execute_command.return_value
        mock_execute_command.assert_called_once()
        mock_context.info.assert_called()


@pytest.mark.parametrize(
    "execute_func",
    [
        execute_kubectl,
        execute_helm,
        execute_istioctl,
        execute_argocd,
    ],
)
@pytest.mark.asyncio
async def test_execute_tool_with_validation_error(execute_func, mock_k8s_cli_status):
    """Validation errors raise CommandValidationError (isError=true in MCP)."""
    error_mock = AsyncMock(side_effect=CommandValidationError("Invalid command"))
    with patch("k8s_mcp_server.server.execute_command", error_mock):
        with pytest.raises(CommandValidationError, match="Invalid command"):
            await execute_func(command="test")


@pytest.mark.parametrize(
    "execute_func",
    [
        execute_kubectl,
        execute_helm,
        execute_istioctl,
        execute_argocd,
    ],
)
@pytest.mark.asyncio
async def test_execute_tool_with_execution_error(execute_func, mock_k8s_cli_status):
    """Execution errors raise CommandExecutionError (isError=true in MCP)."""
    error_mock = AsyncMock(side_effect=CommandExecutionError("Execution failed"))
    with patch("k8s_mcp_server.server.execute_command", error_mock):
        with pytest.raises(CommandExecutionError, match="Execution failed"):
            await execute_func(command="test")


@pytest.mark.asyncio
async def test_tool_command_preprocessing(mock_execute_command, mock_k8s_cli_status):
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        await execute_kubectl("get pods")
        called_command = mock_execute_command.call_args[0][0]
        assert called_command.startswith("kubectl")

        mock_execute_command.reset_mock()
        await execute_kubectl("kubectl get pods")
        called_command = mock_execute_command.call_args[0][0]
        assert called_command == "kubectl get pods"


@pytest.mark.asyncio
async def test_concurrent_command_execution(mock_k8s_cli_status):
    with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"status": "success", "output": "test"}

        async def run_command():
            return await execute_kubectl("get pods")

        results = await asyncio.gather(*[run_command() for _ in range(10)])
        assert all(r["status"] == "success" for r in results)
        assert mock_exec.call_count == 10


@pytest.mark.asyncio
async def test_long_running_command(mock_k8s_cli_status):
    with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"status": "error", "output": "Command timed out after 0.1 seconds"}
        result = await execute_kubectl("get pods", timeout=0.1)
        assert "timed out" in result["output"].lower()
        mock_exec.assert_called_once_with("kubectl get pods", timeout=0.1)

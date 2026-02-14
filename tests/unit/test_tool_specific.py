"""Tests for tool-specific functions in the server module."""

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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_kubectl(mock_get_command_help, mock_k8s_cli_status):
    result = await describe_kubectl(command="get")
    assert result.help_text == "Mocked help text"
    mock_get_command_help.assert_called_once_with("kubectl", "get")

    mock_get_command_help.reset_mock()
    result = await describe_kubectl()
    assert result.help_text == "Mocked help text"
    mock_get_command_help.assert_called_once()


@pytest.mark.asyncio
async def test_describe_kubectl_with_context(mock_get_command_help, mock_k8s_cli_status):
    mock_context = AsyncMock()
    result = await describe_kubectl(command="get", ctx=mock_context)
    assert result.help_text == "Mocked help text"
    mock_get_command_help.assert_called_once_with("kubectl", "get")
    mock_context.info.assert_called_once()


@pytest.mark.asyncio
async def test_describe_kubectl_with_error(mock_k8s_cli_status):
    """Errors from get_command_help raise CommandExecutionError (isError=true in MCP)."""
    error_mock = AsyncMock(side_effect=Exception("Test error"))

    with patch("k8s_mcp_server.server.get_command_help", error_mock):
        with pytest.raises(CommandExecutionError, match="Test error"):
            await describe_kubectl(command="get")


@pytest.mark.asyncio
async def test_describe_helm(mock_get_command_help, mock_k8s_cli_status):
    result = await describe_helm(command="list")
    assert result.help_text == "Mocked help text"
    mock_get_command_help.assert_called_once_with("helm", "list")


@pytest.mark.asyncio
async def test_describe_istioctl(mock_get_command_help, mock_k8s_cli_status):
    result = await describe_istioctl(command="analyze")
    assert result.help_text == "Mocked help text"
    mock_get_command_help.assert_called_once_with("istioctl", "analyze")


@pytest.mark.asyncio
async def test_describe_argocd(mock_get_command_help, mock_k8s_cli_status):
    result = await describe_argocd(command="app")
    assert result.help_text == "Mocked help text"
    mock_get_command_help.assert_called_once_with("argocd", "app")


@pytest.mark.asyncio
async def test_execute_kubectl(mock_execute_command, mock_k8s_cli_status):
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_kubectl(command="get pods")
        assert result == mock_execute_command.return_value
        mock_execute_command.assert_called_once()

    mock_execute_command.reset_mock()
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_kubectl(command="describe pod my-pod")
        assert result == mock_execute_command.return_value
        mock_execute_command.assert_called_once()


@pytest.mark.asyncio
async def test_execute_kubectl_with_context(mock_execute_command, mock_k8s_cli_status):
    mock_context = AsyncMock()
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_kubectl(command="get pods", ctx=mock_context)
        assert result == mock_execute_command.return_value
        mock_execute_command.assert_called_once()
        mock_context.info.assert_called()


@pytest.mark.asyncio
async def test_execute_kubectl_with_validation_error(mock_k8s_cli_status):
    """Validation errors raise CommandValidationError (isError=true in MCP)."""
    error_mock = AsyncMock(side_effect=CommandValidationError("Invalid command"))
    with patch("k8s_mcp_server.server.execute_command", error_mock):
        with pytest.raises(CommandValidationError, match="Invalid command"):
            await execute_kubectl(command="get pods")


@pytest.mark.asyncio
async def test_execute_helm(mock_execute_command, mock_k8s_cli_status):
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_helm(command="list")
        assert result == mock_execute_command.return_value
        mock_execute_command.assert_called_once()


@pytest.mark.asyncio
async def test_execute_istioctl(mock_execute_command, mock_k8s_cli_status):
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_istioctl(command="analyze")
        assert result == mock_execute_command.return_value
        mock_execute_command.assert_called_once()


@pytest.mark.asyncio
async def test_execute_argocd(mock_execute_command, mock_k8s_cli_status):
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_argocd(command="app list")
        assert result == mock_execute_command.return_value
        mock_execute_command.assert_called_once()

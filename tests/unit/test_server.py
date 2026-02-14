"""Tests for the server module."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from k8s_mcp_server.errors import (
    AuthenticationError,
    CommandExecutionError,
    CommandTimeoutError,
    CommandValidationError,
)
from k8s_mcp_server.server import (
    _describe_tool_command,
    _execute_tool_command,
    describe_argocd,
    describe_helm,
    describe_istioctl,
    describe_kubectl,
    execute_argocd,
    execute_helm,
    execute_istioctl,
    execute_kubectl,
    run_startup_checks,
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
    assert hasattr(result, "help_text")
    mock_get_command_help.assert_called_once_with("kubectl", "get")
    mock_context.info.assert_called_once()


@pytest.mark.asyncio
async def test_describe_kubectl_with_error_raises(mock_k8s_cli_status):
    """Errors from get_command_help raise CommandExecutionError (isError=true in MCP)."""
    error_mock = AsyncMock(side_effect=Exception("Test error"))

    with patch("k8s_mcp_server.server.get_command_help", error_mock):
        with pytest.raises(CommandExecutionError, match="Error retrieving kubectl help"):
            await describe_kubectl(command="get")


@pytest.mark.asyncio
async def test_describe_kubectl_tool_not_installed_raises():
    """Tool not installed raises CommandExecutionError (isError=true in MCP)."""
    mock_status = {"kubectl": False}
    with patch("k8s_mcp_server.server.cli_status", mock_status):
        mock_context = AsyncMock()
        with pytest.raises(CommandExecutionError, match="not installed"):
            await describe_kubectl(command="get", ctx=mock_context)
        mock_context.error.assert_called_once()


@pytest.mark.asyncio
async def test_execute_kubectl(mock_execute_command, mock_k8s_cli_status):
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_kubectl(command="get pods")
        assert result == mock_execute_command.return_value
        mock_execute_command.assert_called_once()

    mock_execute_command.reset_mock()
    with patch("k8s_mcp_server.server.execute_command", mock_execute_command):
        result = await execute_kubectl(command="get pods", timeout=30)
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
async def test_execute_kubectl_validation_error_raises(mock_k8s_cli_status):
    """Validation errors raise CommandValidationError (isError=true in MCP)."""
    error_mock = AsyncMock(side_effect=CommandValidationError("Invalid command"))
    with patch("k8s_mcp_server.server.execute_command", error_mock):
        with pytest.raises(CommandValidationError, match="Invalid command"):
            await execute_kubectl(command="get pods")


@pytest.mark.asyncio
async def test_execute_kubectl_execution_error_raises(mock_k8s_cli_status):
    """Execution errors raise CommandExecutionError (isError=true in MCP)."""
    error_mock = AsyncMock(side_effect=CommandExecutionError("Execution failed"))
    with patch("k8s_mcp_server.server.execute_command", error_mock):
        with pytest.raises(CommandExecutionError, match="Execution failed"):
            await execute_kubectl(command="get pods")


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


def test_server_initialization():
    from k8s_mcp_server.server import mcp

    assert mcp.name == "K8s MCP Server"
    from k8s_mcp_server.server import describe_kubectl, execute_kubectl

    assert callable(describe_kubectl)
    assert callable(execute_kubectl)


@pytest.mark.asyncio
async def test_concurrent_command_execution(mock_k8s_cli_status):
    from k8s_mcp_server.server import execute_kubectl

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


@pytest.mark.asyncio
async def test_execute_kubectl_unexpected_error_raises(mock_k8s_cli_status):
    """Unexpected errors are wrapped in CommandExecutionError (isError=true in MCP)."""
    error_mock = AsyncMock(side_effect=Exception("Unexpected error"))
    with patch("k8s_mcp_server.server.execute_command", error_mock):
        with pytest.raises(CommandExecutionError, match="Unexpected error"):
            await execute_kubectl(command="get pods")


@pytest.mark.asyncio
async def test_execute_tool_command_tool_not_installed_raises():
    """Tool not installed raises CommandExecutionError (isError=true in MCP)."""
    mock_status = {"kubectl": True, "helm": False}
    with patch("k8s_mcp_server.server.cli_status", mock_status):
        mock_context = AsyncMock()
        with pytest.raises(CommandExecutionError, match="not installed"):
            await _execute_tool_command(tool="helm", command="list", timeout=30, ctx=mock_context)
        mock_context.error.assert_called_once()


@pytest.mark.asyncio
async def test_execute_tool_command_with_field_info_timeout():
    from pydantic import Field

    timeout_field = Field(default=None)

    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"status": "success", "output": "Command succeeded"}
            await _execute_tool_command(tool="kubectl", command="get pods", timeout=timeout_field, ctx=None)

            from k8s_mcp_server.config import DEFAULT_TIMEOUT

            mock_execute.assert_called_once_with("kubectl get pods", timeout=DEFAULT_TIMEOUT)


@pytest.mark.parametrize(
    "kubectl_installed,other_tools_installed",
    [
        (True, True),
        (True, False),
    ],
)
def test_run_startup_checks(kubectl_installed, other_tools_installed):
    from k8s_mcp_server.config import SUPPORTED_CLI_TOOLS

    def mock_check_cli_installed_factory(kubectl_status, other_status):
        async def mock_check_cli_installed(cli_tool):
            if cli_tool == "kubectl":
                return kubectl_status
            return other_status

        return mock_check_cli_installed

    mock_check = mock_check_cli_installed_factory(kubectl_installed, other_tools_installed)

    with patch("k8s_mcp_server.server.check_cli_installed", new=AsyncMock(side_effect=mock_check)):
        with patch("k8s_mcp_server.server.logger") as mock_logger:
            result = run_startup_checks()

            assert "kubectl" in result
            assert result["kubectl"] == kubectl_installed

            for tool in SUPPORTED_CLI_TOOLS:
                assert tool in result
                if tool == "kubectl":
                    assert result[tool] == kubectl_installed
                else:
                    assert result[tool] == other_tools_installed

            if kubectl_installed:
                mock_logger.info.assert_any_call("kubectl is installed and available")
            else:
                mock_logger.warning.assert_any_call("kubectl is not installed or not in PATH")


def test_run_startup_checks_kubectl_missing():
    async def mock_check_cli_installed(cli_tool):
        return False

    with patch("k8s_mcp_server.server.check_cli_installed", new=AsyncMock(side_effect=mock_check_cli_installed)):
        with patch("k8s_mcp_server.server.sys.exit") as mock_exit:
            run_startup_checks()
            mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_execute_kubectl_auth_error_raises():
    """Auth errors raise AuthenticationError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = AuthenticationError("Authentication error", {"command": "kubectl get pods"})
            with pytest.raises(AuthenticationError, match="Authentication error"):
                await execute_kubectl(command="get pods")
            mock_execute.assert_called_once_with("kubectl get pods", timeout=300)


@pytest.mark.asyncio
async def test_describe_helm():
    with patch("k8s_mcp_server.server.cli_status", {"helm": True}):
        from k8s_mcp_server.tools import CommandHelpResult

        with patch("k8s_mcp_server.server.get_command_help", new_callable=AsyncMock) as mock_help:
            mock_help.return_value = CommandHelpResult(help_text="Helm help text", status="success")
            result = await describe_helm(command="list")
            assert result.help_text == "Helm help text"
            mock_help.assert_called_once_with("helm", "list")


@pytest.mark.asyncio
async def test_describe_helm_with_context():
    with patch("k8s_mcp_server.server.cli_status", {"helm": True}):
        mock_context = AsyncMock()

        with patch("k8s_mcp_server.server.get_command_help", new_callable=AsyncMock) as mock_help:
            from k8s_mcp_server.tools import CommandHelpResult

            mock_help.return_value = CommandHelpResult(help_text="Helm help text", status="success")
            result = await describe_helm(command="list", ctx=mock_context)
            assert result.help_text == "Helm help text"
            mock_help.assert_called_once_with("helm", "list")
            mock_context.info.assert_called_once()


@pytest.mark.asyncio
async def test_describe_helm_not_installed_raises():
    """Tool not installed raises CommandExecutionError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"helm": False}):
        with pytest.raises(CommandExecutionError, match="not installed"):
            await describe_helm(command="list")


@pytest.mark.asyncio
async def test_execute_helm():
    with patch("k8s_mcp_server.server.cli_status", {"helm": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"status": "success", "output": "Chart list", "execution_time": 0.5}

            result = await execute_helm(command="list")
            assert result["status"] == "success"
            assert result["output"] == "Chart list"
            mock_execute.assert_called_once_with("helm list", timeout=300)

            mock_execute.reset_mock()
            mock_execute.return_value = {"status": "success", "output": "Chart list", "execution_time": 0.5}
            result = await execute_helm(command="list --all-namespaces")
            assert result["status"] == "success"
            mock_execute.assert_called_once_with("helm list --all-namespaces", timeout=300)


@pytest.mark.asyncio
async def test_execute_helm_not_installed_raises():
    """Tool not installed raises CommandExecutionError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"helm": False}):
        with pytest.raises(CommandExecutionError, match="not installed"):
            await execute_helm(command="list")


@pytest.mark.asyncio
async def test_execute_helm_error_raises():
    """Execution errors raise CommandExecutionError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"helm": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = CommandExecutionError("Execution error", {"command": "helm list"})
            with pytest.raises(CommandExecutionError, match="Execution error"):
                await execute_helm(command="list")
            mock_execute.assert_called_once_with("helm list", timeout=300)


@pytest.mark.asyncio
async def test_execute_helm_validation_error_raises():
    """Validation errors raise CommandValidationError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"helm": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = CommandValidationError("Validation error", {"command": "helm list"})
            with pytest.raises(CommandValidationError, match="Validation error"):
                await execute_helm(command="list")
            mock_execute.assert_called_once_with("helm list", timeout=300)


@pytest.mark.asyncio
async def test_execute_helm_timeout_raises():
    """Timeout errors raise CommandTimeoutError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"helm": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = CommandTimeoutError("Command timed out", {"command": "helm list", "timeout": 30})
            with pytest.raises(CommandTimeoutError, match="timed out"):
                await execute_helm(command="list", timeout=30)
            mock_execute.assert_called_once_with("helm list", timeout=30)


@pytest.mark.asyncio
async def test_execute_helm_auth_error_raises():
    """Auth errors raise AuthenticationError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"helm": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = AuthenticationError("Authentication error", {"command": "helm list"})
            with pytest.raises(AuthenticationError, match="Authentication error"):
                await execute_helm(command="list")
            mock_execute.assert_called_once_with("helm list", timeout=300)


@pytest.mark.asyncio
async def test_describe_istioctl():
    with patch("k8s_mcp_server.server.cli_status", {"istioctl": True}):
        from k8s_mcp_server.tools import CommandHelpResult

        with patch("k8s_mcp_server.server.get_command_help", new_callable=AsyncMock) as mock_help:
            mock_help.return_value = CommandHelpResult(help_text="Istio help text", status="success")
            result = await describe_istioctl(command="analyze")
            assert result.help_text == "Istio help text"
            mock_help.assert_called_once_with("istioctl", "analyze")


@pytest.mark.asyncio
async def test_describe_istioctl_not_installed_raises():
    """Tool not installed raises CommandExecutionError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"istioctl": False}):
        with pytest.raises(CommandExecutionError, match="not installed"):
            await describe_istioctl(command="analyze")


@pytest.mark.asyncio
async def test_execute_istioctl():
    with patch("k8s_mcp_server.server.cli_status", {"istioctl": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"status": "success", "output": "Istio analyze", "execution_time": 0.5}
            result = await execute_istioctl(command="analyze")
            assert result["status"] == "success"
            assert result["output"] == "Istio analyze"
            mock_execute.assert_called_once_with("istioctl analyze", timeout=300)


@pytest.mark.asyncio
async def test_execute_istioctl_not_installed_raises():
    """Tool not installed raises CommandExecutionError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"istioctl": False}):
        with pytest.raises(CommandExecutionError, match="not installed"):
            await execute_istioctl(command="analyze")


@pytest.mark.asyncio
async def test_describe_argocd():
    with patch("k8s_mcp_server.server.cli_status", {"argocd": True}):
        from k8s_mcp_server.tools import CommandHelpResult

        with patch("k8s_mcp_server.server.get_command_help", new_callable=AsyncMock) as mock_help:
            mock_help.return_value = CommandHelpResult(help_text="ArgoCD help text", status="success")
            result = await describe_argocd(command="app list")
            assert result.help_text == "ArgoCD help text"
            mock_help.assert_called_once_with("argocd", "app list")


@pytest.mark.asyncio
async def test_describe_argocd_not_installed_raises():
    """Tool not installed raises CommandExecutionError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"argocd": False}):
        with pytest.raises(CommandExecutionError, match="not installed"):
            await describe_argocd(command="app list")


@pytest.mark.asyncio
async def test_execute_argocd():
    with patch("k8s_mcp_server.server.cli_status", {"argocd": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"status": "success", "output": "ArgoCD app list", "execution_time": 0.5}
            result = await execute_argocd(command="app list")
            assert result["status"] == "success"
            assert result["output"] == "ArgoCD app list"
            mock_execute.assert_called_once_with("argocd app list", timeout=300)


@pytest.mark.asyncio
async def test_execute_argocd_not_installed_raises():
    """Tool not installed raises CommandExecutionError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"argocd": False}):
        with pytest.raises(CommandExecutionError, match="not installed"):
            await execute_argocd(command="app list")


@pytest.mark.asyncio
async def test_execute_tool_command_with_none_timeout():
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"status": "success", "output": "Command output"}
            result = await _execute_tool_command("kubectl", "get pods", None, None)
            assert result["status"] == "success"
            assert result["output"] == "Command output"
            mock_execute.assert_called_once()


@pytest.mark.asyncio
async def test_execute_tool_command_info_logs():
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"status": "success", "output": "Command output"}
            mock_ctx = AsyncMock()

            await _execute_tool_command("kubectl", "get pods | grep nginx", 30, mock_ctx)
            assert mock_ctx.info.call_count >= 2
            assert any("piped" in str(call) for call in mock_ctx.info.call_args_list)

            mock_ctx.reset_mock()
            await _execute_tool_command("kubectl", "get pods", 30, mock_ctx)
            assert any("executed successfully" in str(call) for call in mock_ctx.info.call_args_list)


@pytest.mark.asyncio
async def test_execute_tool_command_warning_logs():
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch("k8s_mcp_server.server.execute_command", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"status": "error", "output": "Command failed"}
            mock_ctx = AsyncMock()

            await _execute_tool_command("kubectl", "get pods", 30, mock_ctx)
            mock_ctx.warning.assert_called_once()
            assert "failed" in str(mock_ctx.warning.call_args[0][0])


@pytest.mark.asyncio
async def test_execute_tool_command_unexpected_error_raises():
    """Unexpected errors are wrapped in CommandExecutionError and re-raised (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch("k8s_mcp_server.server.execute_command", side_effect=Exception("Unexpected error")):
            mock_ctx = AsyncMock()
            with pytest.raises(CommandExecutionError, match="Unexpected error"):
                await _execute_tool_command("kubectl", "get pods", 30, mock_ctx)
            mock_ctx.error.assert_called_once()
            assert "Unexpected error" in str(mock_ctx.error.call_args[0][0])


@pytest.mark.asyncio
async def test_execute_tool_command_validation_error_raises():
    """Validation errors are re-raised (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch(
            "k8s_mcp_server.server.execute_command",
            side_effect=CommandValidationError("Validation error", {"command": "kubectl invalid"}),
        ):
            mock_ctx = AsyncMock()
            with pytest.raises(CommandValidationError, match="Validation error"):
                await _execute_tool_command("kubectl", "invalid", 30, mock_ctx)
            mock_ctx.error.assert_called_once()
            assert "VALIDATION_ERROR" in str(mock_ctx.error.call_args[0][0])


@pytest.mark.asyncio
async def test_execute_tool_command_authentication_error_raises():
    """Auth errors are re-raised (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch(
            "k8s_mcp_server.server.execute_command",
            side_effect=AuthenticationError("Auth error", {"command": "kubectl get pods"}),
        ):
            mock_ctx = AsyncMock()
            with pytest.raises(AuthenticationError, match="Auth error"):
                await _execute_tool_command("kubectl", "get pods", 30, mock_ctx)
            mock_ctx.error.assert_called_once()
            assert "AUTH_ERROR" in str(mock_ctx.error.call_args[0][0])


@pytest.mark.asyncio
async def test_execute_tool_command_timeout_error_raises():
    """Timeout errors are re-raised (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch(
            "k8s_mcp_server.server.execute_command",
            side_effect=CommandTimeoutError("Timeout error", {"command": "kubectl get pods", "timeout": 30}),
        ):
            mock_ctx = AsyncMock()
            with pytest.raises(CommandTimeoutError, match="Timeout error"):
                await _execute_tool_command("kubectl", "get pods", 30, mock_ctx)
            mock_ctx.error.assert_called_once()
            assert "TIMEOUT_ERROR" in str(mock_ctx.error.call_args[0][0])


@pytest.mark.asyncio
async def test_describe_tool_unexpected_error_raises():
    """Unexpected errors in describe raise CommandExecutionError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch("k8s_mcp_server.server.get_command_help", side_effect=Exception("Unexpected help error")):
            mock_ctx = AsyncMock()
            with pytest.raises(CommandExecutionError, match="Error retrieving kubectl help"):
                await describe_kubectl(command="get", ctx=mock_ctx)
            mock_ctx.error.assert_called_once()
            assert "Unexpected error" in str(mock_ctx.error.call_args[0][0])


@pytest.mark.asyncio
async def test_execute_tool_command_pydantic_validation_error_raises():
    """Pydantic ValidationError is re-raised (isError=true in MCP)."""
    from pydantic import ValidationError

    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        with patch(
            "k8s_mcp_server.server.execute_command",
            side_effect=ValidationError.from_exception_data(
                title="test", line_errors=[{"type": "string_type", "loc": ("command",), "msg": "Input should be a valid string", "input": 123}]
            ),
        ):
            mock_ctx = AsyncMock()
            with pytest.raises(ValidationError):
                await _execute_tool_command("kubectl", "get pods", 30, mock_ctx)
            mock_ctx.error.assert_called_once()
            assert "Input validation error" in str(mock_ctx.error.call_args[0][0])


@pytest.mark.asyncio
async def test_describe_tool_command_shared_logic():
    """The shared _describe_tool_command works for any tool."""
    with patch("k8s_mcp_server.server.cli_status", {"helm": True}):
        from k8s_mcp_server.tools import CommandHelpResult

        with patch("k8s_mcp_server.server.get_command_help", new_callable=AsyncMock) as mock_help:
            mock_help.return_value = CommandHelpResult(help_text="Help text", status="success")
            result = await _describe_tool_command("helm", "list", None)
            assert result.help_text == "Help text"
            mock_help.assert_called_once_with("helm", "list")


@pytest.mark.asyncio
async def test_describe_tool_command_error_result_raises():
    """Error results from get_command_help raise CommandExecutionError (isError=true in MCP)."""
    with patch("k8s_mcp_server.server.cli_status", {"kubectl": True}):
        from k8s_mcp_server.tools import CommandHelpResult

        error_result = CommandHelpResult(
            help_text="Command validation error: invalid command",
            status="error",
            error={"message": "invalid command", "code": "VALIDATION_ERROR"},
        )
        with patch("k8s_mcp_server.server.get_command_help", new_callable=AsyncMock) as mock_help:
            mock_help.return_value = error_result
            with pytest.raises(CommandExecutionError, match="Command validation error"):
                await _describe_tool_command("kubectl", "badcmd", None)

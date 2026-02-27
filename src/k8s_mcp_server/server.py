"""Main server implementation for K8s MCP Server.

This module defines the MCP server instance and tool functions for Kubernetes CLI interaction,
providing a standardized interface for kubectl, istioctl, helm, and argocd command execution
and documentation.
"""

import asyncio
import logging
import sys

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import Icon, ToolAnnotations
from pydantic import Field, ValidationError
from pydantic.fields import FieldInfo

from k8s_mcp_server import __version__
from k8s_mcp_server.cli_executor import (
    check_cli_installed,
    execute_command,
    get_command_help,
)
from k8s_mcp_server.config import DEFAULT_TIMEOUT, INSTRUCTIONS, SUPPORTED_CLI_TOOLS
from k8s_mcp_server.errors import (
    CommandExecutionError,
    K8sMCPError,
)
from k8s_mcp_server.prompts import register_prompts
from k8s_mcp_server.tools import CommandHelpResult, CommandResult

logger = logging.getLogger(__name__)

# Tool icon URLs (CNCF artwork, SVG format)
_CNCF = "https://raw.githubusercontent.com/cncf/artwork/main/projects"
_ICONS: dict[str, list[Icon]] = {
    "kubectl": [Icon(src=f"{_CNCF}/kubernetes/icon/color/kubernetes-icon-color.svg", mimeType="image/svg+xml")],
    "helm": [Icon(src=f"{_CNCF}/helm/icon/color/helm-icon-color.svg", mimeType="image/svg+xml")],
    "istioctl": [Icon(src=f"{_CNCF}/istio/icon/color/istio-icon-color.svg", mimeType="image/svg+xml")],
    "argocd": [Icon(src=f"{_CNCF}/argo/icon/color/argo-icon-color.svg", mimeType="image/svg+xml")],
}


# Function to run startup checks in synchronous context
def run_startup_checks() -> dict[str, bool]:
    """Run startup checks to ensure Kubernetes CLI tools are installed.

    Returns:
        Dictionary of CLI tools and their installation status
    """
    logger.info("Running startup checks...")

    # Check if each supported CLI tool is installed
    cli_status = {}
    for cli_tool in SUPPORTED_CLI_TOOLS:
        if asyncio.run(check_cli_installed(cli_tool)):
            logger.info(f"{cli_tool} is installed and available")
            cli_status[cli_tool] = True
        else:
            logger.warning(f"{cli_tool} is not installed or not in PATH")
            cli_status[cli_tool] = False

    # Verify at least kubectl is available
    if not cli_status.get("kubectl", False):
        logger.error("kubectl is required but not found. Please install kubectl.")
        sys.exit(1)

    return cli_status


# Call the startup checks
cli_status = run_startup_checks()

# Create the FastMCP server following FastMCP best practices
mcp = FastMCP(
    name="K8s MCP Server",
    instructions=INSTRUCTIONS,
)
mcp._mcp_server.version = __version__

# Register prompt templates
register_prompts(mcp)


async def _execute_tool_command(tool: str, command: str, timeout: int | None, ctx: Context | None) -> CommandResult:
    """Internal implementation for executing tool commands.

    Raises exceptions for errors so FastMCP returns them with isError=true per MCP spec.

    Args:
        tool: The CLI tool name (kubectl, istioctl, helm, argocd)
        command: The command to execute
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status

    Raises:
        CommandValidationError: If the command fails validation
        CommandExecutionError: If the command fails to execute
        AuthenticationError: If authentication fails
        CommandTimeoutError: If the command times out
        ValidationError: If input parameters are invalid
    """
    logger.info(f"Executing {tool} command: {command}" + (f" with timeout: {timeout}" if timeout else ""))

    # Check if tool is installed
    if not cli_status.get(tool, False):
        message = f"{tool} is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        raise CommandExecutionError(message)

    # Handle Pydantic Field default for timeout
    actual_timeout = timeout
    if isinstance(timeout, FieldInfo) or timeout is None:
        actual_timeout = DEFAULT_TIMEOUT

    # Add tool prefix if not present
    if not command.strip().startswith(tool):
        command = f"{tool} {command}"

    if ctx:
        is_pipe = "|" in command
        message = "Executing" + (" piped" if is_pipe else "") + f" {tool} command"
        await ctx.info(message + (f" with timeout: {actual_timeout}s" if actual_timeout else ""))

    try:
        result = await execute_command(command, timeout=actual_timeout)

        if result["status"] == "success":
            if ctx:
                await ctx.info(f"{tool} command executed successfully")
        else:
            if ctx:
                await ctx.warning(f"{tool} command failed")

        return result
    except K8sMCPError as e:
        logger.warning(f"{tool} command error ({e.code}): {e}")
        if ctx:
            await ctx.error(f"{e.code}: {str(e)}")
        raise
    except ValidationError as e:
        logger.warning(f"{tool} input validation error: {e}")
        if ctx:
            await ctx.error(f"Input validation error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error in execute_{tool}: {e}")
        if ctx:
            await ctx.error(f"Unexpected error: {str(e)}")
        raise CommandExecutionError(f"Unexpected error: {str(e)}", {"command": command}) from e


async def _describe_tool_command(tool: str, command: str | None, ctx: Context | None) -> CommandHelpResult:
    """Internal implementation for getting tool command help.

    Raises exceptions for errors so FastMCP returns them with isError=true per MCP spec.

    Args:
        tool: The CLI tool name (kubectl, istioctl, helm, argocd)
        command: Specific command to get help for, or None for general help
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text

    Raises:
        CommandExecutionError: If the tool is not installed or help retrieval fails
    """
    logger.info(f"Getting {tool} documentation for command: {command or 'None'}")

    if not cli_status.get(tool, False):
        message = f"{tool} is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        raise CommandExecutionError(message)

    try:
        if ctx:
            await ctx.info(f"Fetching {tool} help for {command or 'general usage'}")

        result = await get_command_help(tool, command)
        if result.status == "error":
            error_msg = result.help_text or f"Error retrieving {tool} help"
            if ctx:
                await ctx.error(error_msg)
            raise CommandExecutionError(error_msg)
        return result
    except Exception as e:
        logger.error(f"Error in describe_{tool}: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving {tool} help: {str(e)}")
        raise CommandExecutionError(f"Error retrieving {tool} help: {str(e)}") from e


# Tool-specific command documentation functions
@mcp.tool(annotations=ToolAnnotations(title="kubectl Help", readOnlyHint=True), icons=_ICONS["kubectl"])
async def describe_kubectl(
    command: str | None = Field(description="Specific kubectl command to get help for", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation and help text for kubectl commands.

    Args:
        command: Specific command or subcommand to get help for (e.g., 'get pods')
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text

    Raises:
        CommandExecutionError: If kubectl is not installed or help retrieval fails
    """
    return await _describe_tool_command("kubectl", command, ctx)


@mcp.tool(annotations=ToolAnnotations(title="Helm Help", readOnlyHint=True), icons=_ICONS["helm"])
async def describe_helm(
    command: str | None = Field(description="Specific Helm command to get help for", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation and help text for Helm commands.

    Args:
        command: Specific command or subcommand to get help for (e.g., 'list')
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text

    Raises:
        CommandExecutionError: If helm is not installed or help retrieval fails
    """
    return await _describe_tool_command("helm", command, ctx)


@mcp.tool(annotations=ToolAnnotations(title="Istio Help", readOnlyHint=True), icons=_ICONS["istioctl"])
async def describe_istioctl(
    command: str | None = Field(description="Specific Istio command to get help for", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation and help text for Istio commands.

    Args:
        command: Specific command or subcommand to get help for (e.g., 'analyze')
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text

    Raises:
        CommandExecutionError: If istioctl is not installed or help retrieval fails
    """
    return await _describe_tool_command("istioctl", command, ctx)


@mcp.tool(annotations=ToolAnnotations(title="ArgoCD Help", readOnlyHint=True), icons=_ICONS["argocd"])
async def describe_argocd(
    command: str | None = Field(description="Specific ArgoCD command to get help for", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation and help text for ArgoCD commands.

    Args:
        command: Specific command or subcommand to get help for (e.g., 'app')
        ctx: Optional MCP context for request tracking

    Returns:
        CommandHelpResult containing the help text

    Raises:
        CommandExecutionError: If argocd is not installed or help retrieval fails
    """
    return await _describe_tool_command("argocd", command, ctx)


# Tool-specific command execution functions
@mcp.tool(
    description="Execute kubectl commands with support for Unix pipes.",
    annotations=ToolAnnotations(title="Execute kubectl", destructiveHint=True, openWorldHint=True),
    icons=_ICONS["kubectl"],
)
async def execute_kubectl(
    command: str = Field(description="Complete kubectl command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute kubectl commands with support for Unix pipes.

    Executes kubectl commands with proper validation, error handling, and resource limits.
    Supports piping output to standard Unix utilities for filtering and transformation.

    Security considerations:
    - Commands are validated against security policies
    - Dangerous operations require specific resource names
    - Interactive shells via kubectl exec are restricted

    Examples:
        kubectl get pods
        kubectl get pods -o json | jq '.items[].metadata.name'
        kubectl describe pod my-pod
        kubectl logs my-pod -c my-container

    Args:
        command: Complete kubectl command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status with structured error information
    """
    return await _execute_tool_command("kubectl", command, timeout, ctx)


@mcp.tool(
    description="Execute Helm commands with support for Unix pipes.",
    annotations=ToolAnnotations(title="Execute Helm", destructiveHint=True, openWorldHint=True),
    icons=_ICONS["helm"],
)
async def execute_helm(
    command: str = Field(description="Complete Helm command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute Helm commands with support for Unix pipes.

    Executes Helm commands with proper validation, error handling, and resource limits.
    Supports piping output to standard Unix utilities for filtering and transformation.

    Security considerations:
    - Commands are validated against security policies
    - Dangerous operations like delete/uninstall require confirmation

    Examples:
        helm list
        helm status my-release
        helm get values my-release
        helm get values my-release -o json | jq '.global'

    Args:
        command: Complete Helm command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status with structured error information
    """
    return await _execute_tool_command("helm", command, timeout, ctx)


@mcp.tool(
    description="Execute Istio commands with support for Unix pipes.",
    annotations=ToolAnnotations(title="Execute Istio", destructiveHint=True, openWorldHint=True),
    icons=_ICONS["istioctl"],
)
async def execute_istioctl(
    command: str = Field(description="Complete Istio command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute Istio commands with support for Unix pipes.

    Executes istioctl commands with proper validation, error handling, and resource limits.
    Supports piping output to standard Unix utilities for filtering and transformation.

    Security considerations:
    - Commands are validated against security policies
    - Experimental commands and proxy-config access are restricted

    Examples:
        istioctl version
        istioctl analyze
        istioctl proxy-status
        istioctl dashboard kiali

    Args:
        command: Complete Istio command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status with structured error information
    """
    return await _execute_tool_command("istioctl", command, timeout, ctx)


@mcp.tool(
    description="Execute ArgoCD commands with support for Unix pipes.",
    annotations=ToolAnnotations(title="Execute ArgoCD", destructiveHint=True, openWorldHint=True),
    icons=_ICONS["argocd"],
)
async def execute_argocd(
    command: str = Field(description="Complete ArgoCD command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute ArgoCD commands with support for Unix pipes.

    Executes ArgoCD commands with proper validation, error handling, and resource limits.
    Supports piping output to standard Unix utilities for filtering and transformation.

    Security considerations:
    - Commands are validated against security policies
    - Destructive operations like app delete and repo removal are restricted

    Examples:
        argocd app list
        argocd app get my-app
        argocd cluster list
        argocd repo list

    Args:
        command: Complete ArgoCD command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status with structured error information
    """
    return await _execute_tool_command("argocd", command, timeout, ctx)

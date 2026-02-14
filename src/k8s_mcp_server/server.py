"""Main server implementation for K8s MCP Server.

This module defines the MCP server instance and tool functions for Kubernetes CLI interaction,
providing a standardized interface for kubectl, istioctl, helm, and argocd command execution
and documentation.
"""

import asyncio
import logging
import sys

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from pydantic.fields import FieldInfo

from k8s_mcp_server import __version__
from k8s_mcp_server.cli_executor import (
    check_cli_installed,
    execute_command,
    get_command_help,
)
from k8s_mcp_server.config import DEFAULT_TIMEOUT, INSTRUCTIONS, SUPPORTED_CLI_TOOLS
from k8s_mcp_server.errors import (
    AuthenticationError,
    CommandExecutionError,
    CommandTimeoutError,
    CommandValidationError,
    create_error_result,
)
from k8s_mcp_server.prompts import register_prompts
from k8s_mcp_server.tools import CommandHelpResult, CommandResult

logger = logging.getLogger(__name__)


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

    Args:
        tool: The CLI tool name (kubectl, istioctl, helm, argocd)
        command: The command to execute
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking

    Returns:
        CommandResult containing output and status
    """
    logger.info(f"Executing {tool} command: {command}" + (f" with timeout: {timeout}" if timeout else ""))

    # Check if tool is installed
    if not cli_status.get(tool, False):
        message = f"{tool} is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandResult(status="error", output=message)

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
    except CommandValidationError as e:
        logger.warning(f"{tool} command validation error: {e}")
        if ctx:
            await ctx.error(f"Command validation error: {str(e)}")
        return create_error_result(e, command=command)
    except CommandExecutionError as e:
        logger.warning(f"{tool} command execution error: {e}")
        if ctx:
            await ctx.error(f"Command execution error: {str(e)}")
        return create_error_result(e, command=command)
    except AuthenticationError as e:
        logger.warning(f"{tool} command authentication error: {e}")
        if ctx:
            await ctx.error(f"Authentication error: {str(e)}")
        return create_error_result(e, command=command)
    except CommandTimeoutError as e:
        logger.warning(f"{tool} command timeout error: {e}")
        if ctx:
            await ctx.error(f"Command timed out: {str(e)}")
        return create_error_result(e, command=command)
    except Exception as e:
        logger.error(f"Error in execute_{tool}: {e}")
        if ctx:
            await ctx.error(f"Unexpected error: {str(e)}")
        error = CommandExecutionError(f"Unexpected error: {str(e)}", {"command": command})
        return create_error_result(error, command=command)


# Tool-specific command documentation functions
@mcp.tool(annotations=ToolAnnotations(title="kubectl Help", readOnlyHint=True))
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
    """
    logger.info(f"Getting kubectl documentation for command: {command or 'None'}")

    # Check if kubectl is installed
    if not cli_status.get("kubectl", False):
        message = "kubectl is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message, status="error")

    try:
        if ctx:
            await ctx.info(f"Fetching kubectl help for {command or 'general usage'}")

        result = await get_command_help("kubectl", command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving kubectl help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_kubectl: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving kubectl help: {str(e)}")
        return CommandHelpResult(help_text=f"Error retrieving kubectl help: {str(e)}", status="error", error={"message": str(e), "code": "INTERNAL_ERROR"})


@mcp.tool(annotations=ToolAnnotations(title="Helm Help", readOnlyHint=True))
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
    """
    logger.info(f"Getting Helm documentation for command: {command or 'None'}")

    # Check if Helm is installed
    if not cli_status.get("helm", False):
        message = "helm is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message, status="error")

    try:
        if ctx:
            await ctx.info(f"Fetching Helm help for {command or 'general usage'}")

        result = await get_command_help("helm", command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving Helm help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_helm: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving Helm help: {str(e)}")
        return CommandHelpResult(help_text=f"Error retrieving Helm help: {str(e)}", status="error", error={"message": str(e), "code": "INTERNAL_ERROR"})


@mcp.tool(annotations=ToolAnnotations(title="Istio Help", readOnlyHint=True))
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
    """
    logger.info(f"Getting istioctl documentation for command: {command or 'None'}")

    # Check if istioctl is installed
    if not cli_status.get("istioctl", False):
        message = "istioctl is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message, status="error")

    try:
        if ctx:
            await ctx.info(f"Fetching istioctl help for {command or 'general usage'}")

        result = await get_command_help("istioctl", command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving istioctl help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_istioctl: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving istioctl help: {str(e)}")
        return CommandHelpResult(help_text=f"Error retrieving istioctl help: {str(e)}", status="error", error={"message": str(e), "code": "INTERNAL_ERROR"})


@mcp.tool(annotations=ToolAnnotations(title="ArgoCD Help", readOnlyHint=True))
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
    """
    logger.info(f"Getting ArgoCD documentation for command: {command or 'None'}")

    # Check if ArgoCD is installed
    if not cli_status.get("argocd", False):
        message = "argocd is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message, status="error")

    try:
        if ctx:
            await ctx.info(f"Fetching ArgoCD help for {command or 'general usage'}")

        result = await get_command_help("argocd", command)
        if ctx and result.status == "error":
            await ctx.error(f"Error retrieving ArgoCD help: {result.help_text}")
        return result
    except Exception as e:
        logger.error(f"Error in describe_argocd: {e}")
        if ctx:
            await ctx.error(f"Unexpected error retrieving ArgoCD help: {str(e)}")
        return CommandHelpResult(help_text=f"Error retrieving ArgoCD help: {str(e)}", status="error", error={"message": str(e), "code": "INTERNAL_ERROR"})


# Tool-specific command execution functions
@mcp.tool(
    description="Execute kubectl commands with support for Unix pipes.",
    annotations=ToolAnnotations(title="Execute kubectl", destructiveHint=True, openWorldHint=True),
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

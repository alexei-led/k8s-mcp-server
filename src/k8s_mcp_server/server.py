"""Main server implementation for K8s MCP Server.

This module defines the MCP server instance and tool functions for Kubernetes CLI interaction,
providing a standardized interface for kubectl, istioctl, helm, and argocd command execution
and documentation.
"""

import asyncio
import logging
import sys
from typing import Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from k8s_mcp_server.cli_executor import (
    CommandExecutionError,
    CommandHelpResult,
    CommandResult,
    CommandValidationError,
    check_cli_installed,
    execute_command,
    get_command_help,
)
from k8s_mcp_server.config import INSTRUCTIONS, SERVER_INFO, SUPPORTED_CLI_TOOLS
from k8s_mcp_server.prompts import register_prompts

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", handlers=[logging.StreamHandler(sys.stderr)])
logger = logging.getLogger("k8s-mcp-server")


# Function to run startup checks in synchronous context
def run_startup_checks() -> Dict[str, bool]:
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
    "K8s MCP Server",
    instructions=INSTRUCTIONS,
    version=SERVER_INFO["version"],
)

# Register prompt templates
register_prompts(mcp)


# Tool-specific command documentation functions
@mcp.tool()
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
        return CommandHelpResult(help_text=message)
    
    try:
        if ctx:
            await ctx.info(f"Fetching kubectl help for {command or 'general usage'}")
            
        result = await get_command_help("kubectl", command)
        return result
    except Exception as e:
        logger.error(f"Error in describe_kubectl: {e}")
        return CommandHelpResult(help_text=f"Error retrieving kubectl help: {str(e)}")


@mcp.tool()
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
        return CommandHelpResult(help_text=message)
    
    try:
        if ctx:
            await ctx.info(f"Fetching Helm help for {command or 'general usage'}")
            
        result = await get_command_help("helm", command)
        return result
    except Exception as e:
        logger.error(f"Error in describe_helm: {e}")
        return CommandHelpResult(help_text=f"Error retrieving Helm help: {str(e)}")


@mcp.tool()
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
        return CommandHelpResult(help_text=message)
    
    try:
        if ctx:
            await ctx.info(f"Fetching istioctl help for {command or 'general usage'}")
            
        result = await get_command_help("istioctl", command)
        return result
    except Exception as e:
        logger.error(f"Error in describe_istioctl: {e}")
        return CommandHelpResult(help_text=f"Error retrieving istioctl help: {str(e)}")


@mcp.tool()
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
        return CommandHelpResult(help_text=message)
    
    try:
        if ctx:
            await ctx.info(f"Fetching ArgoCD help for {command or 'general usage'}")
            
        result = await get_command_help("argocd", command)
        return result
    except Exception as e:
        logger.error(f"Error in describe_argocd: {e}")
        return CommandHelpResult(help_text=f"Error retrieving ArgoCD help: {str(e)}")


# Backward compatibility function for the old describe_command API
@mcp.tool()
async def describe_command(
    cli_tool: str = Field(description="CLI tool (kubectl, istioctl, helm, argocd)"),
    command: str | None = Field(description="Command within the CLI tool", default=None),
    ctx: Context | None = None,
) -> CommandHelpResult:
    """Get documentation for a CLI tool command.

    Retrieves the help documentation for a specified Kubernetes CLI tool
    or a specific command within that tool.

    Returns:
        CommandHelpResult containing the help text
    """
    logger.info(f"Getting documentation for {cli_tool} command: {command or 'None'}")

    # Validate CLI tool
    if cli_tool not in SUPPORTED_CLI_TOOLS:
        allowed_tools = ", ".join(SUPPORTED_CLI_TOOLS.keys())
        message = f"Unsupported CLI tool: {cli_tool}. Supported tools are: {allowed_tools}"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message)
    
    # Check if CLI tool is installed
    if not cli_status.get(cli_tool, False):
        message = f"{cli_tool} is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandHelpResult(help_text=message)

    try:
        if ctx:
            await ctx.info(f"Fetching help for {cli_tool} {command or ''}")

        # Reuse the get_command_help function from cli_executor
        result = await get_command_help(cli_tool, command)
        return result
    except Exception as e:
        logger.error(f"Error in describe_command: {e}")
        return CommandHelpResult(help_text=f"Error retrieving help: {str(e)}")


# Tool-specific command execution functions
@mcp.tool()
async def execute_kubectl(
    command: str = Field(description="Complete kubectl command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute kubectl commands with support for Unix pipes.
    
    Args:
        command: Complete kubectl command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking
        
    Returns:
        CommandResult containing output and status
    """
    logger.info(f"Executing kubectl command: {command}" + (f" with timeout: {timeout}" if timeout else ""))
    
    # Check if kubectl is installed
    if not cli_status.get("kubectl", False):
        message = "kubectl is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandResult(status="error", output=message)
    
    # Add kubectl prefix if not present
    if not command.strip().startswith("kubectl"):
        command = f"kubectl {command}"
    
    if ctx:
        is_pipe = "|" in command
        message = "Executing" + (" piped" if is_pipe else "") + " kubectl command"
        await ctx.info(message + (f" with timeout: {timeout}s" if timeout else ""))
    
    try:
        result = await execute_command(command, timeout)
        
        # Format the output for better readability
        if result["status"] == "success":
            if ctx:
                await ctx.info("kubectl command executed successfully")
        else:
            if ctx:
                await ctx.warning("kubectl command failed")
        
        return CommandResult(status=result["status"], output=result["output"])
    except CommandValidationError as e:
        logger.warning(f"kubectl command validation error: {e}")
        return CommandResult(status="error", output=f"Command validation error: {str(e)}")
    except CommandExecutionError as e:
        logger.warning(f"kubectl command execution error: {e}")
        return CommandResult(status="error", output=f"Command execution error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in execute_kubectl: {e}")
        return CommandResult(status="error", output=f"Unexpected error: {str(e)}")


@mcp.tool()
async def execute_helm(
    command: str = Field(description="Complete Helm command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute Helm commands with support for Unix pipes.
    
    Args:
        command: Complete Helm command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking
        
    Returns:
        CommandResult containing output and status
    """
    logger.info(f"Executing Helm command: {command}" + (f" with timeout: {timeout}" if timeout else ""))
    
    # Check if Helm is installed
    if not cli_status.get("helm", False):
        message = "helm is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandResult(status="error", output=message)
    
    # Add helm prefix if not present
    if not command.strip().startswith("helm"):
        command = f"helm {command}"
    
    if ctx:
        is_pipe = "|" in command
        message = "Executing" + (" piped" if is_pipe else "") + " Helm command"
        await ctx.info(message + (f" with timeout: {timeout}s" if timeout else ""))
    
    try:
        result = await execute_command(command, timeout)
        
        # Format the output for better readability
        if result["status"] == "success":
            if ctx:
                await ctx.info("Helm command executed successfully")
        else:
            if ctx:
                await ctx.warning("Helm command failed")
        
        return CommandResult(status=result["status"], output=result["output"])
    except CommandValidationError as e:
        logger.warning(f"Helm command validation error: {e}")
        return CommandResult(status="error", output=f"Command validation error: {str(e)}")
    except CommandExecutionError as e:
        logger.warning(f"Helm command execution error: {e}")
        return CommandResult(status="error", output=f"Command execution error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in execute_helm: {e}")
        return CommandResult(status="error", output=f"Unexpected error: {str(e)}")


@mcp.tool()
async def execute_istioctl(
    command: str = Field(description="Complete Istio command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute Istio commands with support for Unix pipes.
    
    Args:
        command: Complete Istio command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking
        
    Returns:
        CommandResult containing output and status
    """
    logger.info(f"Executing istioctl command: {command}" + (f" with timeout: {timeout}" if timeout else ""))
    
    # Check if istioctl is installed
    if not cli_status.get("istioctl", False):
        message = "istioctl is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandResult(status="error", output=message)
    
    # Add istioctl prefix if not present
    if not command.strip().startswith("istioctl"):
        command = f"istioctl {command}"
    
    if ctx:
        is_pipe = "|" in command
        message = "Executing" + (" piped" if is_pipe else "") + " istioctl command"
        await ctx.info(message + (f" with timeout: {timeout}s" if timeout else ""))
    
    try:
        result = await execute_command(command, timeout)
        
        # Format the output for better readability
        if result["status"] == "success":
            if ctx:
                await ctx.info("istioctl command executed successfully")
        else:
            if ctx:
                await ctx.warning("istioctl command failed")
        
        return CommandResult(status=result["status"], output=result["output"])
    except CommandValidationError as e:
        logger.warning(f"istioctl command validation error: {e}")
        return CommandResult(status="error", output=f"Command validation error: {str(e)}")
    except CommandExecutionError as e:
        logger.warning(f"istioctl command execution error: {e}")
        return CommandResult(status="error", output=f"Command execution error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in execute_istioctl: {e}")
        return CommandResult(status="error", output=f"Unexpected error: {str(e)}")


@mcp.tool()
async def execute_argocd(
    command: str = Field(description="Complete ArgoCD command to execute (including any pipes and flags)"),
    timeout: int | None = Field(description="Maximum execution time in seconds (default: 300)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute ArgoCD commands with support for Unix pipes.
    
    Args:
        command: Complete ArgoCD command to execute (can include Unix pipes)
        timeout: Optional timeout in seconds
        ctx: Optional MCP context for request tracking
        
    Returns:
        CommandResult containing output and status
    """
    logger.info(f"Executing ArgoCD command: {command}" + (f" with timeout: {timeout}" if timeout else ""))
    
    # Check if ArgoCD is installed
    if not cli_status.get("argocd", False):
        message = "argocd is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandResult(status="error", output=message)
    
    # Add argocd prefix if not present
    if not command.strip().startswith("argocd"):
        command = f"argocd {command}"
    
    if ctx:
        is_pipe = "|" in command
        message = "Executing" + (" piped" if is_pipe else "") + " ArgoCD command"
        await ctx.info(message + (f" with timeout: {timeout}s" if timeout else ""))
    
    try:
        result = await execute_command(command, timeout)
        
        # Format the output for better readability
        if result["status"] == "success":
            if ctx:
                await ctx.info("ArgoCD command executed successfully")
        else:
            if ctx:
                await ctx.warning("ArgoCD command failed")
        
        return CommandResult(status=result["status"], output=result["output"])
    except CommandValidationError as e:
        logger.warning(f"ArgoCD command validation error: {e}")
        return CommandResult(status="error", output=f"Command validation error: {str(e)}")
    except CommandExecutionError as e:
        logger.warning(f"ArgoCD command execution error: {e}")
        return CommandResult(status="error", output=f"Command execution error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in execute_argocd: {e}")
        return CommandResult(status="error", output=f"Unexpected error: {str(e)}")


# Backward compatibility function for the old execute_command API
@mcp.tool()
async def execute_command(
    command: str = Field(description="Complete command to execute (can include pipes with Unix commands)"),
    timeout: int | None = Field(description="Timeout in seconds (defaults to DEFAULT_TIMEOUT)", default=None),
    ctx: Context | None = None,
) -> CommandResult:
    """Execute a Kubernetes CLI command, optionally with Unix command pipes.

    Validates, executes, and processes the results of a command for kubectl, istioctl,
    helm, or argocd, handling errors and formatting the output for better readability.

    The command can include Unix pipes (|) to filter or transform the output,
    similar to a regular shell. The first command must be a supported CLI tool command,
    and subsequent piped commands must be basic Unix utilities.

    Examples:
    - kubectl get pods
    - kubectl get pods -o json | jq '.items[].metadata.name'
    - helm list | grep mysql
    - istioctl analyze | grep Warning

    Returns:
        CommandResult containing output and status
    """
    logger.info(f"Executing command: {command}" + (f" with timeout: {timeout}" if timeout else ""))

    # Extract CLI tool from command
    cli_tool = command.strip().split()[0] if command.strip() else ""
    
    # Validate CLI tool
    if cli_tool not in SUPPORTED_CLI_TOOLS:
        allowed_tools = ", ".join(SUPPORTED_CLI_TOOLS.keys())
        message = f"Unsupported CLI tool: {cli_tool}. Supported tools are: {allowed_tools}"
        if ctx:
            await ctx.error(message)
        return CommandResult(status="error", output=message)
    
    # Check if CLI tool is installed
    if not cli_status.get(cli_tool, False):
        message = f"{cli_tool} is not installed or not in PATH"
        if ctx:
            await ctx.error(message)
        return CommandResult(status="error", output=message)

    if ctx:
        is_pipe = "|" in command
        message = "Executing" + (" piped" if is_pipe else "") + f" {cli_tool} command"
        await ctx.info(message + (f" with timeout: {timeout}s" if timeout else ""))

    try:
        result = await execute_command(command, timeout)

        # Format the output for better readability
        if result["status"] == "success":
            if ctx:
                await ctx.info("Command executed successfully")
        else:
            if ctx:
                await ctx.warning("Command failed")

        return CommandResult(status=result["status"], output=result["output"])
    except CommandValidationError as e:
        logger.warning(f"Command validation error: {e}")
        return CommandResult(status="error", output=f"Command validation error: {str(e)}")
    except CommandExecutionError as e:
        logger.warning(f"Command execution error: {e}")
        return CommandResult(status="error", output=f"Command execution error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in execute_command: {e}")
        return CommandResult(status="error", output=f"Unexpected error: {str(e)}")
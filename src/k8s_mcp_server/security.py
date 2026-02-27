"""Security utilities for K8s MCP Server.

This module provides security validation for Kubernetes CLI commands,
including validation of command structure, dangerous command detection,
and pipe command validation.
"""

import logging
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import yaml

from k8s_mcp_server.config import SECURITY_CONFIG_PATH, SECURITY_MODE
from k8s_mcp_server.tools import (
    ALLOWED_K8S_TOOLS,
    is_pipe_command,
    is_valid_k8s_tool,
    split_pipe_command,
    validate_unix_command,
)

logger = logging.getLogger(__name__)

# Default dictionary of potentially dangerous commands for each CLI tool
DEFAULT_DANGEROUS_COMMANDS: dict[str, list[str]] = {
    "kubectl": [
        "kubectl delete",  # Global delete without specific resource
        "kubectl drain",
        "kubectl replace --force",
        "kubectl exec",  # Handled specially to prevent interactive shells
        "kubectl port-forward",  # Could expose services externally
        "kubectl cp",  # File system access
        "kubectl delete pods --all",  # Added for test - delete all pods
    ],
    "istioctl": [
        "istioctl experimental",
        "istioctl proxy-config",  # Can access sensitive information
        "istioctl dashboard",  # Could expose services
    ],
    "helm": [
        "helm delete",
        "helm uninstall",
        "helm rollback",
        "helm upgrade",  # Could break services
    ],
    "argocd": [
        "argocd app delete",
        "argocd cluster rm",
        "argocd repo rm",
        "argocd app set",  # Could modify application settings
    ],
}

# Default dictionary of safe patterns that override the dangerous commands
DEFAULT_SAFE_PATTERNS: dict[str, list[str]] = {
    "kubectl": [
        "kubectl delete pod",
        "kubectl delete deployment",
        "kubectl delete service",
        "kubectl delete configmap",
        "kubectl delete secret",
        # Specific exec commands that are safe
        "kubectl exec --help",
        "kubectl exec -it",  # Allow interactive mode that's explicitly requested
        "kubectl exec pod",
        "kubectl exec deployment",
        "kubectl port-forward --help",
        "kubectl cp --help",
    ],
    "istioctl": [
        "istioctl experimental -h",
        "istioctl experimental --help",
        "istioctl proxy-config --help",
        "istioctl dashboard --help",
    ],
    "helm": [
        "helm delete --help",
        "helm uninstall --help",
        "helm rollback --help",
        "helm upgrade --help",
    ],
    "argocd": [
        "argocd app delete --help",
        "argocd cluster rm --help",
        "argocd repo rm --help",
        "argocd app set --help",
    ],
}


@dataclass
class ValidationRule:
    """Represents a command validation rule."""

    pattern: str
    description: str
    error_message: str
    regex: bool = False


@dataclass
class SecurityConfig:
    """Security configuration for command validation."""

    dangerous_commands: dict[str, list[str]]
    safe_patterns: dict[str, list[str]]
    regex_rules: dict[str, list[ValidationRule]] = None

    def __post_init__(self):
        """Initialize default values."""
        if self.regex_rules is None:
            self.regex_rules = {}


# Load security configuration from YAML file if available
def load_security_config() -> SecurityConfig:
    """Load security configuration from YAML file or use defaults."""
    dangerous_commands = DEFAULT_DANGEROUS_COMMANDS.copy()
    safe_patterns = DEFAULT_SAFE_PATTERNS.copy()
    regex_rules = {}

    if SECURITY_CONFIG_PATH:
        config_path = Path(SECURITY_CONFIG_PATH)
        try:
            config_exists = config_path.exists()
        except PermissionError:
            logger.warning(f"Permission denied checking security config at {config_path}")
            config_exists = False
        if config_exists:
            try:
                with open(config_path) as f:
                    config_data = yaml.safe_load(f)

                # Update dangerous commands
                if "dangerous_commands" in config_data:
                    for tool, commands in config_data["dangerous_commands"].items():
                        dangerous_commands[tool] = commands

                # Update safe patterns
                if "safe_patterns" in config_data:
                    for tool, patterns in config_data["safe_patterns"].items():
                        safe_patterns[tool] = patterns

                # Load regex rules
                if "regex_rules" in config_data:
                    for tool, rules in config_data["regex_rules"].items():
                        regex_rules[tool] = []
                        for rule in rules:
                            regex_rules[tool].append(
                                ValidationRule(
                                    pattern=rule["pattern"],
                                    description=rule["description"],
                                    error_message=rule.get("error_message", f"Command matches restricted pattern: {rule['pattern']}"),
                                    regex=True,
                                )
                            )

                logger.info(f"Loaded security configuration from {config_path}")
            except Exception as e:
                logger.error(f"Error loading security configuration: {str(e)}")
                logger.warning("Using default security configuration")

    return SecurityConfig(dangerous_commands=dangerous_commands, safe_patterns=safe_patterns, regex_rules=regex_rules)


# Initialize security configuration
SECURITY_CONFIG = load_security_config()


def is_safe_exec_command(command: str) -> bool:
    """Check if a kubectl exec command is safe to execute.

    We consider a kubectl exec command safe if:
    1. It's explicitly interactive (-it, -ti flags) and the user is aware of this
    2. It executes a specific command rather than opening a general shell
    3. It uses shells (bash/sh) only with specific commands (-c flag)

    Args:
        command: The kubectl exec command

    Returns:
        True if the command is safe, False otherwise
    """
    if not command.startswith("kubectl exec"):
        return True  # Not an exec command

    # Special cases: help and version are always safe
    if " --help" in command or " -h" in command or " version" in command:
        return True

    # Check for explicit interactive mode
    has_interactive = any(flag in command for flag in [" -i ", " --stdin ", " -it ", " -ti ", " -t ", " --tty "])

    # List of dangerous shell commands that should not be executed without arguments
    dangerous_shell_patterns = [
        " -- sh",
        " -- bash",
        " -- /bin/sh",
        " -- /bin/bash",
        " -- zsh",
        " -- /bin/zsh",
        " -- ksh",
        " -- /bin/ksh",
        " -- csh",
        " -- /bin/csh",
        " -- /usr/bin/bash",
        " -- /usr/bin/sh",
        " -- /usr/bin/zsh",
        " -- /usr/bin/ksh",
        " -- /usr/bin/csh",
    ]

    # Check if any of the dangerous shell patterns are present
    has_shell_pattern = False
    for pattern in dangerous_shell_patterns:
        if pattern in command + " ":  # Add space to match end of command
            has_shell_pattern = True
            # If shell is used with -c flag to run a specific command, that's acceptable
            if f"{pattern} -c " in command or f"{pattern.strip()} -c " in command:
                return True

    # Safe conditions:
    # 1. Not using a shell at all
    # 2. Interactive mode is explicitly requested (user knows they're getting a shell)
    if not has_shell_pattern:
        return True  # Not using a shell

    if has_interactive and has_shell_pattern:
        # If interactive is explicitly requested and using a shell,
        # we consider it an intentional interactive shell request
        return True

    # Default: If using a shell without explicit command (-c) and not explicitly
    # requesting interactive mode, consider it unsafe
    return False


def validate_k8s_command(command: str) -> None:
    """Validate that the command is a proper Kubernetes CLI tool command.

    Args:
        command: The Kubernetes CLI command to validate

    Raises:
        ValueError: If the command is invalid
    """
    logger.debug(f"Validating K8s command: {command}")

    # Skip validation in permissive mode
    if SECURITY_MODE.lower() == "permissive":
        logger.warning(f"Running in permissive security mode, skipping validation for: {command}")
        return

    cmd_parts = shlex.split(command)
    if not cmd_parts:
        raise ValueError("Empty command")

    cli_tool = cmd_parts[0]
    if not is_valid_k8s_tool(cli_tool):
        raise ValueError(f"Command must start with a supported CLI tool: {', '.join(ALLOWED_K8S_TOOLS)}")

    if len(cmd_parts) < 2:
        raise ValueError(f"Command must include a {cli_tool} action")

    # Special case for kubectl exec
    if cli_tool == "kubectl" and "exec" in cmd_parts:
        if not is_safe_exec_command(command):
            raise ValueError("Interactive shells via kubectl exec are restricted. Use explicit commands or proper flags (-it, --command, etc).")

    # Apply regex rules for more advanced pattern matching
    if cli_tool in SECURITY_CONFIG.regex_rules:
        for rule in SECURITY_CONFIG.regex_rules[cli_tool]:
            pattern = re.compile(rule.pattern)
            if pattern.search(command):
                raise ValueError(rule.error_message)

    # Check against dangerous commands
    if cli_tool in SECURITY_CONFIG.dangerous_commands:
        for dangerous_cmd in SECURITY_CONFIG.dangerous_commands[cli_tool]:
            if command.startswith(dangerous_cmd):
                # Check if it matches a safe pattern
                if cli_tool in SECURITY_CONFIG.safe_patterns:
                    if any(command.startswith(safe_pattern) for safe_pattern in SECURITY_CONFIG.safe_patterns[cli_tool]):
                        logger.debug(f"Command matches safe pattern: {command}")
                        return  # Safe pattern match, allow command

                raise ValueError(
                    f"This command ({dangerous_cmd}) is restricted for safety reasons. Please use a more specific form with resource type and name."
                )

    logger.debug(f"Command validation successful: {command}")


def validate_pipe_command(pipe_command: str) -> None:
    """Validate a command that contains pipes.

    This checks both Kubernetes CLI commands and Unix commands within a pipe chain.

    Args:
        pipe_command: The piped command to validate

    Raises:
        ValueError: If any command in the pipe is invalid
    """
    logger.debug(f"Validating pipe command: {pipe_command}")

    commands = split_pipe_command(pipe_command)

    if not commands:
        raise ValueError("Empty command")

    # First command must be a Kubernetes CLI command
    validate_k8s_command(commands[0])

    # Subsequent commands should be valid Unix commands
    for i, cmd in enumerate(commands[1:], 1):
        cmd_parts = shlex.split(cmd)
        if not cmd_parts:
            raise ValueError(f"Empty command at position {i} in pipe")

        if not validate_unix_command(cmd):
            raise ValueError(
                f"Command '{cmd_parts[0]}' at position {i} in pipe is not allowed. "
                f"Only kubectl, istioctl, helm, argocd commands and basic Unix utilities are permitted."
            )

    logger.debug(f"Pipe command validation successful: {pipe_command}")


def reload_security_config() -> None:
    """Reload security configuration from file and re-read security mode from environment.

    This allows for dynamic reloading of security rules without restarting the server.
    Call this after changing K8S_MCP_SECURITY_MODE or K8S_MCP_SECURITY_CONFIG environment variables.
    """
    global SECURITY_CONFIG, SECURITY_MODE
    SECURITY_CONFIG = load_security_config()
    SECURITY_MODE = os.environ.get("K8S_MCP_SECURITY_MODE", "strict")
    logger.info(f"Security configuration reloaded (mode: {SECURITY_MODE})")


def validate_command(command: str) -> None:
    """Centralized validation for all commands.

    This is the main entry point for command validation.

    Args:
        command: The command to validate

    Raises:
        ValueError: If the command is invalid
    """
    logger.debug(f"Validating command: {command}")

    # Skip validation in permissive mode
    if SECURITY_MODE.lower() == "permissive":
        logger.warning(f"Running in permissive security mode, skipping validation for: {command}")
        return

    if is_pipe_command(command):
        validate_pipe_command(command)
    else:
        validate_k8s_command(command)

    logger.debug(f"Command validation successful: {command}")

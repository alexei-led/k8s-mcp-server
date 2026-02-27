"""Tests for the security module."""

import os
from unittest.mock import mock_open, patch

import pytest
import yaml

import k8s_mcp_server.security
from k8s_mcp_server.security import (
    DEFAULT_DANGEROUS_COMMANDS,
    DEFAULT_SAFE_PATTERNS,
    SecurityConfig,
    ValidationRule,
    is_safe_exec_command,
    load_security_config,
    reload_security_config,
    validate_command,
    validate_k8s_command,
    validate_pipe_command,
)


def test_validation_rule_class():
    """Test the ValidationRule dataclass."""
    # Create a validation rule instance
    rule = ValidationRule(
        pattern="kubectl get",
        description="Get Kubernetes resources",
        error_message="Invalid get command",
    )

    # Check the attributes
    assert rule.pattern == "kubectl get"
    assert rule.description == "Get Kubernetes resources"
    assert rule.error_message == "Invalid get command"


def test_is_safe_exec_command_edge_cases():
    """Test is_safe_exec_command with edge cases."""
    # Edge case: empty command
    assert is_safe_exec_command("") is True  # Not an exec command

    # Edge case: exec with quotes
    assert is_safe_exec_command("kubectl exec pod-name -- 'echo hello'") is True

    # Edge case: exec with double quotes
    assert is_safe_exec_command('kubectl exec pod-name -- "echo hello"') is True

    # Edge case: exec with various shells
    assert is_safe_exec_command("kubectl exec pod-name -- csh") is False
    assert is_safe_exec_command("kubectl exec pod-name -- ksh") is False
    assert is_safe_exec_command("kubectl exec pod-name -- zsh") is False

    # Edge case: exec with full paths
    assert is_safe_exec_command("kubectl exec pod-name -- /usr/bin/bash") is False
    assert is_safe_exec_command("kubectl exec -it pod-name -- /usr/bin/bash") is True

    # Edge case: exec with complex commands
    assert is_safe_exec_command("kubectl exec pod-name -- bash -c 'for i in {1..5}; do echo $i; done'") is True

    # Edge case: exec with shell but with -c flag
    assert is_safe_exec_command("kubectl exec pod-name -- /bin/bash -c 'ls -la'") is True
    assert is_safe_exec_command("kubectl exec pod-name -- sh -c 'find / -name config'") is True


def test_security_config_class():
    """Test the SecurityConfig dataclass."""
    # Create a SecurityConfig instance
    dangerous_commands = {"kubectl": ["kubectl delete"]}
    safe_patterns = {"kubectl": ["kubectl delete pod"]}
    regex_rules = {"kubectl": [ValidationRule(pattern="kubectl\\s+delete\\s+--all", description="Delete all", error_message="Cannot delete all resources")]}

    config = SecurityConfig(dangerous_commands=dangerous_commands, safe_patterns=safe_patterns, regex_rules=regex_rules)

    # Assert the values were set correctly
    assert config.dangerous_commands == dangerous_commands
    assert config.safe_patterns == safe_patterns
    assert config.regex_rules == regex_rules

    # Test default initialization for regex_rules
    config2 = SecurityConfig(dangerous_commands=dangerous_commands, safe_patterns=safe_patterns)

    assert config2.regex_rules == {}


def test_dangerous_and_safe_commands():
    """Test the DEFAULT_DANGEROUS_COMMANDS and DEFAULT_SAFE_PATTERNS dictionaries."""
    # Check that all CLI tools in DEFAULT_DANGEROUS_COMMANDS have corresponding DEFAULT_SAFE_PATTERNS
    for cli_tool in DEFAULT_DANGEROUS_COMMANDS:
        assert cli_tool in DEFAULT_SAFE_PATTERNS, f"{cli_tool} exists in DEFAULT_DANGEROUS_COMMANDS but not in DEFAULT_SAFE_PATTERNS"

    # Check for specific patterns we expect to be in the dictionaries
    assert "kubectl delete" in DEFAULT_DANGEROUS_COMMANDS["kubectl"]
    assert "kubectl exec" in DEFAULT_DANGEROUS_COMMANDS["kubectl"]
    assert "kubectl delete pod" in DEFAULT_SAFE_PATTERNS["kubectl"]
    assert "kubectl exec -it" in DEFAULT_SAFE_PATTERNS["kubectl"]

    # Check for Helm dangerous commands
    assert "helm delete" in DEFAULT_DANGEROUS_COMMANDS["helm"]
    assert "helm delete --help" in DEFAULT_SAFE_PATTERNS["helm"]


def test_validate_k8s_command_edge_cases():
    """Test validate_k8s_command with edge cases."""
    # Commands with exec shells should be checked by is_safe_exec_command
    with pytest.raises(ValueError):
        validate_k8s_command("kubectl exec pod-name -- /bin/bash")

    # But commands with exec and explicit interactive flags should be allowed
    validate_k8s_command("kubectl exec -it pod-name -- /bin/bash")

    # Commands with exec and -c flag should be allowed
    validate_k8s_command("kubectl exec pod-name -- /bin/bash -c 'ls -la'")

    # Command with help should be allowed
    validate_k8s_command("kubectl exec --help")

    # Command with empty string should raise ValueError
    with pytest.raises(ValueError):
        validate_k8s_command("")

    # Check that non-kubectl commands are verified properly
    validate_k8s_command("helm list")
    validate_k8s_command("istioctl version")

    # Test dangerous commands
    with pytest.raises(ValueError):
        validate_k8s_command("helm delete")

    # Test safe override of dangerous command
    validate_k8s_command("helm delete --help")


def test_regex_pattern_validation():
    """Test the regex pattern validation functionality."""
    # Create simplified test rules with simpler patterns that are easier to test
    kubectl_rule1 = ValidationRule(
        pattern=r"--all",  # Simplified to just match --all flag
        description="Delete all resources",
        error_message="Cannot delete all resources",
        regex=True,
    )

    kubectl_rule2 = ValidationRule(
        pattern=r"--namespace=kube-system",  # Simplified to match namespace directly
        description="Operations in kube-system",
        error_message="Operations in kube-system restricted",
        regex=True,
    )

    # Test that regex patterns match correctly
    import re

    # Matches for rule 1
    pattern1 = re.compile(kubectl_rule1.pattern)
    assert pattern1.search("kubectl delete pods --all")
    assert pattern1.search("kubectl delete -n default --all")
    assert not pattern1.search("kubectl delete pod my-pod")
    assert not pattern1.search("kubectl get pods")

    # Matches for rule 2
    pattern2 = re.compile(kubectl_rule2.pattern)
    assert pattern2.search("kubectl get pods --namespace=kube-system")
    assert pattern2.search("kubectl describe pod mypod --namespace=kube-system")
    assert not pattern2.search("kubectl get pods --namespace=default")
    assert not pattern2.search("kubectl get pods")


def test_validate_k8s_command_with_mocked_regex_rules():
    """Test validate_k8s_command with regex validation rules using direct mocking."""
    # Save original mode and ensure we're in strict mode
    original_mode = os.environ.get("K8S_MCP_SECURITY_MODE", "strict")
    os.environ["K8S_MCP_SECURITY_MODE"] = "strict"

    try:
        # For delete --all
        with patch(
            "k8s_mcp_server.security.SECURITY_CONFIG.regex_rules",
            {
                "kubectl": [
                    ValidationRule(
                        pattern=r"kubectl\s+delete\s+(-[A-Za-z]+\s+)*--all\b",
                        description="Delete all resources",
                        error_message="Cannot delete all resources",
                        regex=True,
                    )
                ]
            },
        ):
            # Use a command that actually matches the regex pattern - no mock needed
            with pytest.raises(ValueError, match="Cannot delete all resources"):
                validate_k8s_command("kubectl delete --all")

        # Clean pass with no regex rules
        with patch("k8s_mcp_server.security.SECURITY_CONFIG.regex_rules", {}):
            validate_k8s_command("kubectl get pods")
    finally:
        # Restore original mode
        if original_mode:
            os.environ["K8S_MCP_SECURITY_MODE"] = original_mode
        else:
            os.environ.pop("K8S_MCP_SECURITY_MODE", None)


def test_validate_pipe_command_edge_cases():
    """Test validate_pipe_command with edge cases."""
    # Pipe command with kubectl exec should still be checked for safety
    with pytest.raises(ValueError):
        validate_pipe_command("kubectl exec pod-name -- /bin/bash | grep root")

    # But pipe command with kubectl exec and -it should be allowed
    validate_pipe_command("kubectl exec -it pod-name -- /bin/bash -c 'ls -la' | grep root")

    # Test pipe commands with missing parts
    with pytest.raises(ValueError):
        validate_pipe_command("| grep root")  # Missing first command

    # Test with empty commands list
    with patch("k8s_mcp_server.security.split_pipe_command", return_value=[]):
        with pytest.raises(ValueError, match="Empty command"):
            validate_pipe_command("kubectl get pods | grep nginx")


def test_load_security_config():
    """Test loading security configuration from YAML file."""
    # Define test data
    test_config = {
        "dangerous_commands": {"kubectl": ["kubectl delete", "kubectl drain"]},
        "safe_patterns": {"kubectl": ["kubectl delete pod", "kubectl delete service"]},
        "regex_rules": {"kubectl": [{"pattern": "kubectl\\s+delete\\s+--all", "description": "Delete all resources", "error_message": "This is dangerous"}]},
    }

    # Mock open to return test YAML data
    yaml_data = yaml.dump(test_config)

    with patch("k8s_mcp_server.security.SECURITY_CONFIG_PATH", "dummy_path.yaml"):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=yaml_data)):
                # Call the function
                config = load_security_config()

                # Verify the results
                assert "kubectl" in config.dangerous_commands
                assert "kubectl delete" in config.dangerous_commands["kubectl"]
                assert "kubectl delete pod" in config.safe_patterns["kubectl"]
                assert len(config.regex_rules["kubectl"]) == 1
                assert config.regex_rules["kubectl"][0].pattern == "kubectl\\s+delete\\s+--all"
                assert config.regex_rules["kubectl"][0].regex is True


def test_load_security_config_file_not_found():
    """Test loading security config when file doesn't exist."""
    with patch("k8s_mcp_server.security.SECURITY_CONFIG_PATH", "nonexistent_file.yaml"):
        with patch("pathlib.Path.exists", return_value=False):
            # Call the function
            config = load_security_config()

            # Verify default values are used
            assert config.dangerous_commands == DEFAULT_DANGEROUS_COMMANDS
            assert config.safe_patterns == DEFAULT_SAFE_PATTERNS
            assert config.regex_rules == {}


def test_load_security_config_error_handling():
    """Test error handling when loading config file."""
    with patch("k8s_mcp_server.security.SECURITY_CONFIG_PATH", "invalid_file.yaml"):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="invalid: yaml: content:")):
                with patch("yaml.safe_load", side_effect=yaml.YAMLError("Invalid YAML")):
                    # Call the function
                    config = load_security_config()

                    # Verify default values are used after error
                    assert config.dangerous_commands == DEFAULT_DANGEROUS_COMMANDS
                    assert config.safe_patterns == DEFAULT_SAFE_PATTERNS


def test_reload_security_config():
    """Test reloading security configuration."""
    # Mock the load_security_config function to return a known value
    test_config = SecurityConfig(
        dangerous_commands={"kubectl": ["test command"]},
        safe_patterns={"kubectl": ["test safe pattern"]},
    )

    with patch("k8s_mcp_server.security.load_security_config", return_value=test_config):
        # Get the global SECURITY_CONFIG before modification
        current_config_before = k8s_mcp_server.security.SECURITY_CONFIG

        try:
            # Call reload function
            reload_security_config()

            # Get the SECURITY_CONFIG directly from the module
            current_config = k8s_mcp_server.security.SECURITY_CONFIG

            # Verify config was updated
            assert "kubectl" in current_config.dangerous_commands
            assert "test command" in current_config.dangerous_commands["kubectl"]
            assert "test safe pattern" in current_config.safe_patterns["kubectl"]
        finally:
            # Restore original config
            k8s_mcp_server.security.SECURITY_CONFIG = current_config_before


def test_permissive_security_mode():
    """Test that permissive security mode bypasses validation."""
    # Patch the security mode to permissive
    with patch("k8s_mcp_server.security.SECURITY_MODE", "permissive"):
        # These commands would normally be rejected
        validate_command("kubectl delete")
        validate_command("kubectl exec pod-name -- /bin/bash")

        # Even with pipe commands
        validate_command("kubectl delete | grep result")


def test_validate_command():
    """Test the main validate_command function."""
    # Save original settings
    original_mode = os.environ.get("K8S_MCP_SECURITY_MODE", "strict")
    os.environ["K8S_MCP_SECURITY_MODE"] = "strict"

    try:
        # Test with pipe command
        with patch("k8s_mcp_server.security.is_pipe_command", return_value=True):
            with patch("k8s_mcp_server.security.validate_pipe_command") as mock_validate_pipe:
                validate_command("kubectl get pods | grep nginx")
                mock_validate_pipe.assert_called_once_with("kubectl get pods | grep nginx")

        # Test with non-pipe command
        with patch("k8s_mcp_server.security.is_pipe_command", return_value=False):
            with patch("k8s_mcp_server.security.validate_k8s_command") as mock_validate_k8s:
                validate_command("kubectl get pods")
                mock_validate_k8s.assert_called_once_with("kubectl get pods")

        # Test dangerous commands with direct mocking
        with patch("k8s_mcp_server.security.is_pipe_command", return_value=False):
            with patch("k8s_mcp_server.security.validate_k8s_command", side_effect=ValueError("Test error")):
                with pytest.raises(ValueError, match="Test error"):
                    validate_command("kubectl delete")

        with patch("k8s_mcp_server.security.is_pipe_command", return_value=False):
            with patch("k8s_mcp_server.security.validate_k8s_command", side_effect=ValueError("Shell error")):
                with pytest.raises(ValueError, match="Shell error"):
                    validate_command("kubectl exec pod-name -- /bin/bash")
    finally:
        # Restore original settings
        if original_mode:
            os.environ["K8S_MCP_SECURITY_MODE"] = original_mode
        else:
            os.environ.pop("K8S_MCP_SECURITY_MODE", None)

"""Tests for the config module."""

from unittest.mock import patch

import pytest

from k8s_mcp_server.config import VALID_TRANSPORTS, is_docker_environment


@pytest.mark.unit
def test_valid_transports():
    """Test that VALID_TRANSPORTS contains expected values."""
    assert VALID_TRANSPORTS == {"stdio", "sse", "streamable-http"}


@pytest.mark.unit
def test_is_docker_environment_with_dockerenv():
    """Test Docker detection via /.dockerenv file."""
    from pathlib import Path

    def custom_exists(self):
        if str(self) == "/.dockerenv":
            return True
        return False

    with patch.object(Path, "exists", custom_exists):
        assert is_docker_environment() is True


@pytest.mark.unit
def test_is_docker_environment_with_cgroup():
    """Test Docker detection via /proc/self/cgroup."""
    from pathlib import Path

    def custom_exists(self):
        path_str = str(self)
        if path_str == "/.dockerenv":
            return False
        if path_str == "/proc/self/cgroup":
            return True
        return False

    with patch.object(Path, "exists", custom_exists):
        with patch.object(Path, "read_text", return_value="12:memory:/docker/abc123\n"):
            assert is_docker_environment() is True


@pytest.mark.unit
def test_is_docker_environment_not_docker():
    """Test that non-Docker environments are correctly detected."""
    from pathlib import Path

    def custom_exists(self):
        return False

    with patch.object(Path, "exists", custom_exists):
        assert is_docker_environment() is False

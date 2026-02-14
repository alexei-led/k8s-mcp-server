"""Unit test conftest - mocks startup checks so tests run without kubectl installed."""

from unittest.mock import AsyncMock, patch

# Patch check_cli_installed before server module import triggers run_startup_checks().
# This prevents sys.exit(1) when kubectl is not installed in the test environment.
# We start the mock, import the module, then stop so individual tests can control mocking.
_cli_mock = patch(
    "k8s_mcp_server.cli_executor.check_cli_installed",
    new_callable=AsyncMock,
    return_value=True,
)
_cli_mock.start()

# Force the server module to import (triggers run_startup_checks with our mock).
import k8s_mcp_server.server  # noqa: F401, E402

# Stop the mock so tests can set their own mocks for check_cli_installed.
_cli_mock.stop()

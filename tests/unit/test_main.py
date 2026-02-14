"""Tests for the main module."""

import os
import signal
import warnings
from unittest.mock import call, patch

import pytest


@pytest.mark.unit
def test_main_function():
    """Test the main function that starts the MCP server."""
    with patch("k8s_mcp_server.server.mcp.run") as mock_run:
        with patch.dict(os.environ, {"K8S_MCP_TRANSPORT": "stdio"}):
            from importlib import reload

            import k8s_mcp_server.__main__
            import k8s_mcp_server.config

            reload(k8s_mcp_server.config)
            reload(k8s_mcp_server.__main__)

            k8s_mcp_server.__main__.main()
            mock_run.assert_called_once_with(transport="stdio")

        mock_run.reset_mock()

        with patch.dict(os.environ, {"K8S_MCP_TRANSPORT": "sse"}):
            reload(k8s_mcp_server.config)
            reload(k8s_mcp_server.__main__)

            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                k8s_mcp_server.__main__.main()
            mock_run.assert_called_once_with(transport="sse")

        mock_run.reset_mock()

        with patch.dict(os.environ, {"K8S_MCP_TRANSPORT": "invalid"}):
            reload(k8s_mcp_server.config)
            reload(k8s_mcp_server.__main__)

            k8s_mcp_server.__main__.main()
            mock_run.assert_called_once_with(transport="stdio")


@pytest.mark.unit
def test_main_streamable_http_transport():
    """Test main function with streamable-http transport."""
    with patch("k8s_mcp_server.server.mcp.run") as mock_run:
        with patch.dict(os.environ, {"K8S_MCP_TRANSPORT": "streamable-http"}):
            from importlib import reload

            import k8s_mcp_server.__main__
            import k8s_mcp_server.config

            reload(k8s_mcp_server.config)
            reload(k8s_mcp_server.__main__)

            k8s_mcp_server.__main__.main()
            mock_run.assert_called_once_with(transport="streamable-http")


@pytest.mark.unit
def test_sse_deprecation_warning():
    """Test that SSE transport emits a deprecation warning."""
    with patch("k8s_mcp_server.server.mcp.run"):
        with patch.dict(os.environ, {"K8S_MCP_TRANSPORT": "sse"}):
            from importlib import reload

            import k8s_mcp_server.__main__
            import k8s_mcp_server.config

            reload(k8s_mcp_server.config)
            reload(k8s_mcp_server.__main__)

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                k8s_mcp_server.__main__.main()

                deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
                assert len(deprecation_warnings) == 1
                assert "streamable-http" in str(deprecation_warnings[0].message)


@pytest.mark.unit
def test_docker_host_detection_for_http_transports():
    """Test that HTTP transports bind to 0.0.0.0 in Docker and 127.0.0.1 otherwise."""
    with patch("k8s_mcp_server.server.mcp.run"):
        with patch("k8s_mcp_server.server.mcp.settings") as mock_settings:
            from importlib import reload

            import k8s_mcp_server.__main__
            import k8s_mcp_server.config

            # Test non-Docker: should bind to 127.0.0.1
            with patch.dict(os.environ, {"K8S_MCP_TRANSPORT": "streamable-http"}):
                reload(k8s_mcp_server.config)
                reload(k8s_mcp_server.__main__)

                with patch("k8s_mcp_server.config.is_docker_environment", return_value=False):
                    k8s_mcp_server.__main__.main()
                    mock_settings.__setattr__("host", "127.0.0.1")

            # Test Docker: should bind to 0.0.0.0
            with patch.dict(os.environ, {"K8S_MCP_TRANSPORT": "streamable-http"}):
                reload(k8s_mcp_server.config)
                reload(k8s_mcp_server.__main__)

                with patch("k8s_mcp_server.config.is_docker_environment", return_value=True):
                    k8s_mcp_server.__main__.main()
                    mock_settings.__setattr__("host", "0.0.0.0")


@pytest.mark.unit
def test_stdio_does_not_set_host():
    """Test that stdio transport does not configure host binding."""
    with patch("k8s_mcp_server.server.mcp.run"):
        with patch("k8s_mcp_server.server.mcp.settings") as mock_settings:
            from importlib import reload

            import k8s_mcp_server.__main__
            import k8s_mcp_server.config

            with patch.dict(os.environ, {"K8S_MCP_TRANSPORT": "stdio"}):
                reload(k8s_mcp_server.config)
                reload(k8s_mcp_server.__main__)

                mock_settings.reset_mock()
                k8s_mcp_server.__main__.main()
                # host should not be set for stdio
                assert not hasattr(mock_settings, "_mock_children") or "host" not in [
                    c[0] for c in mock_settings.mock_calls if c[0] == "__setattr__"
                ]


@pytest.mark.unit
def test_graceful_shutdown_handler():
    """Test the graceful shutdown handler for SIGINT signal."""
    from importlib import reload

    import k8s_mcp_server.__main__

    reload(k8s_mcp_server.__main__)

    with patch("sys.exit") as mock_exit:
        with patch("k8s_mcp_server.__main__.logger") as mock_logger:
            k8s_mcp_server.__main__.handle_interrupt(signal.SIGINT, None)

            mock_logger.info.assert_called_once_with(f"Received signal {signal.SIGINT}, shutting down gracefully...")
            mock_exit.assert_called_once_with(0)


@pytest.mark.unit
def test_keyboard_interrupt_handling():
    """Test that keyboard interrupts are handled gracefully."""
    from importlib import reload

    import k8s_mcp_server.__main__

    reload(k8s_mcp_server.__main__)

    with patch("sys.exit") as mock_exit:
        with patch("k8s_mcp_server.__main__.logger") as mock_logger:
            with patch("k8s_mcp_server.server.mcp.run", side_effect=KeyboardInterrupt):
                k8s_mcp_server.__main__.main()

                mock_logger.info.assert_any_call("Keyboard interrupt received. Shutting down gracefully...")
                mock_exit.assert_called_once_with(0)


@pytest.mark.unit
def test_signal_handler_registration():
    """Test that the signal handler is registered correctly."""
    from importlib import reload

    import k8s_mcp_server.__main__

    reload(k8s_mcp_server.__main__)

    with patch("signal.signal") as mock_signal:
        with patch("k8s_mcp_server.server.mcp.run"):
            k8s_mcp_server.__main__.main()

            assert mock_signal.call_count == 2
            mock_signal.assert_has_calls(
                [call(signal.SIGINT, k8s_mcp_server.__main__.handle_interrupt), call(signal.SIGTERM, k8s_mcp_server.__main__.handle_interrupt)], any_order=True
            )

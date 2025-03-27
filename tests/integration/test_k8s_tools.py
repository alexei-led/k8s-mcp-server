"""Integration tests for Kubernetes CLI tools.

These tests require a functioning Kubernetes cluster and installed CLI tools.
The tests connect to an existing Kubernetes cluster using the provided context,
rather than setting up a cluster during the tests.
"""

import json
import os
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest

from k8s_mcp_server.logging_utils import get_logger
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
from tests.helpers import create_test_pod_manifest, wait_for_pod_ready

# Configure logger for tests
logger = get_logger("integration_tests")


# Setup test reporting to capture test results for better diagnostics
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to extend test reporting with additional diagnostics."""
    outcome = yield
    result = outcome.get_result()

    # Store test results for test teardown
    if result.when == "call":
        item.test_outcome = result.outcome
        if result.outcome == "failed":
            item.test_failure_message = str(result.longrepr)

    return result


@pytest.fixture
def ensure_cluster_running(integration_cluster) -> Generator[str]:
    """Ensures cluster is running and returns context.

    This fixture simplifies access to the context provided by the integration_cluster fixture.
    The integration_cluster fixture now handles KWOK cluster creation by default.

    Returns:
        Current context name for use with kubectl commands
    """
    k8s_context = integration_cluster

    if not k8s_context:
        pytest.skip("No Kubernetes context available from integration_cluster fixture.")

    # Verify basic cluster functionality
    try:
        context_args = ["--context", k8s_context] if k8s_context else []
        # Explicitly get and use the KUBECONFIG from environment
        kubeconfig = os.environ.get("KUBECONFIG")
        kubeconfig_args = ["--kubeconfig", kubeconfig] if kubeconfig else []

        # Verify cluster connection with more verbose output and longer timeout
        cluster_cmd = ["kubectl", "cluster-info"] + context_args + kubeconfig_args
        result = subprocess.run(cluster_cmd, capture_output=True, text=True, timeout=10, check=True)
        logger.info(f"Using Kubernetes context: {k8s_context} with kubeconfig: {kubeconfig}")
        logger.debug(f"Cluster info: {result.stdout[:200]}...")

        # Check API server responsiveness with increased timeout
        api_cmd = ["kubectl", "api-resources", "--request-timeout=10s"] + context_args + kubeconfig_args
        api_result = subprocess.run(api_cmd, capture_output=True, timeout=10, check=True)
        logger.debug(f"API resources check successful with exit code: {api_result.returncode}")

        # Store context information for diagnostics
        yield k8s_context
    except subprocess.TimeoutExpired as e:
        logger.error(f"Timeout verifying cluster: {str(e)}")
        pytest.skip(f"Timeout verifying cluster: {str(e)}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error verifying cluster: {str(e)}, stderr: {e.stderr.decode() if e.stderr else 'None'}")
        pytest.skip(f"Error verifying cluster: {str(e)}, stderr: {e.stderr.decode() if e.stderr else 'None'}")
    except FileNotFoundError as e:
        logger.error(f"Required command not found: {str(e)}")
        pytest.skip(f"Required command not found: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error verifying cluster: {str(e)}")
        pytest.skip(f"Unexpected error verifying cluster: {str(e)}")


class _NamespaceManager:
    """Helper class for Kubernetes namespace management with retry logic and better cleanup.

    Note: This is not a test class and is prefixed with underscore to make that clear to pytest.
    """

    def __init__(self, k8s_context: str):
        """Initialize _NamespaceManager.

        Args:
            k8s_context: Kubernetes context name
        """
        self.context = k8s_context
        self.namespace: str | None = None
        self.kubeconfig = os.environ.get("KUBECONFIG")
        self.skip_cleanup = os.environ.get("K8S_SKIP_CLEANUP", "").lower() in ("true", "1", "yes")

    def get_kubectl_args(self) -> list[str]:
        """Get common kubectl arguments including context and kubeconfig.

        Returns:
            List of kubectl command line arguments
        """
        args = []
        if self.context:
            args.extend(["--context", self.context])
        if self.kubeconfig:
            args.extend(["--kubeconfig", self.kubeconfig])
        return args

    def create_namespace(self, max_retries: int = 3) -> str:
        """Create a Kubernetes namespace with retry logic.

        Args:
            max_retries: Maximum number of creation attempts

        Returns:
            Name of the created namespace

        Raises:
            RuntimeError: If namespace creation fails after retries
        """
        # Generate a unique namespace name
        self.namespace = f"k8s-mcp-test-{uuid.uuid4().hex[:8]}"
        logger.info(f"Creating test namespace: {self.namespace}")

        for attempt in range(1, max_retries + 1):
            try:
                cmd = ["kubectl", "create", "namespace", self.namespace] + self.get_kubectl_args()
                subprocess.run(cmd, capture_output=True, check=True, timeout=15)
                logger.info(f"Created test namespace: {self.namespace}")
                return self.namespace
            except subprocess.CalledProcessError as e:
                if b"AlreadyExists" in e.stderr:
                    logger.info(f"Namespace {self.namespace} already exists, reusing")
                    return self.namespace

                # Last attempt failed - raise error
                if attempt == max_retries:
                    error_msg = f"Failed to create namespace after {max_retries} attempts: {e.stderr.decode()}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e

                # Retry with a different namespace name
                self.namespace = f"k8s-mcp-test-{uuid.uuid4().hex[:8]}"
                logger.warning(f"Retrying with new namespace name: {self.namespace} (attempt {attempt + 1}/{max_retries})")
            except (subprocess.TimeoutExpired, Exception) as e:
                if attempt == max_retries:
                    error_msg = f"Failed to create namespace after {max_retries} attempts: {str(e)}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e
                logger.warning(f"Retrying namespace creation (attempt {attempt + 1}/{max_retries}): {str(e)}")
                time.sleep(1)  # Brief pause before retry

        # This should never be reached due to the exceptions above
        raise RuntimeError("Unexpected failure in create_namespace")

    def delete_namespace(self) -> bool:
        """Delete the Kubernetes namespace with error handling.

        Returns:
            True if deletion succeeded or was skipped, False if it failed
        """
        if not self.namespace:
            logger.warning("No namespace to delete")
            return True

        if self.skip_cleanup:
            logger.info(f"Skipping cleanup of namespace '{self.namespace}' as requested by K8S_SKIP_CLEANUP")
            return True

        logger.info(f"Cleaning up test namespace: {self.namespace}")
        try:
            # Use --wait=false to avoid blocking and force to ensure deletion
            cmd = ["kubectl", "delete", "namespace", self.namespace, "--wait=false", "--force"] + self.get_kubectl_args()
            subprocess.run(cmd, capture_output=True, check=False, timeout=15)
            logger.info(f"Namespace deletion initiated for: {self.namespace}")
            return True
        except Exception as e:
            logger.error(f"Error when cleaning up test namespace: {e}")
            return False


@pytest.fixture
def test_namespace(ensure_cluster_running, request) -> Generator[str]:
    """Create a test namespace and clean it up after tests with improved error handling.

    This fixture:
    1. Creates a dedicated test namespace in the test cluster (KWOK or real).
    2. Provides diagnostic information about namespace creation.
    3. Yields the namespace name for tests to use.
    4. Captures test results for conditional cleanup.
    5. Cleans up the namespace after tests complete (unless K8S_SKIP_CLEANUP=true).

    Args:
        ensure_cluster_running: Fixture that provides current K8s context.
        request: pytest request object for test metadata

    Environment Variables:
        K8S_SKIP_CLEANUP: If set to 'true', skip namespace cleanup after tests.

    Returns:
        The name of the test namespace.
    """
    k8s_context = ensure_cluster_running

    # Create namespace manager
    manager = _NamespaceManager(k8s_context)

    try:
        # Create namespace with retry logic
        namespace = manager.create_namespace()
        logger.info(f"Test using namespace: {namespace}")

        # Yield namespace to test
        yield namespace

        # Record test status for conditional cleanup
        test_failed = hasattr(request.node, "test_outcome") and request.node.test_outcome == "failed"
        if test_failed and hasattr(request.node, "test_failure_message"):
            logger.error(f"Test failed: {request.node.test_failure_message}")

        # Skip cleanup based on env var or on test failure if configured
        skip_on_failure = os.environ.get("K8S_SKIP_CLEANUP_ON_FAILURE", "").lower() in ("true", "1", "yes")
        if test_failed and skip_on_failure:
            logger.info(f"Skipping cleanup of namespace '{namespace}' due to test failure")
            return

        # Delete namespace
        manager.delete_namespace()

    except Exception as e:
        logger.error(f"Error in test_namespace fixture: {str(e)}")
        pytest.skip(f"Could not set up test namespace: {str(e)}")


@pytest.fixture
def k8s_resource_creator(ensure_cluster_running, test_namespace) -> Callable:
    """Fixture to create K8s resources for testing with proper cleanup.

    Args:
        ensure_cluster_running: Fixture providing K8s context
        test_namespace: Fixture providing test namespace

    Returns:
        Function to create resources from YAML
    """
    k8s_context = ensure_cluster_running
    created_resources = []

    def create_resource(yaml_content: str) -> dict[str, Any]:
        """Create a Kubernetes resource from YAML content.

        Args:
            yaml_content: YAML resource definition

        Returns:
            Dict with resource metadata

        Raises:
            RuntimeError: If resource creation fails
        """
        try:
            # Create a temporary file for the resource YAML
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as temp_file:
                temp_file.write(yaml_content)
                yaml_file = temp_file.name

            # Build kubectl command with proper context and namespace
            kubeconfig = os.environ.get("KUBECONFIG")
            cmd = ["kubectl", "apply", "-f", yaml_file, "--namespace", test_namespace, "--context", k8s_context]
            if kubeconfig:
                cmd.extend(["--kubeconfig", kubeconfig])

            # Apply the resource
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
            logger.info(f"Created resource: {result.stdout.strip()}")

            # Track created resource for potential cleanup
            if result.stdout:
                for line in result.stdout.splitlines():
                    if "/" in line and "created" in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            resource_type, name = parts[0].split("/")
                            created_resources.append({"type": resource_type, "name": name, "yaml_file": yaml_file})

            # Get resource details to return
            return {"status": "created", "stdout": result.stdout, "yaml_file": yaml_file}

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to create resource: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error creating resource: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    # Return the resource creator function
    yield create_resource

    # Clean up any created resources if not skipping cleanup
    skip_cleanup = os.environ.get("K8S_SKIP_CLEANUP", "").lower() in ("true", "1", "yes")
    if not skip_cleanup:
        for resource in reversed(created_resources):
            try:
                # Remove each created resource
                logger.info(f"Cleaning up resource: {resource['type']}/{resource['name']}")
                kubeconfig = os.environ.get("KUBECONFIG")
                cmd = [
                    "kubectl",
                    "delete",
                    resource["type"],
                    resource["name"],
                    "--namespace",
                    test_namespace,
                    "--context",
                    k8s_context,
                    "--wait=false",  # Don't wait for confirmation
                ]
                if kubeconfig:
                    cmd.extend(["--kubeconfig", kubeconfig])

                subprocess.run(cmd, capture_output=True, check=False, timeout=10)

                # Try to delete the temporary file
                try:
                    if "yaml_file" in resource and os.path.exists(resource["yaml_file"]):
                        os.unlink(resource["yaml_file"])
                except Exception:
                    pass

            except Exception as e:
                logger.warning(f"Error cleaning up resource {resource['type']}/{resource['name']}: {str(e)}")


@pytest.fixture
def diagnostics_dir() -> Generator[Path]:
    """Create a directory for test diagnostics.

    Returns:
        Path to the diagnostics directory
    """
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    diag_dir = Path(tempfile.gettempdir()) / f"k8s-mcp-test-diag-{timestamp}"
    diag_dir.mkdir(exist_ok=True)
    logger.info(f"Created test diagnostics directory: {diag_dir}")

    yield diag_dir

    # Keep diagnostics directory for post-test analysis
    logger.info(f"Test diagnostics available at: {diag_dir}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kubectl_version(ensure_cluster_running):
    """Test that kubectl version command works."""
    k8s_context = ensure_cluster_running
    result = await execute_kubectl(command=f"version --client --context={k8s_context}")

    assert result["status"] == "success"
    assert "Client Version" in result["output"]

    # Additional checks for diagnostics
    assert "execution_time" in result, "Execution time should be included in result"
    assert isinstance(result["execution_time"], float), "Execution time should be a float"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kubectl_get_pods(ensure_cluster_running, test_namespace, k8s_resource_creator, diagnostics_dir):
    """Test that kubectl can list pods in the test namespace."""
    k8s_context = ensure_cluster_running

    # Create a test pod using the resource creator
    pod_manifest = create_test_pod_manifest(namespace=test_namespace)
    k8s_resource_creator(pod_manifest)

    # Save the pod manifest for diagnostics
    manifest_path = diagnostics_dir / "test-pod.yaml"
    with open(manifest_path, "w") as f:
        f.write(pod_manifest)

    # Wait for pod creation
    logger.info("Waiting for pod to be in running state...")
    await wait_for_pod_ready(test_namespace, "test-pod", timeout=30)

    # Capture pod description for diagnostics
    try:
        kubeconfig = os.environ.get("KUBECONFIG")
        describe_cmd = ["kubectl", "describe", "pod", "test-pod", "--namespace", test_namespace, "--context", k8s_context]
        if kubeconfig:
            describe_cmd.extend(["--kubeconfig", kubeconfig])

        describe_result = subprocess.run(describe_cmd, capture_output=True, text=True, check=False)
        describe_path = diagnostics_dir / "test-pod-describe.txt"
        with open(describe_path, "w") as f:
            f.write(describe_result.stdout)
    except Exception as e:
        logger.warning(f"Failed to capture pod description: {str(e)}")

    # Test the function under test with various formats
    result_tests = []

    # Test 1: Basic pod listing
    result = await execute_kubectl(command=f"get pods --namespace={test_namespace} --context={k8s_context}")
    result_tests.append({"test": "basic", "result": result, "expected_status": "success", "expected_content": "test-pod"})

    # Test 2: JSON output
    json_result = await execute_kubectl(command=f"get pod test-pod -n {test_namespace} -o json --context={k8s_context}")
    result_tests.append({"test": "json", "result": json_result, "expected_status": "success", "expected_content": '"name": "test-pod"'})

    # Test 3: Wide output format
    wide_result = await execute_kubectl(command=f"get pods -n {test_namespace} -o wide --context={k8s_context}")
    result_tests.append({"test": "wide", "result": wide_result, "expected_status": "success", "expected_content": "test-pod"})

    # Save all test results for diagnostics
    results_path = diagnostics_dir / "kubectl-results.json"
    with open(results_path, "w") as f:
        json.dump(
            [
                {
                    "test": t["test"],
                    "status": t["result"]["status"],
                    "output": t["result"]["output"][:500],  # Limit output size
                    "success": (t["result"]["status"] == t["expected_status"] and t["expected_content"] in t["result"]["output"]),
                }
                for t in result_tests
            ],
            f,
            indent=2,
        )

    # Verify all test results
    for test in result_tests:
        assert test["result"]["status"] == test["expected_status"], f"{test['test']} test failed with status {test['result']['status']}"
        assert test["expected_content"] in test["result"]["output"], f"{test['test']} test failed: {test['expected_content']} not found in output"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_command_execution_edge_cases(ensure_cluster_running, test_namespace):
    """Test edge cases in command execution, including timeouts and errors."""
    k8s_context = ensure_cluster_running

    # Test 1: Command with very short timeout
    # The server catches the timeout exception and returns an error result
    timeout_result = await execute_kubectl(command=f"get pods --namespace={test_namespace} --watch --context={k8s_context}", timeout=1)
    assert timeout_result["status"] == "error"
    assert timeout_result["error"]["code"] == "TIMEOUT_ERROR"

    # Test 2: Invalid command
    invalid_result = await execute_kubectl(command="get invalid-resource-type")
    assert invalid_result["status"] == "error"
    assert "error" in invalid_result
    assert invalid_result["error"]["code"] == "EXECUTION_ERROR"

    # Test 3: Command with completely invalid flag (should error)
    invalid_flag_result = await execute_kubectl(command=f"get pods --invalid-flag=value --context={k8s_context}")
    assert invalid_flag_result["status"] == "error"
    assert invalid_flag_result["error"]["code"] == "EXECUTION_ERROR"

    # Note: We don't test non-existent namespaces because KWOK/KIND clusters
    # often just return an empty list for non-existent namespaces (success with empty output)
    # rather than an error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kubectl_help(ensure_cluster_running):
    """Test that kubectl help command works."""
    # Test with specific command
    result = await describe_kubectl(command="get")

    # Basic assertions
    assert hasattr(result, "help_text")
    assert "Display one or many resources" in result.help_text
    assert result.status == "success"

    # Test with no command parameter (general help)
    # Pass None explicitly rather than relying on default value
    general_result = await describe_kubectl(command=None)
    assert hasattr(general_result, "help_text")
    assert len(general_result.help_text) > 100  # Should have substantial content
    assert general_result.status == "success"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["get", "describe", "logs", "apply", "create"])
async def test_kubectl_help_commands(ensure_cluster_running, command):
    """Test kubectl help for various commands."""
    result = await describe_kubectl(command=command)
    assert result.status == "success"
    assert len(result.help_text) > 50  # Should have meaningful content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_commands(ensure_cluster_running, test_namespace, k8s_resource_creator):
    """Test executing multiple kubectl commands in sequence."""
    k8s_context = ensure_cluster_running

    # Create a test pod
    pod_manifest = create_test_pod_manifest(namespace=test_namespace)
    k8s_resource_creator(pod_manifest)

    # Wait for pod to be ready
    await wait_for_pod_ready(test_namespace, "test-pod", timeout=30)

    # Run multiple commands in sequence
    commands = [
        f"get pods -n {test_namespace} --context={k8s_context}",
        f"get pod test-pod -n {test_namespace} -o yaml --context={k8s_context}",
        f"describe pod test-pod -n {test_namespace} --context={k8s_context}",
    ]

    results = []
    for cmd in commands:
        result = await execute_kubectl(command=cmd)
        results.append({"command": cmd, "status": result["status"], "output_length": len(result["output"])})
        assert result["status"] == "success", f"Command failed: {cmd}"

    # Verify we have outputs from all commands
    assert len(results) == len(commands)
    for result in results:
        assert result["status"] == "success"
        assert result["output_length"] > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cli_tool_availability():
    """Test detection of installed CLI tools."""
    # Dictionary to track which tools should be tested
    tools = {
        "helm": {"command": "version", "execute_fn": execute_helm, "describe_fn": describe_helm, "found": False},
        "istioctl": {"command": "version", "execute_fn": execute_istioctl, "describe_fn": describe_istioctl, "found": False},
        "argocd": {"command": "version --client", "execute_fn": execute_argocd, "describe_fn": describe_argocd, "found": False},
    }

    # Check which tools are installed
    for tool, config in tools.items():
        try:
            cmd = [tool, "--help"]
            result = subprocess.run(cmd, capture_output=True, timeout=5, check=False)
            if result.returncode == 0 or result.returncode == 2:  # Some tools return 2 on --help
                config["found"] = True
                logger.info(f"{tool} is installed")
            else:
                logger.info(f"{tool} command failed with return code {result.returncode}")
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.info(f"{tool} is not installed")

    # Run tests only for installed tools
    for tool, config in tools.items():
        if config["found"]:
            # Test execution function
            execute_result = await config["execute_fn"](command=config["command"])
            assert execute_result["status"] == "success", f"{tool} execution failed"

            # Test help function - explicitly pass None for command
            help_result = await config["describe_fn"](command=None)
            assert help_result.status == "success", f"{tool} help request failed"
            assert len(help_result.help_text) > 100, f"{tool} help text is too short"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_helm_commands(ensure_cluster_running):
    """Test Helm commands if Helm is installed."""
    k8s_context = ensure_cluster_running

    # Skip if helm is not installed
    try:
        subprocess.run(["helm", "version"], capture_output=True, timeout=5, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.skip("helm is not installed")

    # Test Helm version
    version_result = await execute_helm(command=f"version --kube-context={k8s_context}")
    assert version_result["status"] == "success"
    assert "version.BuildInfo" in version_result["output"]

    # Test Helm list
    list_result = await execute_helm(command=f"list --kube-context={k8s_context}")
    assert list_result["status"] == "success"

    # Test Helm search
    search_result = await execute_helm(command=f"search repo stable --kube-context={k8s_context}")
    # We don't assert on content since search results depend on repository configuration
    assert "status" in search_result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_istioctl_commands(ensure_cluster_running):
    """Test istioctl commands if istioctl is installed."""
    k8s_context = ensure_cluster_running

    # Skip if istioctl is not installed
    try:
        subprocess.run(["istioctl", "version", "--remote=false"], capture_output=True, timeout=5, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.skip("istioctl is not installed")

    # Test istioctl version
    version_result = await execute_istioctl(command=f"version --remote=false --context={k8s_context}")
    assert version_result["status"] == "success"

    # Test basic istioctl command that should work on most versions
    analyze_result = await execute_istioctl(command=f"analyze --context={k8s_context}")
    assert analyze_result["status"] == "success"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_argocd_commands():
    """Test argocd commands if argocd is installed."""
    # Skip if argocd is not installed
    try:
        subprocess.run(["argocd", "version", "--client"], capture_output=True, timeout=5, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.skip("argocd is not installed")

    # Test argocd version
    version_result = await execute_argocd(command="version --client")
    assert version_result["status"] == "success"

    # Test argocd help - explicitly pass None for command
    help_result = await describe_argocd(command=None)
    assert help_result.status == "success"
    assert len(help_result.help_text) > 100

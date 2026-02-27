# K8s MCP Server — Development Guide

## Build & Test Commands

```bash
make install           # Install dependencies
make dev-install       # Install with dev deps
make test              # Unit tests only (default)
make test-all          # All tests (incl. integration)
make test-integration  # Integration tests (needs kubectl + cluster)
make lint              # ruff check src/ tests/
make format            # ruff format src/ tests/
```

Direct commands:

```bash
uv run pytest -q tests/unit/   # Fast unit tests
uvx ruff check src/ tests/     # Lint
python -m k8s_mcp_server        # Run server locally
```

## Architecture

### Server (`src/k8s_mcp_server/server.py`)

- 8 tools: 4 `execute_*` + 4 `describe_*`, all delegating to `_execute_tool_command()` / `_describe_tool_command()`
- CLI status checked at startup — tools gracefully error if CLI not installed
- Uses `FieldInfo` workaround for Pydantic Field defaults in timeout parameter
- `ToolAnnotations`: `readOnlyHint=True` for describe tools, `destructiveHint=True, openWorldHint=True` for execute tools

### Security (`src/k8s_mcp_server/security.py`)

- `validate_command()` — blocked patterns, required resource names for destructive ops
- `kubectl exec` restrictions (no interactive shells)
- Per-tool security rules validated before execution

### Errors (`src/k8s_mcp_server/errors.py`)

- Hierarchy: `K8sMCPError` → `CommandValidationError`, `CommandExecutionError`, `AuthenticationError`, `CommandTimeoutError`
- `create_error_result()` produces structured `CommandResult` with `ErrorDetails`
- Errors returned as tool results with `isError=true` (MCP spec compliant), not as JSON-RPC errors

### CLI Executor (`src/k8s_mcp_server/cli_executor.py`)

- `execute_command()` — asyncio subprocess, pipe support (`|` splitting), timeout
- `get_command_help()` — fetches `--help` output
- `check_cli_installed()` — startup validation

### Tools (`src/k8s_mcp_server/tools.py`)

- `CommandResult`: status, output, error (optional `ErrorDetails`), exit_code
- `CommandHelpResult`: help_text, status, error

### Config (`src/k8s_mcp_server/config.py`)

- `SUPPORTED_CLI_TOOLS = ["kubectl", "helm", "istioctl", "argocd"]`
- `MCP_TRANSPORT` env var: `stdio` (default), `sse`, `streamable-http`
- `DEFAULT_TIMEOUT = 300` seconds
- `INSTRUCTIONS` — system prompt for the MCP server

## Testing Patterns

- **Unit tests:** mock `asyncio.create_subprocess_exec`, fixtures in `conftest.py`
- **Integration:** requires real kubectl + cluster — skip with `pytest -m "not integration"`
- **Security tests:** `tests/unit/test_security.py` — covers all blocked commands
- **Error tests:** each error type has structured output assertion

## MCP Development Guidelines

### Adding a New CLI Tool (step-by-step)

1. Add tool name to `SUPPORTED_CLI_TOOLS` in `config.py`
2. Add `execute_<tool>()` in `server.py` — follow existing pattern, delegate to `_execute_tool_command()`
3. Add `describe_<tool>()` in `server.py` — follow existing help pattern
4. Add `ToolAnnotations` to both functions
5. Add security rules in `security.py` if needed
6. Add prompt templates in `prompts.py`
7. Add unit tests for both new tools
8. Update README

### Error Handling Pattern

- Catch `CommandValidationError`, `CommandExecutionError` etc. — return via `create_error_result()`
- Never raise protocol errors for input validation issues
- All tool functions accept `ctx: Context | None = None`

### Field Descriptions

- Use `pydantic.Field(description=...)` for schema generation in tool parameters

## Code Style

- **Line length:** 120 chars
- **Imports:** sorted by ruff (stdlib → third-party → local)
- **Type hints:** native Python (`list[str]`, not `List[str]`)
- **Docstrings:** Google-style for all public functions
- **Naming:** snake_case for functions/variables, PascalCase for classes

## Important

- **Default branch:** `master` (not main!)
- **Workflow:** branch → PR → CI green → squash merge
- **NEVER push directly to `master`**
- **Git commits:** do NOT add AI co-author trailers

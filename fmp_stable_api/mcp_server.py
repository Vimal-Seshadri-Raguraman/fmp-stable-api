# current/publish/fmp/mcp_server.py
"""
FMP MCP Server — exposes every FMP endpoint as an MCP tool.

Install:  pip install fmp[mcp]
Run:      fmp-mcp

Required env:
    FMP_API_KEY       your FMP API key
    FMP_CLIENT_TYPE   key tier (default: Premium)
    FMP_CUSTOM_LIMIT  requests/min for Enterprise or Custom keys
"""

import asyncio
import os
import sys

from .updater import load_endpoints
from .client import FMP
from .endpoints import safe_param_name


def _to_attr_name(category_key: str) -> str:
    """Convert a category key to its PascalCase attribute name."""
    return "".join(w.title() for w in category_key.replace("-", " ").split())


# Allowlist map: tool_name → (category_attr, func_name, allowed_param_set)
# Built once from the config and used for all dispatch — no getattr on caller input.
_TOOL_MAP: dict = {}


def _build_tools(config: dict, types) -> list:
    global _TOOL_MAP
    _TOOL_MAP = {}
    tools = []
    for category_key, category_endpoints in config.get("endpoints", {}).items():
        if not isinstance(category_endpoints, dict):
            continue
        attr_name = _to_attr_name(category_key)
        for endpoint_key, endpoint_cfg in category_endpoints.items():
            if not isinstance(endpoint_cfg, dict):
                continue
            func_name = endpoint_key.replace("-", "_").replace(" ", "_").lower()
            if func_name and func_name[0].isdigit():
                func_name = f"_{func_name}"
            tool_name = f"{attr_name}__{func_name}"
            required = endpoint_cfg.get("required_params", [])
            optional = endpoint_cfg.get("optional_params", [])
            allowed_params = frozenset(
                safe_param_name(p) for p in required + optional
            )
            properties = {p: {"type": "string"} for p in allowed_params}
            _TOOL_MAP[tool_name] = (attr_name, func_name, allowed_params)
            tools.append(types.Tool(
                name=tool_name,
                description=endpoint_cfg.get("description", f"{category_key}/{endpoint_key}"),
                inputSchema={
                    "type": "object",
                    "properties": properties,
                    "required": [safe_param_name(p) for p in required],
                },
            ))
    return tools


def handle_list_tools(config: dict, types) -> list:
    return _build_tools(config, types)


def handle_call_tool(name: str, arguments: dict, fmp_client: FMP, types) -> list:
    import json
    if name not in _TOOL_MAP:
        return [types.TextContent(type="text", text=f"Error: unknown tool '{name}'")]
    attr_name, func_name, allowed_params = _TOOL_MAP[name]
    # Filter arguments to the declared schema — reject any extra keys
    safe_args = {k: v for k, v in (arguments or {}).items() if k in allowed_params}
    try:
        category = getattr(fmp_client, attr_name)
        fn = getattr(category, func_name)
        result = fn(**safe_args)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


def main():
    try:
        import mcp.server.stdio
        import mcp.types as types
        from mcp.server import NotificationOptions, Server
        from mcp.server.models import InitializationOptions
    except ImportError:
        print("Error: run  pip install fmp[mcp]  to use the MCP server.", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        print("Error: FMP_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    client_type = os.environ.get("FMP_CLIENT_TYPE", "Premium")
    custom = os.environ.get("FMP_CUSTOM_LIMIT")
    fmp_client = FMP(
        client_type=client_type,
        client_key=api_key,
        custom_daily_limit=int(custom) if custom else None,
    )

    config = load_endpoints()
    server = Server("fmp")

    @server.list_tools()
    async def _handle_list_tools() -> list:
        return handle_list_tools(config, types)

    @server.call_tool()
    async def _handle_call_tool(name: str, arguments: dict) -> list:
        return handle_call_tool(name, arguments, fmp_client, types)

    async def _run():
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="fmp",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()

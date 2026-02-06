"""MCP Bridge — connects to MCP server via stdio transport."""

import json
import logging
import os
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

log = logging.getLogger("ollqd.client.bridge")


class MCPBridge:
    """Manages connection to an MCP server over stdio."""

    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None):
        # Forward parent environment to server subprocess
        server_env = {**os.environ, **(env or {})}
        self.params = StdioServerParameters(command=command, args=args, env=server_env)
        self._ctx = None
        self.session: ClientSession | None = None

    async def connect(self) -> "MCPBridge":
        self._ctx = stdio_client(self.params)
        self.read, self.write = await self._ctx.__aenter__()
        self.session = ClientSession(self.read, self.write)
        await self.session.__aenter__()
        await self.session.initialize()
        log.info("Connected to MCP server")
        return self

    async def close(self):
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self._ctx:
            await self._ctx.__aexit__(None, None, None)
        log.info("Disconnected from MCP server")

    async def list_tools(self) -> list:
        result = await self.session.list_tools()
        return result.tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        log.debug("Calling tool: %s(%s)", name, json.dumps(arguments, default=str)[:200])
        result = await self.session.call_tool(name, arguments)
        return result

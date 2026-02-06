"""RAG Loop Runner — orchestrates MCP tools + Ollama chat."""

import json
import logging
from typing import Any

from .mcp_bridge import MCPBridge
from .ollama_agent import OllamaToolAgent

log = logging.getLogger("ollqd.client.rag")


class RAGLoopRunner:
    """Runs the RAG loop: user query -> Ollama -> tool calls -> MCP server -> response."""

    def __init__(self, bridge: MCPBridge, agent: OllamaToolAgent, max_rounds: int = 6):
        self.bridge = bridge
        self.agent = agent
        self.max_rounds = max_rounds

    @staticmethod
    def mcp_tools_to_ollama(mcp_tools: list) -> list[dict]:
        """Convert MCP tool definitions to Ollama tool-calling format."""
        out = []
        for t in mcp_tools:
            out.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                },
            })
        return out

    async def run(self, user_prompt: str, system_prompt: str | None = None) -> str:
        """Execute the RAG loop for a single user prompt."""
        mcp_tools = await self.bridge.list_tools()
        ollama_tools = self.mcp_tools_to_ollama(mcp_tools)

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        for round_num in range(self.max_rounds):
            log.debug("RAG round %d/%d", round_num + 1, self.max_rounds)

            resp = await self.agent.chat(messages, ollama_tools)
            msg = resp.get("message", {})
            messages.append(msg)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return msg.get("content", "")

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = tc["function"].get("arguments", {})
                if isinstance(fn_args, str):
                    fn_args = json.loads(fn_args) if fn_args else {}

                log.info("Tool call: %s(%s)", fn_name, json.dumps(fn_args, default=str)[:200])

                try:
                    tool_result = await self.bridge.call_tool(fn_name, fn_args)
                    # Extract text content from MCP result
                    if hasattr(tool_result, "content") and tool_result.content:
                        result_text = tool_result.content[0].text if tool_result.content else "{}"
                    else:
                        result_text = json.dumps(tool_result, default=str)
                except Exception as e:
                    result_text = json.dumps({"error": str(e)})

                messages.append({
                    "role": "tool",
                    "content": result_text,
                })

        return "Reached maximum tool-calling rounds without a final answer."

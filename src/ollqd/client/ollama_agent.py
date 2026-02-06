"""Ollama chat agent with tool-calling support."""

import logging

import httpx

log = logging.getLogger("ollqd.client.agent")


class OllamaToolAgent:
    """Sends chat messages to Ollama with tool definitions."""

    def __init__(self, host: str, model: str, timeout: float = 120.0):
        self.host = host.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(timeout=timeout)

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Send a chat request to Ollama with optional tools."""
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        if tools:
            payload["tools"] = tools

        resp = await self._client.post(f"{self.host}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()

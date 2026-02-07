"""Async wrapper for all Ollama REST API endpoints."""

import json
import logging
from typing import AsyncIterator, Union

import httpx

log = logging.getLogger("ollqd.web.ollama")


class OllamaService:
    """Wraps all Ollama REST API endpoints with async httpx."""

    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    # ── Models ──────────────────────────────────────────────

    async def list_models(self) -> dict:
        resp = await self.client.get("/api/tags")
        resp.raise_for_status()
        return resp.json()

    async def show_model(self, name: str) -> dict:
        resp = await self.client.post("/api/show", json={"name": name})
        resp.raise_for_status()
        return resp.json()

    async def copy_model(self, source: str, destination: str) -> dict:
        resp = await self.client.post(
            "/api/copy", json={"source": source, "destination": destination}
        )
        resp.raise_for_status()
        return {"status": "ok"}

    async def delete_model(self, name: str) -> dict:
        resp = await self.client.request(
            "DELETE", "/api/delete", json={"name": name}
        )
        resp.raise_for_status()
        return {"status": "ok"}

    async def pull_model_stream(self, name: str) -> AsyncIterator[dict]:
        async with self.client.stream(
            "POST", "/api/pull", json={"name": name, "stream": True}
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    yield json.loads(line)

    # ── Running ─────────────────────────────────────────────

    async def ps(self) -> dict:
        resp = await self.client.get("/api/ps")
        resp.raise_for_status()
        return resp.json()

    # ── Generation ──────────────────────────────────────────

    async def chat_stream(
        self, model: str, messages: list[dict], **kwargs
    ) -> AsyncIterator[str]:
        async with self.client.stream(
            "POST",
            "/api/chat",
            json={"model": model, "messages": messages, "stream": True, **kwargs},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content

    async def generate_stream(
        self, model: str, prompt: str, **kwargs
    ) -> AsyncIterator[str]:
        async with self.client.stream(
            "POST",
            "/api/generate",
            json={"model": model, "prompt": prompt, "stream": True, **kwargs},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    if data.get("response"):
                        yield data["response"]

    async def caption_image(self, model: str, image_base64: str, prompt: str) -> str:
        """Caption an image using a vision model via /api/chat with images array."""
        resp = await self.client.post(
            "/api/chat",
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_base64],
                    }
                ],
                "stream": False,
            },
            timeout=180.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    async def embed(self, model: str, input_text: Union[str, list[str]]) -> dict:
        resp = await self.client.post(
            "/api/embed", json={"model": model, "input": input_text}
        )
        resp.raise_for_status()
        return resp.json()

    # ── System ──────────────────────────────────────────────

    async def version(self) -> dict:
        resp = await self.client.get("/api/version")
        resp.raise_for_status()
        return resp.json()

    async def is_healthy(self) -> bool:
        try:
            resp = await self.client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()

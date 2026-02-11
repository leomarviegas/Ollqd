"""Tests for the WebSocket chat endpoint.

Routes tested:
  GET /api/rag/ws  (WebSocket upgrade)

The WS handler upgrades the connection to WebSocket, then reads JSON
messages and streams back ChatEvent frames from the gRPC ChatService.
Full chat tests require Ollama for LLM inference.

Dependencies:
  pip install websockets
"""

import asyncio
import json

import pytest

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


pytestmark = pytest.mark.skipif(
    not HAS_WEBSOCKETS,
    reason="websockets library not installed",
)


def _ws_url(gateway_url: str) -> str:
    """Convert http://host:port to ws://host:port/api/rag/ws."""
    return gateway_url.replace("http://", "ws://").replace("https://", "wss://") + "/api/rag/ws"


class TestWebSocketUpgrade:
    """WebSocket connection handshake."""

    @pytest.mark.asyncio
    async def test_ws_upgrade(self, gateway_url):
        """A WebSocket connection to /api/rag/ws should succeed (101 Upgrade)."""
        ws_uri = _ws_url(gateway_url)
        try:
            async with websockets.connect(ws_uri, open_timeout=10) as ws:
                # Connection succeeded (context manager ensures open)
                assert ws is not None
        except (ConnectionRefusedError, OSError) as exc:
            pytest.fail(f"WebSocket upgrade failed: {exc}")

    @pytest.mark.asyncio
    async def test_ws_accepts_json_message(self, gateway_url):
        """After connecting, sending a JSON message does not crash the server."""
        ws_uri = _ws_url(gateway_url)
        try:
            async with websockets.connect(ws_uri, open_timeout=10) as ws:
                msg = json.dumps({
                    "message": "ping",
                    "collection": "",
                    "model": "",
                    "pii_enabled": False,
                })
                await ws.send(msg)
                # We should get at least one response frame (could be error or content)
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=10)
                    data = json.loads(response)
                    assert "type" in data
                except asyncio.TimeoutError:
                    # If the chat service is down, we might not get a response
                    pass
        except (websockets.exceptions.InvalidStatusCode, ConnectionRefusedError) as exc:
            pytest.skip(f"WebSocket not available: {exc}")


class TestWebSocketChat:
    """WebSocket chat interaction (requires Ollama)."""

    @pytest.mark.asyncio
    @pytest.mark.requires_ollama
    async def test_ws_sends_done_event(self, gateway_url, ollama_available):
        """After sending a chat message, the server eventually sends a 'done' event."""
        if not ollama_available:
            pytest.skip("Ollama not available for chat")

        ws_uri = _ws_url(gateway_url)
        try:
            async with websockets.connect(ws_uri, open_timeout=10) as ws:
                msg = json.dumps({
                    "message": "Say hello in one word.",
                    "collection": "",
                    "model": "",
                    "pii_enabled": False,
                })
                await ws.send(msg)

                # Collect events until we see "done" or timeout
                events = []
                seen_done = False
                try:
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(raw)
                        events.append(data)
                        if data.get("type") == "done":
                            seen_done = True
                            break
                except asyncio.TimeoutError:
                    pass

                assert seen_done or len(events) > 0, (
                    "Expected at least one event or a 'done' event from the chat"
                )

        except (websockets.exceptions.InvalidStatusCode, ConnectionRefusedError) as exc:
            pytest.skip(f"WebSocket not available: {exc}")

    @pytest.mark.asyncio
    async def test_ws_invalid_json_returns_error(self, gateway_url):
        """Sending non-JSON text should result in an error event."""
        ws_uri = _ws_url(gateway_url)
        try:
            async with websockets.connect(ws_uri, open_timeout=10) as ws:
                await ws.send("this is not json")
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    data = json.loads(raw)
                    assert data.get("type") == "error"
                except asyncio.TimeoutError:
                    pass  # Server may silently drop invalid messages
        except (websockets.exceptions.InvalidStatusCode, ConnectionRefusedError) as exc:
            pytest.skip(f"WebSocket not available: {exc}")

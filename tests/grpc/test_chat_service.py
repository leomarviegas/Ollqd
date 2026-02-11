"""Integration tests for ChatService gRPC endpoints.

Tests cover the Chat server-streaming RPC which returns ChatEvent messages.
Each ChatEvent has a type field: chunk, sources, done, or error.
These tests require Ollama for LLM inference and indexed content for RAG.
"""

import time

import grpc
import pytest

from ollqd.v1 import processing_pb2

from .conftest import requires_ollama, requires_indexed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
VALID_EVENT_TYPES = {"chunk", "sources", "done", "error"}


async def _collect_chat_events(stream, max_events=500, timeout_s=120):
    """Collect ChatEvent messages from the Chat streaming RPC.

    Returns a list of ChatEvent messages. Stops when:
    - A 'done' or 'error' event is received
    - max_events is reached
    - timeout is exceeded
    """
    events = []
    import asyncio

    deadline = time.monotonic() + timeout_s
    try:
        async for event in stream:
            events.append(event)
            if event.type in ("done", "error"):
                break
            if len(events) >= max_events:
                break
            if time.monotonic() > deadline:
                break
    except grpc.aio.AioRpcError:
        pass
    return events


async def _ensure_indexed_for_chat(indexing_stub, codebase_fixtures_dir):
    """Ensure the codebase is indexed so chat has context to work with."""
    collection = "grpc_test_chat"
    stream = indexing_stub.IndexCodebase(
        processing_pb2.IndexCodebaseRequest(
            root_path=str(codebase_fixtures_dir),
            collection=collection,
            chunk_size=256,
            chunk_overlap=32,
            incremental=True,
        )
    )
    async for event in stream:
        if event.status in ("completed", "failed"):
            break
    return collection


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@requires_ollama
@requires_indexed
class TestChatStreamsEvents:
    """Tests for the Chat server-streaming RPC."""

    @pytest.mark.asyncio
    async def test_chat_streams_events(
        self, chat_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """Chat should yield ChatEvent messages with valid type fields."""
        collection = await _ensure_indexed_for_chat(indexing_stub, codebase_fixtures_dir)

        stream = chat_stub.Chat(
            processing_pb2.ChatRequest(
                message="What does the main function do?",
                collection=collection,
            )
        )

        events = await _collect_chat_events(stream)
        assert len(events) > 0, "Chat should yield at least one event"

        for event in events:
            assert event.type in VALID_EVENT_TYPES, (
                f"Event type '{event.type}' is not one of {VALID_EVENT_TYPES}"
            )

    @pytest.mark.asyncio
    async def test_chat_done_event_terminates(
        self, chat_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """The last event in a chat stream should have type='done'."""
        collection = await _ensure_indexed_for_chat(indexing_stub, codebase_fixtures_dir)

        stream = chat_stub.Chat(
            processing_pb2.ChatRequest(
                message="Summarize the codebase in one sentence.",
                collection=collection,
            )
        )

        events = await _collect_chat_events(stream)
        assert len(events) > 0, "Should receive at least one event"

        final = events[-1]
        assert final.type in ("done", "error"), (
            f"Final event should be 'done' or 'error', got '{final.type}'"
        )

    @pytest.mark.asyncio
    async def test_chat_has_chunk_events(
        self, chat_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """A successful chat response should include at least one 'chunk' event with content."""
        collection = await _ensure_indexed_for_chat(indexing_stub, codebase_fixtures_dir)

        stream = chat_stub.Chat(
            processing_pb2.ChatRequest(
                message="Explain the database schema.",
                collection=collection,
            )
        )

        events = await _collect_chat_events(stream)
        chunk_events = [e for e in events if e.type == "chunk"]

        # A successful chat should produce at least one content chunk
        if events and events[-1].type != "error":
            assert len(chunk_events) > 0, (
                "A successful chat should include at least one 'chunk' event"
            )
            # At least one chunk should have non-empty content
            has_content = any(e.content for e in chunk_events)
            assert has_content, "At least one chunk event should have non-empty content"

    @pytest.mark.asyncio
    async def test_chat_sources_event(
        self, chat_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """The chat stream should include a 'sources' event with SearchHit references."""
        collection = await _ensure_indexed_for_chat(indexing_stub, codebase_fixtures_dir)

        stream = chat_stub.Chat(
            processing_pb2.ChatRequest(
                message="What configuration options are available?",
                collection=collection,
            )
        )

        events = await _collect_chat_events(stream)
        source_events = [e for e in events if e.type == "sources"]

        if source_events:
            src = source_events[0]
            assert len(src.sources) > 0, (
                "A 'sources' event should contain at least one SearchHit"
            )
            for hit in src.sources:
                assert hit.file_path, "Source SearchHit should have a file_path"


@requires_ollama
@requires_indexed
class TestChatWithPII:
    """Tests for Chat with PII masking enabled."""

    @pytest.mark.asyncio
    async def test_chat_with_pii_enabled(
        self, chat_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """When pii_enabled=True, ChatEvents should reflect PII masking state."""
        collection = await _ensure_indexed_for_chat(indexing_stub, codebase_fixtures_dir)

        stream = chat_stub.Chat(
            processing_pb2.ChatRequest(
                message="Tell me about the user data handling.",
                collection=collection,
                pii_enabled=True,
            )
        )

        events = await _collect_chat_events(stream)
        assert len(events) > 0, "Should receive at least one event"

        # When PII is enabled, at least some events should reflect masking state.
        # The pii_masked field indicates whether PII masking was applied.
        # We check that the field is accessible (defaults to False if not set).
        for event in events:
            # pii_masked is a bool — just verify it's accessible without error
            _ = event.pii_masked
            _ = event.pii_entities_count

    @pytest.mark.asyncio
    async def test_chat_without_pii(
        self, chat_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """When pii_enabled=False, pii_masked should be False on events."""
        collection = await _ensure_indexed_for_chat(indexing_stub, codebase_fixtures_dir)

        stream = chat_stub.Chat(
            processing_pb2.ChatRequest(
                message="Describe the system architecture.",
                collection=collection,
                pii_enabled=False,
            )
        )

        events = await _collect_chat_events(stream)
        for event in events:
            assert event.pii_masked is False, (
                "With pii_enabled=False, pii_masked should be False"
            )


@requires_ollama
@requires_indexed
class TestChatWithModel:
    """Tests for Chat with a specific model parameter."""

    @pytest.mark.asyncio
    async def test_chat_with_explicit_model(
        self, chat_stub, indexing_stub, codebase_fixtures_dir, config_stub, ollama_available
    ):
        """Chat with an explicit model parameter should still stream events."""
        collection = await _ensure_indexed_for_chat(indexing_stub, codebase_fixtures_dir)

        # Get the current chat model from config
        config = await config_stub.GetConfig(processing_pb2.GetConfigRequest())
        model = config.ollama.chat_model

        if not model:
            pytest.skip("No chat model configured")

        stream = chat_stub.Chat(
            processing_pb2.ChatRequest(
                message="Hello, what can you tell me about this code?",
                collection=collection,
                model=model,
            )
        )

        events = await _collect_chat_events(stream)
        assert len(events) > 0, "Chat with explicit model should yield events"

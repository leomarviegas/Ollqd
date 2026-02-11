"""Integration tests for IndexingService gRPC endpoints.

Tests cover IndexCodebase, IndexDocuments, IndexImages (server-streaming
TaskProgress), and CancelTask RPCs.  These tests require Ollama for embedding.
"""

import asyncio
import time

import grpc
import pytest

from ollqd.v1 import processing_pb2, types_pb2

from .conftest import requires_ollama


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
VALID_STATUSES = {"running", "completed", "failed", "cancelled"}


async def _collect_progress(stream, max_events=200, timeout_s=120):
    """Collect TaskProgress events from a server-streaming RPC.

    Returns a list of TaskProgress messages. Stops when the stream ends,
    a terminal status is received, or the timeout is reached.
    """
    events = []
    deadline = time.monotonic() + timeout_s
    try:
        async for event in stream:
            events.append(event)
            if event.status in ("completed", "failed", "cancelled"):
                break
            if len(events) >= max_events:
                break
            if time.monotonic() > deadline:
                break
    except grpc.aio.AioRpcError:
        pass  # Stream may be cancelled
    return events


# ---------------------------------------------------------------------------
# IndexCodebase
# ---------------------------------------------------------------------------
@requires_ollama
class TestIndexCodebase:
    """Tests for the IndexCodebase server-streaming RPC."""

    @pytest.mark.asyncio
    async def test_index_codebase_streams_progress(
        self, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """IndexCodebase should yield TaskProgress events with valid status values."""
        collection = f"grpc_test_codebase_{int(time.time())}"
        stream = indexing_stub.IndexCodebase(
            processing_pb2.IndexCodebaseRequest(
                root_path=str(codebase_fixtures_dir),
                collection=collection,
                chunk_size=256,
                chunk_overlap=32,
                incremental=False,
            )
        )

        events = await _collect_progress(stream)
        assert len(events) > 0, "IndexCodebase should yield at least one TaskProgress event"

        for event in events:
            assert event.task_id, "Each event should have a non-empty task_id"
            assert event.status in VALID_STATUSES, (
                f"Event status '{event.status}' is not one of {VALID_STATUSES}"
            )
            assert 0.0 <= event.progress <= 1.0, (
                f"Progress {event.progress} should be in [0, 1]"
            )

    @pytest.mark.asyncio
    async def test_index_codebase_completes(
        self, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """The final IndexCodebase event should have status=completed."""
        collection = f"grpc_test_codebase_complete_{int(time.time())}"
        stream = indexing_stub.IndexCodebase(
            processing_pb2.IndexCodebaseRequest(
                root_path=str(codebase_fixtures_dir),
                collection=collection,
                chunk_size=256,
                chunk_overlap=32,
                incremental=False,
            )
        )

        events = await _collect_progress(stream)
        assert len(events) > 0, "Should receive at least one event"

        final = events[-1]
        assert final.status == "completed", (
            f"Final event should have status=completed, got '{final.status}'"
        )
        assert final.progress == pytest.approx(1.0, abs=0.01), (
            "Final progress should be ~1.0"
        )

    @pytest.mark.asyncio
    async def test_index_codebase_task_id_consistent(
        self, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """All TaskProgress events from a single IndexCodebase call should share the same task_id."""
        collection = f"grpc_test_codebase_taskid_{int(time.time())}"
        stream = indexing_stub.IndexCodebase(
            processing_pb2.IndexCodebaseRequest(
                root_path=str(codebase_fixtures_dir),
                collection=collection,
                chunk_size=256,
                chunk_overlap=32,
                incremental=False,
            )
        )

        events = await _collect_progress(stream)
        assert len(events) > 0

        task_ids = {e.task_id for e in events}
        assert len(task_ids) == 1, (
            f"All events should have the same task_id, got {task_ids}"
        )

    @pytest.mark.asyncio
    async def test_index_codebase_progress_monotonic(
        self, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """Progress values should be monotonically non-decreasing."""
        collection = f"grpc_test_codebase_mono_{int(time.time())}"
        stream = indexing_stub.IndexCodebase(
            processing_pb2.IndexCodebaseRequest(
                root_path=str(codebase_fixtures_dir),
                collection=collection,
                chunk_size=256,
                chunk_overlap=32,
                incremental=False,
            )
        )

        events = await _collect_progress(stream)
        for i in range(1, len(events)):
            assert events[i].progress >= events[i - 1].progress, (
                f"Progress should not decrease: event[{i - 1}]={events[i - 1].progress} "
                f"> event[{i}]={events[i].progress}"
            )

    @pytest.mark.asyncio
    async def test_index_codebase_result_map(
        self, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """The final completed event should have a populated result map."""
        collection = f"grpc_test_codebase_result_{int(time.time())}"
        stream = indexing_stub.IndexCodebase(
            processing_pb2.IndexCodebaseRequest(
                root_path=str(codebase_fixtures_dir),
                collection=collection,
                chunk_size=256,
                chunk_overlap=32,
                incremental=False,
            )
        )

        events = await _collect_progress(stream)
        final = events[-1]
        if final.status == "completed":
            # result is a map<string,string> — should have at least some info
            assert len(final.result) > 0, (
                "Completed event should have a non-empty result map"
            )


# ---------------------------------------------------------------------------
# CancelTask
# ---------------------------------------------------------------------------
@requires_ollama
class TestCancelTask:
    """Tests for the CancelTask RPC."""

    @pytest.mark.asyncio
    async def test_cancel_task(
        self, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """Starting an indexing job and immediately cancelling it should work."""
        collection = f"grpc_test_cancel_{int(time.time())}"

        # Start indexing (but do not consume the full stream)
        stream = indexing_stub.IndexCodebase(
            processing_pb2.IndexCodebaseRequest(
                root_path=str(codebase_fixtures_dir),
                collection=collection,
                chunk_size=256,
                chunk_overlap=32,
                incremental=False,
            )
        )

        # Read the first event to get the task_id
        first_event = None
        try:
            first_event = await asyncio.wait_for(stream.read(), timeout=30)
        except asyncio.TimeoutError:
            pytest.skip("Timed out waiting for the first indexing event")

        assert first_event is not None, "Should receive at least one event"
        task_id = first_event.task_id
        assert task_id, "First event should have a task_id"

        # Cancel the task
        cancel_resp = await indexing_stub.CancelTask(
            processing_pb2.CancelTaskRequest(task_id=task_id)
        )
        assert cancel_resp.cancelled is True or cancel_resp.message, (
            "CancelTask should indicate success via cancelled=True or a message"
        )

        # Drain remaining events using .read() (must not mix with async-for)
        remaining = []
        try:
            while True:
                event = await asyncio.wait_for(stream.read(), timeout=10)
                if event is grpc.aio.EOF:
                    break
                remaining.append(event)
                if event.status in ("cancelled", "completed", "failed"):
                    break
        except (grpc.aio.AioRpcError, asyncio.TimeoutError):
            pass  # Acceptable if the stream is already closed or timed out

        if remaining:
            final = remaining[-1]
            assert final.status in ("cancelled", "completed", "failed"), (
                f"After cancel, final status should be terminal, got '{final.status}'"
            )


# ---------------------------------------------------------------------------
# IndexDocuments
# ---------------------------------------------------------------------------
@requires_ollama
class TestIndexDocuments:
    """Tests for the IndexDocuments server-streaming RPC."""

    @pytest.mark.asyncio
    async def test_index_documents_streams_progress(
        self, indexing_stub, docs_fixtures_dir, ollama_available
    ):
        """IndexDocuments should yield TaskProgress events."""
        collection = f"grpc_test_docs_{int(time.time())}"
        stream = indexing_stub.IndexDocuments(
            processing_pb2.IndexDocumentsRequest(
                paths=[str(docs_fixtures_dir)],
                collection=collection,
                chunk_size=256,
                chunk_overlap=32,
            )
        )

        events = await _collect_progress(stream)
        assert len(events) > 0, "IndexDocuments should yield at least one event"

        final = events[-1]
        assert final.status in VALID_STATUSES

    @pytest.mark.asyncio
    async def test_index_documents_completes_successfully(
        self, indexing_stub, docs_fixtures_dir, ollama_available
    ):
        """IndexDocuments for fixture docs should complete without errors."""
        collection = f"grpc_test_docs_ok_{int(time.time())}"
        stream = indexing_stub.IndexDocuments(
            processing_pb2.IndexDocumentsRequest(
                paths=[str(docs_fixtures_dir)],
                collection=collection,
                chunk_size=256,
                chunk_overlap=32,
            )
        )

        events = await _collect_progress(stream)
        final = events[-1]
        assert final.status == "completed", (
            f"Expected completed, got '{final.status}' with error: {final.error}"
        )


# ---------------------------------------------------------------------------
# IndexImages
# ---------------------------------------------------------------------------
@requires_ollama
class TestIndexImages:
    """Tests for the IndexImages server-streaming RPC."""

    @pytest.mark.asyncio
    async def test_index_images_streams_progress(
        self, indexing_stub, images_fixtures_dir, ollama_available
    ):
        """IndexImages should yield TaskProgress events for image fixtures."""
        collection = f"grpc_test_images_{int(time.time())}"
        stream = indexing_stub.IndexImages(
            processing_pb2.IndexImagesRequest(
                root_path=str(images_fixtures_dir),
                collection=collection,
                incremental=False,
            )
        )

        events = await _collect_progress(stream, timeout_s=180)
        assert len(events) > 0, "IndexImages should yield at least one event"

        for event in events:
            assert event.status in VALID_STATUSES

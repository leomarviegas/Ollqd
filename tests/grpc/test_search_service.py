"""Integration tests for SearchService gRPC endpoints.

Tests cover Search and SearchCollection RPCs. Some tests require
indexed content (via IndexCodebase) and Ollama for embeddings.
"""

import time

import grpc
import pytest

from ollqd.v1 import processing_pb2

from .conftest import requires_indexed, requires_ollama


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _ensure_indexed(indexing_stub, codebase_fixtures_dir):
    """Index the codebase fixtures if not already done. Returns the collection name."""
    collection = "grpc_test_search"
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
# Tests — empty collection
# ---------------------------------------------------------------------------
class TestSearchEmptyCollection:
    """Tests for search on a collection that does not exist or is empty."""

    @pytest.mark.asyncio
    async def test_search_empty_collection(self, search_stub, ollama_available):
        """Searching a non-existent collection should return empty results or an error."""
        nonexistent = f"nonexistent_{int(time.time())}"
        try:
            resp = await search_stub.SearchCollection(
                processing_pb2.SearchCollectionRequest(
                    collection=nonexistent,
                    query="test query",
                    top_k=5,
                )
            )
            # If the server returns a response, results should be empty
            assert len(resp.results) == 0, (
                "Search on a non-existent collection should return zero results"
            )
        except grpc.aio.AioRpcError as e:
            # NOT_FOUND or similar is acceptable for a missing collection
            assert e.code() in (
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.INVALID_ARGUMENT,
                grpc.StatusCode.INTERNAL,
            ), f"Unexpected gRPC error code: {e.code()}"


# ---------------------------------------------------------------------------
# Tests — with indexed content
# ---------------------------------------------------------------------------
@requires_ollama
@requires_indexed
class TestSearchWithContent:
    """Tests for search after indexing fixture data."""

    @pytest.mark.asyncio
    async def test_search_returns_hits(
        self, search_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """After indexing, a relevant query should return SearchHit results."""
        collection = await _ensure_indexed(indexing_stub, codebase_fixtures_dir)

        resp = await search_stub.SearchCollection(
            processing_pb2.SearchCollectionRequest(
                collection=collection,
                query="function handler",
                top_k=5,
            )
        )

        assert len(resp.results) > 0, "Search should return at least one hit"
        assert resp.collection == collection

        # Verify SearchHit fields
        hit = resp.results[0]
        assert hit.score > 0.0, "Hit score should be positive"
        assert hit.file_path, "Hit should have a file_path"
        assert hit.content, "Hit should have content"

    @pytest.mark.asyncio
    async def test_search_respects_top_k(
        self, search_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """The number of returned hits should not exceed top_k."""
        collection = await _ensure_indexed(indexing_stub, codebase_fixtures_dir)

        top_k = 2
        resp = await search_stub.SearchCollection(
            processing_pb2.SearchCollectionRequest(
                collection=collection,
                query="import",
                top_k=top_k,
            )
        )

        assert len(resp.results) <= top_k, (
            f"Should return at most {top_k} results, got {len(resp.results)}"
        )

    @pytest.mark.asyncio
    async def test_search_hits_ordered_by_score(
        self, search_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """Search results should be ordered by descending score."""
        collection = await _ensure_indexed(indexing_stub, codebase_fixtures_dir)

        resp = await search_stub.SearchCollection(
            processing_pb2.SearchCollectionRequest(
                collection=collection,
                query="database schema",
                top_k=10,
            )
        )

        if len(resp.results) >= 2:
            scores = [hit.score for hit in resp.results]
            for i in range(1, len(scores)):
                assert scores[i] <= scores[i - 1], (
                    f"Results should be sorted by descending score: "
                    f"score[{i - 1}]={scores[i - 1]} < score[{i}]={scores[i]}"
                )

    @pytest.mark.asyncio
    async def test_search_query_echoed(
        self, search_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """The SearchResponse should echo back the original query string."""
        collection = await _ensure_indexed(indexing_stub, codebase_fixtures_dir)

        query_text = "configuration yaml"
        resp = await search_stub.SearchCollection(
            processing_pb2.SearchCollectionRequest(
                collection=collection,
                query=query_text,
                top_k=3,
            )
        )

        assert resp.query == query_text, (
            f"Response query should echo '{query_text}', got '{resp.query}'"
        )


# ---------------------------------------------------------------------------
# Tests — Search RPC (uses default collection)
# ---------------------------------------------------------------------------
@requires_ollama
@requires_indexed
class TestSearchDefaultCollection:
    """Tests for the Search RPC which uses the configured default collection."""

    @pytest.mark.asyncio
    async def test_search_default_collection(
        self, search_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """The Search RPC should use the default collection when no collection is specified."""
        # Make sure something is indexed first
        await _ensure_indexed(indexing_stub, codebase_fixtures_dir)

        try:
            resp = await search_stub.Search(
                processing_pb2.SearchRequest(
                    query="main function",
                    top_k=3,
                )
            )
            # If it succeeds, verify the response structure
            assert resp.query == "main function"
        except grpc.aio.AioRpcError as e:
            # If default collection is not configured, this may fail gracefully
            assert e.code() in (
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.FAILED_PRECONDITION,
                grpc.StatusCode.INTERNAL,
            ), f"Unexpected error code: {e.code()}"

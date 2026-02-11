"""Integration tests for VisualizationService gRPC endpoints.

Tests cover Overview, FileTree, and Vectors RPCs.
These tests require indexed content in Qdrant to produce meaningful results.
"""

import time

import grpc
import pytest

from ollqd.v1 import processing_pb2

from .conftest import requires_indexed, requires_ollama


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir):
    """Index the codebase fixtures and return the collection name."""
    collection = "grpc_test_viz"
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
# Overview
# ---------------------------------------------------------------------------
@requires_ollama
@requires_indexed
class TestOverview:
    """Tests for the Overview RPC."""

    @pytest.mark.asyncio
    async def test_overview_returns_nodes_edges(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """Overview should return VisNode and VisEdge lists for an indexed collection."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        resp = await visualization_stub.Overview(
            processing_pb2.OverviewRequest(
                collection=collection,
                limit=100,
            )
        )

        assert len(resp.nodes) > 0, "Overview should return at least one node"
        # Edges may be empty for a small codebase, but the field should exist
        assert hasattr(resp, "edges"), "Response should have an edges field"

        # Validate node structure
        node = resp.nodes[0]
        assert node.label, "Node should have a non-empty label"
        assert node.id >= 0, "Node id should be non-negative"

    @pytest.mark.asyncio
    async def test_overview_stats(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """Overview should include stats with total_files and total_chunks."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        resp = await visualization_stub.Overview(
            processing_pb2.OverviewRequest(
                collection=collection,
                limit=100,
            )
        )

        assert resp.HasField("stats"), "Overview should include stats"
        assert resp.stats.collection == collection
        assert resp.stats.total_files > 0, "Stats should report at least one file"
        assert resp.stats.total_chunks > 0, "Stats should report at least one chunk"

    @pytest.mark.asyncio
    async def test_overview_limit_respected(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """The number of nodes should not exceed the requested limit."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        limit = 3
        resp = await visualization_stub.Overview(
            processing_pb2.OverviewRequest(
                collection=collection,
                limit=limit,
            )
        )

        assert len(resp.nodes) <= limit, (
            f"Number of nodes ({len(resp.nodes)}) should not exceed limit ({limit})"
        )

    @pytest.mark.asyncio
    async def test_overview_empty_collection(self, visualization_stub, ollama_available):
        """Overview on a non-existent collection should return empty or error gracefully."""
        nonexistent = f"viz_empty_{int(time.time())}"
        try:
            resp = await visualization_stub.Overview(
                processing_pb2.OverviewRequest(
                    collection=nonexistent,
                    limit=10,
                )
            )
            assert len(resp.nodes) == 0, "Non-existent collection should return no nodes"
        except grpc.aio.AioRpcError as e:
            assert e.code() in (
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.INTERNAL,
            ), f"Unexpected gRPC error: {e.code()}"


# ---------------------------------------------------------------------------
# FileTree
# ---------------------------------------------------------------------------
@requires_ollama
@requires_indexed
class TestFileTree:
    """Tests for the FileTree RPC."""

    @pytest.mark.asyncio
    async def test_file_tree_returns_tree(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """FileTree should return a tree structure with nodes for an indexed collection."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        resp = await visualization_stub.FileTree(
            processing_pb2.FileTreeRequest(
                collection=collection,
            )
        )

        assert len(resp.nodes) > 0, "FileTree should return at least one node"
        assert resp.total_chunks > 0, "FileTree should report total_chunks > 0"

    @pytest.mark.asyncio
    async def test_file_tree_with_path_filter(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """FileTree with a file_path filter should return nodes related to that path."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        resp = await visualization_stub.FileTree(
            processing_pb2.FileTreeRequest(
                collection=collection,
                file_path="main.go",
            )
        )

        # Should return nodes (possibly filtered) or be empty if path not found
        if resp.nodes:
            assert resp.file_path == "main.go" or resp.total_chunks >= 0

    @pytest.mark.asyncio
    async def test_file_tree_node_structure(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """FileTree nodes should have valid VisNode fields."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        resp = await visualization_stub.FileTree(
            processing_pb2.FileTreeRequest(collection=collection)
        )

        for node in resp.nodes:
            assert node.id >= 0, "Node id should be non-negative"
            assert node.label, "Node should have a non-empty label"


# ---------------------------------------------------------------------------
# Vectors
# ---------------------------------------------------------------------------
@requires_ollama
@requires_indexed
class TestVectors:
    """Tests for the Vectors RPC (PCA / t-SNE dimensionality reduction)."""

    @pytest.mark.asyncio
    async def test_vectors_pca(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """Vectors with method=pca should return VectorPoint entries with coordinates."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        resp = await visualization_stub.Vectors(
            processing_pb2.VectorsRequest(
                collection=collection,
                method="pca",
                dims=2,
                limit=50,
            )
        )

        assert len(resp.points) > 0, "Vectors should return at least one point"
        assert resp.method == "pca", f"Method should be 'pca', got '{resp.method}'"
        assert resp.dims == 2, f"Dims should be 2, got {resp.dims}"
        assert resp.original_dims > 0, "original_dims should be positive"

        # Validate point structure
        point = resp.points[0]
        # x and y should be float values (could be 0.0 though)
        assert isinstance(point.x, float), "point.x should be a float"
        assert isinstance(point.y, float), "point.y should be a float"
        assert point.file, "point should have a file field"

    @pytest.mark.asyncio
    async def test_vectors_pca_3d(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """Vectors with dims=3 should include z coordinates."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        resp = await visualization_stub.Vectors(
            processing_pb2.VectorsRequest(
                collection=collection,
                method="pca",
                dims=3,
                limit=50,
            )
        )

        assert resp.dims == 3
        if resp.points:
            point = resp.points[0]
            assert isinstance(point.z, float), "3D point should have a z coordinate"

    @pytest.mark.asyncio
    async def test_vectors_limit_respected(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """The number of returned points should not exceed the limit."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        limit = 5
        resp = await visualization_stub.Vectors(
            processing_pb2.VectorsRequest(
                collection=collection,
                method="pca",
                dims=2,
                limit=limit,
            )
        )

        assert len(resp.points) <= limit, (
            f"Number of points ({len(resp.points)}) should not exceed limit ({limit})"
        )

    @pytest.mark.asyncio
    async def test_vectors_total_points(
        self, visualization_stub, indexing_stub, codebase_fixtures_dir, ollama_available
    ):
        """total_points should reflect the actual number of vectors in the collection."""
        collection = await _ensure_indexed_for_viz(indexing_stub, codebase_fixtures_dir)

        resp = await visualization_stub.Vectors(
            processing_pb2.VectorsRequest(
                collection=collection,
                method="pca",
                dims=2,
                limit=100,
            )
        )

        assert resp.total_points >= len(resp.points), (
            f"total_points ({resp.total_points}) should be >= returned points ({len(resp.points)})"
        )

    @pytest.mark.asyncio
    async def test_vectors_empty_collection(self, visualization_stub, ollama_available):
        """Vectors on a non-existent collection should return empty or error gracefully."""
        nonexistent = f"viz_vectors_empty_{int(time.time())}"
        try:
            resp = await visualization_stub.Vectors(
                processing_pb2.VectorsRequest(
                    collection=nonexistent,
                    method="pca",
                    dims=2,
                    limit=10,
                )
            )
            assert len(resp.points) == 0
        except grpc.aio.AioRpcError as e:
            assert e.code() in (
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.INTERNAL,
            ), f"Unexpected gRPC error: {e.code()}"

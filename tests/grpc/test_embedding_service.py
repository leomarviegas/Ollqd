"""Integration tests for EmbeddingService gRPC endpoints.

Tests cover GetInfo, TestEmbed, CompareModels, and SetModel RPCs.
These tests require a running Ollama instance with an embedding model pulled.
"""

import pytest

from ollqd.v1 import processing_pb2


class TestGetInfo:
    """Tests for the GetInfo RPC."""

    @pytest.mark.asyncio
    async def test_get_info_returns_model_name(self, embedding_stub, ollama_available):
        """GetInfo should return a response with a non-empty model field."""
        resp = await embedding_stub.GetInfo(processing_pb2.GetEmbeddingInfoRequest())

        assert resp.model, "GetInfo response should include a non-empty model name"
        assert resp.dimension > 0, "GetInfo response should have a positive dimension"

    @pytest.mark.asyncio
    async def test_get_info_dimension_is_reasonable(self, embedding_stub, ollama_available):
        """The embedding dimension should be a typical value (e.g. 384, 768, 1024, etc.)."""
        resp = await embedding_stub.GetInfo(processing_pb2.GetEmbeddingInfoRequest())

        # Most embedding models produce dimensions between 128 and 8192
        assert 128 <= resp.dimension <= 8192, (
            f"Embedding dimension {resp.dimension} is outside expected range [128, 8192]"
        )


class TestTestEmbed:
    """Tests for the TestEmbed RPC."""

    @pytest.mark.asyncio
    async def test_test_embed_returns_stats(self, embedding_stub, ollama_available):
        """TestEmbed should return dimension, latency, and statistical measures."""
        resp = await embedding_stub.TestEmbed(
            processing_pb2.TestEmbedRequest(text="Hello, world!")
        )

        assert resp.dimension > 0, "TestEmbed should report a positive dimension"
        assert resp.latency_ms >= 0, "TestEmbed should report non-negative latency"

        # Statistical measures should be populated
        assert resp.norm > 0, "Embedding norm should be positive"
        # min/max/mean/stdev are floats; just verify they exist as numbers
        assert isinstance(resp.min, float)
        assert isinstance(resp.max, float)
        assert isinstance(resp.mean, float)
        assert isinstance(resp.stdev, float)

    @pytest.mark.asyncio
    async def test_test_embed_dimension_matches_info(self, embedding_stub, ollama_available):
        """TestEmbed dimension should match the dimension reported by GetInfo."""
        info = await embedding_stub.GetInfo(processing_pb2.GetEmbeddingInfoRequest())
        embed = await embedding_stub.TestEmbed(
            processing_pb2.TestEmbedRequest(text="Test embedding consistency")
        )

        assert embed.dimension == info.dimension, (
            f"TestEmbed dimension ({embed.dimension}) should match "
            f"GetInfo dimension ({info.dimension})"
        )

    @pytest.mark.asyncio
    async def test_test_embed_min_max_range(self, embedding_stub, ollama_available):
        """The min value should be less than or equal to the max value."""
        resp = await embedding_stub.TestEmbed(
            processing_pb2.TestEmbedRequest(text="Range validation test")
        )

        assert resp.min <= resp.max, (
            f"min ({resp.min}) should be <= max ({resp.max})"
        )
        assert resp.min <= resp.mean <= resp.max, (
            f"mean ({resp.mean}) should be between min ({resp.min}) and max ({resp.max})"
        )


class TestCompareModels:
    """Tests for the CompareModels RPC."""

    @pytest.mark.asyncio
    async def test_compare_models_same_model(self, embedding_stub, ollama_available):
        """Comparing a model with itself should return identical dimensions."""
        info = await embedding_stub.GetInfo(processing_pb2.GetEmbeddingInfoRequest())
        model_name = info.model

        resp = await embedding_stub.CompareModels(
            processing_pb2.CompareModelsRequest(
                text="Comparison test",
                model1=model_name,
                model2=model_name,
            )
        )

        assert resp.model1.model == model_name
        assert resp.model2.model == model_name
        assert resp.model1.dimension == resp.model2.dimension, (
            "Same model should produce identical dimensions"
        )
        assert resp.text == "Comparison test"


class TestSetModel:
    """Tests for the SetModel RPC."""

    @pytest.mark.asyncio
    async def test_set_model_returns_updated_info(self, embedding_stub, ollama_available):
        """SetModel should return EmbeddingInfoResponse with the requested model."""
        # Get current model so we can restore it
        current = await embedding_stub.GetInfo(processing_pb2.GetEmbeddingInfoRequest())
        original_model = current.model

        try:
            # Set the same model (safe operation -- we know it exists)
            resp = await embedding_stub.SetModel(
                processing_pb2.SetEmbedModelRequest(model=original_model)
            )
            assert resp.model == original_model, (
                "SetModel response should reflect the requested model"
            )
            assert resp.dimension > 0
        finally:
            # Ensure we restore the model even if the test fails
            await embedding_stub.SetModel(
                processing_pb2.SetEmbedModelRequest(model=original_model)
            )

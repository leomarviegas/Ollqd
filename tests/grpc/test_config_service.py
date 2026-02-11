"""Integration tests for ConfigService gRPC endpoints.

Tests cover GetConfig, UpdateOllama, UpdateQdrant, UpdateChunking,
UpdatePII, UpdateImage, and ResetConfig RPCs.
"""

import pytest
import pytest_asyncio

from ollqd.v1 import processing_pb2, types_pb2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_config(config_stub):
    """Fetch the current AppConfig from the worker."""
    return await config_stub.GetConfig(processing_pb2.GetConfigRequest())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestGetConfig:
    """Tests for the GetConfig RPC."""

    @pytest.mark.asyncio
    async def test_get_config_returns_app_config(self, config_stub):
        """GetConfig should return a non-empty AppConfig with top-level sections."""
        config = await _get_config(config_stub)

        # AppConfig has nested configs for ollama, qdrant, chunking, image, pii
        assert config.HasField("ollama"), "AppConfig should contain an ollama section"
        assert config.HasField("qdrant"), "AppConfig should contain a qdrant section"
        assert config.HasField("chunking"), "AppConfig should contain a chunking section"
        assert config.HasField("image"), "AppConfig should contain an image section"
        assert config.HasField("pii"), "AppConfig should contain a pii section"

    @pytest.mark.asyncio
    async def test_get_config_ollama_has_base_url(self, config_stub):
        """The Ollama config section should have a non-empty base_url."""
        config = await _get_config(config_stub)
        assert config.ollama.base_url, "ollama.base_url should be non-empty"

    @pytest.mark.asyncio
    async def test_get_config_qdrant_has_url(self, config_stub):
        """The Qdrant config section should have a non-empty url."""
        config = await _get_config(config_stub)
        assert config.qdrant.url, "qdrant.url should be non-empty"

    @pytest.mark.asyncio
    async def test_get_config_chunking_has_defaults(self, config_stub):
        """Chunking config should have positive chunk_size and chunk_overlap."""
        config = await _get_config(config_stub)
        assert config.chunking.chunk_size > 0, "chunk_size should be > 0"
        assert config.chunking.chunk_overlap >= 0, "chunk_overlap should be >= 0"


class TestUpdateChunking:
    """Tests for the UpdateChunking RPC."""

    @pytest.mark.asyncio
    async def test_update_chunking_persists(self, config_stub):
        """Updating chunk_size should be reflected in a subsequent GetConfig call."""
        # Get original values to restore later
        original = await _get_config(config_stub)
        original_size = original.chunking.chunk_size

        try:
            # Update to a known value
            new_size = 512
            resp = await config_stub.UpdateChunking(
                processing_pb2.UpdateChunkingRequest(chunk_size=new_size)
            )
            assert resp.chunk_size == new_size, (
                f"UpdateChunking response should reflect new chunk_size={new_size}"
            )

            # Verify persistence via GetConfig
            config = await _get_config(config_stub)
            assert config.chunking.chunk_size == new_size, (
                "GetConfig should show updated chunk_size after UpdateChunking"
            )
        finally:
            # Restore original
            await config_stub.UpdateChunking(
                processing_pb2.UpdateChunkingRequest(chunk_size=original_size)
            )

    @pytest.mark.asyncio
    async def test_update_chunking_overlap(self, config_stub):
        """Updating chunk_overlap should persist correctly."""
        original = await _get_config(config_stub)
        original_overlap = original.chunking.chunk_overlap

        try:
            new_overlap = 64
            resp = await config_stub.UpdateChunking(
                processing_pb2.UpdateChunkingRequest(chunk_overlap=new_overlap)
            )
            assert resp.chunk_overlap == new_overlap

            config = await _get_config(config_stub)
            assert config.chunking.chunk_overlap == new_overlap
        finally:
            await config_stub.UpdateChunking(
                processing_pb2.UpdateChunkingRequest(chunk_overlap=original_overlap)
            )


class TestUpdatePII:
    """Tests for the UpdatePII RPC."""

    @pytest.mark.asyncio
    async def test_update_pii_toggle_enabled(self, config_stub):
        """Toggling PII enabled on and off should round-trip correctly."""
        # Enable PII
        resp_on = await config_stub.UpdatePII(
            processing_pb2.UpdatePIIRequest(enabled=True)
        )
        assert resp_on.enabled is True, "UpdatePII(enabled=True) should return enabled=True"

        config_on = await _get_config(config_stub)
        assert config_on.pii.enabled is True, "GetConfig should show pii.enabled=True"

        # Disable PII
        resp_off = await config_stub.UpdatePII(
            processing_pb2.UpdatePIIRequest(enabled=False)
        )
        assert resp_off.enabled is False, "UpdatePII(enabled=False) should return enabled=False"

        config_off = await _get_config(config_stub)
        assert config_off.pii.enabled is False, "GetConfig should show pii.enabled=False"

    @pytest.mark.asyncio
    async def test_update_pii_mask_embeddings(self, config_stub):
        """Toggling mask_embeddings should persist."""
        resp = await config_stub.UpdatePII(
            processing_pb2.UpdatePIIRequest(mask_embeddings=True)
        )
        assert resp.mask_embeddings is True

        config = await _get_config(config_stub)
        assert config.pii.mask_embeddings is True

        # Reset
        await config_stub.UpdatePII(
            processing_pb2.UpdatePIIRequest(mask_embeddings=False)
        )


class TestUpdateOllama:
    """Tests for the UpdateOllama RPC."""

    @pytest.mark.asyncio
    async def test_update_ollama_config(self, config_stub):
        """Changing base_url should be reflected in GetConfig."""
        original = await _get_config(config_stub)
        original_url = original.ollama.base_url

        try:
            new_url = "http://custom-ollama:11434"
            resp = await config_stub.UpdateOllama(
                processing_pb2.UpdateOllamaRequest(base_url=new_url)
            )
            assert resp.base_url == new_url, (
                f"UpdateOllama response should reflect base_url={new_url}"
            )

            config = await _get_config(config_stub)
            assert config.ollama.base_url == new_url, (
                "GetConfig should show updated ollama.base_url"
            )
        finally:
            # Restore original
            await config_stub.UpdateOllama(
                processing_pb2.UpdateOllamaRequest(base_url=original_url)
            )

    @pytest.mark.asyncio
    async def test_update_ollama_chat_model(self, config_stub):
        """Changing chat_model should persist."""
        original = await _get_config(config_stub)
        original_model = original.ollama.chat_model

        try:
            new_model = "llama3.2:latest"
            resp = await config_stub.UpdateOllama(
                processing_pb2.UpdateOllamaRequest(chat_model=new_model)
            )
            assert resp.chat_model == new_model

            config = await _get_config(config_stub)
            assert config.ollama.chat_model == new_model
        finally:
            await config_stub.UpdateOllama(
                processing_pb2.UpdateOllamaRequest(chat_model=original_model)
            )


class TestUpdateQdrant:
    """Tests for the UpdateQdrant RPC."""

    @pytest.mark.asyncio
    async def test_update_qdrant_default_collection(self, config_stub):
        """Changing the default collection name should persist."""
        original = await _get_config(config_stub)
        original_coll = original.qdrant.default_collection

        try:
            new_coll = "test_grpc_collection"
            resp = await config_stub.UpdateQdrant(
                processing_pb2.UpdateQdrantRequest(default_collection=new_coll)
            )
            assert resp.default_collection == new_coll

            config = await _get_config(config_stub)
            assert config.qdrant.default_collection == new_coll
        finally:
            await config_stub.UpdateQdrant(
                processing_pb2.UpdateQdrantRequest(default_collection=original_coll)
            )


class TestUpdateImage:
    """Tests for the UpdateImage RPC."""

    @pytest.mark.asyncio
    async def test_update_image_max_size(self, config_stub):
        """Changing max_image_size_kb should persist."""
        original = await _get_config(config_stub)
        original_size = original.image.max_image_size_kb

        try:
            new_size = 2048
            resp = await config_stub.UpdateImage(
                processing_pb2.UpdateImageRequest(max_image_size_kb=new_size)
            )
            assert resp.max_image_size_kb == new_size

            config = await _get_config(config_stub)
            assert config.image.max_image_size_kb == new_size
        finally:
            await config_stub.UpdateImage(
                processing_pb2.UpdateImageRequest(max_image_size_kb=original_size)
            )


class TestResetConfig:
    """Tests for the ResetConfig RPC."""

    @pytest.mark.asyncio
    async def test_reset_config_restores_chunking_defaults(self, config_stub):
        """After modifying chunking config, ResetConfig(section='chunking') should restore defaults."""
        # Save the default state
        defaults = await _get_config(config_stub)
        default_size = defaults.chunking.chunk_size

        # Modify chunking
        await config_stub.UpdateChunking(
            processing_pb2.UpdateChunkingRequest(chunk_size=999)
        )
        modified = await _get_config(config_stub)
        assert modified.chunking.chunk_size == 999, "Precondition: chunk_size should be modified"

        # Reset the chunking section
        reset_resp = await config_stub.ResetConfig(
            processing_pb2.ResetConfigRequest(section="chunking")
        )
        assert reset_resp.section == "chunking", "ResetConfig should echo back the section name"

        # Verify defaults restored
        restored = await _get_config(config_stub)
        assert restored.chunking.chunk_size == default_size, (
            "chunk_size should be restored to default after ResetConfig"
        )

    @pytest.mark.asyncio
    async def test_reset_config_ollama_section(self, config_stub):
        """ResetConfig(section='ollama') should restore Ollama defaults."""
        defaults = await _get_config(config_stub)
        default_url = defaults.ollama.base_url

        # Modify
        await config_stub.UpdateOllama(
            processing_pb2.UpdateOllamaRequest(base_url="http://modified:9999")
        )

        # Reset
        await config_stub.ResetConfig(
            processing_pb2.ResetConfigRequest(section="ollama")
        )

        restored = await _get_config(config_stub)
        assert restored.ollama.base_url == default_url, (
            "ollama.base_url should be restored after ResetConfig"
        )

    @pytest.mark.asyncio
    async def test_reset_config_pii_section(self, config_stub):
        """ResetConfig(section='pii') should restore PII defaults."""
        defaults = await _get_config(config_stub)
        default_enabled = defaults.pii.enabled

        # Modify
        await config_stub.UpdatePII(
            processing_pb2.UpdatePIIRequest(enabled=not default_enabled)
        )

        # Reset
        await config_stub.ResetConfig(
            processing_pb2.ResetConfigRequest(section="pii")
        )

        restored = await _get_config(config_stub)
        assert restored.pii.enabled == default_enabled

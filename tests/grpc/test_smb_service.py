"""Integration tests for SMBService gRPC endpoints.

Tests cover TestConnection and Browse RPCs. These tests are skipped
unless SMB environment variables are configured (SMB_SERVER, SMB_SHARE, etc.).
"""

import os

import grpc
import pytest

from ollqd.v1 import processing_pb2

from .conftest import requires_smb


# ---------------------------------------------------------------------------
# SMB connection parameters from environment
# ---------------------------------------------------------------------------
SMB_SERVER = os.getenv("SMB_SERVER", "")
SMB_SHARE = os.getenv("SMB_SHARE", "")
SMB_USERNAME = os.getenv("SMB_USERNAME", "")
SMB_PASSWORD = os.getenv("SMB_PASSWORD", "")
SMB_DOMAIN = os.getenv("SMB_DOMAIN", "")
SMB_PORT = int(os.getenv("SMB_PORT", "445"))


def _smb_test_request() -> processing_pb2.SMBTestRequest:
    """Build an SMBTestRequest from environment variables."""
    return processing_pb2.SMBTestRequest(
        server=SMB_SERVER,
        share=SMB_SHARE,
        username=SMB_USERNAME,
        password=SMB_PASSWORD,
        domain=SMB_DOMAIN,
        port=SMB_PORT,
    )


def _smb_browse_request(path: str = "/") -> processing_pb2.SMBBrowseRequest:
    """Build an SMBBrowseRequest from environment variables."""
    return processing_pb2.SMBBrowseRequest(
        server=SMB_SERVER,
        share=SMB_SHARE,
        username=SMB_USERNAME,
        password=SMB_PASSWORD,
        domain=SMB_DOMAIN,
        port=SMB_PORT,
        path=path,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@requires_smb
class TestSMBTestConnection:
    """Tests for the TestConnection RPC."""

    @pytest.mark.asyncio
    async def test_connection_ok(self, smb_stub):
        """TestConnection with valid SMB credentials should return ok=True."""
        resp = await smb_stub.TestConnection(_smb_test_request())

        assert resp.ok is True, (
            f"TestConnection should return ok=True, got message: {resp.message}"
        )
        assert resp.message, "Response should include a message"

    @pytest.mark.asyncio
    async def test_connection_bad_server(self, smb_stub):
        """TestConnection to a non-existent server should return ok=False or error."""
        bad_request = processing_pb2.SMBTestRequest(
            server="192.0.2.1",  # RFC 5737 TEST-NET: guaranteed unreachable
            share="nonexistent",
            username="nobody",
            password="wrong",
            port=445,
        )
        try:
            resp = await smb_stub.TestConnection(bad_request)
            assert resp.ok is False, (
                "TestConnection to a bad server should return ok=False"
            )
        except grpc.aio.AioRpcError as e:
            # A connection timeout / unavailable error is acceptable
            assert e.code() in (
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.INTERNAL,
                grpc.StatusCode.DEADLINE_EXCEEDED,
            ), f"Unexpected gRPC error: {e.code()}"


@requires_smb
class TestSMBBrowse:
    """Tests for the Browse RPC."""

    @pytest.mark.asyncio
    async def test_browse_root(self, smb_stub):
        """Browsing the root of the share should return file entries."""
        resp = await smb_stub.Browse(_smb_browse_request("/"))

        # Root browse should return at least something (or be empty for empty shares)
        assert hasattr(resp, "files"), "Response should have a files field"
        assert resp.path == "/" or resp.path == "", (
            f"Response path should echo the requested path, got '{resp.path}'"
        )

    @pytest.mark.asyncio
    async def test_browse_entries_have_names(self, smb_stub):
        """Each SMBFileEntry should have a non-empty name."""
        resp = await smb_stub.Browse(_smb_browse_request("/"))

        for entry in resp.files:
            assert entry.name, "Each file entry should have a non-empty name"
            # is_dir is a bool, size is int64
            assert isinstance(entry.is_dir, bool)
            assert entry.size >= 0 or entry.is_dir, (
                "File size should be non-negative"
            )

    @pytest.mark.asyncio
    async def test_browse_nonexistent_path(self, smb_stub):
        """Browsing a non-existent path should return empty or error gracefully."""
        try:
            resp = await smb_stub.Browse(
                _smb_browse_request("/this/path/does/not/exist_12345")
            )
            # If the server returns a response, files should be empty
            assert len(resp.files) == 0, (
                "Non-existent path should return zero files"
            )
        except grpc.aio.AioRpcError as e:
            assert e.code() in (
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.INTERNAL,
                grpc.StatusCode.INVALID_ARGUMENT,
            ), f"Unexpected gRPC error: {e.code()}"


# ---------------------------------------------------------------------------
# Tests without SMB env — verify graceful skip
# ---------------------------------------------------------------------------
class TestSMBSkipWhenUnavailable:
    """Verify that SMB tests are properly skipped when env is not configured."""

    def test_smb_env_check(self):
        """This test always passes. It documents how SMB tests are gated."""
        if not SMB_SERVER:
            pytest.skip("SMB_SERVER not set; SMB tests are properly skipped")
        # If SMB_SERVER is set, we just confirm the env is available
        assert SMB_SERVER, "SMB_SERVER should be set"

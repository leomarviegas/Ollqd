"""Security-focused tests for the Go gateway.

Validates CORS headers, proxy behavior, header leakage, upload limits,
and path traversal protections.
"""

import io

import pytest
import requests


class TestCORSHeaders:
    """CORS configuration via the chi cors middleware."""

    def test_cors_headers_present(self, api, gateway_url):
        """An OPTIONS preflight request returns the expected CORS headers."""
        r = requests.options(
            f"{gateway_url}/api/system/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
            timeout=10,
        )
        # The CORS middleware should respond (200 or 204)
        assert r.status_code in (200, 204), (
            f"OPTIONS returned {r.status_code}: {r.text}"
        )
        assert "access-control-allow-origin" in {
            k.lower() for k in r.headers.keys()
        }

    def test_cors_allows_all_origins(self, api, gateway_url):
        """The gateway allows any Origin (AllowedOrigins: ['*'])."""
        r = requests.options(
            f"{gateway_url}/api/system/health",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
            timeout=10,
        )
        allow_origin = r.headers.get(
            "Access-Control-Allow-Origin",
            r.headers.get("access-control-allow-origin", ""),
        )
        # Either "*" or the echoed origin
        assert allow_origin in ("*", "https://evil.example.com")

    def test_cors_allows_methods(self, api, gateway_url):
        """The preflight response includes the allowed methods."""
        r = requests.options(
            f"{gateway_url}/api/qdrant/collections",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "DELETE",
            },
            timeout=10,
        )
        allow_methods = r.headers.get(
            "Access-Control-Allow-Methods",
            r.headers.get("access-control-allow-methods", ""),
        ).upper()
        assert "DELETE" in allow_methods


class TestProxyStatusCodes:
    """Verify the gateway proxies upstream status codes faithfully."""

    def test_proxy_preserves_status_codes(self, api, wait_for_qdrant):
        """Requesting a non-existent Qdrant path returns 404 pass-through."""
        r = api.get("/api/qdrant/nonexistent-path-12345", timeout=10)
        # Qdrant should return 404 for unknown paths
        assert r.status_code in (404, 405), (
            f"Expected 404/405 from Qdrant proxy, got {r.status_code}"
        )


class TestHeaderLeakage:
    """Ensure internal headers are not leaked to external clients."""

    def test_no_internal_header_leakage(self, api):
        """Response headers should not contain x-grpc or internal server headers."""
        r = api.get("/api/system/health", timeout=10)
        header_names = {k.lower() for k in r.headers.keys()}

        # These internal headers must not be present
        forbidden = {"x-grpc-status", "x-grpc-message", "grpc-status", "grpc-message"}
        leaked = header_names & forbidden
        assert not leaked, f"Internal headers leaked: {leaked}"

    def test_no_server_version_header(self, api):
        """The Server header should not expose detailed version information."""
        r = api.get("/api/system/health", timeout=10)
        server = r.headers.get("Server", "")
        # chi/Go does not set Server by default, but verify no detailed version
        if server:
            # Should not contain Go version or framework details
            assert "Go/" not in server
            assert "chi/" not in server


class TestUploadSizeLimit:
    """POST /api/rag/upload with oversized payloads."""

    def test_upload_size_limit(self, api, temp_collection):
        """A very large upload triggers a 413 or 400 response.

        The gateway's MaxUploadSizeMB defaults to 50.  We send >50 MB to
        trigger the limit.
        """
        # Create a payload just over the limit.  We use a generator to avoid
        # allocating 51 MB in memory.  Since requests needs to know the
        # content-length for multipart, we create a small but explicitly
        # large Content-Length header trick -- instead, we just send a
        # known-large body.
        large_content = b"X" * (51 * 1024 * 1024)  # 51 MB

        files = {
            "files": ("bigfile.txt", io.BytesIO(large_content), "text/plain"),
        }

        try:
            r = api.post(
                "/api/rag/upload",
                files=files,
                data={"collection": temp_collection},
                timeout=30,
            )
            assert r.status_code in (400, 413), (
                f"Expected 400/413 for oversized upload, got {r.status_code}"
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
            # The server may close the connection early for oversized uploads
            pass


class TestPathTraversalInCollectionName:
    """Path traversal attempts in URL parameters."""

    @pytest.mark.parametrize(
        "bad_name",
        [
            "../../../etc/passwd",
            "..%2F..%2Fetc%2Fpasswd",
            "good-name/../../../etc",
        ],
    )
    def test_path_traversal_in_collection_name(self, api, bad_name, wait_for_qdrant):
        """Collection names containing ../ should not cause server errors.

        The gateway and Qdrant should either reject the name with a 4xx or
        handle it safely.
        """
        r = api.get(
            f"/api/qdrant/collections/{bad_name}/points",
            timeout=10,
        )
        # Must not be a 500 server error; 400/404 are acceptable
        assert r.status_code != 500, (
            f"Server error with traversal name '{bad_name}': {r.text}"
        )

    def test_collection_create_traversal_name(self, api, wait_for_qdrant):
        """POST /api/qdrant/collections with a traversal name is rejected or safe."""
        r = api.post(
            "/api/qdrant/collections",
            json={
                "name": "../../../etc/passwd",
                "vector_size": 384,
                "distance": "Cosine",
            },
            timeout=10,
        )
        # Should not succeed cleanly or at minimum not cause 500
        assert r.status_code != 500

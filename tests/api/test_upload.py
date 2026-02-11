"""Tests for the file upload endpoint.

Routes tested:
  POST /api/rag/upload

The upload handler validates file extensions, enforces size limits, and
starts a background indexing task for uploaded files.
"""

import io
import time

import pytest


class TestUploadTextFile:
    """POST /api/rag/upload with valid text files."""

    def test_upload_text_file(self, api, temp_collection):
        """Upload a .txt file via multipart form and verify acceptance."""
        content = b"This is a test document for upload validation."
        files = {
            "files": ("test_upload.txt", io.BytesIO(content), "text/plain"),
        }
        data = {"collection": temp_collection}

        r = api.post(
            "/api/rag/upload",
            files=files,
            data=data,
            timeout=15,
        )
        # 200 (no indexing service) or 202 (task started)
        assert r.status_code in (200, 202), (
            f"Upload failed ({r.status_code}): {r.text}"
        )
        resp = r.json()
        # Should report the saved file(s)
        assert resp.get("count", resp.get("files_count", 0)) >= 1 or "task_id" in resp

    def test_upload_multiple_files(self, api, temp_collection):
        """Upload multiple text files in a single request."""
        files = [
            ("files", ("a.txt", io.BytesIO(b"Content A"), "text/plain")),
            ("files", ("b.md", io.BytesIO(b"# Content B"), "text/markdown")),
        ]
        data = {"collection": temp_collection}

        r = api.post(
            "/api/rag/upload",
            files=files,
            data=data,
            timeout=15,
        )
        assert r.status_code in (200, 202), f"Multi-upload failed: {r.text}"


class TestUploadRejectsDisallowed:
    """Upload validation: disallowed file extensions."""

    def test_upload_rejects_disallowed_extension(self, api, temp_collection):
        """Uploading a .exe file should be rejected with 400."""
        files = {
            "files": ("malware.exe", io.BytesIO(b"\x00" * 100), "application/octet-stream"),
        }
        r = api.post(
            "/api/rag/upload",
            files=files,
            data={"collection": temp_collection},
            timeout=10,
        )
        assert r.status_code == 400, (
            f"Expected 400 for .exe upload, got {r.status_code}: {r.text}"
        )
        data = r.json()
        assert "detail" in data
        assert "not allowed" in data["detail"].lower() or "extension" in data["detail"].lower()

    @pytest.mark.parametrize(
        "ext",
        [".bat", ".sh_", ".dll", ".so", ".bin"],
    )
    def test_upload_rejects_various_bad_extensions(self, api, temp_collection, ext):
        """Several dangerous or unusual extensions should be rejected."""
        files = {
            "files": (f"file{ext}", io.BytesIO(b"content"), "application/octet-stream"),
        }
        r = api.post(
            "/api/rag/upload",
            files=files,
            data={"collection": temp_collection},
            timeout=10,
        )
        assert r.status_code == 400, (
            f"Expected 400 for {ext} upload, got {r.status_code}"
        )


class TestUploadRejectsEmpty:
    """Upload validation: empty file."""

    def test_upload_rejects_empty_file(self, api, temp_collection):
        """An empty file upload should be handled gracefully.

        Note: The gateway may accept a zero-byte file (size 0 is technically
        valid for text) or reject it depending on implementation. We verify
        no 500 error occurs.
        """
        files = {
            "files": ("empty.txt", io.BytesIO(b""), "text/plain"),
        }
        r = api.post(
            "/api/rag/upload",
            files=files,
            data={"collection": temp_collection},
            timeout=10,
        )
        # Should not be a server error
        assert r.status_code < 500, (
            f"Server error on empty file: {r.status_code}: {r.text}"
        )


class TestUploadPathTraversal:
    """Upload validation: path traversal in filenames."""

    @pytest.mark.parametrize(
        "filename",
        [
            "../../../etc/passwd.txt",
            "foo/../bar/../../../etc/shadow.txt",
        ],
    )
    def test_upload_path_traversal_blocked(self, api, temp_collection, filename):
        """Filenames containing ../ should be sanitized or rejected.

        The gateway generates a UUID-based filename, so traversal should be
        impossible.  We verify no 500 and the saved filename does not match
        the traversal attempt.
        """
        files = {
            "files": (filename, io.BytesIO(b"traversal test"), "text/plain"),
        }
        r = api.post(
            "/api/rag/upload",
            files=files,
            data={"collection": temp_collection},
            timeout=10,
        )
        # The gateway either accepts (sanitized name) or rejects
        assert r.status_code < 500, (
            f"Server error on path traversal filename: {r.status_code}"
        )
        if r.status_code in (200, 202):
            body = r.json()
            # Verify the saved name is not the traversal path
            files_list = body.get("files", [])
            for saved_name in files_list:
                assert ".." not in str(saved_name)

    def test_upload_no_files_field(self, api, temp_collection):
        """POST /api/rag/upload with no 'files' field returns 400."""
        r = api.post(
            "/api/rag/upload",
            data={"collection": temp_collection},
            timeout=10,
        )
        # Missing files field should be caught
        assert r.status_code in (400, 413), (
            f"Expected error for missing files, got {r.status_code}"
        )

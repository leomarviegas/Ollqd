"""Tests for code-aware and document chunking."""

from ollqd.chunking import chunk_file, chunk_document, _is_boundary_line
from ollqd.models import FileInfo

import tempfile
from pathlib import Path


def _make_file(content: str, suffix: str = ".py") -> FileInfo:
    """Create a temp file and return FileInfo."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    tmp.write(content)
    tmp.flush()
    return FileInfo(
        path=f"test{suffix}",
        abs_path=tmp.name,
        language="python" if suffix == ".py" else "text",
        size_bytes=len(content),
        content_hash="abc123",
    )


class TestBoundaryDetection:
    def test_python_function(self):
        assert _is_boundary_line("def hello():", "python") is True

    def test_python_class(self):
        assert _is_boundary_line("class MyClass:", "python") is True

    def test_python_async(self):
        assert _is_boundary_line("async def handler():", "python") is True

    def test_python_comment_not_boundary(self):
        assert _is_boundary_line("# comment", "python") is False

    def test_go_func(self):
        assert _is_boundary_line("func main() {", "go") is True

    def test_js_function(self):
        assert _is_boundary_line("function handleClick() {", "javascript") is True

    def test_rust_fn(self):
        assert _is_boundary_line("fn process(data: &str) -> Result<()> {", "rust") is True

    def test_markdown_heading(self):
        assert _is_boundary_line("## Section Title", "markdown") is True


class TestChunkFile:
    def test_small_file_single_chunk(self):
        fi = _make_file("def hello():\n    return 'world'\n")
        chunks = chunk_file(fi, chunk_size=512, chunk_overlap=64)
        assert len(chunks) == 1
        assert chunks[0].file_path == "test.py"
        assert chunks[0].language == "python"

    def test_empty_file(self):
        fi = _make_file("")
        chunks = chunk_file(fi, chunk_size=512, chunk_overlap=64)
        assert len(chunks) == 0

    def test_chunk_indexes(self):
        code = "\n".join(f"def func_{i}():\n    pass\n" for i in range(100))
        fi = _make_file(code)
        chunks = chunk_file(fi, chunk_size=64, chunk_overlap=8)
        assert len(chunks) > 1
        for i, c in enumerate(chunks):
            assert c.chunk_index == i
            assert c.total_chunks == len(chunks)


class TestChunkDocument:
    def test_markdown_heading_split(self):
        content = "# Title\n\nIntro paragraph.\n\n## Section 1\n\nContent 1.\n\n## Section 2\n\nContent 2."
        chunks = chunk_document("test.md", content, language="markdown", chunk_size=32)
        assert len(chunks) >= 2

    def test_text_paragraph_split(self):
        content = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = chunk_document("test.txt", content, language="text", chunk_size=16)
        assert len(chunks) >= 2

    def test_small_doc_single_chunk(self):
        content = "Short document."
        chunks = chunk_document("test.txt", content, language="text")
        assert len(chunks) == 1

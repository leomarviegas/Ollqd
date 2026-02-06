#!/usr/bin/env python3
"""
Codebase Bulk Indexer for Qdrant + Ollama
=========================================
Walks a codebase, chunks files intelligently (code-aware splitting),
generates embeddings via Ollama, and stores everything in Qdrant
for semantic search / RAG retrieval.

Usage:
    python codebase_indexer.py /path/to/codebase
    python codebase_indexer.py /path/to/codebase --collection my-project --embedding-model nomic-embed-text
    python codebase_indexer.py /path/to/codebase --incremental  # only index changed files
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_COLLECTION = "codebase"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_CHUNK_SIZE = 512       # tokens (approximate via char count / 4)
DEFAULT_CHUNK_OVERLAP = 64     # tokens overlap between chunks
MAX_FILE_SIZE_KB = 512         # skip files larger than this
BATCH_SIZE = 32                # points per Qdrant upsert batch
EMBEDDING_WORKERS = 4          # parallel embedding requests

# File extensions to index, mapped to language hints
LANGUAGE_MAP: dict[str, str] = {
    ".py": "python", ".pyi": "python",
    ".go": "go",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".rs": "rust",
    ".java": "java", ".kt": "kotlin", ".scala": "scala",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".lua": "lua",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".sql": "sql",
    ".r": "r", ".R": "r",
    ".html": "html", ".css": "css", ".scss": "scss",
    ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".json": "json",
    ".md": "markdown", ".rst": "restructuredtext",
    ".tf": "terraform", ".hcl": "hcl",
    ".dockerfile": "dockerfile",
    ".proto": "protobuf",
    ".graphql": "graphql", ".gql": "graphql",
}

# Directories to always skip
SKIP_DIRS: set[str] = {
    ".git", ".svn", ".hg",
    "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".tox", ".venv", "venv", "env", ".env",
    "dist", "build", "target", "out", "bin", "obj",
    ".next", ".nuxt", ".output",
    "vendor", "third_party",
    ".idea", ".vscode",
    "coverage", ".coverage",
}

# Files to always skip
SKIP_FILES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "go.sum", "Cargo.lock", "poetry.lock", "uv.lock",
    "Pipfile.lock", "composer.lock", "Gemfile.lock",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("indexer")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileInfo:
    path: str           # relative to codebase root
    abs_path: str
    language: str
    size_bytes: int
    content_hash: str   # SHA-256 of file content


@dataclass
class Chunk:
    file_path: str      # relative path
    language: str
    chunk_index: int    # 0-based index within the file
    total_chunks: int
    start_line: int
    end_line: int
    content: str
    content_hash: str   # hash of the file (for incremental)

    @property
    def point_id(self) -> str:
        """Deterministic ID so re-indexing overwrites the same point."""
        raw = f"{self.file_path}::chunk_{self.chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_files(root: Path, extra_skip_dirs: Optional[set[str]] = None) -> list[FileInfo]:
    """Walk the codebase and collect indexable files."""
    skip = SKIP_DIRS | (extra_skip_dirs or set())
    files: list[FileInfo] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in skip and not d.startswith(".")
        ]

        for fname in filenames:
            if fname in SKIP_FILES:
                continue

            ext = Path(fname).suffix.lower()
            # Also handle Dockerfile without extension
            if fname.lower() == "dockerfile":
                ext = ".dockerfile"

            if ext not in LANGUAGE_MAP:
                continue

            full = Path(dirpath) / fname
            try:
                stat = full.stat()
            except OSError:
                continue

            if stat.st_size > MAX_FILE_SIZE_KB * 1024:
                log.debug("Skipping large file: %s (%d KB)", full, stat.st_size // 1024)
                continue

            # Read and hash
            try:
                content = full.read_bytes()
                content_hash = hashlib.sha256(content).hexdigest()
            except (OSError, PermissionError):
                continue

            files.append(FileInfo(
                path=str(full.relative_to(root)),
                abs_path=str(full),
                language=LANGUAGE_MAP[ext],
                size_bytes=stat.st_size,
                content_hash=content_hash,
            ))

    log.info("Discovered %d indexable files", len(files))
    return files


# ---------------------------------------------------------------------------
# Code-aware chunking
# ---------------------------------------------------------------------------

def _is_boundary_line(line: str, language: str) -> bool:
    """Heuristic: is this line a natural split point (function/class/block start)?"""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("//"):
        return False

    # Python
    if language == "python":
        return stripped.startswith(("def ", "class ", "async def ", "@"))
    # Go
    if language == "go":
        return stripped.startswith("func ") or stripped.startswith("type ")
    # JS/TS
    if language in ("javascript", "typescript"):
        return any(stripped.startswith(kw) for kw in (
            "function ", "export ", "class ", "const ", "async function",
            "describe(", "it(", "test(",
        ))
    # Rust
    if language == "rust":
        return any(stripped.startswith(kw) for kw in (
            "fn ", "pub fn ", "impl ", "struct ", "enum ", "mod ", "trait ",
        ))
    # Java / Kotlin / C#
    if language in ("java", "kotlin", "csharp", "scala"):
        return any(stripped.startswith(kw) for kw in (
            "public ", "private ", "protected ", "class ", "interface ",
            "fun ", "data class ", "object ", "override ",
        ))
    # C/C++
    if language in ("c", "cpp"):
        # Very rough: lines that look like function definitions
        return ("(" in stripped and ")" in stripped and "{" in stripped
                and not stripped.startswith("if")
                and not stripped.startswith("for")
                and not stripped.startswith("while"))
    # Fallback: blank-line separated blocks
    return False


def chunk_file(file_info: FileInfo, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Split a file into overlapping chunks, preferring natural code boundaries."""
    try:
        content = Path(file_info.abs_path).read_text(errors="replace")
    except (OSError, PermissionError):
        return []

    lines = content.splitlines(keepends=True)
    if not lines:
        return []

    # Approximate token count as chars / 4
    char_budget = chunk_size * 4
    overlap_chars = chunk_overlap * 4

    chunks: list[Chunk] = []
    current_lines: list[str] = []
    current_chars = 0
    chunk_start_line = 1

    def _flush(end_line: int):
        text = "".join(current_lines).strip()
        if text:
            chunks.append(Chunk(
                file_path=file_info.path,
                language=file_info.language,
                chunk_index=len(chunks),
                total_chunks=-1,  # patched after
                start_line=chunk_start_line,
                end_line=end_line,
                content=text,
                content_hash=file_info.content_hash,
            ))

    for i, line in enumerate(lines, start=1):
        line_len = len(line)

        # If adding this line exceeds budget and we're at a boundary, flush
        if (current_chars + line_len > char_budget
                and current_chars > overlap_chars
                and _is_boundary_line(line, file_info.language)):
            _flush(i - 1)
            # Keep overlap: take last N chars worth of lines
            overlap_text = "".join(current_lines)
            if len(overlap_text) > overlap_chars:
                overlap_text = overlap_text[-overlap_chars:]
            overlap_lines = overlap_text.splitlines(keepends=True)
            current_lines = overlap_lines
            current_chars = sum(len(l) for l in current_lines)
            chunk_start_line = max(1, i - len(overlap_lines))

        # Hard split if way over budget (no boundary found)
        if current_chars + line_len > char_budget * 1.5 and current_chars > 0:
            _flush(i - 1)
            current_lines = []
            current_chars = 0
            chunk_start_line = i

        current_lines.append(line)
        current_chars += line_len

    # Final chunk
    _flush(len(lines))

    # Patch total_chunks
    for c in chunks:
        c.total_chunks = len(chunks)

    return chunks


# ---------------------------------------------------------------------------
# Ollama embedding client
# ---------------------------------------------------------------------------

class OllamaEmbedder:
    """Generate embeddings via Ollama's /api/embed endpoint."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=120.0)
        self._dim: Optional[int] = None

    def _embed_request(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["embeddings"]

    def get_dimension(self) -> int:
        """Probe embedding dimension with a test string."""
        if self._dim is None:
            vecs = self._embed_request(["dimension probe"])
            self._dim = len(vecs[0])
            log.info("Embedding dimension: %d (model: %s)", self._dim, self.model)
        return self._dim

    def embed_chunks(self, chunks: list[Chunk]) -> list[list[float]]:
        """Embed a batch of chunks. Prepends file context to each chunk."""
        texts = []
        for c in chunks:
            # Prefix with file path and language for better semantic grounding
            prefix = f"File: {c.file_path} | Language: {c.language} | Lines {c.start_line}-{c.end_line}\n\n"
            texts.append(prefix + c.content)
        return self._embed_request(texts)

    def close(self):
        self._client.close()


# ---------------------------------------------------------------------------
# Qdrant manager
# ---------------------------------------------------------------------------

class QdrantManager:
    """Manages the Qdrant collection and upserts."""

    def __init__(self, url: str, collection: str, dimension: int):
        self.client = QdrantClient(url=url)
        self.collection = collection
        self.dimension = dimension

    def ensure_collection(self):
        """Create collection if it doesn't exist."""
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection in collections:
            log.info("Collection '%s' already exists", self.collection)
            return

        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(
                size=self.dimension,
                distance=Distance.COSINE,
            ),
        )
        # Create payload indexes for filtering
        self.client.create_payload_index(
            collection_name=self.collection,
            field_name="file_path",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection,
            field_name="language",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        self.client.create_payload_index(
            collection_name=self.collection,
            field_name="content_hash",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        log.info("Created collection '%s' (dim=%d, cosine)", self.collection, self.dimension)

    def get_indexed_hashes(self) -> dict[str, str]:
        """Return {file_path: content_hash} of already-indexed files for incremental mode."""
        result: dict[str, str] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection,
                limit=256,
                offset=offset,
                with_payload=["file_path", "content_hash"],
                with_vectors=False,
            )
            for p in points:
                fp = p.payload.get("file_path", "")
                ch = p.payload.get("content_hash", "")
                if fp:
                    result[fp] = ch
            if offset is None:
                break
        return result

    def delete_file_points(self, file_path: str):
        """Remove all points for a given file (before re-indexing it)."""
        self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
            ),
        )

    def upsert_batch(self, points: list[PointStruct]):
        """Upsert a batch of points."""
        self.client.upsert(
            collection_name=self.collection,
            points=points,
        )

    def count(self) -> int:
        info = self.client.get_collection(self.collection)
        return info.points_count


# ---------------------------------------------------------------------------
# Indexing pipeline
# ---------------------------------------------------------------------------

def run_indexing(
    codebase_root: Path,
    ollama_url: str,
    qdrant_url: str,
    collection: str,
    embedding_model: str,
    chunk_size: int,
    chunk_overlap: int,
    incremental: bool,
    workers: int,
    extra_skip_dirs: Optional[set[str]] = None,
):
    t_start = time.time()

    # 1. Discover files
    files = discover_files(codebase_root, extra_skip_dirs)
    if not files:
        log.warning("No indexable files found in %s", codebase_root)
        return

    # 2. Init embedder & get dimension
    embedder = OllamaEmbedder(ollama_url, embedding_model)
    dim = embedder.get_dimension()

    # 3. Init Qdrant
    qdrant = QdrantManager(qdrant_url, collection, dim)
    qdrant.ensure_collection()

    # 4. Incremental: skip unchanged files
    if incremental:
        indexed = qdrant.get_indexed_hashes()
        original_count = len(files)
        files = [f for f in files if indexed.get(f.path) != f.content_hash]
        log.info("Incremental: %d/%d files need (re)indexing", len(files), original_count)

        # Delete stale points for files that changed
        for f in files:
            if f.path in indexed:
                qdrant.delete_file_points(f.path)
                log.debug("Deleted stale points for %s", f.path)

        if not files:
            log.info("Everything is up to date!")
            return

    # 5. Chunk all files
    all_chunks: list[Chunk] = []
    for f in files:
        chunks = chunk_file(f, chunk_size, chunk_overlap)
        all_chunks.extend(chunks)
    log.info("Generated %d chunks from %d files", len(all_chunks), len(files))

    # 6. Embed and upsert in batches
    total_embedded = 0
    failed = 0

    for batch_start in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[batch_start : batch_start + BATCH_SIZE]

        try:
            vectors = embedder.embed_chunks(batch)
        except Exception as e:
            log.error("Embedding failed for batch at offset %d: %s", batch_start, e)
            failed += len(batch)
            continue

        points = []
        for chunk, vec in zip(batch, vectors):
            points.append(PointStruct(
                id=chunk.point_id,
                vector=vec,
                payload={
                    "file_path": chunk.file_path,
                    "language": chunk.language,
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": chunk.total_chunks,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                },
            ))

        try:
            qdrant.upsert_batch(points)
            total_embedded += len(points)
        except Exception as e:
            log.error("Qdrant upsert failed at offset %d: %s", batch_start, e)
            failed += len(batch)
            continue

        pct = min(100, int((batch_start + len(batch)) / len(all_chunks) * 100))
        log.info("Progress: %d%% (%d/%d chunks)", pct, total_embedded, len(all_chunks))

    elapsed = time.time() - t_start
    total_points = qdrant.count()
    embedder.close()

    log.info("=" * 60)
    log.info("Indexing complete in %.1fs", elapsed)
    log.info("  Files processed : %d", len(files))
    log.info("  Chunks embedded : %d", total_embedded)
    log.info("  Failed chunks   : %d", failed)
    log.info("  Total in Qdrant : %d points", total_points)
    log.info("  Collection      : %s", collection)
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Bulk-index a codebase into Qdrant using Ollama embeddings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/project
  %(prog)s /path/to/project --collection my-app --embedding-model nomic-embed-text
  %(prog)s /path/to/project --incremental
  %(prog)s /path/to/project --skip-dirs data,logs,fixtures
        """,
    )
    parser.add_argument("codebase", type=Path, help="Root directory of the codebase to index")
    parser.add_argument("--collection", "-c", default=DEFAULT_COLLECTION,
                        help=f"Qdrant collection name (default: {DEFAULT_COLLECTION})")
    parser.add_argument("--embedding-model", "-e", default=DEFAULT_EMBEDDING_MODEL,
                        help=f"Ollama embedding model (default: {DEFAULT_EMBEDDING_MODEL})")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL,
                        help=f"Ollama base URL (default: {DEFAULT_OLLAMA_URL})")
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL,
                        help=f"Qdrant URL (default: {DEFAULT_QDRANT_URL})")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                        help=f"Approx tokens per chunk (default: {DEFAULT_CHUNK_SIZE})")
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP,
                        help=f"Overlap tokens between chunks (default: {DEFAULT_CHUNK_OVERLAP})")
    parser.add_argument("--incremental", "-i", action="store_true",
                        help="Only re-index files that changed since last run")
    parser.add_argument("--workers", "-w", type=int, default=EMBEDDING_WORKERS,
                        help=f"Parallel embedding workers (default: {EMBEDDING_WORKERS})")
    parser.add_argument("--skip-dirs", type=str, default="",
                        help="Additional directories to skip (comma-separated)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.codebase.is_dir():
        log.error("Not a directory: %s", args.codebase)
        sys.exit(1)

    extra_skip = set(args.skip_dirs.split(",")) - {""} if args.skip_dirs else None

    run_indexing(
        codebase_root=args.codebase.resolve(),
        ollama_url=args.ollama_url,
        qdrant_url=args.qdrant_url,
        collection=args.collection,
        embedding_model=args.embedding_model,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        incremental=args.incremental,
        workers=args.workers,
        extra_skip_dirs=extra_skip,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Ollqd MCP Server — FastMCP server exposing RAG tools.

Tools:
  - index_codebase: Walk + chunk + embed + upsert code files
  - index_documents: Chunk + embed + upsert document files
  - semantic_search: Embed query + search Qdrant
  - list_collections: List all Qdrant collections
  - delete_collection: Drop a collection

Run:
  python -m ollqd.server.main
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from qdrant_client.models import PointStruct

from ..config import AppConfig
from ..chunking import chunk_document, chunk_file
from ..discovery import discover_files
from ..embedder import OllamaEmbedder
from ..errors import EmbeddingError, VectorStoreError
from ..vectorstore import QdrantManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ollqd.server")

cfg = AppConfig()
BATCH_SIZE = 32

mcp = FastMCP(cfg.server.name)


def _get_embedder() -> OllamaEmbedder:
    return OllamaEmbedder(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embed_model,
        timeout=cfg.ollama.timeout_s,
    )


def _get_qdrant(collection: str, dim: int) -> QdrantManager:
    return QdrantManager(url=cfg.qdrant.url, collection=collection, dimension=dim)


@mcp.tool()
def index_codebase(
    root_path: str,
    collection: str = "codebase",
    incremental: bool = True,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    extra_skip_dirs: Optional[list[str]] = None,
) -> dict:
    """Index a codebase directory into Qdrant. Walks files, chunks at code boundaries, embeds via Ollama, upserts to Qdrant."""
    t_start = time.time()
    root = Path(root_path).resolve()

    if not root.is_dir():
        return {"status": "error", "message": f"Not a directory: {root_path}"}

    files = discover_files(root, cfg.chunking.max_file_size_kb, set(extra_skip_dirs or []))
    if not files:
        return {"status": "ok", "message": "No indexable files found", "files": 0, "chunks": 0}

    embedder = _get_embedder()
    dim = embedder.get_dimension()
    qdrant = _get_qdrant(collection, dim)
    qdrant.ensure_collection()

    if incremental:
        indexed = qdrant.get_indexed_hashes()
        original_count = len(files)
        files = [f for f in files if indexed.get(f.path) != f.content_hash]
        for f in files:
            if f.path in indexed:
                qdrant.delete_file_points(f.path)
        log.info("Incremental: %d/%d files need indexing", len(files), original_count)
        if not files:
            embedder.close()
            return {"status": "ok", "message": "Everything up to date", "files": 0, "chunks": 0}

    all_chunks = []
    for f in files:
        all_chunks.extend(chunk_file(f, chunk_size, chunk_overlap))

    total_upserted = 0
    failed = 0

    for batch_start in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[batch_start:batch_start + BATCH_SIZE]
        try:
            vectors = embedder.embed_chunks(batch)
        except EmbeddingError as e:
            log.error("Embedding failed: %s", e)
            failed += len(batch)
            continue

        points = [
            PointStruct(
                id=c.point_id,
                vector=v,
                payload={
                    "file_path": c.file_path,
                    "language": c.language,
                    "chunk_index": c.chunk_index,
                    "total_chunks": c.total_chunks,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "content": c.content,
                    "content_hash": c.content_hash,
                },
            )
            for c, v in zip(batch, vectors)
        ]

        try:
            qdrant.upsert_batch(points)
            total_upserted += len(points)
        except VectorStoreError as e:
            log.error("Qdrant upsert failed: %s", e)
            failed += len(batch)

    embedder.close()
    elapsed = time.time() - t_start

    return {
        "status": "ok",
        "files": len(files),
        "chunks": total_upserted,
        "failed": failed,
        "collection": collection,
        "elapsed_seconds": round(elapsed, 1),
    }


@mcp.tool()
def index_documents(
    paths: list[str],
    collection: str = "documents",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    source_tag: str = "docs",
) -> dict:
    """Index document files (markdown, text, etc.) into Qdrant."""
    t_start = time.time()
    embedder = _get_embedder()
    dim = embedder.get_dimension()
    qdrant = _get_qdrant(collection, dim)
    qdrant.ensure_collection()

    all_chunks = []
    files_processed = 0

    for p in paths:
        path = Path(p).resolve()
        if path.is_file():
            file_list = [path]
        elif path.is_dir():
            file_list = sorted(path.rglob("*"))
        else:
            continue

        for fp in file_list:
            if not fp.is_file():
                continue
            ext = fp.suffix.lower()
            if ext not in (".md", ".txt", ".rst", ".html", ".pdf"):
                continue

            try:
                content = fp.read_text(errors="replace")
            except (OSError, PermissionError):
                continue

            content_hash = hashlib.sha256(content.encode()).hexdigest()
            lang = "markdown" if ext in (".md", ".rst") else "text"

            chunks = chunk_document(
                file_path=str(fp),
                content=content,
                language=lang,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                content_hash=content_hash,
            )
            all_chunks.extend(chunks)
            files_processed += 1

    total_upserted = 0
    for batch_start in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[batch_start:batch_start + BATCH_SIZE]
        try:
            texts = [f"File: {c.file_path} | {c.language}\n\n{c.content}" for c in batch]
            vectors = embedder.embed_texts(texts)
        except EmbeddingError:
            continue

        points = [
            PointStruct(
                id=c.point_id,
                vector=v,
                payload={
                    "file_path": c.file_path,
                    "language": c.language,
                    "chunk_index": c.chunk_index,
                    "total_chunks": c.total_chunks,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "content": c.content,
                    "content_hash": c.content_hash,
                    "source_tag": source_tag,
                },
            )
            for c, v in zip(batch, vectors)
        ]
        try:
            qdrant.upsert_batch(points)
            total_upserted += len(points)
        except VectorStoreError:
            continue

    embedder.close()
    elapsed = time.time() - t_start

    return {
        "status": "ok",
        "files": files_processed,
        "chunks": total_upserted,
        "collection": collection,
        "elapsed_seconds": round(elapsed, 1),
    }


@mcp.tool()
def semantic_search(
    query: str,
    collection: str = "codebase",
    top_k: int = 5,
    language: Optional[str] = None,
    file_path: Optional[str] = None,
) -> dict:
    """Semantic search over indexed content. Returns ranked results with file paths and code snippets."""
    embedder = _get_embedder()
    dim = embedder.get_dimension()
    qdrant = _get_qdrant(collection, dim)

    try:
        query_vec = embedder.embed_query(query)
    except EmbeddingError as e:
        embedder.close()
        return {"status": "error", "message": str(e)}

    hits = qdrant.search(query_vec, top_k=top_k, language=language, file_filter=file_path)
    embedder.close()

    return {"status": "ok", "query": query, "collection": collection, "results": hits}


@mcp.tool()
def list_collections() -> dict:
    """List all Qdrant collections with point counts."""
    try:
        embedder = _get_embedder()
        dim = embedder.get_dimension()
        embedder.close()
        qdrant = _get_qdrant(cfg.qdrant.default_collection, dim)
        collections = qdrant.list_collections()
        return {"status": "ok", "collections": collections}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def delete_collection(collection: str, confirm: bool = False) -> dict:
    """Delete a Qdrant collection. Set confirm=true to proceed."""
    if not confirm:
        return {"status": "error", "message": "Set confirm=true to delete the collection"}
    try:
        embedder = _get_embedder()
        dim = embedder.get_dimension()
        embedder.close()
        qdrant = _get_qdrant(collection, dim)
        qdrant.delete_collection(collection)
        return {"status": "ok", "deleted": collection}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def main():
    log.info("Starting Ollqd MCP Server (%s)", cfg.server.name)
    log.info("  Ollama: %s (embed: %s)", cfg.ollama.base_url, cfg.ollama.embed_model)
    log.info("  Qdrant: %s", cfg.qdrant.url)
    mcp.run(transport=cfg.server.transport)


if __name__ == "__main__":
    main()

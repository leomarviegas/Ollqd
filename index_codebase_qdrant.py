#!/usr/bin/env python3 -u
"""
Bulk-index MatchaJob codebase into Qdrant using Ollama embeddings.

Usage:
    python3 scripts/index_codebase_qdrant.py [--dry-run] [--clear]

Walks the codebase, chunks source files, generates embeddings via Ollama
(qwen3-embedding:0.6b), and upserts into the 'matchajob' Qdrant collection.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import requests

# ── Config ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "matchajob")
EMBED_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-embedding:0.6b")
CHUNK_MAX_CHARS = 2000   # max chars per chunk
CHUNK_OVERLAP = 200      # overlap between chunks
BATCH_SIZE = 20          # points per upsert batch
EMBED_BATCH = 5          # parallel embedding calls (not used yet, sequential for safety)

# File extensions to index
INDEX_EXTENSIONS = {
    ".go", ".py", ".ts", ".tsx", ".js", ".jsx",
    ".yaml", ".yml", ".sql", ".mod", ".sum",
    ".toml", ".cfg", ".ini", ".env.example",
    ".sh", ".bash",
    ".json",  # only specific ones (package.json, tsconfig, etc.)
}

# Directories to skip entirely
SKIP_DIRS = {
    "node_modules", ".next", "__pycache__", "vendor", ".git",
    "_archive", ".turbo", "dist", "build", ".cache",
    "coverage", ".nyc_output", ".pytest_cache", ".mypy_cache",
    "archive",  # api-gateway archive dir
}

# File patterns to skip
SKIP_PATTERNS = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "go.sum", ".coverage", ".DS_Store",
}

# Directories of interest (relative to REPO_ROOT)
SCAN_DIRS = [
    "backend/go",
    "backend/python",
    "backend/services",
    "apps/app-frontend/src",
    "apps/marketing/src",
    "infrastructure",
    "database",
    "packages",
    "tests",
]


def should_index(path: Path) -> bool:
    """Decide if a file should be indexed."""
    # Check extension
    if path.suffix not in INDEX_EXTENSIONS:
        return False

    # Skip known unneeded files
    if path.name in SKIP_PATTERNS:
        return False

    # Skip directories
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return False

    # For .json files, only index specific config files
    if path.suffix == ".json":
        if path.name not in {
            "package.json", "tsconfig.json", "tsconfig.build.json",
        }:
            return False

    # Skip very large files (>100KB likely auto-generated)
    try:
        if path.stat().st_size > 100_000:
            return False
    except OSError:
        return False

    return True


def classify_file(path: Path) -> Dict[str, str]:
    """Return metadata tags for a file based on its location."""
    rel = path.relative_to(REPO_ROOT)
    parts = rel.parts

    meta = {
        "file_path": str(rel),
        "extension": path.suffix,
        "filename": path.name,
    }

    # Determine category and service
    if "backend/go" in str(rel):
        meta["category"] = "backend-go"
        if len(parts) > 2:
            meta["service"] = parts[2]  # e.g. "api-gateway"
    elif "backend/python" in str(rel):
        meta["category"] = "backend-python"
        if len(parts) > 2:
            meta["service"] = parts[2]
    elif "apps/app-frontend" in str(rel):
        meta["category"] = "frontend"
        meta["service"] = "app-frontend"
    elif "apps/marketing" in str(rel):
        meta["category"] = "frontend"
        meta["service"] = "marketing"
    elif "infrastructure" in str(rel):
        meta["category"] = "infrastructure"
    elif "database" in str(rel):
        meta["category"] = "database"
    elif "packages" in str(rel):
        meta["category"] = "shared-packages"
        if len(parts) > 1:
            meta["service"] = parts[1]
    elif "tests" in str(rel):
        meta["category"] = "tests"
    else:
        meta["category"] = "other"

    # Detect sub-type
    if "middleware" in str(rel).lower():
        meta["sub_type"] = "middleware"
    elif "route" in path.name.lower():
        meta["sub_type"] = "routes"
    elif "handler" in path.name.lower():
        meta["sub_type"] = "handler"
    elif "model" in path.name.lower():
        meta["sub_type"] = "model"
    elif "config" in path.name.lower():
        meta["sub_type"] = "config"
    elif path.name in ("main.go", "main.py", "app.py"):
        meta["sub_type"] = "entrypoint"
    elif "test" in path.name.lower() or "spec" in path.name.lower():
        meta["sub_type"] = "test"
    elif path.name.startswith("Dockerfile"):
        meta["sub_type"] = "dockerfile"
    elif path.suffix in (".yaml", ".yml"):
        meta["sub_type"] = "k8s-config"

    return meta


def chunk_text(text: str, file_path: str, max_chars: int = CHUNK_MAX_CHARS,
               overlap: int = CHUNK_OVERLAP) -> List[Tuple[str, int]]:
    """
    Split text into chunks by lines, respecting max_chars.
    Returns list of (chunk_text, start_line).
    """
    lines = text.split("\n")
    chunks = []
    current_chunk_lines = []
    current_chars = 0
    start_line = 1

    for i, line in enumerate(lines, 1):
        line_len = len(line) + 1  # +1 for newline
        if current_chars + line_len > max_chars and current_chunk_lines:
            chunk_text_str = "\n".join(current_chunk_lines)
            # Prepend file path header
            header = f"# File: {file_path} (lines {start_line}-{i-1})\n"
            chunks.append((header + chunk_text_str, start_line))

            # Overlap: keep last N chars worth of lines
            overlap_lines = []
            overlap_chars = 0
            for prev_line in reversed(current_chunk_lines):
                if overlap_chars + len(prev_line) + 1 > overlap:
                    break
                overlap_lines.insert(0, prev_line)
                overlap_chars += len(prev_line) + 1

            current_chunk_lines = overlap_lines
            current_chars = overlap_chars
            start_line = i - len(overlap_lines)

        current_chunk_lines.append(line)
        current_chars += line_len

    # Remaining chunk
    if current_chunk_lines:
        chunk_text_str = "\n".join(current_chunk_lines)
        end_line = len(lines)
        header = f"# File: {file_path} (lines {start_line}-{end_line})\n"
        chunks.append((header + chunk_text_str, start_line))

    return chunks


def get_embedding(text: str) -> Optional[List[float]]:
    """Get embedding from Ollama."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("embedding")
    except Exception as e:
        print(f"  [WARN] Embedding failed: {e}")
        return None


def upsert_batch(points: List[Dict]) -> bool:
    """Upsert a batch of points into Qdrant."""
    try:
        resp = requests.put(
            f"{QDRANT_URL}/collections/{COLLECTION}/points",
            json={"points": points},
            timeout=60,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  [ERROR] Qdrant upsert failed: {e}")
        return False


def delete_all_points() -> bool:
    """Delete all existing points from the collection."""
    try:
        resp = requests.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/delete",
            json={"filter": {}},
            timeout=30,
        )
        resp.raise_for_status()
        print(f"  Cleared all points from '{COLLECTION}'")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to clear collection: {e}")
        return False


def collect_files() -> List[Path]:
    """Collect all files to index."""
    files = []
    for scan_dir in SCAN_DIRS:
        full_dir = REPO_ROOT / scan_dir
        if not full_dir.exists():
            continue
        for root, dirs, filenames in os.walk(full_dir):
            # Prune skip dirs
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in filenames:
                fpath = Path(root) / fname
                if should_index(fpath):
                    files.append(fpath)

    # Also add root-level config files
    for f in REPO_ROOT.iterdir():
        if f.is_file() and f.suffix in {".json", ".yaml", ".yml", ".toml"} and f.name not in SKIP_PATTERNS:
            if f.name in {"package.json", "docker-compose.yaml", "docker-compose.yml"}:
                files.append(f)

    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description="Index MatchaJob codebase into Qdrant")
    parser.add_argument("--dry-run", action="store_true", help="List files without indexing")
    parser.add_argument("--clear", action="store_true", help="Clear collection before indexing")
    parser.add_argument("--category", type=str, help="Only index specific category")
    args = parser.parse_args()

    print(f"MatchaJob Codebase Indexer → Qdrant")
    print(f"  Repo root:  {REPO_ROOT}")
    print(f"  Qdrant:     {QDRANT_URL}/{COLLECTION}")
    print(f"  Ollama:     {OLLAMA_URL} ({EMBED_MODEL})")
    print()

    # Collect files
    files = collect_files()
    print(f"Found {len(files)} files to index")

    if args.dry_run:
        for f in files:
            meta = classify_file(f)
            print(f"  [{meta['category']}] {meta['file_path']}")
        print(f"\nTotal: {len(files)} files (dry run, nothing indexed)")
        return

    # Optionally clear
    if args.clear:
        print("\nClearing existing collection data...")
        delete_all_points()
        time.sleep(1)

    # Index files
    total_chunks = 0
    total_files = 0
    failed_files = 0
    batch_points = []
    start_time = time.time()

    for idx, fpath in enumerate(files):
        rel_path = str(fpath.relative_to(REPO_ROOT))
        meta = classify_file(fpath)

        if args.category and meta.get("category") != args.category:
            continue

        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  [{idx+1}/{len(files)}] SKIP {rel_path}: {e}")
            failed_files += 1
            continue

        if not content.strip():
            continue

        # Chunk the file
        chunks = chunk_text(content, rel_path)

        for chunk_idx, (chunk_text_str, start_line) in enumerate(chunks):
            # Generate embedding
            embedding = get_embedding(chunk_text_str)
            if not embedding:
                failed_files += 1
                continue

            # Create point
            point_id = str(uuid.uuid4())
            point = {
                "id": point_id,
                "vector": embedding,
                "payload": {
                    "text": chunk_text_str,
                    "metadata": json.dumps(meta),
                    **meta,
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks),
                    "start_line": start_line,
                    "content_hash": hashlib.md5(chunk_text_str.encode()).hexdigest(),
                },
            }
            batch_points.append(point)
            total_chunks += 1

            # Upsert when batch is full
            if len(batch_points) >= BATCH_SIZE:
                ok = upsert_batch(batch_points)
                if ok:
                    print(f"  [{idx+1}/{len(files)}] Indexed {total_chunks} chunks ({rel_path})")
                batch_points = []

        total_files += 1

    # Flush remaining batch
    if batch_points:
        upsert_batch(batch_points)
        print(f"  Final batch: {len(batch_points)} chunks")

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Indexing complete!")
    print(f"  Files indexed:  {total_files}")
    print(f"  Total chunks:   {total_chunks}")
    print(f"  Failed:         {failed_files}")
    print(f"  Time:           {elapsed:.1f}s")
    print(f"  Avg:            {elapsed/max(total_chunks,1)*1000:.0f}ms per chunk")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

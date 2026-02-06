"""Ollqd data models."""

import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileInfo:
    path: str
    abs_path: str
    language: str
    size_bytes: int
    content_hash: str


@dataclass
class Chunk:
    file_path: str
    language: str
    chunk_index: int
    total_chunks: int
    start_line: int
    end_line: int
    content: str
    content_hash: str

    @property
    def point_id(self) -> str:
        raw = f"{self.file_path}::chunk_{self.chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()


@dataclass
class SearchResult:
    score: float
    file_path: str
    language: str
    lines: str
    chunk: str
    content: str


@dataclass
class IndexingStats:
    files_discovered: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    chunks_created: int = 0
    chunks_failed: int = 0
    elapsed_seconds: float = 0.0

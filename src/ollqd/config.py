"""Ollqd configuration — dataclass-based with env var overrides."""

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class OllamaConfig:
    base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    chat_model: str = field(default_factory=lambda: os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:14b"))
    embed_model: str = field(default_factory=lambda: os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"))
    timeout_s: float = field(default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT_S", "120")))


@dataclass(slots=True)
class QdrantConfig:
    url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    default_collection: str = field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "codebase"))


@dataclass(slots=True)
class ChunkingConfig:
    chunk_size: int = field(default_factory=lambda: int(os.getenv("CHUNK_SIZE", "512")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "64")))
    max_file_size_kb: int = 512


@dataclass(slots=True)
class ServerConfig:
    name: str = "ollqd-rag-server"
    transport: str = "stdio"


@dataclass(slots=True)
class ClientConfig:
    max_tool_rounds: int = field(default_factory=lambda: int(os.getenv("MAX_TOOL_ROUNDS", "6")))


@dataclass(slots=True)
class AppConfig:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    client: ClientConfig = field(default_factory=ClientConfig)

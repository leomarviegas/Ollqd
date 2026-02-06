"""Ollqd exception hierarchy."""


class OllqdError(Exception):
    """Base exception for all Ollqd errors."""


class ConfigError(OllqdError):
    """Invalid or missing configuration."""


class EmbeddingError(OllqdError):
    """Failed to generate embeddings via Ollama."""


class VectorStoreError(OllqdError):
    """Qdrant operation failed."""


class ChunkingError(OllqdError):
    """File chunking failed."""


class MCPToolError(OllqdError):
    """MCP tool execution failed."""


class MCPClientError(OllqdError):
    """MCP client connection or protocol error."""

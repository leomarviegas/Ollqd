"""Ollqd configuration — dataclass-based with env var overrides."""

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class OllamaConfig:
    base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    chat_model: str = field(default_factory=lambda: os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:14b"))
    embed_model: str = field(default_factory=lambda: os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b"))
    vision_model: str = field(default_factory=lambda: os.getenv("OLLAMA_VISION_MODEL", "llava:7b"))
    timeout_s: float = field(default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT_S", "120")))


@dataclass(slots=True)
class QdrantConfig:
    url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    default_collection: str = field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "codebase"))
    default_distance: str = field(default_factory=lambda: os.getenv("QDRANT_DISTANCE", "Cosine"))


@dataclass(slots=True)
class ChunkingConfig:
    chunk_size: int = field(default_factory=lambda: int(os.getenv("CHUNK_SIZE", "512")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "64")))
    max_file_size_kb: int = 512


@dataclass(slots=True)
class ImageConfig:
    max_image_size_kb: int = field(default_factory=lambda: int(os.getenv("MAX_IMAGE_SIZE_KB", "10240")))
    caption_prompt: str = "Describe this image in detail. Include any text, objects, colors, layout, and context you observe."
    supported_extensions: tuple = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff")


@dataclass(slots=True)
class UploadConfig:
    upload_dir: str = field(default_factory=lambda: os.getenv("UPLOAD_DIR", "/uploads"))
    max_file_size_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")))
    allowed_extensions: tuple = (
        ".md", ".txt", ".rst", ".html", ".pdf",
        ".docx", ".xlsx", ".pptx",
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff",
    )


@dataclass(slots=True)
class PIIConfig:
    enabled: bool = field(default_factory=lambda: os.getenv("PII_MASKING_ENABLED", "false").lower() == "true")
    use_spacy: bool = field(default_factory=lambda: os.getenv("PII_USE_SPACY", "true").lower() == "true")
    mask_embeddings: bool = field(default_factory=lambda: os.getenv("PII_MASK_EMBEDDINGS", "false").lower() == "true")
    enabled_types: str = field(default_factory=lambda: os.getenv("PII_ENABLED_TYPES", "all"))


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
    image: ImageConfig = field(default_factory=ImageConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)
    pii: PIIConfig = field(default_factory=PIIConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    mounted_paths: list[str] = field(
        default_factory=lambda: [
            p.strip() for p in os.getenv("MOUNTED_PATHS", "/Users,/tmp").split(",") if p.strip()
        ]
    )

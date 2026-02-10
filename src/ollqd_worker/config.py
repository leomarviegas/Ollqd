"""Ollqd configuration — dataclass-based with env var overrides."""

import json
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("ollqd.worker.config")


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
        ".csv", ".adoc", ".asciidoc",
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff",
    )


@dataclass(slots=True)
class PIIConfig:
    enabled: bool = field(default_factory=lambda: os.getenv("PII_MASKING_ENABLED", "false").lower() == "true")
    use_spacy: bool = field(default_factory=lambda: os.getenv("PII_USE_SPACY", "true").lower() == "true")
    mask_embeddings: bool = field(default_factory=lambda: os.getenv("PII_MASK_EMBEDDINGS", "false").lower() == "true")
    enabled_types: str = field(default_factory=lambda: os.getenv("PII_ENABLED_TYPES", "all"))


@dataclass(slots=True)
class DoclingConfig:
    enabled: bool = field(default_factory=lambda: os.getenv("DOCLING_ENABLED", "true").lower() == "true")
    ocr_enabled: bool = field(default_factory=lambda: os.getenv("DOCLING_OCR_ENABLED", "true").lower() == "true")
    ocr_engine: str = field(default_factory=lambda: os.getenv("DOCLING_OCR_ENGINE", "easyocr"))
    table_structure: bool = field(default_factory=lambda: os.getenv("DOCLING_TABLE_STRUCTURE", "true").lower() == "true")
    timeout_s: float = field(default_factory=lambda: float(os.getenv("DOCLING_TIMEOUT_S", "300")))


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
    docling: DoclingConfig = field(default_factory=DoclingConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    mounted_paths: list[str] = field(
        default_factory=lambda: [
            p.strip() for p in os.getenv("MOUNTED_PATHS", "/Users,/tmp").split(",") if p.strip()
        ]
    )


# Singleton instance
_config: AppConfig | None = None


def _to_bool(s: str) -> bool:
    return s.lower() in ("true", "1", "yes")


def _to_float(s: str) -> float:
    return float(s)


def _apply_db_overrides(cfg: AppConfig) -> None:
    """Overlay persisted DB overrides onto the in-memory config."""
    try:
        from . import config_db
        overrides = config_db.load_overrides()
    except Exception:
        log.debug("No config DB overrides loaded (DB not initialised yet)")
        return

    if not overrides:
        return

    pii = overrides.get("pii", {})
    if "enabled" in pii:
        cfg.pii.enabled = _to_bool(pii["enabled"])
    if "use_spacy" in pii:
        cfg.pii.use_spacy = _to_bool(pii["use_spacy"])
    if "mask_embeddings" in pii:
        cfg.pii.mask_embeddings = _to_bool(pii["mask_embeddings"])
    if "enabled_types" in pii:
        cfg.pii.enabled_types = pii["enabled_types"]

    docling = overrides.get("docling", {})
    if "enabled" in docling:
        cfg.docling.enabled = _to_bool(docling["enabled"])
    if "ocr_enabled" in docling:
        cfg.docling.ocr_enabled = _to_bool(docling["ocr_enabled"])
    if "ocr_engine" in docling:
        cfg.docling.ocr_engine = docling["ocr_engine"]
    if "table_structure" in docling:
        cfg.docling.table_structure = _to_bool(docling["table_structure"])
    if "timeout_s" in docling:
        cfg.docling.timeout_s = _to_float(docling["timeout_s"])

    ollama = overrides.get("ollama", {})
    if "base_url" in ollama:
        cfg.ollama.base_url = ollama["base_url"]
    if "chat_model" in ollama:
        cfg.ollama.chat_model = ollama["chat_model"]
    if "embed_model" in ollama:
        cfg.ollama.embed_model = ollama["embed_model"]
    if "vision_model" in ollama:
        cfg.ollama.vision_model = ollama["vision_model"]
    if "timeout_s" in ollama:
        cfg.ollama.timeout_s = _to_float(ollama["timeout_s"])

    qdrant = overrides.get("qdrant", {})
    if "url" in qdrant:
        cfg.qdrant.url = qdrant["url"]
    if "default_collection" in qdrant:
        cfg.qdrant.default_collection = qdrant["default_collection"]
    if "default_distance" in qdrant:
        cfg.qdrant.default_distance = qdrant["default_distance"]

    chunking = overrides.get("chunking", {})
    if "chunk_size" in chunking:
        cfg.chunking.chunk_size = int(chunking["chunk_size"])
    if "chunk_overlap" in chunking:
        cfg.chunking.chunk_overlap = int(chunking["chunk_overlap"])
    if "max_file_size_kb" in chunking:
        cfg.chunking.max_file_size_kb = int(chunking["max_file_size_kb"])

    image = overrides.get("image", {})
    if "max_image_size_kb" in image:
        cfg.image.max_image_size_kb = int(image["max_image_size_kb"])
    if "caption_prompt" in image:
        cfg.image.caption_prompt = image["caption_prompt"]

    app = overrides.get("app", {})
    if "mounted_paths" in app:
        try:
            cfg.mounted_paths = json.loads(app["mounted_paths"])
        except (json.JSONDecodeError, TypeError):
            pass

    log.info("Applied DB config overrides: %s", list(overrides.keys()))


def get_config() -> AppConfig:
    """Return the global AppConfig singleton, creating it on first call."""
    global _config
    if _config is None:
        _config = AppConfig()
        _apply_db_overrides(_config)
    return _config


def reset_config() -> AppConfig:
    """Force re-creation of the config singleton from env vars + DB overrides.

    Call this after deleting DB overrides so the in-memory config reflects
    the remaining (or absent) overrides.
    """
    global _config
    _config = AppConfig()
    _apply_db_overrides(_config)
    log.info("Config singleton re-created from env vars + DB overrides")
    return _config

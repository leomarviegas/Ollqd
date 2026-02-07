"""FastAPI dependency injection — singletons for config, Qdrant, Ollama."""

from functools import lru_cache
from typing import AsyncGenerator

from qdrant_client import QdrantClient

from ..config import AppConfig
from ..embedder import OllamaEmbedder
from .services.ollama_service import OllamaService
from .services.pii_service import PIIMaskingService
from .services.smb_service import SMBManager
from .services.task_manager import TaskManager

_task_manager = TaskManager()
_smb_manager = SMBManager()
_pii_service: PIIMaskingService | None = None


@lru_cache()
def get_config() -> AppConfig:
    return AppConfig()


def get_task_manager() -> TaskManager:
    return _task_manager


def get_smb_manager() -> SMBManager:
    return _smb_manager


def get_pii_service() -> PIIMaskingService:
    global _pii_service
    if _pii_service is None:
        cfg = get_config()
        _pii_service = PIIMaskingService(use_spacy=cfg.pii.use_spacy)
    return _pii_service


def get_qdrant_client() -> QdrantClient:
    cfg = get_config()
    return QdrantClient(url=cfg.qdrant.url)


def get_embedder() -> OllamaEmbedder:
    cfg = get_config()
    return OllamaEmbedder(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embed_model,
        timeout=cfg.ollama.timeout_s,
    )


async def get_ollama_service() -> AsyncGenerator[OllamaService, None]:
    cfg = get_config()
    svc = OllamaService(base_url=cfg.ollama.base_url, timeout=cfg.ollama.timeout_s)
    try:
        yield svc
    finally:
        await svc.close()

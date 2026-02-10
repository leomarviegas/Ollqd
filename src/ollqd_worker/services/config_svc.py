"""ConfigService gRPC servicer — wraps AppConfig singleton."""

import json
import logging

import grpc

from ..config import get_config, reset_config
from .. import config_db
from ..processing.docling_converter import DOCLING_EXTENSIONS, is_available as docling_is_available

log = logging.getLogger("ollqd.worker.config")

# Try importing generated stubs; gracefully degrade if not yet generated.
try:
    from ..gen.ollqd.v1 import processing_pb2 as config_pb2
    _STUBS_AVAILABLE = True
except ImportError:
    _STUBS_AVAILABLE = False


def _cfg_to_dict(cfg) -> dict:
    """Serialize the full AppConfig to a JSON-friendly dict."""
    return {
        "ollama": {
            "url": cfg.ollama.base_url,
            "chat_model": cfg.ollama.chat_model,
            "embed_model": cfg.ollama.embed_model,
            "vision_model": cfg.ollama.vision_model,
            "timeout_s": cfg.ollama.timeout_s,
        },
        "qdrant": {
            "url": cfg.qdrant.url,
            "default_collection": cfg.qdrant.default_collection,
            "default_distance": cfg.qdrant.default_distance,
        },
        "chunking": {
            "chunk_size": cfg.chunking.chunk_size,
            "chunk_overlap": cfg.chunking.chunk_overlap,
            "max_file_size_kb": cfg.chunking.max_file_size_kb,
        },
        "image": {
            "max_image_size_kb": cfg.image.max_image_size_kb,
            "caption_prompt": cfg.image.caption_prompt,
        },
        "mounted_paths": cfg.mounted_paths,
        "pii": {
            "enabled": cfg.pii.enabled,
            "use_spacy": cfg.pii.use_spacy,
            "mask_embeddings": cfg.pii.mask_embeddings,
            "enabled_types": cfg.pii.enabled_types,
        },
        "docling": {
            "enabled": cfg.docling.enabled,
            "ocr_enabled": cfg.docling.ocr_enabled,
            "ocr_engine": cfg.docling.ocr_engine,
            "table_structure": cfg.docling.table_structure,
            "timeout_s": cfg.docling.timeout_s,
        },
    }


class ConfigServiceServicer:
    """gRPC servicer for configuration management.

    Methods:
        GetConfig          — return full config as JSON
        UpdateMountedPaths — replace the mounted_paths list
        UpdatePII          — update PII masking settings
        UpdateDocling      — update Docling settings
        UpdateDistance      — update Qdrant default distance metric
        GetPIIConfig       — return PII-specific config
        GetDoclingConfig   — return Docling-specific config
    """

    async def GetConfig(self, request, context):
        """Return full configuration as an AppConfig proto message."""
        from ..gen.ollqd.v1 import types_pb2
        cfg = get_config()

        try:
            return types_pb2.AppConfig(
                ollama=types_pb2.OllamaConfig(
                    base_url=cfg.ollama.base_url,
                    chat_model=cfg.ollama.chat_model,
                    embed_model=cfg.ollama.embed_model,
                    vision_model=cfg.ollama.vision_model,
                    timeout_s=cfg.ollama.timeout_s,
                ),
                qdrant=types_pb2.QdrantConfig(
                    url=cfg.qdrant.url,
                    default_collection=cfg.qdrant.default_collection,
                    default_distance=cfg.qdrant.default_distance,
                ),
                chunking=types_pb2.ChunkingConfig(
                    chunk_size=cfg.chunking.chunk_size,
                    chunk_overlap=cfg.chunking.chunk_overlap,
                    max_file_size_kb=cfg.chunking.max_file_size_kb,
                ),
                image=types_pb2.ImageConfig(
                    max_image_size_kb=cfg.image.max_image_size_kb,
                    caption_prompt=cfg.image.caption_prompt,
                ),
                upload=types_pb2.UploadConfig(
                    upload_dir=cfg.upload.upload_dir,
                    max_file_size_mb=cfg.upload.max_file_size_mb,
                    allowed_extensions=list(cfg.upload.allowed_extensions),
                ),
                pii=types_pb2.PIIConfig(
                    enabled=cfg.pii.enabled,
                    use_spacy=cfg.pii.use_spacy,
                    mask_embeddings=cfg.pii.mask_embeddings,
                    enabled_types=cfg.pii.enabled_types,
                ),
                docling=types_pb2.DoclingConfig(
                    enabled=cfg.docling.enabled,
                    ocr_enabled=cfg.docling.ocr_enabled,
                    ocr_engine=cfg.docling.ocr_engine,
                    table_structure=cfg.docling.table_structure,
                    timeout_s=cfg.docling.timeout_s,
                ),
                mounted_paths=list(cfg.mounted_paths),
            )
        except Exception:
            # Fallback if types_pb2 not available
            payload = _cfg_to_dict(cfg)
            class _Resp:
                def __init__(self, data):
                    self.__dict__.update(data)
            return _Resp(payload)

    async def UpdateMountedPaths(self, request, context):
        """Replace the mounted_paths list with de-duplicated, trimmed paths."""
        cfg = get_config()
        paths = list(request.paths) if hasattr(request, "paths") else []
        seen = set()
        cleaned = []
        for p in paths:
            p = p.strip()
            if p and p not in seen:
                seen.add(p)
                cleaned.append(p)
        cfg.mounted_paths = cleaned
        config_db.save_overrides("app", {"mounted_paths": json.dumps(cleaned)})
        log.info("Updated mounted_paths: %s", cleaned)

        if _STUBS_AVAILABLE:
            return config_pb2.UpdateMountedPathsResponse(mounted_paths=cfg.mounted_paths)

        class _Resp:
            def __init__(self, data):
                self.paths = data
        return _Resp(cfg.mounted_paths)

    async def UpdatePII(self, request, context):
        """Update PII masking configuration fields (only non-default fields are applied)."""
        cfg = get_config()
        if hasattr(request, "enabled") and request.HasField("enabled"):
            cfg.pii.enabled = request.enabled
        if hasattr(request, "use_spacy") and request.HasField("use_spacy"):
            cfg.pii.use_spacy = request.use_spacy
        if hasattr(request, "mask_embeddings") and request.HasField("mask_embeddings"):
            cfg.pii.mask_embeddings = request.mask_embeddings
        if hasattr(request, "enabled_types") and request.enabled_types:
            cfg.pii.enabled_types = request.enabled_types

        result = {
            "enabled": cfg.pii.enabled,
            "use_spacy": cfg.pii.use_spacy,
            "mask_embeddings": cfg.pii.mask_embeddings,
            "enabled_types": cfg.pii.enabled_types,
        }
        config_db.save_overrides("pii", {k: str(v).lower() for k, v in result.items()})
        log.info("Updated PII config: %s", result)

        if _STUBS_AVAILABLE:
            return config_pb2.PIIConfigResponse(**result)

        class _Resp:
            def __init__(self, **kw):
                self.__dict__.update(kw)
        return _Resp(**result)

    async def UpdateDocling(self, request, context):
        """Update Docling configuration fields."""
        cfg = get_config()
        if hasattr(request, "enabled") and request.HasField("enabled"):
            cfg.docling.enabled = request.enabled
        if hasattr(request, "ocr_enabled") and request.HasField("ocr_enabled"):
            cfg.docling.ocr_enabled = request.ocr_enabled
        if hasattr(request, "ocr_engine") and request.ocr_engine:
            cfg.docling.ocr_engine = request.ocr_engine
        if hasattr(request, "table_structure") and request.HasField("table_structure"):
            cfg.docling.table_structure = request.table_structure
        if hasattr(request, "timeout_s") and request.timeout_s > 0:
            cfg.docling.timeout_s = request.timeout_s

        result = {
            "enabled": cfg.docling.enabled,
            "ocr_enabled": cfg.docling.ocr_enabled,
            "ocr_engine": cfg.docling.ocr_engine,
            "table_structure": cfg.docling.table_structure,
            "timeout_s": cfg.docling.timeout_s,
        }
        config_db.save_overrides("docling", {k: str(v).lower() for k, v in result.items()})
        log.info("Updated Docling config: %s", result)

        if _STUBS_AVAILABLE:
            return config_pb2.DoclingConfigResponse(**result)

        class _Resp:
            def __init__(self, **kw):
                self.__dict__.update(kw)
        return _Resp(**result)

    async def UpdateDistance(self, request, context):
        """Update the default Qdrant distance metric."""
        cfg = get_config()
        valid_distances = {"Cosine", "Euclid", "Dot", "Manhattan"}
        distance = request.distance if hasattr(request, "distance") else "Cosine"
        if distance not in valid_distances:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Invalid distance metric: {distance}. Must be one of {valid_distances}",
            )
        old = cfg.qdrant.default_distance
        cfg.qdrant.default_distance = distance
        config_db.save_overrides("qdrant", {"default_distance": distance})
        log.info("Updated distance: %s -> %s", old, distance)

        if _STUBS_AVAILABLE:
            return config_pb2.UpdateDistanceResponse(distance=distance, previous=old)

        class _Resp:
            def __init__(self, **kw):
                self.__dict__.update(kw)
        return _Resp(distance=distance, previous=old)

    async def GetPIIConfig(self, request, context):
        """Return PII-specific configuration plus spaCy availability."""
        cfg = get_config()
        from ..processing.pii_masking import PIIMaskingService
        pii_svc = PIIMaskingService(use_spacy=cfg.pii.use_spacy)

        result = {
            "enabled": cfg.pii.enabled,
            "use_spacy": cfg.pii.use_spacy,
            "mask_embeddings": cfg.pii.mask_embeddings,
            "enabled_types": cfg.pii.enabled_types,
            "spacy_available": pii_svc.is_spacy_available,
        }

        if _STUBS_AVAILABLE:
            return config_pb2.PIIConfigResponse(**result)

        class _Resp:
            def __init__(self, **kw):
                self.__dict__.update(kw)
        return _Resp(**result)

    async def GetDoclingConfig(self, request, context):
        """Return Docling-specific configuration plus availability."""
        cfg = get_config()
        result = {
            "enabled": cfg.docling.enabled,
            "ocr_enabled": cfg.docling.ocr_enabled,
            "ocr_engine": cfg.docling.ocr_engine,
            "table_structure": cfg.docling.table_structure,
            "timeout_s": cfg.docling.timeout_s,
            "available": docling_is_available(),
            "supported_extensions": sorted(DOCLING_EXTENSIONS),
        }

        if _STUBS_AVAILABLE:
            return config_pb2.DoclingConfigResponse(**result)

        class _Resp:
            def __init__(self, **kw):
                self.__dict__.update(kw)
        return _Resp(**result)

    async def ResetConfig(self, request, context):
        """Delete persisted config overrides and revert to env-var defaults."""
        valid_sections = {"pii", "docling", "qdrant", "app", ""}
        section = request.section if hasattr(request, "section") else ""
        keys = list(request.keys) if hasattr(request, "keys") and request.keys else []

        if section and section not in valid_sections:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Invalid section: {section}. Must be one of {valid_sections - {''}}",
            )

        removed = config_db.delete_overrides(section, keys or None)
        reset_config()
        log.info("Reset config: section=%r keys=%s removed=%s", section or "*", keys or "all", removed)

        if _STUBS_AVAILABLE:
            return config_pb2.ResetConfigResponse(section=section or "all", reset_keys=removed)

        class _Resp:
            def __init__(self, **kw):
                self.__dict__.update(kw)
        return _Resp(section=section or "all", reset_keys=removed)

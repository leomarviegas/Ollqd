"""System health and info endpoints."""

import math
import time

from fastapi import APIRouter, Depends, HTTPException

from ...embedder import OllamaEmbedder
from ..deps import get_config, get_embedder, get_ollama_service, get_pii_service
from ..models import (
    CompareEmbedRequest,
    TestEmbedRequest,
    TestPIIMaskingRequest,
    UpdateDistanceConfigRequest,
    UpdateDoclingConfigRequest,
    UpdateEmbedModelRequest,
    UpdateMountedPathsRequest,
    UpdatePIIConfigRequest,
)
from ..services.ollama_service import OllamaService

router = APIRouter()


@router.get("/health")
async def health_check(
    ollama: OllamaService = Depends(get_ollama_service),
):
    cfg = get_config()
    ollama_ok = await ollama.is_healthy()

    qdrant_ok = False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5) as c:
            resp = await c.get(f"{cfg.qdrant.url}/collections")
            qdrant_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "ollama": "ok" if ollama_ok else "down",
        "qdrant": "ok" if qdrant_ok else "down",
        "ollama_url": cfg.ollama.base_url,
        "qdrant_url": cfg.qdrant.url,
    }


@router.get("/config")
async def get_system_config():
    cfg = get_config()
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


@router.put("/config/mounted-paths")
async def update_mounted_paths(req: UpdateMountedPathsRequest):
    cfg = get_config()
    seen = set()
    cleaned = []
    for p in req.paths:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            cleaned.append(p)
    cfg.mounted_paths = cleaned
    return {"mounted_paths": cfg.mounted_paths}


# ── Embedding Management ────────────────────────────────────


def _embed_probe(embedder: OllamaEmbedder) -> dict:
    """Run a quick probe embed to get dimension and latency."""
    t0 = time.time()
    dim = embedder.get_dimension()
    latency_ms = int((time.time() - t0) * 1000)
    return {"dimension": dim, "latency_ms": latency_ms}


def _vector_stats(vec: list[float]) -> dict:
    n = len(vec)
    mn = min(vec)
    mx = max(vec)
    mean = sum(vec) / n
    variance = sum((x - mean) ** 2 for x in vec) / n
    stdev = math.sqrt(variance)
    norm = math.sqrt(sum(x * x for x in vec))
    return {
        "dimension": n,
        "min": round(mn, 6),
        "max": round(mx, 6),
        "mean": round(mean, 6),
        "stdev": round(stdev, 6),
        "norm": round(norm, 6),
    }


@router.get("/config/embedding")
def get_embedding_config():
    cfg = get_config()
    embedder = get_embedder()
    try:
        info = _embed_probe(embedder)
        return {"model": cfg.ollama.embed_model, **info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        embedder.close()


@router.put("/config/embedding")
def update_embedding_model(req: UpdateEmbedModelRequest):
    cfg = get_config()
    old_model = cfg.ollama.embed_model
    # Test new model before switching
    test_embedder = OllamaEmbedder(
        base_url=cfg.ollama.base_url,
        model=req.model,
        timeout=cfg.ollama.timeout_s,
    )
    try:
        info = _embed_probe(test_embedder)
    except Exception as e:
        test_embedder.close()
        raise HTTPException(status_code=400, detail=f"Model test failed: {e}")
    finally:
        test_embedder.close()
    cfg.ollama.embed_model = req.model
    return {"model": req.model, "previous": old_model, **info}


@router.post("/config/embedding/test")
def test_embedding(req: TestEmbedRequest):
    embedder = get_embedder()
    try:
        t0 = time.time()
        vectors = embedder.embed_texts([req.text])
        latency_ms = int((time.time() - t0) * 1000)
        stats = _vector_stats(vectors[0])
        stats["latency_ms"] = latency_ms
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        embedder.close()


@router.post("/config/embedding/compare")
def compare_embeddings(req: CompareEmbedRequest):
    cfg = get_config()

    def _run_model(model_name: str) -> dict:
        emb = OllamaEmbedder(
            base_url=cfg.ollama.base_url,
            model=model_name,
            timeout=cfg.ollama.timeout_s,
        )
        try:
            t0 = time.time()
            vectors = emb.embed_texts([req.text])
            latency_ms = int((time.time() - t0) * 1000)
            stats = _vector_stats(vectors[0])
            stats["latency_ms"] = latency_ms
            stats["model"] = model_name
            return stats
        except Exception as e:
            return {"model": model_name, "error": str(e)}
        finally:
            emb.close()

    return {
        "model1": _run_model(req.model1),
        "model2": _run_model(req.model2),
        "text": req.text,
    }


# ── Distance Metric Configuration ──────────────────────────


@router.put("/config/distance")
def update_distance_config(req: UpdateDistanceConfigRequest):
    cfg = get_config()
    old = cfg.qdrant.default_distance
    cfg.qdrant.default_distance = req.distance
    return {"distance": req.distance, "previous": old}


# ── PII Masking Configuration ─────────────────────────────


@router.get("/config/pii")
def get_pii_config():
    cfg = get_config()
    pii_svc = get_pii_service()
    return {
        "enabled": cfg.pii.enabled,
        "use_spacy": cfg.pii.use_spacy,
        "mask_embeddings": cfg.pii.mask_embeddings,
        "enabled_types": cfg.pii.enabled_types,
        "spacy_available": pii_svc.is_spacy_available,
    }


@router.put("/config/pii")
def update_pii_config(req: UpdatePIIConfigRequest):
    cfg = get_config()
    if req.enabled is not None:
        cfg.pii.enabled = req.enabled
    if req.use_spacy is not None:
        cfg.pii.use_spacy = req.use_spacy
    if req.mask_embeddings is not None:
        cfg.pii.mask_embeddings = req.mask_embeddings
    if req.enabled_types is not None:
        cfg.pii.enabled_types = req.enabled_types
    return {
        "enabled": cfg.pii.enabled,
        "use_spacy": cfg.pii.use_spacy,
        "mask_embeddings": cfg.pii.mask_embeddings,
        "enabled_types": cfg.pii.enabled_types,
    }


@router.get("/config/docling")
def get_docling_config():
    cfg = get_config()
    from ...docling_converter import DOCLING_EXTENSIONS, is_available
    return {
        "enabled": cfg.docling.enabled,
        "ocr_enabled": cfg.docling.ocr_enabled,
        "ocr_engine": cfg.docling.ocr_engine,
        "table_structure": cfg.docling.table_structure,
        "timeout_s": cfg.docling.timeout_s,
        "available": is_available(),
        "supported_extensions": sorted(DOCLING_EXTENSIONS),
    }


@router.put("/config/docling")
def update_docling_config(req: UpdateDoclingConfigRequest):
    cfg = get_config()
    if req.enabled is not None:
        cfg.docling.enabled = req.enabled
    if req.ocr_enabled is not None:
        cfg.docling.ocr_enabled = req.ocr_enabled
    if req.ocr_engine is not None:
        cfg.docling.ocr_engine = req.ocr_engine
    if req.table_structure is not None:
        cfg.docling.table_structure = req.table_structure
    if req.timeout_s is not None:
        cfg.docling.timeout_s = req.timeout_s
    return {
        "enabled": cfg.docling.enabled,
        "ocr_enabled": cfg.docling.ocr_enabled,
        "ocr_engine": cfg.docling.ocr_engine,
        "table_structure": cfg.docling.table_structure,
        "timeout_s": cfg.docling.timeout_s,
    }


@router.post("/config/pii/test")
def test_pii_masking(req: TestPIIMaskingRequest):
    pii_svc = get_pii_service()
    registry = pii_svc.create_registry()
    masked = pii_svc.mask_text(req.text, registry)
    return {
        "original": req.text,
        "masked": masked,
        "entities": [
            {"token": token, "original": value}
            for token, value in registry.token_to_value.items()
        ],
        "entity_count": len(registry.token_to_value),
    }

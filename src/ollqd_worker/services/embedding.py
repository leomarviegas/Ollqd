"""EmbeddingService gRPC servicer — wraps OllamaEmbedder for embedding operations."""

import json
import logging
import math
import time

import grpc

from ..config import get_config
from ..processing.embedder import OllamaEmbedder

log = logging.getLogger("ollqd.worker.embedding")

try:
    from ..gen.ollqd.v1 import processing_pb2 as embedding_pb2
    _STUBS_AVAILABLE = True
except ImportError:
    _STUBS_AVAILABLE = False


def _vector_stats(vec: list[float]) -> dict:
    """Compute summary statistics for an embedding vector."""
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


def _embed_probe(embedder: OllamaEmbedder) -> dict:
    """Run a quick probe embed to get dimension and latency."""
    t0 = time.time()
    dim = embedder.get_dimension()
    latency_ms = int((time.time() - t0) * 1000)
    return {"dimension": dim, "latency_ms": latency_ms}


def _make_embedder() -> OllamaEmbedder:
    """Create a fresh OllamaEmbedder from the current config."""
    cfg = get_config()
    return OllamaEmbedder(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embed_model,
        timeout=cfg.ollama.timeout_s,
    )


class _Response:
    """Fallback response object when proto stubs are not generated."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


class EmbeddingServiceServicer:
    """gRPC servicer for embedding management.

    Methods:
        GetInfo       — probe current embed model for dimension + latency
        TestEmbed     — embed text, return vector stats
        CompareModels — run two models side by side, return stats for both
        SetModel      — switch the active embedding model
    """

    async def GetInfo(self, request, context):
        """Probe the current embedding model for dimension and latency."""
        embedder = _make_embedder()
        try:
            info = _embed_probe(embedder)
            cfg = get_config()
            result = {"model": cfg.ollama.embed_model, **info}
            if _STUBS_AVAILABLE:
                return embedding_pb2.EmbeddingInfoResponse(**result)
            return _Response(**result)
        except Exception as e:
            log.error("GetInfo failed: %s", e)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
        finally:
            embedder.close()

    async def TestEmbed(self, request, context):
        """Embed the given text and return vector statistics."""
        text = request.text if hasattr(request, "text") else ""
        if not text:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "text is required")

        embedder = _make_embedder()
        try:
            t0 = time.time()
            vectors = embedder.embed_texts([text])
            latency_ms = int((time.time() - t0) * 1000)
            stats = _vector_stats(vectors[0])
            stats["latency_ms"] = latency_ms

            if _STUBS_AVAILABLE:
                return embedding_pb2.TestEmbedResponse(**stats)
            return _Response(**stats)
        except Exception as e:
            log.error("TestEmbed failed: %s", e)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
        finally:
            embedder.close()

    async def CompareModels(self, request, context):
        """Run two embedding models on the same text and compare their stats."""
        text = request.text if hasattr(request, "text") else ""
        model1 = request.model1 if hasattr(request, "model1") else ""
        model2 = request.model2 if hasattr(request, "model2") else ""

        if not text or not model1 or not model2:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "text, model1, and model2 are required"
            )

        cfg = get_config()

        def _run_model(model_name: str) -> dict:
            emb = OllamaEmbedder(
                base_url=cfg.ollama.base_url,
                model=model_name,
                timeout=cfg.ollama.timeout_s,
            )
            try:
                t0 = time.time()
                vectors = emb.embed_texts([text])
                latency_ms = int((time.time() - t0) * 1000)
                stats = _vector_stats(vectors[0])
                stats["latency_ms"] = latency_ms
                stats["model"] = model_name
                return stats
            except Exception as e:
                return {"model": model_name, "error": str(e)}
            finally:
                emb.close()

        result1 = _run_model(model1)
        result2 = _run_model(model2)

        if _STUBS_AVAILABLE:
            return embedding_pb2.CompareModelsResponse(
                model1=embedding_pb2.ModelTestResult(**result1),
                model2=embedding_pb2.ModelTestResult(**result2),
                text=text,
            )
        return _Response(model1=result1, model2=result2, text=text)

    async def SetModel(self, request, context):
        """Switch the active embedding model after validating it works."""
        model = request.model if hasattr(request, "model") else ""
        if not model:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "model is required")

        cfg = get_config()
        old_model = cfg.ollama.embed_model

        # Test the new model before switching
        test_embedder = OllamaEmbedder(
            base_url=cfg.ollama.base_url,
            model=model,
            timeout=cfg.ollama.timeout_s,
        )
        try:
            info = _embed_probe(test_embedder)
        except Exception as e:
            test_embedder.close()
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, f"Model test failed: {e}"
            )
        finally:
            test_embedder.close()

        cfg.ollama.embed_model = model
        log.info("Switched embedding model: %s -> %s", old_model, model)

        result = {"model": model, "previous_model": old_model, **info}
        if _STUBS_AVAILABLE:
            return embedding_pb2.EmbeddingInfoResponse(**result)
        return _Response(**result)

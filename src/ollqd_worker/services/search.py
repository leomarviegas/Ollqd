"""SearchService gRPC servicer — semantic search over Qdrant collections."""

import json
import logging

import grpc

from ..config import get_config
from ..processing.embedder import OllamaEmbedder
from ..processing.vectorstore import QdrantManager

log = logging.getLogger("ollqd.worker.search")

try:
    from ..gen.ollqd.v1 import processing_pb2 as search_pb2
    from ..gen.ollqd.v1 import types_pb2
    _STUBS_AVAILABLE = True
except ImportError:
    _STUBS_AVAILABLE = False


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


class SearchServiceServicer:
    """gRPC servicer for semantic search.

    Methods:
        Search           — search the default collection ("codebase")
        SearchCollection — search a specified collection
    """

    async def Search(self, request, context):
        """Search the default 'codebase' collection."""
        return await self._do_search(request, context, collection="codebase")

    async def SearchCollection(self, request, context):
        """Search a specific collection by name."""
        collection = request.collection if hasattr(request, "collection") else ""
        if not collection:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "collection is required"
            )
        return await self._do_search(request, context, collection=collection)

    async def _do_search(self, request, context, collection: str):
        """Internal: embed query and search Qdrant."""
        query = request.query if hasattr(request, "query") else ""
        if not query:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "query is required")

        top_k = request.top_k if hasattr(request, "top_k") and request.top_k > 0 else 5
        language = request.language if hasattr(request, "language") and request.language else None
        file_path = request.file_path if hasattr(request, "file_path") and request.file_path else None

        cfg = get_config()
        embedder = _make_embedder()
        try:
            dim = embedder.get_dimension()
            qdrant = QdrantManager(
                url=cfg.qdrant.url,
                collection=collection,
                dimension=dim,
            )
            query_vec = embedder.embed_query(query)
            hits = qdrant.search(
                query_vec,
                top_k=top_k,
                language=language,
                file_filter=file_path,
            )

            log.info(
                "Search '%s' in '%s': %d results (top_k=%d)",
                query[:50], collection, len(hits), top_k,
            )

            if _STUBS_AVAILABLE:
                result_msgs = []
                for h in hits:
                    result_msgs.append(types_pb2.SearchHit(
                        score=h.get("score", 0.0),
                        file_path=h.get("file_path", ""),
                        language=h.get("language", ""),
                        lines=h.get("lines", ""),
                        chunk_info=h.get("chunk", ""),
                        content=h.get("content", ""),
                    ))
                return search_pb2.SearchResponse(
                    status="ok",
                    query=query,
                    collection=collection,
                    results=result_msgs,
                )

            return _Response(
                status="ok",
                query=query,
                collection=collection,
                results=hits,
            )

        except Exception as e:
            log.error("Search failed: %s", e)
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
        finally:
            embedder.close()

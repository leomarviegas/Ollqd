"""ChatService gRPC servicer — RAG chat with server-streaming responses."""

import json
import logging

import grpc

from ..config import get_config
from ..processing.embedder import OllamaEmbedder
from ..processing.ollama_client import OllamaService
from ..processing.pii_masking import PII_SYSTEM_INSTRUCTION, PIIMaskingService
from ..processing.vectorstore import QdrantManager

log = logging.getLogger("ollqd.worker.chat")

try:
    from ..gen.ollqd.v1 import processing_pb2 as chat_pb2
    from ..gen.ollqd.v1 import types_pb2
    _STUBS_AVAILABLE = True
except ImportError:
    _STUBS_AVAILABLE = False

# Module-level lazy singletons
_pii_service: PIIMaskingService | None = None


def _get_pii_service() -> PIIMaskingService:
    global _pii_service
    if _pii_service is None:
        cfg = get_config()
        _pii_service = PIIMaskingService(use_spacy=cfg.pii.use_spacy)
    return _pii_service


def _make_embedder() -> OllamaEmbedder:
    cfg = get_config()
    return OllamaEmbedder(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embed_model,
        timeout=cfg.ollama.timeout_s,
    )


def _make_chat_event(event_type: str, **kwargs):
    """Build a ChatEvent, using stubs if available or a fallback dict."""
    if _STUBS_AVAILABLE:
        return chat_pb2.ChatEvent(type=event_type, **kwargs)

    class _Event:
        def __init__(self, **kw):
            self.__dict__.update(kw)
    return _Event(type=event_type, **kwargs)


class ChatServiceServicer:
    """gRPC servicer for RAG chat (server streaming).

    The Chat RPC:
      1. Embeds the user query via OllamaEmbedder
      2. Searches Qdrant for top-k context hits
      3. Optionally masks PII in query + context
      4. Builds the prompt (system + context + user query)
      5. Streams the Ollama response back as ChatEvent messages
      6. Optionally unmasks PII tokens in the streamed output
      7. Yields source references and a final done event
    """

    async def Chat(self, request, context):
        """Server-streaming RPC: yields ChatEvent messages."""
        cfg = get_config()
        pii_svc = _get_pii_service()

        # Parse request fields
        query = request.message if hasattr(request, "message") else ""
        collection = request.collection if hasattr(request, "collection") and request.collection else "codebase"
        model = request.model if hasattr(request, "model") and request.model else cfg.ollama.chat_model
        pii_enabled = request.pii_enabled if hasattr(request, "pii_enabled") else cfg.pii.enabled

        if not query:
            yield _make_chat_event("error", content="query is required")
            return

        # Per-turn PII registry
        registry = pii_svc.create_registry() if pii_enabled else None

        # ── Step 1: Semantic search for context ──
        sources = []
        context_text = ""
        embedder = _make_embedder()
        try:
            dim = embedder.get_dimension()
            qdrant = QdrantManager(
                url=cfg.qdrant.url,
                collection=collection,
                dimension=dim,
            )
            query_vec = embedder.embed_query(query)
            sources = qdrant.search(query_vec, top_k=5)
            context_parts = []
            for s in sources:
                if s.get("language") == "image":
                    context_parts.append(f"[Image: {s['file_path']}]\nCaption: {s['content']}")
                else:
                    context_parts.append(f"[{s['file_path']} L{s['lines']}]\n{s['content']}")
            context_text = "\n\n".join(context_parts)
        except Exception as e:
            log.warning("Search failed, chatting without context: %s", e)
        finally:
            embedder.close()

        # ── Step 2: PII masking ──
        if registry is not None:
            masked_query = pii_svc.mask_text(query, registry)
            masked_context = pii_svc.mask_text(context_text, registry) if context_text else ""
        else:
            masked_query = query
            masked_context = context_text

        # ── Step 3: Build messages ──
        system_content = (
            "You are a helpful assistant with access to code and image context. "
            "Use the following context to answer questions. "
            "For code, cite file paths and line numbers. "
            "For images, describe what you know from the captions."
        )
        if registry is not None and registry.has_entities:
            system_content = PII_SYSTEM_INSTRUCTION + "\n\n" + system_content
        if masked_context:
            system_content += "\n\n" + masked_context

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": masked_query},
        ]

        # ── Step 4: Stream Ollama response ──
        ollama = OllamaService(base_url=cfg.ollama.base_url, timeout=cfg.ollama.timeout_s)
        pii_info = {}
        try:
            if registry is not None and registry.has_entities:
                buffer = pii_svc.create_stream_buffer(registry)
                async for chunk in ollama.chat_stream(model=model, messages=messages):
                    if context.cancelled():
                        yield _make_chat_event("cancelled", content="Request cancelled by client")
                        return
                    unmasked = buffer.feed(chunk)
                    if unmasked:
                        yield _make_chat_event("chunk", content=unmasked)
                remaining = buffer.flush()
                if remaining:
                    yield _make_chat_event("chunk", content=remaining)
                pii_info = {
                    "pii_masked": True,
                    "pii_entities_count": len(registry.token_to_value),
                }
            else:
                async for chunk in ollama.chat_stream(model=model, messages=messages):
                    if context.cancelled():
                        yield _make_chat_event("cancelled", content="Request cancelled by client")
                        return
                    yield _make_chat_event("chunk", content=chunk)
        except Exception as e:
            log.error("Chat stream error: %s", e)
            yield _make_chat_event("error", content=str(e))
        finally:
            await ollama.close()

        # ── Step 5: Send sources ──
        if _STUBS_AVAILABLE:
            source_hits = []
            for s in sources:
                source_hits.append(types_pb2.SearchHit(
                    score=s.get("score", 0.0),
                    file_path=s.get("file_path", ""),
                    language=s.get("language", ""),
                    lines=s.get("lines", ""),
                    chunk_info=s.get("chunk", ""),
                    content=s.get("content", ""),
                ))
            yield chat_pb2.ChatEvent(type="sources", sources=source_hits)
        else:
            yield _make_chat_event("sources", content=json.dumps(sources))

        # ── Step 6: Done event ──
        pii_masked = pii_info.get("pii_masked", False)
        pii_count = pii_info.get("pii_entities_count", 0)
        yield _make_chat_event(
            "done",
            pii_masked=pii_masked,
            pii_entities_count=pii_count,
        )

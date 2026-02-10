"""PIIService gRPC servicer — wraps PIIMaskingService for PII detection and masking."""

import logging

import grpc

from ..config import get_config
from ..processing.pii_masking import PIIMaskingService

log = logging.getLogger("ollqd.worker.pii")

try:
    from ..gen.ollqd.v1 import processing_pb2 as pii_pb2
    _STUBS_AVAILABLE = True
except ImportError:
    _STUBS_AVAILABLE = False

# Module-level singleton (lazy-initialized)
_pii_service: PIIMaskingService | None = None


def _get_pii_service() -> PIIMaskingService:
    """Return a lazily-initialized PIIMaskingService singleton."""
    global _pii_service
    if _pii_service is None:
        cfg = get_config()
        _pii_service = PIIMaskingService(use_spacy=cfg.pii.use_spacy)
    return _pii_service


class _Response:
    """Fallback response object when proto stubs are not generated."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


class PIIServiceServicer:
    """gRPC servicer for PII masking operations.

    Methods:
        TestMasking — mask text and return detected entities
    """

    async def TestMasking(self, request, context):
        """Mask PII in the provided text and return the masked version plus entities."""
        text = request.text if hasattr(request, "text") else ""
        if not text:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "text is required")

        pii_svc = _get_pii_service()
        registry = pii_svc.create_registry()
        masked = pii_svc.mask_text(text, registry)

        entities = [
            {"token": token, "original": value}
            for token, value in registry.token_to_value.items()
        ]

        log.info("PII test masking: %d entities found", len(entities))

        if _STUBS_AVAILABLE:
            entity_msgs = [
                pii_pb2.PIIEntity(token=e["token"], original=e["original"])
                for e in entities
            ]
            return pii_pb2.TestMaskingResponse(
                original=text,
                masked=masked,
                entities=entity_msgs,
                entity_count=len(entities),
            )

        return _Response(
            original=text,
            masked=masked,
            entities=entities,
            entity_count=len(entities),
        )

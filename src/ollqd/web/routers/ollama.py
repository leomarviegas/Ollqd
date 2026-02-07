"""Ollama management endpoints — models, generation, embeddings."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..deps import get_config, get_ollama_service, get_pii_service
from ..models import (
    ChatRequest,
    CopyModelRequest,
    EmbedRequest,
    GenerateRequest,
    PullModelRequest,
    ShowModelRequest,
)
from ..services.ollama_service import OllamaService

router = APIRouter()


# ── Models ──────────────────────────────────────────────────


@router.get("/models")
async def list_models(ollama: OllamaService = Depends(get_ollama_service)):
    try:
        return await ollama.list_models()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {e}")


@router.post("/models/show")
async def show_model(
    req: ShowModelRequest, ollama: OllamaService = Depends(get_ollama_service)
):
    try:
        return await ollama.show_model(req.name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/models/pull")
async def pull_model(
    req: PullModelRequest, ollama: OllamaService = Depends(get_ollama_service)
):
    async def stream():
        async for chunk in ollama.pull_model_stream(req.name):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/models/copy")
async def copy_model(
    req: CopyModelRequest, ollama: OllamaService = Depends(get_ollama_service)
):
    try:
        return await ollama.copy_model(req.source, req.destination)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/models/{name:path}")
async def delete_model(
    name: str, ollama: OllamaService = Depends(get_ollama_service)
):
    try:
        return await ollama.delete_model(name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Running ─────────────────────────────────────────────────


@router.get("/ps")
async def running_models(ollama: OllamaService = Depends(get_ollama_service)):
    try:
        return await ollama.ps()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── Generation ──────────────────────────────────────────────


@router.post("/chat")
async def chat(req: ChatRequest, ollama: OllamaService = Depends(get_ollama_service)):
    cfg = get_config()
    pii_svc = get_pii_service()

    registry = None
    masked_messages = req.messages
    if cfg.pii.enabled:
        from ..services.pii_service import PII_SYSTEM_INSTRUCTION
        registry = pii_svc.create_registry()
        masked_messages = []
        for msg in req.messages:
            if msg.get("role") == "user":
                masked_messages.append({**msg, "content": pii_svc.mask_text(msg["content"], registry)})
            else:
                masked_messages.append(msg)
        if registry.has_entities:
            masked_messages.insert(0, {"role": "system", "content": PII_SYSTEM_INSTRUCTION})

    async def stream():
        if registry is not None and registry.has_entities:
            buffer = pii_svc.create_stream_buffer(registry)
            async for chunk in ollama.chat_stream(
                model=req.model,
                messages=masked_messages,
                options={"temperature": req.temperature},
            ):
                unmasked = buffer.feed(chunk)
                if unmasked:
                    yield f"data: {json.dumps({'content': unmasked})}\n\n"
            remaining = buffer.flush()
            if remaining:
                yield f"data: {json.dumps({'content': remaining})}\n\n"
        else:
            async for chunk in ollama.chat_stream(
                model=req.model,
                messages=masked_messages,
                options={"temperature": req.temperature},
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/generate")
async def generate(
    req: GenerateRequest, ollama: OllamaService = Depends(get_ollama_service)
):
    async def stream():
        async for chunk in ollama.generate_stream(
            model=req.model,
            prompt=req.prompt,
            options={"temperature": req.temperature},
        ):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/embed")
async def embed(req: EmbedRequest, ollama: OllamaService = Depends(get_ollama_service)):
    try:
        return await ollama.embed(req.model, req.input)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── System ──────────────────────────────────────────────────


@router.get("/version")
async def version(ollama: OllamaService = Depends(get_ollama_service)):
    try:
        return await ollama.version()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

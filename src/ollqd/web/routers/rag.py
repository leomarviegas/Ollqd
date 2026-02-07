"""RAG endpoints — indexing (background), search, WebSocket chat, visualization."""

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from qdrant_client.models import PointStruct

from ...chunking import chunk_document, chunk_docx, chunk_file, chunk_pdf, chunk_pptx, chunk_xlsx
from ...discovery import discover_files, discover_images
from ...embedder import OllamaEmbedder
from ...errors import EmbeddingError, VectorStoreError
from ...vectorstore import QdrantManager
from ..deps import get_config, get_embedder, get_ollama_service, get_pii_service, get_task_manager
from ..models import IndexCodebaseRequest, IndexDocumentsRequest, IndexImagesRequest, SearchRequest
from ..services.ollama_service import OllamaService
from ..services.task_manager import TaskManager

log = logging.getLogger("ollqd.web.rag")
router = APIRouter()
BATCH_SIZE = 32


# ── Language → Color Mapping ────────────────────────────────

_LANG_COLORS = {
    "python": "#3572A5", "javascript": "#f1e05a", "typescript": "#3178c6",
    "java": "#b07219", "go": "#00ADD8", "rust": "#dea584", "c": "#555555",
    "cpp": "#f34b7d", "csharp": "#178600", "ruby": "#701516", "php": "#4F5D95",
    "swift": "#F05138", "kotlin": "#A97BFF", "scala": "#c22d40",
    "html": "#e34c26", "css": "#563d7c", "shell": "#89e051", "bash": "#89e051",
    "markdown": "#083fa1", "json": "#292929", "yaml": "#cb171e", "toml": "#9c4221",
    "sql": "#e38c00", "text": "#888888", "image": "#e91e63",
}


def _language_color(lang: str) -> str:
    return _LANG_COLORS.get(lang.lower(), "#999999")


# ── Search ──────────────────────────────────────────────────


@router.post("/search")
def semantic_search(req: SearchRequest):
    cfg = get_config()
    embedder = get_embedder()
    try:
        dim = embedder.get_dimension()
        qdrant = QdrantManager(url=cfg.qdrant.url, collection=req.query, dimension=dim)
        # Use the collection from the first available or default
        query_vec = embedder.embed_query(req.query)
    except Exception as e:
        embedder.close()
        raise HTTPException(status_code=500, detail=str(e))

    # Build a proper search using the collection parameter
    collection = "codebase"  # default
    qdrant = QdrantManager(url=cfg.qdrant.url, collection=collection, dimension=dim)
    hits = qdrant.search(
        query_vec,
        top_k=req.top_k,
        language=req.language,
        file_filter=req.file_path,
    )
    embedder.close()
    return {"status": "ok", "query": req.query, "results": hits}


@router.post("/search/{collection}")
def semantic_search_collection(collection: str, req: SearchRequest):
    cfg = get_config()
    embedder = get_embedder()
    try:
        dim = embedder.get_dimension()
        qdrant = QdrantManager(url=cfg.qdrant.url, collection=collection, dimension=dim)
        query_vec = embedder.embed_query(req.query)
        hits = qdrant.search(
            query_vec,
            top_k=req.top_k,
            language=req.language,
            file_filter=req.file_path,
        )
        return {"status": "ok", "query": req.query, "collection": collection, "results": hits}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        embedder.close()


# ── Indexing (background tasks) ─────────────────────────────


def _run_index_codebase(task_id: str, req: IndexCodebaseRequest):
    """Synchronous indexing — runs in a thread via asyncio.to_thread."""
    cfg = get_config()
    tm = get_task_manager()
    tm.start(task_id)

    root = Path(req.root_path).resolve()
    if not root.is_dir():
        tm.fail(task_id, f"Not a directory: {req.root_path}")
        return

    files = discover_files(root, cfg.chunking.max_file_size_kb, set(req.extra_skip_dirs))
    if not files:
        tm.complete(task_id, {"files": 0, "chunks": 0, "message": "No indexable files"})
        return

    embedder = OllamaEmbedder(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embed_model,
        timeout=cfg.ollama.timeout_s,
    )
    dim = embedder.get_dimension()
    qdrant = QdrantManager(
        url=cfg.qdrant.url, collection=req.collection,
        dimension=dim, distance=cfg.qdrant.default_distance,
    )
    qdrant.ensure_collection()

    if req.incremental:
        indexed = qdrant.get_indexed_hashes()
        files = [f for f in files if indexed.get(f.path) != f.content_hash]
        for f in files:
            if f.path in indexed:
                qdrant.delete_file_points(f.path)
        if not files:
            embedder.close()
            tm.complete(task_id, {"files": 0, "chunks": 0, "message": "All up to date"})
            return

    all_chunks = []
    for f in files:
        all_chunks.extend(chunk_file(f, req.chunk_size, req.chunk_overlap))

    total_upserted = 0
    total_batches = max(1, (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE)

    for i, batch_start in enumerate(range(0, len(all_chunks), BATCH_SIZE)):
        # Cooperative cancellation
        if tm.is_cancelled(task_id):
            embedder.close()
            return

        batch = all_chunks[batch_start : batch_start + BATCH_SIZE]
        try:
            vectors = embedder.embed_chunks(batch)
            points = [
                PointStruct(
                    id=c.point_id,
                    vector=v,
                    payload={
                        "file_path": c.file_path,
                        "language": c.language,
                        "chunk_index": c.chunk_index,
                        "total_chunks": c.total_chunks,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "content": c.content,
                        "content_hash": c.content_hash,
                    },
                )
                for c, v in zip(batch, vectors)
            ]
            qdrant.upsert_batch(points)
            total_upserted += len(points)
        except (EmbeddingError, VectorStoreError) as e:
            log.error("Batch %d failed: %s", i, e)

        tm.update_progress(task_id, (i + 1) / total_batches)

    embedder.close()
    tm.complete(
        task_id,
        {
            "files": len(files),
            "chunks": total_upserted,
            "collection": req.collection,
        },
    )


@router.post("/index/codebase")
async def index_codebase(
    req: IndexCodebaseRequest,
    tm: TaskManager = Depends(get_task_manager),
):
    task_id = tm.create_with_params("index_codebase", req.model_dump())
    asyncio.get_event_loop().run_in_executor(None, _run_index_codebase, task_id, req)
    return {"task_id": task_id, "status": "started"}


@router.post("/index/documents")
async def index_documents(
    req: IndexDocumentsRequest,
    tm: TaskManager = Depends(get_task_manager),
):
    task_id = tm.create_with_params("index_documents", req.model_dump())

    def _run():
        import hashlib

        cfg = get_config()
        tm.start(task_id)
        embedder = OllamaEmbedder(
            base_url=cfg.ollama.base_url,
            model=cfg.ollama.embed_model,
            timeout=cfg.ollama.timeout_s,
        )
        dim = embedder.get_dimension()
        qdrant = QdrantManager(
            url=cfg.qdrant.url, collection=req.collection,
            dimension=dim, distance=cfg.qdrant.default_distance,
        )
        qdrant.ensure_collection()

        all_chunks = []
        files_processed = 0
        for p in req.paths:
            path = Path(p).resolve()
            file_list = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
            for fp in file_list:
                if not fp.is_file() or fp.suffix.lower() not in (".md", ".txt", ".rst", ".html"):
                    continue
                try:
                    content = fp.read_text(errors="replace")
                except (OSError, PermissionError):
                    continue
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                lang = "markdown" if fp.suffix.lower() in (".md", ".rst") else "text"
                chunks = chunk_document(
                    str(fp), content, lang, req.chunk_size, req.chunk_overlap, content_hash
                )
                all_chunks.extend(chunks)
                files_processed += 1

        total_upserted = 0
        total_batches = max(1, (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE)
        for i, batch_start in enumerate(range(0, len(all_chunks), BATCH_SIZE)):
            if tm.is_cancelled(task_id):
                embedder.close()
                return

            batch = all_chunks[batch_start : batch_start + BATCH_SIZE]
            try:
                texts = [f"File: {c.file_path} | {c.language}\n\n{c.content}" for c in batch]
                vectors = embedder.embed_texts(texts)
                points = [
                    PointStruct(
                        id=c.point_id, vector=v,
                        payload={
                            "file_path": c.file_path, "language": c.language,
                            "chunk_index": c.chunk_index, "total_chunks": c.total_chunks,
                            "start_line": c.start_line, "end_line": c.end_line,
                            "content": c.content, "content_hash": c.content_hash,
                            "source_tag": req.source_tag,
                        },
                    )
                    for c, v in zip(batch, vectors)
                ]
                qdrant.upsert_batch(points)
                total_upserted += len(points)
            except Exception as e:
                log.error("Batch %d failed: %s", i, e)
            tm.update_progress(task_id, (i + 1) / total_batches)

        embedder.close()
        tm.complete(task_id, {"files": files_processed, "chunks": total_upserted, "collection": req.collection})

    asyncio.get_event_loop().run_in_executor(None, _run)
    return {"task_id": task_id, "status": "started"}


# ── File Upload & Index ─────────────────────────────────────


def _run_upload_index(
    task_id: str,
    saved_paths: list[str],
    collection: str,
    chunk_size: int,
    chunk_overlap: int,
    source_tag: str,
    vision_model: str | None = None,
    caption_prompt: str | None = None,
):
    """Background worker: chunk uploaded files (including PDFs and images) and index into Qdrant."""
    cfg = get_config()
    tm = get_task_manager()
    tm.start(task_id)

    effective_vision_model = vision_model or cfg.ollama.vision_model
    effective_caption_prompt = caption_prompt or cfg.image.caption_prompt

    embedder = OllamaEmbedder(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embed_model,
        timeout=cfg.ollama.timeout_s,
    )
    dim = embedder.get_dimension()
    qdrant = QdrantManager(
        url=cfg.qdrant.url, collection=collection,
        dimension=dim, distance=cfg.qdrant.default_distance,
    )
    qdrant.ensure_collection()

    # Separate images from documents
    _img_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
    doc_paths = []
    image_paths = []
    for p in saved_paths:
        if Path(p).suffix.lower() in _img_exts:
            image_paths.append(p)
        else:
            doc_paths.append(p)

    total_files = len(saved_paths)

    # ── Phase 1: Process document files ──────────────────────
    all_chunks = []
    files_processed = 0

    for p in doc_paths:
        fp = Path(p)
        ext = fp.suffix.lower()
        try:
            raw = fp.read_bytes()
            content_hash = hashlib.sha256(raw).hexdigest()

            if ext == ".pdf":
                chunks = chunk_pdf(str(fp), raw, chunk_size, chunk_overlap, content_hash)
            elif ext == ".docx":
                chunks = chunk_docx(str(fp), raw, chunk_size, chunk_overlap, content_hash)
            elif ext == ".xlsx":
                chunks = chunk_xlsx(str(fp), raw, chunk_size, chunk_overlap, content_hash)
            elif ext == ".pptx":
                chunks = chunk_pptx(str(fp), raw, chunk_size, chunk_overlap, content_hash)
            else:
                content = raw.decode("utf-8", errors="replace")
                lang = "markdown" if ext in (".md", ".rst") else "text"
                chunks = chunk_document(str(fp), content, lang, chunk_size, chunk_overlap, content_hash)

            all_chunks.extend(chunks)
            files_processed += 1
        except Exception as e:
            log.error("Failed to process uploaded file %s: %s", p, e)

    total_upserted = 0
    if all_chunks:
        doc_weight = len(doc_paths) / max(total_files, 1)
        total_batches = max(1, (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE)
        for i, batch_start in enumerate(range(0, len(all_chunks), BATCH_SIZE)):
            if tm.is_cancelled(task_id):
                embedder.close()
                return
            batch = all_chunks[batch_start:batch_start + BATCH_SIZE]
            try:
                texts = [f"File: {c.file_path} | {c.language}\n\n{c.content}" for c in batch]
                vectors = embedder.embed_texts(texts)
                points = [
                    PointStruct(
                        id=c.point_id, vector=v,
                        payload={
                            "file_path": c.file_path, "language": c.language,
                            "chunk_index": c.chunk_index, "total_chunks": c.total_chunks,
                            "start_line": c.start_line, "end_line": c.end_line,
                            "content": c.content, "content_hash": c.content_hash,
                            "source_tag": source_tag,
                        },
                    )
                    for c, v in zip(batch, vectors)
                ]
                qdrant.upsert_batch(points)
                total_upserted += len(points)
            except Exception as e:
                log.error("Batch %d failed: %s", i, e)
            tm.update_progress(task_id, doc_weight * (i + 1) / total_batches)

    # ── Phase 2: Process image files ─────────────────────────
    images_indexed = 0
    images_failed = 0

    for j, img_path in enumerate(image_paths):
        if tm.is_cancelled(task_id):
            embedder.close()
            return

        fp = Path(img_path)
        try:
            image_bytes = fp.read_bytes()
            content_hash = hashlib.sha256(image_bytes).hexdigest()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            caption = _caption_image_sync(
                cfg.ollama.base_url, effective_vision_model, image_b64, effective_caption_prompt
            )

            if not caption.strip():
                log.warning("Empty caption for uploaded image %s, skipping", img_path)
                images_failed += 1
                continue

            embed_text = f"Image: {fp.name}\n\nCaption: {caption}"
            vectors = embedder.embed_texts([embed_text])

            point_id = hashlib.md5(f"image::{fp.name}".encode()).hexdigest()
            payload = {
                "file_path": str(fp),
                "language": "image",
                "image_type": fp.suffix.lower(),
                "caption": caption,
                "content": caption,
                "content_hash": content_hash,
                "chunk_index": 0,
                "total_chunks": 1,
                "start_line": 0,
                "end_line": 0,
                "source_tag": source_tag,
            }

            point = PointStruct(id=point_id, vector=vectors[0], payload=payload)
            qdrant.upsert_batch([point])
            images_indexed += 1
            files_processed += 1

        except Exception as e:
            log.error("Failed to index uploaded image %s: %s", img_path, e)
            images_failed += 1

        doc_weight = len(doc_paths) / max(total_files, 1)
        img_weight = len(image_paths) / max(total_files, 1)
        tm.update_progress(task_id, doc_weight + img_weight * (j + 1) / len(image_paths))

    if not all_chunks and not images_indexed:
        embedder.close()
        tm.complete(task_id, {
            "files": 0, "chunks": 0,
            "images_indexed": 0, "images_failed": images_failed,
            "message": "No content extracted",
        })
        return

    embedder.close()
    tm.complete(task_id, {
        "files": files_processed,
        "chunks": total_upserted,
        "images_indexed": images_indexed,
        "images_failed": images_failed,
        "collection": collection,
    })


@router.post("/upload")
async def upload_and_index(
    files: list[UploadFile] = File(...),
    collection: str = Form("documents"),
    chunk_size: int = Form(512),
    chunk_overlap: int = Form(64),
    source_tag: str = Form("upload"),
    vision_model: str = Form(""),
    caption_prompt: str = Form(""),
    tm: TaskManager = Depends(get_task_manager),
):
    """Accept multipart file uploads, save to disk, then index into Qdrant."""
    cfg = get_config()
    upload_dir = Path(cfg.upload.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    _img_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
    saved_paths: list[str] = []
    has_images = False
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in cfg.upload.allowed_extensions:
            raise HTTPException(400, f"Unsupported file type: {ext}. Allowed: {cfg.upload.allowed_extensions}")
        content = await f.read()
        if len(content) > cfg.upload.max_file_size_mb * 1024 * 1024:
            raise HTTPException(400, f"File too large: {f.filename} ({len(content)} bytes)")

        dest = upload_dir / f"{int(time.time())}_{f.filename}"
        dest.write_bytes(content)
        saved_paths.append(str(dest))
        if ext in _img_exts:
            has_images = True

    task_id = tm.create_with_params("upload_documents", {
        "paths": saved_paths,
        "collection": collection,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "source_tag": source_tag,
        "vision_model": vision_model or None,
        "caption_prompt": caption_prompt or None,
    })

    asyncio.get_event_loop().run_in_executor(
        None, _run_upload_index, task_id, saved_paths, collection,
        chunk_size, chunk_overlap, source_tag,
        vision_model or None, caption_prompt or None,
    )

    return {
        "task_id": task_id,
        "status": "started",
        "files_saved": len(saved_paths),
        "filenames": [Path(p).name for p in saved_paths],
        "has_images": has_images,
    }


# ── Image Indexing ───────────────────────────────────────────


def _caption_image_sync(base_url: str, model: str, image_b64: str, prompt: str, timeout: float = 180.0) -> str:
    """Synchronous vision captioning for use in background thread."""
    import httpx as _httpx
    with _httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")


def _run_index_images(task_id: str, req: IndexImagesRequest):
    """Synchronous image indexing — runs in a thread via asyncio.to_thread."""
    cfg = get_config()
    tm = get_task_manager()
    tm.start(task_id)

    root = Path(req.root_path).resolve()
    if not root.is_dir():
        tm.fail(task_id, f"Not a directory: {req.root_path}")
        return

    max_size = req.max_image_size_kb or cfg.image.max_image_size_kb
    images = discover_images(root, max_size, set(req.extra_skip_dirs))
    if not images:
        tm.complete(task_id, {"images_found": 0, "images_indexed": 0, "message": "No images found"})
        return

    vision_model = req.vision_model or cfg.ollama.vision_model
    caption_prompt = req.caption_prompt or cfg.image.caption_prompt

    embedder = OllamaEmbedder(
        base_url=cfg.ollama.base_url,
        model=cfg.ollama.embed_model,
        timeout=cfg.ollama.timeout_s,
    )
    dim = embedder.get_dimension()
    qdrant = QdrantManager(
        url=cfg.qdrant.url, collection=req.collection,
        dimension=dim, distance=cfg.qdrant.default_distance,
    )
    qdrant.ensure_collection()

    # Incremental: skip unchanged images
    if req.incremental:
        indexed = qdrant.get_indexed_hashes()
        images = [img for img in images if indexed.get(img.path) != img.content_hash]
        for img in images:
            if img.path in indexed:
                qdrant.delete_file_points(img.path)
        if not images:
            embedder.close()
            tm.complete(task_id, {"images_found": 0, "images_indexed": 0, "message": "All images up to date"})
            return

    total = len(images)
    indexed_count = 0
    failed_count = 0

    for i, img in enumerate(images):
        # Cooperative cancellation
        if tm.is_cancelled(task_id):
            embedder.close()
            return

        try:
            # Read and base64-encode image
            image_bytes = Path(img.abs_path).read_bytes()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            # Caption via vision model
            caption = _caption_image_sync(
                cfg.ollama.base_url, vision_model, image_b64, caption_prompt
            )

            if not caption.strip():
                log.warning("Empty caption for %s, skipping", img.path)
                failed_count += 1
                continue

            # Embed caption text
            embed_text = f"Image: {img.path}\n\nCaption: {caption}"
            vectors = embedder.embed_texts([embed_text])

            # Create point ID from image path
            point_id = hashlib.md5(f"image::{img.path}".encode()).hexdigest()

            payload = {
                "file_path": img.path,
                "abs_path": img.abs_path,
                "language": "image",
                "image_type": img.extension,
                "caption": caption,
                "content": caption,
                "content_hash": img.content_hash,
                "chunk_index": 0,
                "total_chunks": 1,
                "start_line": 0,
                "end_line": 0,
            }
            if img.width and img.height:
                payload["width"] = img.width
                payload["height"] = img.height

            point = PointStruct(id=point_id, vector=vectors[0], payload=payload)
            qdrant.upsert_batch([point])
            indexed_count += 1

        except Exception as e:
            log.error("Failed to index image %s: %s", img.path, e)
            failed_count += 1

        tm.update_progress(task_id, (i + 1) / total)

    embedder.close()
    tm.complete(task_id, {
        "images_found": total,
        "images_indexed": indexed_count,
        "images_failed": failed_count,
        "collection": req.collection,
    })


@router.post("/index/images")
async def index_images(
    req: IndexImagesRequest,
    tm: TaskManager = Depends(get_task_manager),
):
    task_id = tm.create_with_params("index_images", req.model_dump())
    asyncio.get_event_loop().run_in_executor(None, _run_index_images, task_id, req)
    return {"task_id": task_id, "status": "started"}


# ── Image Serving ────────────────────────────────────────────

SAFE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
IMAGE_MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp", ".tiff": "image/tiff",
}


@router.get("/image")
async def serve_image(path: str = Query(..., min_length=1)):
    """Serve an image file for thumbnail display. Validates extension and path."""
    resolved = Path(path).resolve()
    ext = resolved.suffix.lower()
    if ext not in SAFE_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Not a supported image type")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    media_type = IMAGE_MEDIA_TYPES.get(ext, "application/octet-stream")
    return FileResponse(str(resolved), media_type=media_type)


# ── Tasks ───────────────────────────────────────────────────


@router.get("/tasks")
def list_tasks(tm: TaskManager = Depends(get_task_manager)):
    return tm.list_all()


@router.delete("/tasks")
def clear_tasks(tm: TaskManager = Depends(get_task_manager)):
    removed = tm.clear_finished()
    return {"cleared": removed}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, tm: TaskManager = Depends(get_task_manager)):
    t = tm.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return t


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, tm: TaskManager = Depends(get_task_manager)):
    if tm.cancel(task_id):
        return {"status": "cancelled", "task_id": task_id}
    raise HTTPException(status_code=400, detail="Task cannot be cancelled (not running or not found)")


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str, tm: TaskManager = Depends(get_task_manager)):
    params = tm.get_retry_params(task_id)
    task_info = tm.get(task_id)
    if not params or not task_info:
        raise HTTPException(status_code=400, detail="No retry params found for this task")

    task_type = task_info["type"]
    if task_type == "index_codebase":
        new_req = IndexCodebaseRequest(**params)
        new_id = tm.create_with_params("index_codebase", params)
        asyncio.get_event_loop().run_in_executor(None, _run_index_codebase, new_id, new_req)
    elif task_type == "index_images":
        new_req = IndexImagesRequest(**params)
        new_id = tm.create_with_params("index_images", params)
        asyncio.get_event_loop().run_in_executor(None, _run_index_images, new_id, new_req)
    elif task_type == "index_documents":
        new_req = IndexDocumentsRequest(**params)
        new_id = tm.create_with_params("index_documents", params)

        def _run():
            cfg = get_config()
            tm.start(new_id)
            embedder = OllamaEmbedder(
                base_url=cfg.ollama.base_url,
                model=cfg.ollama.embed_model,
                timeout=cfg.ollama.timeout_s,
            )
            dim = embedder.get_dimension()
            qdrant = QdrantManager(
                url=cfg.qdrant.url, collection=new_req.collection,
                dimension=dim, distance=cfg.qdrant.default_distance,
            )
            qdrant.ensure_collection()
            all_chunks = []
            files_processed = 0
            for p in new_req.paths:
                path = Path(p).resolve()
                file_list = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
                for fp in file_list:
                    if not fp.is_file() or fp.suffix.lower() not in (".md", ".txt", ".rst", ".html"):
                        continue
                    try:
                        content = fp.read_text(errors="replace")
                    except (OSError, PermissionError):
                        continue
                    content_hash = hashlib.sha256(content.encode()).hexdigest()
                    lang = "markdown" if fp.suffix.lower() in (".md", ".rst") else "text"
                    chunks = chunk_document(
                        str(fp), content, lang, new_req.chunk_size, new_req.chunk_overlap, content_hash
                    )
                    all_chunks.extend(chunks)
                    files_processed += 1

            total_upserted = 0
            total_batches = max(1, (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE)
            for i, batch_start in enumerate(range(0, len(all_chunks), BATCH_SIZE)):
                if tm.is_cancelled(new_id):
                    embedder.close()
                    return
                batch = all_chunks[batch_start: batch_start + BATCH_SIZE]
                try:
                    texts = [f"File: {c.file_path} | {c.language}\n\n{c.content}" for c in batch]
                    vectors = embedder.embed_texts(texts)
                    points = [
                        PointStruct(
                            id=c.point_id, vector=v,
                            payload={
                                "file_path": c.file_path, "language": c.language,
                                "chunk_index": c.chunk_index, "total_chunks": c.total_chunks,
                                "start_line": c.start_line, "end_line": c.end_line,
                                "content": c.content, "content_hash": c.content_hash,
                                "source_tag": new_req.source_tag,
                            },
                        )
                        for c, v in zip(batch, vectors)
                    ]
                    qdrant.upsert_batch(points)
                    total_upserted += len(points)
                except Exception as e:
                    log.error("Batch %d failed: %s", i, e)
                tm.update_progress(new_id, (i + 1) / total_batches)
            embedder.close()
            tm.complete(new_id, {"files": files_processed, "chunks": total_upserted, "collection": new_req.collection})

        asyncio.get_event_loop().run_in_executor(None, _run)
    elif task_type == "upload_documents":
        new_id = tm.create_with_params("upload_documents", params)
        asyncio.get_event_loop().run_in_executor(
            None, _run_upload_index, new_id,
            params["paths"], params["collection"],
            params.get("chunk_size", 512), params.get("chunk_overlap", 64),
            params.get("source_tag", "upload"),
            params.get("vision_model"), params.get("caption_prompt"),
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown task type: {task_type}")

    return {"task_id": new_id, "status": "retrying", "original_task": task_id}


# ── Visualization ──────────────────────────────────────────


@router.get("/visualize/{collection}/overview")
def visualize_overview(
    collection: str,
    limit: int = Query(500, ge=1, le=5000),
):
    """Aggregate points by file_path → nodes/edges for vis-network force graph."""
    cfg = get_config()
    from qdrant_client import QdrantClient
    client = QdrantClient(url=cfg.qdrant.url)

    try:
        client.get_collection(collection)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")

    file_stats: dict[str, dict] = {}
    offset = None
    fetched = 0

    while fetched < limit:
        batch_limit = min(256, limit - fetched)
        points, offset = client.scroll(
            collection_name=collection,
            limit=batch_limit,
            offset=offset,
            with_payload=["file_path", "language"],
            with_vectors=False,
        )
        for p in points:
            fp = p.payload.get("file_path", "unknown")
            lang = p.payload.get("language", "unknown")
            if fp not in file_stats:
                file_stats[fp] = {"count": 0, "language": lang}
            file_stats[fp]["count"] += 1
        fetched += len(points)
        if offset is None:
            break

    # Build vis-network graph data
    nodes = [{"id": 0, "label": collection, "color": "#2196F3", "size": 50, "shape": "diamond"}]
    edges = []
    for i, (fp, stats) in enumerate(file_stats.items(), start=1):
        color = _language_color(stats["language"])
        label = fp.split("/")[-1] if "/" in fp else fp
        nodes.append({
            "id": i, "label": label, "title": f"{fp}\n{stats['count']} chunks\n{stats['language']}",
            "color": color, "size": max(15, min(50, stats["count"] * 3)),
            "file_path": fp, "language": stats["language"], "chunks": stats["count"],
        })
        edges.append({"from": 0, "to": i})

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {"total_files": len(file_stats), "total_chunks": fetched, "collection": collection},
    }


@router.get("/visualize/{collection}/file-tree")
def visualize_file_tree(
    collection: str,
    file_path: str = Query(..., min_length=1),
):
    """Hierarchical view: file → chunks → vectors for one file."""
    cfg = get_config()
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue
    client = QdrantClient(url=cfg.qdrant.url)

    chunks = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            scroll_filter=Filter(must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]),
            with_payload=True,
            with_vectors=False,
        )
        chunks.extend(points)
        if offset is None:
            break

    if not chunks:
        return {"nodes": [], "edges": [], "file_path": file_path}

    lang = chunks[0].payload.get("language", "unknown")
    file_color = _language_color(lang)

    # File node
    nodes = [{"id": 0, "label": file_path.split("/")[-1], "title": file_path, "color": file_color, "level": 0, "size": 40}]
    edges = []

    for i, p in enumerate(sorted(chunks, key=lambda x: x.payload.get("chunk_index", 0)), start=1):
        chunk_idx = p.payload.get("chunk_index", 0)
        lines = f"L{p.payload.get('start_line', '?')}-{p.payload.get('end_line', '?')}"
        content_preview = (p.payload.get("content", "")[:80] + "...") if p.payload.get("content", "") else ""
        nodes.append({
            "id": i, "label": f"Chunk {chunk_idx}", "title": f"{lines}\n{content_preview}",
            "color": file_color, "level": 1, "size": 25, "shape": "box",
        })
        edges.append({"from": 0, "to": i})

    return {"nodes": nodes, "edges": edges, "file_path": file_path, "total_chunks": len(chunks)}


@router.get("/visualize/{collection}/vectors")
def visualize_vectors(
    collection: str,
    method: str = Query("pca", pattern="^(pca|tsne)$"),
    dims: int = Query(3, ge=2, le=3),
    limit: int = Query(500, ge=10, le=2000),
):
    """Reduce vectors to 2D/3D for scatter plot."""
    import numpy as np

    cfg = get_config()
    from qdrant_client import QdrantClient
    client = QdrantClient(url=cfg.qdrant.url)

    raw_points = []
    offset = None
    while len(raw_points) < limit:
        batch_limit = min(100, limit - len(raw_points))
        points, offset = client.scroll(
            collection_name=collection,
            limit=batch_limit,
            offset=offset,
            with_payload=["file_path", "language", "chunk_index"],
            with_vectors=True,
        )
        raw_points.extend(points)
        if offset is None:
            break

    if len(raw_points) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 points for visualization")

    vectors = np.array([p.vector for p in raw_points])
    original_dims = vectors.shape[1]

    if method == "pca":
        from sklearn.decomposition import PCA
        reducer = PCA(n_components=dims)
        reduced = reducer.fit_transform(vectors)
    else:
        from sklearn.manifold import TSNE
        perplexity = min(30, len(raw_points) - 1)
        reducer = TSNE(n_components=dims, perplexity=perplexity, random_state=42)
        reduced = reducer.fit_transform(vectors)

    result_points = []
    for i, p in enumerate(raw_points):
        lang = p.payload.get("language", "unknown")
        pt = {
            "x": float(reduced[i, 0]),
            "y": float(reduced[i, 1]),
            "file": p.payload.get("file_path", ""),
            "language": lang,
            "chunk": p.payload.get("chunk_index", 0),
            "color": _language_color(lang),
        }
        if dims == 3:
            pt["z"] = float(reduced[i, 2])
        result_points.append(pt)

    return {
        "points": result_points,
        "method": method,
        "dims": dims,
        "original_dims": original_dims,
        "total_points": len(result_points),
    }


# ── WebSocket RAG Chat ──────────────────────────────────────


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    cfg = get_config()
    pii_svc = get_pii_service()

    ollama = OllamaService(base_url=cfg.ollama.base_url, timeout=cfg.ollama.timeout_s)

    try:
        while True:
            data = await websocket.receive_json()
            query = data.get("message", "")
            collection = data.get("collection", "codebase")
            model = data.get("model", cfg.ollama.chat_model)
            pii_enabled = data.get("pii_enabled", cfg.pii.enabled)

            # Per-turn PII registry
            registry = pii_svc.create_registry() if pii_enabled else None

            # Semantic search for context
            sources = []
            context = ""
            try:
                embedder = get_embedder()
                dim = embedder.get_dimension()
                qdrant = QdrantManager(url=cfg.qdrant.url, collection=collection, dimension=dim)
                query_vec = embedder.embed_query(query)
                sources = qdrant.search(query_vec, top_k=5)
                context_parts = []
                for s in sources:
                    if s.get("language") == "image":
                        context_parts.append(f"[Image: {s['file_path']}]\nCaption: {s['content']}")
                    else:
                        context_parts.append(f"[{s['file_path']} L{s['lines']}]\n{s['content']}")
                context = "\n\n".join(context_parts)
                embedder.close()
            except Exception as e:
                log.warning("Search failed, chatting without context: %s", e)

            # Mask PII in query + context before sending to LLM
            if registry is not None:
                masked_query = pii_svc.mask_text(query, registry)
                masked_context = pii_svc.mask_text(context, registry) if context else ""
            else:
                masked_query = query
                masked_context = context

            # Build messages
            from ..services.pii_service import PII_SYSTEM_INSTRUCTION
            messages = []
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
            messages.append({"role": "system", "content": system_content})
            messages.append({"role": "user", "content": masked_query})

            # Stream chat response with PII unmasking
            pii_info = {}
            try:
                if registry is not None and registry.has_entities:
                    buffer = pii_svc.create_stream_buffer(registry)
                    async for chunk in ollama.chat_stream(model=model, messages=messages):
                        unmasked = buffer.feed(chunk)
                        if unmasked:
                            await websocket.send_json({"type": "chunk", "content": unmasked})
                    remaining = buffer.flush()
                    if remaining:
                        await websocket.send_json({"type": "chunk", "content": remaining})
                    pii_info = {"pii_masked": True, "pii_entities_count": len(registry.token_to_value)}
                else:
                    async for chunk in ollama.chat_stream(model=model, messages=messages):
                        await websocket.send_json({"type": "chunk", "content": chunk})
            except Exception as e:
                await websocket.send_json({"type": "error", "content": str(e)})

            await websocket.send_json({"type": "sources", "results": sources})
            await websocket.send_json({"type": "done", **pii_info})

    except WebSocketDisconnect:
        pass
    finally:
        await ollama.close()

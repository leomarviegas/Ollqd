"""IndexingService gRPC servicer — all indexing operations with server-streaming progress."""

import base64
import hashlib
import json
import logging
import uuid
from pathlib import Path
from tempfile import mkdtemp

import grpc
from qdrant_client.models import PointStruct

from ..config import get_config
from ..errors import EmbeddingError, VectorStoreError
from ..processing.chunking import (
    chunk_document,
    chunk_docx,
    chunk_file,
    chunk_pdf,
    chunk_pptx,
    chunk_with_docling,
    chunk_xlsx,
)
from ..processing.discovery import discover_files, discover_images
from ..processing.embedder import OllamaEmbedder
from ..processing.vectorstore import QdrantManager

log = logging.getLogger("ollqd.worker.indexing")

BATCH_SIZE = 32

try:
    from ..gen.ollqd.v1 import processing_pb2 as indexing_pb2
    from ..gen.ollqd.v1 import types_pb2
    _STUBS_AVAILABLE = True
except ImportError:
    _STUBS_AVAILABLE = False

# In-memory set of cancelled task IDs for cooperative cancellation
_cancelled_tasks: set[str] = set()


def _make_progress(task_id: str, status: str, progress: float = 0.0,
                   message: str = "", result_json: str = ""):
    """Build a TaskProgress message.

    Proto fields: task_id, progress, status, error, result (map<string,string>).
    ``message`` is mapped to error for non-completed statuses.
    ``result_json`` is parsed and placed in the result map if provided.
    """
    result_map: dict[str, str] = {}
    if result_json:
        try:
            parsed = json.loads(result_json)
            result_map = {str(k): str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, AttributeError):
            result_map = {"raw": result_json}

    error_str = message if status in ("failed", "cancelled") else ""

    if _STUBS_AVAILABLE:
        return types_pb2.TaskProgress(
            task_id=task_id,
            status=status,
            progress=progress,
            error=error_str,
            result=result_map,
        )

    class _Progress:
        def __init__(self, **kw):
            self.__dict__.update(kw)
    return _Progress(
        task_id=task_id,
        status=status,
        progress=progress,
        error=error_str,
        result=result_map,
    )


def _caption_image_sync(base_url: str, model: str, image_b64: str,
                        prompt: str, timeout: float = 180.0) -> str:
    """Synchronous vision captioning for image indexing."""
    import httpx
    with httpx.Client(timeout=timeout) as client:
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


class IndexingServiceServicer:
    """gRPC servicer for all indexing operations (server streaming).

    All indexing methods yield TaskProgress messages to report progress.

    Methods:
        IndexCodebase  — index source code files from a directory
        IndexDocuments — index document files from given paths
        IndexImages    — index image files with vision-model captioning
        IndexUploads   — index pre-saved uploaded files (docs + images)
        IndexSMBFiles  — download files from SMB share, then index
        CancelTask     — cancel a running indexing task
    """

    async def IndexCodebase(self, request, context):
        """Index source code files from a codebase directory."""
        cfg = get_config()
        task_id = uuid.uuid4().hex[:12]

        root_path = request.root_path if hasattr(request, "root_path") else ""
        collection = request.collection if hasattr(request, "collection") and request.collection else "codebase"
        incremental = request.incremental if hasattr(request, "incremental") else True
        chunk_size = request.chunk_size if hasattr(request, "chunk_size") and request.chunk_size > 0 else cfg.chunking.chunk_size
        chunk_overlap = request.chunk_overlap if hasattr(request, "chunk_overlap") and request.chunk_overlap >= 0 else cfg.chunking.chunk_overlap
        extra_skip_dirs = list(request.extra_skip_dirs) if hasattr(request, "extra_skip_dirs") else []

        yield _make_progress(task_id, "running", 0.0, "Starting codebase indexing")

        root = Path(root_path).resolve()
        if not root.is_dir():
            yield _make_progress(task_id, "failed", 0.0, f"Not a directory: {root_path}")
            return

        # Discover files
        files = discover_files(root, cfg.chunking.max_file_size_kb, set(extra_skip_dirs))
        if not files:
            yield _make_progress(task_id, "completed", 1.0, "No indexable files",
                                 json.dumps({"files": 0, "chunks": 0}))
            return

        # Setup embedder + Qdrant
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

        # Incremental: filter unchanged files
        if incremental:
            indexed = qdrant.get_indexed_hashes()
            files = [f for f in files if indexed.get(f.path) != f.content_hash]
            for f in files:
                if f.path in indexed:
                    qdrant.delete_file_points(f.path)
            if not files:
                embedder.close()
                yield _make_progress(task_id, "completed", 1.0, "All up to date",
                                     json.dumps({"files": 0, "chunks": 0}))
                return

        yield _make_progress(task_id, "running", 0.05, f"Discovered {len(files)} files to index")

        # Chunk all files
        all_chunks = []
        for f in files:
            all_chunks.extend(chunk_file(f, chunk_size, chunk_overlap))

        total_upserted = 0
        total_batches = max(1, (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE)

        for i in range(0, len(all_chunks), BATCH_SIZE):
            # Cooperative cancellation
            if context.cancelled() or task_id in _cancelled_tasks:
                _cancelled_tasks.discard(task_id)
                embedder.close()
                yield _make_progress(task_id, "cancelled", 0.0)
                return

            batch = all_chunks[i:i + BATCH_SIZE]
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
                log.error("Batch %d failed: %s", i // BATCH_SIZE, e)

            batch_num = i // BATCH_SIZE + 1
            progress = batch_num / total_batches
            yield _make_progress(task_id, "running", progress,
                                 f"Batch {batch_num}/{total_batches}")

        embedder.close()
        result = {"files": len(files), "chunks": total_upserted, "collection": collection}
        yield _make_progress(task_id, "completed", 1.0, "Indexing complete",
                             json.dumps(result))

    async def IndexDocuments(self, request, context):
        """Index document files (markdown, text, rst, html) from given paths."""
        cfg = get_config()
        task_id = uuid.uuid4().hex[:12]

        paths = list(request.paths) if hasattr(request, "paths") else []
        collection = request.collection if hasattr(request, "collection") and request.collection else "documents"
        chunk_size = request.chunk_size if hasattr(request, "chunk_size") and request.chunk_size > 0 else cfg.chunking.chunk_size
        chunk_overlap = request.chunk_overlap if hasattr(request, "chunk_overlap") and request.chunk_overlap >= 0 else cfg.chunking.chunk_overlap
        source_tag = request.source_tag if hasattr(request, "source_tag") and request.source_tag else "docs"

        yield _make_progress(task_id, "running", 0.0, "Starting document indexing")

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

        all_chunks = []
        files_processed = 0
        for p in paths:
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
                    str(fp), content, lang, chunk_size, chunk_overlap, content_hash
                )
                all_chunks.extend(chunks)
                files_processed += 1

        yield _make_progress(task_id, "running", 0.1,
                             f"Chunked {files_processed} files into {len(all_chunks)} chunks")

        total_upserted = 0
        total_batches = max(1, (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE)
        for i in range(0, len(all_chunks), BATCH_SIZE):
            if context.cancelled() or task_id in _cancelled_tasks:
                _cancelled_tasks.discard(task_id)
                embedder.close()
                yield _make_progress(task_id, "cancelled", 0.0)
                return

            batch = all_chunks[i:i + BATCH_SIZE]
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
                log.error("Batch %d failed: %s", i // BATCH_SIZE, e)

            batch_num = i // BATCH_SIZE + 1
            yield _make_progress(task_id, "running", batch_num / total_batches,
                                 f"Batch {batch_num}/{total_batches}")

        embedder.close()
        result = {"files": files_processed, "chunks": total_upserted, "collection": collection}
        yield _make_progress(task_id, "completed", 1.0, "Document indexing complete",
                             json.dumps(result))

    async def IndexImages(self, request, context):
        """Index image files using vision-model captioning."""
        cfg = get_config()
        task_id = uuid.uuid4().hex[:12]

        root_path = request.root_path if hasattr(request, "root_path") else ""
        collection = request.collection if hasattr(request, "collection") and request.collection else "images"
        vision_model = request.vision_model if hasattr(request, "vision_model") and request.vision_model else cfg.ollama.vision_model
        caption_prompt = request.caption_prompt if hasattr(request, "caption_prompt") and request.caption_prompt else cfg.image.caption_prompt
        incremental = request.incremental if hasattr(request, "incremental") else True
        max_image_size_kb = request.max_image_size_kb if hasattr(request, "max_image_size_kb") and request.max_image_size_kb > 0 else cfg.image.max_image_size_kb
        extra_skip_dirs = list(request.extra_skip_dirs) if hasattr(request, "extra_skip_dirs") else []

        yield _make_progress(task_id, "running", 0.0, "Starting image indexing")

        root = Path(root_path).resolve()
        if not root.is_dir():
            yield _make_progress(task_id, "failed", 0.0, f"Not a directory: {root_path}")
            return

        images = discover_images(root, max_image_size_kb, set(extra_skip_dirs))
        if not images:
            yield _make_progress(task_id, "completed", 1.0, "No images found",
                                 json.dumps({"images_found": 0, "images_indexed": 0}))
            return

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

        # Incremental: skip unchanged images
        if incremental:
            indexed = qdrant.get_indexed_hashes()
            images = [img for img in images if indexed.get(img.path) != img.content_hash]
            for img in images:
                if img.path in indexed:
                    qdrant.delete_file_points(img.path)
            if not images:
                embedder.close()
                yield _make_progress(task_id, "completed", 1.0, "All images up to date",
                                     json.dumps({"images_found": 0, "images_indexed": 0}))
                return

        total = len(images)
        indexed_count = 0
        failed_count = 0

        for i, img in enumerate(images):
            if context.cancelled() or task_id in _cancelled_tasks:
                _cancelled_tasks.discard(task_id)
                embedder.close()
                yield _make_progress(task_id, "cancelled", 0.0)
                return

            try:
                image_bytes = Path(img.abs_path).read_bytes()
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")

                caption = _caption_image_sync(
                    cfg.ollama.base_url, vision_model, image_b64, caption_prompt
                )

                if not caption.strip():
                    log.warning("Empty caption for %s, skipping", img.path)
                    failed_count += 1
                    continue

                embed_text = f"Image: {img.path}\n\nCaption: {caption}"
                vectors = embedder.embed_texts([embed_text])

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

            yield _make_progress(task_id, "running", (i + 1) / total,
                                 f"Image {i + 1}/{total}")

        embedder.close()
        result = {
            "images_found": total,
            "images_indexed": indexed_count,
            "images_failed": failed_count,
            "collection": collection,
        }
        yield _make_progress(task_id, "completed", 1.0, "Image indexing complete",
                             json.dumps(result))

    async def IndexUploads(self, request, context):
        """Index pre-saved uploaded files (documents and images)."""
        cfg = get_config()
        task_id = uuid.uuid4().hex[:12]

        saved_paths = list(request.saved_paths) if hasattr(request, "saved_paths") else []
        collection = request.collection if hasattr(request, "collection") and request.collection else "documents"
        chunk_size = request.chunk_size if hasattr(request, "chunk_size") and request.chunk_size > 0 else cfg.chunking.chunk_size
        chunk_overlap = request.chunk_overlap if hasattr(request, "chunk_overlap") and request.chunk_overlap >= 0 else cfg.chunking.chunk_overlap
        source_tag = request.source_tag if hasattr(request, "source_tag") and request.source_tag else "upload"
        vision_model = request.vision_model if hasattr(request, "vision_model") and request.vision_model else cfg.ollama.vision_model
        caption_prompt = request.caption_prompt if hasattr(request, "caption_prompt") and request.caption_prompt else cfg.image.caption_prompt

        yield _make_progress(task_id, "running", 0.0, "Starting upload indexing")

        _img_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
        doc_paths = []
        image_paths = []
        for p in saved_paths:
            if Path(p).suffix.lower() in _img_exts:
                image_paths.append(p)
            else:
                doc_paths.append(p)

        total_files = len(saved_paths)

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

        # Phase 1: Process document files
        all_chunks = []
        files_processed = 0

        for p in doc_paths:
            fp = Path(p)
            ext = fp.suffix.lower()
            try:
                raw = fp.read_bytes()
                content_hash = hashlib.sha256(raw).hexdigest()
                chunks = None

                # Try docling first
                if cfg.docling.enabled:
                    chunks = chunk_with_docling(
                        file_path=str(fp), file_bytes=raw,
                        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                        content_hash=content_hash,
                        ocr_enabled=cfg.docling.ocr_enabled,
                        ocr_engine=cfg.docling.ocr_engine,
                        table_structure=cfg.docling.table_structure,
                        timeout_s=cfg.docling.timeout_s,
                    )

                # Fallback to legacy parsers
                if chunks is None:
                    if ext == ".pdf":
                        chunks = chunk_pdf(str(fp), raw, chunk_size, chunk_overlap, content_hash)
                    elif ext == ".docx":
                        chunks = chunk_docx(str(fp), raw, chunk_size, chunk_overlap, content_hash)
                    elif ext == ".xlsx":
                        chunks = chunk_xlsx(str(fp), raw, chunk_size, chunk_overlap, content_hash)
                    elif ext == ".pptx":
                        chunks = chunk_pptx(str(fp), raw, chunk_size, chunk_overlap, content_hash)
                    elif ext in (".csv", ".adoc", ".asciidoc"):
                        content = raw.decode("utf-8", errors="replace")
                        chunks = chunk_document(str(fp), content, "text", chunk_size, chunk_overlap, content_hash)
                    else:
                        content = raw.decode("utf-8", errors="replace")
                        lang = "markdown" if ext in (".md", ".rst") else "text"
                        chunks = chunk_document(str(fp), content, lang, chunk_size, chunk_overlap, content_hash)

                if chunks:
                    all_chunks.extend(chunks)
                files_processed += 1
            except Exception as e:
                log.error("Failed to process uploaded file %s: %s", p, e)

        total_upserted = 0
        if all_chunks:
            doc_weight = len(doc_paths) / max(total_files, 1)
            total_batches = max(1, (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE)
            for i in range(0, len(all_chunks), BATCH_SIZE):
                if context.cancelled() or task_id in _cancelled_tasks:
                    _cancelled_tasks.discard(task_id)
                    embedder.close()
                    yield _make_progress(task_id, "cancelled", 0.0)
                    return
                batch = all_chunks[i:i + BATCH_SIZE]
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
                    log.error("Batch %d failed: %s", i // BATCH_SIZE, e)

                batch_num = i // BATCH_SIZE + 1
                yield _make_progress(task_id, "running",
                                     doc_weight * batch_num / total_batches,
                                     f"Doc batch {batch_num}/{total_batches}")

        # Phase 2: Process image files
        images_indexed = 0
        images_failed = 0

        for j, img_path in enumerate(image_paths):
            if context.cancelled() or task_id in _cancelled_tasks:
                _cancelled_tasks.discard(task_id)
                embedder.close()
                yield _make_progress(task_id, "cancelled", 0.0)
                return

            fp = Path(img_path)
            try:
                image_bytes = fp.read_bytes()
                content_hash = hashlib.sha256(image_bytes).hexdigest()
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")

                caption = _caption_image_sync(
                    cfg.ollama.base_url, vision_model, image_b64, caption_prompt
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
            yield _make_progress(task_id, "running",
                                 doc_weight + img_weight * (j + 1) / len(image_paths),
                                 f"Image {j + 1}/{len(image_paths)}")

        embedder.close()
        result = {
            "files": files_processed,
            "chunks": total_upserted,
            "images_indexed": images_indexed,
            "images_failed": images_failed,
            "collection": collection,
        }
        yield _make_progress(task_id, "completed", 1.0, "Upload indexing complete",
                             json.dumps(result))

    async def IndexSMBFiles(self, request, context):
        """Download files from an SMB share, then chunk, embed, and index them."""
        cfg = get_config()
        task_id = uuid.uuid4().hex[:12]

        # SMB connection info from the request
        server = request.server if hasattr(request, "server") else ""
        share = request.share if hasattr(request, "share") else ""
        username = request.username if hasattr(request, "username") else ""
        password = request.password if hasattr(request, "password") else ""
        domain = request.domain if hasattr(request, "domain") else ""
        port = request.port if hasattr(request, "port") and request.port > 0 else 445
        remote_paths = list(request.remote_paths) if hasattr(request, "remote_paths") else []
        collection = request.collection if hasattr(request, "collection") and request.collection else "documents"
        chunk_size = request.chunk_size if hasattr(request, "chunk_size") and request.chunk_size > 0 else cfg.chunking.chunk_size
        chunk_overlap = request.chunk_overlap if hasattr(request, "chunk_overlap") and request.chunk_overlap >= 0 else cfg.chunking.chunk_overlap
        source_tag = request.source_tag if hasattr(request, "source_tag") and request.source_tag else "smb"

        yield _make_progress(task_id, "running", 0.0, "Starting SMB file indexing")

        # Download files to temp dir
        from ..processing.smb_client import SMBManager, SMBShareConfig
        smb = SMBManager()
        smb_config = SMBShareConfig(
            id="grpc_temp",
            server=server,
            share=share,
            username=username,
            password=password,
            domain=domain,
            port=port,
        )
        smb.add_share(smb_config)

        tmp_dir = Path(mkdtemp(prefix="ollqd_smb_"))
        try:
            local_paths = smb.download_files("grpc_temp", remote_paths, tmp_dir)
        except Exception as e:
            yield _make_progress(task_id, "failed", 0.0, f"SMB download failed: {e}")
            return

        yield _make_progress(task_id, "running", 0.1,
                             f"Downloaded {len(local_paths)} files from SMB")

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

        all_chunks = []
        files_processed = 0

        for p in local_paths:
            fp = Path(p)
            ext = fp.suffix.lower()
            try:
                raw = fp.read_bytes()
                content_hash = hashlib.sha256(raw).hexdigest()

                if ext == ".pdf":
                    chunks = chunk_pdf(str(fp), raw, chunk_size, chunk_overlap, content_hash)
                elif ext in (".md", ".txt", ".rst", ".html"):
                    content = raw.decode("utf-8", errors="replace")
                    lang = "markdown" if ext in (".md", ".rst") else "text"
                    chunks = chunk_document(str(fp), content, lang, chunk_size, chunk_overlap, content_hash)
                else:
                    continue

                all_chunks.extend(chunks)
                files_processed += 1
            except Exception as e:
                log.error("Failed to process SMB file %s: %s", p, e)

        if not all_chunks:
            embedder.close()
            yield _make_progress(task_id, "completed", 1.0, "No content extracted",
                                 json.dumps({"files": files_processed, "chunks": 0}))
            return

        total_upserted = 0
        total_batches = max(1, (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE)
        for i in range(0, len(all_chunks), BATCH_SIZE):
            if context.cancelled() or task_id in _cancelled_tasks:
                _cancelled_tasks.discard(task_id)
                embedder.close()
                yield _make_progress(task_id, "cancelled", 0.0)
                return

            batch = all_chunks[i:i + BATCH_SIZE]
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
                log.error("Batch %d failed: %s", i // BATCH_SIZE, e)

            batch_num = i // BATCH_SIZE + 1
            yield _make_progress(task_id, "running", 0.1 + 0.9 * batch_num / total_batches,
                                 f"Batch {batch_num}/{total_batches}")

        embedder.close()
        result = {"files": files_processed, "chunks": total_upserted, "collection": collection}
        yield _make_progress(task_id, "completed", 1.0, "SMB indexing complete",
                             json.dumps(result))

    async def CancelTask(self, request, context):
        """Cancel a running indexing task by its task_id."""
        task_id = request.task_id if hasattr(request, "task_id") else ""
        if not task_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "task_id is required")

        _cancelled_tasks.add(task_id)
        log.info("Task %s marked for cancellation", task_id)

        if _STUBS_AVAILABLE:
            return indexing_pb2.CancelTaskResponse(
                cancelled=True,
                message=f"Task {task_id} marked for cancellation",
            )

        class _Resp:
            def __init__(self, **kw):
                self.__dict__.update(kw)
        return _Resp(cancelled=True, message=f"Task {task_id} marked for cancellation")

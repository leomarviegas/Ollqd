"""SMB/CIFS share management and file browsing endpoints."""

import asyncio
import hashlib
import logging
import uuid
from pathlib import Path
from tempfile import mkdtemp

from fastapi import APIRouter, Depends, HTTPException
from qdrant_client.models import PointStruct

from ...chunking import chunk_document, chunk_pdf
from ...embedder import OllamaEmbedder
from ...vectorstore import QdrantManager
from ..deps import get_config, get_smb_manager, get_task_manager
from ..models import (
    SMBShareCreateRequest,
    SMBShareIndexRequest,
    SMBShareListFilesRequest,
    SMBShareTestRequest,
)
from ..services.smb_service import SMBManager, SMBShareConfig
from ..services.task_manager import TaskManager

log = logging.getLogger("ollqd.web.smb")
router = APIRouter()
BATCH_SIZE = 32


@router.get("/shares")
def list_shares(smb: SMBManager = Depends(get_smb_manager)):
    return {"shares": [
        {
            "id": s.id, "server": s.server, "share": s.share,
            "username": s.username, "domain": s.domain,
            "port": s.port, "label": s.label,
            "display_name": s.display_name,
        }
        for s in smb.list_shares()
    ]}


@router.post("/shares")
def add_share(
    req: SMBShareCreateRequest,
    smb: SMBManager = Depends(get_smb_manager),
):
    config = SMBShareConfig(
        id=uuid.uuid4().hex[:12],
        server=req.server,
        share=req.share,
        username=req.username,
        password=req.password,
        domain=req.domain,
        port=req.port,
        label=req.label,
    )
    smb.add_share(config)
    return {"id": config.id, "display_name": config.display_name}


@router.delete("/shares/{share_id}")
def remove_share(share_id: str, smb: SMBManager = Depends(get_smb_manager)):
    if not smb.remove_share(share_id):
        raise HTTPException(404, "Share not found")
    return {"removed": share_id}


@router.post("/shares/test")
def test_share(
    req: SMBShareTestRequest,
    smb: SMBManager = Depends(get_smb_manager),
):
    config = SMBShareConfig(
        id="test", server=req.server, share=req.share,
        username=req.username, password=req.password,
        domain=req.domain, port=req.port,
    )
    return smb.test_connection(config)


@router.post("/shares/{share_id}/browse")
def browse_share(
    share_id: str,
    req: SMBShareListFilesRequest,
    smb: SMBManager = Depends(get_smb_manager),
):
    try:
        files = smb.list_remote_files(share_id, req.path)
        return {"files": files, "path": req.path}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Browse failed: {e}")


def _run_smb_index(
    task_id: str,
    smb: SMBManager,
    share_id: str,
    remote_paths: list[str],
    collection: str,
    chunk_size: int,
    chunk_overlap: int,
    source_tag: str,
):
    """Background worker: download files from SMB, chunk, embed, upsert."""
    cfg = get_config()
    tm = get_task_manager()
    tm.start(task_id)

    # Download files to temp dir
    tmp_dir = Path(mkdtemp(prefix="ollqd_smb_"))
    try:
        local_paths = smb.download_files(share_id, remote_paths, tmp_dir)
    except Exception as e:
        tm.fail(task_id, f"SMB download failed: {e}")
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
        tm.complete(task_id, {"files": files_processed, "chunks": 0, "message": "No content extracted"})
        return

    total_upserted = 0
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
        tm.update_progress(task_id, (i + 1) / total_batches)

    embedder.close()
    tm.complete(task_id, {"files": files_processed, "chunks": total_upserted, "collection": collection})


@router.post("/shares/{share_id}/index")
async def index_share_files(
    share_id: str,
    req: SMBShareIndexRequest,
    smb: SMBManager = Depends(get_smb_manager),
    tm: TaskManager = Depends(get_task_manager),
):
    """Download selected files from SMB share, then index into Qdrant."""
    share = smb.get_share(share_id)
    if not share:
        raise HTTPException(404, "Share not found")

    task_id = tm.create_with_params("index_smb", {
        "share_id": share_id,
        "remote_paths": req.remote_paths,
        "collection": req.collection,
        "chunk_size": req.chunk_size,
        "chunk_overlap": req.chunk_overlap,
        "source_tag": req.source_tag,
    })

    asyncio.get_event_loop().run_in_executor(
        None, _run_smb_index, task_id, smb, share_id,
        req.remote_paths, req.collection,
        req.chunk_size, req.chunk_overlap, req.source_tag,
    )

    return {"task_id": task_id, "status": "started"}

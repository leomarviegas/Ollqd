"""Qdrant management endpoints — collections, points, search."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    VectorParams,
)

from ..deps import get_qdrant_client
from ..models import CreateCollectionRequest, SearchRequest

router = APIRouter()


# ── Collections ─────────────────────────────────────────────


@router.get("/collections")
def list_collections(client: QdrantClient = Depends(get_qdrant_client)):
    collections = client.get_collections().collections
    result = []
    for c in collections:
        info = client.get_collection(c.name)
        vec_cfg = info.config.params.vectors
        result.append(
            {
                "name": c.name,
                "points_count": info.points_count or 0,
                "status": info.status.value if info.status else "unknown",
                "config": {
                    "size": vec_cfg.size if hasattr(vec_cfg, "size") else None,
                    "distance": vec_cfg.distance.value
                    if hasattr(vec_cfg, "distance")
                    else None,
                },
            }
        )
    return {"collections": result}


@router.post("/collections")
def create_collection(
    req: CreateCollectionRequest,
    client: QdrantClient = Depends(get_qdrant_client),
):
    distance_map = {
        "Cosine": Distance.COSINE,
        "Euclid": Distance.EUCLID,
        "Dot": Distance.DOT,
        "Manhattan": Distance.MANHATTAN,
    }
    try:
        client.create_collection(
            collection_name=req.name,
            vectors_config=VectorParams(
                size=req.vector_size, distance=distance_map[req.distance]
            ),
        )
        for field_name in ("file_path", "language", "content_hash"):
            client.create_payload_index(
                collection_name=req.name,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        return {"status": "ok", "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/collections/{name}")
def get_collection(name: str, client: QdrantClient = Depends(get_qdrant_client)):
    try:
        info = client.get_collection(name)
        vec_cfg = info.config.params.vectors
        return {
            "name": name,
            "points_count": info.points_count or 0,
            "status": info.status.value if info.status else "unknown",
            "config": {
                "size": vec_cfg.size if hasattr(vec_cfg, "size") else None,
                "distance": vec_cfg.distance.value
                if hasattr(vec_cfg, "distance")
                else None,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/collections/{name}")
def delete_collection(name: str, client: QdrantClient = Depends(get_qdrant_client)):
    try:
        client.delete_collection(collection_name=name)
        return {"status": "ok", "deleted": name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Points ──────────────────────────────────────────────────


@router.get("/collections/{name}/points")
def scroll_points(
    name: str,
    limit: int = 20,
    offset: Optional[str] = None,
    client: QdrantClient = Depends(get_qdrant_client),
):
    try:
        points, next_offset = client.scroll(
            collection_name=name,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        return {
            "points": [
                {"id": p.id, "payload": p.payload} for p in points
            ],
            "next_offset": next_offset,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/collections/{name}/points/{point_id}")
def get_point(
    name: str,
    point_id: str,
    client: QdrantClient = Depends(get_qdrant_client),
):
    try:
        points = client.retrieve(
            collection_name=name, ids=[point_id], with_payload=True, with_vectors=False
        )
        if not points:
            raise HTTPException(status_code=404, detail="Point not found")
        p = points[0]
        return {"id": p.id, "payload": p.payload}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/collections/{name}/count")
def count_points(name: str, client: QdrantClient = Depends(get_qdrant_client)):
    try:
        info = client.get_collection(name)
        return {"collection": name, "count": info.points_count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collections/{name}/search")
def search_points(
    name: str,
    req: SearchRequest,
    client: QdrantClient = Depends(get_qdrant_client),
):
    """Text-based search — embeds the query and searches Qdrant."""
    from ..deps import get_embedder

    embedder = get_embedder()
    try:
        query_vec = embedder.embed_query(req.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")

    conditions = []
    if req.language:
        conditions.append(
            FieldCondition(key="language", match=MatchValue(value=req.language))
        )
    query_filter = Filter(must=conditions) if conditions else None

    try:
        results = client.query_points(
            collection_name=name,
            query=query_vec,
            limit=req.top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        hits = []
        for p in results.points:
            hits.append(
                {
                    "id": p.id,
                    "score": p.score,
                    "file_path": p.payload.get("file_path", ""),
                    "language": p.payload.get("language", ""),
                    "lines": f"{p.payload.get('start_line', '?')}-{p.payload.get('end_line', '?')}",
                    "content": p.payload.get("content", ""),
                }
            )
        return {"results": hits}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        embedder.close()

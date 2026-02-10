"""Qdrant vector store manager."""

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from ..errors import VectorStoreError

log = logging.getLogger("ollqd.vectorstore")


class QdrantManager:
    """Manages Qdrant collections and point operations."""

    def __init__(self, url: str, collection: str, dimension: int, distance: str = "Cosine"):
        try:
            self.client = QdrantClient(url=url)
        except Exception as e:
            raise VectorStoreError(f"Cannot connect to Qdrant at {url}: {e}") from e
        self.collection = collection
        self.dimension = dimension
        self.distance = distance

    _distance_map = {
        "Cosine": Distance.COSINE,
        "Euclid": Distance.EUCLID,
        "Dot": Distance.DOT,
        "Manhattan": Distance.MANHATTAN,
    }

    def ensure_collection(self):
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection in collections:
            log.info("Collection '%s' already exists", self.collection)
            return

        dist = self._distance_map.get(self.distance, Distance.COSINE)
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.dimension, distance=dist),
        )
        for field in ("file_path", "language", "content_hash"):
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        log.info("Created collection '%s' (dim=%d, %s)", self.collection, self.dimension, self.distance)

    def get_indexed_hashes(self) -> dict[str, str]:
        result: dict[str, str] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection,
                limit=256,
                offset=offset,
                with_payload=["file_path", "content_hash"],
                with_vectors=False,
            )
            for p in points:
                fp = p.payload.get("file_path", "")
                ch = p.payload.get("content_hash", "")
                if fp:
                    result[fp] = ch
            if offset is None:
                break
        return result

    def delete_file_points(self, file_path: str):
        self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
            ),
        )

    def upsert_batch(self, points: list[PointStruct]):
        self.client.upsert(collection_name=self.collection, points=points)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        language: Optional[str] = None,
        file_filter: Optional[str] = None,
    ) -> list[dict]:
        conditions = []
        if language:
            conditions.append(FieldCondition(key="language", match=MatchValue(value=language)))
        if file_filter:
            conditions.append(FieldCondition(key="file_path", match=MatchValue(value=file_filter)))

        query_filter = Filter(must=conditions) if conditions else None

        results = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )

        hits = []
        for point in results.points:
            hit = {
                "score": point.score,
                "file_path": point.payload.get("file_path", ""),
                "language": point.payload.get("language", ""),
                "lines": f"{point.payload.get('start_line', '?')}-{point.payload.get('end_line', '?')}",
                "chunk": f"{point.payload.get('chunk_index', 0) + 1}/{point.payload.get('total_chunks', '?')}",
                "content": point.payload.get("content", ""),
            }
            # Include extra fields for image results
            if point.payload.get("language") == "image":
                hit["abs_path"] = point.payload.get("abs_path", "")
                hit["caption"] = point.payload.get("caption", "")
                hit["image_type"] = point.payload.get("image_type", "")
                if point.payload.get("width"):
                    hit["width"] = point.payload["width"]
                    hit["height"] = point.payload["height"]
            hits.append(hit)
        return hits

    def count(self) -> int:
        info = self.client.get_collection(self.collection)
        return info.points_count

    def list_collections(self) -> list[dict]:
        collections = self.client.get_collections().collections
        result = []
        for c in collections:
            info = self.client.get_collection(c.name)
            result.append({"name": c.name, "points": info.points_count})
        return result

    def delete_collection(self, name: str):
        self.client.delete_collection(collection_name=name)
        log.info("Deleted collection '%s'", name)

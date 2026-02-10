"""VisualizationService gRPC servicer — vector space and codebase visualizations."""

import json
import logging

import grpc

from ..config import get_config

log = logging.getLogger("ollqd.worker.visualization")

try:
    from ..gen.ollqd.v1 import processing_pb2 as visualization_pb2
    _STUBS_AVAILABLE = True
except ImportError:
    _STUBS_AVAILABLE = False

# ── Language -> Color Mapping ────────────────────────────────

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


class _Response:
    """Fallback response object when proto stubs are not generated."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


class VisualizationServiceServicer:
    """gRPC servicer for visualization data.

    Methods:
        Overview  — force-graph nodes/edges by file aggregation
        FileTree  — hierarchical file -> chunks view
        Vectors   — PCA/t-SNE dimensionality reduction for scatter plot
    """

    async def Overview(self, request, context):
        """Aggregate points by file_path for a vis-network force graph."""
        cfg = get_config()

        collection = request.collection if hasattr(request, "collection") and request.collection else "codebase"
        limit = request.limit if hasattr(request, "limit") and request.limit > 0 else 500
        limit = min(limit, 5000)

        from qdrant_client import QdrantClient
        client = QdrantClient(url=cfg.qdrant.url)

        try:
            client.get_collection(collection)
        except Exception:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"Collection '{collection}' not found"
            )

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

        # Build graph data
        nodes = [{"id": 0, "label": collection, "color": "#2196F3", "size": 50, "shape": "diamond"}]
        edges = []
        for i, (fp, stats) in enumerate(file_stats.items(), start=1):
            color = _language_color(stats["language"])
            label = fp.split("/")[-1] if "/" in fp else fp
            nodes.append({
                "id": i, "label": label,
                "title": f"{fp}\n{stats['count']} chunks\n{stats['language']}",
                "color": color, "size": max(15, min(50, stats["count"] * 3)),
                "file_path": fp, "language": stats["language"], "chunks": stats["count"],
            })
            edges.append({"from": 0, "to": i})

        result = {
            "nodes_json": json.dumps(nodes),
            "edges_json": json.dumps(edges),
            "stats_json": json.dumps({
                "total_files": len(file_stats),
                "total_chunks": fetched,
                "collection": collection,
            }),
        }

        if _STUBS_AVAILABLE:
            return visualization_pb2.OverviewResponse(**result)
        return _Response(**result)

    async def FileTree(self, request, context):
        """Hierarchical view: file -> chunks for one file."""
        cfg = get_config()

        collection = request.collection if hasattr(request, "collection") and request.collection else "codebase"
        file_path = request.file_path if hasattr(request, "file_path") else ""

        if not file_path:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "file_path is required")

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
                scroll_filter=Filter(
                    must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
                ),
                with_payload=True,
                with_vectors=False,
            )
            chunks.extend(points)
            if offset is None:
                break

        if not chunks:
            result = {
                "nodes_json": json.dumps([]),
                "edges_json": json.dumps([]),
                "file_path": file_path,
                "total_chunks": 0,
            }
            if _STUBS_AVAILABLE:
                return visualization_pb2.FileTreeResponse(**result)
            return _Response(**result)

        lang = chunks[0].payload.get("language", "unknown")
        file_color = _language_color(lang)

        # File node
        nodes = [{"id": 0, "label": file_path.split("/")[-1], "title": file_path,
                   "color": file_color, "level": 0, "size": 40}]
        edges = []

        for i, p in enumerate(
            sorted(chunks, key=lambda x: x.payload.get("chunk_index", 0)), start=1
        ):
            chunk_idx = p.payload.get("chunk_index", 0)
            lines = f"L{p.payload.get('start_line', '?')}-{p.payload.get('end_line', '?')}"
            content_preview = (p.payload.get("content", "")[:80] + "...") if p.payload.get("content", "") else ""
            nodes.append({
                "id": i, "label": f"Chunk {chunk_idx}",
                "title": f"{lines}\n{content_preview}",
                "color": file_color, "level": 1, "size": 25, "shape": "box",
            })
            edges.append({"from": 0, "to": i})

        result = {
            "nodes_json": json.dumps(nodes),
            "edges_json": json.dumps(edges),
            "file_path": file_path,
            "total_chunks": len(chunks),
        }

        if _STUBS_AVAILABLE:
            return visualization_pb2.FileTreeResponse(**result)
        return _Response(**result)

    async def Vectors(self, request, context):
        """Reduce vectors to 2D/3D for scatter plot using PCA or t-SNE."""
        import numpy as np

        cfg = get_config()

        collection = request.collection if hasattr(request, "collection") and request.collection else "codebase"
        method = request.method if hasattr(request, "method") and request.method else "pca"
        dims = request.dims if hasattr(request, "dims") and request.dims in (2, 3) else 3
        limit = request.limit if hasattr(request, "limit") and request.limit > 0 else 500
        limit = max(10, min(limit, 2000))

        if method not in ("pca", "tsne"):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Invalid method: {method}. Must be 'pca' or 'tsne'"
            )

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
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                "Need at least 2 points for visualization"
            )

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

        result = {
            "points_json": json.dumps(result_points),
            "method": method,
            "dims": dims,
            "original_dims": original_dims,
            "total_points": len(result_points),
        }

        if _STUBS_AVAILABLE:
            return visualization_pb2.VectorsResponse(**result)
        return _Response(**result)

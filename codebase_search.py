#!/usr/bin/env python3
"""
Codebase Search — Query your indexed codebase via Qdrant + Ollama
=================================================================
Semantic search over the codebase indexed by codebase_indexer.py.
Supports interactive REPL mode and single-query CLI mode.

Usage:
    python codebase_search.py "how does authentication work"
    python codebase_search.py --interactive
    python codebase_search.py "database connection" --language python --top-k 10
"""

import argparse
import json
import sys
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_COLLECTION = "codebase"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_TOP_K = 5


def embed_query(ollama_url: str, model: str, query: str) -> list[float]:
    """Get embedding for a search query."""
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{ollama_url.rstrip('/')}/api/embed",
            json={"model": model, "input": [query]},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]


def search(
    qdrant_url: str,
    collection: str,
    query_vector: list[float],
    top_k: int = DEFAULT_TOP_K,
    language: str | None = None,
    file_filter: str | None = None,
) -> list[dict]:
    """Search Qdrant for the most relevant code chunks."""
    client = QdrantClient(url=qdrant_url)

    conditions = []
    if language:
        conditions.append(FieldCondition(key="language", match=MatchValue(value=language)))
    if file_filter:
        conditions.append(FieldCondition(key="file_path", match=MatchValue(value=file_filter)))

    query_filter = Filter(must=conditions) if conditions else None

    results = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    hits = []
    for point in results.points:
        hits.append({
            "score": point.score,
            "file_path": point.payload.get("file_path", ""),
            "language": point.payload.get("language", ""),
            "lines": f"{point.payload.get('start_line', '?')}-{point.payload.get('end_line', '?')}",
            "chunk": f"{point.payload.get('chunk_index', 0)+1}/{point.payload.get('total_chunks', '?')}",
            "content": point.payload.get("content", ""),
        })
    return hits


def format_result(hit: dict, index: int, show_content: bool = True) -> str:
    """Format a single search result for terminal display."""
    lines = [
        f"\n{'─' * 70}",
        f"  #{index+1}  {hit['file_path']}  (L{hit['lines']})  chunk {hit['chunk']}",
        f"  score: {hit['score']:.4f}  |  language: {hit['language']}",
        f"{'─' * 70}",
    ]
    if show_content:
        # Truncate very long content for display
        content = hit["content"]
        if len(content) > 2000:
            content = content[:2000] + "\n... [truncated]"
        lines.append(content)
    return "\n".join(lines)


def format_results_json(hits: list[dict]) -> str:
    """Format results as JSON (for piping to other tools / MCP)."""
    return json.dumps(hits, indent=2)


def interactive_repl(
    ollama_url: str,
    qdrant_url: str,
    collection: str,
    model: str,
    top_k: int,
):
    """Interactive search REPL."""
    print(f"\n🔍 Codebase Search (collection: {collection}, model: {model})")
    print(f"   Type a query to search. Commands: :quit, :top N, :lang <lang>, :json\n")

    language = None
    output_json = False

    while True:
        try:
            query = input("search❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not query:
            continue
        if query in (":quit", ":q", ":exit"):
            break
        if query.startswith(":top "):
            try:
                top_k = int(query.split()[1])
                print(f"  → top_k set to {top_k}")
            except ValueError:
                print("  → Usage: :top N")
            continue
        if query.startswith(":lang"):
            parts = query.split(maxsplit=1)
            language = parts[1] if len(parts) > 1 and parts[1] != "all" else None
            print(f"  → language filter: {language or 'none'}")
            continue
        if query == ":json":
            output_json = not output_json
            print(f"  → JSON output: {'on' if output_json else 'off'}")
            continue

        try:
            vec = embed_query(ollama_url, model, query)
            hits = search(qdrant_url, collection, vec, top_k=top_k, language=language)
        except Exception as e:
            print(f"  Error: {e}")
            continue

        if not hits:
            print("  No results found.")
            continue

        if output_json:
            print(format_results_json(hits))
        else:
            for i, hit in enumerate(hits):
                print(format_result(hit, i))
            print()


def main():
    parser = argparse.ArgumentParser(
        description="Semantic search over an indexed codebase",
    )
    parser.add_argument("query", nargs="?", help="Search query (omit for interactive mode)")
    parser.add_argument("--interactive", "-I", action="store_true", help="Interactive REPL mode")
    parser.add_argument("--collection", "-c", default=DEFAULT_COLLECTION)
    parser.add_argument("--embedding-model", "-e", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL)
    parser.add_argument("--top-k", "-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--language", "-l", help="Filter by language (e.g. python, go, typescript)")
    parser.add_argument("--file", "-f", help="Filter by file path")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.interactive or args.query is None:
        interactive_repl(
            args.ollama_url, args.qdrant_url, args.collection,
            args.embedding_model, args.top_k,
        )
        return

    vec = embed_query(args.ollama_url, args.embedding_model, args.query)
    hits = search(
        args.qdrant_url, args.collection, vec,
        top_k=args.top_k, language=args.language, file_filter=args.file,
    )

    if not hits:
        print("No results found.")
        sys.exit(1)

    if args.json:
        print(format_results_json(hits))
    else:
        for i, hit in enumerate(hits):
            print(format_result(hit, i))


if __name__ == "__main__":
    main()

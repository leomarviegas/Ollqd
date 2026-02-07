# Architecture

## 1. High-Level Design (HLD)

### 1.1 System Overview

Ollqd is a local-first RAG (Retrieval-Augmented Generation) system that combines Ollama (local LLM/embeddings), Qdrant (vector database), and the Model Context Protocol (MCP) to enable AI-powered semantic search over codebases, documents, and images — all without sending data to third-party cloud APIs.

The system has three interfaces:
- **WebUI** (FastAPI + Alpine.js) — browser-based dashboard, chat, indexing, and management
- **CLI/REPL** (`ollqd-chat`) — terminal-based RAG chat with tool-calling
- **MCP Server** (`ollqd-server`) — stdio-based tool server for Claude Desktop and other MCP hosts

```
+===========================================================================+
|                          PRESENTATION LAYER                                |
|  +----------------+   +-------------------+   +------------------------+  |
|  | WebUI (SPA)    |   | ollqd-chat        |   | Claude Desktop /       |  |
|  | Alpine.js      |   | CLI / REPL        |   | Any MCP Host           |  |
|  | localhost:8000  |   |                   |   |                        |  |
|  +-------+--------+   +--------+----------+   +-----------+------------+  |
+=========|======================|===========================|==============+
          | HTTP/WS              | stdio                     | stdio
+=========|======================|===========================|==============+
|         |              SERVICE LAYER                       |              |
|  +------v---------+   +-------v-----------+   +-----------v----------+   |
|  | FastAPI Server  |   | MCP Client Layer  |   | MCP Server (FastMCP) |   |
|  | REST + WS + SSE |   | MCPBridge         |   | 5 tools              |   |
|  | 25+ endpoints   |   | OllamaToolAgent   |   | index / search /     |   |
|  | Background tasks|   | RAGLoopRunner     |   | manage collections   |   |
|  +------+----------+   +---------+---------+   +-----------+----------+   |
+=========|========================|===========================|============+
          |                        |                           |
+=========|========================|===========================|============+
|                            CORE LAYER                                     |
|  +------------+  +----------+  +-----------+  +------------------------+  |
|  | Discovery   |  | Chunking |  | Embedder  |  | VectorStore            |  |
|  | files +     |  | code +   |  | Ollama    |  | Qdrant Manager         |  |
|  | images      |  | docs     |  | /api/embed|  | CRUD + search          |  |
|  +------+------+  +----+-----+  +-----+-----+  +------------+-----------+  |
+=========|===============|==============|======================|===========+
          |               |              |                      |
+=========|===============|==============|======================|===========+
|                       INFRASTRUCTURE LAYER                                |
|  +------------------+  +-------------------+  +------------------------+  |
|  | Local File System |  | Ollama Server     |  | Qdrant Vector DB       |  |
|  | source code,      |  | /api/embed        |  | cosine similarity      |  |
|  | images, documents |  | /api/chat         |  | payload indexes        |  |
|  |                   |  | /api/chat (vision) |  | scroll pagination      |  |
|  +------------------+  +-------------------+  +------------------------+  |
+===========================================================================+
```

### 1.2 Design Principles

| Principle | Description |
|-----------|-------------|
| **Local-first** | All data stays on the user's machine. No cloud APIs required. |
| **Protocol-driven** | MCP (JSON-RPC over stdio) enables any compatible AI host to use ollqd tools. |
| **Incremental** | SHA-256 content hashing ensures only changed files/images are re-indexed. |
| **Language-agnostic** | Heuristic boundary detection supports 40+ programming languages. |
| **Composable** | Server, client, and WebUI are independent — use any combination. |
| **Zero-build frontend** | Alpine.js + Tailwind CDN — no npm, no webpack, no build step. |
| **Caption-first images** | Vision models generate text captions that reuse the existing text embedding pipeline. |

### 1.3 Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Alpine.js 3.x + Tailwind CSS + Font Awesome 6.5 | Zero-build SPA |
| Web Server | FastAPI + Uvicorn | REST, WebSocket, SSE, static files |
| Protocol | MCP (Model Context Protocol) | Standardized AI tool interface |
| Server framework | FastMCP (`mcp` Python SDK) | Declarative tool registration |
| Transport | stdio (JSON-RPC 2.0) | Process-level isolation |
| Embeddings | Ollama `/api/embed` | Local embedding generation (1024-dim) |
| Chat/LLM | Ollama `/api/chat` | Tool-calling RAG responses |
| Vision | Ollama `/api/chat` + images array | Image captioning (llava, etc.) |
| Vector DB | Qdrant | Cosine similarity search, payload indexing |
| HTTP client | httpx (sync + async) | All Ollama/Qdrant communication |
| Background tasks | `asyncio.run_in_executor` + `TaskManager` | Non-blocking indexing |
| Language | Python 3.10+ | Core runtime |
| Containers | Docker + Docker Compose | Multi-service deployment |

### 1.4 Key Architectural Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| stdio transport for MCP (not HTTP) | Process isolation, no port conflicts, simpler security | Single-client; no multi-tenant |
| Heuristic chunking (not tree-sitter) | Zero-dependency, works for 40+ languages | ~90% accuracy vs AST-perfect splits |
| Deterministic point IDs (`md5(path::chunk_N)`) | Idempotent upserts, reliable incremental mode | MD5 collision risk (negligible) |
| Caption-first image RAG (not CLIP) | Reuses text embedding pipeline, no extra model | Loses direct visual similarity |
| In-memory TaskManager | Simple, no DB dependency | Tasks lost on restart |
| Alpine.js (not React/Vue) | No build step, CDN-only, tiny footprint | Less ecosystem/tooling |
| Sync embedder in threads | Simpler code path, Ollama handles batching | Slightly slower than full async |
| Module-level config (`AppConfig()`) | Single config instance, env var overrides | Not easily testable with different configs |

### 1.5 Deployment Topologies

#### A. Local Development (Default)

```
Developer Machine
  +-- ollqd-web (Python) ........... :8000
  +-- Ollama (native/Docker) ....... :11434
  +-- Qdrant (Docker) .............. :6333
```

#### B. Docker Compose (All-in-One)

```
docker-compose.yml
  +-- web (ollqd-web image) ........ :8000  -> ollama:11434, qdrant:6333
  +-- ollama (ollama/ollama) ....... :11434
  +-- qdrant (qdrant/qdrant) ....... :6333
  volumes: qdrant_data, ollama_data
```

#### C. MCP-Only (Claude Desktop)

```
Claude Desktop
  +-- ollqd-server (stdio child process)
       +-> Ollama :11434
       +-> Qdrant :6333
```

---

## 2. Low-Level Design (LLD)

### 2.1 Module Dependency Graph

```
Entry Points                   Core Modules                External
-----------                    -----------                 --------
web/app.py -----------------> config.py                   fastapi
web/routers/rag.py ----------> discovery.py --------+      uvicorn
web/routers/qdrant.py -------> chunking.py ------+  |      httpx
web/routers/ollama.py -------> embedder.py ----+ |  |      qdrant-client
web/routers/system.py -------> vectorstore.py  | |  |      mcp SDK
                               models.py <-----+-+--+
server/main.py --------------> errors.py <-----+-+
client/main.py -> rag_loop.py -> mcp_bridge.py -------->   mcp SDK
              |-> ollama_agent.py ---------------------->   httpx
```

### 2.2 Package Structure

```
src/ollqd/
|-- __init__.py              # Package root
|-- config.py                # 7 dataclass configs (Ollama, Qdrant, Chunking, Image, Server, Client, App)
|-- errors.py                # 6 exception types (OllqdError base + 5 specific)
|-- models.py                # 5 dataclasses (FileInfo, Chunk, SearchResult, ImageFileInfo, IndexingStats)
|-- discovery.py             # discover_files() (40+ langs), discover_images() (7 formats)
|-- chunking.py              # chunk_file(), chunk_document(), _is_boundary_line()
|-- embedder.py              # OllamaEmbedder (sync httpx, batch embed, dimension probe)
|-- vectorstore.py           # QdrantManager (ensure_collection, upsert, search, incremental)
|
|-- server/
|   |-- __init__.py
|   |-- main.py              # FastMCP server, 5 tool handlers, batch processing
|
|-- client/
|   |-- __init__.py
|   |-- main.py              # CLI entry point (argparse, single/interactive modes)
|   |-- mcp_bridge.py        # MCPBridge (async context manager, stdio transport)
|   |-- ollama_agent.py      # OllamaToolAgent (async httpx, /api/chat with tools)
|   |-- rag_loop.py          # RAGLoopRunner (tool conversion, multi-round loop)
|
|-- web/
    |-- __init__.py
    |-- app.py               # FastAPI app factory, CORS, static mount, router includes
    |-- deps.py              # Dependency injection (config, qdrant, embedder, ollama, tasks)
    |-- models.py            # 10 Pydantic request/response schemas
    |-- routers/
    |   |-- system.py        # GET /health, GET /config
    |   |-- qdrant.py        # Collections CRUD, points scroll, search
    |   |-- ollama.py        # Models list/pull/delete, chat/generate/embed streams
    |   |-- rag.py           # Indexing (codebase/docs/images), search, image serving, WS chat
    |-- services/
    |   |-- ollama_service.py  # Async Ollama wrapper (17 methods)
    |   |-- task_manager.py    # In-memory task tracking (create/start/progress/complete/fail)
    |-- static/
        |-- index.html       # SPA markup (409 lines, 5 views + 3 modals)
        |-- app.js           # Alpine.js app logic (500+ lines)
        |-- styles.css       # Custom styles (thumbnails, chat, animations)
```

### 2.3 Class Design

#### Configuration (`config.py`)

```
AppConfig
 +-- ollama: OllamaConfig
 |    +-- base_url (env: OLLAMA_URL)
 |    +-- chat_model (env: OLLAMA_CHAT_MODEL)
 |    +-- embed_model (env: OLLAMA_EMBED_MODEL)
 |    +-- vision_model (env: OLLAMA_VISION_MODEL)
 |    +-- timeout_s (env: OLLAMA_TIMEOUT_S)
 +-- qdrant: QdrantConfig
 |    +-- url (env: QDRANT_URL)
 |    +-- default_collection (env: QDRANT_COLLECTION)
 +-- chunking: ChunkingConfig
 |    +-- chunk_size (env: CHUNK_SIZE)
 |    +-- chunk_overlap (env: CHUNK_OVERLAP)
 |    +-- max_file_size_kb
 +-- image: ImageConfig
 |    +-- max_image_size_kb (env: MAX_IMAGE_SIZE_KB)
 |    +-- caption_prompt
 |    +-- supported_extensions
 +-- server: ServerConfig
 |    +-- name, transport
 +-- client: ClientConfig
      +-- max_tool_rounds (env: MAX_TOOL_ROUNDS)
```

#### Exception Hierarchy (`errors.py`)

```
OllqdError (base)
 +-- ConfigError
 +-- EmbeddingError
 +-- VectorStoreError
 +-- ChunkingError
 +-- MCPToolError
 +-- MCPClientError
```

#### Data Models (`models.py`)

```
FileInfo           # path, abs_path, language, size_bytes, content_hash
Chunk              # file_path, language, chunk_index, total_chunks, start_line, end_line, content, content_hash
                   # property: point_id = md5(file_path::chunk_N)
SearchResult       # score, file_path, language, lines, chunk, content
ImageFileInfo      # path, abs_path, extension, size_bytes, content_hash, width?, height?
IndexingStats      # files_discovered, files_indexed, files_skipped, chunks_created, chunks_failed, elapsed_seconds
```

#### Task Management (`task_manager.py`)

```
TaskStatus(Enum): PENDING -> RUNNING -> COMPLETED | FAILED

TaskInfo
 +-- id: str (hex UUID fragment)
 +-- type: str (index_codebase | index_documents | index_images)
 +-- status: TaskStatus
 +-- progress: float (0.0 - 1.0)
 +-- result: dict | None
 +-- error: str | None
 +-- created_at, completed_at

TaskManager
 +-- create(type) -> task_id
 +-- start(task_id)
 +-- update_progress(task_id, progress)
 +-- complete(task_id, result)
 +-- fail(task_id, error)
 +-- get(task_id) -> dict
 +-- list_all() -> list[dict]
 +-- _prune() -- keeps last 100 tasks
```

### 2.4 Qdrant Collection Schema

```
Collection: "codebase" (or "images", "documents", user-defined)
+-- Vector Config
|    +-- Size: dynamic (1024 for qwen3-embedding, 768 for nomic)
|    +-- Distance: Cosine
+-- Payload Indexes (keyword type)
|    +-- file_path    -- enables file-filtered search
|    +-- language      -- enables language-filtered search ("image" for images)
|    +-- content_hash  -- enables incremental indexing
+-- Point Schema (Code/Document)
|    +-- id: md5("file_path::chunk_N")
|    +-- vector: float[dim]
|    +-- payload: file_path, language, chunk_index, total_chunks,
|                 start_line, end_line, content, content_hash
+-- Point Schema (Image)
     +-- id: md5("image::path")
     +-- vector: float[dim]  (embedding of caption text)
     +-- payload: file_path, abs_path, language="image", image_type,
                  caption, content=caption, content_hash,
                  chunk_index=0, total_chunks=1, width?, height?
```

### 2.5 WebUI Frontend Architecture

```
index.html (SPA shell)
 +-- Alpine.js x-data="app()" binding
 +-- Tailwind CSS (CDN)
 +-- Font Awesome 6.5 (CDN)
 +-- 5 views (x-show conditional):
 |    +-- Dashboard: stats cards + collections table
 |    +-- Collections: CRUD, browse points, semantic search
 |    +-- Models: list, pull (SSE progress), details modal, delete
 |    +-- RAG Chat: WebSocket streaming, markdown rendering, sources with image thumbnails
 |    +-- Indexing: tabbed form (Codebase | Images), task progress tracking
 +-- 3 modals: create collection, pull model, model details

app.js (Alpine.js logic)
 +-- State: view, health, collections, models, tasks, chat*, index*
 +-- API calls: fetch() for REST, WebSocket for chat
 +-- Polling: _pollTask() for background job progress
 +-- Markdown: _renderMarkdown() (code blocks, bold, italic, line breaks)
```

### 2.6 Security Model

| Layer | Mechanism |
|-------|-----------|
| Image serving | Extension allowlist (`.png/.jpg/.jpeg/.gif/.webp/.bmp/.tiff`), path validation |
| File discovery | Skip directories (`.git`, `node_modules`, etc.), max file size limits |
| Collection delete | Requires `confirm=true` in MCP tool, browser `confirm()` in WebUI |
| CORS | Wildcard in dev (configurable for production) |
| Input validation | Pydantic models with field constraints (min_length, ge, le) |
| No auth | Local-only deployment assumption (Qdrant/Ollama bound to localhost) |

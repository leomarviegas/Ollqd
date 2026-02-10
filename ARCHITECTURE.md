# Ollqd Architecture Documentation

> **Version:** 0.3.0 | **Last updated:** 2026-02-09

---

## Table of Contents

- [1. System Overview](#1-system-overview)
- [2. Architecture Evolution](#2-architecture-evolution)
- [3. High-Level Architecture](#3-high-level-architecture)
- [4. Service Descriptions](#4-service-descriptions)
  - [4.1 Go API Gateway](#41-go-api-gateway)
  - [4.2 Python gRPC Worker](#42-python-grpc-worker)
  - [4.3 Qdrant Vector Database](#43-qdrant-vector-database)
  - [4.4 Ollama LLM Server](#44-ollama-llm-server)
- [5. Protocol Buffer Contracts](#5-protocol-buffer-contracts)
  - [5.1 Shared Types](#51-shared-types)
  - [5.2 gRPC Services](#52-grpc-services)
- [6. Key Streaming Patterns](#6-key-streaming-patterns)
  - [6.1 Indexing (Server Streaming)](#61-indexing-server-streaming)
  - [6.2 RAG Chat (WebSocket-to-gRPC Bridge)](#62-rag-chat-websocket-to-grpc-bridge)
- [7. API Endpoint Map](#7-api-endpoint-map)
- [8. Project Structure](#8-project-structure)
- [9. Docker Compose Topology](#9-docker-compose-topology)
- [10. Environment Variables](#10-environment-variables)
- [11. Build & Run](#11-build--run)
- [12. Design Decisions](#12-design-decisions)
- [13. Migration Strategy](#13-migration-strategy)

---

## 1. System Overview

Ollqd is an MCP (Model Context Protocol) client-server **Retrieval-Augmented Generation** system. It indexes codebases, documents, and images into a Qdrant vector database using Ollama embeddings, enabling:

- **Semantic search** across code, documents, and images
- **RAG chat** with streaming responses, source citations, and context-aware answers
- **PII masking/unmasking** via regex patterns and spaCy NER during chat and indexing
- **Document conversion** for PDF, DOCX, XLSX, PPTX (via Docling and legacy parsers)
- **Image captioning** using Ollama vision models
- **SMB file access** for indexing remote network shares
- **Interactive visualizations** (force graphs, file trees, PCA/t-SNE vector projections)

---

## 2. Architecture Evolution

### Before: Monolithic FastAPI

```
 Browser / MCP Client
         |
         v
 [Python FastAPI :8000]
   ├── Web routing (5 routers)
   ├── File discovery & chunking
   ├── Embedding via Ollama
   ├── Vector ops via Qdrant
   ├── PII masking (spaCy)
   ├── Docling conversion
   ├── Visualization (numpy/sklearn)
   └── WebSocket chat
         |
    +---------+---------+
    |                   |
 [Ollama :11434]   [Qdrant :6333]
```

**Problem:** Web routing and heavy processing (chunking, embedding, indexing, RAG chat) were tangled in a single 1100-line `rag.py` monolith. Scaling, testing, and language-appropriate tooling were constrained.

### After: Decoupled Three-Tier Architecture

```
 Browser / MCP Client
         |
         v
 [Go API Gateway :8000]  ────────────────────────────> [Ollama :11434]
   │  (REST + WebSocket)                                 (reverse proxy)
   │
   │ gRPC (proto/ollqd/v1/)                            [Qdrant :6333]
   │                                                     (reverse proxy)
   v
 [Python gRPC Worker :50051]  ──────> [Ollama :11434]
   (headless processing)              [Qdrant :6333]
```

---

## 3. High-Level Architecture

```
                    +-----------------------+
                    |     Browser / CLI     |
                    +-----------+-----------+
                                |
                          HTTP / WebSocket
                                |
                    +-----------v-----------+
                    |   Go API Gateway      |
                    |       :8000           |
                    |                       |
                    |  +-----------------+  |
                    |  |  chi Router     |  |
                    |  |  CORS, Logger   |  |
                    |  +-----------------+  |
                    |                       |
                    |  +---------+-------+  |
                    |  | Reverse | Task  |  |
                    |  | Proxies | Store |  |
                    |  +---------+-------+  |
                    +----|---------|--------+
                         |         |
              +----------+    +----v----------+
              |               |               |
     +--------v-----+   +----v----+   +------v------+
     | Ollama       |   | Qdrant  |   | Python gRPC |
     | :11434       |   | :6333   |   | Worker      |
     | (proxy)      |   | (proxy) |   | :50051      |
     +--------------+   +---------+   |             |
                                      | Services:   |
                                      |  Indexing   |
                                      |  Search     |
                                      |  Chat       |
                                      |  Embedding  |
                                      |  PII        |
                                      |  Config     |
                                      |  Visualize  |
                                      |  SMB        |
                                      +------+------+
                                             |
                                      +------v------+
                                      | Ollama      |
                                      | Qdrant      |
                                      | (direct)    |
                                      +-------------+
```

### Data Flow Summary

| Operation | Flow |
|-----------|------|
| Ollama model list | Client -> Gateway -> Ollama (reverse proxy) |
| Qdrant collections | Client -> Gateway -> Qdrant (reverse proxy) |
| Health check | Client -> Gateway -> ping Ollama + Qdrant directly |
| Search | Client -> Gateway -> gRPC SearchService -> Ollama (embed) + Qdrant (query) |
| Index codebase | Client -> Gateway (creates task) -> gRPC IndexingService (stream) -> Ollama + Qdrant |
| RAG chat | Client -> WebSocket -> Gateway -> gRPC ChatService (stream) -> Ollama + Qdrant |
| File upload | Client -> Gateway (save multipart) -> gRPC IndexingService |
| Visualization | Client -> Gateway -> gRPC VisualizationService -> Qdrant + numpy/sklearn |

---

## 4. Service Descriptions

### 4.1 Go API Gateway

**Port:** 8000 (public)
**Language:** Go 1.23
**Framework:** [chi](https://github.com/go-chi/chi) router
**Container:** `ollqd-gateway`

The gateway is the **single public entry point**. It handles:

#### Direct Operations (no gRPC round-trip)
- **Ollama reverse proxy** (`/api/ollama/*`) — `httputil.ReverseProxy` with `FlushInterval: -1` for chunked streaming passthrough (chat, generate, pull)
- **Qdrant reverse proxy** (`/api/qdrant/*`) — `httputil.ReverseProxy` for collection and search operations
- **Health checks** — pings Ollama and Qdrant directly
- **Task management** — in-memory task store (mutex-protected), CRUD + retry
- **File upload** — multipart form parsing, saves to `/uploads`, then delegates to gRPC
- **Image serving** — `http.ServeFile` from upload directory
- **Static SPA** — serves existing `static/` directory with SPA fallback to `index.html`

#### gRPC-Delegated Operations
All heavy computation is delegated to the Python worker via gRPC:
- Indexing (codebase, documents, images, uploads, SMB)
- Semantic search (embed query + Qdrant search)
- RAG chat (embed + search + PII + LLM stream)
- Embedding configuration, testing, model comparison
- PII masking test
- Application configuration management
- Visualizations (requires numpy/sklearn)

#### Middleware Stack
1. **CORS** — allows all origins, all methods
2. **Request logger** — logs method, path, status, duration (API routes only)
3. **Recoverer** — panic recovery
4. **RealIP** — extracts client IP from proxy headers

#### Graceful Shutdown
Listens for SIGINT/SIGTERM, drains connections with a 10-second grace period. gRPC connection is closed via `defer gc.Close()`.

---

### 4.2 Python gRPC Worker

**Port:** 50051 (internal only, not exposed publicly)
**Language:** Python 3.12
**Framework:** `grpc.aio` (async gRPC server)
**Container:** `ollqd-worker`

The worker is a **headless processing server** with no HTTP endpoints. It owns all computation-heavy operations that require Python-native libraries.

#### Registered Services

| Service | Methods | Description |
|---------|---------|-------------|
| `ConfigService` | 7 RPCs | Get/update application configuration |
| `EmbeddingService` | 4 RPCs | Embedding model info, test, compare, switch |
| `PIIService` | 1 RPC | Test PII masking on sample text |
| `SearchService` | 2 RPCs | Embed query + Qdrant semantic search |
| `ChatService` | 1 RPC (streaming) | RAG chat with context search, PII, streaming LLM |
| `IndexingService` | 6 RPCs (5 streaming) | Index codebase/docs/images/uploads/SMB + cancel |
| `VisualizationService` | 3 RPCs | Force graph, file tree, PCA/t-SNE vectors |

#### Processing Pipeline

```
File Discovery → Language-Aware Chunking → Embedding (Ollama) → Upsert (Qdrant)
                       │
                       ├── Code: chunk_file() with syntax-aware splits
                       ├── Markdown/Text: chunk_document()
                       ├── PDF: chunk_pdf() (PyMuPDF) or Docling
                       ├── DOCX: chunk_docx() (python-docx) or Docling
                       ├── XLSX: chunk_xlsx() (openpyxl)
                       ├── PPTX: chunk_pptx() (python-pptx)
                       └── Images: vision captioning → embed caption
```

#### Server Configuration
- Max message size: 50 MB (send + receive)
- Graceful shutdown: 5-second grace period on SIGTERM/SIGINT
- Stub-safe: all services work with or without generated proto stubs (fallback to plain Python objects)

---

### 4.3 Qdrant Vector Database

**Ports:** 6333 (REST), 6334 (gRPC)
**Image:** `qdrant/qdrant:latest`
**Container:** `ollqd-qdrant`

Stores vector embeddings with rich payloads (file path, language, content, line numbers, content hash). Supports cosine distance by default. Data persisted in a named Docker volume (`qdrant_data`).

---

### 4.4 Ollama LLM Server

**Port:** 11434
**Image:** `ollama/ollama:latest`
**Container:** `ollqd-ollama`

Provides local LLM inference for:
- **Embeddings:** `qwen3-embedding:0.6b` (1024 dimensions)
- **Chat:** `qwen3-vl:235b-cloud`, `ministral-3:14b-cloud`
- **Vision:** captioning for image indexing

Configured with `OLLAMA_KEEP_ALIVE=24h` to prevent model unloading between requests.

---

## 5. Protocol Buffer Contracts

All contracts are defined in `proto/ollqd/v1/` and compiled to both Go and Python stubs.

### 5.1 Shared Types (`types.proto`)

```protobuf
message Chunk {
  string file_path, language, content, content_hash, point_id, source_tag;
  int32  chunk_index, total_chunks, start_line, end_line;
}

message SearchHit {
  float score; string file_path, language, lines, content, caption, image_type;
  int32 width, height;
}

message TaskProgress {
  string task_id, status, error;  // status: running|completed|failed|cancelled
  float  progress;                // 0.0 to 1.0
  map<string, string> result;
}

message AppConfig {
  OllamaConfig, QdrantConfig, ChunkingConfig, ImageConfig,
  UploadConfig, PIIConfig, DoclingConfig;
  repeated string mounted_paths;
}
```

### 5.2 gRPC Services (`processing.proto`)

| # | Service | RPC Methods | Streaming |
|---|---------|-------------|-----------|
| 1 | `IndexingService` | IndexCodebase, IndexDocuments, IndexImages, IndexUploads, IndexSMBFiles, CancelTask | Server streaming (5 methods return `stream TaskProgress`) |
| 2 | `SearchService` | Search, SearchCollection | Unary |
| 3 | `ChatService` | Chat | Server streaming (`stream ChatEvent`) |
| 4 | `EmbeddingService` | GetInfo, TestEmbed, CompareModels, SetModel | Unary |
| 5 | `PIIService` | TestMasking | Unary |
| 6 | `ConfigService` | GetConfig, UpdateMountedPaths, UpdatePII, UpdateDocling, UpdateDistance, GetPIIConfig, GetDoclingConfig | Unary |
| 7 | `VisualizationService` | Overview, FileTree, Vectors | Unary |
| 8 | `SMBService` | TestConnection, Browse | Unary |

#### ChatEvent Types

| Type | Content | Description |
|------|---------|-------------|
| `chunk` | Token text | Streaming LLM response token |
| `sources` | JSON array of SearchHit | Context sources used for RAG |
| `done` | JSON with PII info | Stream complete |
| `error` | Error message | Error occurred |

---

## 6. Key Streaming Patterns

### 6.1 Indexing (Server Streaming)

```
Client                    Gateway                     Worker
  |                         |                           |
  |  POST /api/rag/index/*  |                           |
  |------------------------>|                           |
  |                         | Create task (in-memory)   |
  |                         | Start goroutine           |
  |  {"task_id": "abc123"} |                           |
  |<------------------------|                           |
  |                         |  gRPC IndexCodebase()     |
  |                         |-------------------------->|
  |                         |                           | Discover files
  |                         |  stream TaskProgress      | Chunk files
  |                         |<--------------------------| Embed batches
  |                         | Update task store          | Upsert to Qdrant
  |                         |                           |
  |  GET /api/rag/tasks/abc |                           |
  |------------------------>|                           |
  |  {"progress": 0.65}    |                           |
  |<------------------------|                           |
  |                         |  TaskProgress(completed)  |
  |                         |<--------------------------|
  |                         | Mark task complete         |
  |  GET /api/rag/tasks/abc |                           |
  |------------------------>|                           |
  |  {"status":"completed"} |                           |
  |<------------------------|                           |
```

**Key details:**
- Gateway creates a **background goroutine** per indexing request
- Goroutine reads `TaskProgress` messages and updates the in-memory task store
- Client **polls** `GET /api/rag/tasks/{id}` for progress
- Cancellation: `DELETE /api/rag/tasks/{id}` cancels the gRPC context
- Worker uses cooperative cancellation: checks `context.cancelled()` between batches

### 6.2 RAG Chat (WebSocket-to-gRPC Bridge)

```
Client                    Gateway                     Worker
  |                         |                           |
  |  WS /api/rag/ws/chat   |                           |
  |<=======================>| (WebSocket upgrade)       |
  |                         |                           |
  |  {"message":"..."}      |                           |
  |------------------------>|                           |
  |                         |  gRPC Chat(ChatRequest)   |
  |                         |-------------------------->|
  |                         |                           | 1. Embed query
  |                         |                           | 2. Search Qdrant
  |                         |                           | 3. Mask PII
  |                         |                           | 4. Build prompt
  |                         |  ChatEvent(chunk)         | 5. Stream Ollama
  |                         |<--------------------------|
  |  {"type":"chunk",...}   |                           |
  |<------------------------|                           |
  |  {"type":"chunk",...}   | ChatEvent(chunk)          |
  |<------------------------|<--------------------------|
  |  ...                    |                           |
  |                         |  ChatEvent(sources)       | 6. Unmask PII
  |                         |<--------------------------|
  |  {"type":"sources",...} |                           |
  |<------------------------|                           |
  |                         |  ChatEvent(done)          |
  |                         |<--------------------------|
  |  {"type":"done",...}    |                           |
  |<------------------------|                           |
```

**Key details:**
- Each WebSocket message opens a **new gRPC Chat stream** with a cancellable context
- If the WebSocket disconnects mid-stream, the gRPC context is cancelled
- PII masking: query + context are masked before sending to Ollama, response tokens are unmasked via `StreamUnmaskBuffer` before sending to client
- Sources include scored file paths, line numbers, and content snippets

---

## 7. API Endpoint Map

| Method | Path | Handler | Backend |
|--------|------|---------|---------|
| `GET` | `/api/system/health` | system.go | Direct (Ollama + Qdrant ping) |
| `GET` | `/api/system/config` | system.go | gRPC ConfigService |
| `PUT` | `/api/system/config/mounted-paths` | system.go | gRPC ConfigService |
| `PUT` | `/api/system/config/pii` | system.go | gRPC ConfigService |
| `PUT` | `/api/system/config/docling` | system.go | gRPC ConfigService |
| `PUT` | `/api/system/config/distance` | system.go | gRPC ConfigService |
| `GET` | `/api/system/embedding/info` | system.go | gRPC EmbeddingService |
| `POST` | `/api/system/embedding/test` | system.go | gRPC EmbeddingService |
| `POST` | `/api/system/embedding/compare` | system.go | gRPC EmbeddingService |
| `POST` | `/api/system/embedding/model` | system.go | gRPC EmbeddingService |
| `POST` | `/api/system/pii/test` | system.go | gRPC PIIService |
| `GET` | `/api/system/pii/config` | system.go | gRPC ConfigService |
| `GET` | `/api/system/docling/config` | system.go | gRPC ConfigService |
| `ANY` | `/api/ollama/*` | ollama.go | Reverse proxy to Ollama |
| `ANY` | `/api/qdrant/*` | qdrant.go | Reverse proxy to Qdrant |
| `POST` | `/api/rag/search` | rag.go | gRPC SearchService |
| `POST` | `/api/rag/search/{collection}` | rag.go | gRPC SearchService |
| `POST` | `/api/rag/index/codebase` | rag.go | gRPC IndexingService (streaming) |
| `POST` | `/api/rag/index/documents` | rag.go | gRPC IndexingService (streaming) |
| `POST` | `/api/rag/index/images` | rag.go | gRPC IndexingService (streaming) |
| `POST` | `/api/rag/upload` | upload.go | Save file + gRPC IndexingService |
| `GET` | `/api/rag/tasks` | tasks.go | In-memory task store |
| `GET` | `/api/rag/tasks/{id}` | tasks.go | In-memory task store |
| `DELETE` | `/api/rag/tasks/{id}` | tasks.go | Cancel task + gRPC CancelTask |
| `POST` | `/api/rag/tasks/{id}/retry` | tasks.go | Re-open gRPC stream |
| `DELETE` | `/api/rag/tasks` | tasks.go | Clear finished tasks |
| `GET` | `/api/rag/ws/chat` | ws.go | gRPC ChatService (streaming) |
| `GET` | `/api/rag/visualize/{col}/overview` | rag.go | gRPC VisualizationService |
| `GET` | `/api/rag/visualize/{col}/file-tree` | rag.go | gRPC VisualizationService |
| `GET` | `/api/rag/visualize/{col}/vectors` | rag.go | gRPC VisualizationService |
| `GET` | `/api/rag/image/{path}` | image.go | Static file serving |
| `POST` | `/api/smb/shares` | smb.go | In-memory store + gRPC SMBService |
| `GET` | `/api/smb/shares` | smb.go | In-memory store |
| `GET` | `/api/smb/shares/{id}` | smb.go | In-memory store |
| `DELETE` | `/api/smb/shares/{id}` | smb.go | In-memory store |
| `POST` | `/api/smb/shares/{id}/test` | smb.go | gRPC SMBService |
| `POST` | `/api/smb/shares/{id}/browse` | smb.go | gRPC SMBService |
| `POST` | `/api/smb/shares/{id}/index` | smb.go | gRPC IndexingService |
| `*` | `/*` | SPA fallback | Static files |

---

## 8. Project Structure

```
ollqd/
├── proto/ollqd/v1/                    # Protocol Buffer definitions
│   ├── types.proto                    # Shared messages (Chunk, SearchHit, TaskProgress, configs)
│   └── processing.proto               # 8 gRPC service definitions
│
├── gateway/                           # Go API Gateway
│   ├── cmd/gateway/main.go           # Entry point: config, gRPC client, HTTP server
│   ├── internal/
│   │   ├── config/config.go          # Env-based configuration
│   │   ├── server/server.go          # chi router, middleware, route groups, SPA fallback
│   │   ├── grpc/client.go            # gRPC client connection pool to Python worker
│   │   ├── tasks/manager.go          # In-memory task store (mutex-protected)
│   │   ├── proxy/
│   │   │   ├── ollama.go             # httputil.ReverseProxy with streaming support
│   │   │   └── qdrant.go             # httputil.ReverseProxy
│   │   └── handlers/
│   │       ├── helpers.go            # JSON response / error helpers
│   │       ├── system.go             # /api/system/* (health, config, embedding, PII)
│   │       ├── ollama.go             # /api/ollama/* -> Ollama proxy
│   │       ├── qdrant.go             # /api/qdrant/* -> Qdrant proxy
│   │       ├── rag.go                # /api/rag/search, /index, /visualize -> gRPC
│   │       ├── tasks.go              # /api/rag/tasks/* CRUD + retry
│   │       ├── upload.go             # /api/rag/upload -> multipart save + gRPC
│   │       ├── ws.go                 # /api/rag/ws/chat -> WebSocket-to-gRPC bridge
│   │       ├── smb.go                # /api/smb/* -> in-memory + gRPC SMBService
│   │       └── image.go              # /api/rag/image -> static file serving
│   ├── gen/ollqd/v1/                 # Generated Go protobuf stubs
│   ├── static/                       # Static SPA files (copied into Docker image)
│   ├── go.mod                        # chi, gorilla/websocket, grpc, protobuf
│   └── Dockerfile.gateway            # Multi-stage Go 1.23-alpine build
│
├── src/ollqd_worker/                  # Python gRPC Worker
│   ├── __init__.py
│   ├── main.py                       # grpc.aio server on :50051, graceful shutdown
│   ├── config.py                     # AppConfig singleton (env-based)
│   ├── errors.py                     # Exception hierarchy
│   ├── models.py                     # FileInfo, Chunk, SearchResult, ImageFileInfo
│   ├── processing/
│   │   ├── chunking.py               # Language-aware code/doc/PDF/DOCX/XLSX/PPTX chunking
│   │   ├── discovery.py              # File and image discovery with skip patterns
│   │   ├── embedder.py               # OllamaEmbedder (sync httpx client)
│   │   ├── vectorstore.py            # QdrantManager (CRUD, search, hash tracking)
│   │   ├── docling_converter.py      # Docling integration for Office/PDF conversion
│   │   ├── pii_masking.py            # Regex + spaCy NER masking, EntityRegistry, StreamUnmaskBuffer
│   │   ├── ollama_client.py          # Async httpx Ollama client (chat streaming)
│   │   └── smb_client.py             # SMBManager with pysmb
│   ├── services/
│   │   ├── config_svc.py             # ConfigServiceServicer
│   │   ├── embedding.py              # EmbeddingServiceServicer
│   │   ├── pii.py                    # PIIServiceServicer
│   │   ├── search.py                 # SearchServiceServicer
│   │   ├── chat.py                   # ChatServiceServicer (server streaming)
│   │   ├── indexing.py               # IndexingServiceServicer (5 streaming methods)
│   │   └── visualization.py          # VisualizationServiceServicer
│   └── gen/ollqd/v1/                 # Generated Python protobuf stubs
│
├── src/ollqd/                         # Legacy FastAPI app (kept for migration)
│   └── web/                          # Original monolithic web layer
│
├── Makefile                           # proto-gen, build-gateway, build-worker, docker-*
├── Dockerfile.worker                  # Python 3.12-slim with grpcio, spaCy, Docling
├── docker-compose.yml                # Full stack: qdrant, ollama, worker, gateway
└── pyproject.toml                    # Python project config with worker deps
```

---

## 9. Docker Compose Topology

```
                    +-------------------+
                    |   docker-compose  |
                    +-------------------+
                    |                   |
     +--------------+---+  +-----------+----------+
     |  ollqd-qdrant    |  |  ollqd-ollama        |
     |  qdrant:latest   |  |  ollama:latest       |
     |  :6333 (REST)    |  |  :11434              |
     |  :6334 (gRPC)    |  |  KEEP_ALIVE=24h      |
     |  vol: qdrant_data|  |  vol: ollama_data     |
     +------------------+  +-----------------------+
              ^  ^                  ^  ^
              |  |                  |  |
     +--------+--+---------+-------+--+----------+
     |                     |                      |
     |  ollqd-gateway      |  ollqd-worker        |
     |  Go 1.23-alpine     |  Python 3.12-slim    |
     |  :8000 (public)     |  :50051 (internal)   |
     |  vol: uploads_data  |  vol: uploads_data   |
     |  depends: worker,   |  depends: qdrant,    |
     |    ollama, qdrant   |    ollama             |
     +---------------------+----------------------+
```

### Service Details

| Service | Image | Ports | Volumes | Restart |
|---------|-------|-------|---------|---------|
| `qdrant` | `qdrant/qdrant:latest` | 6333, 6334 | `qdrant_data` | unless-stopped |
| `ollama` | `ollama/ollama:latest` | 11434 | `ollama_data` | unless-stopped |
| `worker` | Custom (Dockerfile.worker) | 50051 (expose) | `uploads_data`, host mounts | unless-stopped |
| `gateway` | Custom (Dockerfile.gateway) | 8000 | `uploads_data` | unless-stopped |
| `web` (legacy) | Custom (Dockerfile) | 8001 | `uploads_data`, host mounts | unless-stopped, profile: `legacy` |

### Named Volumes
- `qdrant_data` — Qdrant storage persistence
- `ollama_data` — Downloaded model weights
- `uploads_data` — Shared upload directory between gateway and worker

---

## 10. Environment Variables

### Gateway

| Variable | Default | Description |
|----------|---------|-------------|
| `LISTEN_ADDR` | `:8000` | HTTP listen address |
| `WORKER_ADDR` | `worker:50051` | gRPC worker address |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama base URL for reverse proxy |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant base URL for reverse proxy |
| `UPLOAD_DIR` | `/uploads` | Directory for uploaded files |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum upload size in megabytes |
| `STATIC_DIR` | `/static` | Directory for static SPA files |

### Worker

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | `50051` | gRPC server port |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama base URL |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant base URL |
| `MOUNTED_PATHS` | _(empty)_ | Comma-separated allowed mount paths |
| `UPLOAD_DIR` | `/uploads` | Upload storage directory |
| `PII_MASKING_ENABLED` | `false` | Enable PII masking globally |
| `PII_USE_SPACY` | `true` | Use spaCy NER in addition to regex |
| `DOCLING_ENABLED` | `true` | Enable Docling for document conversion |

---

## 11. Build & Run

### Prerequisites
- Go 1.23+
- Python 3.12+
- `protoc` with Go and Python plugins
- Docker & Docker Compose

### Generate Proto Stubs

```bash
# Generate both Go and Python stubs
make proto-gen

# Or individually
make proto-go    # -> gateway/gen/ollqd/v1/
make proto-py    # -> src/ollqd_worker/gen/ollqd/v1/
```

### Local Development

```bash
# Build Go gateway
make build-gateway    # -> gateway/bin/gateway

# Install Python worker dependencies
make build-worker     # pip install -e ".[worker]"
```

### Docker

```bash
# Build all images
docker compose build

# Start full stack (qdrant, ollama, worker, gateway)
docker compose up -d

# Stop all services
docker compose down

# Also start legacy FastAPI service (optional)
docker compose --profile legacy up -d
```

### Clean Generated Files

```bash
make clean-proto
```

---

## 12. Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Go for the gateway** | Efficient reverse proxying with built-in streaming support, minimal memory footprint, goroutine-per-request for concurrent gRPC streams, fast startup |
| **Python stays for processing** | numpy, sklearn, spaCy, docling, PyMuPDF, and Ollama client libraries are Python-native; no benefit to rewriting in Go |
| **gRPC over REST for IPC** | Type-safe contracts via protobuf, native server streaming for progress and chat, efficient binary encoding, built-in cancellation propagation |
| **In-memory task store in Go** | Indexing tasks are transient (minutes); gRPC streams update progress in real-time via goroutines; no need for external state store |
| **WebSocket-to-gRPC bridge** | Preserves the existing WebSocket chat API (browser-compatible) while delegating all LLM processing to Python |
| **Reverse proxies for Ollama/Qdrant** | Go proxies these directly, avoiding unnecessary gRPC round-trips for simple pass-through requests that don't need processing |
| **Cooperative cancellation** | Worker checks `context.cancelled()` between batches; gateway cancels gRPC context on task delete or WebSocket disconnect |
| **Stub-safe services** | Python servicers work with or without generated proto stubs via try/except imports and fallback plain objects, enabling gradual migration |
| **Legacy service on profile** | Original FastAPI app available via `--profile legacy` on port 8001 for parallel testing during migration |

---

## 13. Migration Strategy

### Phase 1: Parallel Operation
- Legacy FastAPI (`web`) runs on port 8001 via Docker profile `legacy`
- New stack (gateway + worker) runs on port 8000
- Both share the same Qdrant and Ollama instances

### Phase 2: Endpoint Verification
- Test each endpoint group against the same curl/WebSocket commands
- Verify: health, config, search, indexing with progress, chat streaming, upload, visualization

### Phase 3: Frontend Migration
- Existing static SPA is served by the Go gateway
- Future: Nuxt 3 frontend with SSR, replacing the static SPA

### Phase 4: Cleanup
- Remove legacy `web` service from docker-compose
- Remove `src/ollqd/web/` directory
- Simplify pyproject.toml (remove `web` optional dependency group)

---

*Generated for the Ollqd project. For questions or contributions, refer to the source code and proto definitions.*

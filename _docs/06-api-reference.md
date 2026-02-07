# API Reference

## 1. REST API Endpoints

Base URL: `http://localhost:8000`

---

### 1.1 System (`/api/system`)

#### `GET /api/system/health`

Health check for all infrastructure services.

**Response** `200`:
```json
{
  "ollama": "ok",
  "qdrant": "ok",
  "ollama_url": "http://localhost:11434",
  "qdrant_url": "http://localhost:6333"
}
```

Values for `ollama`/`qdrant`: `"ok"` or `"down"`.

#### `GET /api/system/config`

Current server configuration.

**Response** `200`:
```json
{
  "ollama": {
    "url": "http://localhost:11434",
    "chat_model": "qwen2.5:14b",
    "embed_model": "qwen3-embedding:0.6b"
  },
  "qdrant": {
    "url": "http://localhost:6333",
    "default_collection": "codebase"
  },
  "chunking": {
    "chunk_size": 512,
    "chunk_overlap": 64,
    "max_file_size_kb": 512
  }
}
```

---

### 1.2 Qdrant Collections (`/api/qdrant`)

#### `GET /api/qdrant/collections`

List all collections with metadata.

**Response** `200`:
```json
{
  "collections": [
    {
      "name": "codebase",
      "points_count": 1842,
      "status": "green",
      "config": {
        "size": 1024,
        "distance": "Cosine"
      }
    }
  ]
}
```

#### `POST /api/qdrant/collections`

Create a new collection.

**Body** (`CreateCollectionRequest`):
```json
{
  "name": "my-project",
  "vector_size": 1024,
  "distance": "Cosine"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `name` | string | yes | 1-255 chars |
| `vector_size` | int | yes | 1-8192 |
| `distance` | string | no | `"Cosine"` (default), `"Euclid"`, `"Dot"` |

**Response** `200`:
```json
{"status": "ok", "name": "my-project"}
```

#### `GET /api/qdrant/collections/{name}`

Get collection details.

**Response** `200`:
```json
{
  "name": "codebase",
  "points_count": 1842,
  "status": "green",
  "config": {"size": 1024, "distance": "Cosine"}
}
```

#### `DELETE /api/qdrant/collections/{name}`

Delete a collection permanently.

**Response** `200`:
```json
{"status": "ok", "deleted": "codebase"}
```

#### `GET /api/qdrant/collections/{name}/points`

Browse points with pagination.

**Query Parameters**:
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 20 | Points per page |
| `offset` | string | null | Pagination cursor |

**Response** `200`:
```json
{
  "points": [
    {
      "id": "a1b2c3d4",
      "payload": {
        "file_path": "src/auth.py",
        "language": "python",
        "content": "def authenticate()..."
      }
    }
  ],
  "next_offset": "abc123"
}
```

#### `GET /api/qdrant/collections/{name}/points/{point_id}`

Get a single point by ID.

#### `GET /api/qdrant/collections/{name}/count`

**Response** `200`:
```json
{"collection": "codebase", "count": 1842}
```

#### `POST /api/qdrant/collections/{name}/search`

Semantic search within a collection.

**Body** (`SearchRequest`):
```json
{
  "query": "authentication middleware",
  "top_k": 10,
  "language": "python",
  "file_path": null
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `query` | string | yes | min 1 char |
| `top_k` | int | no | 1-100, default 5 |
| `language` | string | no | Filter by language (e.g., `"python"`, `"image"`) |
| `file_path` | string | no | Filter by exact file path |

**Response** `200`:
```json
{
  "results": [
    {
      "id": "a1b2c3d4",
      "score": 0.92,
      "file_path": "src/auth.py",
      "language": "python",
      "lines": "12-45",
      "content": "def authenticate()..."
    },
    {
      "score": 0.85,
      "file_path": "login.png",
      "language": "image",
      "lines": "0-0",
      "content": "Login form screenshot...",
      "abs_path": "/full/path/login.png",
      "caption": "Login form screenshot...",
      "image_type": ".png",
      "width": 1920,
      "height": 1080
    }
  ]
}
```

---

### 1.3 Ollama Models (`/api/ollama`)

#### `GET /api/ollama/models`

List all local models.

**Response** `200`:
```json
{
  "models": [
    {
      "name": "qwen2.5:14b",
      "size": 9123456789,
      "details": {
        "family": "qwen2",
        "parameter_size": "14B",
        "quantization_level": "Q4_K_M"
      }
    }
  ]
}
```

#### `POST /api/ollama/models/show`

**Body**: `{"name": "qwen2.5:14b"}`

**Response**: Full model details (parameters, template, license, etc.)

#### `POST /api/ollama/models/pull`

Pull a model with SSE streaming progress.

**Body**: `{"name": "llava:7b"}`

**Response**: `text/event-stream`
```
data: {"status": "pulling manifest"}
data: {"status": "pulling f5...", "completed": 1024000, "total": 4096000}
data: {"status": "pulling f5...", "completed": 4096000, "total": 4096000}
data: {"status": "success"}
data: [DONE]
```

#### `POST /api/ollama/models/copy`

**Body**: `{"source": "qwen2.5:14b", "destination": "my-qwen"}`

#### `DELETE /api/ollama/models/{name:path}`

Delete a model. Path parameter supports names with colons (e.g., `llava:7b`).

#### `GET /api/ollama/ps`

List currently running (loaded) models.

**Response** `200`:
```json
{
  "models": [
    {"name": "qwen2.5:14b", "model": "qwen2.5:14b", "size": 5000000000}
  ]
}
```

#### `POST /api/ollama/chat`

Streaming chat with SSE.

**Body** (`ChatRequest`):
```json
{
  "model": "qwen2.5:14b",
  "messages": [{"role": "user", "content": "Hello"}],
  "temperature": 0.7
}
```

**Response**: `text/event-stream`
```
data: {"content": "Hello"}
data: {"content": "! How"}
data: {"content": " can I help?"}
data: [DONE]
```

#### `POST /api/ollama/generate`

Streaming text generation with SSE.

**Body** (`GenerateRequest`):
```json
{
  "model": "qwen2.5:14b",
  "prompt": "Write a function...",
  "temperature": 0.7
}
```

#### `POST /api/ollama/embed`

Generate embeddings.

**Body** (`EmbedRequest`):
```json
{
  "model": "qwen3-embedding:0.6b",
  "input": "authentication middleware"
}
```

**Response** `200`:
```json
{
  "embeddings": [[0.12, -0.4, 0.87, ...]]
}
```

#### `GET /api/ollama/version`

**Response** `200`:
```json
{"version": "0.5.4"}
```

---

### 1.4 RAG (`/api/rag`)

#### `POST /api/rag/search`

Global semantic search (default collection).

**Body** (`SearchRequest`): same as collection search.

#### `POST /api/rag/search/{collection}`

Semantic search in a specific collection.

#### `POST /api/rag/index/codebase`

Start background codebase indexing.

**Body** (`IndexCodebaseRequest`):
```json
{
  "root_path": "/Users/me/project",
  "collection": "codebase",
  "incremental": true,
  "chunk_size": 512,
  "chunk_overlap": 64,
  "extra_skip_dirs": ["vendor"]
}
```

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `root_path` | string | yes | -- | min 1 char |
| `collection` | string | no | `"codebase"` | |
| `incremental` | bool | no | `true` | |
| `chunk_size` | int | no | `512` | 32-4096 |
| `chunk_overlap` | int | no | `64` | 0-512 |
| `extra_skip_dirs` | string[] | no | `[]` | |

**Response** `200`:
```json
{"task_id": "abc123def456", "status": "started"}
```

#### `POST /api/rag/index/documents`

Start background document indexing.

**Body** (`IndexDocumentsRequest`):
```json
{
  "paths": ["/Users/me/docs/"],
  "collection": "documents",
  "chunk_size": 512,
  "chunk_overlap": 64,
  "source_tag": "docs"
}
```

#### `POST /api/rag/index/images`

Start background image indexing with vision captioning.

**Body** (`IndexImagesRequest`):
```json
{
  "root_path": "/Users/me/screenshots",
  "collection": "images",
  "vision_model": "llava:7b",
  "caption_prompt": "Describe this image in detail...",
  "incremental": true,
  "max_image_size_kb": 10240,
  "extra_skip_dirs": []
}
```

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `root_path` | string | yes | -- | min 1 char |
| `collection` | string | no | `"images"` | |
| `vision_model` | string | no | server config | |
| `caption_prompt` | string | no | server config | |
| `incremental` | bool | no | `true` | |
| `max_image_size_kb` | int | no | `10240` | 64-102400 |
| `extra_skip_dirs` | string[] | no | `[]` | |

**Response** `200`:
```json
{"task_id": "abc123def456", "status": "started"}
```

#### `GET /api/rag/image`

Serve an image file for thumbnail display.

**Query Parameters**:
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Absolute path to image file |

**Response**: Image file (`image/png`, `image/jpeg`, etc.)

**Error Responses**:
- `400`: Not a supported image type (extension check)
- `404`: Image not found

#### `GET /api/rag/tasks`

List all background tasks.

**Response** `200`:
```json
[
  {
    "id": "abc123def456",
    "type": "index_codebase",
    "status": "completed",
    "progress": 1.0,
    "result": {
      "files": 42,
      "chunks": 186,
      "collection": "codebase"
    },
    "error": null,
    "created_at": "2026-02-06T12:00:00",
    "completed_at": "2026-02-06T12:01:30"
  }
]
```

Task result varies by type:

| Type | Result Fields |
|------|--------------|
| `index_codebase` | `files`, `chunks`, `collection` |
| `index_documents` | `files`, `chunks`, `collection` |
| `index_images` | `images_found`, `images_indexed`, `images_failed`, `collection` |

#### `GET /api/rag/tasks/{task_id}`

Get a single task by ID.

---

## 2. WebSocket API

### `WS /api/rag/ws/chat`

RAG chat with streaming responses.

#### Client -> Server

```json
{
  "message": "How does authentication work?",
  "collection": "codebase",
  "model": "qwen2.5:14b"
}
```

#### Server -> Client

| Type | Payload | Description |
|------|---------|-------------|
| `chunk` | `{"type": "chunk", "content": "token"}` | Streaming token |
| `sources` | `{"type": "sources", "results": [...]}` | Search results used as context |
| `done` | `{"type": "done"}` | Stream complete |
| `error` | `{"type": "error", "content": "msg"}` | Error occurred |

Source result objects contain the same fields as search results (including `abs_path`, `caption`, `image_type` for image sources).

---

## 3. MCP Tool Schemas

Transport: stdio (JSON-RPC 2.0)

### `index_codebase`

```json
{
  "name": "index_codebase",
  "description": "Walk a codebase directory, chunk source files, generate embeddings, and store in Qdrant",
  "inputSchema": {
    "type": "object",
    "properties": {
      "root_path": {"type": "string", "description": "Absolute path to codebase root"},
      "collection": {"type": "string", "default": "codebase"},
      "incremental": {"type": "boolean", "default": true},
      "chunk_size": {"type": "integer", "default": 512},
      "chunk_overlap": {"type": "integer", "default": 64},
      "extra_skip_dirs": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["root_path"]
  }
}
```

**Returns**: `{status, files, chunks, failed, collection, elapsed_seconds}`

### `index_documents`

```json
{
  "name": "index_documents",
  "inputSchema": {
    "type": "object",
    "properties": {
      "paths": {"type": "array", "items": {"type": "string"}},
      "collection": {"type": "string", "default": "documents"},
      "chunk_size": {"type": "integer", "default": 512},
      "chunk_overlap": {"type": "integer", "default": 64},
      "source_tag": {"type": "string", "default": "docs"}
    },
    "required": ["paths"]
  }
}
```

**Returns**: `{status, files, chunks, collection, elapsed_seconds}`

### `semantic_search`

```json
{
  "name": "semantic_search",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "collection": {"type": "string", "default": "codebase"},
      "top_k": {"type": "integer", "default": 5},
      "language": {"type": "string", "nullable": true},
      "file_path": {"type": "string", "nullable": true}
    },
    "required": ["query"]
  }
}
```

**Returns**: `{status, query, collection, results: [{score, file_path, language, lines, chunk, content}]}`

### `list_collections`

No parameters.

**Returns**: `{status, collections: [{name, points}]}`

### `delete_collection`

```json
{
  "name": "delete_collection",
  "inputSchema": {
    "type": "object",
    "properties": {
      "collection": {"type": "string"},
      "confirm": {"type": "boolean"}
    },
    "required": ["collection", "confirm"]
  }
}
```

**Returns**: `{status, deleted}` or `{status: "error", message: "..."}`

---

## 4. Pydantic Models

### Request Models

```python
class CreateCollectionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    vector_size: int = Field(..., gt=0, le=8192)
    distance: Literal["Cosine", "Euclid", "Dot"] = "Cosine"

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=100)
    language: Optional[str] = None
    file_path: Optional[str] = None

class PullModelRequest(BaseModel):
    name: str = Field(..., min_length=1)

class ShowModelRequest(BaseModel):
    name: str = Field(..., min_length=1)

class CopyModelRequest(BaseModel):
    source: str = Field(..., min_length=1)
    destination: str = Field(..., min_length=1)

class ChatRequest(BaseModel):
    model: str = Field(..., min_length=1)
    messages: list[dict]
    temperature: float = Field(0.7, ge=0.0, le=2.0)

class GenerateRequest(BaseModel):
    model: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    temperature: float = Field(0.7, ge=0.0, le=2.0)

class EmbedRequest(BaseModel):
    model: str = Field(..., min_length=1)
    input: str | list[str]

class IndexCodebaseRequest(BaseModel):
    root_path: str = Field(..., min_length=1)
    collection: str = "codebase"
    incremental: bool = True
    chunk_size: int = Field(512, ge=32, le=4096)
    chunk_overlap: int = Field(64, ge=0, le=512)
    extra_skip_dirs: list[str] = Field(default_factory=list)

class IndexImagesRequest(BaseModel):
    root_path: str = Field(..., min_length=1)
    collection: str = "images"
    vision_model: Optional[str] = None
    caption_prompt: Optional[str] = None
    incremental: bool = True
    max_image_size_kb: int = Field(10240, ge=64, le=102400)
    extra_skip_dirs: list[str] = Field(default_factory=list)

class IndexDocumentsRequest(BaseModel):
    paths: list[str] = Field(..., min_length=1)
    collection: str = "documents"
    chunk_size: int = Field(512, ge=32, le=4096)
    chunk_overlap: int = Field(64, ge=0, le=512)
    source_tag: str = "docs"
```

---

## 5. Error Responses

### HTTP Errors

| Code | Meaning | Example |
|------|---------|---------|
| `400` | Bad request / validation error | Invalid image extension, missing required field |
| `404` | Not found | Task not found, image file not found |
| `422` | Validation error (Pydantic) | Field constraints violated |
| `500` | Internal server error | Qdrant/Ollama connection failure |

### Error Response Format

```json
{
  "detail": "Error description here"
}
```

### WebSocket Error

```json
{
  "type": "error",
  "content": "Error description here"
}
```

---

## 6. Entry Points

| Command | Module | Description |
|---------|--------|-------------|
| `ollqd-web` | `ollqd.web.app:main` | FastAPI server on 0.0.0.0:8000 |
| `ollqd-server` | `ollqd.server.main:main` | MCP server over stdio |
| `ollqd-chat` | `ollqd.client.main:main` | CLI RAG client |
| `codebase-index` | `codebase_indexer:main` | Legacy standalone indexer |
| `codebase-search` | `codebase_search:main` | Legacy standalone search |

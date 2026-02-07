# Data Flows

## 1. Codebase Indexing Pipeline

### Overview

```
Filesystem -> Discovery -> Incremental Check -> Chunking -> Embedding -> Qdrant
```

### Step-by-Step

#### 1.1 Discovery (`discovery.py:discover_files()`)

```
Input:  root_path = "/Users/me/project"
        max_file_size_kb = 512
        extra_skip_dirs = {"vendor"}

Process:
  os.walk(root) recursively
  |-- Skip directories: .git, node_modules, __pycache__, .venv, dist, build, ...
  |-- Skip files: package-lock.json, yarn.lock, go.sum, Cargo.lock, ...
  |-- Match extensions: 40+ language map (.py -> "python", .go -> "go", ...)
  |-- Check size: stat.st_size <= 512KB
  |-- Hash content: SHA-256(file_bytes)

Output: FileInfo[]
  [
    FileInfo(path="src/auth.py", abs_path="/Users/me/project/src/auth.py",
             language="python", size_bytes=2048, content_hash="a1b2c3...")
  ]
```

#### 1.2 Incremental Check

```
If incremental=True:
  1. QdrantManager.get_indexed_hashes() -> {file_path: content_hash}
     (scrolls ALL points, extracts file_path + content_hash)
  2. Filter: keep files where indexed_hash != current_hash
  3. Delete stale: QdrantManager.delete_file_points(path)
     (filter by file_path keyword index)
  4. If no changes -> return "All up to date"
```

#### 1.3 Chunking (`chunking.py:chunk_file()`)

```
Input: FileInfo + chunk_size=512 + chunk_overlap=64

Process:
  1. Read file content as text
  2. Split into lines
  3. For each line:
     - Track character budget (chunk_size * 4 chars per token estimate)
     - Detect boundaries: _is_boundary_line(line, language)
       Python: "def ", "class ", "async def ", "@"
       Go: "func ", "type "
       JS/TS: "function ", "export ", "class ", "const ", "describe(", "it("
       Rust: "fn ", "pub fn ", "impl ", "struct ", "enum ", "mod ", "trait "
       etc.
     - On boundary + budget exceeded: flush chunk with overlap
     - On 1.5x budget exceeded (no boundary): force flush
  4. Set total_chunks on all Chunk objects

Output: Chunk[]
  [
    Chunk(file_path="src/auth.py", language="python",
          chunk_index=0, total_chunks=3,
          start_line=1, end_line=45,
          content="def authenticate(...):\n    ...",
          content_hash="d4e5f6...")
  ]

Point ID: md5("src/auth.py::chunk_0") -> "a1b2c3d4e5f6..."
```

#### 1.4 Embedding (`embedder.py:embed_chunks()`)

```
Input: Chunk[] (batched in groups of 32)

Process:
  1. Prefix each chunk with metadata:
     "File: src/auth.py | Language: python | Lines 1-45\n\n{content}"
  2. POST /api/embed to Ollama:
     {"model": "qwen3-embedding:0.6b", "input": [text1, text2, ...]}
  3. Response: {"embeddings": [[0.12, -0.4, ...], ...]}

Output: float[1024][] (one vector per chunk)
```

#### 1.5 Storage (`vectorstore.py:upsert_batch()`)

```
Input: PointStruct[] (id, vector, payload)

Process:
  1. ensure_collection():
     - Create if missing (vector_size=1024, distance=Cosine)
     - Create payload indexes: file_path, language, content_hash (Keyword)
  2. upsert_batch(points) -> Qdrant REST API

Payload stored per point:
  {
    "file_path": "src/auth.py",
    "language": "python",
    "chunk_index": 0,
    "total_chunks": 3,
    "start_line": 1,
    "end_line": 45,
    "content": "def authenticate(...):\n    ...",
    "content_hash": "d4e5f6..."
  }
```

---

## 2. Document Indexing Pipeline

Similar to codebase but with different discovery:

```
Input: paths = ["/Users/me/docs/"]

Process:
  1. Recursive glob: *.md, *.txt, *.rst, *.html files
  2. chunk_document(): paragraph/heading-based splitting
     - Markdown: split at #/##/### headings
     - Text: split at double-newline paragraphs
  3. Embed with source_tag in payload
  4. Upsert to "documents" collection

Payload includes:
  { ..., "source_tag": "docs" }
```

---

## 3. Image RAG Pipeline

### Overview

```
Filesystem -> Discovery -> Incremental -> Base64 -> Vision Caption -> Embed Caption -> Qdrant
```

### Step-by-Step

#### 3.1 Image Discovery (`discovery.py:discover_images()`)

```
Input:  root_path = "/Users/me/screenshots"
        max_image_size_kb = 10240  (10MB)

Process:
  os.walk(root) recursively
  |-- Skip directories: same SKIP_DIRS set
  |-- Match extensions: .png, .jpg, .jpeg, .gif, .webp, .bmp, .tiff
  |-- Check size: <= 10MB
  |-- Hash content: SHA-256(image_bytes)
  |-- Optional: Pillow Image.open() for width/height

Output: ImageFileInfo[]
  [
    ImageFileInfo(path="dashboard.png", abs_path="/full/path/dashboard.png",
                  extension=".png", size_bytes=245760,
                  content_hash="f1e2d3...", width=1920, height=1080)
  ]
```

#### 3.2 Incremental Check

Same as codebase — compare content_hash vs indexed hashes in Qdrant.

#### 3.3 Vision Captioning

```
Input: ImageFileInfo

Process:
  1. Read image bytes from abs_path
  2. Base64 encode: base64.b64encode(bytes).decode("utf-8")
  3. POST to Ollama /api/chat:
     {
       "model": "llava:7b",
       "messages": [{
         "role": "user",
         "content": "Describe this image in detail...",
         "images": ["base64_data..."]
       }],
       "stream": false
     }
  4. Timeout: 180 seconds (vision models are slow)

Output: caption string
  "This image shows a web dashboard with a dark sidebar navigation..."
```

#### 3.4 Caption Embedding

```
Input: caption text + image path

Process:
  1. Build embed text: "Image: dashboard.png\n\nCaption: This image shows..."
  2. POST /api/embed: same as text embedding
  3. Point ID: md5("image::dashboard.png")

Output: float[1024] vector
```

#### 3.5 Image Point Storage

```
Payload stored per image point:
  {
    "file_path": "dashboard.png",
    "abs_path": "/full/path/dashboard.png",
    "language": "image",           <-- discriminator
    "image_type": ".png",
    "caption": "This image shows...",
    "content": "This image shows...",  (same as caption for search display)
    "content_hash": "f1e2d3...",
    "chunk_index": 0,
    "total_chunks": 1,
    "start_line": 0,
    "end_line": 0,
    "width": 1920,                 (optional, requires Pillow)
    "height": 1080
  }
```

---

## 4. Search Pipeline

### 4.1 Semantic Search (REST)

```
POST /api/qdrant/collections/{name}/search
Body: {"query": "auth middleware", "top_k": 10}

Flow:
  1. OllamaEmbedder.embed_query("auth middleware") -> float[1024]
  2. QdrantManager.search(vector, top_k=10, language=None, file_filter=None)
  3. Qdrant query_points with cosine similarity
  4. Return scored results with payload

Response:
  {
    "results": [
      {
        "score": 0.92,
        "file_path": "src/auth.py",
        "language": "python",
        "lines": "12-45",
        "chunk": "1/3",
        "content": "def authenticate(...)..."
      },
      {
        "score": 0.85,
        "file_path": "screenshots/login.png",
        "language": "image",
        "lines": "0-0",
        "content": "This image shows the login form...",
        "abs_path": "/full/path/login.png",
        "caption": "This image shows the login form...",
        "image_type": ".png"
      }
    ]
  }
```

### 4.2 Filtered Search

Qdrant payload indexes enable efficient filtering:

```
# Filter by language
{"query": "error handling", "language": "python"}
-> FieldCondition(key="language", match=MatchValue(value="python"))

# Filter by file path
{"query": "config", "file_path": "src/config.py"}
-> FieldCondition(key="file_path", match=MatchValue(value="src/config.py"))

# Image-only search
{"query": "dashboard screenshot", "language": "image"}
```

---

## 5. WebSocket RAG Chat Flow

```
Browser                    FastAPI                   Ollama            Qdrant
   |                          |                        |                 |
   |-- WS connect ----------->|                        |                 |
   |<- accept ---------------|                        |                 |
   |                          |                        |                 |
   |-- {message, collection,  |                        |                 |
   |    model} -------------->|                        |                 |
   |                          |                        |                 |
   |                          |-- embed_query() ------>|                 |
   |                          |<- vector[1024] --------|                 |
   |                          |                        |                 |
   |                          |-- query_points() ----------------------->|
   |                          |<- search results ------------------------|
   |                          |                        |                 |
   |                          |  Build context:        |                 |
   |                          |  Code: [file L1-20]    |                 |
   |                          |  Image: [Image: path]  |                 |
   |                          |         Caption: ...   |                 |
   |                          |                        |                 |
   |                          |-- POST /api/chat ----->|                 |
   |                          |    (stream=True)       |                 |
   |                          |                        |                 |
   |<- {type:"chunk"} -------|<- token ----------------|                 |
   |<- {type:"chunk"} -------|<- token ----------------|                 |
   |<- {type:"chunk"} -------|<- token ----------------|                 |
   |   ...                    |   ...                  |                 |
   |                          |                        |                 |
   |<- {type:"sources"} -----|                        |                 |
   |<- {type:"done"} --------|                        |                 |
```

### Message Types

| Type | Direction | Payload |
|------|-----------|---------|
| (request) | Client -> Server | `{message, collection, model}` |
| `chunk` | Server -> Client | `{type: "chunk", content: "token"}` |
| `sources` | Server -> Client | `{type: "sources", results: [{score, file_path, ...}]}` |
| `done` | Server -> Client | `{type: "done"}` |
| `error` | Server -> Client | `{type: "error", content: "message"}` |

---

## 6. Background Task Flow

```
POST /api/rag/index/codebase
  |
  v
TaskManager.create("index_codebase") -> task_id
  |
  v
asyncio.run_in_executor(None, _run_index_codebase, task_id, req)
  |  (returns immediately to client)
  v
Response: {"task_id": "abc123", "status": "started"}

Background thread:
  1. TaskManager.start(task_id)          # status: running
  2. discover_files(root)
  3. Incremental check
  4. For each batch:
     a. chunk + embed + upsert
     b. TaskManager.update_progress(task_id, progress)
  5. TaskManager.complete(task_id, result)  # status: completed
     OR
     TaskManager.fail(task_id, error)       # status: failed

Frontend polling:
  Every 1 second: GET /api/rag/tasks/{task_id}
  Updates progress bar + status badge
  Stops when status is "completed" or "failed"
```

---

## 7. Vector Lifecycle

```
CREATE:
  index_codebase/images/documents -> discover -> chunk/caption -> embed -> upsert

READ:
  semantic_search -> embed query -> query_points -> return scored hits
  browse (scroll) -> paginated point listing with payload

UPDATE (incremental re-index):
  1. Compare SHA-256 hashes
  2. Delete stale points (delete by file_path filter)
  3. Re-create with new content + new vectors

DELETE:
  delete_collection -> drops entire collection
  (no per-point delete from WebUI, only via incremental re-index)
```

---

## 8. Data Sizes & Estimates

| Item | Typical Size |
|------|-------------|
| Embedding vector (1024-dim float32) | 4 KB |
| Payload per code chunk | ~2-4 KB |
| Payload per image point | ~1-3 KB (caption text) |
| 1000 code files (avg 3 chunks each) | ~3000 vectors, ~20 MB in Qdrant |
| 100 images with captions | 100 vectors, ~1 MB in Qdrant |
| Embedding latency (batch of 32) | ~200-500ms (local Ollama) |
| Vision captioning per image | ~3-15 seconds (llava:7b) |
| WebSocket chat latency (first token) | ~500ms-2s (depends on model) |

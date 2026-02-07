# Features

## 1. Feature Inventory

### Core Features

| # | Feature | Status | Interface | Description |
|---|---------|--------|-----------|-------------|
| F01 | Codebase Indexing | Done | WebUI, MCP, CLI | Walk directory, chunk code files, embed, store in Qdrant |
| F02 | Document Indexing | Done | WebUI, MCP | Index markdown/text/html documents |
| F03 | Image Indexing | Done | WebUI | Vision model captioning + text embedding for images |
| F04 | Semantic Search | Done | WebUI, MCP, CLI | Natural language query -> cosine similarity results |
| F05 | Filtered Search | Done | WebUI, MCP | Filter by language, file path |
| F06 | Incremental Indexing | Done | All | SHA-256 hash comparison, skip unchanged files |
| F07 | RAG Chat (WebSocket) | Done | WebUI | Streaming chat with code/image context |
| F08 | RAG Chat (Tool-calling) | Done | CLI, MCP | Multi-round tool-calling loop with Ollama |
| F09 | Collection Management | Done | WebUI, MCP | Create, delete, browse, search collections |
| F10 | Model Management | Done | WebUI | List, pull, delete, show details, running status |
| F11 | Health Monitoring | Done | WebUI | Real-time Ollama + Qdrant status indicators |
| F12 | Background Tasks | Done | WebUI | Non-blocking indexing with progress tracking |
| F13 | Image Thumbnails | Done | WebUI | Inline image previews in browse, search, and chat |
| F14 | Model Pull Streaming | Done | WebUI | SSE progress bar for model downloads |
| F15 | Point Browsing | Done | WebUI | Paginated scroll through collection points |

### Interface Features

| # | Feature | Interface | Description |
|---|---------|-----------|-------------|
| F16 | Dashboard | WebUI | Overview cards: collections, vectors, models |
| F17 | Sidebar Navigation | WebUI | 5-tab navigation with Font Awesome icons |
| F18 | Interactive REPL | CLI | Multi-turn conversation with `:model` and `:quit` commands |
| F19 | MCP Tool Discovery | CLI, MCP | Automatic tool listing via MCP ListTools |
| F20 | Markdown Rendering | WebUI | Code blocks, inline code, bold, italic in chat |
| F21 | Clear Chat | WebUI | Reset conversation and WebSocket connection |
| F22 | Tabbed Indexing | WebUI | Codebase and Images tabs in indexing form |

---

## 2. Capability Matrix

| Capability | WebUI | CLI (ollqd-chat) | MCP Server | Legacy Scripts |
|-----------|-------|-------------------|------------|----------------|
| Index codebase | POST /api/rag/index/codebase | Via MCP tool | index_codebase | codebase_indexer.py |
| Index documents | POST /api/rag/index/documents | Via MCP tool | index_documents | -- |
| Index images | POST /api/rag/index/images | -- | -- | -- |
| Semantic search | POST /api/qdrant/.../search | Via MCP tool | semantic_search | codebase_search.py |
| RAG chat | WebSocket /api/rag/ws/chat | Interactive REPL | -- | -- |
| Collection CRUD | REST /api/qdrant/* | Via MCP tool | list/delete | -- |
| Model management | REST /api/ollama/* | -- | -- | -- |
| Health check | GET /api/system/health | -- | -- | -- |
| Image serving | GET /api/rag/image | -- | -- | -- |
| Task tracking | GET /api/rag/tasks | -- | -- | -- |
| Vision captioning | During image indexing | -- | -- | -- |

---

## 3. Feature-to-Component Mapping

| Feature | Files Involved |
|---------|---------------|
| F01: Codebase Indexing | `discovery.py`, `chunking.py`, `embedder.py`, `vectorstore.py`, `web/routers/rag.py` |
| F02: Document Indexing | `chunking.py:chunk_document()`, `web/routers/rag.py:index_documents()` |
| F03: Image Indexing | `discovery.py:discover_images()`, `web/routers/rag.py:_run_index_images()`, `config.py:ImageConfig` |
| F04: Semantic Search | `embedder.py:embed_query()`, `vectorstore.py:search()`, `web/routers/qdrant.py` |
| F05: Filtered Search | `vectorstore.py:search(language=, file_filter=)`, Qdrant payload indexes |
| F06: Incremental | `vectorstore.py:get_indexed_hashes()`, `vectorstore.py:delete_file_points()` |
| F07: RAG Chat (WS) | `web/routers/rag.py:ws_chat()`, `web/services/ollama_service.py:chat_stream()` |
| F08: RAG Chat (MCP) | `client/rag_loop.py`, `client/mcp_bridge.py`, `client/ollama_agent.py` |
| F09: Collection Mgmt | `web/routers/qdrant.py`, `vectorstore.py`, `server/main.py` |
| F10: Model Mgmt | `web/routers/ollama.py`, `web/services/ollama_service.py` |
| F11: Health | `web/routers/system.py`, `web/services/ollama_service.py:is_healthy()` |
| F12: Background Tasks | `web/services/task_manager.py`, `web/routers/rag.py` (run_in_executor) |
| F13: Image Thumbnails | `web/routers/rag.py:serve_image()`, `vectorstore.py` (abs_path in search), `static/index.html` |
| F14: Model Pull SSE | `web/routers/ollama.py:pull_model()`, `static/app.js:pullModel()` |
| F15: Point Browsing | `web/routers/qdrant.py:browse_points()`, `static/app.js:browseCollection()` |

---

## 4. Supported Languages (40+)

| Language | Extensions | Boundary Patterns |
|----------|------------|-------------------|
| Python | `.py`, `.pyi` | `def `, `class `, `async def `, `@` |
| Go | `.go` | `func `, `type ` |
| JavaScript | `.js`, `.mjs`, `.cjs` | `function `, `export `, `class `, `const `, `describe(`, `it(`, `test(` |
| TypeScript | `.ts`, `.tsx` | Same as JavaScript |
| JSX | `.jsx` | Same as JavaScript |
| Rust | `.rs` | `fn `, `pub fn `, `impl `, `struct `, `enum `, `mod `, `trait ` |
| Java | `.java` | `public `, `private `, `protected `, `class `, `interface ` |
| Kotlin | `.kt` | `fun `, `class `, `data class `, `object `, `override ` |
| Scala | `.scala` | `def `, `class `, `object `, `trait ` |
| C | `.c`, `.h` | Function signatures with `(`, `)`, `{` |
| C++ | `.cpp`, `.hpp`, `.cc` | Same as C |
| C# | `.cs` | Same as Java |
| Ruby | `.rb` | `def `, `class `, `module ` |
| PHP | `.php` | `function `, `class ` |
| Swift | `.swift` | `func `, `class `, `struct `, `enum `, `protocol ` |
| Lua | `.lua` | `function `, `local function ` |
| Shell | `.sh`, `.bash`, `.zsh` | `function `, lines ending with `()` |
| SQL | `.sql` | `CREATE`, `ALTER`, `SELECT`, `INSERT` |
| R | `.r`, `.R` | `function(` |
| HTML | `.html` | Tag-based (less relevant for chunking) |
| CSS | `.css` | Selector blocks |
| SCSS | `.scss` | Same as CSS |
| YAML | `.yml`, `.yaml` | Top-level keys |
| TOML | `.toml` | `[section]` headers |
| JSON | `.json` | Top-level keys |
| Markdown | `.md` | `#`, `##`, `###` headings |
| reStructuredText | `.rst` | Section underlines |
| Terraform | `.tf` | `resource `, `data `, `variable `, `output ` |
| HCL | `.hcl` | Same as Terraform |
| Dockerfile | `Dockerfile` | `FROM`, `RUN`, `COPY`, `CMD` |
| Protobuf | `.proto` | `message `, `service `, `enum ` |
| GraphQL | `.graphql`, `.gql` | `type `, `query `, `mutation `, `subscription ` |

### Supported Image Formats

| Format | Extension |
|--------|-----------|
| PNG | `.png` |
| JPEG | `.jpg`, `.jpeg` |
| GIF | `.gif` |
| WebP | `.webp` |
| BMP | `.bmp` |
| TIFF | `.tiff` |

---

## 5. Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_CHAT_MODEL` | `qwen2.5:14b` | Default chat model |
| `OLLAMA_EMBED_MODEL` | `qwen3-embedding:0.6b` | Embedding model |
| `OLLAMA_VISION_MODEL` | `llava:7b` | Vision captioning model |
| `OLLAMA_TIMEOUT_S` | `120` | Request timeout (seconds) |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant REST URL |
| `QDRANT_COLLECTION` | `codebase` | Default collection name |
| `CHUNK_SIZE` | `512` | Tokens per chunk |
| `CHUNK_OVERLAP` | `64` | Overlap tokens |
| `MAX_IMAGE_SIZE_KB` | `10240` | Max image size (KB) |
| `MAX_TOOL_ROUNDS` | `6` | Max RAG loop rounds |

### Embedding Model Comparison

| Model | Dimensions | Speed | Code Quality | Notes |
|-------|-----------|-------|-------------|-------|
| qwen3-embedding:0.6b | 1024 | Fast | Good | Default, multilingual |
| nomic-embed-text | 768 | Fast | Good | Balanced |
| mxbai-embed-large | 1024 | Moderate | Excellent | Best for code |
| all-minilm | 384 | Very fast | Fair | Low memory |
| snowflake-arctic-embed | 1024 | Moderate | Excellent | Code-optimized |

### Vision Model Options

| Model | Speed | Caption Quality | VRAM |
|-------|-------|----------------|------|
| llava:7b | Moderate | Good | ~5GB |
| llava:13b | Slow | Better | ~8GB |
| llava:34b | Very slow | Best | ~20GB |
| bakllava:7b | Moderate | Good | ~5GB |
| moondream:1.8b | Fast | Fair | ~2GB |

### Chunk Size Guidelines

| Content Type | Recommended Size | Overlap | Strategy |
|-------------|-----------------|---------|----------|
| Code (40+ langs) | 512 | 64 | Function/class boundaries |
| Markdown docs | 1024 | 128 | Heading hierarchy |
| Plain text | 1024 | 128 | Paragraph groups |
| Images | N/A | N/A | One vector per image (caption) |

---

## 6. Skip Lists

### Skipped Directories

```
.git, .svn, .hg, node_modules, __pycache__, .mypy_cache, .pytest_cache,
.tox, .venv, venv, env, .env, dist, build, target, out, bin, obj,
.next, .nuxt, .output, vendor, third_party, .idea, .vscode,
coverage, .coverage
```

### Skipped Files

```
package-lock.json, yarn.lock, pnpm-lock.yaml, go.sum, Cargo.lock,
poetry.lock, uv.lock, Pipfile.lock, composer.lock, Gemfile.lock
```

---

## 7. Security Features

| Feature | Mechanism | Scope |
|---------|-----------|-------|
| Image serving validation | Extension allowlist + file existence check | `GET /api/rag/image` |
| File size limits | `max_file_size_kb=512` (code), `max_image_size_kb=10240` (images) | Discovery |
| Directory skipping | `SKIP_DIRS` set (26 patterns) | Discovery |
| Input validation | Pydantic models with `Field(min_length, ge, le)` | All POST endpoints |
| Collection delete guard | `confirm=true` required (MCP), `window.confirm()` (WebUI) | Delete operations |
| No secrets in index | Lock files and env files excluded | Discovery |
| Local-only by default | All services bound to localhost | Deployment |

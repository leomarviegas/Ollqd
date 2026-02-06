# Ollqd — MCP Client-Server RAG System

Local-first RAG system that indexes codebases and documents into [Qdrant](https://qdrant.tech/) using [Ollama](https://ollama.com/) embeddings. Exposes everything through [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) so AI assistants can search your code via tool-calling.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  User Interface                                                  │
│  ┌─────────────┐  ┌─────────────────────────────────────────┐   │
│  │ ollqd-chat   │  │ Claude Desktop / any MCP host           │   │
│  │ (CLI / REPL) │  │ (connects to ollqd-server directly)     │   │
│  └──────┬───────┘  └────────────────┬────────────────────────┘   │
└─────────┼──────────────────────────┼────────────────────────────┘
          │ stdio JSON-RPC           │ stdio JSON-RPC
┌─────────▼──────────────────────────▼────────────────────────────┐
│  Ollqd MCP Server (FastMCP)                                     │
│  ┌───────────────┐ ┌─────────────────┐ ┌─────────────────────┐  │
│  │index_codebase │ │index_documents  │ │semantic_search      │  │
│  │index docs     │ │markdown/text/rst│ │embed query → Qdrant │  │
│  └───────┬───────┘ └────────┬────────┘ └──────────┬──────────┘  │
│  ┌───────┴──────┐  ┌───────┴────────┐             │             │
│  │list_collections│ │delete_collection│             │             │
│  └──────────────┘  └────────────────┘             │             │
└─────────┬──────────────────────────────────────────┼────────────┘
          │ /api/embed                               │
┌─────────▼──────────┐                    ┌──────────▼─────────┐
│  Ollama             │                    │  Qdrant             │
│  nomic-embed-text   │                    │  cosine similarity  │
│  + chat models      │                    │  payload indexes    │
└────────────────────┘                    └────────────────────┘
```

### How it works

1. **Discovery** — Walks the codebase, filters by language (40+ extensions), skips lock files / build artifacts / vendor dirs.

2. **Code-aware chunking** — Splits files at natural code boundaries (function defs, class declarations, impl blocks) rather than blindly cutting at token limits. Overlapping windows preserve context.

3. **Embedding** — Sends chunks to Ollama's `/api/embed` in batches. Each chunk is prefixed with file path + language + line range for better semantic grounding.

4. **Storage** — Upserts into Qdrant with full metadata payload. Payload indexes on `file_path`, `language`, and `content_hash` enable filtered search and incremental re-indexing.

5. **RAG loop** — The client sends user queries to Ollama with MCP tools attached. Ollama decides when to call `semantic_search`, gets results from the server, and synthesizes a final answer with code citations.

## Setup

### Prerequisites

- **Ollama** running locally with an embedding model pulled
- **Qdrant** running (Docker recommended)
- **Python 3.10+**

```bash
# Pull the embedding model
ollama pull nomic-embed-text

# Pull a chat model (any that supports tool-calling)
ollama pull qwen2.5:14b

# Start Qdrant (and optionally Ollama via Docker)
docker compose up -d
```

### Install

```bash
# With uv (recommended)
uv venv && source .venv/bin/activate
uv pip install -e ".[client,dev]"

# Or with pip
pip install -e ".[client,dev]"
```

## Usage

### Start the MCP server (standalone)

```bash
ollqd-server
```

The server communicates over stdio using JSON-RPC (MCP protocol). It's meant to be launched by MCP clients, not used directly.

### Interactive RAG chat

```bash
# Interactive REPL — ask questions about your codebase
ollqd-chat --interactive

# Single query
ollqd-chat "how does the auth middleware work?"

# Use a different chat model
ollqd-chat --interactive --model llama3.1

# Debug mode
ollqd-chat -v "find the database connection setup"
```

REPL commands:
- `:quit` / `:q` — exit
- `:model <name>` — switch chat model on the fly

### Use with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ollqd": {
      "command": "ollqd-server",
      "args": []
    }
  }
}
```

Then in Claude Desktop, ask things like:
- "Index my project at /path/to/codebase"
- "Search for how authentication is implemented"
- "What error handling patterns are used?"
- "List all indexed collections"

## MCP Tools

| Tool | Description |
|------|-------------|
| `index_codebase` | Walk + chunk + embed + upsert code files from a directory |
| `index_documents` | Chunk + embed + upsert document files (markdown, text, rst) |
| `semantic_search` | Embed a natural language query and search Qdrant |
| `list_collections` | List all Qdrant collections with point counts |
| `delete_collection` | Drop a collection (requires `confirm=true`) |

## Configuration

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant REST URL |
| `OLLAMA_CHAT_MODEL` | `qwen2.5:14b` | Chat model for RAG |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `OLLAMA_TIMEOUT_S` | `120` | Request timeout (seconds) |
| `CHUNK_SIZE` | `512` | Approximate tokens per chunk |
| `CHUNK_OVERLAP` | `64` | Overlap tokens between chunks |
| `MAX_TOOL_ROUNDS` | `6` | Max tool-calling rounds per query |

### ollqd.toml

```toml
[ollama]
host = "http://localhost:11434"
chat_model = "qwen2.5:14b"
embed_model = "nomic-embed-text"
timeout = 120

[qdrant]
host = "http://localhost:6333"
default_collection = "codebase"

[indexing]
chunk_size = 512
chunk_overlap = 64
max_file_size_kb = 512

[server]
name = "ollqd-rag-server"
transport = "stdio"

[client]
max_tool_rounds = 6
```

## Project structure

```
src/ollqd/
├── __init__.py
├── config.py          # AppConfig dataclass + env var overrides
├── errors.py          # Exception hierarchy
├── models.py          # FileInfo, Chunk, SearchResult, IndexingStats
├── chunking.py        # Code-aware + document chunking
├── discovery.py       # File discovery (40+ languages)
├── embedder.py        # OllamaEmbedder wrapping /api/embed
├── vectorstore.py     # QdrantManager (upsert, search, incremental)
├── server/
│   └── main.py        # FastMCP server with 5 tools
└── client/
    ├── mcp_bridge.py  # MCP session over stdio
    ├── ollama_agent.py # Ollama chat with tool-calling
    ├── rag_loop.py    # RAG loop runner
    └── main.py        # CLI entry point
```

## Supported languages

Python, Go, JavaScript, TypeScript, Rust, Java, Kotlin, Scala, C, C++, C#, Ruby, PHP, Swift, Lua, Shell, SQL, R, HTML, CSS, SCSS, YAML, TOML, JSON, Markdown, reStructuredText, Terraform, HCL, Dockerfile, Protobuf, GraphQL.

## Embedding models

Any Ollama model that supports `/api/embed` works. Recommended:

| Model | Dimensions | Notes |
|-------|-----------|-------|
| `nomic-embed-text` | 768 | Good balance of quality and speed (default) |
| `mxbai-embed-large` | 1024 | Higher quality, slower |
| `all-minilm` | 384 | Fast, smaller footprint |
| `snowflake-arctic-embed` | 1024 | Strong code understanding |

## Design decisions

**Why MCP?** — The Model Context Protocol lets any compatible AI assistant (Claude Desktop, custom clients, IDE extensions) use ollqd's indexing and search tools without custom integration code.

**Why not tree-sitter for chunking?** — Tree-sitter gives perfect AST-based splits but adds a heavy dependency per language. The heuristic boundary detection covers ~90% of cases with zero extra setup.

**Why deterministic point IDs?** — `md5(file_path::chunk_N)` means re-indexing the same file overwrites existing points instead of creating duplicates. This makes incremental mode reliable.

**Why prefix chunks with metadata?** — Embedding models produce better vectors when given context. "File: auth/middleware.go | Language: go | Lines 45-82" followed by the code produces more semantically meaningful vectors.

## Legacy scripts

The standalone scripts from v0.1 are still available:

```bash
# Bulk index (standalone, no MCP)
python codebase_indexer.py /path/to/project --collection myproject

# Search (standalone, no MCP)
python codebase_search.py "auth middleware" --interactive
```

See [DESIGN.md](DESIGN.md) for the full architecture document with diagrams, security analysis (STRIDE), and detailed API reference.

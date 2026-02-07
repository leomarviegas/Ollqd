# Diagrams

All diagrams use Mermaid syntax and render in GitHub, VS Code, and any Mermaid-compatible viewer.

---

## 1. System Architecture

```mermaid
graph TB
    subgraph "User Interface"
        WEB["WebUI<br/>Alpine.js + Tailwind<br/>localhost:8000"]
        CLI["ollqd-chat<br/>CLI / REPL"]
        IDE["Claude Desktop<br/>/ MCP Host"]
    end

    subgraph "Web API Layer"
        FAPI["FastAPI Server<br/>REST + WS + SSE"]
        SYS["system.py<br/>health / config"]
        QR["qdrant.py<br/>collections CRUD"]
        OLR["ollama.py<br/>models / chat"]
        RAGR["rag.py<br/>index / search / chat"]
        TM["TaskManager<br/>background jobs"]
    end

    subgraph "MCP Client Layer"
        BRIDGE["MCPBridge<br/>(stdio_client)"]
        AGENT["OllamaToolAgent<br/>(httpx async)"]
        RAG["RAGLoopRunner<br/>(orchestrator)"]
    end

    subgraph "MCP Server Layer"
        SERVER["Ollqd MCP Server<br/>(FastMCP / stdio)"]
        T1["index_codebase"]
        T2["index_documents"]
        T3["semantic_search"]
        T4["list_collections"]
        T5["delete_collection"]
    end

    subgraph "Core Processing"
        DISC["Discovery<br/>files + images"]
        CHUNK["Chunking<br/>code-aware"]
        EMBED["OllamaEmbedder<br/>/api/embed"]
        VS["QdrantManager<br/>upsert / search"]
        CAPTION["Vision Captioning<br/>/api/chat + images"]
    end

    subgraph "Infrastructure"
        OLLAMA["Ollama Server<br/>localhost:11434"]
        QDRANT["Qdrant DB<br/>localhost:6333"]
        FS["Local Filesystem"]
    end

    WEB --> FAPI
    FAPI --> SYS & QR & OLR & RAGR
    RAGR --> TM
    CLI --> RAG
    IDE --> SERVER

    RAG --> BRIDGE & AGENT
    BRIDGE <-->|"stdio JSON-RPC"| SERVER

    SERVER --> T1 & T2 & T3 & T4 & T5

    RAGR --> DISC & CHUNK & EMBED & VS & CAPTION
    T1 & T2 --> DISC --> FS
    T1 & T2 --> CHUNK
    T1 & T2 & T3 --> EMBED --> OLLAMA
    T1 & T2 --> VS
    T3 --> VS --> QDRANT
    CAPTION --> OLLAMA
    AGENT --> OLLAMA

    style WEB fill:#6366f1,color:#fff
    style FAPI fill:#3b82f6,color:#fff
    style SERVER fill:#2d6a4f,color:#fff
    style RAG fill:#1b4332,color:#fff
    style OLLAMA fill:#e76f51,color:#fff
    style QDRANT fill:#264653,color:#fff
    style CAPTION fill:#9333ea,color:#fff
```

---

## 2. WebUI RAG Chat Sequence

```mermaid
sequenceDiagram
    actor User
    participant Browser as WebUI (Alpine.js)
    participant WS as WebSocket /api/rag/ws/chat
    participant Embedder as OllamaEmbedder
    participant Qdrant as Qdrant DB
    participant LLM as Ollama /api/chat

    User->>Browser: Type message, click Send
    Browser->>WS: connect ws://host/api/rag/ws/chat
    Browser->>WS: {"message": "...", "collection": "codebase", "model": "qwen2.5:14b"}

    WS->>Embedder: embed_query(message)
    Embedder->>LLM: POST /api/embed
    LLM-->>Embedder: vector[1024]

    WS->>Qdrant: query_points(vector, top_k=5)
    Qdrant-->>WS: [{score, file_path, content, language}]

    Note over WS: Build context from sources<br/>(code: [file L1-20]\ncontent)<br/>(image: [Image: path]\nCaption: ...)

    WS->>LLM: POST /api/chat (stream) with system prompt + context
    loop Token streaming
        LLM-->>WS: {"message": {"content": "token"}}
        WS-->>Browser: {"type": "chunk", "content": "token"}
        Browser->>Browser: Append to assistant message, render markdown
    end

    WS-->>Browser: {"type": "sources", "results": [...]}
    WS-->>Browser: {"type": "done"}
    Browser->>Browser: Show sources (thumbnails for images)
    Browser->>User: Complete response with citations
```

---

## 3. MCP CLI RAG Sequence

```mermaid
sequenceDiagram
    actor User
    participant CLI as ollqd-chat
    participant RAG as RAGLoopRunner
    participant Agent as OllamaToolAgent
    participant Bridge as MCPBridge
    participant Server as MCP Server
    participant Embed as OllamaEmbedder
    participant Qdrant as Qdrant DB
    participant LLM as Ollama /api/chat

    User->>CLI: "How does auth work?"
    CLI->>RAG: run(prompt, system_prompt)
    RAG->>Bridge: list_tools()
    Bridge->>Server: ListToolsRequest
    Server-->>Bridge: 5 tool definitions
    RAG->>RAG: mcp_tools_to_ollama()

    loop RAG Round (max 6)
        RAG->>Agent: chat(messages, tools)
        Agent->>LLM: POST /api/chat {messages, tools}
        LLM-->>Agent: {tool_calls: [{semantic_search, args}]}

        RAG->>Bridge: call_tool("semantic_search", args)
        Bridge->>Server: CallToolRequest
        Server->>Embed: embed_query("auth middleware")
        Embed-->>Server: vector[1024]
        Server->>Qdrant: query_points(vector, limit=5)
        Qdrant-->>Server: scored results
        Server-->>Bridge: tool_result (JSON)
        Bridge-->>RAG: result content

        RAG->>Agent: chat(messages + tool_result)
        Agent->>LLM: POST /api/chat {messages}
        LLM-->>Agent: {content: "The auth middleware is in..."}
    end

    RAG-->>CLI: final answer
    CLI-->>User: Display response with sources
```

---

## 4. Codebase Indexing Pipeline

```mermaid
flowchart LR
    subgraph "1. Discovery"
        ROOT["Root<br/>Directory"] --> WALK["os.walk()<br/>recursive"]
        WALK --> FILTER["Filter:<br/>extensions (40+)<br/>skip dirs<br/>skip files<br/>max 512KB"]
        FILTER --> HASH["SHA-256<br/>hash"]
        HASH --> FI["FileInfo[]"]
    end

    subgraph "2. Incremental"
        FI --> INCR{"incremental?"}
        INCR -->|Yes| COMPARE["Compare hashes<br/>vs Qdrant"]
        COMPARE --> CHANGED["Changed only"]
        COMPARE --> DEL["Delete stale"]
        INCR -->|No| ALL["All files"]
    end

    subgraph "3. Chunking"
        CHANGED & ALL --> CHUNK["Code-Aware<br/>Chunking"]
        CHUNK --> BOUNDARY{"Boundary?<br/>def/class/fn"}
        BOUNDARY -->|Yes| SPLIT["Split at<br/>boundary"]
        BOUNDARY -->|No/budget| FORCE["Force split<br/>with overlap"]
        SPLIT & FORCE --> CHUNKS["Chunk[]"]
    end

    subgraph "4. Embedding"
        CHUNKS --> PREFIX["Metadata<br/>prefix"]
        PREFIX --> BATCH["Batch x 32"]
        BATCH --> OLLAMA["/api/embed"]
        OLLAMA --> VECS["float[1024]"]
    end

    subgraph "5. Storage"
        VECS --> POINTS["PointStruct"]
        POINTS --> UPSERT["Qdrant<br/>upsert"]
        UPSERT --> DONE["Indexed"]
    end

    style ROOT fill:#e76f51,color:#fff
    style DONE fill:#2d6a4f,color:#fff
```

---

## 5. Image RAG Pipeline

```mermaid
flowchart LR
    subgraph "1. Discovery"
        IROOT["Image<br/>Directory"] --> IWALK["os.walk()"]
        IWALK --> IFILTER["Filter:<br/>.png .jpg .jpeg<br/>.gif .webp .bmp<br/>.tiff<br/>max 10MB"]
        IFILTER --> IHASH["SHA-256 hash"]
        IHASH --> IDIM["Pillow<br/>dimensions<br/>(optional)"]
        IDIM --> IMG["ImageFileInfo[]"]
    end

    subgraph "2. Incremental"
        IMG --> IINCR{"incremental?"}
        IINCR -->|Yes| ICOMP["Compare hashes"]
        ICOMP --> ICHANGED["Changed only"]
        IINCR -->|No| IALL["All images"]
    end

    subgraph "3. Captioning"
        ICHANGED & IALL --> B64["Base64<br/>encode"]
        B64 --> VISION["/api/chat<br/>+ images[]<br/>(llava:7b)"]
        VISION --> CAPTION["Text<br/>caption"]
    end

    subgraph "4. Embedding"
        CAPTION --> CTEXT["'Image: path<br/>Caption: ...'"]
        CTEXT --> IEMBED["/api/embed"]
        IEMBED --> IVEC["float[1024]"]
    end

    subgraph "5. Storage"
        IVEC --> IPOINT["PointStruct<br/>language='image'<br/>caption, abs_path"]
        IPOINT --> IUPSERT["Qdrant<br/>upsert"]
        IUPSERT --> IDONE["Indexed"]
    end

    style IROOT fill:#9333ea,color:#fff
    style VISION fill:#9333ea,color:#fff
    style IDONE fill:#2d6a4f,color:#fff
```

---

## 6. Component Diagram

```mermaid
graph LR
    subgraph "ollqd package"
        subgraph "web/"
            WAPP["app.py<br/><i>FastAPI</i>"]
            WDEPS["deps.py<br/><i>DI</i>"]
            WSYS["system.py<br/><i>health</i>"]
            WQD["qdrant.py<br/><i>collections</i>"]
            WOL["ollama.py<br/><i>models</i>"]
            WRAG["rag.py<br/><i>index+search+chat</i>"]
            WOLSVC["ollama_service.py<br/><i>async wrapper</i>"]
            WTM["task_manager.py<br/><i>bg jobs</i>"]
        end

        subgraph "server/"
            SMAIN["main.py<br/><i>FastMCP</i><br/>5 tools"]
        end

        subgraph "client/"
            CMAIN["main.py<br/><i>CLI</i>"]
            BRIDGE["mcp_bridge.py"]
            AGENT["ollama_agent.py"]
            RLOOP["rag_loop.py"]
        end

        subgraph "core"
            CONFIG["config.py"]
            MODELS["models.py"]
            ERRORS["errors.py"]
            DISC["discovery.py"]
            CHUNK["chunking.py"]
            EMBED["embedder.py"]
            VSTORE["vectorstore.py"]
        end

        subgraph "static/"
            HTML["index.html"]
            JS["app.js"]
            CSS["styles.css"]
        end
    end

    WAPP --> WSYS & WQD & WOL & WRAG
    WAPP --> WDEPS
    WRAG --> WTM & WOLSVC
    WRAG --> DISC & CHUNK & EMBED & VSTORE
    CMAIN --> RLOOP --> BRIDGE & AGENT
    SMAIN --> CONFIG & DISC & CHUNK & EMBED & VSTORE
    DISC & CHUNK --> MODELS
    EMBED & VSTORE --> ERRORS
```

---

## 7. Deployment Diagram

```mermaid
graph TB
    subgraph "Docker Compose / Developer Machine"
        subgraph "Container: ollqd-web"
            WEB_PROC["FastAPI + Uvicorn<br/>:8000"]
            STATIC["Static Files<br/>(HTML/JS/CSS)"]
        end

        subgraph "Container: qdrant"
            QD["Qdrant<br/>:6333 REST<br/>:6334 gRPC"]
            QVOL[("qdrant_data")]
        end

        subgraph "Container: ollama"
            OL["Ollama<br/>:11434"]
            OVOL[("ollama_data<br/>models")]
        end

        subgraph "Process: ollqd-chat (optional)"
            CLIENT["MCP Client"]
            subgraph "Child Process"
                MCP_SRV["MCP Server"]
            end
        end

        WEB_PROC -->|"HTTP"| OL
        WEB_PROC -->|"HTTP"| QD
        CLIENT <-->|"stdio"| MCP_SRV
        MCP_SRV -->|"HTTP"| OL
        MCP_SRV -->|"HTTP"| QD
    end

    BROWSER["Browser"] -->|"HTTP/WS :8000"| WEB_PROC
    CLAUDE["Claude Desktop"] -->|"stdio"| MCP_SRV

    style WEB_PROC fill:#3b82f6,color:#fff
    style QD fill:#264653,color:#fff
    style OL fill:#e76f51,color:#fff
    style BROWSER fill:#6366f1,color:#fff
```

---

## 8. State Machine: Task Lifecycle

```mermaid
stateDiagram-v2
    [*] --> pending : TaskManager.create()

    pending --> running : TaskManager.start()

    running --> running : update_progress(0.0-1.0)

    running --> completed : complete(result)
    running --> failed : fail(error)

    completed --> [*]
    failed --> [*]

    note right of running
        WebUI polls GET /api/rag/tasks/{id}
        every 1 second for progress updates
    end note
```

---

## 9. State Machine: RAG Chat Loop

```mermaid
stateDiagram-v2
    [*] --> Initialize : run(user_prompt)

    Initialize --> FetchTools : list_tools()
    FetchTools --> ConvertTools : mcp_tools_to_ollama()
    ConvertTools --> ChatRound

    state ChatRound {
        [*] --> SendToLLM
        SendToLLM --> CheckResponse
        CheckResponse --> ExecuteTools : has tool_calls
        CheckResponse --> ReturnAnswer : no tool_calls
        ExecuteTools --> AppendResults : bridge.call_tool()
        AppendResults --> [*] : next round
    }

    ChatRound --> MaxRoundsReached : round > max_rounds
    ChatRound --> ReturnAnswer : LLM returns content

    ReturnAnswer --> [*]
    MaxRoundsReached --> [*] : "Reached maximum rounds"
```

---

## 10. State Machine: Indexing Pipeline

```mermaid
stateDiagram-v2
    [*] --> Discovering : start indexing

    Discovering --> IncrementalCheck : files/images found
    Discovering --> Done : nothing found

    IncrementalCheck --> Processing : changed files exist
    IncrementalCheck --> Done : all up to date

    state Processing {
        [*] --> Chunking : (codebase/docs)
        [*] --> Captioning : (images)
        Chunking --> Embedding
        Captioning --> Embedding
        Embedding --> Upserting
        Upserting --> [*] : batch complete
    }

    Processing --> Done : all batches done
    Processing --> PartialDone : some batches failed
    Processing --> Error : fatal error

    PartialDone --> Done
    Error --> Done : report error

    Done --> [*]
```

---

## 11. Chunking Decision Flowchart

```mermaid
flowchart TD
    START["Read file content"] --> EMPTY{"Empty?"}
    EMPTY -->|Yes| SKIP["Return []"]
    EMPTY -->|No| LINES["Split into lines"]

    LINES --> LOOP["For each line"]
    LOOP --> BUDGET{"chars + line<br/>> budget?"}

    BUDGET -->|No| ADD["Add line to<br/>current chunk"]
    ADD --> LOOP

    BUDGET -->|Yes| BOUNDARY{"Is boundary<br/>line?"}

    BOUNDARY -->|Yes| FLUSH["Flush chunk<br/>with overlap"]
    FLUSH --> NEWCHUNK["Start new chunk"]
    NEWCHUNK --> ADD

    BOUNDARY -->|No| HARD{"Exceeds<br/>1.5x budget?"}
    HARD -->|Yes| FORCE["Force flush"]
    FORCE --> ADD
    HARD -->|No| ADD

    LOOP -->|"EOF"| FINAL["Flush remaining"]
    FINAL --> FIX["Set total_chunks"]
    FIX --> DONE["Return Chunk[]"]

    style START fill:#264653,color:#fff
    style DONE fill:#2d6a4f,color:#fff
```

---

## 12. WebSocket Chat Protocol

```mermaid
sequenceDiagram
    participant C as Browser (Alpine.js)
    participant S as FastAPI WebSocket

    C->>S: connect /api/rag/ws/chat
    S-->>C: connection accepted

    loop Per message
        C->>S: {"message": "...", "collection": "...", "model": "..."}

        Note over S: 1. Embed query<br/>2. Search Qdrant (top 5)<br/>3. Build context

        loop Token stream
            S-->>C: {"type": "chunk", "content": "token"}
        end

        S-->>C: {"type": "sources", "results": [{score, file_path, ...}]}
        S-->>C: {"type": "done"}
    end

    C->>S: close
```

---

## 13. Model Pull SSE Stream

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as FastAPI
    participant O as Ollama

    B->>F: POST /api/ollama/models/pull {"name": "llava:7b"}
    F->>O: POST /api/pull (stream)

    loop Progress events
        O-->>F: {"status": "pulling ...", "completed": N, "total": M}
        F-->>B: data: {"status": "...", "completed": N, "total": M}
        B->>B: Update progress bar
    end

    O-->>F: {"status": "success"}
    F-->>B: data: [DONE]
    B->>B: Reload models list
```

---

## 14. Boundary Detection by Language

```mermaid
graph LR
    subgraph "Language Boundary Patterns"
        PY["Python"] --> PYP["def, class,<br/>async def, @decorator"]
        GO["Go"] --> GOP["func, type"]
        JS["JS / TS"] --> JSP["function, export,<br/>class, const,<br/>describe, it, test"]
        RS["Rust"] --> RSP["fn, pub fn, impl,<br/>struct, enum,<br/>mod, trait"]
        JV["Java / Kotlin<br/>C# / Scala"] --> JVP["public, private,<br/>protected, class,<br/>interface, fun,<br/>data class, object"]
        CC["C / C++"] --> CCP["function signature<br/>with ( ) {"]
        MD["Markdown"] --> MDP["#, ##, ###"]
    end

    style PY fill:#3572A5,color:#fff
    style GO fill:#00ADD8,color:#fff
    style JS fill:#f7df1e,color:#000
    style RS fill:#dea584,color:#000
    style JV fill:#b07219,color:#fff
    style CC fill:#555555,color:#fff
    style MD fill:#083fa1,color:#fff
```

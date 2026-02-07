# Ollqd Documentation

> Local-first RAG System — Ollama + Qdrant | MCP Server + WebUI + CLI

## Contents

| # | Document | Description |
|---|----------|-------------|
| 01 | [Architecture](01-architecture.md) | High-Level Design, Low-Level Design, system topology, component interactions, technology stack |
| 02 | [Diagrams](02-diagrams.md) | System architecture, sequence diagrams, component diagrams, class diagrams, deployment diagrams, state machines (all Mermaid) |
| 03 | [User Flows](03-user-flows.md) | User journeys for WebUI, CLI, MCP/Claude Desktop, and Image RAG workflows |
| 04 | [Data Flows](04-data-flows.md) | Codebase indexing pipeline, image RAG pipeline, search pipeline, WebSocket chat flow, incremental indexing, vector lifecycle |
| 05 | [Features](05-features.md) | Feature inventory, capability matrix, feature-to-component mapping, configuration reference, supported languages |
| 06 | [API Reference](06-api-reference.md) | REST API (25+ endpoints), WebSocket protocol, MCP tool schemas, Pydantic models, error codes |

## Quick Navigation

| I want to... | Start here |
|--------------|------------|
| Understand the system | [Architecture](01-architecture.md) then [Diagrams](02-diagrams.md) |
| Use the WebUI | [User Flows](03-user-flows.md#2-webui-flows) |
| Use the CLI | [User Flows](03-user-flows.md#3-cli-flows) |
| Integrate with Claude Desktop | [User Flows](03-user-flows.md#4-mcp-integration-flow) |
| Understand the image pipeline | [Data Flows](04-data-flows.md#3-image-rag-pipeline) |
| See all features | [Features](05-features.md) |
| Build against the API | [API Reference](06-api-reference.md) |
| Contribute code | [Architecture LLD](01-architecture.md#2-low-level-design-lld) then [Features](05-features.md) |
| Deploy with Docker | [Architecture](01-architecture.md#15-deployment-topologies) |

## System at a Glance

```
                       +------------------+
                       |    WebUI (SPA)   |  Alpine.js + Tailwind
                       |  localhost:8000  |
                       +--------+---------+
                                |
                       +--------v---------+
                       |   FastAPI Server  |  REST + WebSocket + SSE
                       |   25+ endpoints   |
                       +--------+---------+
                                |
              +-----------------+------------------+
              |                 |                   |
     +--------v------+  +------v-------+  +--------v--------+
     | Ollama Server  |  | Qdrant DB    |  | Local Filesystem |
     | :11434         |  | :6333        |  | (source code,    |
     | embed / chat / |  | vectors +    |  |  images, docs)   |
     | vision caption |  | payload idx  |  |                  |
     +---------+------+  +------+-------+  +-----------------+
               |                |
     +---------v----------------v---------+
     |          MCP Server (stdio)        |  5 tools for AI assistants
     |    index / search / manage         |
     +--------+-----------+---------------+
              |           |
     +--------v---+  +----v-----------+
     | ollqd-chat |  | Claude Desktop |
     | CLI / REPL |  | / Any MCP Host |
     +------------+  +----------------+
```

## Version

This documentation covers Ollqd **v0.3.0** including:
- MCP server with 5 tools
- CLI client with interactive REPL
- WebUI with dashboard, collections, models, RAG chat, and indexing
- Image RAG pipeline (vision model captioning)
- Docker Compose deployment

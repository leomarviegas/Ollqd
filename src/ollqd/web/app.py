"""Ollqd WebUI — FastAPI application."""

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import ollama, qdrant, rag, smb, system

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="Ollqd WebUI",
    description="Web interface for Ollama + Qdrant RAG system",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(qdrant.router, prefix="/api/qdrant", tags=["qdrant"])
app.include_router(ollama.router, prefix="/api/ollama", tags=["ollama"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
app.include_router(smb.router, prefix="/api/smb", tags=["smb"])

# Static files (SPA) — mounted last as catch-all
static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


def main():
    print("\n  Ollqd WebUI")
    print("  Open http://localhost:8000 in your browser\n")
    uvicorn.run(
        "ollqd.web.app:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()

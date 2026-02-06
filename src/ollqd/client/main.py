#!/usr/bin/env python3
"""
Ollqd MCP Client — Interactive RAG chat using Ollama + MCP tools.

Usage:
  python -m ollqd.client.main "how does auth work?"
  python -m ollqd.client.main --interactive
  python -m ollqd.client.main --interactive --model llama3.1
"""

import argparse
import asyncio
import logging
import sys

from ..config import AppConfig
from .mcp_bridge import MCPBridge
from .ollama_agent import OllamaToolAgent
from .rag_loop import RAGLoopRunner

log = logging.getLogger("ollqd.client")

SYSTEM_PROMPT = """You are a helpful code assistant with access to a semantic search tool over the user's codebase.
When the user asks about code, use the semantic_search tool to find relevant code snippets before answering.
Always cite the file paths and line numbers from the search results.
If the codebase hasn't been indexed yet, suggest using the index_codebase tool first."""


async def run_single(prompt: str, cfg: AppConfig):
    bridge = await MCPBridge(
        command=sys.executable,
        args=["-m", "ollqd.server.main"],
    ).connect()

    agent = OllamaToolAgent(
        host=cfg.ollama.base_url,
        model=cfg.ollama.chat_model,
        timeout=cfg.ollama.timeout_s,
    )

    runner = RAGLoopRunner(bridge, agent, max_rounds=cfg.client.max_tool_rounds)

    try:
        answer = await runner.run(prompt, system_prompt=SYSTEM_PROMPT)
        print(answer)
    finally:
        await agent.close()
        await bridge.close()


async def run_interactive(cfg: AppConfig):
    print(f"\nOllqd RAG Chat (model: {cfg.ollama.chat_model})")
    print(f"  Server: {cfg.ollama.base_url} | Qdrant: {cfg.qdrant.url}")
    print("  Commands: :quit, :collection <name>, :model <name>")
    print()

    bridge = await MCPBridge(
        command=sys.executable,
        args=["-m", "ollqd.server.main"],
    ).connect()

    agent = OllamaToolAgent(
        host=cfg.ollama.base_url,
        model=cfg.ollama.chat_model,
        timeout=cfg.ollama.timeout_s,
    )

    runner = RAGLoopRunner(bridge, agent, max_rounds=cfg.client.max_tool_rounds)

    try:
        while True:
            try:
                query = input("ollqd> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye!")
                break

            if not query:
                continue
            if query in (":quit", ":q", ":exit"):
                break
            if query.startswith(":model "):
                new_model = query.split(maxsplit=1)[1]
                agent = OllamaToolAgent(
                    host=cfg.ollama.base_url,
                    model=new_model,
                    timeout=cfg.ollama.timeout_s,
                )
                runner = RAGLoopRunner(bridge, agent, max_rounds=cfg.client.max_tool_rounds)
                print(f"  Switched to model: {new_model}")
                continue

            try:
                answer = await runner.run(query, system_prompt=SYSTEM_PROMPT)
                print(f"\n{answer}\n")
            except Exception as e:
                print(f"  Error: {e}")
    finally:
        await agent.close()
        await bridge.close()


def main():
    parser = argparse.ArgumentParser(description="Ollqd RAG Client")
    parser.add_argument("query", nargs="?", help="Single query (omit for interactive)")
    parser.add_argument("--interactive", "-I", action="store_true", help="Interactive mode")
    parser.add_argument("--model", "-m", help="Ollama chat model override")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = AppConfig()
    if args.model:
        cfg.ollama.chat_model = args.model

    if args.interactive or args.query is None:
        asyncio.run(run_interactive(cfg))
    else:
        asyncio.run(run_single(args.query, cfg))


if __name__ == "__main__":
    main()

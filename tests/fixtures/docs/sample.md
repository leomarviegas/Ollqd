# Project Architecture Guide

## Overview

This document describes the architecture of the Ollqd self-hosted RAG platform.
The system uses a microservices architecture with five Docker containers.

## Components

### Gateway Service

The Go gateway handles HTTP routing, WebSocket upgrades, and reverse proxying.
It communicates with the Python worker via gRPC for compute-heavy operations.

### Worker Service

The Python worker performs chunking, embedding, search, and chat operations.
It uses an async gRPC server with streaming support for long-running tasks.

### Vector Database

Qdrant stores document embeddings and supports semantic similarity search.
Collections can be created, searched, and deleted through the gateway API.

## Configuration

Settings are managed through a three-tier system:
1. Environment variables in docker-compose.yml
2. Default values in ollqd.toml
3. SQLite persistence for runtime changes

## Security

PII masking uses regex patterns and spaCy NER to detect sensitive data.
Masked tokens are preserved through the LLM and unmasked in the response stream.

## Known Sentence for Search Validation

The quick brown fox jumps over the lazy dog near the ancient oak tree.
This sentence exists specifically for deterministic search result testing.

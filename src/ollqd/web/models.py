"""Pydantic request/response schemas for the web API."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Qdrant ──────────────────────────────────────────────────

class CreateCollectionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    vector_size: int = Field(..., gt=0, le=8192)
    distance: Literal["Cosine", "Euclid", "Dot", "Manhattan"] = "Cosine"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=100)
    language: Optional[str] = None
    file_path: Optional[str] = None


# ── Ollama ──────────────────────────────────────────────────

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


# ── RAG ─────────────────────────────────────────────────────

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


# ── System ─────────────────────────────────────────────────

class UpdateMountedPathsRequest(BaseModel):
    paths: list[str] = Field(..., min_length=1)


class UpdateEmbedModelRequest(BaseModel):
    model: str = Field(..., min_length=1)


class TestEmbedRequest(BaseModel):
    text: str = Field(..., min_length=1)


class CompareEmbedRequest(BaseModel):
    text: str = Field(..., min_length=1)
    model1: str = Field(..., min_length=1)
    model2: str = Field(..., min_length=1)


class UpdateDistanceConfigRequest(BaseModel):
    distance: Literal["Cosine", "Euclid", "Dot", "Manhattan"] = "Cosine"


# ── PII ───────────────────────────────────────────────────

class UpdatePIIConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    use_spacy: Optional[bool] = None
    mask_embeddings: Optional[bool] = None
    enabled_types: Optional[str] = None


class TestPIIMaskingRequest(BaseModel):
    text: str = Field(..., min_length=1)


# ── SMB/CIFS ──────────────────────────────────────────────

class SMBShareCreateRequest(BaseModel):
    server: str = Field(..., min_length=1)
    share: str = Field(..., min_length=1)
    username: str = ""
    password: str = ""
    domain: str = ""
    port: int = Field(445, ge=1, le=65535)
    label: str = ""


class SMBShareTestRequest(BaseModel):
    server: str = Field(..., min_length=1)
    share: str = Field(..., min_length=1)
    username: str = ""
    password: str = ""
    domain: str = ""
    port: int = Field(445, ge=1, le=65535)


class SMBShareListFilesRequest(BaseModel):
    path: str = "/"


class SMBShareIndexRequest(BaseModel):
    remote_paths: list[str] = Field(..., min_length=1)
    collection: str = "documents"
    chunk_size: int = Field(512, ge=32, le=4096)
    chunk_overlap: int = Field(64, ge=0, le=512)
    source_tag: str = "smb"

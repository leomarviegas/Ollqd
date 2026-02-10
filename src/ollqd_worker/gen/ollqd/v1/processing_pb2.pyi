from ollqd.v1 import types_pb2 as _types_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class IndexCodebaseRequest(_message.Message):
    __slots__ = ("root_path", "collection", "incremental", "chunk_size", "chunk_overlap", "extra_skip_dirs")
    ROOT_PATH_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    INCREMENTAL_FIELD_NUMBER: _ClassVar[int]
    CHUNK_SIZE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_OVERLAP_FIELD_NUMBER: _ClassVar[int]
    EXTRA_SKIP_DIRS_FIELD_NUMBER: _ClassVar[int]
    root_path: str
    collection: str
    incremental: bool
    chunk_size: int
    chunk_overlap: int
    extra_skip_dirs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, root_path: _Optional[str] = ..., collection: _Optional[str] = ..., incremental: bool = ..., chunk_size: _Optional[int] = ..., chunk_overlap: _Optional[int] = ..., extra_skip_dirs: _Optional[_Iterable[str]] = ...) -> None: ...

class IndexDocumentsRequest(_message.Message):
    __slots__ = ("paths", "collection", "chunk_size", "chunk_overlap", "source_tag")
    PATHS_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    CHUNK_SIZE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_OVERLAP_FIELD_NUMBER: _ClassVar[int]
    SOURCE_TAG_FIELD_NUMBER: _ClassVar[int]
    paths: _containers.RepeatedScalarFieldContainer[str]
    collection: str
    chunk_size: int
    chunk_overlap: int
    source_tag: str
    def __init__(self, paths: _Optional[_Iterable[str]] = ..., collection: _Optional[str] = ..., chunk_size: _Optional[int] = ..., chunk_overlap: _Optional[int] = ..., source_tag: _Optional[str] = ...) -> None: ...

class IndexImagesRequest(_message.Message):
    __slots__ = ("root_path", "collection", "vision_model", "caption_prompt", "incremental", "max_image_size_kb", "extra_skip_dirs")
    ROOT_PATH_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    VISION_MODEL_FIELD_NUMBER: _ClassVar[int]
    CAPTION_PROMPT_FIELD_NUMBER: _ClassVar[int]
    INCREMENTAL_FIELD_NUMBER: _ClassVar[int]
    MAX_IMAGE_SIZE_KB_FIELD_NUMBER: _ClassVar[int]
    EXTRA_SKIP_DIRS_FIELD_NUMBER: _ClassVar[int]
    root_path: str
    collection: str
    vision_model: str
    caption_prompt: str
    incremental: bool
    max_image_size_kb: int
    extra_skip_dirs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, root_path: _Optional[str] = ..., collection: _Optional[str] = ..., vision_model: _Optional[str] = ..., caption_prompt: _Optional[str] = ..., incremental: bool = ..., max_image_size_kb: _Optional[int] = ..., extra_skip_dirs: _Optional[_Iterable[str]] = ...) -> None: ...

class IndexUploadsRequest(_message.Message):
    __slots__ = ("saved_paths", "collection", "chunk_size", "chunk_overlap", "source_tag", "vision_model", "caption_prompt")
    SAVED_PATHS_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    CHUNK_SIZE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_OVERLAP_FIELD_NUMBER: _ClassVar[int]
    SOURCE_TAG_FIELD_NUMBER: _ClassVar[int]
    VISION_MODEL_FIELD_NUMBER: _ClassVar[int]
    CAPTION_PROMPT_FIELD_NUMBER: _ClassVar[int]
    saved_paths: _containers.RepeatedScalarFieldContainer[str]
    collection: str
    chunk_size: int
    chunk_overlap: int
    source_tag: str
    vision_model: str
    caption_prompt: str
    def __init__(self, saved_paths: _Optional[_Iterable[str]] = ..., collection: _Optional[str] = ..., chunk_size: _Optional[int] = ..., chunk_overlap: _Optional[int] = ..., source_tag: _Optional[str] = ..., vision_model: _Optional[str] = ..., caption_prompt: _Optional[str] = ...) -> None: ...

class IndexSMBFilesRequest(_message.Message):
    __slots__ = ("share_id", "remote_paths", "collection", "chunk_size", "chunk_overlap", "source_tag", "server", "share", "username", "password", "domain", "port")
    SHARE_ID_FIELD_NUMBER: _ClassVar[int]
    REMOTE_PATHS_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    CHUNK_SIZE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_OVERLAP_FIELD_NUMBER: _ClassVar[int]
    SOURCE_TAG_FIELD_NUMBER: _ClassVar[int]
    SERVER_FIELD_NUMBER: _ClassVar[int]
    SHARE_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    DOMAIN_FIELD_NUMBER: _ClassVar[int]
    PORT_FIELD_NUMBER: _ClassVar[int]
    share_id: str
    remote_paths: _containers.RepeatedScalarFieldContainer[str]
    collection: str
    chunk_size: int
    chunk_overlap: int
    source_tag: str
    server: str
    share: str
    username: str
    password: str
    domain: str
    port: int
    def __init__(self, share_id: _Optional[str] = ..., remote_paths: _Optional[_Iterable[str]] = ..., collection: _Optional[str] = ..., chunk_size: _Optional[int] = ..., chunk_overlap: _Optional[int] = ..., source_tag: _Optional[str] = ..., server: _Optional[str] = ..., share: _Optional[str] = ..., username: _Optional[str] = ..., password: _Optional[str] = ..., domain: _Optional[str] = ..., port: _Optional[int] = ...) -> None: ...

class CancelTaskRequest(_message.Message):
    __slots__ = ("task_id",)
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    def __init__(self, task_id: _Optional[str] = ...) -> None: ...

class CancelTaskResponse(_message.Message):
    __slots__ = ("cancelled", "message")
    CANCELLED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    cancelled: bool
    message: str
    def __init__(self, cancelled: bool = ..., message: _Optional[str] = ...) -> None: ...

class SearchRequest(_message.Message):
    __slots__ = ("query", "top_k", "language", "file_path")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    TOP_K_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    query: str
    top_k: int
    language: str
    file_path: str
    def __init__(self, query: _Optional[str] = ..., top_k: _Optional[int] = ..., language: _Optional[str] = ..., file_path: _Optional[str] = ...) -> None: ...

class SearchCollectionRequest(_message.Message):
    __slots__ = ("collection", "query", "top_k", "language", "file_path")
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    TOP_K_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    collection: str
    query: str
    top_k: int
    language: str
    file_path: str
    def __init__(self, collection: _Optional[str] = ..., query: _Optional[str] = ..., top_k: _Optional[int] = ..., language: _Optional[str] = ..., file_path: _Optional[str] = ...) -> None: ...

class SearchResponse(_message.Message):
    __slots__ = ("status", "query", "collection", "results")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    status: str
    query: str
    collection: str
    results: _containers.RepeatedCompositeFieldContainer[_types_pb2.SearchHit]
    def __init__(self, status: _Optional[str] = ..., query: _Optional[str] = ..., collection: _Optional[str] = ..., results: _Optional[_Iterable[_Union[_types_pb2.SearchHit, _Mapping]]] = ...) -> None: ...

class ChatRequest(_message.Message):
    __slots__ = ("message", "collection", "model", "pii_enabled")
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    PII_ENABLED_FIELD_NUMBER: _ClassVar[int]
    message: str
    collection: str
    model: str
    pii_enabled: bool
    def __init__(self, message: _Optional[str] = ..., collection: _Optional[str] = ..., model: _Optional[str] = ..., pii_enabled: bool = ...) -> None: ...

class ChatEvent(_message.Message):
    __slots__ = ("type", "content", "sources", "pii_masked", "pii_entities_count")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    PII_MASKED_FIELD_NUMBER: _ClassVar[int]
    PII_ENTITIES_COUNT_FIELD_NUMBER: _ClassVar[int]
    type: str
    content: str
    sources: _containers.RepeatedCompositeFieldContainer[_types_pb2.SearchHit]
    pii_masked: bool
    pii_entities_count: int
    def __init__(self, type: _Optional[str] = ..., content: _Optional[str] = ..., sources: _Optional[_Iterable[_Union[_types_pb2.SearchHit, _Mapping]]] = ..., pii_masked: bool = ..., pii_entities_count: _Optional[int] = ...) -> None: ...

class GetEmbeddingInfoRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class EmbeddingInfoResponse(_message.Message):
    __slots__ = ("model", "dimension", "latency_ms", "previous_model")
    MODEL_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    PREVIOUS_MODEL_FIELD_NUMBER: _ClassVar[int]
    model: str
    dimension: int
    latency_ms: int
    previous_model: str
    def __init__(self, model: _Optional[str] = ..., dimension: _Optional[int] = ..., latency_ms: _Optional[int] = ..., previous_model: _Optional[str] = ...) -> None: ...

class TestEmbedRequest(_message.Message):
    __slots__ = ("text",)
    TEXT_FIELD_NUMBER: _ClassVar[int]
    text: str
    def __init__(self, text: _Optional[str] = ...) -> None: ...

class TestEmbedResponse(_message.Message):
    __slots__ = ("dimension", "min", "max", "mean", "stdev", "norm", "latency_ms")
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    MIN_FIELD_NUMBER: _ClassVar[int]
    MAX_FIELD_NUMBER: _ClassVar[int]
    MEAN_FIELD_NUMBER: _ClassVar[int]
    STDEV_FIELD_NUMBER: _ClassVar[int]
    NORM_FIELD_NUMBER: _ClassVar[int]
    LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    dimension: int
    min: float
    max: float
    mean: float
    stdev: float
    norm: float
    latency_ms: int
    def __init__(self, dimension: _Optional[int] = ..., min: _Optional[float] = ..., max: _Optional[float] = ..., mean: _Optional[float] = ..., stdev: _Optional[float] = ..., norm: _Optional[float] = ..., latency_ms: _Optional[int] = ...) -> None: ...

class CompareModelsRequest(_message.Message):
    __slots__ = ("text", "model1", "model2")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    MODEL1_FIELD_NUMBER: _ClassVar[int]
    MODEL2_FIELD_NUMBER: _ClassVar[int]
    text: str
    model1: str
    model2: str
    def __init__(self, text: _Optional[str] = ..., model1: _Optional[str] = ..., model2: _Optional[str] = ...) -> None: ...

class ModelTestResult(_message.Message):
    __slots__ = ("model", "dimension", "min", "max", "mean", "stdev", "norm", "latency_ms", "error")
    MODEL_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    MIN_FIELD_NUMBER: _ClassVar[int]
    MAX_FIELD_NUMBER: _ClassVar[int]
    MEAN_FIELD_NUMBER: _ClassVar[int]
    STDEV_FIELD_NUMBER: _ClassVar[int]
    NORM_FIELD_NUMBER: _ClassVar[int]
    LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    model: str
    dimension: int
    min: float
    max: float
    mean: float
    stdev: float
    norm: float
    latency_ms: int
    error: str
    def __init__(self, model: _Optional[str] = ..., dimension: _Optional[int] = ..., min: _Optional[float] = ..., max: _Optional[float] = ..., mean: _Optional[float] = ..., stdev: _Optional[float] = ..., norm: _Optional[float] = ..., latency_ms: _Optional[int] = ..., error: _Optional[str] = ...) -> None: ...

class CompareModelsResponse(_message.Message):
    __slots__ = ("model1", "model2", "text")
    MODEL1_FIELD_NUMBER: _ClassVar[int]
    MODEL2_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    model1: ModelTestResult
    model2: ModelTestResult
    text: str
    def __init__(self, model1: _Optional[_Union[ModelTestResult, _Mapping]] = ..., model2: _Optional[_Union[ModelTestResult, _Mapping]] = ..., text: _Optional[str] = ...) -> None: ...

class SetEmbedModelRequest(_message.Message):
    __slots__ = ("model",)
    MODEL_FIELD_NUMBER: _ClassVar[int]
    model: str
    def __init__(self, model: _Optional[str] = ...) -> None: ...

class TestMaskingRequest(_message.Message):
    __slots__ = ("text",)
    TEXT_FIELD_NUMBER: _ClassVar[int]
    text: str
    def __init__(self, text: _Optional[str] = ...) -> None: ...

class PIIEntity(_message.Message):
    __slots__ = ("token", "original")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_FIELD_NUMBER: _ClassVar[int]
    token: str
    original: str
    def __init__(self, token: _Optional[str] = ..., original: _Optional[str] = ...) -> None: ...

class TestMaskingResponse(_message.Message):
    __slots__ = ("original", "masked", "entities", "entity_count")
    ORIGINAL_FIELD_NUMBER: _ClassVar[int]
    MASKED_FIELD_NUMBER: _ClassVar[int]
    ENTITIES_FIELD_NUMBER: _ClassVar[int]
    ENTITY_COUNT_FIELD_NUMBER: _ClassVar[int]
    original: str
    masked: str
    entities: _containers.RepeatedCompositeFieldContainer[PIIEntity]
    entity_count: int
    def __init__(self, original: _Optional[str] = ..., masked: _Optional[str] = ..., entities: _Optional[_Iterable[_Union[PIIEntity, _Mapping]]] = ..., entity_count: _Optional[int] = ...) -> None: ...

class GetConfigRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class UpdateMountedPathsRequest(_message.Message):
    __slots__ = ("paths",)
    PATHS_FIELD_NUMBER: _ClassVar[int]
    paths: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, paths: _Optional[_Iterable[str]] = ...) -> None: ...

class UpdateMountedPathsResponse(_message.Message):
    __slots__ = ("mounted_paths",)
    MOUNTED_PATHS_FIELD_NUMBER: _ClassVar[int]
    mounted_paths: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, mounted_paths: _Optional[_Iterable[str]] = ...) -> None: ...

class UpdatePIIRequest(_message.Message):
    __slots__ = ("enabled", "use_spacy", "mask_embeddings", "enabled_types")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    USE_SPACY_FIELD_NUMBER: _ClassVar[int]
    MASK_EMBEDDINGS_FIELD_NUMBER: _ClassVar[int]
    ENABLED_TYPES_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    use_spacy: bool
    mask_embeddings: bool
    enabled_types: str
    def __init__(self, enabled: bool = ..., use_spacy: bool = ..., mask_embeddings: bool = ..., enabled_types: _Optional[str] = ...) -> None: ...

class PIIConfigResponse(_message.Message):
    __slots__ = ("enabled", "use_spacy", "mask_embeddings", "enabled_types", "spacy_available")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    USE_SPACY_FIELD_NUMBER: _ClassVar[int]
    MASK_EMBEDDINGS_FIELD_NUMBER: _ClassVar[int]
    ENABLED_TYPES_FIELD_NUMBER: _ClassVar[int]
    SPACY_AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    use_spacy: bool
    mask_embeddings: bool
    enabled_types: str
    spacy_available: bool
    def __init__(self, enabled: bool = ..., use_spacy: bool = ..., mask_embeddings: bool = ..., enabled_types: _Optional[str] = ..., spacy_available: bool = ...) -> None: ...

class UpdateDoclingRequest(_message.Message):
    __slots__ = ("enabled", "ocr_enabled", "ocr_engine", "table_structure", "timeout_s")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    OCR_ENABLED_FIELD_NUMBER: _ClassVar[int]
    OCR_ENGINE_FIELD_NUMBER: _ClassVar[int]
    TABLE_STRUCTURE_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    ocr_enabled: bool
    ocr_engine: str
    table_structure: bool
    timeout_s: float
    def __init__(self, enabled: bool = ..., ocr_enabled: bool = ..., ocr_engine: _Optional[str] = ..., table_structure: bool = ..., timeout_s: _Optional[float] = ...) -> None: ...

class DoclingConfigResponse(_message.Message):
    __slots__ = ("enabled", "ocr_enabled", "ocr_engine", "table_structure", "timeout_s", "available", "supported_extensions")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    OCR_ENABLED_FIELD_NUMBER: _ClassVar[int]
    OCR_ENGINE_FIELD_NUMBER: _ClassVar[int]
    TABLE_STRUCTURE_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    SUPPORTED_EXTENSIONS_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    ocr_enabled: bool
    ocr_engine: str
    table_structure: bool
    timeout_s: float
    available: bool
    supported_extensions: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, enabled: bool = ..., ocr_enabled: bool = ..., ocr_engine: _Optional[str] = ..., table_structure: bool = ..., timeout_s: _Optional[float] = ..., available: bool = ..., supported_extensions: _Optional[_Iterable[str]] = ...) -> None: ...

class UpdateDistanceRequest(_message.Message):
    __slots__ = ("distance",)
    DISTANCE_FIELD_NUMBER: _ClassVar[int]
    distance: str
    def __init__(self, distance: _Optional[str] = ...) -> None: ...

class UpdateDistanceResponse(_message.Message):
    __slots__ = ("distance", "previous")
    DISTANCE_FIELD_NUMBER: _ClassVar[int]
    PREVIOUS_FIELD_NUMBER: _ClassVar[int]
    distance: str
    previous: str
    def __init__(self, distance: _Optional[str] = ..., previous: _Optional[str] = ...) -> None: ...

class UpdateOllamaRequest(_message.Message):
    __slots__ = ("base_url", "chat_model", "embed_model", "vision_model", "timeout_s", "local")
    BASE_URL_FIELD_NUMBER: _ClassVar[int]
    CHAT_MODEL_FIELD_NUMBER: _ClassVar[int]
    EMBED_MODEL_FIELD_NUMBER: _ClassVar[int]
    VISION_MODEL_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    LOCAL_FIELD_NUMBER: _ClassVar[int]
    base_url: str
    chat_model: str
    embed_model: str
    vision_model: str
    timeout_s: float
    local: bool
    def __init__(self, base_url: _Optional[str] = ..., chat_model: _Optional[str] = ..., embed_model: _Optional[str] = ..., vision_model: _Optional[str] = ..., timeout_s: _Optional[float] = ..., local: bool = ...) -> None: ...

class OllamaConfigResponse(_message.Message):
    __slots__ = ("base_url", "chat_model", "embed_model", "vision_model", "timeout_s", "local")
    BASE_URL_FIELD_NUMBER: _ClassVar[int]
    CHAT_MODEL_FIELD_NUMBER: _ClassVar[int]
    EMBED_MODEL_FIELD_NUMBER: _ClassVar[int]
    VISION_MODEL_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_S_FIELD_NUMBER: _ClassVar[int]
    LOCAL_FIELD_NUMBER: _ClassVar[int]
    base_url: str
    chat_model: str
    embed_model: str
    vision_model: str
    timeout_s: float
    local: bool
    def __init__(self, base_url: _Optional[str] = ..., chat_model: _Optional[str] = ..., embed_model: _Optional[str] = ..., vision_model: _Optional[str] = ..., timeout_s: _Optional[float] = ..., local: bool = ...) -> None: ...

class UpdateQdrantRequest(_message.Message):
    __slots__ = ("url", "default_collection", "default_distance")
    URL_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_COLLECTION_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_DISTANCE_FIELD_NUMBER: _ClassVar[int]
    url: str
    default_collection: str
    default_distance: str
    def __init__(self, url: _Optional[str] = ..., default_collection: _Optional[str] = ..., default_distance: _Optional[str] = ...) -> None: ...

class QdrantConfigResponse(_message.Message):
    __slots__ = ("url", "default_collection", "default_distance")
    URL_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_COLLECTION_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_DISTANCE_FIELD_NUMBER: _ClassVar[int]
    url: str
    default_collection: str
    default_distance: str
    def __init__(self, url: _Optional[str] = ..., default_collection: _Optional[str] = ..., default_distance: _Optional[str] = ...) -> None: ...

class UpdateChunkingRequest(_message.Message):
    __slots__ = ("chunk_size", "chunk_overlap", "max_file_size_kb")
    CHUNK_SIZE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_OVERLAP_FIELD_NUMBER: _ClassVar[int]
    MAX_FILE_SIZE_KB_FIELD_NUMBER: _ClassVar[int]
    chunk_size: int
    chunk_overlap: int
    max_file_size_kb: int
    def __init__(self, chunk_size: _Optional[int] = ..., chunk_overlap: _Optional[int] = ..., max_file_size_kb: _Optional[int] = ...) -> None: ...

class ChunkingConfigResponse(_message.Message):
    __slots__ = ("chunk_size", "chunk_overlap", "max_file_size_kb")
    CHUNK_SIZE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_OVERLAP_FIELD_NUMBER: _ClassVar[int]
    MAX_FILE_SIZE_KB_FIELD_NUMBER: _ClassVar[int]
    chunk_size: int
    chunk_overlap: int
    max_file_size_kb: int
    def __init__(self, chunk_size: _Optional[int] = ..., chunk_overlap: _Optional[int] = ..., max_file_size_kb: _Optional[int] = ...) -> None: ...

class UpdateImageRequest(_message.Message):
    __slots__ = ("max_image_size_kb", "caption_prompt")
    MAX_IMAGE_SIZE_KB_FIELD_NUMBER: _ClassVar[int]
    CAPTION_PROMPT_FIELD_NUMBER: _ClassVar[int]
    max_image_size_kb: int
    caption_prompt: str
    def __init__(self, max_image_size_kb: _Optional[int] = ..., caption_prompt: _Optional[str] = ...) -> None: ...

class ImageConfigResponse(_message.Message):
    __slots__ = ("max_image_size_kb", "caption_prompt")
    MAX_IMAGE_SIZE_KB_FIELD_NUMBER: _ClassVar[int]
    CAPTION_PROMPT_FIELD_NUMBER: _ClassVar[int]
    max_image_size_kb: int
    caption_prompt: str
    def __init__(self, max_image_size_kb: _Optional[int] = ..., caption_prompt: _Optional[str] = ...) -> None: ...

class GetPIIConfigRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetDoclingConfigRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ResetConfigRequest(_message.Message):
    __slots__ = ("section", "keys")
    SECTION_FIELD_NUMBER: _ClassVar[int]
    KEYS_FIELD_NUMBER: _ClassVar[int]
    section: str
    keys: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, section: _Optional[str] = ..., keys: _Optional[_Iterable[str]] = ...) -> None: ...

class ResetConfigResponse(_message.Message):
    __slots__ = ("section", "reset_keys")
    SECTION_FIELD_NUMBER: _ClassVar[int]
    RESET_KEYS_FIELD_NUMBER: _ClassVar[int]
    section: str
    reset_keys: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, section: _Optional[str] = ..., reset_keys: _Optional[_Iterable[str]] = ...) -> None: ...

class OverviewRequest(_message.Message):
    __slots__ = ("collection", "limit")
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    collection: str
    limit: int
    def __init__(self, collection: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class VisNode(_message.Message):
    __slots__ = ("id", "label", "title", "color", "size", "shape", "file_path", "language", "chunks", "level")
    ID_FIELD_NUMBER: _ClassVar[int]
    LABEL_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    SHAPE_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    CHUNKS_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    id: int
    label: str
    title: str
    color: str
    size: int
    shape: str
    file_path: str
    language: str
    chunks: int
    level: int
    def __init__(self, id: _Optional[int] = ..., label: _Optional[str] = ..., title: _Optional[str] = ..., color: _Optional[str] = ..., size: _Optional[int] = ..., shape: _Optional[str] = ..., file_path: _Optional[str] = ..., language: _Optional[str] = ..., chunks: _Optional[int] = ..., level: _Optional[int] = ...) -> None: ...

class VisEdge(_message.Message):
    __slots__ = ("to",)
    FROM_FIELD_NUMBER: _ClassVar[int]
    TO_FIELD_NUMBER: _ClassVar[int]
    to: int
    def __init__(self, to: _Optional[int] = ..., **kwargs) -> None: ...

class OverviewStats(_message.Message):
    __slots__ = ("total_files", "total_chunks", "collection")
    TOTAL_FILES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_CHUNKS_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    total_files: int
    total_chunks: int
    collection: str
    def __init__(self, total_files: _Optional[int] = ..., total_chunks: _Optional[int] = ..., collection: _Optional[str] = ...) -> None: ...

class OverviewResponse(_message.Message):
    __slots__ = ("nodes", "edges", "stats")
    NODES_FIELD_NUMBER: _ClassVar[int]
    EDGES_FIELD_NUMBER: _ClassVar[int]
    STATS_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[VisNode]
    edges: _containers.RepeatedCompositeFieldContainer[VisEdge]
    stats: OverviewStats
    def __init__(self, nodes: _Optional[_Iterable[_Union[VisNode, _Mapping]]] = ..., edges: _Optional[_Iterable[_Union[VisEdge, _Mapping]]] = ..., stats: _Optional[_Union[OverviewStats, _Mapping]] = ...) -> None: ...

class FileTreeRequest(_message.Message):
    __slots__ = ("collection", "file_path")
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    collection: str
    file_path: str
    def __init__(self, collection: _Optional[str] = ..., file_path: _Optional[str] = ...) -> None: ...

class FileTreeResponse(_message.Message):
    __slots__ = ("nodes", "edges", "file_path", "total_chunks")
    NODES_FIELD_NUMBER: _ClassVar[int]
    EDGES_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    TOTAL_CHUNKS_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[VisNode]
    edges: _containers.RepeatedCompositeFieldContainer[VisEdge]
    file_path: str
    total_chunks: int
    def __init__(self, nodes: _Optional[_Iterable[_Union[VisNode, _Mapping]]] = ..., edges: _Optional[_Iterable[_Union[VisEdge, _Mapping]]] = ..., file_path: _Optional[str] = ..., total_chunks: _Optional[int] = ...) -> None: ...

class VectorsRequest(_message.Message):
    __slots__ = ("collection", "method", "dims", "limit")
    COLLECTION_FIELD_NUMBER: _ClassVar[int]
    METHOD_FIELD_NUMBER: _ClassVar[int]
    DIMS_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    collection: str
    method: str
    dims: int
    limit: int
    def __init__(self, collection: _Optional[str] = ..., method: _Optional[str] = ..., dims: _Optional[int] = ..., limit: _Optional[int] = ...) -> None: ...

class VectorPoint(_message.Message):
    __slots__ = ("x", "y", "z", "file", "language", "chunk", "color")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    FILE_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    file: str
    language: str
    chunk: int
    color: str
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ..., file: _Optional[str] = ..., language: _Optional[str] = ..., chunk: _Optional[int] = ..., color: _Optional[str] = ...) -> None: ...

class VectorsResponse(_message.Message):
    __slots__ = ("points", "method", "dims", "original_dims", "total_points")
    POINTS_FIELD_NUMBER: _ClassVar[int]
    METHOD_FIELD_NUMBER: _ClassVar[int]
    DIMS_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_DIMS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_POINTS_FIELD_NUMBER: _ClassVar[int]
    points: _containers.RepeatedCompositeFieldContainer[VectorPoint]
    method: str
    dims: int
    original_dims: int
    total_points: int
    def __init__(self, points: _Optional[_Iterable[_Union[VectorPoint, _Mapping]]] = ..., method: _Optional[str] = ..., dims: _Optional[int] = ..., original_dims: _Optional[int] = ..., total_points: _Optional[int] = ...) -> None: ...

class SMBTestRequest(_message.Message):
    __slots__ = ("server", "share", "username", "password", "domain", "port")
    SERVER_FIELD_NUMBER: _ClassVar[int]
    SHARE_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    DOMAIN_FIELD_NUMBER: _ClassVar[int]
    PORT_FIELD_NUMBER: _ClassVar[int]
    server: str
    share: str
    username: str
    password: str
    domain: str
    port: int
    def __init__(self, server: _Optional[str] = ..., share: _Optional[str] = ..., username: _Optional[str] = ..., password: _Optional[str] = ..., domain: _Optional[str] = ..., port: _Optional[int] = ...) -> None: ...

class SMBTestResponse(_message.Message):
    __slots__ = ("ok", "message")
    OK_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ok: bool
    message: str
    def __init__(self, ok: bool = ..., message: _Optional[str] = ...) -> None: ...

class SMBBrowseRequest(_message.Message):
    __slots__ = ("server", "share", "username", "password", "domain", "port", "path")
    SERVER_FIELD_NUMBER: _ClassVar[int]
    SHARE_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    DOMAIN_FIELD_NUMBER: _ClassVar[int]
    PORT_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    server: str
    share: str
    username: str
    password: str
    domain: str
    port: int
    path: str
    def __init__(self, server: _Optional[str] = ..., share: _Optional[str] = ..., username: _Optional[str] = ..., password: _Optional[str] = ..., domain: _Optional[str] = ..., port: _Optional[int] = ..., path: _Optional[str] = ...) -> None: ...

class SMBFileEntry(_message.Message):
    __slots__ = ("name", "is_dir", "size", "path")
    NAME_FIELD_NUMBER: _ClassVar[int]
    IS_DIR_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    name: str
    is_dir: bool
    size: int
    path: str
    def __init__(self, name: _Optional[str] = ..., is_dir: bool = ..., size: _Optional[int] = ..., path: _Optional[str] = ...) -> None: ...

class SMBBrowseResponse(_message.Message):
    __slots__ = ("files", "path")
    FILES_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    files: _containers.RepeatedCompositeFieldContainer[SMBFileEntry]
    path: str
    def __init__(self, files: _Optional[_Iterable[_Union[SMBFileEntry, _Mapping]]] = ..., path: _Optional[str] = ...) -> None: ...

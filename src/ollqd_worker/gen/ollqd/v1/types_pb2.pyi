from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Chunk(_message.Message):
    __slots__ = ("file_path", "language", "chunk_index", "total_chunks", "start_line", "end_line", "content", "content_hash", "point_id", "source_tag")
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_INDEX_FIELD_NUMBER: _ClassVar[int]
    TOTAL_CHUNKS_FIELD_NUMBER: _ClassVar[int]
    START_LINE_FIELD_NUMBER: _ClassVar[int]
    END_LINE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    CONTENT_HASH_FIELD_NUMBER: _ClassVar[int]
    POINT_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_TAG_FIELD_NUMBER: _ClassVar[int]
    file_path: str
    language: str
    chunk_index: int
    total_chunks: int
    start_line: int
    end_line: int
    content: str
    content_hash: str
    point_id: str
    source_tag: str
    def __init__(self, file_path: _Optional[str] = ..., language: _Optional[str] = ..., chunk_index: _Optional[int] = ..., total_chunks: _Optional[int] = ..., start_line: _Optional[int] = ..., end_line: _Optional[int] = ..., content: _Optional[str] = ..., content_hash: _Optional[str] = ..., point_id: _Optional[str] = ..., source_tag: _Optional[str] = ...) -> None: ...

class SearchHit(_message.Message):
    __slots__ = ("score", "file_path", "language", "lines", "chunk_info", "content", "abs_path", "caption", "image_type", "width", "height")
    SCORE_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    LINES_FIELD_NUMBER: _ClassVar[int]
    CHUNK_INFO_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    ABS_PATH_FIELD_NUMBER: _ClassVar[int]
    CAPTION_FIELD_NUMBER: _ClassVar[int]
    IMAGE_TYPE_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    score: float
    file_path: str
    language: str
    lines: str
    chunk_info: str
    content: str
    abs_path: str
    caption: str
    image_type: str
    width: int
    height: int
    def __init__(self, score: _Optional[float] = ..., file_path: _Optional[str] = ..., language: _Optional[str] = ..., lines: _Optional[str] = ..., chunk_info: _Optional[str] = ..., content: _Optional[str] = ..., abs_path: _Optional[str] = ..., caption: _Optional[str] = ..., image_type: _Optional[str] = ..., width: _Optional[int] = ..., height: _Optional[int] = ...) -> None: ...

class TaskProgress(_message.Message):
    __slots__ = ("task_id", "progress", "status", "error", "result")
    class ResultEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    progress: float
    status: str
    error: str
    result: _containers.ScalarMap[str, str]
    def __init__(self, task_id: _Optional[str] = ..., progress: _Optional[float] = ..., status: _Optional[str] = ..., error: _Optional[str] = ..., result: _Optional[_Mapping[str, str]] = ...) -> None: ...

class OllamaConfig(_message.Message):
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

class QdrantConfig(_message.Message):
    __slots__ = ("url", "default_collection", "default_distance")
    URL_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_COLLECTION_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_DISTANCE_FIELD_NUMBER: _ClassVar[int]
    url: str
    default_collection: str
    default_distance: str
    def __init__(self, url: _Optional[str] = ..., default_collection: _Optional[str] = ..., default_distance: _Optional[str] = ...) -> None: ...

class ChunkingConfig(_message.Message):
    __slots__ = ("chunk_size", "chunk_overlap", "max_file_size_kb")
    CHUNK_SIZE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_OVERLAP_FIELD_NUMBER: _ClassVar[int]
    MAX_FILE_SIZE_KB_FIELD_NUMBER: _ClassVar[int]
    chunk_size: int
    chunk_overlap: int
    max_file_size_kb: int
    def __init__(self, chunk_size: _Optional[int] = ..., chunk_overlap: _Optional[int] = ..., max_file_size_kb: _Optional[int] = ...) -> None: ...

class ImageConfig(_message.Message):
    __slots__ = ("max_image_size_kb", "caption_prompt")
    MAX_IMAGE_SIZE_KB_FIELD_NUMBER: _ClassVar[int]
    CAPTION_PROMPT_FIELD_NUMBER: _ClassVar[int]
    max_image_size_kb: int
    caption_prompt: str
    def __init__(self, max_image_size_kb: _Optional[int] = ..., caption_prompt: _Optional[str] = ...) -> None: ...

class UploadConfig(_message.Message):
    __slots__ = ("upload_dir", "max_file_size_mb", "allowed_extensions")
    UPLOAD_DIR_FIELD_NUMBER: _ClassVar[int]
    MAX_FILE_SIZE_MB_FIELD_NUMBER: _ClassVar[int]
    ALLOWED_EXTENSIONS_FIELD_NUMBER: _ClassVar[int]
    upload_dir: str
    max_file_size_mb: int
    allowed_extensions: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, upload_dir: _Optional[str] = ..., max_file_size_mb: _Optional[int] = ..., allowed_extensions: _Optional[_Iterable[str]] = ...) -> None: ...

class PIIConfig(_message.Message):
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

class DoclingConfig(_message.Message):
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

class AppConfig(_message.Message):
    __slots__ = ("ollama", "qdrant", "chunking", "image", "upload", "pii", "docling", "mounted_paths")
    OLLAMA_FIELD_NUMBER: _ClassVar[int]
    QDRANT_FIELD_NUMBER: _ClassVar[int]
    CHUNKING_FIELD_NUMBER: _ClassVar[int]
    IMAGE_FIELD_NUMBER: _ClassVar[int]
    UPLOAD_FIELD_NUMBER: _ClassVar[int]
    PII_FIELD_NUMBER: _ClassVar[int]
    DOCLING_FIELD_NUMBER: _ClassVar[int]
    MOUNTED_PATHS_FIELD_NUMBER: _ClassVar[int]
    ollama: OllamaConfig
    qdrant: QdrantConfig
    chunking: ChunkingConfig
    image: ImageConfig
    upload: UploadConfig
    pii: PIIConfig
    docling: DoclingConfig
    mounted_paths: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, ollama: _Optional[_Union[OllamaConfig, _Mapping]] = ..., qdrant: _Optional[_Union[QdrantConfig, _Mapping]] = ..., chunking: _Optional[_Union[ChunkingConfig, _Mapping]] = ..., image: _Optional[_Union[ImageConfig, _Mapping]] = ..., upload: _Optional[_Union[UploadConfig, _Mapping]] = ..., pii: _Optional[_Union[PIIConfig, _Mapping]] = ..., docling: _Optional[_Union[DoclingConfig, _Mapping]] = ..., mounted_paths: _Optional[_Iterable[str]] = ...) -> None: ...
